# ReFlow Standard Library: Full Implementation Plan

## Overview

This document is a complete task-level plan for implementing every module defined in `stdlib_spec.md`. The plan covers both new C runtime functions and new stdlib `.reflow` wrapper modules. It is organized into Epics by functional area, broken into Stories, broken into Tickets.

The stdlib spec defines 20 modules with 231 functions. 80 are already implemented in the runtime. This plan covers the remaining 151 planned functions, the creation of all `.reflow` module files, and the tests for each.

---

## Conventions for This Document

- **Epic**: A group of related stdlib modules.
- **Story**: A coherent unit of work within an epic.
- **Ticket**: A single implementable task with a clear definition of done.
- Tickets are numbered `SL-EPIC-STORY-TICKET`, e.g., `SL-1-1-1`.
- Tickets marked `[BLOCKER]` must be complete before the next story or epic can begin.
- Every ticket includes both the C runtime function and its stdlib wrapper unless noted otherwise.
- "Implemented" means the C runtime function exists. "Needs wrapper" means the `.reflow` file must still expose it.

---

## Prerequisites

Before this plan can begin:

1. The `native` keyword must be implemented in the compiler (lexer, parser, resolver, lowering). See `stdlib_spec.md` "Native Function Declarations" section.
2. Multi-file compilation must work (RB-0-0-1 from `reflow_bootstrap_plan.md`).
3. The driver must resolve `use io` to `stdlib/io.reflow` before looking in the project directory.

If these are not yet done, Epic 0 of this plan covers them.

---

---

# EPIC 0: Native Declaration Infrastructure

The compiler must support `= native "c_name"` syntax before any stdlib `.reflow` module can be written. If this is already complete, skip to Epic 1.

---

## Story 0-1: Native Keyword Support

**SL-0-1-1** `[BLOCKER]`
Add `NATIVE` to the lexer's keyword map in `compiler/lexer.py`. It is a reserved keyword — user code cannot use `native` as an identifier.

**SL-0-1-2** `[BLOCKER]`
Add `native_name: str | None` field to `FnDecl` in `compiler/ast_nodes.py`. Default is `None`. Set when parsing the `= native "c_name"` form.

**SL-0-1-3** `[BLOCKER]`
Update `parse_fn_decl` in `compiler/parser.py` to accept the `= native "c_name"` form after the return type. When `=` is followed by the `NATIVE` keyword, consume it, expect a `STRING_LIT`, and store the string value in `FnDecl.native_name`.

**SL-0-1-4** `[BLOCKER]`
Update the resolver: native functions are resolved as normal function symbols. No body resolution is needed. The resolver should skip body resolution when `native_name is not None`.

**SL-0-1-5** `[BLOCKER]`
Update the lowering pass: when lowering a `Call` whose target symbol has `native_name` set, emit `LCall(native_name, args)` directly instead of `LCall(mangled_reflow_name, args)`. This bypasses mangling entirely.

**SL-0-1-6** `[BLOCKER]`
Update the driver to discover stdlib modules. When the driver encounters `use io`, it must look in `stdlib/io.reflow` before searching the project directory. Add a `stdlib_path` configuration that defaults to `<project_root>/stdlib/`.

**SL-0-1-7**
Write tests: a minimal `stdlib/test_native.reflow` with one native function, a test program that imports and calls it, verify compilation succeeds and the C output contains a direct call to the C function name.

---

---

# EPIC 1: Core I/O Modules

The `io`, `file`, and `sys` modules. These are the first modules most programs need.

---

## Story 1-1: io Module Wrappers

All runtime functions exist. Create the `.reflow` file.

**SL-1-1-1** `[BLOCKER]`
Create `stdlib/io.reflow` with native declarations for all implemented functions: `print`, `println`, `eprint`, `eprintln`, `read_line`, `read_byte`, `stdin_stream`, `read_file`, `write_file`, `tmpfile_create`, `tmpfile_remove`.

**SL-1-1-2**
Write E2E test: a program imports `io`, calls `io.println("hello")`, verify stdout output.

---

## Story 1-2: io Module Extensions

New runtime functions for missing `io` features.

**SL-1-2-1**
Implement `rf_read_file_bytes` in the C runtime. Opens a file in binary mode, reads the entire contents into an `RF_Array` of `rf_byte`, returns `RF_Option_ptr`. Add to `reflow_runtime.h`.

**SL-1-2-2**
Implement `rf_write_file_bytes` in the C runtime. Opens a file in binary mode, writes the `RF_Array` data. Returns `rf_bool`.

**SL-1-2-3**
Implement `rf_append_file` in the C runtime. Opens with `"a"` mode, writes string contents. Returns `rf_bool`.

**SL-1-2-4**
Add `read_file_bytes`, `write_file_bytes`, `append_file` to `stdlib/io.reflow`.

**SL-1-2-5**
Write tests: read/write bytes round-trip, append to existing file.

---

## Story 1-3: file Module

Handle-based file I/O. All new C runtime functions.

**SL-1-3-1** `[BLOCKER]`
Define `RF_File` struct in the runtime:
```c
typedef struct {
    FILE*   fp;
    rf_bool is_binary;
} RF_File;
```

Implement `rf_file_open_read`, `rf_file_open_write`, `rf_file_open_append`, `rf_file_open_read_bytes`, `rf_file_open_write_bytes`. Each returns `RF_Option_ptr` wrapping an `RF_File*`, or `RF_NONE_PTR` on failure.

**SL-1-3-2**
Implement `rf_file_close`. Calls `fclose`. Idempotent (checks for NULL fp).

**SL-1-3-3**
Implement `rf_file_read_bytes(RF_File*, rf_int)`, `rf_file_read_line(RF_File*)`, `rf_file_read_all(RF_File*)`, `rf_file_read_all_bytes(RF_File*)`.

**SL-1-3-4**
Implement `rf_file_lines(RF_File*)` — returns an `RF_Stream*` that yields one line per `next()` call. Implement `rf_file_byte_stream(RF_File*)` — returns a stream of individual bytes.

**SL-1-3-5**
Implement `rf_file_write_bytes`, `rf_file_write_string`, `rf_file_flush`.

**SL-1-3-6**
Implement `rf_file_seek`, `rf_file_seek_end`, `rf_file_position`, `rf_file_size`.

**SL-1-3-7**
Create `stdlib/file.reflow` with native declarations for all 20 functions.

**SL-1-3-8**
Write tests: open/read/close round-trip, line streaming, seek and position, binary read/write, write + flush + read back.

---

## Story 1-4: sys Module Extensions

**SL-1-4-1**
Implement `rf_env_get` in the C runtime. Wraps `getenv()`, returns `RF_Option_ptr` with an `RF_String*` or `RF_NONE_PTR`.

**SL-1-4-2**
Implement `rf_clock_ms` in the C runtime. Wraps `clock_gettime(CLOCK_MONOTONIC)`, returns `rf_int64` milliseconds.

**SL-1-4-3**
Create `stdlib/sys.reflow` with native declarations for all 6 functions (4 existing + 2 new).

**SL-1-4-4**
Write tests: `env_get` for a known variable (`PATH`), `clock_ms` returns increasing values.

---

---

# EPIC 2: String, Character, and Conversion Modules

These modules are already fully implemented in the runtime. This epic creates the `.reflow` wrapper files and verifies everything works end-to-end.

---

## Story 2-1: conv Module

**SL-2-1-1** `[BLOCKER]`
Create `stdlib/conv.reflow` with `pure` native declarations for all 7 functions.

**SL-2-1-2**
Write E2E test: import `conv`, convert int to string and back, verify round-trip.

---

## Story 2-2: string Module

**SL-2-2-1** `[BLOCKER]`
Create `stdlib/string.reflow` with native declarations for all 16 implemented functions.

**SL-2-2-2**
Implement `rf_string_to_bytes` and `rf_string_from_bytes` in the C runtime. `to_bytes` creates an `RF_Array` of `rf_byte` from the string's data. `from_bytes` creates an `RF_String` from an `RF_Array` of `rf_byte`.

**SL-2-2-3**
Add `to_bytes` and `from_bytes` to `stdlib/string.reflow`.

**SL-2-2-4**
Write tests: to_bytes/from_bytes round-trip, verify byte values match.

---

## Story 2-3: char Module

**SL-2-3-1**
Create `stdlib/char.reflow` with native declarations for all 7 functions.

**SL-2-3-2**
Write E2E test: classify characters, convert between char and int.

---

---

# EPIC 3: Path and Math Modules

---

## Story 3-1: path Module Wrappers and Extensions

**SL-3-1-1** `[BLOCKER]`
Create `stdlib/path.reflow` with native declarations for the 7 implemented functions.

**SL-3-1-2**
Implement `rf_path_is_dir` and `rf_path_is_file` in the C runtime. Use `stat()` and check `S_ISDIR`/`S_ISREG`.

**SL-3-1-3**
Implement `rf_path_extension` in the C runtime. Finds the last `.` after the last `/`. Returns `RF_Option_ptr` with the extension including the dot (e.g., `".txt"`), or `RF_NONE_PTR` if none.

**SL-3-1-4**
Implement `rf_path_list_dir` in the C runtime. Uses `opendir`/`readdir`/`closedir`. Returns `RF_Option_ptr` wrapping an `RF_Array` of `RF_String*` filenames (not full paths), or `RF_NONE_PTR` on failure.

**SL-3-1-5**
Add `is_dir`, `is_file`, `extension`, `list_dir` to `stdlib/path.reflow`.

**SL-3-1-6**
Write tests: extension extraction, is_dir/is_file on known paths, list_dir on the test directory.

---

## Story 3-2: math Module

All functions are new. Thin wrappers around C math operations.

**SL-3-2-1** `[BLOCKER]`
Implement all 13 math functions in the C runtime: `rf_math_abs_int`, `rf_math_abs_float`, `rf_math_min_int`, `rf_math_max_int`, `rf_math_min_float`, `rf_math_max_float`, `rf_math_clamp_int`, `rf_math_floor`, `rf_math_ceil`, `rf_math_round`, `rf_math_pow`, `rf_math_sqrt`, `rf_math_log`. Link with `-lm` if not already linked.

- `abs_int` must handle `INT_MIN` safely (checked, or document the edge case).
- Float functions wrap `<math.h>` directly: `floor()`, `ceil()`, `round()`, `pow()`, `sqrt()`, `log()`.
- Integer min/max/clamp are branchless where possible.

**SL-3-2-2**
Create `stdlib/math.reflow` with `pure` native declarations for all 13 functions plus the constant `let` bindings (`pi`, `e`, `max_int`, `min_int`).

**SL-3-2-3**
Write tests: abs edge cases, min/max, clamp boundaries, sqrt/pow/log basic values, floor/ceil/round for negative and positive floats.

---

---

# EPIC 4: Data Structure Modules

The `map`, `set`, `buffer`, and `sort` modules.

---

## Story 4-1: map Module Wrapper

**SL-4-1-1**
Create `stdlib/map.reflow` with native declarations for all 5 implemented functions.

**SL-4-1-2**
Write E2E test: create a map, set/get/has, verify len.

---

## Story 4-2: set Module

**SL-4-2-1**
Create `stdlib/set.reflow` with native declarations for the 5 implemented functions.

**SL-4-2-2**
Implement `rf_set_to_array` in the C runtime. Iterates the internal map entries and collects keys into an `RF_Array`.

**SL-4-2-3**
Implement `rf_set_to_stream` in the C runtime. Returns an `RF_Stream*` that yields set elements.

**SL-4-2-4**
Add `to_array` and `to_stream` to `stdlib/set.reflow`.

**SL-4-2-5**
Write tests: add/has/remove cycle, to_array length matches set length, to_stream yields all elements.

---

## Story 4-3: buffer Module

**SL-4-3-1** `[BLOCKER]`
Create `stdlib/buffer.reflow` with native declarations for the 9 implemented functions.

**SL-4-3-2**
Implement `rf_buffer_to_array` in the C runtime. Creates an immutable `RF_Array` from the buffer's current contents.

**SL-4-3-3**
Implement `rf_buffer_clear` in the C runtime. Resets `len` to 0 without freeing allocation.

**SL-4-3-4**
Implement `rf_buffer_pop` in the C runtime. Decrements `len`, returns `RF_Option_ptr` with the last element, or `RF_NONE_PTR` if empty.

**SL-4-3-5**
Implement `rf_buffer_last` in the C runtime. Returns `RF_Option_ptr` with the last element without removing it.

**SL-4-3-6**
Implement `rf_buffer_set` in the C runtime. Replaces element at index. Panics on OOB.

**SL-4-3-7**
Implement `rf_buffer_insert` in the C runtime. Inserts at index, shifts elements right. Grows if needed.

**SL-4-3-8**
Implement `rf_buffer_remove` in the C runtime. Removes at index, shifts elements left, returns removed element.

**SL-4-3-9**
Implement `rf_buffer_contains` in the C runtime. Linear scan comparing by byte content.

**SL-4-3-10**
Implement `rf_buffer_slice` in the C runtime. Returns a new buffer with a copy of `[start, end)`.

**SL-4-3-11**
Add all 9 new functions to `stdlib/buffer.reflow`.

**SL-4-3-12**
Write tests: push/pop/last cycle, set/get round-trip, insert/remove at various positions, contains, clear + len == 0, slice, to_array immutability.

---

## Story 4-4: sort Module

**SL-4-4-1** `[BLOCKER]`
Implement `rf_sort_array_by` in the C runtime. Copies the array into a temp buffer, sorts with `qsort_r` (or a `qsort` wrapper using thread-local closure storage), returns a new `RF_Array`. The comparator is an `RF_Closure*`.

**SL-4-4-2**
Implement `rf_sort_ints`, `rf_sort_strings`, `rf_sort_floats` in the C runtime with built-in comparators. Each returns a new sorted `RF_Array`.

**SL-4-4-3**
Implement `rf_array_reverse` in the C runtime. Returns a new `RF_Array` with elements in reversed order.

**SL-4-4-4**
Create `stdlib/sort.reflow` with native declarations for all 5 functions.

**SL-4-4-5**
Write tests: sort ints ascending, sort strings lexicographic, sort with custom comparator (descending), reverse, sort empty array.

---

---

# EPIC 5: Stream and Channel Modules

---

## Story 5-1: stream Module — Wrappers

**SL-5-1-1** `[BLOCKER]`
Create `stdlib/stream.reflow` with native declarations for the 5 implemented functions: `take`, `skip`, `map`, `filter`, `reduce`. Also include `collect` (maps to `rf_buffer_collect`).

**SL-5-1-2**
Write E2E test: create a stream via a yielding function, apply take/map/filter/reduce, verify result.

---

## Story 5-2: stream Module — Construction

**SL-5-2-1** `[BLOCKER]`
Implement `rf_stream_range(rf_int start, rf_int end)` in the C runtime. Returns an `RF_Stream*` that yields integers from `start` to `end` (exclusive). State struct holds current value and end.

**SL-5-2-2**
Implement `rf_stream_range_step` in the C runtime. Same as `range` but with a step parameter. Step of 0 panics.

**SL-5-2-3**
Implement `rf_stream_from_array(RF_Array*)` in the C runtime. Returns a stream that yields elements from the array by index.

**SL-5-2-4**
Implement `rf_stream_repeat(void* val, rf_int n)` in the C runtime. Yields `val` exactly `n` times.

**SL-5-2-5**
Implement `rf_stream_empty()` in the C runtime. Returns a stream whose `next` immediately returns `RF_NONE_PTR`.

**SL-5-2-6**
Add all 5 construction functions to `stdlib/stream.reflow`.

**SL-5-2-7**
Write tests: range produces correct sequence, range_step with positive and negative steps, from_array round-trip, repeat count, empty yields none immediately.

---

## Story 5-3: stream Module — Transformation

**SL-5-3-1**
Implement `rf_stream_enumerate` in the C runtime. Wraps the source stream, yielding `(index, value)` pairs. The pair is heap-allocated as a two-element struct.

**SL-5-3-2**
Implement `rf_stream_zip` in the C runtime. Takes two streams, yields `(a, b)` pairs until either is exhausted.

**SL-5-3-3**
Implement `rf_stream_chain` in the C runtime. Concatenates two streams: yields all of `a`, then all of `b`.

**SL-5-3-4**
Implement `rf_stream_flat_map` in the C runtime. For each element of the source, calls the closure to get a sub-stream, yields all elements of each sub-stream before advancing the source.

**SL-5-3-5**
Add `enumerate`, `zip`, `chain`, `flat_map` to `stdlib/stream.reflow`.

**SL-5-3-6**
Write tests: enumerate indices, zip terminates at shorter stream, chain concatenation, flat_map expansion.

---

## Story 5-4: stream Module — Consumption

**SL-5-4-1**
Implement `rf_stream_to_array` in the C runtime. Collects into a buffer then converts to an array.

**SL-5-4-2**
Implement `rf_stream_foreach` in the C runtime. Calls a closure for each element. Returns nothing.

**SL-5-4-3**
Implement `rf_stream_count` in the C runtime. Drains the stream, counting elements.

**SL-5-4-4**
Implement `rf_stream_any` and `rf_stream_all` in the C runtime. Short-circuiting — stop consuming on first true/false respectively.

**SL-5-4-5**
Implement `rf_stream_find` in the C runtime. Returns the first matching element as `RF_Option_ptr`.

**SL-5-4-6**
Implement `rf_stream_sum_int` in the C runtime. Uses checked addition.

**SL-5-4-7**
Add `to_array`, `foreach`, `count`, `any`, `all`, `find`, `sum_int` to `stdlib/stream.reflow`.

**SL-5-4-8**
Write tests: to_array matches expected, foreach side effect count, count on known-length stream, any/all short-circuit behavior, find returns first match, sum_int correctness.

---

## Story 5-5: channel Module Wrapper

**SL-5-5-1**
Create `stdlib/channel.reflow` with native declarations for the 6 implemented functions.

**SL-5-5-2**
Implement `rf_channel_try_send` and `rf_channel_try_recv` in the C runtime. Non-blocking: `try_send` returns false immediately if full or closed. `try_recv` returns `RF_NONE_PTR` immediately if empty (without waiting for close).

**SL-5-5-3**
Add `try_send` and `try_recv` to `stdlib/channel.reflow`.

**SL-5-5-4**
Write tests: try_send on full channel returns false, try_recv on empty channel returns none.

---

---

# EPIC 6: Bytes and Networking

The modules needed for network-capable programs.

---

## Story 6-1: bytes Module

**SL-6-1-1** `[BLOCKER]`
Implement `rf_bytes_from_string` in the C runtime. Creates an `RF_Array` of `rf_byte` from an `RF_String*`. Shares no memory — copies the data.

**SL-6-1-2**
Implement `rf_bytes_to_string` in the C runtime. Creates an `RF_String` from an `RF_Array` of `rf_byte`. No UTF-8 validation.

**SL-6-1-3**
Implement `rf_bytes_slice`, `rf_bytes_concat`, `rf_bytes_index_of`, `rf_bytes_len` in the C runtime.

**SL-6-1-4**
Create `stdlib/bytes.reflow` with native declarations for all 6 functions.

**SL-6-1-5**
Write tests: string→bytes→string round-trip, slice boundaries, concat, index_of found and not found, len.

---

## Story 6-2: net Module — Listener and Accept

**SL-6-2-1** `[BLOCKER]`
Define `RF_TcpListener` and `RF_TcpConnection` structs in the runtime:
```c
typedef struct { int fd; } RF_TcpListener;
typedef struct { int fd; } RF_TcpConnection;
```

**SL-6-2-2** `[BLOCKER]`
Implement `rf_net_listen` in the C runtime. Wraps `socket()` + `setsockopt(SO_REUSEADDR)` + `bind()` + `listen(fd, 128)`. Returns a result: `ok(RF_TcpListener*)` or `err(RF_String*)` with `strerror`.

**SL-6-2-3** `[BLOCKER]`
Implement `rf_net_accept` in the C runtime. Wraps `accept()`. Returns `ok(RF_TcpConnection*)` or `err(RF_String*)`.

**SL-6-2-4**
Implement `rf_net_close` and `rf_net_close_listener` in the C runtime. Wrap `close(fd)`. Idempotent (set fd to -1 after close).

---

## Story 6-3: net Module — Read/Write

**SL-6-3-1** `[BLOCKER]`
Implement `rf_net_read` in the C runtime. Wraps `recv()`. Returns `ok(RF_Array* of rf_byte)` or `err(RF_String*)`. An empty array on clean close (recv returns 0).

**SL-6-3-2**
Implement `rf_net_write` in the C runtime. Wraps `send()` in a loop to handle partial writes. Returns `ok(rf_int bytes_written)` or `err(RF_String*)`.

**SL-6-3-3**
Implement `rf_net_write_string` in the C runtime. Convenience: converts `RF_String*` data pointer and length directly to `send()`. No allocation.

---

## Story 6-4: net Module — Utilities

**SL-6-4-1**
Implement `rf_net_connect` in the C runtime. Wraps `socket()` + `connect()`. Uses `getaddrinfo` for hostname resolution. Returns `ok(RF_TcpConnection*)` or `err(RF_String*)`.

**SL-6-4-2**
Implement `rf_net_set_timeout` in the C runtime. Sets `SO_RCVTIMEO` and `SO_SNDTIMEO` via `setsockopt`. Timeout in milliseconds; 0 means no timeout.

**SL-6-4-3**
Implement `rf_net_remote_addr` in the C runtime. Wraps `getpeername()` + `inet_ntop()`. Returns `"ip:port"` string.

---

## Story 6-5: net Module Wrapper and Tests

**SL-6-5-1**
Create `stdlib/net.reflow` with native declarations for all 10 functions.

**SL-6-5-2**
Write C-level test (`tests/runtime/test_net.c`): start a listener on a random port, connect from the same process, send bytes, receive bytes, verify round-trip. Add to `make test-runtime`.

**SL-6-5-3**
Write E2E test: a ReFlow program that listens, spawns a thread to connect and send data, receives and prints it.

---

---

# EPIC 7: JSON Module

Recursive descent JSON parser and serializer in C.

---

## Story 7-1: JSON Value Type

**SL-7-1-1** `[BLOCKER]`
Define `RF_JsonValue` struct in the runtime:
```c
typedef struct RF_JsonValue {
    rf_byte tag;  // 0=null, 1=bool, 2=int, 3=float, 4=string, 5=array, 6=object
    union {
        rf_bool     bool_val;
        rf_int64    int_val;
        rf_float    float_val;
        RF_String*  string_val;
        RF_Array*   array_val;
        RF_Map*     object_val;
    } data;
} RF_JsonValue;
```

Implement `rf_json_null`, `rf_json_bool`, `rf_json_int`, `rf_json_float`, `rf_json_string`, `rf_json_array`, `rf_json_object` — constructor functions that heap-allocate and return `RF_JsonValue*`.

---

## Story 7-2: JSON Parser

**SL-7-2-1** `[BLOCKER]`
Implement `rf_json_parse(RF_String* s)` in the C runtime. Recursive descent parser handling:
- Objects: `{ "key": value, ... }`
- Arrays: `[ value, ... ]`
- Strings: with full escape support (`\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`, `\uXXXX`)
- Numbers: integer (→ `JsonInt`) and floating-point (→ `JsonFloat`)
- `true`, `false`, `null`

Returns a result-like struct: ok with `RF_JsonValue*` or err with `RF_String*` error message including position.

**SL-7-2-2**
Write C-level test (`tests/runtime/test_json.c`): parse objects, arrays, nested structures, all value types, string escapes, error cases (trailing comma, unclosed brace, invalid token). Add to `make test-runtime`.

---

## Story 7-3: JSON Serializer

**SL-7-3-1**
Implement `rf_json_to_string(RF_JsonValue*)` in the C runtime. Produces compact JSON (no whitespace).

**SL-7-3-2**
Implement `rf_json_to_string_pretty(RF_JsonValue*, rf_int indent)` in the C runtime.

**SL-7-3-3**
Write tests: serialize then re-parse, verify round-trip. Compact and pretty outputs both valid.

---

## Story 7-4: JSON Accessors

**SL-7-4-1**
Implement all accessor functions: `rf_json_get`, `rf_json_get_index`, `rf_json_as_string`, `rf_json_as_int`, `rf_json_as_float`, `rf_json_as_bool`, `rf_json_as_array`, `rf_json_is_null`. Each returns `RF_Option_ptr` (or `rf_bool` for `is_null`).

---

## Story 7-5: JSON Module Wrapper

**SL-7-5-1**
Create `stdlib/json.reflow` with native declarations for all 19 functions.

**SL-7-5-2**
Write E2E test: parse a JSON string, access nested fields, serialize back.

---

---

# EPIC 8: Random and Time Modules

---

## Story 8-1: random Module

**SL-8-1-1** `[BLOCKER]`
Implement the PRNG core in the C runtime. Thread-local `xoshiro256**` state, seeded from `/dev/urandom` on first use. Implement `_rf_rng_ensure_seeded()` and `_rf_rng_next_u64()` as internal helpers.

**SL-8-1-2**
Implement `rf_random_int_range(rf_int min, rf_int max)`. Uniform distribution over `[min, max]`. Panics if `min > max`. Uses rejection sampling to avoid modulo bias.

**SL-8-1-3**
Implement `rf_random_int64_range`, `rf_random_float_unit`, `rf_random_bool`.

**SL-8-1-4**
Implement `rf_random_bytes(rf_int n)`. Reads directly from `/dev/urandom` for cryptographic quality. Returns `RF_Array` of `rf_byte`.

**SL-8-1-5**
Implement `rf_random_shuffle(RF_Array*)`. Fisher-Yates shuffle on a copy. Returns a new `RF_Array`.

**SL-8-1-6**
Implement `rf_random_choice(RF_Array*)`. Returns `RF_Option_ptr` — random element, or `RF_NONE_PTR` if empty.

**SL-8-1-7**
Create `stdlib/random.reflow` with native declarations for all 7 functions.

**SL-8-1-8**
Write tests: `int_range` stays within bounds over 1000 calls, `float_unit` in `[0, 1)`, `shuffle` preserves elements, `choice` on empty returns none, `bytes` returns correct length.

---

## Story 8-2: time Module — Monotonic Time

**SL-8-2-1** `[BLOCKER]`
Define `RF_Instant` struct in the runtime:
```c
typedef struct { struct timespec ts; } RF_Instant;
```

Implement `rf_time_now()`. Returns heap-allocated `RF_Instant*` from `clock_gettime(CLOCK_MONOTONIC)`.

**SL-8-2-2**
Implement `rf_time_elapsed_ms(RF_Instant*)` and `rf_time_elapsed_us(RF_Instant*)`. Compute difference from `now()`.

**SL-8-2-3**
Implement `rf_time_diff_ms(RF_Instant* start, RF_Instant* end)`. Pure computation on two instants.

---

## Story 8-3: time Module — Wall Clock

**SL-8-3-1** `[BLOCKER]`
Define `RF_DateTime` struct in the runtime:
```c
typedef struct {
    time_t     epoch;
    rf_int     utc_offset;
    struct tm  components;
} RF_DateTime;
```

Implement `rf_time_datetime_now()` (local time) and `rf_time_datetime_utc()` (UTC).

**SL-8-3-2**
Implement `rf_time_unix_timestamp()` and `rf_time_unix_timestamp_ms()`.

---

## Story 8-4: time Module — Formatting and Components

**SL-8-4-1**
Implement `rf_time_format_iso8601`, `rf_time_format_rfc2822`, `rf_time_format_http`. Use `strftime` where possible. `format_http` always produces GMT.

**SL-8-4-2**
Implement component accessors: `rf_time_year`, `rf_time_month`, `rf_time_day`, `rf_time_hour`, `rf_time_minute`, `rf_time_second`. Read from `components` field.

**SL-8-4-3**
Create `stdlib/time.reflow` with native declarations for all 17 functions.

**SL-8-4-4**
Write tests: `now` + sleep + `elapsed_ms` > 0, `datetime_utc` year >= 2026, `format_http` matches expected pattern, component accessors consistent with each other.

---

---

# EPIC 9: Testing Module

Required for the self-hosted compiler's own test suite.

---

## Story 9-1: Assertion Functions

**SL-9-1-1** `[BLOCKER]`
Define a test-failure exception tag in the runtime (e.g., `RF_TEST_FAILURE_TAG = 9999`).

**SL-9-1-2** `[BLOCKER]`
Implement `rf_test_assert_true`, `rf_test_assert_false` in the C runtime. On failure, format a message string and call `_rf_throw` with the test-failure tag.

**SL-9-1-3**
Implement `rf_test_assert_eq_int`, `rf_test_assert_eq_int64`, `rf_test_assert_eq_string`, `rf_test_assert_eq_bool`. Each formats an "expected X, got Y" message on failure.

**SL-9-1-4**
Implement `rf_test_assert_eq_float`. Uses epsilon comparison.

**SL-9-1-5**
Implement `rf_test_assert_some` and `rf_test_assert_none`. `assert_some` returns the unwrapped value on success.

**SL-9-1-6**
Implement `rf_test_fail`. Unconditionally throws test-failure.

---

## Story 9-2: Test Runner

**SL-9-2-1** `[BLOCKER]`
Implement `rf_test_run(RF_String* name, RF_Closure* test_fn)` in the C runtime. Wraps the test function in a `setjmp` exception frame. Returns a result struct: pass or fail with message.

**SL-9-2-2**
Implement `rf_test_run_all` in the C runtime. Takes an array of `(name, fn)` pairs, runs each via `rf_test_run`, prints results, returns failure count.

**SL-9-2-3**
Implement `rf_test_report` in the C runtime. Prints formatted PASS/FAIL summary.

---

## Story 9-3: testing Module Wrapper

**SL-9-3-1**
Create `stdlib/testing.reflow` with native declarations for all 13 functions.

**SL-9-3-2**
Write a ReFlow test program that uses `testing.run_all` with a mix of passing and failing tests. Verify output format and exit code.

---

---

# EPIC 10: Integration and Verification

End-to-end validation that all modules work together.

---

## Story 10-1: Static File Server Example

**SL-10-1-1**
Write `examples/http_server.reflow` — the static file server from `stdlib_spec.md`. This exercises `io`, `net`, `path`, `string`, `bytes`, `conv`.

**SL-10-1-2**
Verify it compiles and runs. Create a `examples/public/` directory with a test HTML file. Manually verify a browser can load the page.

---

## Story 10-2: JSON API Example

**SL-10-2-1**
Write `examples/json_echo.reflow` — a TCP server that accepts JSON, parses it, adds a `"timestamp"` field using `time.format_iso8601`, and returns it. Exercises `net`, `json`, `time`, `bytes`.

---

## Story 10-3: Test Suite Example

**SL-10-3-1**
Write `examples/self_test.reflow` — a program that tests itself using `testing.run_all`. Exercises `testing`, `conv`, `string`, `math`.

---

## Story 10-4: Full Regression

**SL-10-4-1** `[BLOCKER]`
Run `make test` — all existing compiler tests must still pass (no regressions from runtime additions).

**SL-10-4-2** `[BLOCKER]`
Run `make test-runtime` — all C-level runtime tests must pass.

**SL-10-4-3**
Compile and run all three example programs. Verify expected behavior.

---

---

# Dependency Map

```
EPIC 0 (Native Infrastructure)
  └─ must complete before all other epics

EPIC 1 (Core I/O)
  └─ depends on EPIC 0
  └─ blocks EPIC 6 (Networking — uses file I/O patterns)
  └─ blocks EPIC 10 (Integration)

EPIC 2 (String/Char/Conv)
  └─ depends on EPIC 0
  └─ blocks EPIC 6 (bytes module needs string.to_bytes)
  └─ blocks EPIC 7 (JSON parser uses string ops)

EPIC 3 (Path/Math)
  └─ depends on EPIC 0
  └─ no downstream blockers

EPIC 4 (Data Structures)
  └─ depends on EPIC 0
  └─ blocks EPIC 7 (JSON uses map)

EPIC 5 (Stream/Channel)
  └─ depends on EPIC 0
  └─ no downstream blockers

EPIC 6 (Bytes/Networking)
  └─ depends on EPIC 1, EPIC 2
  └─ blocks EPIC 10 (HTTP server example)

EPIC 7 (JSON)
  └─ depends on EPIC 2, EPIC 4
  └─ blocks EPIC 10 (JSON API example)

EPIC 8 (Random/Time)
  └─ depends on EPIC 0
  └─ blocks EPIC 10 (time used in JSON API example)

EPIC 9 (Testing)
  └─ depends on EPIC 0
  └─ blocks EPIC 10 (self-test example)
  └─ blocks bootstrap (Epic 11 of compiler plan)

EPIC 10 (Integration)
  └─ depends on all other epics
  └─ final validation gate
```

---

# Parallelism Opportunities

These epics can be worked on concurrently since they have no dependencies on each other (only on EPIC 0):

- **EPIC 1** (Core I/O) + **EPIC 2** (String/Char/Conv) + **EPIC 3** (Path/Math)
- **EPIC 4** (Data Structures) + **EPIC 5** (Stream/Channel) + **EPIC 8** (Random/Time)
- **EPIC 9** (Testing) can start as soon as EPIC 0 is done

After those complete:
- **EPIC 6** (Bytes/Net) and **EPIC 7** (JSON) can run in parallel

---

# Ticket Counts

| Epic | Stories | Tickets |
|------|---------|---------|
| 0: Native Infrastructure | 1 | 7 |
| 1: Core I/O | 4 | 17 |
| 2: String/Char/Conv | 3 | 7 |
| 3: Path/Math | 2 | 9 |
| 4: Data Structures | 4 | 17 |
| 5: Stream/Channel | 5 | 22 |
| 6: Bytes/Networking | 5 | 14 |
| 7: JSON | 5 | 10 |
| 8: Random/Time | 4 | 15 |
| 9: Testing | 3 | 9 |
| 10: Integration | 4 | 6 |
| **Total** | **40** | **133** |
