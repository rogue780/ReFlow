# Plan: Flow Grep

## Overview

A recursive file search tool. Given a pattern and a path, searches files for
matching lines and prints results with filenames and line numbers. A practical
CLI utility that exercises **streaming**, **file I/O**, **string operations**,
and **recursion over directory trees**.

**File:** `apps/grep/grep.flow`

**Usage:**
```
python main.py run apps/grep/grep.flow -- <pattern> [path] [options]
```

**Examples:**
```bash
# Search current directory recursively
flowgrep "TODO" .

# Search a single file
flowgrep "error" server.log

# Case-insensitive search
flowgrep -i "warning" logs/

# Invert match (lines that don't contain pattern)
flowgrep -v "debug" app.log

# Show only filenames
flowgrep -l "import" src/

# Show match count per file
flowgrep -c "fn" src/

# Limit to specific extension
flowgrep --ext ".flow" "main" .
```

**Output format:**
```
src/server.flow:14:  let server = net.listen("0.0.0.0", port)
src/server.flow:27:  let client = net.accept(server)
src/utils.flow:3:  fn:pure parse_port(s: string): int
```

**Stdlib modules used:** `io`, `string`, `array`, `file`, `path`, `conv`, `sys`

---

## Gap Discovery Policy

These apps exist to find holes in the language and stdlib. When implementation
hits a point where the natural approach doesn't work — a missing stdlib
function, a type system limitation, an awkward workaround — **stop and report
it** instead of working around it.

Specifically:
1. **Do not silently work around** a missing feature. If you want to call
   `path.list_dir(dir)` and it doesn't exist, that's a finding.
2. **Identify the gap** clearly: what you wanted to do, what's missing, and
   where in the pipeline (stdlib, parser, type system, runtime) the fix belongs.
3. **Propose solutions** — at least two options with tradeoffs. Prefer
   well-engineered fixes (new stdlib function, language feature) over hacks.
4. **Present to the user** before continuing. The user decides whether to
   fix the gap first or defer it.
5. **Document** each gap with a `; GAP: <description>` comment in the app
   source if deferred.

This policy applies to every ticket in this plan.

### Already-Known Likely Gaps

These are features this app will almost certainly need that may not exist:
- **Directory listing** (`path.list_dir` or `file.read_dir`) — needed for
  recursive search. If missing, this is the highest-priority gap to fix.
- **Regex or glob matching** — real grep uses regex. Flow may only have
  `string.contains`. Decide whether to add pattern matching to stdlib or
  keep this as a substring-only tool.
- **ANSI color output** — nice-to-have for highlighting matches. Requires
  either an `io.is_tty()` check or a `--color` flag.

---

## Conventions

- Tickets are numbered `GR-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Single-File Search

---

## Story 1-1: CLI Argument Parsing

**GR-1-1-1** `[BLOCKER]`
Create `apps/grep/grep.flow` with a `main()` that:
- Reads `sys.args()`.
- First positional arg: pattern (required).
- Second positional arg: path (default `"."`).
- Flags: `-i` (case insensitive), `-v` (invert), `-l` (files only),
  `-c` (count), `-n` (line numbers — on by default), `--ext <ext>`
  (filter by extension).
- On missing pattern, print usage and exit 1.

Parse flags manually by iterating `sys.args()` and matching on
`string.starts_with(arg, "-")`.

**Definition of done:** Args are parsed into a config struct. Missing
pattern prints usage.

---

## Story 1-2: Line-by-Line File Search

**GR-1-2-1** `[BLOCKER]`
Implement `fn search_file(filepath: string, pattern: string, config: SearchConfig): SearchResult`:
- Open file with `file.open_read(filepath)`.
- Read lines in a loop with `file.read_line(f)`.
- For each line, check if it contains the pattern using `string.contains`.
- If `-i` flag is set, compare `string.to_lower(line)` against
  `string.to_lower(pattern)`.
- If `-v` flag is set, invert the match.
- Collect matching lines with their line numbers.

Use a struct for results:
```
struct MatchLine {
    line_num: int
    text: string
}
struct SearchResult {
    filepath: string
    matches: array<MatchLine>
}
```

**GR-1-2-2**
Implement output formatting based on config:
- Default: `"filepath:line_num:  text"`
- `-l` mode: print filepath once if any match, skip line details.
- `-c` mode: print `"filepath:count"`.
- Color: not supported in v1 (no ANSI escape stdlib), but structure the
  formatter so it could be added.

**Definition of done:** `flowgrep "fn" somefile.flow` prints all lines
containing "fn" with file path and line numbers.

---

# EPIC 2: Recursive Directory Walking

---

## Story 2-1: Directory Traversal

**GR-2-1-1** `[BLOCKER]`
Implement `fn walk_files(dir: string, ext_filter: string?): array<string>`:
- Use `file.open_read` to test if the path is a file (single-file mode).
- For directories, use `io.read_file` on the directory won't work, so we need
  a different approach.

Design decision: since the stdlib doesn't have a `read_dir` function, use a
workaround. Options:
- (a) Require the user to pass a list of files explicitly (simpler, less useful).
- (b) Implement the file listing in a helper that reads directory contents.

Check if `path.list_dir` or similar exists in the stdlib. If not, document
the limitation and accept only single files or use a simple glob approach
where the user pipes file lists:
```
# Workaround if no readdir
find . -name "*.flow" | flowgrep --stdin-files "pattern"
```

If `path` module supports directory listing, use it. Otherwise, accept a
flat list of files as arguments:
```
flowgrep "pattern" file1.flow file2.flow file3.flow
```

**GR-2-1-2**
Implement multi-file search:
- Iterate the file list.
- Call `search_file` for each.
- Aggregate results.
- When searching multiple files, always prefix output with the filename.
- When searching a single file, omit the filename prefix (like real grep).

**Definition of done:** `flowgrep "fn" a.flow b.flow c.flow` searches all
three files and prefixes matches with filenames.

---

## Story 2-2: Extension Filtering

**GR-2-2-1**
Implement `--ext` flag:
- When set, skip files whose path doesn't end with the given extension.
- Use `string.ends_with(filepath, ext)`.
- Can be specified multiple times: `--ext .flow --ext .md`.

**Definition of done:** `flowgrep --ext .flow "fn" file1.flow file2.c`
only searches `file1.flow`.

---

# EPIC 3: Advanced Features

---

## Story 3-1: Context Lines

**GR-3-1-1**
Implement `-A <n>` (after context) and `-B <n>` (before context):
- `-A 2`: print 2 lines after each match.
- `-B 2`: print 2 lines before each match.
- Separate match groups with `--` (like real grep).

This requires reading the entire file into an array of lines first, then
searching with index-based access to get surrounding context.

**GR-3-1-2**
Implement `-C <n>` as shorthand for `-A n -B n`.

**Definition of done:** `flowgrep -C 1 "error" log.txt` shows one line
of context above and below each match.

---

## Story 3-2: Match Statistics

**GR-3-2-1**
After all files are searched, if `--stats` flag is set, print a summary:
```
3 files searched
12 lines matched
47ms elapsed
```

Use the `time` module for elapsed time.

**Definition of done:** `flowgrep --stats "fn" *.flow` prints match
summary after results.

---

# EPIC 4: Testing

---

## Story 4-1: Self-Test Program

**GR-4-1-1**
Create `tests/programs/app_grep.flow` — a self-test version that:
- Writes test files to temp paths using `io.tmpfile_create`.
- Searches them with various patterns and flags.
- Prints results.
- Cleans up temp files.

Test cases:
- Basic substring match.
- Case-insensitive match.
- Inverted match.
- File-only mode.
- Count mode.
- No matches (should print nothing).

**GR-4-1-2**
Create `tests/expected_stdout/app_grep.txt` with expected output.

---

## Story 4-2: Documentation

**GR-4-2-1**
Create `apps/grep/README.md` with:
- Usage examples.
- Flag reference.
- Comparison to real grep (scope: substring matching only, no regex).
- Known limitations (no regex, no directory recursion without file list).

---

## Dependency Map

```
EPIC 1 (Single File) → EPIC 2 (Multi-File) → EPIC 3 (Advanced) → EPIC 4 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **File I/O** (`file` module) | Open, read line-by-line, close |
| **`io` module** | stdout/stderr output, tmpfile for tests |
| **String operations** | `contains`, `to_lower`, `ends_with`, `starts_with`, `trim` |
| **`option<T>` / `??`** | `file.read_line` returns `string?`, EOF detection |
| **Structs** | `SearchConfig`, `MatchLine`, `SearchResult` |
| **`array<T>`** | File list, match collection, context lines |
| **`match` expression** | Flag parsing, output mode dispatch |
| **`fn:pure`** | Line matching logic, extension filtering |
| **`sys.args()`** | CLI argument parsing |
| **`sys.exit()`** | Non-zero exit on errors |
| **`path` module** | Extension checking, path manipulation |
| **`conv` module** | Line numbers to strings |
| **`time` module** | Elapsed time for `--stats` |
| **`string_builder`** | Efficient output assembly for large results |
