# Plan: JSON Query Tool

## Overview

A command-line tool for querying and transforming JSON files. Reads a JSON
file, evaluates a dot-path expression to extract values, and prints results.
A practical Unix-style utility — pipe-friendly, composable, zero-config.

**File:** `apps/jsonq/jsonq.flow`

**Usage:**
```
python main.py run apps/jsonq/jsonq.flow -- <file.json> <query> [options]
```

**Examples:**
```bash
# Extract a string field
jsonq data.json "name"
# → "Alice"

# Nested access
jsonq data.json "address.city"
# → "New York"

# Array index
jsonq data.json "users.0.email"
# → "alice@example.com"

# Array length
jsonq data.json "users.#"
# → 3

# All values of a field across an array
jsonq data.json "users.*.name"
# → "Alice"
# → "Bob"
# → "Charlie"

# Pretty-print a subtree
jsonq data.json "config" --pretty
# → {
# →   "debug": true,
# →   "port": 8080
# → }

# Read from stdin
cat data.json | jsonq - "name"
```

**Stdlib modules used:** `json`, `io`, `string`, `array`, `conv`, `sys`, `file`

---

## Conventions

- Tickets are numbered `JQ-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Core Query Engine

---

## Story 1-1: CLI Argument Parsing

**JQ-1-1-1** `[BLOCKER]`
Create `apps/jsonq/jsonq.flow` with a `main()` that:
- Reads `sys.args()`.
- Expects at least 2 args: `<file>` and `<query>`.
- On missing args, prints usage and exits with code 1.
- Supports `--pretty` flag for indented output.
- Supports `-` as filename to read from stdin.

**JQ-1-1-2**
Implement file reading:
- If filename is `-`, read from stdin using `io.read_line()` in a loop
  and accumulate into a string.
- Otherwise, use `io.read_file(path)`.
- Parse with `json.parse(content)`.
- On parse failure, print `"Error: invalid JSON"` to stderr and exit 1.

**Definition of done:** `jsonq data.json ""` reads the file, parses it, and
pretty-prints the entire document.

---

## Story 1-2: Path Parser

**JQ-1-2-1** `[BLOCKER]`
Create `fn:pure parse_path(query: string): array<string>` that splits a
dot-path into segments:
- `"name"` → `["name"]`
- `"users.0.email"` → `["users", "0", "email"]`
- `""` (empty) → `[]` (root — return entire document)
- `"users.#"` → `["users", "#"]`
- `"users.*.name"` → `["users", "*", "name"]`

Handle edge cases:
- Leading/trailing dots → error.
- Double dots `..` → error.
- Empty segments → error.

**JQ-1-2-2**
Create `fn:pure is_array_index(segment: string): bool` that returns true if
the segment is a non-negative integer string.

**Definition of done:** Unit-testable path parser that handles all valid
path formats.

---

## Story 1-3: Path Traversal

**JQ-1-3-1** `[BLOCKER]`
Implement `fn resolve(root: JsonValue, segments: array<string>): JsonValue?`:
- Walk the segments left to right.
- For each segment:
  - If current value is an object, use `json.get(current, segment)`.
  - If current value is an array and segment is a number, use
    `json.get_index(current, index)`.
  - If segment is `"#"`, return `json.int_val(array_length)`.
  - If value is not found at any step, return `none`.

**JQ-1-3-2**
Implement output formatting:
- String values → print without quotes (raw) for pipe-friendliness.
- Number/bool/null → print as JSON literal.
- Object/array → print as JSON string (compact by default, indented with
  `--pretty`).

**Definition of done:** `jsonq data.json "users.0.name"` returns the correct
value for nested access.

---

# EPIC 2: Advanced Queries

---

## Story 2-1: Wildcard Expansion

**JQ-2-1-1** `[BLOCKER]`
Implement the `*` (wildcard) segment:
- When the current value is an array, `*` means "iterate all elements".
- Remaining path segments are applied to each element.
- Each matching result is printed on its own line.

Example: `"users.*.name"` on `[{"name":"A"},{"name":"B"}]` prints:
```
A
B
```

**JQ-2-1-2**
Handle nested wildcards: `"data.*.items.*.id"` — recurse for each `*`.

**Definition of done:** Multi-level wildcard queries produce correct
multi-line output.

---

## Story 2-2: Array Length and Type Queries

**JQ-2-2-1**
Implement `#` (length) operator:
- On arrays: returns the element count.
- On objects: returns the key count (if feasible with the json module).
- On strings: returns the character length.
- On other types: error.

**JQ-2-2-2**
Implement `?type` query suffix:
- `jsonq data.json "name?type"` → `"string"`
- `jsonq data.json "age?type"` → `"number"`
- `jsonq data.json "active?type"` → `"boolean"`
- `jsonq data.json "items?type"` → `"array"`

**Definition of done:** Type introspection works for all JSON value types.

---

# EPIC 3: Error Handling and Edge Cases

---

## Story 3-1: Graceful Errors

**JQ-3-1-1**
When a path doesn't resolve (key not found, index out of bounds):
- Print nothing to stdout (so piped commands get empty input).
- Print `"Error: path 'foo.bar' not found"` to stderr.
- Exit with code 1.

**JQ-3-1-2**
When the JSON file doesn't exist:
- Print `"Error: file 'data.json' not found"` to stderr.
- Exit with code 1.

**JQ-3-1-3**
When the query path is malformed:
- Print `"Error: invalid query path 'foo..bar'"` to stderr.
- Exit with code 1.

**Definition of done:** All error cases produce clear messages on stderr
and non-zero exit codes.

---

## Story 3-2: Multiple Queries

**JQ-3-2-1**
Support multiple query arguments:
```
jsonq data.json "name" "age" "city"
```
Each result printed on its own line. Useful for extracting multiple fields
from the same document without re-reading.

**Definition of done:** Multiple queries produce one result per line.

---

# EPIC 4: Testing and Polish

---

## Story 4-1: Test Suite

**JQ-4-1-1**
Create test JSON files in `apps/jsonq/testdata/`:
- `simple.json` — flat object with string, int, bool, null fields.
- `nested.json` — object with nested objects and arrays.
- `array.json` — top-level array of objects.

**JQ-4-1-2**
Create `tests/programs/app_json_query.flow` — a self-test version that:
- Writes test JSON to a temp file.
- Runs queries against it using the query engine functions directly.
- Prints results and verifies correctness.

**JQ-4-1-3**
Create `tests/expected_stdout/app_json_query.txt` with expected output.

---

## Story 4-2: Documentation

**JQ-4-2-1**
Create `apps/jsonq/README.md` with:
- Usage examples.
- Query syntax reference.
- Comparison to `jq` (scope — this is a simple path extractor, not a
  full query language).

---

## Dependency Map

```
EPIC 1 (Core Engine) → EPIC 2 (Advanced Queries) → EPIC 3 (Error Handling) → EPIC 4 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| `json` module | Full use: parse, get, get_index, as_string, as_int, as_float, as_bool, is_null, to_string, to_string_pretty |
| `option<T>` / `??` | Every json access returns `JsonValue?` |
| Pattern matching (`match`) | Dispatching on value types, option unwrapping |
| `fn:pure` | Path parser, resolver, formatters |
| `sys.args()` | CLI argument parsing |
| `sys.exit()` | Non-zero exit on errors |
| File I/O | `io.read_file` for JSON input |
| String manipulation | Path parsing, output formatting |
| `array<string>` | Path segments, multiple queries |
| Recursion | Wildcard expansion over nested structures |
| `io.eprintln` | Error messages to stderr |
| `conv` module | Index string → int conversion |
