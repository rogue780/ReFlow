# Flow Language Specification

Flow is a strongly-typed functional language with a composition-first design, linear ownership semantics, and first-class streaming. It is suitable for general-purpose programming and excels at data transformation workloads.

---

## Philosophy

- Every function can be built by composing smaller functions. Every function can be decomposed into smaller functions.
- All data is immutable by default. Mutation is explicit, visible, and confined.
- Immutable data is freely shareable across threads and coroutines with zero copying. Mutable data has exactly one owner at a time.
- Functions can only interact with their parameters, local variables, imported functions, and static type members. No global variables.
- Deterministic (`pure`) functions are verifiably safe to cache and parallelize.
- Every function returns exactly one value.
- Type boundaries are explicit. Structural compatibility is checked, not assumed.
- Errors are values. Exceptions are for exceptional conditions, not ordinary failure paths.

---

## Comments

Single-line comments use `//`. There is no block comment syntax. Multiline comments repeat `//` on each line.

```
// this is a single-line comment

//================================
// This is a multiline comment.
// Each line uses double-slash.
//================================
```

---

## Modules

Every `.flow` file belongs to a module declared at the top. The module name reflects the file's path relative to the project root. If the declaration is absent, the compiler issues a warning and treats the file as an anonymous module that cannot be imported.

```
module math.vector

export type Vec3 { x: float64, y: float64, z: float64 }
export fn dot(a: Vec3, b: Vec3): float64 = ...
export fn cross(a: Vec3, b: Vec3): Vec3 = ...
```

### Importing

```
import math.vector  // imports all exports into vector namespace
import math.vector (Vec3, dot)  // named imports into local scope
import math.vector as vec  // aliased namespace
```

The namespace for a bare import is the **last component** of the import path. `import math.vector` makes exports available as `vector.Vec3`, `vector.dot`, etc. Named imports (`import math.vector (Vec3, dot)`) bring names directly into scope. Aliased imports (`import math.vector as vec`) use the alias as the namespace: `vec.Vec3`.

Imports are resolved by relative path from the project root. The module name must match the file path. `math.vector` resolves to `math/vector.flow`.

### Circular Imports

Circular imports are a compile error. The compiler detects cycles and reports the full import chain.

### Shared Statics Across Modules

When two modules import the same module, that module is instantiated exactly once. All importers share the same static values. Mutable statics are type-namespaced shared state (`Config.host`). This is explicit, not global, but it is shared. Treat mutable statics with the same discipline as shared mutable state in any concurrent system.

```
// file: config.flow
module config

export type DB {
    static host: string:mut = "localhost",
    static port: int:mut = 5432
}
```

```
// file: server.flow
module server
import config (DB)

fn connect(): Connection {
    return db.open(DB.host, DB.port)  // reads shared static
}
```

```
// file: admin.flow
module admin
import config (DB)

fn override_host(h: string) {
    DB.host = h  // modifies shared static, server.flow sees this change
}
```

### Export

Only declarations marked `export` are visible to importers. Unmarked declarations are module-private.

```
export fn visible(): int = 42
fn private(): int = 99  // not importable
```

---

## Keywords

`module`, `import`, `export`, `as`, `alias`, `type`, `typeof`, `mut`, `imut`, `let`, `fn`, `return`, `yield`, `try`, `retry`, `catch`, `finally`, `interface`, `fulfills`, `constructor`, `self`, `for`, `in`, `while`, `if`, `else`, `match`, `none`, `break`, `continue`, `static`, `pure`, `record`, `some`, `ok`, `err`, `coerce`, `cast`, `throw`, `extern`, and all built-in type names.

---

## `typeof`

`typeof(expr)` is a compile-time operator that returns the static type of an expression as a type value. It does not evaluate `expr` at runtime. It is used for generic constraints, type assertions, and compile-time introspection.

```
let x: int = 42
let t = typeof(x)  // t is the type `int`

typeof(x) == typeof(42)  // true: both are int
typeof(x) == typeof("hi")  // false: int != string
```

`typeof` is most useful in generic functions to assert or constrain types:

```
fn ensure_same_type<T, U>(a: T, b: U) {
    if (typeof(a) != typeof(b)) {
        throw TypeMismatchError(f"expected {typeof(a)}, got {typeof(b)}")
    }
}
```

`typeof` never causes a runtime side effect. It is always resolved at compile time when types are statically known, and at runtime only when operating on interface-typed values whose concrete type is not statically determined.

---

## Operators

### Math

| Operator | Description |
|----------|-------------|
| `+` | Addition |
| `-` | Subtraction |
| `/` | Division |
| `*` | Multiplication |
| `**` | Exponentiation |
| `</` | Integer (floor) division |
| `%` | Modulo |

### Comparison

| Operator | Description |
|----------|-------------|
| `<` | Less than |
| `>` | Greater than |
| `<=` | Less than or equal |
| `>=` | Greater than or equal |
| `==` | Equality. Field-by-field value comparison. See [Equality and Congruence](#equality-and-congruence). |
| `===` | Congruence. Structural shape check. See [Equality and Congruence](#equality-and-congruence). |

### Logical

| Operator | Description |
|----------|-------------|
| `&&` | Logical AND |
| `\|\|` | Logical OR |
| `!` | Logical NOT |

### Assignment and Update

| Operator | Description |
|----------|-------------|
| `=` | Assignment |
| `+=` | Add and assign |
| `-=` | Subtract and assign |
| `*=` | Multiply and assign |
| `/=` | Divide and assign |
| `++` | Increment |
| `--` | Decrement |

All update operators are only valid on `:mut` bindings. Using them on an immutable binding is a compile error.

### Composition

| Operator | Description |
|----------|-------------|
| `->` | Left-to-right composition. Values and functions form a chain evaluated left to right. See [Composition](#composition). |
| `\|` | Fan-out. Groups functions that each independently receive the incoming value and push their results left to right. |
| `<:(\|)` | Parallel fan-out. Concurrent execution of fan-out branches. See [Parallel Fan-out](#parallel-fan-out). |

### Option and Result Operators

| Operator | Description |
|----------|-------------|
| `?` | Nullable type modifier. `int?` is sugar for `option<int>`. |
| `??` | Null coalescing. Returns the left side if non-none, otherwise the right side. |
| `?` (postfix) | Propagation. On `result<T, E>`, unwraps `ok(v)` or short-circuits with `err(e)`. On `option<T>`, unwraps `some(v)` or short-circuits with `none`. See [The `?` Propagation Operator](#the--propagation-operator). |

### Other

| Operator | Description |
|----------|-------------|
| `@` | Copy operator. Always a mutable deep copy, independent of source. Value types are trivial stack copies. See [Ownership](#ownership). |
| `&` | Ref operator. Cheap refcount increment. Immutable bindings only. See [Ownership](#ownership). |
| `:<` | Coroutine operator. `let b :< a()` spawns `a()` as a threaded producer. See [Coroutines](#coroutines). |
| `? :` | Ternary. `let a = b == c ? d : e` |

---

## Naming Conventions

| Element | Convention | Examples |
|---------|-----------|----------|
| Primitive types | lowercase single word | `int`, `int64`, `float`, `string`, `char`, `byte`, `bool` |
| Complex types (structs, sum types) | PascalCase | `Point`, `LogEntry`, `JsonValue`, `Socket` |
| Sum type variants (user-defined) | PascalCase | `Circle(r)`, `Rectangle(w, h)` |
| Built-in variants | lowercase | `some(v)`, `none`, `ok(v)`, `err(e)` |
| Functions | snake_case | `read_file`, `to_string`, `parse_command` |
| Variables / bindings | snake_case | `sender_addr`, `client_fds`, `port_str` |
| Modules | snake_case | `io`, `net`, `string_builder`, `json` |

---

## Built-in Types

| Type | Description |
|------|-------------|
| `bool` | Boolean (`true` or `false`). Value type. |
| `byte` | Unsigned 8-bit integer. Value type. |
| `int` | Signed 32-bit integer. Value type. |
| `int16` | Signed 16-bit integer. Value type. |
| `int32` | Signed 32-bit integer. Alias for `int`. Value type. |
| `int64` | Signed 64-bit integer. Value type. |
| `uint` | Unsigned 32-bit integer. Value type. |
| `uint16` | Unsigned 16-bit integer. Value type. |
| `uint32` | Unsigned 32-bit integer. Alias for `uint`. Value type. |
| `uint64` | Unsigned 64-bit integer. Value type. |
| `float` | 64-bit floating point. Value type. Alias for `float64`. |
| `float32` | 32-bit floating point. Value type. |
| `float64` | 64-bit floating point. Value type. |
| `char` | Unicode scalar value. Value type. |
| `string` | UTF-8 string. Heap-allocated, reference-counted when immutable. |
| `none` | The type whose only value is `none`. The absence case in `option<T>`. |
| `option<T>` | Sum type: `some(T)` or `none`. Represents a value that may be absent. Sugar: `T?` is `option<T>`. |
| `result<T, E>` | Sum type: `ok(T)` or `err(E)`. Represents an operation that may fail with a typed error. |
| `array<T>` | Ordered, fixed-size, immutable sequence. Integer-indexed. |
| `tuple<T...>` | Fixed-size ordered product of typed values. See [Tuples](#tuples). |
| `record` | Structural type with string keys and heterogeneous values. See [Records](#records). |
| `stream<T>` | Lazy, pull-based sequence. See [Streams](#streams). |
| `buffer<T>` | Mutable, in-memory container for materializing stream data. See [Buffers](#buffers). |
| `map<K, V>` | Key-value collection. Implements `collection<K, V>`. See [Collections](#collections). |
| `set<T>` | Unordered collection of unique values. See [Collections](#collections). |
| `ptr` | Opaque raw pointer (`void*`). FFI-only type. Cannot be dereferenced. See [FFI](#foreign-function-interface-ffi). |
| `channel<T>` | *(internal)* Bounded, thread-safe FIFO queue used by the coroutine runtime. Not a user-facing type. |

### Value Types

`bool`, `byte`, `int`, `int16`, `int32`, `int64`, `uint`, `uint16`, `uint32`, `uint64`, `float`, `float32`, `float64`, and `char` are value types. They are stack-allocated and implicitly copied on assignment, function call, and yield. Ownership semantics do not apply to value types.

```
let count: int:mut = 0
count++
yield count  // implicitly copied, count still accessible
yield count  // fine
```

### Array Literals

Arrays are constructed with bracket syntax. The element type is inferred from the contents or may be annotated explicitly.

```
let nums: array<int> = [1, 2, 3, 4, 5]
let names: array<string> = ["alice", "bob", "carol"]
let empty: array<int> = []
let mixed_inference = [10, 20, 30]  // inferred as array<int>
```

All elements must be of the same type. A heterogeneous literal is a compile error:

```
let bad = [1, "two", 3]  // compile error: int and string are not the same type
```

Arrays are immutable by default. The `:mut` modifier on the binding allows reassigning the variable to a different array, not modifying individual elements. Arrays have no in-place mutation; transformations produce new arrays.

```
let a: array<int> = [1, 2, 3]
let b: array<int> = a.push(4)  // new array [1, 2, 3, 4]; a is unchanged

let c: array<int>:mut = [1, 2, 3]
c = [4, 5, 6]  // ok: rebinding c to a new array
c.get(0)  // some(4)
```

Nested arrays:

```
let matrix: array<array<int>> = [[1, 2], [3, 4], [5, 6]]
```

#### Array Stdlib API

The `array` module provides generic and type-specific functions. The generic `push<T>` and `get_any<T>` functions work for all element types, including pointer/heap types, value types, and user-defined sum types. The compiler automatically handles the necessary boxing and dereferencing for non-pointer element types. Type-specific variants are also available for common value types.

```
// Construction from variadic args (pure Flow, monomorphized)
array.of<T>(..items:T): array<T>

// Generic (works for all element types including sum types)
array.push<T>(arr: array<T>, val: T): array<T>
array.get_any<T>(arr: array<T>, idx: int): T?
array.size<T>(arr: array<T>): int
array.concat<T>(a: array<T>, b: array<T>): array<T>

// Value-type push variants (also work via generic push<T>)
array.push_int(arr: array<int>, val: int): array<int>
array.push_float(arr: array<float>, val: float): array<float>
array.push_bool(arr: array<bool>, val: bool): array<bool>
array.push_byte(arr: array<byte>, val: byte): array<byte>
array.push_int64(arr: array<int64>, val: int64): array<int64>

// Type-specific getters
array.get_int(arr: array<int>, idx: int): int?
array.get_float(arr: array<float>, idx: int): float?
array.get_bool(arr: array<bool>, idx: int): bool?
array.get(arr: array<string>, idx: int): string?

// Type-specific lengths
array.len(arr: array<int>): int
array.len_string(arr: array<string>): int
array.len_float(arr: array<float>): int
```

---

## Numeric Sizing and Overflow

### Integer Widths

`int` is 32-bit signed by default. Sized variants are available for all widths:

```
let a: int = 100  // 32-bit signed
let b: int64 = 1_000_000_000_000
let c: uint = 42  // 32-bit unsigned
let d: uint64 = 18_446_744_073_709_551_615
```

Underscores are allowed in numeric literals for readability: `1_000_000`.

### Float Widths

`float` is 64-bit (IEEE 754 double precision) by default. `float32` is available for memory-constrained contexts.

### Overflow and Underflow

Integer overflow and underflow throw `OverflowError` at runtime. There is no silent wraparound.

```
let max: int = 2_147_483_647
let n = max + 1  // throws OverflowError
```

### Division by Zero

Integer division by zero throws `DivisionByZeroError`.

Float division by zero follows IEEE 754: dividing a non-zero float by zero produces `float.infinity` or `float.neg_infinity`. Dividing zero by zero produces `float.nan`.

```
let a: float = 1.0 / 0.0  // float.infinity
let b: float = -1.0 / 0.0  // float.neg_infinity
let c: float = 0.0 / 0.0  // float.nan
```

### Float Modulo

The `%` operator works on both integer and float operands. For integers, it computes the remainder after integer division. For floats, it computes the IEEE 754 remainder using C's `fmod()` function.

Float modulo by zero throws `DivisionByZeroError` (unlike float division, which follows IEEE 754).

```
let a: float = 10.5 % 3.0  // 1.5
let b: float = -7.5 % 2.0  // -1.5
let c: float = 1.0 % 0.0  // throws DivisionByZeroError
```

### Numeric Conversion

Conversions between numeric types are always explicit using `cast<T>`. Widening casts always succeed. Narrowing casts throw `OverflowError` if the value does not fit in the target type.

```
let a: int = 100
let b: int64 = cast<int64>(a)  // widening, always succeeds
let c: float64 = cast<float64>(a) // int to float, always succeeds
let d: int32 = cast<int32>(b)  // narrowing, throws if out of range
let e: int = cast<int>(3.9)  // truncates toward zero: e == 3
```

### Implicit Integer Widening

Integer types of the same signedness widen implicitly when the target is strictly wider. This applies to arithmetic operations, function arguments, and variable assignments:

```
let a: int = 100
let b: int64 = 200
let c: int64 = a + b  // a is implicitly widened to int64
let d: int64 = a  // implicit widening in assignment

fn accept_large(n: int64): none { }
accept_large(a)  // int implicitly widens to int64
```

Mixed signedness (e.g., `int + uint`) remains a compile error. Narrowing (e.g., `int64` to `int`) still requires explicit `cast<T>`. Float-to-int and int-to-float conversions remain explicit.

---

## Null, None, and Option

`option<T>` is a sum type with two variants: `some(T)` and `none`. It represents a value that may be absent.

`int?` is syntactic sugar for `option<int>`. A bare `int` can never be `none`.

The value `none` is both the type name and the literal value representing absence.

```
let x: int? = some(5)  // explicitly some
let y: int? = 5  // int is automatically lifted to some(5)
let z: int? = none  // explicit absence
```

### Auto-lifting Rules

When a non-optional value is assigned or passed where an `option<T>` is expected, it is automatically wrapped in `some()`. This lifting is applied only when the target type is statically known to be `option<T>` and the source type is `T` (not itself an `option<T>`).

```
let a: int? = 5  // lifted: some(5)
let b: int? = some(5)  // explicit: same result
let c: int? = none  // explicit none, no lifting

fn maybe_score(): int? { return 95 }  // return value lifted to some(95)

fn process(x: int?): string = ...
process(42)  // argument lifted to some(42)
process(none)  // explicit none, no lifting
process(some(42))  // explicit some, no double-wrapping
```

Auto-lifting does **not** apply when:

- The source is already `option<T>`. `option<option<T>>` is never produced by accident.
- The target type is a bare type variable `T` in a generic context where `T` could be any type. In generics, passing a non-optional value to `option<T>` requires explicit `some()`.
- The assignment is within a `match` arm that binds via `some(v)`: the bound `v` is already the inner value.

```
// Generic context: explicit wrapping required
fn wrap<T>(val: T): option<T> = some(val)  // must be explicit

// Non-generic: auto-lift works
let n: int? = compute_score()  // lifted if compute_score returns int
```

### The `??` Operator

`??` unwraps an `option<T>` value or provides a default. If the left side is `some(v)`, `v` is returned. If the left side is `none`, the right side is evaluated and returned.

```
let name: string = user.middle_name ?? "N/A"
let port: int = config_port() ?? 5432
```

The right side is only evaluated if the left side is `none` (short-circuit semantics).

### Pattern Matching with `option<T>`

```
let value = match lookup(key) {
    some(v) : v,
    none    : default_value()
}
```

### `if let` — Conditional Pattern Matching

`if let` is sugar for a `match` with two arms: one for the matching pattern, and a complement for the else branch. It avoids the boilerplate of exhaustive match when only one variant is interesting.

```
// Unwrap some — skip on none
if (let some(v) = find_user(id)) {
    println(f"found: {v}")
}

// Unwrap some with else
if (let some(v) = find_user(id)) {
    greet(v)
} else {
    println("user not found")
}

// Unwrap ok — else handles the error case
if (let ok(data) = read_file(path)) {
    process(data)
} else {
    println("read failed")
}

// Unwrap err
if (let err(e) = validate(input)) {
    log_error(e)
}
```

The parser desugars `if (let ...)` into a `match` statement:
- `if (let some(x) = expr) { body }` becomes `match expr { some(x): { body }, none: {} }`
- `if (let ok(x) = expr) { body } else { alt }` becomes `match expr { ok(x): { body }, err(_): { alt } }`
- `if (let err(e) = expr) { body }` becomes `match expr { err(e): { body }, ok(_): {} }`

No changes to the resolver, type checker, lowering, or emitter are needed — the desugared `match` flows through the existing pipeline.

### Nullable with Mutability

```
let x: int?:mut = 5  // nullable, mutable
let y: int:mut = 5  // mutable, never none
let z: int? = none  // nullable, immutable
```

---

## Result Type

`result<T, E>` is a sum type with two variants: `ok(T)` for success and `err(E)` for failure. It is the standard mechanism for operations that may fail in recoverable, expected ways.

```
type result<T, E> =
    | ok(T)
    | err(E)
```

### Constructing Results

```
fn parse_int(s: string): result<int, string> {
    if (s.is_empty()) {
        return err("empty string")
    }
    // ... parse logic ...
    return ok(parsed_value)
}
```

### Pattern Matching on Results

```
match parse_int("42") {
    ok(n)    : process(n),
    err(msg) : log(msg)
}
```

### The `?` Propagation Operator

The postfix `?` operator unwraps a `result` or `option` value, short-circuiting with early return if the value is an error or none.

**On `result<T, E>`:** Within a function that returns `result<T, E>`, appending `?` to a `result<T, E>` expression unwraps `ok(v)` to `v` or returns `err(e)` immediately.

```
fn load_and_process(path: string): result<record, string> {
    let raw = read_file(path)?  // if err, return err immediately
    let parsed = parse(raw)?  // same
    let validated = validate(parsed)?
    return ok(validated)
}
```

The `E` type in the propagated `err` must be compatible with the enclosing function's `E`. If they differ, a `cast` or explicit mapping is required.

**On `option<T>`:** Within a function that returns `option<T>` (or `T?`), appending `?` to an `option<T>` expression unwraps `some(v)` to `v` or returns `none` immediately.

```
fn double_positive(x: int): int? {
    let v = find_positive(x)?  // if none, return none immediately
    return some(v * 2)
}
```

Using `?` on an option in a function that does not return an option type is a compile error.

### Result vs Exceptions

Use `result<T, E>` for expected, recoverable failures: parsing, validation, IO that commonly fails. Use exceptions (`try/retry/catch`) for unexpected failures, retries with corrective logic, and pipeline-level error recovery. The two mechanisms are complementary.

---

## Sum Types

Sum types (also called algebraic data types or tagged unions) define a type that is exactly one of several named variants. Each variant may carry data.

### Defining Sum Types

```
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)
    | Triangle(base: float, height: float)

type Direction = | North | South | East | West

type Tree<T> =
    | Leaf
    | Node(value: T, left: Tree<T>, right: Tree<T>)
```

Variants without data (like `North`, `Leaf`) carry no payload. Variants with data carry named or positional fields.

### Pattern Matching on Sum Types

Matching on a sum type must be exhaustive. If any variant is unhandled, it is a compile error. Use `_` to explicitly opt out of exhaustiveness for the remaining variants.

```
fn area(s: Shape): float = match s {
    Circle(r)       : 3.14159 * r * r,
    Rectangle(w, h) : w * h,
    Triangle(b, h)  : 0.5 * b * h
}

fn move(d: Direction): string = match d {
    North : "moving north",
    South : "moving south",
    _     : "moving east or west"
}
```

Omitting a variant without `_` is a compile error:

```
fn bad(s: Shape): float = match s {
    Circle(r) : r * r
    // compile error: Rectangle and Triangle not handled
}
```

### Generic Sum Types

```
type tree<T> =
    | Leaf
    | Node(value: T, left: tree<T>, right: tree<T>)

fn depth<T>(t: tree<T>): int = match t {
    Leaf           : 0,
    Node(_, l, r)  : 1 + max(depth(l), depth(r))
}
```

### Sum Types in Interfaces

Interfaces can define functions that return or accept sum types:

```
interface Parseable<T, E> {
    fn parse(raw: string): result<T, E>
}
```

---

## Enums

Enums define named integer constants grouped under a type name. Enums are always `int`-backed.

### Defining Enums

```
enum Color {
    Red = 0
    Green = 1
    Blue = 2
}
```

Variants are newline-separated. Each variant may have an explicit integer value via `= value`, or the value is auto-incremented from the previous variant (starting at 0).

```
enum Direction {
    North       // 0
    South       // 1
    East        // 2
    West        // 3
}

enum Offset {
    A = 10      // 10
    B           // 11
    C           // 12
    D = 20      // 20
    E           // 21
}
```

Negative values are supported: `A = -1`.

### Accessing Enum Values

Enum variants are accessed as static members:

```
let c:int = Color.Red       // 0
let d:int = Direction.West  // 3
```

### Subtyping

Enum values are implicitly assignable to `int`. No cast is required:

```
fn process(code:int):string { ... }
process(Color.Red)          // ok — Color is a subtype of int
```

Two enum values of the same enum type are comparable with `==`:

```
if(c == Color.Red) { ... }
```

### Exporting Enums

```
export enum Color {
    Red = 0
    Green = 1
    Blue = 2
}
```

Exported enums are available to importing modules.

### Constraints

- Enum must have at least one variant.
- Duplicate values within the same enum are a compile-time error.
- Enums cannot have methods, fields, or constructors.

---

## Tuples

Tuples are fixed-size ordered products of typed values. They are structural (no name required) and immutable.

```
let pair: (int, string) = (42, "hello")
let triple: (float, float, float) = (1.0, 2.0, 3.0)
```

### Access

Tuple fields are accessed by zero-based index:

```
let n: int = pair.0  // 42
let s: string = pair.1  // "hello"
```

### Destructuring

```
let (x, y) = pair
let (a, b, c) = triple
```

Tuples may be used anywhere a type is expected, including as function parameters and return types:

```
fn min_max(items: array<int>): (int, int) {
    // ... compute ...
    return (min_val, max_val)
}

let (lo, hi) = min_max(data)
```

### Tuples vs Records vs Types

Tuples are for short-lived, anonymous groupings of values, especially function returns. Records are for dynamic, schema-flexible containers with named fields. Named types are for domain objects with methods and validation. Prefer named types as data crosses module boundaries.

---

## Equality and Congruence

### `==` (Equality)

Field-by-field value comparison. Works on values of the same type or congruent types. If types are not congruent, it is a compile error.

```
type LogEntry { timestamp: int, source: string }
type EventRecord { source: string, timestamp: int }

let a = LogEntry { timestamp: 100, source: "us-east-1" }
let b = EventRecord { source: "us-east-1", timestamp: 100 }

a == b  // true: all field values match
```

For primitives and strings, `==` is standard value equality.

### `===` (Congruence)

A compile-time or runtime check that two values have the same field names and field types. Values and methods do not matter. Field order does not matter.

```
type LogEntry { timestamp: int, source: string }
type EventRecord { source: string, timestamp: int }
type MetricPoint { timestamp: int, value: float }

let a: LogEntry = ...
let b: EventRecord = ...
let c: MetricPoint = ...

a === b  // true: same field names and types
a === c  // false: MetricPoint has 'value', not 'source'
```

Congruence is most useful as a guard before structural assignment via `coerce`.

### `coerce` (Structural Assignment)

To assign values across congruent types, use the built-in `coerce` function. `coerce` performs a field-by-field copy from the source to a new value of the target type. It is a compile error to call `coerce` on non-congruent types.

```
type SomeData      { x: int, y: int }
type TransformedData { x: int, y: int }
type Transformer   { x: int, y: int, fn do_transform(self) { self.x += 3; self.y += 2 } }

let sd: SomeData = { x: 5, y: 2 }

let tf: Transformer = coerce(sd)  // copies x and y, method 'do_transform' is from the type
tf.do_transform()

let tfd: TransformedData = coerce(tf)
// tfd is { x: 8, y: 4 }
```

`coerce` does not invoke constructors. It copies field values by name. If the target type has a constructor, use it explicitly if validation is required.

---

## Mutability Modifiers

| Modifier | Meaning |
|----------|---------|
| `:mut` | Binding is mutable. Can be modified by the owning scope. |
| `:imut` | Binding is explicitly immutable. Cannot be modified. |
| *(bare)* | No modifier. Immutable when declaring variables. Accepts either mutability in function parameters. |

### Modifier Grammar

Type modifiers follow a fixed order: type, then `?`, then `:mut`/`:imut`. No duplicates. Order is not commutative.

```
int  // immutable int
int?  // immutable nullable int
int:mut  // mutable int
int?:mut  // mutable nullable int
```

`int:mut?` is a compile error. `?` must precede `:mut`.

### Variables

```
let x: int = 5  // immutable
let y: int:imut = 5  // explicitly immutable, same as above
let z: int:mut = 5  // mutable
```

### Function Parameters

`:imut` means "this function will not mutate this parameter." It accepts both mutable and immutable bindings from the caller. The function simply cannot mutate it.

`:mut` means "this function will mutate this parameter and the caller will see the changes." The caller must pass a mutable binding.

Bare (no modifier) accepts either mutability with no guarantee either way.

```
fn read_only(data: array<int>:imut): int {
    // accepts both :mut and bare/imut bindings
    // cannot mutate data
}

fn will_modify(data: array<int>:mut): int {
    // caller must pass a :mut binding
    // mutations are visible to the caller
}

fn flexible(data: array<int>): int {
    // accepts any mutability
}
```

### Passing `:imut` to a `:mut` Parameter

Passing an `:imut` binding to a `:mut` parameter is a compile error. The function requires mutation visibility that the `:imut` binding cannot provide. Use `@` to pass an explicit mutable deep copy:

```
fn increment(x: int:mut) { x++ }

let a: int = 5  // immutable
increment(a)  // compile error: imut binding cannot fulfill :mut contract
increment(@a)  // ok: @a is a mutable deep copy, original a is unchanged
increment(&a)  // compile error: & does not satisfy :mut
```

---

## Records

A `record` is a built-in structural type with string keys and heterogeneous values. Records are immutable by default.

```
let row: record = { name: "Alice", age: 30, active: true }
let name: string = row.name
let age: int = row.age
```

Records are structurally typed. Two records with the same field names and types are congruent. Records support `==` and `===` with the same semantics as named types.

Records are appropriate for intermediate pipeline data, parsed rows, and dynamic schemas. For domain objects with validation and methods, use named types.

---

## Type Aliases

Aliases create distinct named types wrapping an underlying type. An alias is not interchangeable with its underlying type without explicit conversion.

```
alias Timestamp: int
alias UserID: string
alias Transform<T, U>: fn(stream<T>): stream<U>
```

```
fn process(ts: Timestamp, id: UserID) { ... }

let t: Timestamp = Timestamp.from(12345)
let i: UserID = UserID.from("abc")
process(t, i)  // fine
process(i, t)  // compile error: UserID is not Timestamp
process(12345, i)  // compile error: int is not Timestamp
```

Conversion uses `.from()` to construct and `.value()` to unwrap:

```
let t: Timestamp = Timestamp.from(12345)
let raw: int = t.value()
```

---

## Types

Types are structs with fields and methods. There is no inheritance. Types can fulfill interfaces to satisfy contracts.

### Basic Type Definition

```
type LogEntry {
    timestamp: int,
    source: string,
    level: string,
    message: string,

    fn severity_score(self): int {
        if (self.level == "ERROR") { return 8 }
        if (self.level == "WARN")  { return 5 }
        return 1
    }

    fn is_critical(self): bool = self.severity_score() >= 8
}
```

### `self`

Methods take explicit `self` as their first parameter. Nothing is implicitly injected. Methods are syntactic sugar for functions whose first parameter is the owning type; they participate in composition chains:

```
let entry: LogEntry = ...
entry -> severity_score  // composition chain
entry.severity_score()  // method call syntax — identical
```

### Per-Field Mutability

Fields are immutable by default. Individual fields may be declared `:mut`:

```
type Record {
    id: int,
    raw: string,
    status: string:mut,
    score: int:mut,

    fn update_score(self, s: int) {
        self.score = s  // fine: score is :mut
    }

    fn set_id(self, i: int) {
        self.id = i  // compile error: id is not :mut
    }
}
```

### Static Members

Static members belong to the type, not to instances. They are accessed via the type name and provide namespaced shared state.

```
type Config {
    static host: string:mut = "localhost",
    static port: int:mut = 5432,
    static max_retries: int = 3,

    fn:static connection_string(): string {
        return f"postgres://{Config.host}:{Config.port}"
    }
}
```

Functions that read or write mutable statics are not parallelizable and may not appear inside `<:(a | b)`. Mutable statics must be read through `@` (deep copy) for thread safety.

### Constructors

Types may define one or more named constructors. When any constructor is defined, literal construction is disabled: all instance creation must go through a constructor. This enforces validation.

```
type LogEntry {
    timestamp: int,
    source: string,
    level: string,

    constructor from_raw(ts: int, src: string, lvl: string): LogEntry {
        if (lvl != "DEBUG" && lvl != "INFO" && lvl != "WARN" && lvl != "ERROR") {
            throw InvalidLevelError(lvl)
        }
        return LogEntry { timestamp: ts, source: src, level: lvl }
    }

    constructor from_string(raw: string): LogEntry {
        let parts = raw.split("|")
        return LogEntry.from_raw(
            cast<int>(parts.get(0) ?? "0"),
            parts.get(1) ?? "",
            parts.get(2) ?? "INFO"
        )
    }
}

let a = LogEntry.from_raw(12345, "us-east-1", "ERROR")
let b = LogEntry.from_string("12345|us-east-1|ERROR")
```

If no constructor is defined, literal construction is available:

```
let entry = LogEntry { timestamp: 12345, source: "us-east-1", level: "ERROR" }
```

### Struct Spread (`..`)

When constructing a type literal, the `..source` syntax copies all fields from `source` into the new value, except those explicitly overridden. This is called a struct spread. It is a convenience for creating a modified copy of an existing value without restating every field.

```
type Point { x: float, y: float, z: float }

let p = Point { x: 1.0, y: 2.0, z: 3.0 }
let q = Point { x: 9.9, ..p }  // q is { x: 9.9, y: 2.0, z: 3.0 }
```

The spread `..source` must come last in the field list. Explicitly named fields take precedence over spread fields. Any field that appears both explicitly and in the spread uses the explicit value.

```
let r = Point { z: 0.0, ..p }  // r is { x: 1.0, y: 2.0, z: 0.0 }
```

The source and target must be the same type or structurally congruent (for use with `coerce`). Spreading between non-congruent types is a compile error.

Struct spread does not invoke constructors. If the target type has a constructor and validation is required, construct through the constructor explicitly.

```
// Spread bypasses constructors — use for trusted internal copies only
let copy = LogEntry { level: "WARN", ..original }  // no constructor validation

// Use constructor if validation matters
let safe = LogEntry.from_raw(original.timestamp, original.source, "WARN")
```

### Generic Types

```
type Pair<A, B> {
    first: A,
    second: B,

    fn map_first<C>(self, f: fn(A): C): Pair<C, B> {
        return Pair<C, B> { first: f(self.first), second: self.second }
    }
}
```

Type parameters may carry interface bounds using `fulfills`. The bound
restricts which concrete types may be substituted for the parameter:

```
type SortedList<T fulfills Comparable> {
    items: array<T>,

    fn insert(self, val: T): SortedList<T> {
        // T is guaranteed to have compare()
        ...
    }
}

let valid: SortedList<int> = ...  // ok: int fulfills Comparable
let invalid: SortedList<MyPlainType> = ...  // compile error: MyPlainType does not fulfill Comparable
```

Multiple bounds on a single parameter require parentheses:

```
type IndexedCache<K fulfills (Hashable, Comparable), V> {
    data: map<K, V>,
    ...
}
```

### Fulfilling Interfaces

```
type LogEntry fulfills Serializable {
    timestamp: int,
    source: string,

    fn serialize(self): string {
        return f"{self.timestamp}|{self.source}"
    }

    fn byte_size(self): int {
        return self.serialize().len()
    }
}
```

---

## Interfaces

Interfaces define contracts: sets of function signatures and optional constructor constraints. Interfaces contain no fields, no default implementations, and no data.

### Basic Interface

```
interface Serializable {
    fn serialize(self): string
    fn byte_size(self): int
}
```

### Constructor Constraints

```
interface Parseable<T> {
    constructor from_string(raw: string): self
    fn validate(self): bool
}
```

The `self` return type means "returns an instance of whatever type fulfills this interface."

### Pure in Interfaces

```
interface Transform<T, U> {
    fn:pure apply(self, input: T): U
}
```

Any type fulfilling `Transform` must provide a deterministic `apply`.

### Generic Interfaces

```
interface Mappable<T> {
    fn map<U>(self, f: fn(T): U): Mappable<U>
}
```

### Bounded Type Parameters on Interfaces

Interface type parameters may also carry bounds:

```
interface SortedContainer<T fulfills Comparable> {
    fn insert(self, val: T): self
    fn min(self): option<T>
    fn max(self): option<T>
}
```

Any type fulfilling `SortedContainer` must supply a concrete type for `T`
that itself fulfills `Comparable`.

### Core Built-in Interfaces

These four interfaces exist without any `interface` declaration in user code.
They are registered by the compiler and fulfilled by built-in types via
compiler-synthesized method implementations (not source-level `fulfills`
declarations).

```
// Ordering comparison.
// Returns negative if self < other, zero if equal, positive if self > other.
interface Comparable {
    fn:pure compare(self, other: self): int
}

// Arithmetic operations on numeric types.
interface Numeric {
    fn:pure negate(self): self
    fn:pure add(self, other: self): self
    fn:pure sub(self, other: self): self
    fn:pure mul(self, other: self): self
}

// Value equality.
interface Equatable {
    fn:pure equals(self, other: self): bool
}

// Human-readable string conversion.
interface Showable {
    fn:pure to_string(self): string
}
```

The `self` type annotation in non-receiver parameters (e.g.,
`compare(self, other: self)`) means "the implementing type." When
`int fulfills Comparable`, the method signature becomes
`compare(self: int, other: int): int`.

`Numeric` intentionally omits a `zero()` static factory. Functions that
need a zero value (such as `sum`) accept it as an explicit parameter.

### Built-in Fulfillments

| Type | Comparable | Numeric | Equatable | Showable |
|------|:---:|:---:|:---:|:---:|
| `int` | yes | yes | yes | yes |
| `int64` | yes | yes | yes | yes |
| `float` | yes | yes | yes | yes |
| `string` | yes (lexicographic) | — | yes | yes (identity) |
| `bool` | — | — | yes | yes |
| `char` | yes (Unicode scalar) | — | yes | yes |
| `byte` | yes | — | yes | yes |

Operator mappings for the compiler's synthetic implementations:

- `compare(other)` → `(self < other) ? -1 : (self > other) ? 1 : 0`
- `negate()` → `-self`
- `add(other)` → `self + other` (checked for integer types)
- `sub(other)` → `self - other` (checked for integer types)
- `mul(other)` → `self * other` (checked for integer types)
- `equals(other)` → `self == other`
- `to_string()` → calls the corresponding runtime conversion function
- `string.to_string()` → returns `self` (identity, retains)

### The `collection` Interface

`collection<K, V>` is a built-in interface. Standard collection types (`map<K, V>`, `array<T>`, `buffer<T>`) implement it. Custom types may also fulfill it.

```
interface collection<K, V> {
    fn get(self, key: K): option<V>
    fn set(self, key: K, val: V): self
    fn keys(self): stream<K>
    fn values(self): stream<V>
    fn has(self, key: K): bool
    fn len(self): int
}
```

`get` returns `option<V>`. An absent key returns `none`, not an exception.

---

## Collections

### `map<K, V>`

A hash map implementing `collection<K, V>`. Keys must be hashable (all primitives, strings, and types that fulfill `Hashable`).

```
let scores: map<string, int> = map.new()
let scores2 = scores.set("alice", 95).set("bob", 87)

let alice_score: option<int> = scores2.get("alice")  // some(95)
let carol_score: option<int> = scores2.get("carol")  // none

let with_default: int = scores2.get("carol") ?? 0  // 0
```

Maps are immutable by default. `.set()` returns a new map. For a mutable map:

```
let scores: map<string, int>:mut = map.new()
scores.insert("alice", 95)  // mutates in place
scores.remove("bob")
```

#### Map API

The stdlib `map` module provides generic functions where the value type `V` is inferred from the binding context. `V` can be any type, including value types like `int` and `float` — the compiler automatically handles boxing/unboxing when storing value types in the map's `void*`-based storage. Keys are currently `string` in the stdlib implementation.

```
map.new<V>(): map<string, V>
map.from_pairs(pairs: array<(K, V)>): map<K, V>

map.get<V>(m: map<string, V>, key: string): V?
map.set<V>(m: map<string, V>, key: string, val: V): map<string, V>
m.insert(key: K, val: V)  // :mut only: mutates in place
map.remove<V>(m: map<string, V>, key: string): map<string, V>
map.has<V>(m: map<string, V>, key: string): bool
map.keys<V>(m: map<string, V>): array<string>
map.values<V>(m: map<string, V>): array<V>
m.entries(): stream<(K, V)>
map.len<V>(m: map<string, V>): int64
m.merge(other: map<K, V>): map<K, V>  // right-biased on key collision
```

### `set<T>`

An unordered collection of unique values. Elements must be hashable.

```
let tags: set<string> = set.from(["alpha", "beta", "gamma"])
let has_alpha: bool = tags.has("alpha")  // true
let updated = tags.add("delta").remove("beta")
```

#### Set API

```
set.new(): set<T>
set.from(items: array<T>): set<T>

s.has(val: T): bool
s.add(val: T): set<T>  // immutable: returns new set
s.remove(val: T): set<T>  // immutable: returns new set
s.insert(val: T)  // :mut only
s.delete(val: T)  // :mut only
s.union(other: set<T>): set<T>
s.intersect(other: set<T>): set<T>
s.difference(other: set<T>): set<T>
s.values(): stream<T>
s.len(): int
```

### Custom Collection Types

Any type may fulfill `collection<K, V>` to plug into generic collection-handling code:

```
type OrderedMap<K, V> fulfills collection<K, V> {
    // tree-backed ordered map implementation
    fn get(self, key: K): option<V> { ... }
    fn set(self, key: K, val: V): OrderedMap<K, V> { ... }
    fn keys(self): stream<K> { ... }
    fn values(self): stream<V> { ... }
    fn has(self, key: K): bool { ... }
    fn len(self): int { ... }
}
```

---

## Functions

Every function returns exactly one value. For multiple return values, use a tuple, record, or named type. The return type `none` is for functions that perform side effects without producing a result.

### Named Functions

```
fn add(x: int, y: int): int {
    return x + y
}
```

Single-expression body (expression form):

```
fn add(x: int, y: int): int = x + y
```

### Default Parameter Values

Parameters may have default values. Once a parameter has a default, all subsequent parameters must also have defaults. Default values must be compile-time constant expressions (literals or `none`).

```
fn connect(host:string, port:int = 80, timeout:int = 30):Connection {
    // ...
}

connect("example.com")             // port=80, timeout=30
connect("example.com", 443)        // timeout=30
connect("example.com", 443, 60)    // all explicit
```

### Named Arguments

Function calls may use named arguments to pass values by parameter name rather than position. Named arguments follow positional arguments. Once a named argument appears, all subsequent arguments must be named.

```
connect(host: "example.com", port: 443)
connect("example.com", timeout: 60)    // positional first, then named
```

Named arguments are reordered to match parameter positions at compile time. They interact with defaults: named arguments can skip parameters that have defaults.

```
fn f(a:int, b:int = 10, c:int = 20):int = a + b + c

f(1, c: 5)    // a=1, b=10 (default), c=5
```

Errors:
- Positional argument after a named argument is a compile error.
- Duplicate named arguments are a compile error.
- Unknown parameter names are a compile error.

### Variadic Parameters

A function may declare its last parameter as variadic using the `..` prefix. Inside the function body, the variadic parameter has type `array<T>` where `T` is the declared element type.

```
fn sum(..vals:int):int {
    let total:int:mut = 0
    for (v:int in vals) {
        total = total + v
    }
    return total
}
```

At call sites, individual arguments are automatically packed into an array:

```
sum(1, 2, 3)    // vals = [1, 2, 3]
sum()            // vals = []  (empty array)
sum(42)          // vals = [42]
```

An existing array can be spread into a variadic position with `..`:

```
let nums = [10, 20, 30]
sum(..nums)      // vals = nums
```

A function may have both fixed and variadic parameters. The variadic parameter must be last:

```
fn log(level:string, ..parts:string):none { ... }
log("INFO", "started", "server")   // level="INFO", parts=["started", "server"]
```

Restrictions:
- Only one variadic parameter per function.
- The variadic parameter must be the last parameter.
- A variadic parameter cannot have a default value.
- Not available on `extern fn` declarations.
- At a call site, either pass individual arguments or a single spread (`..arr`), not both mixed.
- Named arguments fill fixed parameters only, not the variadic parameter.

Several stdlib functions use variadic parameters:
- `path.join(..segments:string)` — join any number of path segments
- `math.min(first:T, ..rest:T)` / `math.max(first:T, ..rest:T)` — N-ary min/max
- `string.join(sep:string, ..parts:string)` — join strings with separator
- `json.array_val(..items:JsonValue)` — build a JSON array from values

### Lambdas

```
let f = \(x: int, y: int => x + y)
```

The type of `f` is inferred as `fn(int, int): int`. An explicit type annotation:

```
let f: fn(int, int): int = \(x: int, y: int => x + y)
```

Lambdas capture variables from the enclosing scope (see [Lambda Capture Semantics](#lambda-capture-semantics)):

```
fn process(x: int, threshold: int): bool {
    let check = \(v: int => v > threshold)  // captures threshold
    return check(x)
}
```

### Function Types

```
fn(int): bool
fn(int, int): int
fn(string): stream<int>
fn(record): bool
```

Function types are used in parameter declarations:

```
fn filter<T>(pred: fn(T): bool, s: stream<T>): stream<T> {
    for(item: T in s) {
        if (pred(item)) { yield item }
    }
}
```

### Generic Functions

```
fn transform<T, U>(s: stream<T>, f: fn(T): U): stream<U> {
    for(item: T in s) {
        yield f(item)
    }
}
```

### Bounded Generic Functions

Type parameters on functions may carry interface bounds. The compiler checks
bounds at each call site: the concrete type inferred for the parameter must
fulfill the required interface.

```
// Single bound
fn max<T fulfills Comparable>(a: T, b: T): T {
    return if (a.compare(b) > 0) then a else b
}

// Multiple bounds on one parameter (parenthesized)
fn format_and_hash<T fulfills (Printable, Hashable)>(val: T): int {
    io.println(val.to_str())
    return val.hash()
}

// Multiple bounded parameters
fn convert<A fulfills Serializable, B fulfills Parseable>(a: A): B {
    return B.from_string(a.serialize())
}

// Mixed bounded and unbounded
fn wrap<T fulfills Printable, U>(val: T, extra: U): string {
    return val.to_str()
}
```

**Disambiguation rule**: Without parentheses, a comma after a bound name starts
a new type parameter. `<T fulfills A, B>` declares two parameters: `T` with
bound `A`, and unbounded `B`. To give `T` two bounds, use parentheses:
`<T fulfills (A, B)>`.

Bounded generics also work on type declarations, interface declarations, and
type aliases:

```
type Box<T fulfills Serializable> { value: T }
interface Transformer<T fulfills Parseable> { fn transform(self, input: T): T }
alias Sortable<T fulfills Comparable>: array<T>
```

### Pure Functions

A `pure` function is deterministic: the same inputs always produce the same outputs. The compiler transitively verifies purity:

- All called functions must also be `pure`.
- No mutable statics are read or written.
- No mutable statics are accessed (even with `@`).
- No I/O is performed.
- No randomness or time-dependent operations.
- No `:mut` parameters are accepted.

`pure` functions may use local `:mut` variables internally, as long as the mutation does not escape.

```
fn:pure square(x: int): int = x * x

fn:pure sum(items: array<int>): int {
    let total: int:mut = 0
    for(item: int in items) { total += item }
    return total
}

fn:pure bad(x: int): int = x + random()  // compile error: random() is not pure
```

#### Caching and Memoization

The runtime may memoize `pure` function results within a composition chain. If two fan-out branches call the same `pure` function on the same element, the result is computed once and shared. The cache is per-element and released when the element clears the pipeline.

### Function-level `finally`

Any function may include a `finally` block that runs exactly once on termination, regardless of how the function exits (return, early return, consumer abandonment, or exception).

```
fn read_lines(path: string): stream<string> {
    let handle = file.open(path)
    for(line: string in handle) {
        if (line == "STOP") { return }
        yield line
    }
} finally {
    handle.close()
}
```

---

## String Interpolation

Flow supports f-strings for string interpolation. An f-string is prefixed with `f` and uses `{}` for embedded expressions.

```
let name: string = "Alice"
let score: int = 95
let msg: string = f"Player {name} scored {score} points."

let url: string = f"postgres://{Config.host}:{Config.port}/{Config.db_name}"
```

Expressions inside `{}` are evaluated and converted to strings using the value's `.to_string()` method. Complex expressions are supported:

```
let summary = f"Total: {items -> count}, Average: {items -> average -> round(2)}"
```

Standard string concatenation with `+` remains available for simple cases.

### Showable Auto-coercion in String Concatenation

When one operand of `+` is a `string` and the other is a type that fulfills `Showable`, the compiler automatically inserts a `.to_string()` call on the non-string operand. This allows natural string building:

```
let count = 42
let msg = "count: " + count  // "count: 42"
let pi = 3.14
let s = "pi = " + pi + "!"  // "pi = 3.14!"
```

This coercion applies only to `+` and only when at least one operand is statically `string`. It does not apply to other arithmetic operators.

---

## Scoping

Functions can only access:

- Their own parameters.
- Local variables declared within the function body.
- Imported functions from the module level.
- Static type members via the type name.

Functions cannot access outer function scopes or module-level `let` bindings.

Lambdas are the exception: a lambda can access anything in the scope where it is defined, including the enclosing function's parameters and locals.

### Shadowing

Inner scopes silently shadow outer names. The outer name is inaccessible within the inner scope. There is no parent accessor. This applies everywhere: blocks, functions, lambdas, match arms. No warning is emitted when shadowing occurs.

```
fn example(): none {
    let x = 1
    if (true) {
        let x = 2  // shadows outer x, no warning
        print(x)  // prints 2
    }
    print(x)  // prints 1
}
```

```
fn process(x: int, threshold: int): bool {
    let check = \(v: int => v > threshold)  // captures threshold
    return check(x)
    // v is not accessible here
}
```

### Lambda Capture Semantics

Immutable values are captured by reference (cheap, safe to share). Mutable values are captured by copy (snapshot at creation time). Changes to the original do not affect the lambda's copy and vice versa.

```
fn example(): fn(): int {
    let x: int = 10  // immutable: captured by reference
    let y: int:mut = 20  // mutable: captured by copy

    return \( => x + y)  // x is shared, y is snapshot
}
```

A lambda that captures `:mut` values by copy is safe to use in parallel fan-out.

---

## Ownership

Flow uses a **linear ownership with implicit borrowing** model. Every value has exactly one owner at a time. Passing a value to a function is an implicit borrow: the function uses the value temporarily, and ownership reverts to the caller when the function returns. Ownership permanently transfers only when a value escapes the function (via return, yield, or storage).

The compiler tracks ownership statically and rejects programs that would share mutable data across parallel execution boundaries.

### Implicit Borrow (Default)

```
let a: string = "hello"
foo(a)
// a is accessible here: foo borrowed it, returned, ownership reverted
foo(a)
bar(a)
// both calls are valid, a is borrowed and returned each time
```

During `foo`'s execution, `a` is owned by `foo`. This prevents concurrent access but requires no special syntax for the 90% case.

### Ownership Escape

A value escapes a function when it is:

- Returned from the function.
- Stored inside a returned value.
- Yielded to a stream consumer.

When a value escapes, ownership transfers to the caller permanently. The original binding is no longer accessible after the escape point.

```
fn identity(x: string): string {
    return x  // x escapes via return; ownership moves to caller
}

fn process(x: string): int {
    let len = x.len()
    return len  // len escapes (value type, copied); x did not escape, reverts
}
```

### Mutation Visibility

Modifying a `:mut` parameter is visible to the caller after the function returns:

```
fn increment(x: int:mut) { x++ }

let val: int:mut = 5
increment(val)
// val is now 6
```

To prevent mutation visibility, pass a copy:

```
increment(@val)
// val is still 5, the copy was modified and discarded
```

### The `@` Copy Operator

`@` always produces a mutable deep copy — an independent value that does not share memory with the source. For value types (int, float, bool, byte), `@` is a trivial stack copy. For heap types (string, array), `@` allocates a new copy of the data.

```
let data: array<int> = [1, 2, 3]
process(@data)
// data is still owned here; @data is an independent deep copy
```

### The `&` Ref Operator

`&` produces a cheap immutable reference — a refcount increment that allows the data to be shared without copying. `&` is only valid on immutable bindings; applying `&` to a `:mut` binding is a compile error. Since `&` does not create a new independent copy, it cannot satisfy a `:mut` parameter.

```
let data: array<int> = [1, 2, 3]
inspect(&data)
// data is still owned here; &data shared the same backing memory (refcount++)
```

### Ownership and Parallel Execution

Mutable data cannot be shared across parallel fan-out branches or coroutine boundaries. To use mutable data in parallel:

- Transfer ownership (the sender loses access).
- Copy with `@` (each branch gets an independent copy).
- Use `@` on a mutable static to get a thread-safe deep copy (see [Reading Mutable Statics](#reading-mutable-statics)).

Coroutines run on separate threads. Values passed to a coroutine function are owned by the coroutine's thread for its lifetime. Values yielded into the channel transfer ownership to the consumer. Immutable data can be safely shared between the spawning scope and the coroutine without copying.

### Ownership and Streams

In streaming functions consumed directly (without `:<`), parameters stay owned by the function for the stream's entire lifetime. The function is a suspended frame holding its captured variables until the stream closes. Ownership reverts only on stream close, not on each yield.

### Ownership and Coroutines

When a stream function is launched as a coroutine with `:<`, its parameters are owned by the producer thread for the coroutine's lifetime. Immutable parameters are shared via refcount increment. Mutable parameters are moved — the spawning scope loses access. Yielded values transfer ownership through the channel to the consumer.

For receivable coroutines (first parameter is `stream<S>`), the inbox stream is created by the runtime and owned by the producer thread. Values sent via `.send()` transfer ownership through the inbox channel to the producer, following the same rules as yielded values in the reverse direction: immutable data is shared via refcount, mutable data is moved.

### Ownership Summary

| Action | Effect |
|--------|--------|
| `foo(a)` | `a` is borrowed by `foo`. Reverts to caller when `foo` returns, unless `a` escapes. |
| `foo(@a)` | A mutable deep copy is passed. Caller retains original `a`. Always independent. |
| `foo(&a)` | An immutable ref is passed (refcount increment). Only valid on immutable `a`. Cannot satisfy `:mut`. |
| `yield val` | Ownership of `val` transfers to the consumer. Value types are implicitly copied. |
| `yield @val` | A deep copy is yielded. Function retains ownership of `val`. |
| `return val` | Ownership of `val` transfers to the caller. Function terminates. |

---

## Memory Model

### Immutable Data

Immutable values (the default) are allocated once and shared freely across function calls, fan-out branches, composition chains, coroutines, and threads. No copying, no synchronization.

Primitives are stack-allocated and copied trivially. Heap-allocated immutable values (strings, arrays, custom types) are reference-counted. Reference cycles in immutable data are impossible by construction: a value cannot reference something that does not yet exist, and immutable values cannot be modified after creation.

### Mutable Data

Mutable values follow single-owner semantics enforced at compile time. At any moment, exactly one scope owns a mutable value.

### Stream Consumption

A stream can only have one consumer. This is enforced at compile time where possible and at runtime otherwise. When a stream is launched as a coroutine with `:<`, the coroutine handle is the sole consumer of the internal channel.

### Channel Communication

Channels provide thread-safe value transfer between coroutine producers and consumers. Sending a value into a channel is an atomic ownership transfer. Immutable values are shared via refcount (atomic increment). Mutable values are moved. Reference counting uses atomic operations to ensure thread safety.

```
// Compile error: stream consumed twice
let s = read_lines("data.csv")
let a = s -> process_a
let b = s -> process_b  // error: s already consumed

// Correct: buffer and copy
let s = read_lines("data.csv")
let buf: buffer<string>:mut = buffer.collect(s)
let a = (@buf).drain() -> process_a
let b = buf.drain() -> process_b
```

---

## Reading Mutable Statics

Mutable statics must be read through the `@` (copy) operator. This ensures a thread-safe deep copy is taken, preventing data races when mutable statics are accessed from concurrent contexts.

```
type Config {
    static host:string:mut = "localhost",
    static port:int:mut = 5432
}

let port = @Config.port    // deep copy of port at this moment
let host = @Config.host    // deep copy of host
```

Reading a mutable static without `@` is a compile error:

```
let port = Config.port     // compile error: mutable static 'port' must be accessed with @ for thread safety
```

Writing to a mutable static does not require `@`:

```
Config.port = 8080         // assignment is fine without @
```

The `@` operator uses the existing deep-copy mechanism (`@expr`), which is already part of the language for ownership management. This replaces the former `snapshot()` built-in with a more consistent approach that reuses existing language primitives.

---

## Control Flow

### `if` / `else`

```
if (a == 9) {
    do_something()
} else if (a == 10) {
    do_something_else()
} else {
    default_action()
}
```

`if`/`else` is an expression when both branches produce the same type:

```
let label: string = if (score >= 90) { "A" } else { "B" }
```

### Ternary

```
let a = b == c ? d : e
```

### `match`

Pattern matching with `:` for each branch. Match arms are evaluated in order. For sum types, the compiler enforces exhaustiveness (see [Sum Types](#sum-types)).

```
let result = match entry.level {
    "ERROR" : handle_error(entry),
    "WARN"  : handle_warning(entry),
    _       : handle_default(entry)
}
```

Matching on sum types:

```
let area: float = match shape {
    Circle(r)        : 3.14159 * r * r,
    Rectangle(w, h)  : w * h,
    Triangle(b, h)   : 0.5 * b * h
}
```

Matching on `option<T>` and `result<T, E>`:

```
let value = match lookup(key) {
    some(v)  : v,
    none     : default_value()
}

let msg = match parse(raw) {
    ok(record)   : f"Parsed: {record.id}",
    err(e)       : f"Failed: {e}"
}
```

### Exhaustiveness

For sum types: all variants must be handled or `_` must be present. Omitting a variant is a compile error.

For primitive types and strings: full exhaustiveness cannot always be verified statically. Unmatched patterns produce a runtime error with a compile-time warning. Use `_` to suppress the warning and handle the default explicitly.

### `while`

```
while (condition) {
    do_something()
}

while (condition) {
    do_work()
} finally {
    cleanup()
}
```

### Loop Control: `break` and `continue`

`break` exits the innermost enclosing `while` or `for` loop. `continue` skips the remainder of the current iteration and proceeds to the next one.

```
while (i < 100) {
    i = i + 1
    if (i == 50) { continue }  // skip 50, keep going
    if (i == 75) { break }  // stop at 75
    process(i)
}
```

Both `break` and `continue` trigger the `finally` block of the enclosing loop if one is present.

### `for`

Iteration form:

```
for(item: int in collection) {
    do_something(item)
}
```

`for` supports `finally`:

```
for(item: int in data) {
    if (item == 0) { break }
    process(item)
} finally {
    cleanup()  // runs after exhaustion or break
}
```

### Composable `for`

A `for` block may appear in a composition chain. It consumes a collection or stream, iterates, and its `yield` statements produce an output stream flowing to the next stage.

```
fn process(data: array<int>): stream<string> =
    data -> for(x: int) {
        let doubled = x * 2
        yield f"val: {doubled}"
    } -> filter(\(s: string => s != "val: 4"))
```

Without a body, `for` decomposes the collection into a stream:

```
fn process(data: array<int>): stream<int> =
    data -> for(x: int) -> double -> square
```

---

## Composition

Composition chains are evaluated left to right. The chain operates on an implicit value stack: encountered values are pushed, encountered functions consume values from the stack by arity and push their result.

Every function returns exactly one value. `none` is a value and participates in the stack normally.

### Definitions

```
let sqr = \(x: int => x * x)
let mul = \(x: int, y: int => x * y)
let dbl = \(x: int => x * 2)
```

### Linear Composition

```
fn bar(x: int, y: int): int = x -> y -> mul -> sqr
```

Scanning left to right: `x` and `y` pushed to stack, `mul` (arity 2) consumes both and pushes result, `sqr` (arity 1) consumes result and pushes final value.

Equivalent to `sqr(mul(x, y))`.

### Fan-out with `|`

The `|` operator groups functions that each independently receive the same input. Results are pushed left to right.

The compiler statically verifies that the number of values produced by the fan-out group matches the arity of the downstream function. A mismatch is a compile error.

Shorthand form (one input, distributed to all branches):

```
fn foo(x: int): int = x -> (dbl | sqr) -> mul
```

`x` fans into both `dbl` and `sqr`. Their results feed `mul` (arity 2). Equivalent to `mul(dbl(x), sqr(x))`.

Long form (different inputs per branch):

```
fn baz(x: int, y: int): int = (x -> sqr | y -> dbl) -> mul
```

Equivalent to `mul(sqr(x), dbl(y))`.

Arity checking:

```
fn good(x: int): int = x -> (dbl | sqr) -> mul  // fan-out 2, mul takes 2: ok
fn bad(x: int): int  = x -> (dbl | sqr | inc) -> mul  // compile error: fan-out 3, mul takes 2
```

### Parallel Fan-out

`<:(a | b)` opts into concurrent execution of branches. The runtime may schedule branches on separate threads.

```
fn process(x: record): output =
    x -> <:(validate | compute_hash | extract_id) -> build_output
```

Parallel fan-out is safe because:

- Input to the fan-out is immutable.
- No branch reads or writes mutable statics.
- `pure` functions are always safe in parallel fan-out.
- Non-pure functions are permitted if they take only `:imut` parameters and do not access mutable statics.

### Chaining Fan-out with Linear Composition

```
fn pipeline(x: int): int = x -> (dbl | sqr) -> mul -> sqr
```

Equivalent to `sqr(mul(dbl(x), sqr(x)))`.

---

## Streams

A `stream<T>` is a lazy, pull-based sequence produced one value at a time. The consumer pulls values by iterating; the producer suspends on `yield` until the next pull. Backpressure is inherent.

A stream can have only one consumer.

Streams are single-threaded by default. To run a stream-producing function on a separate thread with channel-based buffering, use the `:<` coroutine operator. See [Coroutines](#coroutines).

### `yield` and `return`

In a `stream<T>` function:

- `yield` emits a value and suspends. Execution resumes on the next pull. Ownership transfers to the consumer (value types are implicitly copied).
- `return` closes the stream without emitting a value.

```
fn read_lines(path: string): stream<string> {
    let handle = file.open(path)
    for(line: string in handle) {
        if (line == "STOP") { return }
        yield line
    }
} finally {
    handle.close()
}
```

### Auto-mapping in Composition Chains

When a `stream<T>` flows into a function expecting `T` (not `stream<T>`), the chain automatically maps that function over each element. Every eager function is usable in a streaming pipeline without modification.

```
fn parse(line: string): record { ... }
fn filter<T>(pred: fn(T): bool, s: stream<T>): stream<T> { ... }
fn count<T>(s: stream<T>): int { ... }

fn pipeline(src: string): int =
    src -> read_lines -> parse -> filter(is_valid) -> count
```

- `read_lines`: `string -> stream<string>`
- `parse`: `string -> record`, auto-mapped element by element over the stream
- `filter`: `stream<record> -> stream<record>`, receives stream directly
- `count`: `stream<record> -> int`, consumes stream to a value

### Fan-out with Streams

Fan-out applies at the element level. Each element fans independently:

```
fn process(src: string): stream<output> =
    src -> read_lines -> (extract_id | parse_body) -> build_record
```

### Stream Helpers

```
stream.chunks(n: int): stream<buffer<T>>
stream.group_by(f: fn(T): K): stream<(K, buffer<T>)>
stream.take(n: int): stream<T>
stream.skip(n: int): stream<T>
stream.zip<U>(other: stream<U>): stream<(T, U)>
stream.flatten<U>(): stream<U>  // where T is stream<U> or array<U>
stream.map<U>(f: fn(T): U): stream<U>
stream.filter(pred: fn(T): bool): stream<T>
stream.reduce<U>(init: U, f: fn(U, T): U): U
```

`group_by` returns a stream of `(key, buffer)` pairs. The key is preserved:

```
fn summarize(src: string): stream<(string, int)> =
    src -> read_lines -> parse
        -> stream.group_by(\(r: record => r.category))
        -> for(group: (string, buffer<record>)) {
            let (cat, buf) = group
            yield (cat, buf.len())
        }
```

---

## Buffers

A `buffer<T>` is a mutable, in-memory container for materializing stream data. Used when an operation requires the full dataset (sorting, grouping). Buffers are always mutable.

A buffer that exceeds available memory throws `BufferOverflowError`.

### Buffer API

```
buffer.new(): buffer<T>
buffer.collect(s: stream<T>): buffer<T>
buffer.with_capacity(n: int): buffer<T>

buf.push(val: T)
buf.drain(): stream<T>  // converts to stream, consumes buffer
buf.len(): int
buf.get(i: int): option<T>
buf.sort_by(f: fn(T, T): int)
buf.reverse()
buf.slice(start: int, end: int): buffer<T>
```

### Buffers in Pipelines

Functions that buffer internally still present a `stream -> stream` interface to composition chains:

```
fn sort_by_date(s: stream<record>): stream<record> {
    let buf: buffer<record>:mut = buffer.collect(s)
    buf.sort_by(\(a: record, b: record => a.date - b.date))
    return buf.drain()
}
```

### Windowed Buffering

```
fn batch_process(s: stream<record>): stream<record> {
    let chunks: stream<buffer<record>> = s.chunks(1000)
    // process each chunk independently
}
```

---

## Coroutines

The `:<` operator spawns a stream-producing function on a new thread, creating a **threaded producer** that communicates with the caller through an internal channel. This is Flow's primary mechanism for concurrent execution of producers and consumers.

Streams (`stream<T>`) remain lazy and pull-based when consumed directly. The `:<` operator is what adds threading — it wraps a stream function in a concurrent producer that pushes values into a bounded channel as they are yielded.

### Starting a Coroutine

```
let gen :< producer(seed)
```

This:

1. Creates a bounded channel internally.
2. Spawns a new thread that runs `producer(seed)`.
3. Each `yield` in the producer pushes a value into the channel (blocking if full).
4. Returns immediately with a coroutine handle.

### Configurable Buffer Capacity

The default channel capacity is 64. To specify a different capacity, annotate the stream type on the function signature with `[N]`:

```
fn producer(seed: int): stream<int>[128] {  // outbox capacity 128
    yield seed
}

fn handler(inbox: stream<string>[32]): stream<Result>[64] {
    // inbox capacity 32, outbox capacity 64
    for (msg in inbox) {
        yield process(msg)
    }
}

let gen :< producer(seed)  // uses capacity 128 from signature
```

The `[N]` capacity is a runtime hint, not part of type identity — `stream<int>[64]` and `stream<int>[128]` are both `stream<int>` for type checking purposes. `N` can be any integer expression. When `[N]` is omitted, the default capacity of 64 is used.

### Coroutine API

The coroutine handle exposes up to three methods, depending on whether the coroutine function is **receivable** (supports bidirectional communication).

```
gen.next(): option<YieldType>  // read next value from channel; blocks if empty; none when done
gen.poll(): option<YieldType>  // non-blocking: returns none immediately if nothing ready
gen.send(val: SendType)  // push a value into the producer's inbox stream (receivable only)
gen.done(): bool  // true when producer has finished AND channel is drained
```

`.next()` blocks the calling thread if the channel is empty and the producer is still running. It returns `none` only when the producer has finished (returned or fallen off the end of the function) and all buffered values have been consumed.

`.poll()` is the non-blocking counterpart of `.next()`. It checks the channel without blocking — returning `none` immediately if no value is available yet. `.poll()` is useful for event loops that need to check multiple coroutines without blocking on any single one.

`.done()` returns `true` only when both conditions hold: the producer thread has terminated and the internal channel has been fully drained. While buffered values remain, `.done()` returns `false` even if the producer has finished.

### Receivable Coroutines and `.send()`

A coroutine function is **receivable** when its first parameter has type `stream<S>`. This first parameter is the **inbox** — a stream that the runtime automatically creates and wires to the coroutine handle's `.send()` method. The inbox parameter is implicit at the call site; remaining parameters are passed as normal arguments.

```
fn handler(inbox: stream<string>, config: Config): stream<Result> { ... }

let h :< handler(my_config)  // inbox is auto-created; my_config maps to 2nd param
h.send("command")  // pushes "command" onto inbox: stream<string>
match h.next() { ... }  // pulls from yields: option<Result>
```

The type of `.send()` is derived from the inbox parameter: if the first parameter is `stream<S>`, then `.send()` accepts `S`. The type of `.next()` is derived from the return type: if the function returns `stream<Y>`, then `.next()` returns `option<Y>`. The two types are independent.

| Method | Type | Direction |
|--------|------|-----------|
| `.send(val)` | `S` from first param `stream<S>` | consumer → producer |
| `.next()` | `option<Y>` from return `stream<Y>` | producer → consumer |
| `yield val` | `Y` | producer emits |
| inbox consumption | `S` | producer receives |

If the first parameter is **not** `stream<S>`, the coroutine is **send-less** — calling `.send()` is a compile error.

Inside the producer function, the inbox is consumed like any other stream: via `for-in`, pattern matching on `.next()` calls, or any stream operation. The inbox is backed by a bounded channel, so the consumer's `.send()` blocks if the inbox buffer is full (backpressure applies in both directions).

### Receivable Coroutine Example

```
fn echo_worker(inbox: stream<string>): stream<string> {
    for (msg: string in inbox) {
        yield "echo: " + msg
    }
}

let w :< echo_worker()
w.send("hello")
w.send("world")
match w.next() { some(v): { io.println(v) } none: {} }  // "echo: hello"
match w.next() { some(v): { io.println(v) } none: {} }  // "echo: world"
```

The type parameters of `.send()` and `.next()` are always derived from the coroutine function's signature. Passing the wrong type is a compile error.

### Example: Basic Producer

```
fn producer(seed: int): stream<int> {
    let current: int:mut = seed
    while (true) {
        yield current  // pushes into channel, may block if full
        current = current * 2
    }
}

let gen :< producer(1)  // spawns thread, returns immediately
let a: option<int> = gen.next()  // some(1) — reads from channel
let b: option<int> = gen.next()  // some(2)
let c: option<int> = gen.next()  // some(4)
```

The producer runs concurrently. While the caller processes value `a`, the producer may have already computed and buffered values `b`, `c`, and beyond (up to the channel capacity).

### Example: Concurrent Producers

Immutable data can be safely shared across multiple coroutines without copying or locking:

```
let config: Config = load_config()
let a :< process_batch(config, chunk_1)
let b :< process_batch(config, chunk_2)
// both threads share config via refcount — zero copies, zero locks
```

Both producers run concurrently on separate threads. The caller can interleave reads:

```
match a.next() { some(v): { handle(v) } none: {} }
match b.next() { some(v): { handle(v) } none: {} }
```

### Backpressure

Backpressure is automatic. When the channel is full, the producer's `yield` blocks until the consumer calls `.next()`. This prevents unbounded memory growth without requiring explicit flow control.

A capacity of 1 creates tight synchronization: the producer can only advance one step ahead of the consumer. A larger capacity allows the producer to run ahead, smoothing out latency variations.

### Exception Propagation

If the producer thread throws an exception, it is captured and re-thrown on the consumer thread the next time `.next()` is called. This preserves the illusion of sequential execution for error handling:

```
fn failing_producer(): stream<int> {
    yield 1
    throw ParseError("bad data")
}

let gen :< failing_producer()
let a = gen.next()  // some(1)
let b = gen.next()  // throws ParseError on the caller's thread
```

### Coroutine Lifetime

A coroutine's producer thread runs until the function returns, the stream is exhausted, or an exception is thrown. When the coroutine handle goes out of scope and is released, the runtime closes both the output channel and the inbox channel (if receivable), then joins the producer thread. If the producer is blocked on a full channel or waiting on an empty inbox, the close unblocks it.

### Streams vs. Coroutines

| | `stream<T>` | `let c :< fn()` |
|---|---|---|
| **Execution** | Lazy, pull-based, same thread | Eager, push-based, separate thread |
| **Yield** | Suspends via state machine, resumes on next pull | Pushes into channel, blocks if full |
| **Backpressure** | Inherent (consumer drives) | Channel capacity (producer blocks when full) |
| **Bidirectional** | No | Yes, if first param is `stream<S>` (receivable) |
| **Use when** | Simple pipelines, composition chains | Concurrent production, I/O overlap, bidirectional communication |

---

## Exception Handling

Exceptions are for conditions outside the expected failure path: infrastructure failures, corrupted data, bugs, and situations that may be correctable with retry logic. For expected, typed failures, use `result<T, E>`.

Exceptions are types that fulfill the built-in `Exception<T>` interface, where `T` is the type of the failing payload:

```
interface Exception<T> {
    fn message(self): string  // human-readable description of the failure
    fn data(self): T  // the payload that caused the failure (mutable in retry context)
    fn original(self): T  // the original payload, unmodified, read-only
}
```

`data` and `original` separate the correctable state from the audit trail. In a `retry` block, `ex.data` is mutable: the developer modifies it before the named function re-runs. `ex.original` is always the value as it was when the exception was first thrown, regardless of how many times `ex.data` has been modified across retry attempts.

### Defining Exception Types

Exception types are declared as regular types fulfilling `Exception<T>`:

```
type ParseError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor from_raw(m: string, p: string): ParseError {
        return ParseError {
            msg: m,
            payload: p,
            original_payload: p  // original is set once at construction and never changes
        }
    }

    fn message(self): string  { return self.msg }
    fn data(self): string     { return self.payload }
    fn original(self): string { return self.original_payload }
}

type ValidationError fulfills Exception<record> {
    msg: string,
    payload: record:mut,
    original_payload: record,

    constructor from_record(m: string, r: record): ValidationError {
        return ValidationError { msg: m, payload: r, original_payload: r }
    }

    fn message(self): string  { return self.msg }
    fn data(self): record     { return self.payload }
    fn original(self): record { return self.original_payload }
}
```

The `payload` field is declared `:mut` so the `retry` block can correct it. `original_payload` is immutable and set once at construction.

Throwing an exception:

```
throw ParseError.from_raw("unexpected token", raw_line)
throw ValidationError.from_record("missing required field", row)
```

### Syntax

```
try {
    // code that may throw
} retry function_name (ex: ExceptionType, attempts: <expr>) {
    // ex.data is mutable here: correct it before the retry
    // ex.original is always the original failing value, read-only
    // the named function re-runs with the corrected ex.data
    // <expr> is any integer expression (literal, variable, or computation)
} catch (ex: ExceptionType) {
    // handle after retries are exhausted (or if no retry exists)
    // ex.data holds the last corrected value; ex.original holds the first
} finally (? ex: Exception) {
    // cleanup; always runs exactly once
    // ex is present if an exception occurred, absent if try succeeded
}
```

All blocks except `try` are optional. `retry` and `catch` may each appear multiple times for different exception types.

### `retry` Semantics

`retry function_name` names the specific function in the composition chain to re-invoke. The `retry` block receives the exception, the developer corrects `ex.data`, and the named function is called again with the corrected value. Its result flows through the rest of the chain normally.

```
try {
    let result = line -> parse -> validate -> write
} retry parse (ex: ParseError, attempts: 3) {
    ex.data = sanitize(ex.data)  // correct the payload
    // parse() re-runs with the corrected string
    // its result flows into validate -> write as normal
}
```

After all retry attempts are exhausted, `catch` receives the exception. `ex.data` reflects the last attempted correction. `ex.original` is unchanged from the initial throw.

```
try {
    let result = src -> read_csv -> parse -> validate -> write
} retry parse (ex: ParseError, attempts: 3) {
    ex.data = sanitize(ex.data)
} retry validate (ex: ValidationError) {
    ex.data.missing_field = default_value()
} catch (ex: ParseError) {
    log(f"bad record after 3 attempts. original: {ex.original}, last attempt: {ex.data}")
} catch (ex: ValidationError) {
    quarantine(ex.data)
} finally (? ex: Exception) {
    if (ex) { log("pipeline completed with errors") }
    close_connections()
}
```

For non-chain code (imperative blocks), `retry` restarts the named function from its call site. Naming a function that does not appear in the `try` block is a compile error.

### `retry` and `catch` Escalation

For the same exception type, `retry` and `catch` form an escalation chain:

1. Exception thrown: `retry` runs if present. `ex.data` is corrected. The named function re-executes.
2. If it throws again: `retry` runs again, up to the attempt limit.
3. After attempts are exhausted: falls through to `catch` if present.
4. If no `catch`: exception propagates up the call stack.

### Execution Order

`finally` runs exactly once at termination, never between retries.

```
// Try succeeds:
try -> finally

// Retry fixes it:
try -> retry -> (function re-executes) -> finally

// Retry exhausted, catch exists:
try -> retry (n times) -> catch -> finally

// Retry exhausted, no catch:
try -> retry (n times) -> finally -> exception propagates

// No retry, catch exists:
try -> catch -> finally

// No retry, no catch:
try -> finally -> exception propagates
```

### Exception Propagation

Unhandled exceptions propagate up the call stack until caught or until the program terminates with an unhandled exception error.

---

## Foreign Function Interface (FFI)

Flow provides three `extern` declaration forms for binding C libraries directly
from any `.flow` module. The intended pattern is to declare extern bindings
privately and expose Flow-friendly wrappers as the public API.

### `extern lib`

Links a shared library at compile time. Translates to a `-l` flag passed to the
linker.

```
extern lib "ssl"       // -lssl
extern lib "crypto"    // -lcrypto
```

`export extern lib` is not allowed — library linkage is a build-level concern,
not an API concern.

### `extern type`

Declares an opaque C type. The type is represented as `void*` at runtime — Flow
code cannot inspect or modify its contents. Opaque types can be passed to and
returned from extern functions.

```
extern type SSL_CTX
extern type SSL
```

Extern types can be exported (`export extern type SSL_CTX`) so that importing
modules can use the type in their own function signatures.

### `extern fn`

Declares a C function by its exact name. The compiler emits the function call
with no name mangling.

```
extern fn SSL_CTX_new():ptr
extern fn SSL_write(ssl:SSL, buf:ptr, n:int):int
```

An optional alias form allows the Flow-callable name to differ from the C name:

```
extern fn "fl_sort_array_by" sort_by<T>(arr:array<T>, cmp:fn(T, T):int):array<T>
```

Generic type parameters are supported. The type parameters are used for
type inference at call sites but erased in the C call — the underlying C
function uses `void*` or similar type-erased signatures:

```
extern fn "fl_array_push_ptr" push<T>(arr:array<T>, val:T):array<T>
extern fn "fl_map_get_str" get<V>(m:map<string, V>, key:string):V?
```

Bounded type parameters work the same as for regular Flow functions:

```
extern fn "fl_sort" sort<T fulfills Comparable>(arr:array<T>):array<T>
```

Parameters and return types must use Flow types that map directly to C:

| Flow type | C type |
|-----------|--------|
| `int` | `int32_t` |
| `int64` | `int64_t` |
| `float` | `double` |
| `float32` | `float` |
| `bool` | `int32_t` (0/1) |
| `byte` | `uint8_t` |
| `ptr` | `void*` |
| `fn(A):B` | `B (*)(A)` (function pointer) |

Extern functions can be exported so that importing modules can call them
directly, but the idiomatic pattern is to wrap them:

```
module ssl

extern lib "ssl"
extern type SSL
extern fn SSL_write(ssl:SSL, buf:ptr, n:int):int

export fn write(ssl:SSL, data:string):int {
    return SSL_write(ssl, string.to_cptr(data), string.len(data))
}
```

### `ptr` type

`ptr` is a built-in opaque type representing a raw `void*` pointer. It cannot be
dereferenced, indexed, or used in pointer arithmetic — it is strictly an FFI
marshaling type. The only operations on `ptr` are:

- Pass to / receive from extern functions
- Assign `none` (null pointer)
- Convert to/from strings via `string.to_cptr()` and `string.from_cptr()`

### Function pointer callbacks

Non-capturing Flow functions can be passed as C function pointer arguments to
extern functions. When an extern fn parameter has a function type
(`fn(A, B):C`), passing a named Flow function takes its address directly:

```
extern fn register_handler(cb:fn(int):int):none

fn my_handler(x:int):int {
    return x * 2
}

fn main() {
    register_handler(my_handler)    // passes &fl_main_my_handler
}
```

Capturing closures (lambdas that reference outer variables) cannot be passed to
extern functions. The compiler rejects this with a clear error.

### Limitations

- **No automatic header inclusion.** Declaring `extern fn strlen(s:ptr):int`
  will conflict with the system `<string.h>` declaration if the types don't
  match exactly. For standard C library functions, use the Flow-equivalent
  signatures or wrap them in a separate C helper.
- **No struct-by-value.** C structs cannot be passed or returned by value. Use
  `ptr` for struct pointers.
- **No variadic extern functions.** Flow's variadic parameter syntax (`..name:Type`)
  is not available on `extern fn` declarations. C variadic functions like `printf`
  cannot be bound. Wrap them in a C helper with fixed arguments instead.

---

## Full Example: Data Pipeline

```
module pipeline.orders

import io (read_csv, write_csv)
import domain.order (Order, ParseError, ValidationError)

type PipelineConfig {
    static input_path: string:mut  = "data/orders.csv",
    static output_path: string:mut = "data/processed.csv",
    static error_log: string:mut   = "data/errors.log"
}

fn validate_order(o: Order): result<Order, string> {
    if (o.amount <= 0.0) {
        return err(f"Invalid amount: {o.amount}")
    }
    if (o.customer_id.is_empty()) {
        return err("Missing customer ID")
    }
    return ok(o)
}

// pure: no I/O, no mutation of external state, deterministic
fn:pure apply_discount(o: Order): Order =
    Order { amount: o.amount * 0.95, ..o }  // struct spread: copy all fields, override amount

fn run(): result<int, string> {
    let input  = @PipelineConfig.input_path
    let output = @PipelineConfig.output_path

    try {
        let count = input
            -> read_csv
            -> parse_order
            -> filter(\(o: Order => o.amount > 0.0))
            -> <:(validate_order | apply_discount)
            -> merge_validated
            -> write_csv(output)

        return ok(count)

    } retry parse_order (ex: ParseError, attempts: 2) {
        // ex.data is the string that failed to parse
        // ex.original is that same string, frozen at throw time
        ex.data = sanitize(ex.data)  // correct it; parse_order re-runs with ex.data

    } catch (ex: ParseError) {
        // retries exhausted: log both the original and the last attempted correction
        log_error(PipelineConfig.error_log,
            f"parse failed after retries. original: '{ex.original}', last: '{ex.data}'")

    } finally (? ex: Exception) {
        if (ex) { return err(ex.message()) }
    }
}
```
