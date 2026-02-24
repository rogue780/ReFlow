# Plan: Key-Value Store (Mini Redis)

## Overview

An in-memory key-value store with a TCP text protocol, concurrent client
handling via coroutines, and optional disk persistence. Think `redis-cli` but
built entirely in ReFlow.

**File:** `apps/kvstore/server.reflow`

**Usage:**
```
python main.py run apps/kvstore/server.reflow -- [port]
```
Connect with: `nc localhost <port>`

**Protocol:**
```
SET key value     → +OK
GET key           → +value   or  -ERR key not found
DEL key           → +1       or  +0
KEYS              → +key1 key2 key3 ...
COUNT             → +42
EXISTS key        → +1       or  +0
SAVE              → +OK      (snapshot to disk)
LOAD              → +OK      (restore from disk)
PING              → +PONG
QUIT              → (closes connection)
```

Responses prefixed with `+` on success, `-` on error.

**Stdlib modules used:** `net`, `io`, `string`, `array`, `map`, `conv`, `sys`,
`json`, `file`, `time`

---

## Conventions

- Tickets are numbered `KV-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Server Shell and Protocol Parser

---

## Story 1-1: TCP Server with Accept Loop

**KV-1-1-1** `[BLOCKER]`
Create `apps/kvstore/server.reflow` with:
- Port from `sys.args()`, default 6370.
- `net.listen` + accept loop.
- Per-client coroutine via `:< handle_client(sock)`.
- Server prints `"KV store listening on port NNNN"`.

**Definition of done:** Multiple `nc` sessions can connect simultaneously.

---

## Story 1-2: Command Parser

**KV-1-2-1** `[BLOCKER]`
Create `fn:pure parse_command(line: string): (string, array<string>)` that:
- Trims whitespace.
- Splits on spaces.
- Returns `(COMMAND, [arg1, arg2, ...])` with the command uppercased.
- Handles edge cases: empty lines, excess whitespace.

**KV-1-2-2**
Create response formatting functions:
- `fn:pure ok_response(msg: string): string` → `"+msg\n"`
- `fn:pure err_response(msg: string): string` → `"-ERR msg\n"`

**KV-1-2-3**
Wire the parser into `handle_client`: read a line, parse it, dispatch via
`match`, send a response. Start with just `PING` → `+PONG` and `QUIT`.

**Definition of done:** `nc` session can send `PING` and get `+PONG` back,
`QUIT` closes the connection.

---

# EPIC 2: Core Key-Value Operations

---

## Story 2-1: In-Memory Store

**KV-2-1-1** `[BLOCKER]`
Create the store as a mutable `map<string, string>` owned by the main
function and shared with client handlers.

Design decision: since map is mutable and coroutines run on separate threads,
the store must be accessed safely. Options:
- (a) Single-writer model — all writes go through a coordinator coroutine.
- (b) Accept that the runtime's map operations are not thread-safe and run
  a single-threaded event loop instead of coroutines.
- (c) Use the simplest working approach: coroutine-per-client with a
  shared store reference, relying on the fact that string-keyed map
  operations in the C runtime use pointer-sized atomic-ish operations.

Recommended: option (b) for correctness — use a single-threaded read loop
that polls each client socket, or option (a) with a command queue. Document
the tradeoff.

For the MVP, use a single-threaded loop that accepts one client at a time
and services it fully before accepting the next (simple and correct). Then
upgrade to concurrent in Epic 4.

**KV-2-1-2**
Implement `SET key value`:
- `map.set(store, key, value)`
- Response: `+OK`

**KV-2-1-3**
Implement `GET key`:
- `map.get(store, key)`
- Found: `+value`
- Not found: `-ERR key not found`

**KV-2-1-4**
Implement `DEL key`:
- `map.remove(store, key)`
- Response: `+1` if key existed, `+0` otherwise (check with `map.has` first).

**Definition of done:** A client can SET, GET, and DEL keys across multiple
commands in a single session.

---

## Story 2-2: Query Commands

**KV-2-2-1**
Implement `KEYS`:
- `map.keys(store)` → join with spaces.
- Response: `+key1 key2 key3` or `+` (empty) if no keys.

**KV-2-2-2**
Implement `COUNT`:
- `map.len(store)` → convert to string.
- Response: `+42`.

**KV-2-2-3**
Implement `EXISTS key`:
- `map.has(store, key)`.
- Response: `+1` or `+0`.

**Definition of done:** All query commands return correct results.

---

# EPIC 3: Persistence

Snapshot the in-memory store to disk and restore it on command.

---

## Story 3-1: JSON Serialization

**KV-3-1-1** `[BLOCKER]`
Implement `fn serialize_store(store: map<string, string>): string`:
- Iterate `map.keys(store)`.
- Build a JSON object string: `{"key1":"val1","key2":"val2"}`.
- Use `string_builder` for efficiency.

**KV-3-1-2**
Implement `fn deserialize_store(data: string): map<string, string>`:
- Parse with `json.parse(data)`.
- Iterate top-level keys.
- Build a new map from the parsed key-value pairs.

**Definition of done:** Round-trip test — serialize a map, deserialize it,
verify all keys and values match.

---

## Story 3-2: SAVE and LOAD Commands

**KV-3-2-1**
Implement `SAVE`:
- Serialize the store to JSON.
- Write to `kvstore.dat` using `io.write_file`.
- Response: `+OK` or `-ERR write failed`.

**KV-3-2-2**
Implement `LOAD`:
- Read `kvstore.dat` using `io.read_file`.
- Deserialize and replace the current store.
- Response: `+OK (N keys loaded)` or `-ERR file not found`.

**KV-3-2-3**
Add auto-load on startup: if `kvstore.dat` exists when the server starts,
load it automatically and print `"Loaded N keys from kvstore.dat"`.

**Definition of done:** SET some keys, SAVE, restart the server, verify keys
are restored.

---

# EPIC 4: Concurrency and Polish

---

## Story 4-1: Concurrent Client Handling

**KV-4-1-1**
Upgrade from single-threaded to coroutine-per-client. Introduce a command
queue pattern:
- Client coroutines parse commands and push them into a shared structure.
- A main-loop coroutine processes commands sequentially against the store.
- Responses are routed back to the requesting client.

If this proves too complex given stdlib constraints, document the limitation
and keep the single-threaded model.

**KV-4-1-2**
Add client tracking: print connect/disconnect messages with timestamps.

---

## Story 4-2: Error Handling and Edge Cases

**KV-4-2-1**
Handle malformed commands gracefully:
- Empty lines → ignore.
- Unknown commands → `-ERR unknown command 'FOO'`.
- Wrong argument count → `-ERR SET requires 2 arguments`.

**KV-4-2-2**
Handle client disconnects (broken pipe) with `try/catch` around all
`net.write` calls.

**KV-4-2-3**
Add a `FLUSHALL` command that clears the entire store. Response: `+OK`.

---

## Story 4-3: Testing

**KV-4-3-1**
Create `tests/programs/app_kv_store.reflow` — a self-test version that:
- Starts the server on a random high port.
- Spawns a coroutine client that connects and runs a scripted sequence:
  `SET foo bar`, `GET foo`, `DEL foo`, `GET foo`, `KEYS`, `COUNT`.
- Captures and verifies responses.
- Shuts down after the test.

**KV-4-3-2**
Create `tests/expected_stdout/app_kv_store.txt` with expected output.

---

## Dependency Map

```
EPIC 1 (Server Shell) → EPIC 2 (KV Operations) → EPIC 3 (Persistence) → EPIC 4 (Polish)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| TCP networking (`net` module) | Server accept loop, client I/O |
| Coroutines (`:< `) | Per-client connection handling |
| `map<string, string>` | The entire data store |
| Map operations | `set`, `get`, `has`, `remove`, `keys`, `len` |
| `option<T>` / `??` | `map.get` returns `string?` |
| Pattern matching (`match`) | Command dispatch |
| `try/catch` | Network error handling |
| `fn:pure` | Command parser, response formatting |
| `json` module | Store serialization/deserialization |
| File I/O | `io.read_file` / `io.write_file` for persistence |
| `string_builder` | JSON serialization |
| `sys.args()` | CLI port configuration |
| `time` module | Timestamps, uptime tracking |
| Records | Command structures, client metadata |
