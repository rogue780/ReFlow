# Chapter 13: A Complete Application

The preceding twelve chapters introduced Flow's features one at a time. This chapter uses all of them at once.

We will build a log analysis pipeline: a program that ingests log lines in multiple formats, normalizes them into a common structure, filters by severity, counts and summarizes by category, handles malformed input with retry logic, and prints a report. The program is small enough to read in one sitting and large enough to require real design decisions about types, modules, error handling, and concurrency.

The application touches every major feature covered in this book: sum types, structs, interfaces, pure functions, composition chains, streams, coroutines, fan-out, pattern matching, option and result types, exception handling with retry, and module organization. If something from an earlier chapter felt abstract, this is where it becomes concrete.

---

## 13.1 The Problem

Server logs arrive in three formats, depending on which system produced them.

**Key-value format** (from the API tier):

```
ts=2024-01-15T09:30:00 level=ERROR src=api msg=connection_timeout
```

**CSV format** (from the database layer):

```
2024-01-15T09:30:01,WARN,db,slow_query_detected
```

**Space-delimited format** (from the web frontend):

```
2024-01-15T09:30:02 web INFO page_served
```

Some lines are malformed: missing fields, garbled encodings, truncated writes. The program must handle these without crashing.

The goals:

1. Parse each line, detecting the format automatically.
2. Normalize every line into a common `LogEntry` structure.
3. Filter entries by severity threshold.
4. Count entries by source and severity.
5. Handle malformed lines with retry (attempt to sanitize and re-parse).
6. Print a summary report.

This is a data transformation pipeline. Flow was built for exactly this kind of work.

---

## 13.2 Module Structure

A real project would split this into multiple files:

```
log_analyzer/
    main.flow           ; module log_analyzer.main
    models.flow         ; module log_analyzer.models
    parser.flow         ; module log_analyzer.parser
    pipeline.flow       ; module log_analyzer.pipeline
```

`models.flow` defines the data types: severity levels, log entries, the summary report, and the custom exception type. It has no logic --- just type definitions. `parser.flow` contains pure functions for detecting formats and parsing lines. Every function in this module is marked `fn:pure`; it has no I/O and no side effects. `pipeline.flow` assembles the stream processing stages, including the report accumulator and formatting functions. `main.flow` wires everything together, handles errors, and produces output.

The dependency graph is strictly one-directional:

```
main.flow  -->  pipeline.flow  -->  parser.flow  -->  models.flow
```

No module imports a module that imports it. No circular dependencies. This is not a convention; it is enforced by the compiler (Chapter 12).

In a multi-file project, the imports would look like this:

```flow
; main.flow
module log_analyzer.main
import log_analyzer.models (Severity, LogEntry, Report, ParseError)
import log_analyzer.parser (detect_and_parse, sanitize)
import log_analyzer.pipeline (format_entry, add_to_report, empty_report, print_report)
```

Each import names exactly which symbols it uses. The caller's namespace contains only what it asked for. This makes dependencies explicit at the top of every file --- you can see at a glance what a module depends on.

Since the examples in this book are single-file programs, the code below lives in one file with comments marking where each module boundary would fall. The structure is real; only the packaging is simplified.

---

## 13.3 Defining the Data Model

We start with the types. Every downstream function depends on these definitions, so they come first.

```flow
module log_analyzer
import io (println)
import string
import array
import conv

;; ============================================================
;; Module: log_analyzer.models
;; Types and sum types for the log analysis domain
;; ============================================================

; Severity is a sum type: exactly one of four levels.
; Adding a fifth level later will cause the compiler to flag
; every match that does not handle it.

type Severity =
    | Error
    | Warn
    | Info
    | Debug
```

Why a sum type instead of a string or an integer? Three reasons. First, the compiler enforces exhaustiveness: every `match` on `Severity` must handle all four variants or include a wildcard. If we add a `Fatal` variant next month, the compiler finds every place in the code that needs updating. Second, there is no way to construct an invalid severity. A string could be `"ERORR"` or `"warning"` or empty. A `Severity` is always one of the four defined variants. Third, pattern matching on sum types is cleaner than string comparison chains.

```flow
; A parsed log entry. All fields are strings for simplicity;
; a production system would parse the timestamp into a proper
; date type.

type LogEntry {
    timestamp: string
    severity: Severity
    source: string
    message: string
}
```

`LogEntry` is a struct with four fields. It is immutable by default. Once a `LogEntry` is constructed, its fields cannot change. This makes it safe to pass between pipeline stages, between threads, and between coroutines without copying.

```flow
; A report accumulates counts as it processes entries.

type Report {
    total: int
    errors: int
    warnings: int
    infos: int
    debugs: int
}
```

`Report` holds the running totals. We will build it up incrementally as entries flow through the pipeline.

We also need a way to represent parse failures as structured exceptions, not bare strings. This lets the retry mechanism inspect and correct the failing input.

```flow
; A typed exception for parse failures.
; Fulfills Exception<string> so retry blocks can access
; and modify the failing line via ex.data().

type ParseError fulfills Exception<string> {
    msg: string
    payload: string:mut
    original_payload: string

    fn message(self): string  { return self.msg }
    fn data(self): string     { return self.payload }
    fn original(self): string { return self.original_payload }
}
```

`ParseError` carries the failing line as its payload. The `payload` field is `:mut` so the retry block can modify it --- sanitize it, trim it, strip bad characters --- before the parser tries again. The `original_payload` is immutable: it preserves the line exactly as it was first seen, regardless of how many retry attempts modify the payload. This separation between correctable state and audit trail is central to Flow's retry model.

---

## 13.4 Parsing and Validation

The parser module is entirely pure functions. No I/O, no mutation of external state, no access to anything outside the function's parameters. This means every parser function is safe to test in isolation, safe to memoize, and safe to run in parallel fan-out.

### Severity Parsing

```flow
;; ============================================================
;; Module: log_analyzer.parser
;; Pure functions for parsing different log formats
;; ============================================================

fn:pure parse_severity(s: string): Severity {
    match s {
        "ERROR": { return Error }
        "WARN":  { return Warn }
        "INFO":  { return Info }
        "DEBUG": { return Debug }
        _: { return Debug }
    }
}
```

The wildcard arm maps any unrecognized severity string to `Debug`. This is a deliberate choice: unknown severity levels are not errors. They are low-priority entries from systems we have not catalogued yet. A stricter system could throw here; this one degrades gracefully.

### Format Detection

Log lines come in three formats. Rather than requiring the caller to specify the format, we detect it from the line's structure:

```flow
fn:pure detect_format(line: string): string {
    if (string.starts_with(line, "ts=")) { return "kv" }
    if (string.contains(line, ","))      { return "csv" }
    return "simple"
}
```

Key-value lines start with `ts=`. CSV lines contain commas. Everything else is space-delimited. This heuristic is imperfect --- a space-delimited line that happens to contain a comma would be misparsed as CSV. In a production system you would use a more robust detection scheme. For our purposes, the three formats are distinct enough that this works.

### The Three Parsers

Each parser takes a raw string and returns a `LogEntry`. If the line is too short or missing required fields, it throws a `ParseError`.

```flow
; Key-value format: ts=TIMESTAMP level=LEVEL src=SOURCE msg=MESSAGE
fn:pure parse_kv(line: string): LogEntry {
    let parts = string.split(line, " ")
    if (array.len_string(parts) < 4) {
        throw ParseError {
            msg: "kv: insufficient fields",
            payload: line,
            original_payload: line
        }
    }
    let ts    = string.replace(array.get(parts, 0) ?? "", "ts=", "")
    let level = string.replace(array.get(parts, 1) ?? "", "level=", "")
    let src   = string.replace(array.get(parts, 2) ?? "", "src=", "")
    let msg   = string.replace(array.get(parts, 3) ?? "", "msg=", "")
    return LogEntry {
        timestamp: ts,
        severity: parse_severity(level),
        source: src,
        message: msg
    }
}

; CSV format: TIMESTAMP,LEVEL,SOURCE,MESSAGE
fn:pure parse_csv(line: string): LogEntry {
    let parts = string.split(line, ",")
    if (array.len_string(parts) < 4) {
        throw ParseError {
            msg: "csv: insufficient fields",
            payload: line,
            original_payload: line
        }
    }
    return LogEntry {
        timestamp: array.get(parts, 0) ?? "",
        severity: parse_severity(array.get(parts, 1) ?? ""),
        source: array.get(parts, 2) ?? "",
        message: array.get(parts, 3) ?? ""
    }
}

; Space-delimited format: TIMESTAMP SOURCE LEVEL MESSAGE
fn:pure parse_simple(line: string): LogEntry {
    let parts = string.split(line, " ")
    if (array.len_string(parts) < 4) {
        throw ParseError {
            msg: "simple: insufficient fields",
            payload: line,
            original_payload: line
        }
    }
    return LogEntry {
        timestamp: array.get(parts, 0) ?? "",
        severity: parse_severity(array.get(parts, 2) ?? ""),
        source: array.get(parts, 1) ?? "",
        message: array.get(parts, 3) ?? ""
    }
}
```

Notice the field order difference. In key-value format, fields are labeled, so order does not matter (we extract by prefix). In CSV, the order is timestamp, level, source, message. In space-delimited, it is timestamp, source, level, message --- source and level are swapped. Each parser knows its format's conventions.

All three parsers use `array.get` with `??` to provide empty-string defaults for individual fields. The field-count check at the top catches lines that are clearly too short before we attempt to extract fields. This two-level approach --- structural validation first, field extraction second --- keeps the error messages informative.

### The Dispatch Function

```flow
fn:pure detect_and_parse(line: string): LogEntry {
    let fmt = detect_format(line)
    match fmt {
        "kv":     { return parse_kv(line) }
        "csv":    { return parse_csv(line) }
        _:        { return parse_simple(line) }
    }
}
```

`detect_and_parse` is the single entry point for parsing. Callers do not need to know which format a line uses. They pass a raw string and get back a `LogEntry` or a `ParseError`. The function is pure: same input, same output, no side effects.

### Sanitization

When a line fails to parse, the retry block needs a way to clean it up before trying again. `sanitize` strips common sources of corruption:

```flow
fn:pure sanitize(line: string): string {
    let cleaned = string.replace(line, "\t", " ")
    let trimmed = string.trim(cleaned)
    return trimmed
}
```

This is intentionally simple. Tabs become spaces (fixing lines where a tab character split a field), and leading/trailing whitespace is removed. A production sanitizer would handle encoding issues, escaped characters, and partial writes. The structure is the same: a pure function that takes a bad string and returns a better one.

---

## 13.5 Stream Processing with Composition

With the types and parsers defined, we can build the processing pipeline. The key insight is that each stage is a small function, and composition connects them.

### Producing a Stream of Lines

In a real system, lines come from a file or a network socket. Here we produce them from an array:

```flow
;; ============================================================
;; Module: log_analyzer.pipeline
;; Stream processing stages
;; ============================================================

fn line_source(lines: array<string>): stream<string> {
    for (line: string in lines) {
        yield line
    }
}
```

`line_source` converts an array into a stream. The `yield` keyword produces one value at a time. The consumer pulls values lazily: nothing happens until someone iterates the stream. Replacing this function with one that reads from a file would change nothing downstream --- the rest of the pipeline consumes `stream<string>` regardless of where the strings came from.

This is the adapter pattern. The rest of the pipeline does not know or care whether its input comes from an array, a file, a network socket, or a coroutine. It consumes `stream<string>`. The source function is the only piece that needs to change when the input medium changes.

A file-backed version would look like this:

```flow
fn file_source(path: string): stream<string> {
    let handle = file.open(path)
    for (line: string in handle) {
        yield line
    }
} finally {
    handle.close()
}
```

The `finally` block on the function ensures the file handle is closed when the stream is exhausted or abandoned. The rest of the pipeline is identical.

### Filtering by Severity

```flow
fn:pure severity_at_least(entry: LogEntry, threshold: Severity): bool {
    let entry_level = severity_to_int(entry.severity)
    let threshold_level = severity_to_int(threshold)
    return entry_level <= threshold_level
}

fn:pure severity_to_int(s: Severity): int {
    match s {
        Error: { return 0 }
        Warn:  { return 1 }
        Info:  { return 2 }
        Debug: { return 3 }
    }
}
```

`severity_to_int` maps each variant to a numeric level. Lower numbers mean higher severity. `severity_at_least` compares an entry's severity against a threshold. Both are pure.

### Formatting

```flow
fn:pure severity_label(s: Severity): string {
    match s {
        Error: { return "ERROR" }
        Warn:  { return "WARN" }
        Info:  { return "INFO" }
        Debug: { return "DEBUG" }
    }
}

fn:pure format_entry(entry: LogEntry): string {
    return "[" + severity_label(entry.severity) + "] "
         + entry.timestamp + " "
         + entry.source + ": "
         + entry.message
}
```

`format_entry` produces a normalized output string regardless of the original format. Every entry looks the same after formatting. This is the value of normalizing to a common type early in the pipeline: downstream stages do not care whether the original line was key-value, CSV, or space-delimited.

### Building the Report

The report accumulator takes the current report and a new entry, and returns an updated report:

```flow
fn:pure add_to_report(report: Report, entry: LogEntry): Report {
    let new_errors   = report.errors + (match entry.severity { Error: { 1 } _: { 0 } })
    let new_warnings = report.warnings + (match entry.severity { Warn: { 1 } _: { 0 } })
    let new_infos    = report.infos + (match entry.severity { Info: { 1 } _: { 0 } })
    let new_debugs   = report.debugs + (match entry.severity { Debug: { 1 } _: { 0 } })
    return Report {
        total: report.total + 1,
        errors: new_errors,
        warnings: new_warnings,
        infos: new_infos,
        debugs: new_debugs
    }
}
```

The function is pure. It does not mutate the existing report; it returns a new one with updated counts. This is a fold: we will start with an empty report and accumulate each entry into it.

```flow
fn:pure empty_report(): Report {
    return Report {
        total: 0,
        errors: 0,
        warnings: 0,
        infos: 0,
        debugs: 0
    }
}
```

### Fan-Out: Multiple Outputs from One Entry

Sometimes you need to send each entry to multiple destinations. Flow's fan-out operator handles this directly. Suppose we want both a formatted line for display and a severity label for counting:

```flow
fn:pure format_and_label(entry: LogEntry): string {
    let formatted = format_entry(entry)
    let label = severity_label(entry.severity)
    return formatted + " [" + label + "]"
}
```

In a composition chain, fan-out lets you split a value to multiple functions and combine the results:

```flow
; Fan-out: entry goes to both format_entry and severity_label,
; results are combined by build_display_line
fn:pure build_display_line(formatted: string, label: string): string {
    return formatted + " [" + label + "]"
}

; Usage in a chain:
; entry -> (format_entry | severity_label) -> build_display_line
```

The entry flows into `format_entry` and `severity_label` simultaneously. `format_entry` produces a formatted string; `severity_label` produces a label. Both results are pushed onto the value stack and consumed by `build_display_line`, which takes two arguments. The types align, the arity matches, and the compiler verifies it all statically.

---

## 13.6 Concurrent Processing with Coroutines

For a small batch of log lines, sequential processing is fine. For a continuous stream --- tailing a live log file, ingesting from a network socket --- you want concurrency. The parsing stage is CPU-bound (string splitting, format detection), and it can run on a separate thread while the main thread handles output.

### A Coroutine Producer

```flow
fn parse_worker(inbox: stream<string>): stream<LogEntry> {
    for (line: string in inbox) {
        let entry = detect_and_parse(line)
        yield entry
    }
}
```

`parse_worker` is a receivable coroutine. Its first parameter is `stream<string>` --- the inbox. The runtime automatically creates this inbox and wires it to the coroutine handle's `.send()` method. Each line sent to the coroutine is parsed and yielded as a `LogEntry`.

Spawning it:

```flow
let parser :< parse_worker()
parser.send("ts=2024-01-15T09:30:00 level=ERROR src=api msg=timeout")
match parser.next() {
    some(entry): { println(format_entry(entry)) }
    none: {}
}
```

The coroutine runs on a separate thread. The main thread sends lines via `.send()` and reads parsed entries via `.next()`. Backpressure is automatic: if the parser falls behind, `.send()` blocks until the parser catches up. If the main thread falls behind reading entries, the parser blocks on `yield` until the output channel has room.

### Multiple Concurrent Producers

For higher throughput, spawn multiple parsers:

```flow
fn run_parallel_parsers(lines: array<string>) {
    let p1 :< parse_worker()
    let p2 :< parse_worker()

    ; Distribute lines round-robin across parsers
    let i: int:mut = 0
    for (line: string in lines) {
        if (i % 2 == 0) {
            p1.send(line)
        } else {
            p2.send(line)
        }
        i = i + 1
    }

    ; Collect results
    ; (In practice, you would interleave reads with sends
    ; to avoid deadlock with bounded channels)
}
```

Each parser runs on its own thread. Lines are distributed round-robin. The parsers share no mutable state --- `detect_and_parse` is pure, and each coroutine has its own local variables. This is safe concurrency without locks, without mutexes, without `synchronized` blocks. Immutable data and pure functions make it possible.

### Configurable Buffer Capacity

The default channel capacity for a coroutine is 64. For a parsing pipeline where lines arrive in bursts, a larger buffer smooths out latency:

```flow
fn parse_worker_buffered(inbox: stream<string>[128]): stream<LogEntry>[256] {
    for (line: string in inbox) {
        let entry = detect_and_parse(line)
        yield entry
    }
}
```

The `[128]` on the inbox means the sender can push up to 128 lines before blocking. The `[256]` on the return type means the parser can yield up to 256 entries before blocking on a slow consumer. These numbers are runtime hints, not type distinctions --- `stream<string>[128]` and `stream<string>` are the same type for the type checker.

A capacity of 1 creates tight lock-step synchronization: the producer advances exactly one step ahead of the consumer. This minimizes memory usage but maximizes blocking. A larger capacity allows the producer to run ahead during bursts, smoothing throughput. The right number depends on the workload. For log parsing, 64 to 256 is typically sufficient.

### When Concurrency Helps

Coroutines add overhead: thread creation, channel synchronization, context switching. For ten log lines, sequential processing is faster. For ten thousand lines arriving continuously from a network socket, the ability to parse on one thread while writing to disk on another makes a measurable difference.

The rule from Chapter 10 applies: use coroutines when stages are expensive enough that concurrent execution outweighs the overhead. Parsing is a good candidate because it involves string splitting, format detection, and field extraction --- operations that take microseconds per line but add up over millions of lines.

### Coroutine Lifetime

When the coroutine handle goes out of scope, the runtime closes the channels and joins the producer thread. If the producer is blocked on a full output channel or an empty inbox, the close unblocks it. You do not need to explicitly shut down a coroutine. The ownership model handles it: when the handle is freed, the thread is cleaned up.

This matters for error recovery. If the main thread catches an exception and abandons the coroutine, the producer thread is still cleaned up properly. No resource leaks, no orphaned threads.

---

## 13.7 Error Handling and Retry

Not every log line is well-formed. Truncated writes, encoding errors, and garbled network output produce lines that no parser can handle. The program must recover gracefully: attempt to fix the line, try again, and skip it if all attempts fail.

### The Retry Pattern

Flow's `try`/`retry`/`catch` mechanism is designed for exactly this situation. The retry block names the function to re-invoke, receives the exception, corrects the data, and lets the runtime call the function again:

```flow
fn process_line(line: string): option<LogEntry> {
    try {
        let entry = detect_and_parse(line)
        return some(entry)
    } retry detect_and_parse (ex: ParseError, attempts: 2) {
        ; The parse failed. Sanitize the line and try again.
        ; ex.data is mutable: we modify the payload before retry.
        ex.payload = sanitize(ex.data())
    } catch (ex: ParseError) {
        ; All retries exhausted. Log the failure and move on.
        println("SKIP: " + ex.message()
              + " | original: " + ex.original()
              + " | last attempt: " + ex.data())
        return none
    }
}
```

Trace through a malformed line like `"corrupt???\tbad"`:

1. `detect_and_parse` is called with `"corrupt???\tbad"`. The line has no `ts=` prefix and no comma, so it falls through to `parse_simple`. `parse_simple` splits on spaces, gets fewer than four parts, and throws a `ParseError`.

2. The `retry` block catches the exception. `ex.data()` returns `"corrupt???\tbad"`. The block calls `sanitize`, which replaces the tab with a space and trims whitespace, producing `"corrupt??? bad"`. This sanitized string is assigned back to `ex.payload`.

3. `detect_and_parse` runs again with `"corrupt??? bad"`. It still has only two space-separated tokens, so it throws again.

4. The retry counter has reached 2 attempts. The exception falls through to `catch`.

5. The `catch` block prints a diagnostic message showing both the original input and the last sanitized attempt, then returns `none`.

6. The caller sees `none` and skips this line.

The key design elements:

- **`retry` names the function**, not just the block. The runtime re-invokes `detect_and_parse` specifically, with the corrected payload. The rest of any composition chain that follows `detect_and_parse` runs normally if the retry succeeds.

- **`ex.data()` is mutable in the retry block.** This is where you apply corrections. Sanitize the string, fill in a default field, strip invalid characters --- whatever the domain requires.

- **`ex.original()` is immutable.** It preserves the input exactly as it was when the exception was first thrown. This is your audit trail. Log it, store it, inspect it later.

- **`catch` runs after all retries are exhausted.** `ex.data()` in the catch block holds the last corrected value. `ex.original()` is unchanged.

### Why Not Just Use `if`?

You could check for errors with an `if` statement and handle them manually. The retry mechanism provides three things that manual error handling does not:

1. **Automatic re-invocation.** The runtime calls the named function again. You do not need to reconstruct the call, manage a loop counter, or track which attempt you are on.

2. **Structured data flow.** `ex.data()`, `ex.original()`, and `ex.message()` give you access to the failing payload, the original input, and the error description through a consistent interface. Every exception type uses the same protocol.

3. **Composition integration.** In a composition chain like `line -> detect_and_parse -> validate -> write`, a retry on `detect_and_parse` re-runs only that stage. If the retry succeeds, the result flows into `validate -> write` as if nothing went wrong. Manual error handling would require breaking the chain apart.

---

## 13.8 Putting It All Together

Here is the complete program. Each section is marked with the module it would belong to in a multi-file project.

```flow
module log_analyzer

import io (println)
import string
import array
import conv

;; ============================================================
;; Module: log_analyzer.models
;; ============================================================

type Severity =
    | Error
    | Warn
    | Info
    | Debug

type LogEntry {
    timestamp: string
    severity: Severity
    source: string
    message: string
}

type Report {
    total: int
    errors: int
    warnings: int
    infos: int
    debugs: int
}

type ParseError fulfills Exception<string> {
    msg: string
    payload: string:mut
    original_payload: string

    fn message(self): string  { return self.msg }
    fn data(self): string     { return self.payload }
    fn original(self): string { return self.original_payload }
}

;; ============================================================
;; Module: log_analyzer.parser
;; ============================================================

fn:pure parse_severity(s: string): Severity {
    match s {
        "ERROR": { return Error }
        "WARN":  { return Warn }
        "INFO":  { return Info }
        "DEBUG": { return Debug }
        _: { return Debug }
    }
}

fn:pure severity_to_int(s: Severity): int {
    match s {
        Error: { return 0 }
        Warn:  { return 1 }
        Info:  { return 2 }
        Debug: { return 3 }
    }
}

fn:pure severity_label(s: Severity): string {
    match s {
        Error: { return "ERROR" }
        Warn:  { return "WARN" }
        Info:  { return "INFO" }
        Debug: { return "DEBUG" }
    }
}

fn:pure parse_kv(line: string): LogEntry {
    let parts = string.split(line, " ")
    if (array.len_string(parts) < 4) {
        throw ParseError {
            msg: "kv: insufficient fields",
            payload: line,
            original_payload: line
        }
    }
    let ts    = string.replace(array.get(parts, 0) ?? "", "ts=", "")
    let level = string.replace(array.get(parts, 1) ?? "", "level=", "")
    let src   = string.replace(array.get(parts, 2) ?? "", "src=", "")
    let msg   = string.replace(array.get(parts, 3) ?? "", "msg=", "")
    return LogEntry {
        timestamp: ts,
        severity: parse_severity(level),
        source: src,
        message: msg
    }
}

fn:pure parse_csv(line: string): LogEntry {
    let parts = string.split(line, ",")
    if (array.len_string(parts) < 4) {
        throw ParseError {
            msg: "csv: insufficient fields",
            payload: line,
            original_payload: line
        }
    }
    return LogEntry {
        timestamp: array.get(parts, 0) ?? "",
        severity: parse_severity(array.get(parts, 1) ?? ""),
        source: array.get(parts, 2) ?? "",
        message: array.get(parts, 3) ?? ""
    }
}

fn:pure parse_simple(line: string): LogEntry {
    let parts = string.split(line, " ")
    if (array.len_string(parts) < 4) {
        throw ParseError {
            msg: "simple: insufficient fields",
            payload: line,
            original_payload: line
        }
    }
    return LogEntry {
        timestamp: array.get(parts, 0) ?? "",
        severity: parse_severity(array.get(parts, 2) ?? ""),
        source: array.get(parts, 1) ?? "",
        message: array.get(parts, 3) ?? ""
    }
}

fn:pure detect_and_parse(line: string): LogEntry {
    if (string.starts_with(line, "ts=")) { return parse_kv(line) }
    if (string.contains(line, ","))      { return parse_csv(line) }
    return parse_simple(line)
}

fn:pure sanitize(line: string): string {
    let cleaned = string.replace(line, "\t", " ")
    return string.trim(cleaned)
}

;; ============================================================
;; Module: log_analyzer.pipeline
;; ============================================================

fn:pure format_entry(entry: LogEntry): string {
    return "[" + severity_label(entry.severity) + "] "
         + entry.timestamp + " "
         + entry.source + ": "
         + entry.message
}

fn:pure add_to_report(report: Report, entry: LogEntry): Report {
    let new_errors = report.errors
        + (match entry.severity { Error: { 1 } _: { 0 } })
    let new_warnings = report.warnings
        + (match entry.severity { Warn: { 1 } _: { 0 } })
    let new_infos = report.infos
        + (match entry.severity { Info: { 1 } _: { 0 } })
    let new_debugs = report.debugs
        + (match entry.severity { Debug: { 1 } _: { 0 } })
    return Report {
        total: report.total + 1,
        errors: new_errors,
        warnings: new_warnings,
        infos: new_infos,
        debugs: new_debugs
    }
}

fn:pure empty_report(): Report {
    return Report {
        total: 0, errors: 0, warnings: 0, infos: 0, debugs: 0
    }
}

fn print_report(report: Report) {
    println("========== LOG ANALYSIS REPORT ==========")
    println(f"Total entries: {report.total}")
    println(f"  Errors:      {report.errors}")
    println(f"  Warnings:    {report.warnings}")
    println(f"  Info:        {report.infos}")
    println(f"  Debug:       {report.debugs}")
    println("==========================================")
}

;; ============================================================
;; Module: log_analyzer.main
;; ============================================================

fn process_line(line: string): option<LogEntry> {
    try {
        let entry = detect_and_parse(line)
        return some(entry)
    } retry detect_and_parse (ex: ParseError, attempts: 2) {
        ex.payload = sanitize(ex.data())
    } catch (ex: ParseError) {
        println("SKIP: " + ex.message()
              + " | line: " + ex.original())
        return none
    }
}

fn main() {
    ; Sample log data: three formats plus two malformed lines
    let lines = [
        "ts=2024-01-15T09:30:00 level=ERROR src=api msg=connection_timeout",
        "ts=2024-01-15T09:30:01 level=WARN src=api msg=high_latency",
        "2024-01-15T09:30:02,INFO,db,connected_successfully",
        "2024-01-15T09:30:03,WARN,db,slow_query_detected",
        "2024-01-15T09:30:04,ERROR,db,replication_lag",
        "2024-01-15T09:30:05 web INFO page_served",
        "2024-01-15T09:30:06 web DEBUG cache_hit",
        "corrupt???",
        "2024-01-15T09:30:07,ERROR,api,request_failed",
        "",
        "ts=2024-01-15T09:30:08 level=INFO src=web msg=health_check_ok",
        "2024-01-15T09:30:09 api WARN rate_limit_approaching"
    ]

    println("Processing log entries...")
    println("")

    let report: Report:mut = empty_report()
    let skipped: int:mut = 0

    for (line: string in lines) {
        ; Skip empty lines
        if (string.len(line) == 0) {
            skipped = skipped + 1
            continue
        }

        let result = process_line(line)
        match result {
            some(entry): {
                ; Print the formatted entry
                println(format_entry(entry))

                ; Accumulate into the report
                report = add_to_report(report, entry)
            }
            none: {
                skipped = skipped + 1
            }
        }
    } finally {
        println("")
        print_report(report)
        println(f"Skipped lines: {skipped}")
    }
}
```

Running this program:

```
$ flow run log_analyzer.flow
Processing log entries...

[ERROR] 2024-01-15T09:30:00 api: connection_timeout
[WARN] 2024-01-15T09:30:01 api: high_latency
[INFO] 2024-01-15T09:30:02 db: connected_successfully
[WARN] 2024-01-15T09:30:03 db: slow_query_detected
[ERROR] 2024-01-15T09:30:04 db: replication_lag
[INFO] 2024-01-15T09:30:05 web: page_served
[DEBUG] 2024-01-15T09:30:06 web: cache_hit
SKIP: simple: insufficient fields | line: corrupt???
[ERROR] 2024-01-15T09:30:07 api: request_failed
[INFO] 2024-01-15T09:30:08 web: health_check_ok
[WARN] 2024-01-15T09:30:09 api: rate_limit_approaching

========== LOG ANALYSIS REPORT ==========
Total entries: 10
  Errors:      3
  Warnings:    3
  Info:        3
  Debug:       1
==========================================
Skipped lines: 2
```

Trace the data flow:

1. Twelve lines enter the `for` loop.
2. Empty lines are caught by the length check and skipped.
3. Each non-empty line enters `process_line`, which calls `detect_and_parse`.
4. Well-formed lines parse successfully and return `some(entry)`.
5. `"corrupt???"` fails to parse (only one token). The retry block sanitizes it (trimming does not help; there is only one token), and the second attempt also fails. The catch block prints a diagnostic and returns `none`.
6. Each successful entry is formatted and printed, then folded into the running report.
7. After the loop, the `finally` block prints the summary.

---

## 13.9 Using Composition Chains

The main loop above uses explicit `let` bindings and a `match` statement. Let us refactor the successful path into a composition chain to see how the same logic looks in pipeline style.

### Fan-Out for Display and Reporting

When an entry is successfully parsed, we do two things with it: format it for display and fold it into the report. This is a fan-out:

```flow
fn process_entry(entry: LogEntry, report: Report): Report {
    ; Fan-out: entry goes to both format_entry and severity_label
    let display = entry -> (format_entry | severity_label)
                        -> build_display_line
    println(display)
    return add_to_report(report, entry)
}

fn:pure build_display_line(formatted: string, label: string): string {
    return formatted + " [" + label + "]"
}
```

The fan-out `(format_entry | severity_label)` sends the entry to both functions. Their results --- a formatted string and a severity label --- are consumed by `build_display_line`, which takes two arguments. The types check: `format_entry` returns `string`, `severity_label` returns `string`, and `build_display_line` takes `(string, string)`.

### Composition with Auto-Mapping

If you have a stream of log entries, auto-mapping lets you apply per-entry functions across the entire stream without an explicit loop:

```flow
fn line_source(lines: array<string>): stream<string> {
    for (line: string in lines) {
        if (string.len(line) > 0) {
            yield line
        }
    }
}

; In a composition chain:
; lines -> line_source -> detect_and_parse -> format_entry
;
; line_source produces stream<string>
; detect_and_parse takes string, returns LogEntry -> auto-mapped
; format_entry takes LogEntry, returns string -> auto-mapped
; Result: stream<string> of formatted log entries
```

Each stage is a small function. Composition connects them. Auto-mapping handles the iteration. The pipeline reads as a description of the transformation, not as a sequence of loop instructions.

This is the most important design pattern in Flow. You write each function for a single value. Composition lifts it to work on streams. You do not write two versions of `detect_and_parse` --- one for a single string and one for a stream of strings. The single-value version works in both contexts. When a `stream<string>` flows into a function expecting `string`, the runtime auto-maps: it applies the function to each element and produces a `stream<LogEntry>`. This is not magic; it is a type-directed transformation that the compiler verifies statically.

The stream pipeline also composes with stream helpers from the standard library:

```flow
; Filter, transform, and take the first N entries
fn first_errors(lines: array<string>, n: int): stream<string> {
    let entries = line_source(lines)
    for (line: string in entries) {
        let result = process_line(line)
        match result {
            some(entry): {
                match entry.severity {
                    Error: { yield format_entry(entry) }
                    _: {}
                }
            }
            none: {}
        }
    }
}
```

Or more concisely with stream helpers:

```flow
; Using take to limit output
for (line: string in first_errors(lines, 5).take(5)) {
    println(line)
}
```

`.take(5)` stops the stream after five values, regardless of how many the source could produce. The producer does not run unnecessarily --- backpressure ensures it stops yielding when the consumer stops pulling.

### Concurrent Pipeline with Coroutines

For heavy workloads, wrap the parsing stage in a coroutine:

```flow
fn parse_stage(inbox: stream<string>): stream<LogEntry> {
    for (line: string in inbox) {
        try {
            yield detect_and_parse(line)
        } catch (ex: ParseError) {
            ; skip malformed lines in the coroutine
            ; (in production, yield an error variant instead)
        }
    }
}

fn run_concurrent(lines: array<string>) {
    let parser :< parse_stage()

    ; Feed lines to the parser coroutine
    for (line: string in lines) {
        if (string.len(line) > 0) {
            parser.send(line)
        }
    }

    ; Read parsed entries
    let report: Report:mut = empty_report()
    while (!parser.done()) {
        match parser.next() {
            some(entry): {
                println(format_entry(entry))
                report = add_to_report(report, entry)
            }
            none: {}
        }
    }
    print_report(report)
}
```

The parser runs on a separate thread. The main thread sends lines and reads results. Backpressure is automatic: if the parser is slower than the sender, `.send()` blocks. If the sender is slower than the parser, `.next()` blocks.

Note the trade-off. The sequential version handles errors with retry: it attempts to sanitize and re-parse each malformed line. The concurrent version skips errors silently. This is not a limitation of coroutines; you could implement retry inside the coroutine. But the code is more complex, and the benefit depends on how many lines are malformed. For a stream where 99.9% of lines are valid, skipping the rare bad line is pragmatic. For a stream with significant corruption, the sequential version with retry is better.

---

## 13.10 Extending the Application

The design of this program makes several kinds of extensions straightforward. Each extension touches one part of the code and leaves the rest unchanged.

### Adding a New Log Format

Suppose a new system produces JSON-formatted log lines:

```
{"ts":"2024-01-15T09:30:10","level":"ERROR","src":"queue","msg":"overflow"}
```

To add support:

1. Write a new pure parser function:

```flow
fn:pure parse_json_log(line: string): LogEntry {
    ; Extract fields from the JSON string
    ; (Uses the json module or manual string parsing)
    ...
}
```

2. Update `detect_format` and `detect_and_parse`:

```flow
fn:pure detect_and_parse(line: string): LogEntry {
    if (string.starts_with(line, "ts=")) { return parse_kv(line) }
    if (string.starts_with(line, "{"))   { return parse_json_log(line) }
    if (string.contains(line, ","))      { return parse_csv(line) }
    return parse_simple(line)
}
```

Nothing else changes. The pipeline, the report, the error handling, the formatting --- all untouched. The new format is a new parser function and a new detection case. The rest of the program processes `LogEntry` values, and it does not care where they came from.

### Adding a New Severity Level

Suppose we add a `Fatal` severity:

```flow
type Severity =
    | Fatal
    | Error
    | Warn
    | Info
    | Debug
```

The compiler immediately flags every `match` expression on `Severity` that does not handle `Fatal`. There are four:

- `parse_severity` --- add a `"FATAL"` case
- `severity_to_int` --- assign it level 0 (or -1 if you want it higher than Error)
- `severity_label` --- add `Fatal: { return "FATAL" }`
- `add_to_report` --- add a counter for `Fatal`

The compiler-driven approach means you cannot forget. Every incomplete match is a compile error. This is one of the concrete benefits of sum types over strings or integers: the type system tracks which values exist and forces you to handle all of them.

### Adding a New Output Target

Suppose you want to write entries to a file in addition to printing them. Add a new function and call it alongside `println`:

```flow
fn write_to_file(entry: LogEntry, path: string) {
    let line = format_entry(entry)
    file.append(path, line + "\n")
}
```

Or use fan-out to send each entry to multiple destinations:

```flow
; entry -> (format_for_console | format_for_file)
;       -> (println | write_to_file)
```

Fan-out is not limited to pure functions. The branches can perform I/O, as long as they do not share mutable state. Sequential fan-out (`|`) evaluates branches one at a time, so there is no concurrency issue. Parallel fan-out (`<:()`) requires pure functions or functions that do not access mutable statics.

### Scaling the Processing

The coroutine version from Section 13.9 uses one parser thread. For higher throughput, add more:

```flow
fn run_scaled(lines: array<string>) {
    let p1 :< parse_stage()
    let p2 :< parse_stage()
    let p3 :< parse_stage()

    ; Distribute lines across parsers
    let i: int:mut = 0
    for (line: string in lines) {
        if (string.len(line) > 0) {
            match i % 3 {
                0: { p1.send(line) }
                1: { p2.send(line) }
                _: { p3.send(line) }
            }
            i = i + 1
        }
    }

    ; Collect from all three
    ; ...
}
```

Each `parse_stage` coroutine runs on its own thread. `detect_and_parse` is pure, so running multiple instances concurrently is safe. The scaling is linear: more parsers, more throughput, up to the number of available cores.

### Adding Source-Level Grouping

The report currently counts by severity. To add per-source counts, use a map:

```flow
import map

fn build_source_report(entries: array<LogEntry>): map<string, int> {
    let counts: map<string, int>:mut = map.new()
    for (entry: LogEntry in entries) {
        let current = map.get(counts, entry.source) ?? 0
        counts = map.set(counts, entry.source, current + 1)
    }
    return counts
}
```

Maps are immutable by default. `map.set` returns a new map with the added entry. The `:mut` binding allows us to rebind `counts` to the new map on each iteration. This is not in-place mutation --- each `set` produces a new map --- but the old maps are freed as soon as the binding is rebound.

---

## 13.11 Design Decisions

Several design choices in this program are worth examining explicitly.

### Pure Parsers, Impure Main Loop

The parsers are pure. The main loop is not --- it prints to the console, accumulates a mutable report, and tracks a skip counter. This is intentional. Purity should be applied where it adds value: the parsing functions benefit from testability, memoizability, and parallelizability. The main loop orchestrates side effects. Forcing it to be pure would add complexity without benefit.

The general principle: push purity as deep as possible. The leaves of the call tree --- parsers, formatters, validators --- should be pure. The root --- the main function, the I/O orchestration --- is where effects belong.

### Sum Types Over Strings

Severity is a sum type, not a string. This costs a few extra lines of definition but saves hours of debugging. String comparisons are case-sensitive, typo-prone, and invisible to the compiler. Sum type matches are exhaustive, compiler-checked, and impossible to misspell.

The `parse_severity` function is the boundary: it converts an external string (untrusted, unvalidated) into an internal sum type (trusted, validated). After that boundary, every function works with `Severity`, not with strings. This pattern --- parse external data into internal types at the boundary, work with internal types everywhere else --- is worth adopting in every Flow program.

### Immutable Data with Mutable Accumulators

The `Report` struct is immutable. The binding `report: Report:mut` is mutable --- it can be rebound to a new `Report` --- but the structs themselves are not modified. `add_to_report` takes a report and returns a new one.

This is Flow's standard pattern for accumulation. You do not mutate the old state; you produce new state and rebind the variable. The old state is freed when no references remain. For small structs like `Report`, this is negligible overhead. For large collections, Flow's reference counting ensures that shared data is not copied unnecessarily.

### Error Handling at the Right Level

Parse errors are thrown as exceptions, not returned as results. This is deliberate. The parsers are pure functions that transform strings to `LogEntry` values. In the common case --- well-formed input --- they return successfully. The exceptional case --- malformed input --- is genuinely exceptional: it represents corrupted data, not an expected failure mode.

The `process_line` function catches these exceptions and converts them to `option<LogEntry>`. This is where the boundary sits: below this function, exceptions fly. Above it, callers work with options. The retry logic lives exactly at this boundary, where the exception is caught and the correction is applied.

If malformed input were common rather than exceptional --- if, say, half the lines were unparseable --- `result<LogEntry, ParseError>` would be more appropriate. The choice between exceptions and results depends on how common the failure is, not on how severe it is.

---

## 13.12 Testing the Application

Every function in this program is testable in isolation. The pure functions are the easiest: call them with known input, check the output.

### Testing Parsers

```flow
; Unit tests for parse_kv
fn test_parse_kv() {
    let entry = parse_kv("ts=2024-01-15 level=ERROR src=api msg=timeout")
    assert(entry.timestamp == "2024-01-15")
    assert(entry.source == "api")
    assert(entry.message == "timeout")
    match entry.severity {
        Error: {} ; expected
        _: { throw "wrong severity" }
    }
}

; Unit tests for parse_csv
fn test_parse_csv() {
    let entry = parse_csv("2024-01-15,WARN,db,slow_query")
    assert(entry.timestamp == "2024-01-15")
    assert(entry.source == "db")
    match entry.severity {
        Warn: {} ; expected
        _: { throw "wrong severity" }
    }
}
```

### Testing Error Handling

```flow
; Test that malformed lines throw ParseError
fn test_malformed_throws() {
    try {
        let entry = detect_and_parse("garbage")
        throw "should have thrown"
    } catch (ex: ParseError) {
        assert(ex.original() == "garbage")
    }
}
```

### Testing the Report Accumulator

```flow
fn test_report_accumulation() {
    let r = empty_report()
    let e1 = LogEntry {
        timestamp: "t1", severity: Error,
        source: "api", message: "fail"
    }
    let e2 = LogEntry {
        timestamp: "t2", severity: Warn,
        source: "db", message: "slow"
    }
    let r = add_to_report(r, e1)
    let r = add_to_report(r, e2)
    assert(r.total == 2)
    assert(r.errors == 1)
    assert(r.warnings == 1)
}
```

Because `add_to_report` is pure and takes explicit inputs, testing it requires no setup, no mocking, no test fixtures. You construct inputs, call the function, and check the output. This is the payoff of the composition-first design: small pure functions are inherently testable.

### Testing Format Detection

```flow
fn test_format_detection() {
    ; Key-value lines start with ts=
    let kv_entry = detect_and_parse(
        "ts=2024-01-15 level=WARN src=api msg=slow")
    match kv_entry.severity {
        Warn: {}
        _: { throw "expected Warn" }
    }
    assert(kv_entry.source == "api")

    ; CSV lines contain commas
    let csv_entry = detect_and_parse(
        "2024-01-15,ERROR,db,connection_lost")
    match csv_entry.severity {
        Error: {}
        _: { throw "expected Error" }
    }
    assert(csv_entry.source == "db")

    ; Everything else is space-delimited
    let simple_entry = detect_and_parse(
        "2024-01-15 web INFO page_rendered")
    match simple_entry.severity {
        Info: {}
        _: { throw "expected Info" }
    }
    assert(simple_entry.source == "web")
}
```

Each test constructs a line in a specific format, parses it, and verifies that the correct parser was selected by checking the extracted fields. The three parsers extract fields from different positions, so a wrong parser choice produces wrong values --- the test catches it.

### Testing Sanitization and Retry

```flow
fn test_sanitize() {
    ; Tab characters become spaces
    assert(sanitize("hello\tworld") == "hello world")

    ; Leading and trailing whitespace removed
    assert(sanitize("  padded  ") == "padded")

    ; Combined: tab and whitespace
    assert(sanitize("  a\tb  ") == "a b")
}

fn test_retry_behavior() {
    ; A line that is malformed but fixable by sanitization
    ; "ts=2024\tlevel=WARN\tsrc=api\tmsg=ok" has tabs instead of spaces
    ; After sanitize: "ts=2024 level=WARN src=api msg=ok" which parses as kv
    let result = process_line("ts=2024\tlevel=WARN\tsrc=api\tmsg=ok")
    match result {
        some(entry): {
            assert(entry.source == "api")
            match entry.severity {
                Warn: {}
                _: { throw "expected Warn" }
            }
        }
        none: { throw "expected successful parse after retry" }
    }
}
```

The retry test verifies that a line with tab-separated fields fails on the first attempt (tabs are not spaces; `string.split` on `" "` produces one big token), gets sanitized (tabs become spaces), and succeeds on the second attempt. This is the concrete benefit of the retry mechanism: fixable errors are fixed automatically.

### End-to-End Testing

For the full pipeline, provide known input and check the output:

```flow
fn test_end_to_end() {
    let lines = [
        "ts=2024-01-15 level=ERROR src=api msg=fail",
        "corrupt",
        "2024-01-15,INFO,db,ok"
    ]

    let report: Report:mut = empty_report()
    let skipped: int:mut = 0

    for (line: string in lines) {
        if (string.len(line) == 0) { continue }
        match process_line(line) {
            some(entry): { report = add_to_report(report, entry) }
            none: { skipped = skipped + 1 }
        }
    }

    assert(report.total == 2)
    assert(report.errors == 1)
    assert(report.infos == 1)
    assert(skipped == 1)
}
```

This test exercises parsing, error handling, and report accumulation in a single pass. The corrupt line is skipped; the two valid lines are counted correctly. No I/O, no network, no file system. The test runs in microseconds.

---

## 13.13 Summary

This chapter built a complete application using every major feature of Flow:

- **Sum types** for severity levels. The compiler enforces exhaustive handling.
- **Structs** for log entries and reports. Immutable by default, safe to share.
- **Interfaces** for the `Exception<T>` protocol. Structured error data with mutable correction and immutable audit trail.
- **Pure functions** for parsing, formatting, and accumulation. Testable, memoizable, parallelizable.
- **Composition chains** for connecting stages. Left-to-right data flow, auto-mapping over streams.
- **Fan-out** for sending data to multiple processing paths.
- **Streams** for lazy iteration. Produce values one at a time, consume on demand.
- **Coroutines** for concurrent processing. Separate threads, bounded channels, automatic backpressure.
- **Exception handling with retry** for malformed input. Correct the data and try again.
- **Pattern matching** on sum types, options, and results. Exhaustive, compiler-checked dispatch.
- **Module organization** for separating concerns. Types in one module, parsers in another, pipeline logic in a third.

The design followed a consistent pattern at every level: parse external data into internal types at the boundary, work with internal types everywhere else, push purity as deep as possible, and let the type system enforce invariants. This is not specific to log analysis. It is how Flow programs are built.

---

## Exercises

**1.** Add a `Fatal` severity variant to the sum type. Update every function that matches on `Severity` until the program compiles and runs correctly. Count how many match sites the compiler flagged.

**2.** Write a `parse_json_log` function that handles log lines in the format `{"ts":"...","level":"...","src":"...","msg":"..."}`. Use `string.contains` and `string.split` to extract fields (or the `json` module if available). Update `detect_and_parse` to detect and dispatch JSON lines.

**3.** Add a per-source summary to the report. After the main loop, print how many entries came from each source (e.g., `api: 4, db: 3, web: 3`). Use a `map<string, int>` to track counts.

**4.** Replace the sequential `for` loop in `main` with a coroutine-based pipeline. Spawn a `parse_stage` coroutine, send lines to it, and read parsed entries from it. Compare the code structure with the sequential version.

**5.** Add a severity filter to the pipeline. Accept a threshold severity (e.g., `Warn`) and only process entries at that severity or higher. Write a `filter_by_severity` function and integrate it into the main loop. Verify that `Debug` and `Info` entries are excluded when the threshold is `Warn`.

**6.** (Challenge) Implement a `format_csv_report` function that outputs the report as CSV instead of the human-readable table. Then use fan-out to produce both outputs from the same data: `entry -> (format_entry | format_csv_entry) -> ...`. Write a test that verifies both outputs are correct for a known input.
