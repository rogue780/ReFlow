# Plan: Streaming Log Analyzer

## Overview

A streaming log analyzer that reads log lines from a coroutine producer, parses
and classifies each entry through a composition chain with auto-mapping, and
fans out to three analysis sinks: a counter (receivable coroutine), an alerter
(stream filter for errors), and a pretty-printer. Demonstrates streams with
auto-mapping, stream helpers (`filter`, `group_by`, `chunks`), fan-out,
try/retry/catch for malformed log lines, and coroutine backpressure.

**File:** `apps/logwatch/logwatch.flow`

**Usage:**
```
python main.py run apps/logwatch/logwatch.flow
```

**Example output:**
```
[LOG] Log analyzer starting...
[LOG] 2024-01-15 10:23:45 [ERROR] Connection refused to database
  >>> ALERT: Connection refused to database
[LOG] 2024-01-15 10:23:46 [INFO] Retrying database connection...
[LOG] 2024-01-15 10:23:47 [WARN] Connection pool at 80% capacity
[LOG] RETRY parse_line (attempt 1): trying relaxed format
[LOG] 2024-01-15 10:23:48 [DEBUG] Cache miss for key user:1234
[LOG] malformed garbage line %%%
[LOG] RETRY parse_line (attempt 1): trying relaxed format
[LOG] RETRY parse_line (attempt 2): still unparseable
[LOG] CATCH: unparseable line, recording as UNKNOWN
[LOG] 2024-01-15 10:23:50 [ERROR] Out of memory in worker pool
  >>> ALERT: Out of memory in worker pool
[LOG] --- Stats (batch) ---
[LOG] ERROR: 2
[LOG] WARN: 1
[LOG] INFO: 1
[LOG] DEBUG: 1
[LOG] UNKNOWN: 1
[LOG] Total: 6
```

**Stdlib modules used:** `io`, `string`, `array`, `conv`, `map`, `time`

---

## Gap Discovery Policy

These apps exist to find holes in the language and stdlib. When implementation
hits a point where the natural approach doesn't work — a missing stdlib
function, a type system limitation, an awkward workaround — **stop and report
it** instead of working around it.

Specifically:
1. **Do not silently work around** a missing feature. If you want to write
   `string.char_at(s, i)` and it doesn't exist, that's a finding.
2. **Identify the gap** clearly: what you wanted to do, what's missing, and
   where in the pipeline (stdlib, parser, type system, runtime) the fix belongs.
3. **Propose solutions** — at least two options with tradeoffs. Prefer
   well-engineered fixes (new stdlib function, language feature) over hacks.
4. **Present to the user** before continuing. The user decides whether to
   fix the gap first or defer it.
5. **Document** each gap with a `; GAP: <description>` comment in the app
   source if deferred.

This policy applies to every ticket in this plan.

---

## Conventions

- Tickets are numbered `LW-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Data Types & Exception Types

---

## Story 1-1: Log Entry Types

**LW-1-1-1** `[BLOCKER]`
Define the log entry and level types:
```
type LogLevel =
    | Error
    | Warn
    | Info
    | Debug
    | Unknown

type LogEntry {
    timestamp: string,
    level: LogLevel,
    message: string,
    raw: string
}

type LevelCount {
    level: LogLevel,
    count: int
}

type LogStats {
    counts: array<LevelCount>,
    total: int
}
```

**LW-1-1-2**
Implement helper for log level display:
```
fn:pure level_to_string(level: LogLevel): string {
    match level {
        Error:   "ERROR"
        Warn:    "WARN"
        Info:    "INFO"
        Debug:   "DEBUG"
        Unknown: "UNKNOWN"
    }
}

fn:pure string_to_level(s: string): LogLevel {
    match s {
        "ERROR": Error
        "WARN":  Warn
        "INFO":  Info
        "DEBUG": Debug
        _:       Unknown
    }
}
```

**Definition of done:** Types compile. `LogLevel` sum type has all variants.

---

## Story 1-2: Exception Types

**LW-1-2-1** `[BLOCKER]`
Define parse exception for malformed log lines:
```
type ParseException fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor from_line(m: string, line: string): ParseException {
        return ParseException {
            msg: m,
            payload: line,
            original_payload: line
        }
    }

    fn message(self): string  { return self.msg }
    fn data(self): string     { return self.payload }
    fn original(self): string { return self.original_payload }
}
```

The `payload` is the raw line string. In retry, `ex.data` is mutated to try a
relaxed parsing format (e.g., strip special characters, try alternate timestamp
formats).

**Definition of done:** Exception type compiles, throwable and catchable.

---

# EPIC 2: Log Producer (Coroutine)

---

## Story 2-1: Simulated Log Source

**LW-2-1-1** `[BLOCKER]`
Implement a coroutine that yields raw log lines, simulating `tail -f`:
```
fn log_source(): stream<string> {
    let lines = array.of(
        "2024-01-15 10:23:45 [ERROR] Connection refused to database",
        "2024-01-15 10:23:46 [INFO] Retrying database connection...",
        "2024-01-15 10:23:47 [WARN] Connection pool at 80% capacity",
        "2024-01-15 10:23:47 [???] Partially corrupt log entry",
        "2024-01-15 10:23:48 [DEBUG] Cache miss for key user:1234",
        "malformed garbage line %%%",
        "2024-01-15 10:23:50 [ERROR] Out of memory in worker pool",
        "2024-01-15 10:23:51 [INFO] Graceful shutdown initiated",
        "2024-01-15 10:23:52 [WARN] 3 pending requests dropped",
        "2024-01-15 10:23:53 [ERROR] Disk write failed: /var/log/app.log"
    )

    for (line: string in lines) {
        yield line
    }
}
```

**LW-2-1-2**
Spawn as a coroutine with backpressure:
```
let source :< log_source() with capacity(4)
```

With `capacity(4)`, the producer can buffer 4 lines ahead. If the consumer
(parser/classifier) is busy retrying a malformed line, the producer blocks.

**Definition of done:** Coroutine yields all lines. Consumer reads and prints
each raw line.

---

# EPIC 3: Parser & Classifier

---

## Story 3-1: Log Line Parser

**LW-3-1-1** `[BLOCKER]`
Implement `parse_line` that extracts timestamp, level, and message from a
standard-format log line. Throws `ParseException` on malformed input:
```
fn parse_line(raw: string): LogEntry {
    ; expected format: "YYYY-MM-DD HH:MM:SS [LEVEL] message"
    ; timestamp is chars 0-18, level is between [ and ], message is the rest

    if string.length(raw) < 22 {
        throw ParseException.from_line("line too short", raw)
    }

    let timestamp = string.slice(raw, 0, 19)
    let rest = string.slice(raw, 20, string.length(raw))

    ; find level between brackets
    let bracket_start = string.index_of(rest, "[")
    let bracket_end = string.index_of(rest, "]")

    match (bracket_start, bracket_end) {
        (some(s), some(e)): {
            let level_str = string.slice(rest, s + 1, e)
            let level = string_to_level(level_str)
            let message = string.trim(string.slice(rest, e + 1, string.length(rest)))

            return LogEntry {
                timestamp: timestamp,
                level: level,
                message: message,
                raw: raw
            }
        }
        _: {
            throw ParseException.from_line("no level bracket found", raw)
        }
    }
}
```

**LW-3-1-2**
Implement a relaxed parser for retry attempts:
```
fn:pure sanitize_line(raw: string): string {
    ; strip non-printable characters, normalize whitespace
    ; try to extract any bracketed word as level
    let cleaned = string.trim(raw)
    ; replace common corruption patterns
    let cleaned = string.replace(cleaned, "???", "UNKNOWN")
    return cleaned
}
```

**Definition of done:** `parse_line` parses standard format lines correctly.
Malformed lines throw `ParseException`. `sanitize_line` cleans up common issues.

---

## Story 3-2: Auto-mapping in Composition Chain

**LW-3-2-1**
Demonstrate stream auto-mapping: when `stream<string>` flows into `parse_line`
(which takes `string`), it auto-maps:
```
; Conceptual pipeline:
; source -> parse_line -> classify -> fan-out(count | alert | format)
;
; parse_line takes string, but source yields stream<string>
; auto-mapping applies parse_line to each element
```

**Definition of done:** The composition chain auto-maps `parse_line` over each
streamed line.

---

# EPIC 4: Analysis Sinks (Fan-out)

---

## Story 4-1: Counter (Receivable Coroutine)

**LW-4-1-1** `[BLOCKER]`
Implement a receivable coroutine that counts entries by log level:
```
fn counter(inbox: stream<LogEntry>): stream<LogStats> {
    let error_count = 0
    let warn_count = 0
    let info_count = 0
    let debug_count = 0
    let unknown_count = 0
    let total = 0

    for (entry: LogEntry in inbox) {
        total = total + 1
        match entry.level {
            Error:   { error_count = error_count + 1 }
            Warn:    { warn_count = warn_count + 1 }
            Info:    { info_count = info_count + 1 }
            Debug:   { debug_count = debug_count + 1 }
            Unknown: { unknown_count = unknown_count + 1 }
        }
    }

    yield LogStats {
        counts: array.of(
            LevelCount { level: Error,   count: error_count },
            LevelCount { level: Warn,    count: warn_count },
            LevelCount { level: Info,    count: info_count },
            LevelCount { level: Debug,   count: debug_count },
            LevelCount { level: Unknown, count: unknown_count }
        ),
        total: total
    }
}
```

**Definition of done:** Counter receives entries via `.send()`, yields accurate
`LogStats` via `.next()`.

---

## Story 4-2: Alerter (Stream Filter)

**LW-4-2-1** `[BLOCKER]`
Implement an alerter that filters for `Error` level entries and prints alerts:
```
fn alert_on_error(entry: LogEntry): void {
    match entry.level {
        Error: {
            io.println(f"  >>> ALERT: {entry.message}")
        }
        _: {}
    }
}
```

Alternatively, use `stream.filter` if the composition allows:
```
; Conceptual: entries -> stream.filter(\(e: LogEntry => is_error(e))) -> print_alert

fn:pure is_error(entry: LogEntry): bool {
    match entry.level {
        Error: true
        _:     false
    }
}
```

**Definition of done:** Only `Error` entries trigger alert output.

---

## Story 4-3: Pretty-Printer (Formatter)

**LW-4-3-1**
Implement a formatter that prints each entry in a standardized format:
```
fn format_entry(entry: LogEntry): void {
    io.println(f"[LOG] {entry.timestamp} [{level_to_string(entry.level)}] {entry.message}")
}
```

**Definition of done:** All entries are printed in consistent format.

---

# EPIC 5: Pipeline Assembly with Try/Retry/Catch

---

## Story 5-1: Main Pipeline

**LW-5-1-1** `[BLOCKER]`
Assemble the full pipeline in `main()`:
```
fn main(): void {
    io.println("[LOG] Log analyzer starting...")

    let source :< log_source() with capacity(4)
    let stats :< counter() with capacity(8)

    for (raw: string in source) {
        try {
            let entry = parse_line(raw)
            format_entry(entry)
            alert_on_error(entry)
            stats.send(entry)

        } retry parse_line (ex: ParseException, attempts: 2) {
            ; try relaxed parsing: sanitize the line and retry
            io.println(f"[LOG] RETRY parse_line: trying relaxed format")
            ex.data = sanitize_line(ex.data)

        } catch (ex: ParseException) {
            ; permanently unparseable: create an Unknown entry
            io.println(f"[LOG] CATCH: unparseable line, recording as UNKNOWN")
            let fallback = LogEntry {
                timestamp: "????-??-?? ??:??:??",
                level: Unknown,
                message: ex.original,
                raw: ex.original
            }
            format_entry(fallback)
            stats.send(fallback)
        }
    }

    ; read and print final stats
    match stats.next() {
        some(s): {
            io.println("[LOG] --- Stats ---")
            for (lc: LevelCount in s.counts) {
                if lc.count > 0 {
                    io.println(f"[LOG] {level_to_string(lc.level)}: {conv.to_string(lc.count)}")
                }
            }
            io.println(f"[LOG] Total: {conv.to_string(s.total)}")
        }
        none: {
            io.println("[LOG] No stats available")
        }
    }
}
```

Key features demonstrated:
- **Coroutine producer** with backpressure for log source
- **try/retry/catch** for malformed log lines
- **`ex.data` mutation**: `sanitize_line` cleans the raw string before retry
- **`ex.original`**: Used as fallback message when parsing permanently fails
- **Receivable coroutine**: Counter receives entries via `.send()`
- **Implicit fan-out**: Each entry goes to formatter, alerter, and counter
  (imperative fan-out; document if `|` composition with `.send()` is a gap)

**Definition of done:** Full pipeline runs end-to-end. Good lines are parsed,
classified, formatted, alerted (if Error), and counted. Bad lines retry with
sanitized data, then fall back to Unknown entries.

---

# EPIC 6: Stream Helpers Integration

---

## Story 6-1: Stream Filter for Alerter

**LW-6-1-1**
Use `stream.filter` to create a filtered stream of error-only entries:
```
; If composition allows:
; entries_stream -> stream.filter(is_error) -> print_alert
```

Document if `stream.filter` can be used in this context or if it's a gap.

**LW-6-1-2**
Use `stream.group_by` to group entries by log level (stretch goal):
```
; entries_stream -> stream.group_by(\(e: LogEntry => level_to_string(e.level)))
```

This produces `stream<(string, buffer<LogEntry>)>` pairs.

**LW-6-1-3**
Use `stream.chunks` for batched stats reporting (stretch goal):
```
; entries_stream -> stream.chunks(5) -> report_batch
```

Processes entries in batches of 5 for periodic status updates rather than
one final summary.

**Definition of done:** At least `stream.filter` is used for the alerter.
Document gaps for `group_by` and `chunks` if they cannot be used.

---

# EPIC 7: Testing

---

## Story 7-1: End-to-End Test

**LW-7-1-1**
Create `tests/programs/app_logwatch.flow` — a self-contained test with
hardcoded log lines and deterministic output.

**LW-7-1-2**
Create `tests/expected_stdout/app_logwatch.txt` with expected output covering:
- Standard log lines parsed and formatted
- Error-level alerts
- Retry on malformed lines (sanitized format)
- Catch for permanently unparseable lines (Unknown fallback)
- Final stats by log level

**Definition of done:** `make test` passes with the golden file test.

---

## Dependency Map

```
EPIC 1 (Types) → EPIC 2 (Producer) → EPIC 3 (Parser/Classifier)
                                           ↓
EPIC 4 (Sinks: Counter, Alerter, Formatter) ← ←
         ↓
EPIC 5 (Pipeline Assembly) → EPIC 6 (Stream Helpers) → EPIC 7 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **Coroutines (`:< `)** | `log_source` producer, `counter` receivable coroutine |
| **Receivable coroutine (`.send()`)** | Counter receives `LogEntry` records |
| **`.next()`** | Reading final stats from counter |
| **`with capacity(n)`** | Bounded channels on producer and counter |
| **Backpressure** | Producer blocks when parse/classify is busy retrying |
| **Stream auto-mapping** | `parse_line` auto-maps over `stream<string>` |
| **`stream.filter`** | Filtering for error-level entries |
| **`stream.group_by`** | Grouping entries by log level (stretch) |
| **`stream.chunks`** | Batched reporting (stretch) |
| **`try/retry/catch`** | Malformed log line recovery |
| **`ex.data` mutation** | `sanitize_line` cleans raw line before retry |
| **`ex.original`** | Used as fallback message for Unknown entries |
| **`Exception<T>` interface** | `ParseException` with `fulfills` |
| **Composition chains (`->`)** | Pipeline: source -> parse -> classify -> sinks |
| **Fan-out** | Entries go to counter, alerter, and formatter |
| **Sum types** | `LogLevel` with 5 variants |
| **Pattern matching** | Dispatch on `LogLevel` in counter, alerter, helpers |
| **`fn:pure`** | `level_to_string`, `string_to_level`, `is_error`, `sanitize_line` |
| **`for-in` on streams** | Consuming inbox in counter, iterating source |
| **`option<T>`** | Coroutine `.next()` result, `string.index_of` return |
| **`string` module** | Slice, index_of, trim, replace, length |
| **`array` module** | Log line batch, stats array |
| **`conv` module** | Integer-to-string for stats |
| **`io` module** | All output |
