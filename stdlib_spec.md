# Flow Standard Library Specification

This document specifies every module in the Flow standard library. Each
module maps to a `stdlib/<name>.flow` file and is backed by native C
functions in `runtime/flow_runtime.h` / `runtime/flow_runtime.c`.

**Status key:**
- **Implemented** — runtime function exists and is tested
- **Declared** — runtime function declared in header but not yet callable from Flow
- **Planned** — not yet in the runtime; needs new C code

---

## Native Function Declarations

Standard library modules bind Flow names to C runtime functions using the
`native` keyword:

```
fn println(s: string): none = native "fl_println"
fn exit(code: int): none = native "fl_sys_exit"
```

### Rules

- `native` declarations may only appear in modules under `stdlib/`.
- The declared parameter types and return type must match the C function's
  signature exactly. The compiler does not verify this — a mismatch is
  undefined behavior.
- `native` functions are not `pure` unless explicitly marked `pure`.
- Downstream passes emit a direct `LCall` to the C name, bypassing mangling.

---

## Entry Point Convention

A Flow program's entry point is `fn main(): none`. The driver appends a C
`main` that calls `_fl_runtime_init(argc, argv)` then the mangled Flow main.

---

## Module: `io`

**File:** `stdlib/io.flow`

Console and basic I/O. All functions are non-pure.

### Console

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `print` | `fn print(s: string): none` | Implemented | `fl_print` |
| `println` | `fn println(s: string): none` | Implemented | `fl_println` |
| `eprint` | `fn eprint(s: string): none` | Implemented | `fl_eprint` |
| `eprintln` | `fn eprintln(s: string): none` | Implemented | `fl_eprintln` |
| `read_line` | `fn read_line(): string?` | Implemented | `fl_read_line` |
| `read_byte` | `fn read_byte(): byte?` | Implemented | `fl_read_byte` |
| `stdin_stream` | `fn stdin_stream(): stream<byte>` | Implemented | `fl_stdin_stream` |

### File I/O

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `read_file` | `fn read_file(path: string): string?` | Implemented | `fl_read_file` |
| `write_file` | `fn write_file(path: string, contents: string): bool` | Implemented | `fl_write_file` |
| `read_file_bytes` | `fn read_file_bytes(path: string): array<byte>?` | Planned | `fl_read_file_bytes` |
| `write_file_bytes` | `fn write_file_bytes(path: string, data: array<byte>): bool` | Planned | `fl_write_file_bytes` |
| `append_file` | `fn append_file(path: string, contents: string): bool` | Planned | `fl_append_file` |

### Temporary Files

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `tmpfile_create` | `fn tmpfile_create(suffix: string, contents: string): string` | Implemented | `fl_tmpfile_create` |
| `tmpfile_remove` | `fn tmpfile_remove(path: string): none` | Implemented | `fl_tmpfile_remove` |

### Behavior Notes

- `read_line()` reads from stdin up to `\n`, returns the line with `\n`
  stripped. Returns `none` on EOF.
- `read_byte()` reads one byte from stdin. Returns `some(byte)` or `none`
  on EOF.
- `read_file(path)` returns the entire file contents as `some(string)`, or
  `none` if the file cannot be opened.
- `read_file_bytes(path)` returns raw bytes without UTF-8 interpretation.
  Required for binary file serving (images, etc).
- `write_file(path, contents)` overwrites the file. Returns true on success.
- `append_file(path, contents)` appends to existing file (opens with `"a"`).

---

## Module: `file`

**File:** `stdlib/file.flow`

Handle-based file I/O for incremental reading and writing. All functions
are non-pure. The convenience functions in `io` (`read_file`, `write_file`)
slurp/dump entire files in one call — this module is for everything else:
streaming large files, appending to logs, reading line-by-line, and serving
binary content over a network connection without loading it all into memory.

### Types

```
type File  // opaque, wraps a FILE* (or fd)
```

### Opening / Closing

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `open_read` | `fn open_read(path: string): File?` | Planned | `fl_file_open_read` |
| `open_write` | `fn open_write(path: string): File?` | Planned | `fl_file_open_write` |
| `open_append` | `fn open_append(path: string): File?` | Planned | `fl_file_open_append` |
| `open_read_bytes` | `fn open_read_bytes(path: string): File?` | Planned | `fl_file_open_read_bytes` |
| `open_write_bytes` | `fn open_write_bytes(path: string): File?` | Planned | `fl_file_open_write_bytes` |
| `close` | `fn close(f: File): none` | Planned | `fl_file_close` |

### Reading

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `read_bytes` | `fn read_bytes(f: File, n: int): array<byte>?` | Planned | `fl_file_read_bytes` |
| `read_line` | `fn read_line(f: File): string?` | Planned | `fl_file_read_line` |
| `read_all` | `fn read_all(f: File): string?` | Planned | `fl_file_read_all` |
| `read_all_bytes` | `fn read_all_bytes(f: File): array<byte>?` | Planned | `fl_file_read_all_bytes` |
| `lines` | `fn lines(f: File): stream<string>` | Planned | `fl_file_lines` |
| `byte_stream` | `fn byte_stream(f: File): stream<byte>` | Planned | `fl_file_byte_stream` |

### Writing

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `write_bytes` | `fn write_bytes(f: File, data: array<byte>): result<int, string>` | Planned | `fl_file_write_bytes` |
| `write_string` | `fn write_string(f: File, s: string): result<int, string>` | Planned | `fl_file_write_string` |
| `flush` | `fn flush(f: File): none` | Planned | `fl_file_flush` |

### Seeking

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `seek` | `fn seek(f: File, offset: int64): result<int64, string>` | Planned | `fl_file_seek` |
| `seek_end` | `fn seek_end(f: File, offset: int64): result<int64, string>` | Planned | `fl_file_seek_end` |
| `position` | `fn position(f: File): int64` | Planned | `fl_file_position` |

### Metadata

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `size` | `fn size(f: File): int64` | Planned | `fl_file_size` |

### Behavior Notes

- `open_read` / `open_write` open in text mode (platform line-ending
  translation on Windows; no-op on POSIX). `open_read_bytes` /
  `open_write_bytes` open in binary mode (`"rb"` / `"wb"`). For serving
  files over HTTP, always use the `_bytes` variants.
- All `open_*` return `none` if the file can't be opened (doesn't exist,
  permission denied, etc). They never panic.
- `open_write` truncates the file. `open_append` preserves existing content.
- `read_bytes(f, n)` reads up to `n` bytes. Returns `none` on EOF (no bytes
  read). Returns a shorter array if fewer than `n` bytes are available.
- `read_line(f)` reads up to `\n`, strips the newline. Returns `none` on
  EOF.
- `lines(f)` returns a lazy stream of lines from the file. The stream
  yields `none` at EOF. The file handle is closed when the stream is
  released.
- `byte_stream(f)` returns a lazy stream of individual bytes. Same
  lifecycle as `lines`.
- `write_bytes` / `write_string` return the number of bytes written, or
  `err` on failure.
- `seek(f, offset)` seeks from the beginning of the file. `seek_end(f, 0)`
  seeks to the end. Both return the new absolute position.
- `position(f)` returns the current read/write position.
- `size(f)` uses `fseek`/`ftell` to determine file size without changing
  the current position.
- `close` is idempotent. A file handle that goes out of scope without being
  closed is a resource leak (Flow does not have finalizers; this matches
  the ownership model — the programmer is responsible).
- `flush` forces buffered data to be written to disk.

### Runtime Implementation Notes

```c
typedef struct {
    FILE*   fp;
    fl_bool is_binary;
} FL_File;
```

All functions wrap standard C `<stdio.h>` operations. `FL_File` is
heap-allocated and opaque to Flow code. No refcounting — single-owner
semantics match Flow's linear ownership model.

### Relationship to `io` Module

The `io` module's `read_file` / `write_file` remain as convenience
functions for the common "slurp/dump" pattern. They don't use `File`
handles internally — they open, read/write, and close in a single C
function call. This is deliberate: the convenience functions are simpler
and avoid handle lifecycle concerns.

For anything beyond whole-file operations, use `file`.

---

## Module: `sys`

**File:** `stdlib/sys.flow`

Process and environment functions. All non-pure.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `exit` | `fn exit(code: int): none` | Implemented | `fl_sys_exit` |
| `args` | `fn args(): array<string>` | Implemented | `fl_sys_args` |
| `run` | `fn run(command: string, args: array<string>): int` | Implemented | `fl_run_process` |
| `run_capture` | `fn run_capture(command: string, args: array<string>): string?` | Implemented | `fl_run_process_capture` |
| `env_get` | `fn env_get(name: string): string?` | Planned | `fl_env_get` |
| `clock_ms` | `fn clock_ms(): int64` | Planned | `fl_clock_ms` |

### Behavior Notes

- `exit(code)` terminates immediately via C `exit()`. Does not run finally
  blocks or stream cleanup.
- `args()` returns command-line arguments. `args()[0]` is the program name.
- `run(command, args)` forks and execs. Returns the exit code, or -1 on
  failure.
- `run_capture(command, args)` captures stderr. Returns `some(stderr_text)` on
  non-zero exit, `none` on success.
- `env_get(name)` reads an environment variable. Returns `none` if unset.
- `clock_ms()` returns monotonic wall-clock milliseconds (for timing, not
  wall-clock time). Wraps `clock_gettime(CLOCK_MONOTONIC)`.

---

## Module: `conv`

**File:** `stdlib/conv.flow`

Type conversions. All functions are `pure`.

| Function | Signature | Status | Notes |
|----------|-----------|--------|-------|
| `to_string` | `fn:pure to_string<T fulfills Showable>(val: T): string` | Planned | generic |
| `string_to_int` | `fn:pure string_to_int(s: string): int?` | Implemented | `fl_string_to_int_opt` |
| `string_to_int64` | `fn:pure string_to_int64(s: string): int64?` | Implemented | `fl_string_to_int64_opt` |
| `string_to_float` | `fn:pure string_to_float(s: string): float?` | Implemented | `fl_string_to_float_opt` |

`to_string` is a trivial generic wrapper: `return val.to_string()`. Its
value is providing a uniform calling convention. The underlying C runtime
functions (`fl_int_to_string`, `fl_float_to_string`, etc.) remain for use
by the compiler's monomorphized output.

Parsing functions remain type-specific — each target type has different
rules and error modes.

### Behavior Notes

- `to_string(f: float)` delegates to `fl_float_to_string` which uses
  `%.17g` — shortest representation that round-trips.
- `string_to_*` return `none` on any parse failure (non-numeric characters,
  overflow, empty string). They never panic.

---

## Module: `string`

**File:** `stdlib/string.flow`

String manipulation. All functions are `pure`.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `len` | `fn:pure len(s: string): int64` | Implemented | `fl_string_len` |
| `char_at` | `fn:pure char_at(s: string, idx: int64): char?` | Implemented | `fl_string_char_at` |
| `substring` | `fn:pure substring(s: string, start: int64, end: int64): string` | Implemented | `fl_string_substring` |
| `index_of` | `fn:pure index_of(s: string, needle: string): int?` | Implemented | `fl_string_index_of` |
| `contains` | `fn:pure contains(s: string, needle: string): bool` | Implemented | `fl_string_contains` |
| `starts_with` | `fn:pure starts_with(s: string, prefix: string): bool` | Implemented | `fl_string_starts_with` |
| `ends_with` | `fn:pure ends_with(s: string, suffix: string): bool` | Implemented | `fl_string_ends_with` |
| `split` | `fn:pure split(s: string, sep: string): array<string>` | Implemented | `fl_string_split` |
| `trim` | `fn:pure trim(s: string): string` | Implemented | `fl_string_trim` |
| `trim_left` | `fn:pure trim_left(s: string): string` | Implemented | `fl_string_trim_left` |
| `trim_right` | `fn:pure trim_right(s: string): string` | Implemented | `fl_string_trim_right` |
| `replace` | `fn:pure replace(s: string, old: string, new: string): string` | Implemented | `fl_string_replace` |
| `join` | `fn:pure join(parts: array<string>, sep: string): string` | Implemented | `fl_string_join` |
| `to_lower` | `fn:pure to_lower(s: string): string` | Implemented | `fl_string_to_lower` |
| `to_upper` | `fn:pure to_upper(s: string): string` | Implemented | `fl_string_to_upper` |
| `concat` | `fn:pure concat(a: string, b: string): string` | Implemented | `fl_string_concat` |
| `to_bytes` | `fn:pure to_bytes(s: string): array<byte>` | Implemented | `fl_string_to_bytes` |
| `from_bytes` | `fn:pure from_bytes(data: array<byte>): string` | Implemented | `fl_string_from_bytes` |
| `repeat` | `fn repeat(s: string, n: int): string` | Implemented | `fl_string_repeat` |
| `url_decode` | `fn url_decode(s: string): string` | Implemented | `fl_string_url_decode` |
| `url_encode` | `fn url_encode(s: string): string` | Implemented | `fl_string_url_encode` |

### Behavior Notes

- `char_at` uses byte indexing (bootstrap simplification — all bootstrap
  source is ASCII). Returns `none` for out-of-bounds.
- `substring(s, start, end)` is half-open `[start, end)`. Clamps to bounds.
- `split(s, "")` splits into individual characters (bytes).
- `index_of` returns the byte offset of the first occurrence, or `none`.
- `to_bytes` / `from_bytes` convert between string and raw byte array. No
  encoding validation on `from_bytes` (caller's responsibility).
- `repeat(s, n)` returns `s` concatenated `n` times. Returns `""` for `n <= 0`.
- `url_decode` decodes percent-encoded strings (`%20` → space, `+` → space).
- `url_encode` encodes non-URL-safe characters as `%XX`.

---

## Module: `string_builder`

**File:** `stdlib/string_builder.flow`

Mutable string builder for efficient incremental string construction.
Avoids the O(n^2) cost of repeated `+` concatenation.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `new` | `fn new(): StringBuilder` | Implemented | `fl_sb_new` |
| `with_capacity` | `fn with_capacity(cap: int64): StringBuilder` | Implemented | `fl_sb_with_capacity` |
| `append` | `fn append(sb: StringBuilder, s: string): none` | Implemented | `fl_sb_append` |
| `append_char` | `fn append_char(sb: StringBuilder, c: char): none` | Implemented | `fl_sb_append_char` |
| `append_int` | `fn append_int(sb: StringBuilder, v: int): none` | Implemented | `fl_sb_append_int` |
| `append_int64` | `fn append_int64(sb: StringBuilder, v: int64): none` | Implemented | `fl_sb_append_int64` |
| `append_float` | `fn append_float(sb: StringBuilder, v: float): none` | Implemented | `fl_sb_append_float` |
| `build` | `fn build(sb: StringBuilder): string` | Implemented | `fl_sb_build` |
| `len` | `fn len(sb: StringBuilder): int64` | Implemented | `fl_sb_len` |
| `clear` | `fn clear(sb: StringBuilder): none` | Implemented | `fl_sb_clear` |

### Behavior Notes

- `build` creates a new `FL_String` from the builder's contents. The builder
  can continue to be used after calling `build`.
- `clear` resets the builder to empty without deallocating its internal buffer.
- `with_capacity` pre-allocates buffer space to avoid reallocation.

---

## Module: `array`

**File:** `stdlib/array.flow`

Array access and manipulation functions.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `get_int` | `fn get_int(arr: array<int>, idx: int): int?` | Implemented | `fl_array_get_int` |
| `get_int64` | `fn get_int64(arr: array<int64>, idx: int): int64?` | Implemented | `fl_array_get_int64` |
| `get_float` | `fn get_float(arr: array<float>, idx: int): float?` | Implemented | `fl_array_get_float` |
| `get_bool` | `fn get_bool(arr: array<bool>, idx: int): bool?` | Implemented | `fl_array_get_bool` |
| `get` | `fn get(arr: array<string>, idx: int): string?` | Implemented | `fl_array_get_safe` |
| `len` | `fn len(arr: array<int>): int` | Implemented | `fl_array_len_int` |
| `len64` | `fn len64(arr: array<int>): int64` | Implemented | `fl_array_len` |
| `concat_int` | `fn concat_int(a: array<int>, b: array<int>): array<int>` | Implemented | `fl_array_concat` |
| `concat_string` | `fn concat_string(a: array<string>, b: array<string>): array<string>` | Implemented | `fl_array_concat` |
| `concat_byte` | `fn concat_byte(a: array<byte>, b: array<byte>): array<byte>` | Implemented | `fl_array_concat` |

### Behavior Notes

- `get_*` functions return `none` for out-of-bounds indices (safe access).
- `len` returns the array length as `int` (truncated from int64).
- `concat_*` creates a new array combining both input arrays.

---

## Module: `char`

**File:** `stdlib/char.flow`

Character classification and conversion. All functions are `pure`.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `is_digit` | `fn:pure is_digit(c: char): bool` | Implemented | `fl_char_is_digit` |
| `is_alpha` | `fn:pure is_alpha(c: char): bool` | Implemented | `fl_char_is_alpha` |
| `is_alphanumeric` | `fn:pure is_alphanumeric(c: char): bool` | Implemented | `fl_char_is_alphanumeric` |
| `is_whitespace` | `fn:pure is_whitespace(c: char): bool` | Implemented | `fl_char_is_whitespace` |
| `to_int` | `fn:pure to_int(c: char): int` | Implemented | `fl_char_to_int` |
| `from_int` | `fn:pure from_int(n: int): char` | Implemented | `fl_int_to_char` |
| `to_string` | `fn:pure to_string(c: char): string` | Implemented | `fl_char_to_string` |

### Behavior Notes

- `is_alpha` includes underscore (`_`), matching identifier rules.
- All classification is ASCII-only (bootstrap simplification).

---

## Module: `path`

**File:** `stdlib/path.flow`

Filesystem path manipulation. Pure functions operate on strings; impure
functions touch the filesystem.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `join` | `fn:pure join(a: string, b: string): string` | Implemented | `fl_path_join` |
| `stem` | `fn:pure stem(path: string): string` | Implemented | `fl_path_stem` |
| `parent` | `fn:pure parent(path: string): string` | Implemented | `fl_path_parent` |
| `with_suffix` | `fn:pure with_suffix(path: string, suffix: string): string` | Implemented | `fl_path_with_suffix` |
| `cwd` | `fn cwd(): string` | Implemented | `fl_path_cwd` |
| `resolve` | `fn resolve(path: string): string` | Implemented | `fl_path_resolve` |
| `exists` | `fn exists(path: string): bool` | Implemented | `fl_path_exists` |
| `is_dir` | `fn is_dir(path: string): bool` | Planned | `fl_path_is_dir` |
| `is_file` | `fn is_file(path: string): bool` | Planned | `fl_path_is_file` |
| `extension` | `fn:pure extension(path: string): string?` | Planned | `fl_path_extension` |
| `list_dir` | `fn list_dir(path: string): array<string>?` | Planned | `fl_path_list_dir` |

### Behavior Notes

- `join(a, b)` inserts `/` between `a` and `b` if `a` doesn't already end
  with `/`.
- `stem("foo/bar.txt")` returns `"bar"`.
- `parent("foo/bar.txt")` returns `"foo"`. Returns `"."` if no slash.
- `resolve` calls `realpath`. Returns the input unchanged if the path doesn't
  exist.
- `extension("foo.tar.gz")` returns `some(".gz")`. Returns `none` if no dot
  after the last slash.
- `list_dir` returns filenames (not full paths) in the directory, or `none`
  if the directory can't be opened.

---

## Module: `math`

**File:** `stdlib/math.flow`

Numeric operations. All functions are `pure`.

| Function | Signature | Status | Notes |
|----------|-----------|--------|-------|
| `abs` | `fn:pure abs<T fulfills (Numeric, Comparable)>(n: T): T` | Planned | generic |
| `min` | `fn:pure min<T fulfills Comparable>(a: T, b: T): T` | Planned | generic |
| `max` | `fn:pure max<T fulfills Comparable>(a: T, b: T): T` | Planned | generic |
| `clamp` | `fn:pure clamp<T fulfills Comparable>(val: T, lo: T, hi: T): T` | Planned | generic |
| `floor` | `fn:pure floor(f: float): float` | Planned | `fl_math_floor` |
| `ceil` | `fn:pure ceil(f: float): float` | Planned | `fl_math_ceil` |
| `round` | `fn:pure round(f: float): float` | Planned | `fl_math_round` |
| `pow` | `fn:pure pow(base: float, exp: float): float` | Planned | `fl_math_pow` |
| `sqrt` | `fn:pure sqrt(f: float): float` | Planned | `fl_math_sqrt` |
| `log` | `fn:pure log(f: float): float` | Planned | `fl_math_log` |

The generic functions are implemented in Flow using `Comparable` and
`Numeric` interface methods. The compiler monomorphizes them at each call
site. `abs` avoids a `zero()` static method by computing
`n.compare(n.negate())` — if `n` is negative, `negate()` is returned.
`clamp` delegates to `min` and `max`.

The float-specific functions (`floor`, `ceil`, `round`, `pow`, `sqrt`,
`log`) remain `native` because they wrap `<math.h>` and have no generic
equivalent.

### Constants

These can be defined as top-level `let` bindings in the module:

```
let pi: float = 3.14159265358979323846
let e: float = 2.71828182845904523536
let max_int: int = 2147483647
let min_int: int = -2147483648
```

### Behavior Notes

- Integer math functions use checked arithmetic where overflow is possible.
- `clamp_int(val, lo, hi)` returns `lo` if `val < lo`, `hi` if `val > hi`,
  else `val`.
- Float functions wrap the C `<math.h>` equivalents directly.

---

## Module: `net`

**File:** `stdlib/net.flow`

TCP networking. All functions are non-pure. This module is the primary
blocker for network-capable programs (HTTP servers, clients, etc).

### Types

```
type TcpListener   // opaque, wraps a listening socket fd
type TcpConnection // opaque, wraps a connected socket fd
```

### Functions

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `listen` | `fn listen(host: string, port: int): result<TcpListener, string>` | Planned | `fl_net_listen` |
| `accept` | `fn accept(listener: TcpListener): result<TcpConnection, string>` | Planned | `fl_net_accept` |
| `connect` | `fn connect(host: string, port: int): result<TcpConnection, string>` | Planned | `fl_net_connect` |
| `read` | `fn read(conn: TcpConnection, max_bytes: int): result<array<byte>, string>` | Planned | `fl_net_read` |
| `write` | `fn write(conn: TcpConnection, data: array<byte>): result<int, string>` | Planned | `fl_net_write` |
| `write_string` | `fn write_string(conn: TcpConnection, s: string): result<int, string>` | Planned | `fl_net_write_string` |
| `close` | `fn close(conn: TcpConnection): none` | Planned | `fl_net_close` |
| `close_listener` | `fn close_listener(listener: TcpListener): none` | Planned | `fl_net_close_listener` |
| `set_timeout` | `fn set_timeout(conn: TcpConnection, ms: int): none` | Planned | `fl_net_set_timeout` |
| `remote_addr` | `fn remote_addr(conn: TcpConnection): string` | Planned | `fl_net_remote_addr` |

### Behavior Notes

- `listen(host, port)` creates a socket, binds, and listens. `host` is
  typically `"0.0.0.0"` or `"127.0.0.1"`. Returns `err(message)` if bind
  fails (e.g., port in use).
- `accept(listener)` blocks until a client connects. Returns a new
  `TcpConnection`.
- `connect(host, port)` establishes an outbound TCP connection. Useful for
  HTTP clients, testing, etc.
- `read(conn, max_bytes)` reads up to `max_bytes` from the connection.
  Returns `err` on connection reset or timeout. Returns an empty array on
  clean close.
- `write(conn, data)` writes the byte array. Returns the number of bytes
  written, or `err` on failure.
- `write_string(conn, s)` convenience wrapper — converts string to bytes
  and writes. Avoids the need for explicit `string.to_bytes()` on every
  response write.
- `close` closes the connection fd. Idempotent.
- `set_timeout(conn, ms)` sets read/write timeout via `SO_RCVTIMEO` /
  `SO_SNDTIMEO`. 0 means no timeout (blocking).
- `remote_addr(conn)` returns `"ip:port"` string of the peer.

### Runtime Implementation Notes

The C runtime types will be:

```c
typedef struct {
    int fd;
} FL_TcpListener;

typedef struct {
    int fd;
} FL_TcpConnection;
```

`fl_net_listen` wraps `socket()` + `setsockopt(SO_REUSEADDR)` + `bind()` +
`listen()`. Backlog defaults to 128.

`fl_net_read` wraps `recv()` into a heap-allocated `FL_Array` of bytes.

---

## Module: `stream`

**File:** `stdlib/stream.flow`

Stream construction, transformation, and consumption. Streams are lazy,
pull-based sequences — the core iteration abstraction in Flow. Most
transformation functions are `pure` (they build new streams without side
effects); consumption functions that exhaust a stream are non-pure since
they drive effects in the underlying source.

### Construction

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `range` | `fn:pure range(start: int, end: int): stream<int>` | Planned | `fl_stream_range` |
| `range_step` | `fn:pure range_step(start: int, end: int, step: int): stream<int>` | Planned | `fl_stream_range_step` |
| `from_array` | `fn:pure from_array(arr: array<T>): stream<T>` | Planned | `fl_stream_from_array` |
| `repeat` | `fn:pure repeat(val: T, n: int): stream<T>` | Planned | `fl_stream_repeat` |
| `empty` | `fn:pure empty(): stream<T>` | Planned | `fl_stream_empty` |

### Transformation (lazy — return new streams)

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `take` | `fn:pure take(src: stream<T>, n: int): stream<T>` | Implemented | `fl_stream_take` |
| `skip` | `fn:pure skip(src: stream<T>, n: int): stream<T>` | Implemented | `fl_stream_skip` |
| `map` | `fn:pure map(src: stream<T>, f: fn(T): U): stream<U>` | Implemented | `fl_stream_map` |
| `filter` | `fn:pure filter(src: stream<T>, f: fn(T): bool): stream<T>` | Implemented | `fl_stream_filter` |
| `enumerate` | `fn:pure enumerate(src: stream<T>): stream<(int, T)>` | Planned | `fl_stream_enumerate` |
| `zip` | `fn:pure zip(a: stream<T>, b: stream<U>): stream<(T, U)>` | Planned | `fl_stream_zip` |
| `chain` | `fn:pure chain(a: stream<T>, b: stream<T>): stream<T>` | Planned | `fl_stream_chain` |
| `flat_map` | `fn:pure flat_map(src: stream<T>, f: fn(T): stream<U>): stream<U>` | Planned | `fl_stream_flat_map` |

### Consumption (eager — exhaust the stream)

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `reduce` | `fn reduce(src: stream<T>, init: U, f: fn(U, T): U): U` | Implemented | `fl_stream_reduce` |
| `collect` | `fn collect(src: stream<T>): buffer<T>` | Implemented | `fl_buffer_collect` |
| `to_array` | `fn to_array(src: stream<T>): array<T>` | Planned | `fl_stream_to_array` |
| `foreach` | `fn foreach(src: stream<T>, f: fn(T): none): none` | Planned | `fl_stream_foreach` |
| `count` | `fn count(src: stream<T>): int` | Planned | `fl_stream_count` |
| `any` | `fn any(src: stream<T>, f: fn(T): bool): bool` | Planned | `fl_stream_any` |
| `all` | `fn all(src: stream<T>, f: fn(T): bool): bool` | Planned | `fl_stream_all` |
| `find` | `fn find(src: stream<T>, f: fn(T): bool): T?` | Planned | `fl_stream_find` |
| `sum_int` | `fn sum_int(src: stream<int>): int` | Planned | `fl_stream_sum_int` |

### Behavior Notes

- `range(start, end)` produces `[start, end)` — half-open, matching
  `substring` and `slice` conventions. `range(0, 0)` is empty.
- `range_step(0, 10, 2)` produces `0, 2, 4, 6, 8`.
- Transformation functions are lazy — they return immediately and only
  pull from the source when the resulting stream is consumed.
- `collect` returns a `buffer<T>`. Use `to_array` if you need an immutable
  `array<T>` (it collects into a buffer then converts).
- `foreach` is the idiomatic way to consume a stream for side effects.
  Equivalent to a `for item in stream { ... }` loop.
- `any` / `all` short-circuit — they stop consuming as soon as the answer
  is determined.
- `find` returns the first element matching the predicate, or `none`.
  Short-circuits.
- `sum_int` is a convenience for the common `reduce(s, 0, fn(a, b) { a + b })`
  pattern. Uses checked arithmetic.
- `zip` terminates when either input stream is exhausted.
- `chain(a, b)` produces all elements of `a`, then all elements of `b`.
- `flat_map` is equivalent to `map` followed by flattening nested streams.

---

## Module: `channel`

**File:** `stdlib/channel.flow`

Bounded, thread-safe FIFO channels for concurrent communication. Non-pure.

### Functions

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `new` | `fn new(capacity: int): channel<T>` | Implemented | `fl_channel_new` |
| `send` | `fn send(ch: channel<T>, val: T): none` | Implemented | `fl_channel_send` (+ panic wrapper) |
| `recv` | `fn recv(ch: channel<T>): T?` | Implemented | `fl_channel_recv` |
| `close` | `fn close(ch: channel<T>): none` | Implemented | `fl_channel_close` |
| `len` | `fn len(ch: channel<T>): int` | Implemented | `fl_channel_len` |
| `is_closed` | `fn is_closed(ch: channel<T>): bool` | Implemented | `fl_channel_is_closed` |
| `try_send` | `fn try_send(ch: channel<T>, val: T): bool` | Planned | `fl_channel_try_send` |
| `try_recv` | `fn try_recv(ch: channel<T>): T?` | Planned | `fl_channel_try_recv` |

### Behavior Notes

- `send` blocks if the channel is full. Panics if the channel is closed
  (the internal `fl_channel_send` returns false; the compiler-generated
  wrapper checks this and panics).
- `recv` blocks if the channel is empty. Returns `none` when the channel
  is closed and drained. Re-throws any exception stored by the producer.
- `close` is idempotent. Wakes all blocked senders and receivers.
- `try_send` / `try_recv` are non-blocking variants. `try_send` returns
  false if the channel is full or closed. `try_recv` returns `none` if
  empty (without waiting for close).

---

## Module: `bytes`

**File:** `stdlib/bytes.flow`

Byte array utilities for working with binary data. Needed for network
protocols, file formats, etc. All manipulation functions are `pure`.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `from_string` | `fn:pure from_string(s: string): array<byte>` | Planned | `fl_bytes_from_string` |
| `to_string` | `fn:pure to_string(data: array<byte>): string` | Planned | `fl_bytes_to_string` |
| `slice` | `fn:pure slice(data: array<byte>, start: int64, end: int64): array<byte>` | Planned | `fl_bytes_slice` |
| `concat` | `fn:pure concat(a: array<byte>, b: array<byte>): array<byte>` | Planned | `fl_bytes_concat` |
| `index_of` | `fn:pure index_of(data: array<byte>, needle: array<byte>): int?` | Planned | `fl_bytes_index_of` |
| `len` | `fn:pure len(data: array<byte>): int64` | Planned | `fl_bytes_len` |

### Behavior Notes

- `from_string` / `to_string` are the bridge between text and binary
  worlds. `to_string` treats the bytes as UTF-8 (no validation for
  bootstrap).
- `slice(data, start, end)` is half-open `[start, end)`, returns a new
  array.
- These functions are essential for building HTTP responses where headers
  are text but the body may be binary.

---

## Module: `map`

**File:** `stdlib/map.flow`

Hash map operations. Currently exposed through compiler-generated code;
this module provides a user-facing API.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `new` | `fn new(): map<string, string>` | Implemented | `fl_map_new` |
| `set` | `fn set(m: map<string, string>, key: string, val: string): map<string, string>` | Implemented | `fl_map_set_str` |
| `get` | `fn get(m: map<string, string>, key: string): string?` | Implemented | `fl_map_get_str` |
| `has` | `fn has(m: map<string, string>, key: string): bool` | Implemented | `fl_map_has_str` |
| `remove` | `fn remove(m: map<string, string>, key: string): map<string, string>` | Implemented | `fl_map_remove_str` |
| `len` | `fn len(m: map<string, string>): int64` | Implemented | `fl_map_len` |
| `keys` | `fn keys(m: map<string, string>): array<string>` | Implemented | `fl_map_keys` |
| `values` | `fn values(m: map<string, string>): array<string>` | Implemented | `fl_map_values` |

### Behavior Notes

- The current implementation is specialized for `string` keys and values.
  Generic `map<K, V>` support requires monomorphization improvements.
- Maps are persistent (immutable). `set` returns a new map. This aligns
  with Flow's ownership model.
- Keys are compared by byte content (structural equality).
- `keys` and `values` return arrays in insertion order.

---

## Module: `set`

**File:** `stdlib/set.flow`

Hash set operations. Runtime implementation exists (`FL_Set`), backed by
`FL_Map` internally. All functions are non-pure (sets are mutable
collections).

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `new` | `fn new(): set<T>` | Implemented | `fl_set_new` |
| `add` | `fn add(s: set<T>, val: T): bool` | Implemented | `fl_set_add` |
| `has` | `fn has(s: set<T>, val: T): bool` | Implemented | `fl_set_has` |
| `remove` | `fn remove(s: set<T>, val: T): bool` | Implemented | `fl_set_remove` |
| `len` | `fn len(s: set<T>): int64` | Implemented | `fl_set_len` |
| `to_array` | `fn to_array(s: set<T>): array<T>` | Planned | `fl_set_to_array` |
| `to_stream` | `fn to_stream(s: set<T>): stream<T>` | Planned | `fl_set_to_stream` |

### Behavior Notes

- `add` returns true if the element was new, false if already present.
- `remove` returns true if the element was present and removed, false if
  not found.
- Elements are compared by byte content (structural equality), same as
  map keys.
- `to_array` / `to_stream` iterate the set in insertion order (not
  guaranteed — implementation detail of the hash table). Users should not
  depend on ordering.

---

## Module: `buffer`

**File:** `stdlib/buffer.flow`

Mutable, growable sequence — the counterpart to immutable `array`. Buffers
are the primary collection for building up data incrementally (parsing
tokens, collecting results, building output). All functions are non-pure.

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `new` | `fn new(): buffer<T>` | Implemented | `fl_buffer_new` |
| `with_capacity` | `fn with_capacity(cap: int64): buffer<T>` | Implemented | `fl_buffer_with_capacity` |
| `push` | `fn push(buf: buffer<T>, val: T): none` | Implemented | `fl_buffer_push` |
| `get` | `fn get(buf: buffer<T>, idx: int64): T?` | Implemented | `fl_buffer_get` |
| `len` | `fn len(buf: buffer<T>): int64` | Implemented | `fl_buffer_len` |
| `drain` | `fn drain(buf: buffer<T>): stream<T>` | Implemented | `fl_buffer_drain` |
| `sort_by` | `fn sort_by(buf: buffer<T>, cmp: fn(T, T): int): none` | Implemented | `fl_buffer_sort_by` |
| `reverse` | `fn reverse(buf: buffer<T>): none` | Implemented | `fl_buffer_reverse` |
| `collect` | `fn collect(src: stream<T>): buffer<T>` | Implemented | `fl_buffer_collect` |
| `to_array` | `fn to_array(buf: buffer<T>): array<T>` | Planned | `fl_buffer_to_array` |
| `clear` | `fn clear(buf: buffer<T>): none` | Planned | `fl_buffer_clear` |
| `pop` | `fn pop(buf: buffer<T>): T?` | Planned | `fl_buffer_pop` |
| `last` | `fn last(buf: buffer<T>): T?` | Planned | `fl_buffer_last` |
| `set` | `fn set(buf: buffer<T>, idx: int64, val: T): none` | Planned | `fl_buffer_set` |
| `insert` | `fn insert(buf: buffer<T>, idx: int64, val: T): none` | Planned | `fl_buffer_insert` |
| `remove` | `fn remove(buf: buffer<T>, idx: int64): T?` | Planned | `fl_buffer_remove` |
| `contains` | `fn contains(buf: buffer<T>, val: T): bool` | Planned | `fl_buffer_contains` |
| `slice` | `fn slice(buf: buffer<T>, start: int64, end: int64): buffer<T>` | Planned | `fl_buffer_slice` |

### Behavior Notes

- `push` appends to the end. Amortized O(1) with geometric growth.
- `pop` removes and returns the last element, or `none` if empty.
- `sort_by(buf, cmp)` sorts in-place. `cmp` returns negative/zero/positive
  (standard comparator convention). Wraps C `qsort`.
- `reverse` reverses in-place.
- `drain` returns a lazy stream that yields elements in order. The buffer
  retains the data (drain doesn't consume the buffer — it's a view).
- `to_array` creates an immutable copy. The buffer is not consumed.
- `collect` builds a buffer from a stream. This is the bridge between
  lazy streams and eager collections.
- `clear` resets length to 0 without freeing the backing allocation.
- `set(buf, idx, val)` replaces the element at `idx`. Panics on
  out-of-bounds.
- `insert(buf, idx, val)` inserts at position, shifting elements right.
- `remove(buf, idx)` removes at position, shifting elements left. Returns
  the removed element.
- `slice(buf, start, end)` returns a new buffer with a copy of `[start, end)`.

---

## Module: `sort`

**File:** `stdlib/sort.flow`

Sorting for arrays and convenience comparators. All sort functions return
new arrays (arrays are immutable in Flow). Pure.

| Function | Signature | Status | Notes |
|----------|-----------|--------|-------|
| `sort` | `fn:pure sort<T fulfills Comparable>(arr: array<T>): array<T>` | Planned | generic |
| `sort_by` | `fn:pure sort_by<T>(arr: array<T>, cmp: fn(T, T): int): array<T>` | Planned | `fl_sort_array_by` |
| `reverse` | `fn:pure reverse<T>(arr: array<T>): array<T>` | Planned | `fl_array_reverse` |

`sort` is implemented in Flow as `sort_by(arr, fn(a: T, b: T): int { a.compare(b) })`.
The compiler monomorphizes it for each concrete element type. `sort_by` and
`reverse` remain `native` — they are type-erased operations over `void*` elements.

### Behavior Notes

- `sort(arr)` sorts by the natural `Comparable` ordering. Ascending. For
  descending, compose with `reverse`.
- `sort_by(arr, cmp)` copies the array into a buffer, sorts via `qsort`,
  and returns a new array. The original is untouched.
- `reverse` returns a new array with elements in reversed order.
- All functions allocate a new array — they never mutate the input.

### Runtime Implementation Notes

Implementation pattern for `fl_sort_array_by`:

```c
FL_Array* fl_sort_array_by(FL_Array* arr, FL_Closure* cmp) {
    // 1. Copy arr data into a temporary buffer
    // 2. qsort with a wrapper that calls the closure
    // 3. Build new FL_Array from sorted data
}
```

The `qsort` comparator wrapper needs to call through the `FL_Closure`,
which requires thread-local storage to pass the closure pointer to the
C comparator function (since `qsort`'s comparator takes no user context).
Alternatively, use `qsort_r` where available.

---

## Module: `json`

**File:** `stdlib/json.flow`

JSON parsing and serialization. Non-pure (parsing allocates; serialization
is pure but grouped here for cohesion).

### Types

```
type JsonValue = sum {
    JsonNull
    JsonBool(bool)
    JsonInt(int64)
    JsonFloat(float)
    JsonString(string)
    JsonArray(array<JsonValue>)
    JsonObject(map<string, JsonValue>)
}
```

### Parsing

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `parse` | `fn parse(s: string): result<JsonValue, string>` | Planned | `fl_json_parse` |

### Serialization

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `to_string` | `fn:pure to_string(val: JsonValue): string` | Planned | `fl_json_to_string` |
| `to_string_pretty` | `fn:pure to_string_pretty(val: JsonValue, indent: int): string` | Planned | `fl_json_to_string_pretty` |

### Accessors (convenience for navigating parsed JSON)

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `get` | `fn:pure get(val: JsonValue, key: string): JsonValue?` | Planned | `fl_json_get` |
| `get_index` | `fn:pure get_index(val: JsonValue, idx: int): JsonValue?` | Planned | `fl_json_get_index` |
| `as_string` | `fn:pure as_string(val: JsonValue): string?` | Planned | `fl_json_as_string` |
| `as_int` | `fn:pure as_int(val: JsonValue): int64?` | Planned | `fl_json_as_int` |
| `as_float` | `fn:pure as_float(val: JsonValue): float?` | Planned | `fl_json_as_float` |
| `as_bool` | `fn:pure as_bool(val: JsonValue): bool?` | Planned | `fl_json_as_bool` |
| `as_array` | `fn:pure as_array(val: JsonValue): array<JsonValue>?` | Planned | `fl_json_as_array` |
| `is_null` | `fn:pure is_null(val: JsonValue): bool` | Planned | `fl_json_is_null` |

### Building (convenience for constructing JSON)

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `null_val` | `fn:pure null_val(): JsonValue` | Planned | `fl_json_null` |
| `string_val` | `fn:pure string_val(s: string): JsonValue` | Planned | `fl_json_string` |
| `int_val` | `fn:pure int_val(n: int64): JsonValue` | Planned | `fl_json_int` |
| `float_val` | `fn:pure float_val(f: float): JsonValue` | Planned | `fl_json_float` |
| `bool_val` | `fn:pure bool_val(b: bool): JsonValue` | Planned | `fl_json_bool` |
| `array_val` | `fn:pure array_val(items: array<JsonValue>): JsonValue` | Planned | `fl_json_array` |
| `object_val` | `fn:pure object_val(m: map<string, JsonValue>): JsonValue` | Planned | `fl_json_object` |

### Behavior Notes

- `parse` handles the full JSON spec (RFC 8259): objects, arrays, strings
  (with escape sequences), numbers (integer and floating-point), booleans,
  null. Returns `err(message)` with a description of the parse error
  including approximate position.
- Numbers without a decimal point or exponent are parsed as `JsonInt`.
  Numbers with `.` or `e`/`E` are parsed as `JsonFloat`. Numbers that
  overflow `int64` are parsed as `JsonFloat`.
- `to_string` produces compact JSON (no whitespace). `to_string_pretty`
  indents with `indent` spaces per level.
- `get(val, key)` works on `JsonObject` — returns `none` if the value is
  not an object or the key is not present.
- `get_index(val, idx)` works on `JsonArray` — returns `none` if not an
  array or index is out of bounds.
- `as_*` accessors return `none` if the value is not the expected variant.

### Runtime Implementation Notes

The parser is a recursive descent parser implemented in C. The `JsonValue`
sum type maps to a tagged struct:

```c
typedef struct FL_JsonValue {
    fl_byte tag;  // 0=null, 1=bool, 2=int, 3=float, 4=string, 5=array, 6=object
    union {
        fl_bool     bool_val;
        fl_int64    int_val;
        fl_float    float_val;
        FL_String*  string_val;
        FL_Array*   array_val;   // array of FL_JsonValue*
        FL_Map*     object_val;  // map from string bytes to FL_JsonValue*
    } data;
} FL_JsonValue;
```

String escapes handled: `\"`, `\\`, `\/`, `\b`, `\f`, `\n`, `\r`, `\t`,
`\uXXXX`. Surrogate pairs are converted to UTF-8.

---

## Module: `random`

**File:** `stdlib/random.flow`

Random number generation. All functions are non-pure (they read from the
OS entropy source or advance PRNG state).

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `int_range` | `fn int_range(min: int, max: int): int` | Planned | `fl_random_int_range` |
| `int64_range` | `fn int64_range(min: int64, max: int64): int64` | Planned | `fl_random_int64_range` |
| `float_unit` | `fn float_unit(): float` | Planned | `fl_random_float_unit` |
| `bool` | `fn bool(): bool` | Planned | `fl_random_bool` |
| `bytes` | `fn bytes(n: int): array<byte>` | Planned | `fl_random_bytes` |
| `shuffle` | `fn shuffle(arr: array<T>): array<T>` | Planned | `fl_random_shuffle` |
| `choice` | `fn choice(arr: array<T>): T?` | Planned | `fl_random_choice` |

### Behavior Notes

- `int_range(min, max)` returns a uniformly distributed integer in
  `[min, max]` (inclusive on both ends). Panics if `min > max`.
- `float_unit()` returns a uniformly distributed float in `[0.0, 1.0)`.
- `bool()` returns true or false with equal probability.
- `bytes(n)` returns `n` cryptographically random bytes. Reads from
  `/dev/urandom` (Linux) or `arc4random_buf` (macOS).
- `shuffle(arr)` returns a new array with elements in random order
  (Fisher-Yates). Does not mutate the input.
- `choice(arr)` returns a random element, or `none` if the array is empty.

### Runtime Implementation Notes

Seed from `/dev/urandom` on first call. Use `xoshiro256**` as the PRNG
for `int_range`, `float_unit`, etc. Use `/dev/urandom` directly for
`bytes` (cryptographic quality).

```c
static __thread fl_uint64 _fl_rng_state[4];
static __thread fl_bool   _fl_rng_seeded = fl_false;

static void _fl_rng_seed(void) {
    FILE* f = fopen("/dev/urandom", "rb");
    fread(_fl_rng_state, sizeof(_fl_rng_state), 1, f);
    fclose(f);
    _fl_rng_seeded = fl_true;
}
```

Thread-local state ensures concurrent coroutines don't interfere.

---

## Module: `time`

**File:** `stdlib/time.flow`

Wall-clock time, timestamps, and formatting. All functions are non-pure.

### Types

```
type Instant   // opaque, monotonic timestamp for measuring durations
type DateTime  // opaque, wall-clock time with timezone info
```

### Monotonic Time (for measuring durations)

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `mono_now` | `fn mono_now(): Instant` | Planned | `fl_time_now` |
| `elapsed_ms` | `fn elapsed_ms(start: Instant): int64` | Planned | `fl_time_elapsed_ms` |
| `elapsed_us` | `fn elapsed_us(start: Instant): int64` | Planned | `fl_time_elapsed_us` |
| `diff_ms` | `fn:pure diff_ms(start: Instant, end: Instant): int64` | Planned | `fl_time_diff_ms` |

### Wall-Clock Time

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `datetime_now` | `fn datetime_now(): DateTime` | Implemented | `fl_time_datetime_now` |
| `datetime_utc` | `fn datetime_utc(): DateTime` | Implemented | `fl_time_datetime_utc` |
| `now` | `fn now(): int64` | Implemented | `fl_time_unix_timestamp` |
| `now_ms` | `fn now_ms(): int64` | Implemented | `fl_time_unix_timestamp_ms` |

### Formatting

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `format_iso8601` | `fn format_iso8601(dt: DateTime): string` | Implemented | `fl_time_format_iso8601` |
| `format_rfc2822` | `fn format_rfc2822(dt: DateTime): string` | Implemented | `fl_time_format_rfc2822` |
| `format_http` | `fn format_http(dt: DateTime): string` | Implemented | `fl_time_format_http` |

### Components

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `year` | `fn year(dt: DateTime): int` | Implemented | `fl_time_year` |
| `month` | `fn month(dt: DateTime): int` | Implemented | `fl_time_month` |
| `day` | `fn day(dt: DateTime): int` | Implemented | `fl_time_day` |
| `hour` | `fn hour(dt: DateTime): int` | Implemented | `fl_time_hour` |
| `minute` | `fn minute(dt: DateTime): int` | Implemented | `fl_time_minute` |
| `second` | `fn second(dt: DateTime): int` | Implemented | `fl_time_second` |

### Behavior Notes

- `now()` returns a monotonic instant from `clock_gettime(CLOCK_MONOTONIC)`.
  Only useful for measuring durations — not a wall-clock time.
- `elapsed_ms(start)` is shorthand for `diff_ms(start, now())`.
- `datetime_now()` returns local time. `datetime_utc()` returns UTC.
- `unix_timestamp()` returns seconds since Unix epoch (1970-01-01T00:00:00Z).
- `format_iso8601` produces `"2026-02-22T14:30:00Z"` (UTC) or
  `"2026-02-22T14:30:00-05:00"` (with offset).
- `format_rfc2822` produces `"Sun, 22 Feb 2026 14:30:00 +0000"` — used in
  email headers.
- `format_http` produces `"Sun, 22 Feb 2026 14:30:00 GMT"` — the format
  required by HTTP `Date:` headers (RFC 7231). This is what the static
  file server needs.
- Component accessors (`year`, `month`, etc.) return values in the
  `DateTime`'s timezone. `month` is 1-12. `day` is 1-31.

### Runtime Implementation Notes

```c
typedef struct {
    struct timespec ts;
} FL_Instant;

typedef struct {
    time_t      epoch;
    fl_int      utc_offset;  // seconds east of UTC
    struct tm   components;  // cached broken-down time
} FL_DateTime;
```

`format_*` functions use `strftime` where possible. `format_http` always
formats in GMT regardless of the `DateTime`'s timezone.

---

## Module: `testing`

**File:** `stdlib/testing.flow`

Minimal test framework for writing tests in Flow. Required for the
self-hosted compiler's own test suite (Epic 11). All functions are
non-pure.

### Types

```
type TestResult = sum {
    Pass
    Fail(string)  // failure message
}
```

### Assertions

| Function | Signature | Status | Notes |
|----------|-----------|--------|-------|
| `assert_true` | `fn assert_true(cond: bool, msg: string): void` | Planned | `fl_test_assert_true` |
| `assert_false` | `fn assert_false(cond: bool, msg: string): void` | Planned | `fl_test_assert_false` |
| `assert_eq` | `fn assert_eq<T fulfills (Equatable, Showable)>(expected: T, actual: T, msg: string): void` | Planned | generic |
| `assert_approx` | `fn assert_approx(expected: float, actual: float, epsilon: float, msg: string): void` | Planned | float-specific |
| `assert_some` | `fn assert_some<T>(val: T?): T` | Planned | `fl_test_assert_some` |
| `assert_none` | `fn assert_none<T>(val: T?): void` | Planned | `fl_test_assert_none` |
| `fail` | `fn fail(msg: string): void` | Planned | `fl_test_fail` |

`assert_eq` is implemented in Flow using `Equatable.equals` and
`Showable.to_string`. The compiler monomorphizes it per concrete type.
`assert_approx` (epsilon comparison) is kept separate — epsilon comparison
is a fundamentally different operation from exact equality and has no
generic equivalent.

### Test Runner

| Function | Signature | Status | Runtime |
|----------|-----------|--------|---------|
| `run` | `fn run(name: string, test_fn: fn(): none): TestResult` | Planned | `fl_test_run` |
| `run_all` | `fn run_all(tests: array<(string, fn(): none)>): int` | Planned | `fl_test_run_all` |
| `report` | `fn report(results: array<(string, TestResult)>): none` | Planned | `fl_test_report` |

### Behavior Notes

- Assertion functions throw an exception (using the existing exception
  mechanism) on failure. The exception carries the failure message
  including expected vs actual values.
- `assert_eq_float` uses epsilon comparison: passes if
  `abs(expected - actual) < epsilon`.
- `assert_some(val)` returns the unwrapped value on success, throws on
  `none`. This is the idiomatic pattern for "unwrap or fail the test."
- `fail(msg)` unconditionally fails the current test. Useful for
  unreachable branches: `_ -> testing.fail("unexpected variant")`.
- `run(name, test_fn)` executes `test_fn` inside a catch frame. Returns
  `Pass` if no exception, `Fail(message)` if an assertion exception is
  caught.
- `run_all(tests)` runs all tests, prints results to stdout, returns the
  number of failures. The exit code of a test program is this return value
  (0 = all passed).
- `report` prints a formatted summary:
  ```
  PASS  test_lexer_integers
  PASS  test_lexer_strings
  FAIL  test_lexer_floats: expected 3.14, got 3.15
  ---
  2 passed, 1 failed, 3 total
  ```

### Runtime Implementation Notes

Assertions are thin: they check the condition, and if false, format a
message string and call `_fl_throw` with a test-failure exception tag.

`fl_test_run` wraps the test function in `setjmp`/`_fl_exception_push`:

```c
FL_TestResult fl_test_run(FL_String* name, FL_Closure* test_fn) {
    FL_ExceptionFrame ef;
    _fl_exception_push(&ef);
    if (setjmp(ef.jmp) == 0) {
        ((void(*)(void*))test_fn->fn)(test_fn->env);
        _fl_exception_pop();
        return (FL_TestResult){.tag = 0};  // Pass
    } else {
        _fl_exception_pop();
        FL_String* msg = (FL_String*)ef.exception;
        return (FL_TestResult){.tag = 1, .message = msg};  // Fail
    }
}
```

### Design Note

This is deliberately minimal — just enough to write assertion-based tests
with a runner that reports pass/fail. There is no test discovery, no
fixtures, no mocking, no parameterized tests. The self-hosted compiler's
test suite will be a Flow program that calls `testing.run_all` with an
explicit list of test functions. This matches the bootstrap constraint:
simple, no magic.

---

## Example: Static File HTTP Server

With the modules above, a static file server becomes straightforward:

```
module http_server

use io
use net
use path
use string
use conv
use bytes

fn content_type(file_path: string): string {
    match true {
        string.ends_with(file_path, ".html") -> "text/html"
        string.ends_with(file_path, ".css")  -> "text/css"
        string.ends_with(file_path, ".js")   -> "application/javascript"
        string.ends_with(file_path, ".json") -> "application/json"
        string.ends_with(file_path, ".png")  -> "image/png"
        string.ends_with(file_path, ".jpg")  -> "image/jpeg"
        string.ends_with(file_path, ".svg")  -> "image/svg+xml"
        string.ends_with(file_path, ".txt")  -> "text/plain"
        _                                    -> "application/octet-stream"
    }
}

fn handle_request(conn: net.TcpConnection, root: string): none {
    let request_bytes = match net.read(conn, 4096) {
        ok(data) -> data
        err(_)   -> { net.close(conn); return }
    }
    let request = bytes.to_string(request_bytes)
    let lines = string.split(request, "\r\n")
    let parts = string.split(lines[0], " ")
    let method = parts[0]
    let url_path = parts[1]

    // Only serve GET
    if method != "GET" {
        let resp = "HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n"
        net.write_string(conn, resp)
        net.close(conn)
        return
    }

    // Map URL to filesystem
    let file_path = path.join(root, url_path)

    match io.read_file(file_path) {
        some(contents) -> {
            let ct = content_type(file_path)
            let header = f"HTTP/1.1 200 OK\r\nContent-Type: {ct}\r\nContent-Length: {string.len(contents)}\r\n\r\n"
            net.write_string(conn, header)
            net.write_string(conn, contents)
        }
        none -> {
            let body = "404 Not Found"
            let header = f"HTTP/1.1 404 Not Found\r\nContent-Length: {string.len(body)}\r\n\r\n"
            net.write_string(conn, header)
            net.write_string(conn, body)
        }
    }
    net.close(conn)
}

fn main(): none {
    let root = "./public"
    let port = 8080
    io.println(f"Serving {root} on port {port}")

    let listener = match net.listen("0.0.0.0", port) {
        ok(l)  -> l
        err(e) -> { io.eprintln(f"Failed to listen: {e}"); sys.exit(1) }
    }

    // Accept loop
    loop {
        match net.accept(listener) {
            ok(conn) -> handle_request(conn, root)
            err(e)   -> io.eprintln(f"Accept error: {e}")
        }
    }
}
```

### What this example exercises

| Module | Functions used |
|--------|---------------|
| `io` | `println`, `eprintln`, `read_file` |
| `net` | `listen`, `accept`, `read`, `write_string`, `close` |
| `path` | `join` |
| `string` | `split`, `ends_with`, `len` |
| `bytes` | `to_string` |
| `conv` | (via f-strings) `int_to_string`, `int64_to_string` |

### Implementation priority for this example

1. `net` module (the only hard blocker — everything else exists)
2. `bytes.to_string` / `bytes.from_string` (bridging text and binary)
3. `io.read_file_bytes` (for serving binary files like images)

---

## Implementation Status Summary

| Module | Implemented | Planned | Total |
|--------|-------------|---------|-------|
| `io` | 9 | 3 | 12 |
| `file` | 0 | 20 | 20 |
| `sys` | 4 | 2 | 6 |
| `conv` | 7 | 0 | 7 |
| `string` | 19 | 2 | 21 |
| `string_builder` | 10 | 0 | 10 |
| `char` | 7 | 0 | 7 |
| `path` | 7 | 4 | 11 |
| `math` | 0 | 13 | 13 |
| `net` | 0 | 10 | 10 |
| `stream` | 5 | 17 | 22 |
| `channel` | 6 | 2 | 8 |
| `bytes` | 0 | 6 | 6 |
| `array` | 10 | 0 | 10 |
| `map` | 8 | 0 | 8 |
| `set` | 5 | 2 | 7 |
| `buffer` | 9 | 9 | 18 |
| `sort` | 0 | 5 | 5 |
| `json` | 0 | 19 | 19 |
| `random` | 0 | 7 | 7 |
| `time` | 13 | 4 | 17 |
| `testing` | 0 | 13 | 13 |
| **Total** | **119** | **138** | **257** |
