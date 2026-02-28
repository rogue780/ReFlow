# Appendix B: Standard Library Reference

This appendix documents every module in the Flow standard library. Each entry
shows the function signature as it appears in Flow source, a one-line
description, and a minimal usage example. Functions marked `fn:pure` are
guaranteed side-effect-free.

Modules are imported with `import module_name` (qualified access) or
`import module_name (fn1, fn2)` (unqualified access). Both styles appear
in the examples below.

---

## B.1 `io` --- Input/Output

The `io` module provides console I/O and one-shot file operations. For
handle-based file I/O with seeking and streaming, see `file` (B.2).

| Signature | Description |
|-----------|-------------|
| `fn print(s: string): none` | Write `s` to stdout without a trailing newline. |
| `fn println(s: string): none` | Write `s` to stdout followed by a newline. |
| `fn eprint(s: string): none` | Write `s` to stderr without a trailing newline. |
| `fn eprintln(s: string): none` | Write `s` to stderr followed by a newline. |
| `fn read_line(): string?` | Read one line from stdin. Returns `none` at EOF. |
| `fn read_byte(): byte?` | Read one byte from stdin. Returns `none` at EOF. |
| `fn read_stdin(): string?` | Read all remaining stdin as a string. |
| `fn read_file(path: string): string?` | Read entire file contents. Returns `none` on failure. |
| `fn write_file(path: string, contents: string): bool` | Write string to file, creating or truncating it. |
| `fn append_file(path: string, contents: string): bool` | Append string to file. |
| `fn read_file_bytes(path: string): array<byte>?` | Read entire file as raw bytes. |
| `fn write_file_bytes(path: string, data: array<byte>): bool` | Write raw bytes to file. |
| `fn tmpfile_create(suffix: string, contents: string): string` | Create a temp file with given suffix and contents; returns the path. |
| `fn tmpfile_remove(path: string): none` | Delete a temp file created by `tmpfile_create`. |

```flow
import io (println, print, read_line, read_file, write_file)

fn main() {
    print("Name: ")
    match read_line() {
        some(name) -> println(f"Hello, {name}!")
        none -> println("No input")
    }

    write_file("/tmp/greeting.txt", "Hello from Flow!")
    match read_file("/tmp/greeting.txt") {
        some(s) -> println(s)
        none -> println("read failed")
    }
}
```

---

## B.2 `file` --- Handle-Based File I/O

The `file` module provides handle-based file operations with explicit open,
read/write, seek, and close. All open functions return `file?`; a `none` result
indicates failure to open.

| Signature | Description |
|-----------|-------------|
| `fn open_read(path: string): file?` | Open a file for text reading. |
| `fn open_write(path: string): file?` | Open a file for text writing (creates/truncates). |
| `fn open_append(path: string): file?` | Open a file for appending. |
| `fn open_read_bytes(path: string): file?` | Open a file for binary reading. |
| `fn open_write_bytes(path: string): file?` | Open a file for binary writing. |
| `fn close(f: file): none` | Close an open file handle. |
| `fn read_line(f: file): string?` | Read one line. Returns `none` at EOF. |
| `fn read_all(f: file): string?` | Read all remaining content as a string. |
| `fn read_bytes(f: file, n: int): array<byte>?` | Read up to `n` bytes. |
| `fn read_all_bytes(f: file): array<byte>?` | Read all remaining content as bytes. |
| `fn write_string(f: file, s: string): bool` | Write a string to the file. |
| `fn write_bytes(f: file, data: array<byte>): bool` | Write raw bytes to the file. |
| `fn flush(f: file): bool` | Flush buffered writes to disk. |
| `fn seek(f: file, offset: int64): bool` | Seek to an absolute byte offset from the start. |
| `fn seek_end(f: file, offset: int64): bool` | Seek to an offset relative to the end. |
| `fn position(f: file): int64` | Return the current byte position. |
| `fn size(f: file): int64` | Return the total file size in bytes. |

```flow
import file
import io (println)

fn main(): none =
    let wf = file.open_write("/tmp/demo.txt")
    match wf
        | some(f) ->
            file.write_string(f, "Line one\nLine two\n")
            file.flush(f)
            file.close(f)
        | none -> println("cannot open for writing")

    let rf = file.open_read("/tmp/demo.txt")
    match rf
        | some(f) ->
            match file.read_line(f)
                | some(line) -> println(f"first line: {line}")
                | none -> println("empty")
            file.close(f)
        | none -> println("cannot open for reading")
```

---

## B.3 `path` --- Filesystem Paths

All functions operate on path strings; no special Path type is required.

| Signature | Description |
|-----------|-------------|
| `fn join(..segments: string): string` | Join any number of path segments with `/`. |
| `fn stem(p: string): string` | Filename without extension: `"main.flow"` -> `"main"`. |
| `fn parent(p: string): string` | Parent directory: `"foo/bar.txt"` -> `"foo"`. |
| `fn with_suffix(p: string, suffix: string): string` | Replace extension: `with_suffix("x.txt", ".md")` -> `"x.md"`. |
| `fn cwd(): string` | Current working directory. |
| `fn resolve(p: string): string` | Resolve to an absolute path. |
| `fn exists(p: string): bool` | True if the path exists on disk. |
| `fn is_dir(p: string): bool` | True if the path is a directory. |
| `fn is_file(p: string): bool` | True if the path is a regular file. |
| `fn:pure extension(p: string): string?` | File extension including the dot, or `none`. |
| `fn list_dir(p: string): array<string>?` | List directory entries, or `none` on failure. |

```flow
import path
import io (println)

fn main() {
    let dir = path.cwd()
    let full = path.join(dir, "src/main.flow")
    println(f"stem: {path.stem(full)}")  // "main"
    println(f"parent: {path.parent(full)}")  // ".../src"

    match path.extension("report.csv") {
        some(ext) -> println(f"ext: {ext}")  // ".csv"
        none -> println("no extension")
    }
}
```

---

## B.4 `string` --- String Manipulation

String functions operate on immutable UTF-8 strings and always return new values.

| Signature | Description |
|-----------|-------------|
| `fn len(s: string): int` | Byte length of the string (excludes null terminator). |
| `fn char_at(s: string, idx: int): char?` | Character at byte index, or `none` if out of bounds. |
| `fn substring(s: string, start: int, end_idx: int): string` | Substring from `start` (inclusive) to `end_idx` (exclusive). |
| `fn index_of(s: string, needle: string): int?` | Byte index of first occurrence, or `none`. |
| `fn contains(s: string, needle: string): bool` | True if `needle` appears anywhere in `s`. |
| `fn starts_with(s: string, prefix: string): bool` | True if `s` begins with `prefix`. |
| `fn ends_with(s: string, suffix: string): bool` | True if `s` ends with `suffix`. |
| `fn split(s: string, sep: string): array<string>` | Split on `sep`; returns all parts. |
| `fn trim(s: string): string` | Strip leading and trailing whitespace. |
| `fn trim_left(s: string): string` | Strip leading whitespace. |
| `fn trim_right(s: string): string` | Strip trailing whitespace. |
| `fn replace(s: string, old: string, new_str: string): string` | Replace all occurrences of `old` with `new_str`. |
| `fn join(sep: string, ..parts: string): string` | Join strings with `sep` between them. Variadic. |
| `fn to_lower(s: string): string` | Convert to lowercase. |
| `fn to_upper(s: string): string` | Convert to uppercase. |
| `fn:pure to_bytes(s: string): array<byte>` | Convert string to its UTF-8 byte representation. |
| `fn:pure from_bytes(data: array<byte>): string` | Construct a string from a UTF-8 byte array. |
| `fn repeat(s: string, n: int): string` | Repeat `s` exactly `n` times. |
| `fn url_encode(s: string): string` | Percent-encode for URLs. |
| `fn url_decode(s: string): string` | Decode a percent-encoded string. |

```flow
import string
import io (println)

fn main() {
    let s = "Hello, World!"
    println(f"length: {string.len(s)}")
    println(f"upper: {string.to_upper(s)}")
    println(f"contains 'World': {string.contains(s, "World")}")

    let parts = string.split("a,b,c", ",")
    println(f"joined: {string.join(" | ", ..parts)}")

    let border = string.repeat("=-", 20)
    println(border)
}
```

---

## B.5 `array` --- Array Operations

Arrays in Flow are immutable by default. Push operations return a new array.
The module provides type-specific variants for value types and generic
variants for pointer/heap types.

**Construction:**

| Signature | Description |
|-----------|-------------|
| `fn of<T>(..items:T):array<T>` | Create an array from variadic arguments. |

```flow
let nums = array.of(10, 20, 30)   // array<int> with 3 elements
let strs = array.of("a", "b")     // array<string> with 2 elements
```

**Type-specific getters:**

| Signature | Description |
|-----------|-------------|
| `fn get_int(arr: array<int>, idx: int): int?` | Safe get for `int` arrays. |
| `fn get_int64(arr: array<int64>, idx: int): int64?` | Safe get for `int64` arrays. |
| `fn get_float(arr: array<float>, idx: int): float?` | Safe get for `float` arrays. |
| `fn get_bool(arr: array<bool>, idx: int): bool?` | Safe get for `bool` arrays. |
| `fn get(arr: array<string>, idx: int): string?` | Safe get for `string` arrays. |
| `fn get_any<T>(arr: array<T>, idx: int): T?` | Generic safe get for any element type. |

**Length:**

| Signature | Description |
|-----------|-------------|
| `fn len(arr: array<int>): int` | Length of an `int` array. |
| `fn len_string(arr: array<string>): int` | Length of a `string` array. |
| `fn len_float(arr: array<float>): int` | Length of a `float` array. |
| `fn len_bool(arr: array<bool>): int` | Length of a `bool` array. |
| `fn len_byte(arr: array<byte>): int` | Length of a `byte` array. |
| `fn len64(arr: array<int>): int64` | 64-bit length. |
| `fn size<T>(arr: array<T>): int` | Generic length for any element type. |

**Push (returns a new array):**

| Signature | Description |
|-----------|-------------|
| `fn push<T>(arr: array<T>, val: T): array<T>` | Generic push for pointer/heap types. |
| `fn push_int(arr: array<int>, val: int): array<int>` | Push an `int`. |
| `fn push_int64(arr: array<int64>, val: int64): array<int64>` | Push an `int64`. |
| `fn push_float(arr: array<float>, val: float): array<float>` | Push a `float`. |
| `fn push_bool(arr: array<bool>, val: bool): array<bool>` | Push a `bool`. |
| `fn push_byte(arr: array<byte>, val: byte): array<byte>` | Push a `byte`. |

**Concatenation:**

| Signature | Description |
|-----------|-------------|
| `fn concat<T>(a: array<T>, b: array<T>): array<T>` | Generic concatenation. |
| `fn concat_int(a: array<int>, b: array<int>): array<int>` | Concatenate `int` arrays. |
| `fn concat_string(a: array<string>, b: array<string>): array<string>` | Concatenate `string` arrays. |
| `fn concat_byte(a: array<byte>, b: array<byte>): array<byte>` | Concatenate `byte` arrays. |

```flow
import array
import io (println)

fn main() {
    let nums = [10, 20, 30]
    match array.get_int(nums, 1) {
        some(v) -> println(f"nums[1] = {v}")  // 20
        none -> println("out of bounds")
    }

    // Build an array dynamically
    let names: array<string>:mut = []
    names = array.push(names, "Alice")
    names = array.push(names, "Bob")
    println(f"count: {array.size(names)}")  // 2

    // Concatenate
    let all = array.concat([1, 2], [3, 4])
    println(f"total: {array.len(all)}")  // 4
}
```

---

## B.6 `map` --- Hash Maps

Maps use string keys and generic values. The value type `V` is inferred from
usage. All mutating operations return a new map (persistent interface).

| Signature | Description |
|-----------|-------------|
| `fn new<V>(): map<string, V>` | Create an empty map. |
| `fn set<V>(m: map<string, V>, key: string, val: V): map<string, V>` | Insert or update a key-value pair. Returns the updated map. |
| `fn get<V>(m: map<string, V>, key: string): V?` | Look up a key. Returns `none` if absent. |
| `fn has<V>(m: map<string, V>, key: string): bool` | True if the key exists. |
| `fn remove<V>(m: map<string, V>, key: string): map<string, V>` | Remove a key. Returns the updated map. |
| `fn len<V>(m: map<string, V>): int64` | Number of entries. |
| `fn keys<V>(m: map<string, V>): array<string>` | All keys as an array. |
| `fn values<V>(m: map<string, V>): array<V>` | All values as an array. |

```flow
import map
import io (println)

fn main() {
    let m = map.new()
    let m = map.set(m, "host", "localhost")
    let m = map.set(m, "port", "8080")

    match map.get(m, "host") {
        some(v) -> println(f"host = {v}")
        none -> println("not found")
    }

    println(f"entries: {map.len(m)}")  // 2
    println(f"has port: {map.has(m, "port")}")  // true

    let ks = map.keys(m)
    for (k: string in ks) {
        let val = map.get(m, k) ?? "?"
        println(f"  {k} = {val}")
    }
}
```

---

## B.7 `sort` --- Sorting

Generic sorting with interface-based comparison or custom comparator functions.

| Signature | Description |
|-----------|-------------|
| `fn:pure sort<T fulfills Comparable>(arr: array<T>): array<T>` | Sort using the natural `Comparable` order. Returns a new sorted array. |
| `fn:pure sort_by<T>(arr: array<T>, cmp: fn(T, T): int): array<T>` | Sort with a custom comparator. Negative = less, zero = equal, positive = greater. |
| `fn:pure reverse<T>(arr: array<T>): array<T>` | Reverse the array. Returns a new array. |

```flow
import sort
import io (println)

fn main() {
    let nums = [5, 3, 1, 4, 2]
    let sorted = sort.sort(nums)
    for (n: int in sorted) { println(f"  {n}") }  // 1 2 3 4 5

    let desc = sort.reverse(sorted)
    for (n: int in desc) { println(f"  {n}") }  // 5 4 3 2 1

    let words = ["banana", "apple", "cherry"]
    let sorted_w = sort.sort(words)
    for (w: string in sorted_w) { println(w) }  // apple banana cherry
}
```

---

## B.8 `conv` --- Type Conversions

The `conv` module provides generic-to-string conversion via the `Showable`
interface, and type-specific string-to-value parsing. Parsing functions return
option types to handle invalid input safely.

| Signature | Description |
|-----------|-------------|
| `fn:pure to_string<T fulfills Showable>(val: T): string` | Convert any `Showable` value to its string representation. Works with `int`, `float`, `bool`, `string`, and user types implementing `Showable`. |
| `fn:pure string_to_int(s: string): int?` | Parse a string as `int`. Returns `none` on invalid input. |
| `fn:pure string_to_int64(s: string): int64?` | Parse a string as `int64`. Returns `none` on invalid input. |
| `fn:pure string_to_float(s: string): float?` | Parse a string as `float`. Returns `none` on invalid input. |

```flow
import conv
import io (println)

fn main() {
    println(conv.to_string(42))  // "42"
    println(conv.to_string(3.14))  // "3.14"
    println(conv.to_string(true))  // "true"

    match conv.string_to_int("123") {
        some(n) -> println(f"parsed: {n}")
        none -> println("invalid")
    }

    match conv.string_to_float("not a number") {
        some(f) -> println(f"got: {f}")
        none -> println("parse failed (expected)")
    }
}
```

---

## B.9 `math` --- Mathematics

The `math` module provides generic numeric functions via the `Comparable` and
`Numeric` interfaces, plus float-specific operations that map to the C math
library.

**Generic functions** (work with `int`, `float`, or any `Comparable`/`Numeric` type):

| Signature | Description |
|-----------|-------------|
| `fn:pure abs<T fulfills (Numeric, Comparable)>(n: T): T` | Absolute value. |
| `fn:pure min<T fulfills Comparable>(first: T, ..rest: T): T` | Smallest of one or more values. Variadic. |
| `fn:pure max<T fulfills Comparable>(first: T, ..rest: T): T` | Largest of one or more values. Variadic. |
| `fn:pure clamp<T fulfills Comparable>(val: T, lo: T, hi: T): T` | Clamp `val` to the range `[lo, hi]`. |

**Float-specific functions:**

| Signature | Description |
|-----------|-------------|
| `fn:pure floor(f: float): float` | Round toward negative infinity. |
| `fn:pure ceil(f: float): float` | Round toward positive infinity. |
| `fn:pure round(f: float): float` | Round to nearest integer (half rounds away from zero). |
| `fn:pure pow(base: float, exp: float): float` | Raise `base` to the power `exp`. |
| `fn:pure sqrt(f: float): float` | Square root. |
| `fn:pure log(f: float): float` | Natural logarithm (base e). |

```flow
import math
import io (println)

fn main() {
    println(f"abs(-42) = {math.abs(-42)}")
    println(f"min(3, 7) = {math.min(3, 7)}")
    println(f"clamp(15, 0, 10) = {math.clamp(15, 0, 10)}")

    println(f"sqrt(144.0) = {math.sqrt(144.0)}")
    println(f"pow(2.0, 10.0) = {math.pow(2.0, 10.0)}")
    println(f"floor(3.7) = {math.floor(3.7)}")
    println(f"ceil(3.2) = {math.ceil(3.2)}")
}
```

---

## B.10 `char` --- Character Utilities

Character classification and conversion functions. Flow's `char` type represents
a Unicode scalar value (32-bit).

| Signature | Description |
|-----------|-------------|
| `fn:pure is_digit(c: char): bool` | True if `c` is an ASCII digit (`0`--`9`). |
| `fn:pure is_alpha(c: char): bool` | True if `c` is an ASCII letter (`a`--`z`, `A`--`Z`). |
| `fn:pure is_alphanumeric(c: char): bool` | True if `c` is a digit or letter. |
| `fn:pure is_whitespace(c: char): bool` | True if `c` is whitespace (space, tab, newline, etc.). |
| `fn:pure to_code(c: char): int` | Unicode code point as an integer. |
| `fn:pure from_code(n: int): char` | Integer to character. |
| `fn:pure to_string(c: char): string` | Convert a single character to a one-character string. |

```flow
import char
import io (println)

fn main() {
    println(f"is_digit('5'): {char.is_digit('5')}")  // true
    println(f"is_alpha('z'): {char.is_alpha('z')}")  // true
    println(f"is_whitespace(' '): {char.is_whitespace(' ')}") ; true
    println(f"code of 'A': {char.to_code('A')}")  // 65
}
```

---

## B.11 `json` --- JSON Parsing and Generation

The `json` module works with an opaque `JsonValue` type. Values are constructed
with builder functions, inspected with typed accessors, and serialized back to
strings.

**Parsing and serialization:**

| Signature | Description |
|-----------|-------------|
| `fn parse(s: string): JsonValue?` | Parse a JSON string. Returns `none` on invalid JSON. |
| `fn:pure to_string(val: JsonValue): string` | Serialize to a compact JSON string. |
| `fn:pure to_string_pretty(val: JsonValue, indent: int): string` | Serialize with indentation for readability. |

**Accessors:**

| Signature | Description |
|-----------|-------------|
| `fn:pure get(val: JsonValue, key: string): JsonValue?` | Get a field from a JSON object by key. |
| `fn:pure get_index(val: JsonValue, idx: int64): JsonValue?` | Get an element from a JSON array by index. |
| `fn:pure as_string(val: JsonValue): string?` | Extract as string, or `none` if wrong type. |
| `fn:pure as_int(val: JsonValue): int64?` | Extract as integer, or `none` if wrong type. |
| `fn:pure as_float(val: JsonValue): float?` | Extract as float, or `none` if wrong type. |
| `fn:pure as_bool(val: JsonValue): bool?` | Extract as boolean, or `none` if wrong type. |
| `fn:pure as_array(val: JsonValue): array<JsonValue>?` | Extract as array of JSON values. |
| `fn:pure is_null(val: JsonValue): bool` | True if the value is JSON null. |
| `fn:pure type_tag(val: JsonValue): byte` | Numeric tag: 0=null, 1=bool, 2=int, 3=float, 4=string, 5=array, 6=object. |
| `fn:pure keys(val: JsonValue): array<string>?` | Keys of a JSON object, or `none` if not an object. |

**Builders:**

| Signature | Description |
|-----------|-------------|
| `fn:pure null_val(): JsonValue` | Create a JSON null. |
| `fn:pure string_val(s: string): JsonValue` | Create a JSON string. |
| `fn:pure int_val(n: int64): JsonValue` | Create a JSON integer. |
| `fn:pure float_val(f: float): JsonValue` | Create a JSON float. |
| `fn:pure bool_val(b: bool): JsonValue` | Create a JSON boolean. |
| `fn:pure array_val(items: array<JsonValue>): JsonValue` | Create a JSON array. |
| `fn:pure object_val(entries: map<string, JsonValue>): JsonValue` | Create a JSON object from a map. |

```flow
import json
import io (println)

fn main() {
    // Parse
    match json.parse("{\"name\":\"Flow\",\"version\":1}") {
        some(root) -> {
            println(json.to_string_pretty(root, 2))

            // Access fields
            match json.get(root, "name") {
                some(n) -> match json.as_string(n) {
                    some(s) -> println(f"name: {s}")
                    none -> println("not a string")
                }
                none -> println("no name field")
            }
        }
        none -> println("parse failed")
    }

    // Build
    let v = json.string_val("hello")
    println(json.to_string(v))  // "hello"
    println(f"is null: {json.is_null(json.null_val())}")  // true
}
```

---

## B.12 `net` --- Networking

TCP socket operations. All connection-creating functions return option types;
`none` indicates failure. The `Socket` type is opaque.

| Signature | Description |
|-----------|-------------|
| `fn listen(host: string, port: int): Socket?` | Bind and listen on a TCP address. Port 0 = OS-assigned. |
| `fn accept(sock: Socket): Socket?` | Accept an incoming connection (blocks). |
| `fn connect(host: string, port: int): Socket?` | Connect to a remote TCP address. |
| `fn read(sock: Socket, max_bytes: int): array<byte>?` | Read up to `max_bytes`. Returns `none` on error/EOF. |
| `fn write(sock: Socket, data: array<byte>): bool` | Write raw bytes. |
| `fn write_string(sock: Socket, s: string): bool` | Write a string. |
| `fn close(sock: Socket): none` | Close the socket. |
| `fn set_timeout(sock: Socket, ms: int): bool` | Set read/write timeout in milliseconds. |
| `fn remote_addr(sock: Socket): string?` | Remote peer address as a string. |
| `fn fd(sock: Socket): int` | Raw file descriptor (for low-level use). |
| `fn write_to_fd(fd: int, msg: string): bool` | Write a string directly to a file descriptor. |

```flow
import net
import io (println)

fn main() {
    // Listen on loopback
    match net.listen("127.0.0.1", 8080) {
        some(srv) -> {
            println("Listening on :8080")
            match net.accept(srv) {
                some(client) -> {
                    net.write_string(client, "Hello!\n")
                    net.close(client)
                }
                none -> println("accept failed")
            }
            net.close(srv)
        }
        none -> println("listen failed")
    }
}
```

---

## B.13 `time` --- Time and Dates

The `time` module provides wall-clock timestamps, sleep, and structured
date/time via the opaque `DateTime` type.

| Signature | Description |
|-----------|-------------|
| `fn now(): int64` | Current Unix timestamp in seconds. |
| `fn now_ms(): int64` | Current Unix timestamp in milliseconds. |
| `fn sleep_ms(ms: int): none` | Sleep for `ms` milliseconds. |
| `fn datetime_now(): DateTime` | Current local date/time. |
| `fn datetime_utc(): DateTime` | Current UTC date/time. |
| `fn format_iso8601(dt: DateTime): string` | Format as ISO 8601 (e.g., `"2025-01-15T14:30:00"`). |
| `fn format_rfc2822(dt: DateTime): string` | Format as RFC 2822 (email-style). |
| `fn format_http(dt: DateTime): string` | Format as HTTP date (RFC 7231). |
| `fn year(dt: DateTime): int` | Year component. |
| `fn month(dt: DateTime): int` | Month (1--12). |
| `fn day(dt: DateTime): int` | Day of month (1--31). |
| `fn hour(dt: DateTime): int` | Hour (0--23). |
| `fn minute(dt: DateTime): int` | Minute (0--59). |
| `fn second(dt: DateTime): int` | Second (0--59). |

```flow
import time
import io (println)
import conv (to_string)

fn main() {
    let ts = time.now()
    println(f"timestamp: {ts}")

    let dt = time.datetime_now()
    println(time.format_iso8601(dt))
    println(f"hour: {time.hour(dt)}")

    time.sleep_ms(100)
    let elapsed = time.now_ms() - (ts * 1000)
    println(f"elapsed: ~{to_string(elapsed)}ms")
}
```

---

## B.14 `sys` --- System Operations

| Signature | Description |
|-----------|-------------|
| `fn args(): array<string>` | Command-line arguments. `args()[0]` is the program name. |
| `fn exit(code: int): none` | Terminate with exit code. Does not return. |
| `fn env_get(name: string): string?` | Read an environment variable. Returns `none` if unset. |
| `fn clock_ms(): int64` | Monotonic clock in milliseconds (for timing, not wall time). |
| `fn run_process(command: string, args: array<string>): int` | Run a subprocess; returns its exit code. |
| `fn run_process_capture(command: string, args: array<string>): string?` | Run a subprocess and capture its stdout. |

```flow
import sys
import io (println)

fn main() {
    let argv = sys.args()
    println(f"program: {argv[0]}")

    match sys.env_get("HOME") {
        some(home) -> println(f"HOME = {home}")
        none -> println("HOME not set")
    }

    let start = sys.clock_ms()
    // ... work ...
    let elapsed = sys.clock_ms() - start
    println(f"took {elapsed}ms")
}
```

---

## B.15 `string_builder` --- Efficient String Building

`StringBuilder` accumulates text in a mutable buffer and produces a single
`string` when complete. Far more efficient than repeated concatenation in loops.

| Signature | Description |
|-----------|-------------|
| `fn new(): StringBuilder` | Create an empty builder. |
| `fn with_capacity(cap: int64): StringBuilder` | Create a builder pre-allocated for `cap` bytes. |
| `fn append(sb: StringBuilder, s: string): none` | Append a string. |
| `fn append_char(sb: StringBuilder, c: char): none` | Append a single character. |
| `fn append_int(sb: StringBuilder, v: int): none` | Append an integer's string representation. |
| `fn append_int64(sb: StringBuilder, v: int64): none` | Append an `int64`'s string representation. |
| `fn append_float(sb: StringBuilder, v: float): none` | Append a float's string representation. |
| `fn build(sb: StringBuilder): string` | Produce the final string. |
| `fn len(sb: StringBuilder): int64` | Current accumulated byte length. |
| `fn clear(sb: StringBuilder): none` | Reset the builder to empty. |

```flow
import string_builder as sb
import io (println)

fn main() {
    let b = sb.new()
    sb.append(b, "<ul>")
    let i: int:mut = 1
    while (i <= 3) {
        sb.append(b, "<li>Item ")
        sb.append_int(b, i)
        sb.append(b, "</li>")
        i = i + 1
    }
    sb.append(b, "</ul>")
    println(sb.build(b))
    // <ul><li>Item 1</li><li>Item 2</li><li>Item 3</li></ul>
}
```

---

## B.16 `bytes` --- Byte Array Utilities

Operations on `array<byte>` for binary data manipulation.

| Signature | Description |
|-----------|-------------|
| `fn:pure from_string(s: string): array<byte>` | Convert a string to its UTF-8 byte array. |
| `fn:pure to_string(data: array<byte>): string` | Interpret bytes as a UTF-8 string. |
| `fn:pure slice(data: array<byte>, start: int64, end_idx: int64): array<byte>` | Byte slice from `start` (inclusive) to `end_idx` (exclusive). |
| `fn:pure concat(a: array<byte>, b: array<byte>): array<byte>` | Concatenate two byte arrays. |
| `fn:pure len(data: array<byte>): int64` | Number of bytes. |

```flow
import bytes
import io (println)

fn main() {
    let data = bytes.from_string("Hello, World!")
    println(f"byte length: {bytes.len(data)}")

    let head = bytes.slice(data, 0, 5)
    println(f"first 5 bytes: {bytes.to_string(head)}")  // "Hello"

    let combined = bytes.concat(
        bytes.from_string("Hello"),
        bytes.from_string(" Flow")
    )
    println(bytes.to_string(combined))  // "Hello Flow"
}
```

---

## B.17 `random` --- Random Number Generation

Pseudo-random value generation. Not cryptographically secure.

| Signature | Description |
|-----------|-------------|
| `fn int_range(min: int, max: int): int` | Random integer in `[min, max]` inclusive. |
| `fn float_unit(): float` | Random float in `[0.0, 1.0)`. |
| `fn bool(): bool` | Random boolean (coin flip). |

```flow
import random
import io (println)

fn main() {
    let roll = random.int_range(1, 6)
    println(f"dice: {roll}")

    let pct = random.float_unit()
    println(f"random: {pct}")

    let coin = random.bool()
    println(f"heads: {coin}")
}
```

---

## B.18 `testing` --- Test Assertions

The `testing` module provides assertion functions for writing tests. Failed
assertions throw an internal test-failure exception.

| Signature | Description |
|-----------|-------------|
| `fn assert_true(val: bool, msg: string): void` | Assert that `val` is `true`. |
| `fn assert_false(val: bool, msg: string): void` | Assert that `val` is `false`. |
| `fn assert_eq<T fulfills (Equatable, Showable)>(expected: T, actual: T, msg: string): void` | Assert equality. On failure, prints expected vs. actual values. |
| `fn fail(msg: string): void` | Unconditionally fail with a message. |

```flow
import testing
import io (println)

fn main() {
    testing.assert_true(1 + 1 == 2, "basic arithmetic")
    testing.assert_eq(42, 42, "integers equal")
    testing.assert_eq("hello", "hello", "strings equal")
    testing.assert_false(1 == 2, "not equal")
    println("all tests passed")
}
```

---

## B.19 Stream Helpers

Stream helper methods are called as method-style postfix operations on any
`stream<T>`. They are part of the language core, not a separate import.

| Signature | Description |
|-----------|-------------|
| `.take(n: int): stream<T>` | Yield at most `n` elements, then stop. |
| `.skip(n: int): stream<T>` | Drop the first `n` elements, yield the rest. |
| `.map<U>(f: fn(T): U): stream<U>` | Transform each element with `f`. |
| `.filter(pred: fn(T): bool): stream<T>` | Yield only elements where `pred` returns true. |
| `.reduce<U>(init: U, f: fn(U, T): U): U` | Fold the stream to a single value. |
| `.zip<U>(other: stream<U>): stream<(T, U)>` | Pair elements from two streams. Stops when either ends. |
| `.chunks(n: int): stream<buffer<T>>` | Group elements into buffers of size `n`. |
| `.group_by<K>(f: fn(T): K): stream<(K, buffer<T>)>` | Group consecutive elements by key. |
| `.flatten<U>(): stream<U>` | Flatten a `stream<stream<U>>` or `stream<array<U>>`. |

```flow
import io (println)

fn range(n: int): stream<int> {
    let i: int:mut = 0
    while (i < n) {
        yield i
        i = i + 1
    }
}

fn main() {
    // Take and skip
    for (n: int in range(10).skip(3).take(4)) {
        println(f"  {n}")  // 3, 4, 5, 6
    }

    // Map and filter
    for (n: int in range(10).filter(\(x: int => x % 2 == 0)).map(\(x: int => x * 3))) {
        println(f"  {n}")  // 0, 6, 12, 18, 24
    }

    // Reduce
    let sum = range(5).reduce(0, \(acc: int, x: int => acc + x))
    println(f"sum: {sum}")  // 10
}
```

---

## B.20 Buffer Operations

A `buffer<T>` is a mutable, in-memory container for materializing stream data.
Used when an operation requires random access or the complete dataset (sorting,
grouping). Buffers are always mutable.

| Signature | Description |
|-----------|-------------|
| `buffer.new(): buffer<T>` | Create an empty buffer. |
| `buffer.collect(s: stream<T>): buffer<T>` | Consume a stream into a buffer. |
| `buffer.with_capacity(n: int): buffer<T>` | Create a buffer pre-allocated for `n` elements. |
| `buf.push(val: T)` | Append a value to the buffer. |
| `buf.drain(): stream<T>` | Convert buffer contents to a stream. Consumes the buffer. |
| `buf.len(): int` | Number of elements currently in the buffer. |
| `buf.get(i: int): T?` | Safe indexed access. Returns `none` if out of bounds. |
| `buf.sort_by(f: fn(T, T): int)` | Sort in place using a comparator. |
| `buf.reverse()` | Reverse in place. |
| `buf.slice(start: int, end: int): buffer<T>` | Create a new buffer from a sub-range. |

```flow
import io (println)

fn numbers(): stream<int> {
    yield 3
    yield 1
    yield 4
    yield 1
    yield 5
}

fn sort_stream(s: stream<int>): stream<int> {
    let buf: buffer<int>:mut = buffer.collect(s)
    buf.sort_by(\(a: int, b: int => a - b))
    return buf.drain()
}

fn main() {
    for (n: int in sort_stream(numbers())) {
        println(f"  {n}")  // 1, 1, 3, 4, 5
    }
}
```

---

## Cross-Reference: Module Summary

| Module | Import | Primary Use |
|--------|--------|-------------|
| `io` | `import io` | Console I/O, one-shot file ops |
| `file` | `import file` | Handle-based file I/O with seeking |
| `path` | `import path` | Filesystem path manipulation |
| `string` | `import string` | String searching, splitting, transformation |
| `array` | `import array` | Array access, push, concatenation |
| `map` | `import map` | String-keyed hash maps |
| `sort` | `import sort` | Generic sorting and reversal |
| `conv` | `import conv` | Type conversions (to/from string) |
| `math` | `import math` | Numeric functions (abs, min, sqrt, etc.) |
| `char` | `import char` | Character classification |
| `json` | `import json` | JSON parsing, access, and generation |
| `net` | `import net` | TCP networking |
| `time` | `import time` | Timestamps, dates, sleep |
| `sys` | `import sys` | CLI args, env vars, process execution |
| `string_builder` | `import string_builder` | Efficient string construction |
| `bytes` | `import bytes` | Binary data manipulation |
| `random` | `import random` | Pseudo-random generation |
| `testing` | `import testing` | Test assertions |
