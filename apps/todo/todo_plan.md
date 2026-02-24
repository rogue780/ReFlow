# Plan: Todo CLI

## Overview

A command-line task manager backed by a JSON file. Add, complete, list, and
remove tasks from the terminal. Demonstrates **JSON round-tripping**,
**file persistence**, **option/result handling**, and **struct manipulation**
in a small, approachable app.

**File:** `apps/todo/todo.flow`

**Usage:**
```
python main.py run apps/todo/todo.flow -- <command> [args]
```

**Commands:**
```bash
# Add a task
todo add "Write the parser"
todo add "Fix bug in emitter" --tag bug

# List tasks
todo list
#  1. [ ] Write the parser
#  2. [ ] Fix bug in emitter  [bug]

# Complete a task
todo done 1
#  Completed: "Write the parser"

todo list
#  1. [x] Write the parser
#  2. [ ] Fix bug in emitter  [bug]

# Remove a task
todo rm 2
#  Removed: "Fix bug in emitter"

# Show only incomplete tasks
todo list --pending
#  (none)

# Show summary
todo stats
#  Total: 2  Done: 1  Pending: 1

# Clear all completed tasks
todo clean
#  Removed 1 completed task(s)
```

**Data file:** `todo.json` in the current directory (configurable via
`--file <path>`).

**JSON format:**
```json
{
  "tasks": [
    {"id": 1, "text": "Write the parser", "done": true, "tag": ""},
    {"id": 2, "text": "Fix bug in emitter", "done": false, "tag": "bug"}
  ],
  "next_id": 3
}
```

**Stdlib modules used:** `io`, `string`, `array`, `json`, `conv`, `sys`,
`string_builder`

---

## Gap Discovery Policy

These apps exist to find holes in the language and stdlib. When implementation
hits a point where the natural approach doesn't work — a missing stdlib
function, a type system limitation, an awkward workaround — **stop and report
it** instead of working around it.

Specifically:
1. **Do not silently work around** a missing feature. If you want to call
   `json.set(obj, "done", true)` and it doesn't support bool values, that's
   a finding.
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
- **JSON mutation** — the `json` module may not support setting fields on an
  existing JSON value. If `json.set` doesn't exist or can't handle nested
  updates, this is a critical gap.
- **JSON array append** — adding a task means appending to a JSON array.
  If the stdlib only supports reading arrays, not building them, this needs
  a fix.
- **JSON bool/int construction** — creating `{"done": false}` requires
  building JSON values from Flow primitives. Check whether `json.bool_val`,
  `json.int_val`, `json.string_val` constructors exist.
- **File existence check** — `io.read_file` returns `option`, which works
  for detection, but a dedicated `path.exists` or `file.exists` would be
  cleaner.

---

## Conventions

- Tickets are numbered `TD-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Data Model and Persistence

---

## Story 1-1: Task Data Model

**TD-1-1-1** `[BLOCKER]`
Create `apps/todo/todo.flow` with the data model. Since Flow structs can't
be stored in generic arrays easily, represent tasks as parallel arrays or
as JSON values directly.

Design decision: maintain the task list as a JSON value (the parsed
`todo.json` content) and manipulate it with `json.*` functions. This
avoids the need for struct-to-JSON serialization and keeps the code simple.

Alternative: use a `map<string, string>` per task, stored in an
`array<map<string, string>>`. This is more idiomatic but cumbersome.

Recommended: work directly with the JSON value. The `json` module provides
`json.get`, `json.set`, `json.array_len`, etc.

**TD-1-1-2** `[BLOCKER]`
Implement `fn load_tasks(filepath: string): JsonValue`:
- Read file with `io.read_file(filepath)`.
- If file doesn't exist (returns `none`), return a default empty state:
  `{"tasks": [], "next_id": 1}`.
- Parse with `json.parse`.
- On parse failure, print warning and return default.

**TD-1-1-3** `[BLOCKER]`
Implement `fn save_tasks(filepath: string, data: JsonValue): none`:
- Serialize with `json.to_string(data)`.
- Write with `io.write_file(filepath, serialized)`.
- On write failure, print error to stderr.

**Definition of done:** Load from a non-existent file returns the default.
Save then load round-trips correctly.

---

## Story 1-2: CLI Argument Parsing

**TD-1-2-1** `[BLOCKER]`
Implement argument parsing in `main()`:
- First arg after flags: command (`add`, `list`, `done`, `rm`, `stats`,
  `clean`).
- `--file <path>`: override default `todo.json` path.
- Dispatch via `match` on the command string.
- On unknown command or missing args, print usage and exit 1.

**Definition of done:** `todo --file tasks.json list` routes to the list
handler with the correct file path.

---

# EPIC 2: Core Commands

---

## Story 2-1: Add Task

**TD-2-1-1** `[BLOCKER]`
Implement `add` command:
- Read the task text from args (everything after `add`; join with spaces
  if multiple words).
- Parse optional `--tag <tag>` from the remaining args.
- Load the current task list.
- Create a new task JSON object:
  ```json
  {"id": <next_id>, "text": "<text>", "done": false, "tag": "<tag>"}
  ```
- Append to the `"tasks"` array.
- Increment `"next_id"`.
- Save.
- Print `Added: "<text>"` (with `[tag]` if set).

**Definition of done:** `todo add "Buy milk"` creates the file and adds
the task. Running it again adds a second task with id 2.

---

## Story 2-2: List Tasks

**TD-2-2-1** `[BLOCKER]`
Implement `list` command:
- Load the task list.
- Iterate the `"tasks"` array.
- For each task, format:
  - `" 1. [x] Task text  [tag]"` (done)
  - `" 2. [ ] Task text"` (pending, no tag)
- If `--pending` flag, skip done tasks.
- If `--done` flag, skip pending tasks.
- If no tasks match, print `"(no tasks)"`.

**TD-2-2-2**
Implement `--tag <tag>` filter for list:
- Only show tasks with the matching tag.
- Combinable with `--pending` / `--done`.

**Definition of done:** `todo list` shows all tasks. `todo list --pending`
shows only incomplete ones.

---

## Story 2-3: Complete and Remove

**TD-2-3-1** `[BLOCKER]`
Implement `done <id>` command:
- Load the task list.
- Find the task with the matching id in the `"tasks"` array.
- If not found, print `"Error: task #<id> not found"` and exit 1.
- If already done, print `"Task #<id> is already completed"`.
- Otherwise, set its `"done"` field to true.
- Save.
- Print `Completed: "<text>"`.

**TD-2-3-2**
Implement `rm <id>` command:
- Load the task list.
- Find and remove the task with the matching id.
- If not found, print `"Error: task #<id> not found"` and exit 1.
- Save.
- Print `Removed: "<text>"`.

Note: removing a task does not reassign IDs. IDs are permanent
(like database primary keys).

**Definition of done:** `todo done 1` marks task 1 complete. `todo rm 1`
removes it entirely.

---

# EPIC 3: Utility Commands

---

## Story 3-1: Stats and Clean

**TD-3-1-1**
Implement `stats` command:
- Load the task list.
- Count total, done, and pending tasks.
- Print: `"Total: N  Done: N  Pending: N"`.
- If tags are in use, print a tag breakdown:
  ```
  Tags: bug(2) feature(3) docs(1)
  ```

**TD-3-1-2**
Implement `clean` command:
- Load the task list.
- Remove all tasks where `"done"` is true.
- Save.
- Print `"Removed N completed task(s)"`.
- If none removed, print `"Nothing to clean"`.

**Definition of done:** `todo stats` prints the correct counts. `todo clean`
removes completed tasks.

---

## Story 3-2: Edit Task

**TD-3-2-1**
Implement `edit <id> <new text>` command:
- Load the task list.
- Find the task by id.
- Update its text.
- Save.
- Print `Updated: "<new text>"`.

**TD-3-2-2**
Implement `tag <id> <tag>` command:
- Load the task list.
- Find the task by id.
- Update its tag (empty string to clear).
- Save.
- Print `Tagged #<id>: [<tag>]` or `Untagged #<id>`.

**Definition of done:** `todo edit 1 "New text"` updates the task.

---

# EPIC 4: Testing

---

## Story 4-1: Self-Test Program

**TD-4-1-1**
Create `tests/programs/app_todo.flow` — a self-test that:
- Uses a temp file via `io.tmpfile_create`.
- Exercises the core functions directly (not via CLI dispatch):
  - Load from non-existent file → default state.
  - Add 3 tasks.
  - List all → verify count.
  - Complete task 1.
  - List pending → verify 2 tasks.
  - Remove task 2.
  - Stats → verify counts.
  - Clean → remove completed.
  - List → verify 1 remaining.
- Cleans up temp file.

**TD-4-1-2**
Create `tests/expected_stdout/app_todo.txt` with expected output.

---

## Story 4-2: Documentation

**TD-4-2-1**
Create `apps/todo/README.md` with:
- Usage examples for each command.
- JSON file format description.
- Customizing the data file path.

---

## Dependency Map

```
EPIC 1 (Data Model) → EPIC 2 (Core Commands) → EPIC 3 (Utility Commands) → EPIC 4 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **`json` module** | Full use: parse, get, set, array iteration, to_string |
| **`option<T>` / `??`** | File read, json.get, task lookup |
| **`match` expression** | Command dispatch, flag parsing |
| **`fn:pure`** | Task formatting, ID lookup, filtering |
| **Structs** | Could use for SearchConfig-like flag bundles |
| **`array<T>`** | Task collection, arg list |
| **`map<string, string>`** | Tag counting for stats |
| **`string` module** | Join, trim, starts_with for arg parsing |
| **`string_builder`** | Building formatted task list output |
| **`conv` module** | ID int↔string conversion |
| **`sys.args()`** | CLI argument parsing |
| **`sys.exit()`** | Non-zero exit on errors |
| **File I/O** | `io.read_file` / `io.write_file` for persistence |
| **`io` module** | stdout/stderr output |
