# Appendix A: Language Reference

This appendix is a concise, complete reference to the Flow programming language. It is organized for lookup, not for learning. For tutorial-style coverage, see the main chapters.

---

## A.1 Lexical Elements

### A.1.1 Keywords

Flow reserves the following identifiers. They cannot be used as variable names, function names, type names, or module path components.

| | | | | | |
|---|---|---|---|---|---|
| `alias` | `as` | `bool` | `break` | `buffer` | `byte` |
| `cast` | `catch` | `char` | `coerce` | `constructor` | `continue` |
| `else` | `err` | `export` | `false` | `finally` | `float` |
| `float32` | `float64` | `fn` | `for` | `fulfills` | `if` |
| `import` | `imut` | `in` | `int` | `int16` | `int32` |
| `int64` | `interface` | `let` | `match` | `module` | `mut` |
| `native` | `none` | `ok` | `option` | `pure` | `record` |
| `result` | `retry` | `return` | `self` | `set` | `snapshot` |
| `some` | `static` | `stream` | `string` | `throw` | `true` |
| `try` | `type` | `typeof` | `uint` | `uint16` | `uint32` |
| `uint64` | `while` | `yield` | | | |

The modifier `fn:pure` is written as the keyword `fn` followed by `:pure`, not as a single token. Similarly, `:mut` and `:imut` are the colon token followed by a keyword.

### A.1.2 Operators and Precedence

Operators are listed from highest precedence (tightest binding) to lowest. Operators at the same precedence level are evaluated according to the associativity column.

| Prec | Operator(s) | Description | Assoc |
|:----:|-------------|-------------|:-----:|
| 1 | `.` | Field/method access | Left |
| 1 | `()` | Function call | Left |
| 1 | `[]` | Index access | Left |
| 2 | `!` | Logical NOT | Right |
| 2 | `-` (unary) | Negation | Right |
| 2 | `@` | Copy | Right |
| 3 | `**` | Exponentiation | Right |
| 4 | `*`  `/`  `%`  `//` | Multiply, divide, modulo, floor div | Left |
| 5 | `+`  `-` | Add, subtract | Left |
| 6 | `<`  `>`  `<=`  `>=` | Relational comparison | Left |
| 7 | `==`  `!=`  `===` | Equality, inequality, congruence | Left |
| 8 | `&&` | Logical AND (short-circuit) | Left |
| 9 | `\|\|` | Logical OR (short-circuit) | Left |
| 10 | `??` | Null coalescing (short-circuit) | Left |
| 11 | `?` (postfix) | Propagation | Left |
| 12 | `? :` | Ternary conditional | Right |
| 13 | `->` | Composition | Left |
| 14 | `\|` | Fan-out | Left |
| 14 | `<:(` | Parallel fan-out | Left |
| 15 | `:<` | Coroutine spawn | Right |
| 16 | `=`  `+=`  `-=`  `*=`  `/=` | Assignment, compound assignment | Right |
| 16 | `++`  `--` | Increment, decrement (statement) | N/A |

### A.1.3 Literals

#### Integer Literals

```flow
42                  ; decimal
-17                 ; negative
0                   ; zero
1_000_000           ; underscores for readability
0xFF                ; hexadecimal
0xDEAD_BEEF         ; hex with underscores
```

Integer literals are `int` (32-bit signed) by default. Assign to a typed binding for other widths:

```flow
let a: int64 = 1_000_000_000_000
let b: uint = 42
let c: byte = 255
```

#### Float Literals

```flow
3.14                ; basic decimal
-0.5                ; negative
1.0                 ; explicit float (the decimal point is required)
1e10                ; scientific notation
2.5e-3              ; scientific with negative exponent
1_000.000_1         ; underscores permitted
```

Float literals are `float` (64-bit, IEEE 754 double) by default. Use a typed binding for `float32`.

#### String Literals

```flow
"hello"             ; plain string
"line one\nline two"; escape sequences
""                  ; empty string
```

Escape sequences:

| Sequence | Meaning |
|----------|---------|
| `\n` | Newline |
| `\t` | Tab |
| `\r` | Carriage return |
| `\\` | Backslash |
| `\"` | Double quote |
| `\'` | Single quote |
| `\0` | Null byte |
| `\{` | Literal `{` (in f-strings) |
| `\u{XXXX}` | Unicode scalar (hex) |

#### F-String Literals

```flow
f"hello {name}"
f"result: {x + y}"
f"nested: {items -> count}"
```

Expressions inside `{}` are evaluated and converted to string via `.to_string()`. Use `\{` for a literal brace.

#### Boolean Literals

```flow
true
false
```

#### Character Literals

```flow
'A'
'\n'
'\u{03B1}'          ; Greek alpha
```

Character literals produce a `char` value (Unicode scalar).

#### Array Literals

```flow
[1, 2, 3]           ; array<int>
["a", "b"]           ; array<string>
[]                   ; empty array (type inferred from context)
```

All elements must be the same type.

#### Tuple Literals

```flow
(42, "hello")        ; (int, string)
(1.0, 2.0, 3.0)     ; (float, float, float)
```

#### None Literal

```flow
none                 ; the absence value for option<T>
```

### A.1.4 Comments

```flow
; this is a comment
; there are no block comments
; multi-line comments repeat the semicolon on each line
```

The `;` character begins a comment that extends to the end of the line. There is no block comment syntax.

### A.1.5 Identifiers

Identifiers begin with a letter or underscore, followed by letters, digits, or underscores. Flow is case-sensitive. Identifiers must not collide with keywords.

```
[a-zA-Z_][a-zA-Z0-9_]*
```

---

## A.2 Types

### A.2.1 Primitive Types

| Type | Size | Description | Value type |
|------|------|-------------|:----------:|
| `bool` | 1 byte | `true` or `false` | Yes |
| `byte` | 8-bit | Unsigned integer 0--255 | Yes |
| `char` | 32-bit | Unicode scalar value | Yes |
| `int` | 32-bit | Signed integer (alias: `int32`) | Yes |
| `int16` | 16-bit | Signed integer | Yes |
| `int32` | 32-bit | Signed integer (same as `int`) | Yes |
| `int64` | 64-bit | Signed integer | Yes |
| `uint` | 32-bit | Unsigned integer (alias: `uint32`) | Yes |
| `uint16` | 16-bit | Unsigned integer | Yes |
| `uint32` | 32-bit | Unsigned integer (same as `uint`) | Yes |
| `uint64` | 64-bit | Unsigned integer | Yes |
| `float` | 64-bit | IEEE 754 double (alias: `float64`) | Yes |
| `float32` | 32-bit | IEEE 754 single | Yes |
| `float64` | 64-bit | IEEE 754 double (same as `float`) | Yes |
| `string` | ptr | Immutable UTF-8, ref-counted on heap | No |
| `none` | 0 | Unit type; sole value is `none` | Yes |

Value types are stack-allocated and implicitly copied on assignment, function call, and yield. Ownership semantics do not apply to value types.

### A.2.2 Compound Types

| Type | Description |
|------|-------------|
| `array<T>` | Ordered, immutable sequence. Integer-indexed. |
| `(T, U, ...)` | Tuple. Fixed-size ordered product. |
| `option<T>` | `some(T)` or `none`. Sugar: `T?` |
| `result<T, E>` | `ok(T)` or `err(E)` |
| `stream<T>` | Lazy, pull-based sequence. Single consumer. |
| `buffer<T>` | Mutable materialized sequence. |
| `map<K, V>` | Hash map. Keys must be hashable. |
| `set<T>` | Unordered unique collection. Elements must be hashable. |
| `record` | Structural type with string keys, heterogeneous values. |

#### Named Struct Types

```flow
type Point {
    x: float,
    y: float
}
```

#### Sum Types (Tagged Unions)

```flow
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)
    | Triangle(base: float, height: float)

type Direction = | North | South | East | West
```

Variants without parentheses carry no payload.

### A.2.3 Function Types

```flow
fn(int): bool               ; takes int, returns bool
fn(int, int): int            ; two params
fn(string): stream<int>      ; returns a stream
fn(): none                   ; no params, no meaningful return
```

Function types are used for lambda bindings, higher-order parameters, and type annotations.

### A.2.4 Generic Types

Type parameters are declared in angle brackets. They may carry interface bounds.

```flow
; Unbounded
type Pair<A, B> { first: A, second: B }

; Single bound
type SortedList<T fulfills Comparable> { items: array<T> }

; Multiple bounds (parenthesized)
type Cache<K fulfills (Hashable, Comparable), V> { data: map<K, V> }
```

### A.2.5 Type Modifiers

Modifiers follow a strict order: type, then `?`, then `:mut`/`:imut`.

| Syntax | Meaning |
|--------|---------|
| `int` | Immutable integer |
| `int?` | Immutable optional integer (sugar for `option<int>`) |
| `int:mut` | Mutable integer |
| `int?:mut` | Mutable optional integer |
| `int:imut` | Explicitly immutable integer |
| `int:mut?` | **Compile error.** `?` must precede `:mut`. |

### A.2.6 Type Aliases

```flow
alias Timestamp: int
alias UserID: string
alias Transform<T, U>: fn(stream<T>): stream<U>
```

Aliases create distinct named types. Convert with `.from()` and `.value()`:

```flow
let t: Timestamp = Timestamp.from(12345)
let raw: int = t.value()
```

---

## A.3 Expressions

### A.3.1 Expression Summary Table

| Form | Syntax | Example |
|------|--------|---------|
| Integer literal | `N` | `42` |
| Float literal | `N.N` | `3.14` |
| String literal | `"..."` | `"hello"` |
| F-string | `f"...{expr}..."` | `f"x={x}"` |
| Boolean literal | `true` / `false` | `true` |
| Character literal | `'c'` | `'A'` |
| None literal | `none` | `none` |
| Array literal | `[e, ...]` | `[1, 2, 3]` |
| Tuple literal | `(e, e)` | `(42, "hi")` |
| Identifier | `name` | `count` |
| Field access | `expr.field` | `p.x` |
| Tuple index | `expr.N` | `pair.0` |
| Method call | `expr.method(args)` | `s.len()` |
| Function call | `fn(args)` | `sqrt(x)` |
| Index access | `expr[expr]` | `arr[i]` |
| Binary op | `expr op expr` | `a + b` |
| Unary negation | `-expr` | `-x` |
| Logical NOT | `!expr` | `!done` |
| Copy | `@expr` | `@data` |
| Lambda | `\(params => body)` | `\(x: int => x * 2)` |
| Ternary | `cond ? then : else` | `x > 0 ? x : -x` |
| If expression | `if (c) { a } else { b }` | `if (ok) { 1 } else { 0 }` |
| Match expression | `match e { arms }` | See A.6 |
| Cast | `cast<T>(expr)` | `cast<int64>(x)` |
| Coerce | `coerce(expr)` | `coerce(src)` |
| Typeof | `typeof(expr)` | `typeof(x)` |
| Snapshot | `snapshot(expr)` | `snapshot(Config.port)` |
| Copy operator | `@expr` | `@data` |
| Some wrapping | `some(expr)` | `some(42)` |
| Ok wrapping | `ok(expr)` | `ok(value)` |
| Err wrapping | `err(expr)` | `err("bad")` |
| Propagation | `expr?` | `parse(s)?` |
| Null coalescing | `expr ?? expr` | `name ?? "N/A"` |
| Composition | `expr -> expr` | `x -> f -> g` |
| Fan-out | `(expr \| expr)` | `(dbl \| sqr)` |
| Parallel fan-out | `<:(expr \| expr)` | `<:(a \| b)` |
| Coroutine spawn | `let x :< call()` | `let g :< produce(1)` |
| Struct literal | `Type { f: v }` | `Point { x: 1.0, y: 2.0 }` |
| Struct spread | `Type { f: v, ..src }` | `Point { x: 9.0, ..p }` |
| Record literal | `{ f: v, ... }` | `{ name: "A", age: 30 }` |

### A.3.2 Composition Chains

Composition chains evaluate left to right using an implicit value stack.

```flow
x -> f -> g              ; g(f(x))
x -> y -> mul            ; mul(x, y)
x -> (dbl | sqr) -> mul  ; mul(dbl(x), sqr(x))
```

Rules:
- Encountered values push onto the stack.
- Encountered functions consume arguments by arity and push their result.
- Fan-out `|` distributes the input to each branch; results push left to right.
- The compiler verifies that fan-out output count matches downstream function arity.

### A.3.3 The `?` Propagation Operator

Postfix `?` short-circuits on error/none:

| Subject type | On success | On failure |
|-------------|------------|------------|
| `result<T, E>` | Unwraps `ok(v)` to `v` | Returns `err(e)` from enclosing function |
| `option<T>` | Unwraps `some(v)` to `v` | Returns `none` from enclosing function |

The enclosing function must return a compatible `result` or `option` type.

### A.3.4 The `??` Null Coalescing Operator

```flow
let port: int = config_port() ?? 5432
```

If the left operand is `some(v)`, evaluates to `v`. If `none`, evaluates the right operand. Right side is only evaluated when needed (short-circuit).

### A.3.5 Lambdas

```flow
\(x: int => x * 2)                      ; single param
\(x: int, y: int => x + y)              ; multiple params
\( => 42)                                ; no params
\(s: string => s.len() > 5)             ; predicate
```

Capture rules:
- Immutable values captured by reference (cheap).
- Mutable values captured by copy (snapshot at lambda creation time).

### A.3.6 The `@` Copy Operator

| Data kind | `@` behavior |
|-----------|-------------|
| Immutable heap data (string, array, struct) | Refcount increment (cheap) |
| Mutable data | Deep copy (independent value) |
| Value types (int, float, bool, byte, char) | Implicit copy (no-op) |

---

## A.4 Statements

### A.4.1 Statement Summary Table

| Statement | Syntax |
|-----------|--------|
| Let binding | `let name: Type = expr` |
| Let binding (inferred) | `let name = expr` |
| Mutable let | `let name: Type:mut = expr` |
| Assignment | `target = expr` |
| Compound assignment | `target += expr` / `-=` / `*=` / `/=` |
| Increment | `target++` |
| Decrement | `target--` |
| Return | `return expr` / `return` |
| Yield | `yield expr` |
| Break | `break` |
| Continue | `continue` |
| Throw | `throw expr` |
| Expression statement | `expr` |
| Block | `{ stmts }` |

### A.4.2 `let` Bindings

```flow
let x: int = 5              ; immutable, explicit type
let y = compute()            ; immutable, inferred type
let z: int:mut = 0           ; mutable
let w: int?:mut = none       ; mutable optional
```

A `let` without `:mut` creates an immutable binding. Reassignment to an immutable binding is a compile error.

### A.4.3 Assignment and Update

Assignment and compound assignment are only valid on `:mut` bindings or `:mut` struct fields.

```flow
x = 10                       ; simple assignment
x += 5                       ; compound: x = x + 5
x -= 1                       ; compound: x = x - 1
x *= 2                       ; compound: x = x * 2
x /= 3                       ; compound: x = x / 3
x++                          ; increment: x = x + 1
x--                          ; decrement: x = x - 1
```

### A.4.4 `return`

Returns a value from the enclosing function. `return` without an expression returns `none`.

```flow
fn add(a: int, b: int): int {
    return a + b
}

fn log(msg: string) {
    io.println(msg)
    return                   ; explicit return none
}
```

### A.4.5 `yield`

Emits a value from a `stream<T>` function and suspends until the consumer pulls the next value. Ownership of the yielded value transfers to the consumer.

```flow
fn range(start: int, end: int): stream<int> {
    let i: int:mut = start
    while (i < end) {
        yield i
        i++
    }
}
```

### A.4.6 `break` and `continue`

`break` exits the innermost `while` or `for` loop. `continue` skips to the next iteration. Both trigger any `finally` block on the enclosing loop.

### A.4.7 `throw`

Throws an exception value. The value must fulfill the `Exception<T>` interface.

```flow
throw ParseError.from_raw("unexpected token", line)
```

---

## A.5 Declarations

### A.5.1 Module Declaration

Every file begins with a module declaration. The module path reflects the file's location relative to the project root.

```flow
module math.vector
```

### A.5.2 Import Declarations

```flow
import math.vector                   ; namespace import: vector.Vec3, vector.dot
import math.vector (Vec3, dot)       ; named imports: Vec3, dot in local scope
import math.vector as vec            ; aliased: vec.Vec3, vec.dot
```

Bare import uses the **last component** as the namespace name. Circular imports are a compile error.

### A.5.3 Export

Only `export`-marked declarations are visible to importers.

```flow
export fn visible(): int = 42
fn private(): int = 99               ; module-private
export type Point { x: float, y: float }
```

### A.5.4 Function Declarations

#### Block body

```flow
fn add(x: int, y: int): int {
    return x + y
}
```

#### Expression body

```flow
fn add(x: int, y: int): int = x + y
```

#### Pure functions

```flow
fn:pure square(x: int): int = x * x
```

Pure function restrictions:
- All called functions must be `pure`.
- No mutable statics read or written.
- No `snapshot()`, no I/O, no randomness.
- No `:mut` parameters accepted.
- Local `:mut` variables are permitted if mutation does not escape.

#### Generic functions

```flow
fn transform<T, U>(s: stream<T>, f: fn(T): U): stream<U> {
    for (item: T in s) { yield f(item) }
}
```

#### Bounded generic functions

```flow
fn max<T fulfills Comparable>(a: T, b: T): T {
    return if (a.compare(b) > 0) { a } else { b }
}

fn format<T fulfills (Printable, Hashable)>(val: T): string {
    return val.to_str()
}
```

Disambiguation: `<T fulfills A, B>` declares two parameters (`T` bounded by `A`, unbounded `B`). For two bounds on one parameter: `<T fulfills (A, B)>`.

#### Function-level `finally`

```flow
fn read_lines(path: string): stream<string> {
    let handle = file.open(path)
    for (line: string in handle) {
        yield line
    }
} finally {
    handle.close()
}
```

The `finally` block runs exactly once when the function terminates, regardless of how it exits.

### A.5.5 Type Declarations

#### Struct type

```flow
type LogEntry {
    timestamp: int,
    source: string,
    level: string,
    message: string
}
```

#### Struct with methods

```flow
type LogEntry {
    timestamp: int,
    source: string,

    fn severity(self): int {
        return if (self.source == "ERROR") { 8 } else { 1 }
    }

    fn is_critical(self): bool = self.severity() >= 8
}
```

Methods take explicit `self` as the first parameter.

#### Per-field mutability

```flow
type Counter {
    name: string,            ; immutable
    count: int:mut           ; mutable
}
```

#### Static members

```flow
type Config {
    static host: string:mut = "localhost",
    static port: int:mut = 5432,
    static max_retries: int = 3
}
```

Accessed via the type name: `Config.host`, `Config.port`.

#### Constructors

When any constructor is defined, literal construction is disabled.

```flow
type LogEntry {
    timestamp: int,
    source: string,

    constructor from_raw(ts: int, src: string): LogEntry {
        return LogEntry { timestamp: ts, source: src }
    }
}

let e = LogEntry.from_raw(100, "us-east-1")
```

#### Struct spread

```flow
let q = Point { x: 9.9, ..p }       ; copies y, z from p; overrides x
```

The `..source` must come last. Spread bypasses constructors.

#### Fulfilling interfaces

```flow
type LogEntry fulfills Serializable {
    timestamp: int,
    source: string,

    fn serialize(self): string = f"{self.timestamp}|{self.source}"
    fn byte_size(self): int = self.serialize().len()
}
```

#### Generic types

```flow
type Pair<A, B> {
    first: A,
    second: B
}

type SortedList<T fulfills Comparable> {
    items: array<T>
}
```

### A.5.6 Sum Type Declarations

```flow
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)
    | Triangle(base: float, height: float)

type Direction = | North | South | East | West

type Tree<T> =
    | Leaf
    | Node(value: T, left: Tree<T>, right: Tree<T>)
```

### A.5.7 Interface Declarations

```flow
interface Serializable {
    fn serialize(self): string
    fn byte_size(self): int
}
```

Interfaces contain method signatures only. No fields, no default implementations.

#### Constructor constraints

```flow
interface Parseable<T> {
    constructor from_string(raw: string): self
    fn validate(self): bool
}
```

#### Generic interfaces with bounds

```flow
interface SortedContainer<T fulfills Comparable> {
    fn insert(self, val: T): self
    fn min(self): option<T>
}
```

### A.5.8 Built-in Interfaces

| Interface | Methods |
|-----------|---------|
| `Comparable` | `fn:pure compare(self, other: self): int` |
| `Numeric` | `fn:pure negate(self): self`, `add`, `sub`, `mul` |
| `Equatable` | `fn:pure equals(self, other: self): bool` |
| `Showable` | `fn:pure to_string(self): string` |

Built-in fulfillments:

| Type | Comparable | Numeric | Equatable | Showable |
|------|:----------:|:-------:|:---------:|:--------:|
| `int` | Yes | Yes | Yes | Yes |
| `int64` | Yes | Yes | Yes | Yes |
| `float` | Yes | Yes | Yes | Yes |
| `string` | Yes | -- | Yes | Yes |
| `bool` | -- | -- | Yes | Yes |
| `char` | Yes | -- | Yes | Yes |
| `byte` | Yes | -- | Yes | Yes |

### A.5.9 Alias Declarations

```flow
alias Timestamp: int
alias UserID: string
alias Transform<T, U>: fn(stream<T>): stream<U>
```

---

## A.6 Pattern Matching

### A.6.1 `match` Syntax

```flow
let result = match expr {
    pattern1 : expr1,
    pattern2 : expr2,
    _        : default_expr
}
```

Match arms use `:` (not `=>`). Arms are evaluated in order. The first matching arm is selected.

### A.6.2 Pattern Forms

| Pattern | Syntax | Matches |
|---------|--------|---------|
| Literal | `42`, `"hello"`, `true` | Exact value equality |
| Binding | `x` | Any value; binds to `x` |
| Wildcard | `_` | Any value; no binding |
| Some | `some(v)` | `option<T>` with value; binds inner to `v` |
| None | `none` | `option<T>` absence |
| Ok | `ok(v)` | `result<T, E>` success; binds inner to `v` |
| Err | `err(e)` | `result<T, E>` failure; binds inner to `e` |
| Variant | `Circle(r)` | Sum type variant; binds fields positionally |
| Variant (no payload) | `North` | Payload-less sum type variant |
| Tuple | `(a, b)` | Tuple; binds elements to `a`, `b` |

### A.6.3 Exhaustiveness Rules

| Subject type | Exhaustiveness requirement |
|-------------|---------------------------|
| Sum type | All variants handled, or `_` present |
| `option<T>` | Both `some(v)` and `none` handled, or `_` present |
| `result<T, E>` | Both `ok(v)` and `err(e)` handled, or `_` present |
| Primitive / string | `_` required for completeness; unmatched patterns produce runtime error with compile-time warning |

### A.6.4 `if let` (Conditional Pattern Matching)

```flow
if (let some(v) = find_user(id)) {
    greet(v)
} else {
    println("not found")
}

if (let ok(data) = read_file(path)) {
    process(data)
}

if (let err(e) = validate(input)) {
    log_error(e)
}
```

`if let` desugars to `match` internally:
- `if (let some(x) = e) { ... }` becomes `match e { some(x): { ... }, none: {} }`
- `if (let ok(x) = e) { ... } else { ... }` becomes `match e { ok(x): { ... }, err(_): { ... } }`

### A.6.5 Match on Sum Types

```flow
fn area(s: Shape): float = match s {
    Circle(r)       : 3.14159 * r * r,
    Rectangle(w, h) : w * h,
    Triangle(b, h)  : 0.5 * b * h
}
```

Variant field bindings are positional, matching the order in the type declaration.

---

## A.7 Control Flow

### A.7.1 `if` / `else`

```flow
if (condition) {
    body
} else if (other_condition) {
    body
} else {
    body
}
```

`if`/`else` is an expression when both branches produce the same type:

```flow
let label = if (score >= 90) { "A" } else { "B" }
```

### A.7.2 Ternary

```flow
let x = cond ? then_val : else_val
```

### A.7.3 `while`

```flow
while (condition) {
    body
}

while (condition) {
    body
} finally {
    cleanup()
}
```

### A.7.4 `for`

```flow
for (item: int in collection) {
    process(item)
}

for (item: int in data) {
    if (item == 0) { break }
    process(item)
} finally {
    cleanup()
}
```

#### Composable `for`

In a composition chain, `for` decomposes a collection into a stream:

```flow
data -> for(x: int) -> double -> square
```

With a body, `for` produces a stream via `yield`:

```flow
data -> for(x: int) {
    yield x * 2
} -> filter(\(v: int => v > 10))
```

---

## A.8 Exception Handling

### A.8.1 Syntax

```flow
try {
    ; code that may throw
} retry function_name (ex: ExceptionType, attempts: N) {
    ; correct ex.data before retry
} catch (ex: ExceptionType) {
    ; handle after retries exhausted
} finally (? ex: Exception) {
    ; cleanup; always runs once
}
```

All blocks after `try` are optional. `retry` and `catch` may appear multiple times for different exception types.

### A.8.2 `retry` Semantics

`retry function_name` names the function to re-invoke. Inside the retry block:
- `ex.data` is mutable; modify it before the function re-runs.
- `ex.original` is always the original payload, read-only.

### A.8.3 Escalation Order

```
try -> retry (up to N times) -> catch -> finally
```

`finally` runs exactly once at termination, never between retries.

### A.8.4 Exception Types

Exception types must fulfill `Exception<T>`:

```flow
interface Exception<T> {
    fn message(self): string
    fn data(self): T
    fn original(self): T
}
```

---

## A.9 Coroutines

### A.9.1 Spawning

```flow
let gen :< producer(seed)
```

The `:<` operator spawns a stream-producing function on a new thread with a bounded channel.

### A.9.2 Coroutine Handle API

| Method | Signature | Description |
|--------|-----------|-------------|
| `.next()` | `(): option<Y>` | Blocking read; `none` when producer finished and channel drained |
| `.poll()` | `(): option<Y>` | Non-blocking read; `none` if nothing available |
| `.send(val)` | `(S): none` | Push to inbox (receivable coroutines only) |
| `.done()` | `(): bool` | `true` when producer terminated and channel drained |

### A.9.3 Receivable Coroutines

A coroutine function is receivable when its first parameter is `stream<S>`. The inbox parameter is implicit at the call site.

```flow
fn handler(inbox: stream<string>): stream<Result> {
    for (msg: string in inbox) {
        yield process(msg)
    }
}

let h :< handler()                   ; inbox auto-created
h.send("command")                    ; pushes to inbox
let r = h.next()                     ; reads from yields
```

### A.9.4 Channel Capacity

Default capacity: 64. Override with `[N]` on the stream return type:

```flow
fn producer(seed: int): stream<int>[128] {
    yield seed
}
```

Capacity is a runtime hint, not part of type identity.

### A.9.5 Coroutine Pipelines

Multiple stages can be chained in a single `:<` expression:

```flow
let result :< producer() -> transform() -> aggregate()
```

Worker pools multiply a stage:

```flow
let result :< producer() -> transform() * 5 -> aggregate()
```

### A.9.6 Streams vs. Coroutines

| Property | `stream<T>` | `let c :< fn()` |
|----------|-------------|-----------------|
| Execution | Lazy, pull-based, same thread | Eager, push-based, separate thread |
| Yield behavior | Suspends via state machine | Pushes into channel, blocks if full |
| Backpressure | Inherent (consumer drives) | Channel capacity |
| Bidirectional | No | Yes (if receivable) |

---

## A.10 Ownership and Memory

### A.10.1 Ownership Rules

| Action | Effect |
|--------|--------|
| `foo(a)` | `a` borrowed by `foo`; reverts when `foo` returns (unless `a` escapes) |
| `foo(@a)` | Copy passed; caller retains `a` |
| `return val` | Ownership transfers to caller |
| `yield val` | Ownership transfers to consumer (value types implicitly copied) |
| `yield @val` | Copy yielded; function retains `val` |

### A.10.2 Escape Rules

A value escapes when it is returned, stored inside a returned value, or yielded. After escape, the original binding is inaccessible.

### A.10.3 Mutability and Borrowing

| Param modifier | Caller constraint | Function guarantee |
|----------------|-------------------|-------------------|
| *(bare)* | Any binding | No guarantee |
| `:imut` | Any binding | Will not mutate |
| `:mut` | Must pass `:mut` binding | Mutations visible to caller |

Passing `:imut` to `:mut` is a compile error. Use `@` for a mutable copy.

### A.10.4 Parallel Safety

Mutable data cannot cross parallel fan-out or coroutine boundaries. Options:
- Transfer ownership (sender loses access).
- Copy with `@`.
- Use `snapshot()` for static values.

---

## A.11 Modules and Visibility

### A.11.1 Module Structure

```flow
module path.name

import other.module (Name)

export fn public_fn(): int = 42
fn private_fn(): int = 99
```

- Every file belongs to one module.
- Module path matches file path: `math.vector` resolves to `math/vector.flow`.
- Only `export`-marked declarations are importable.
- Circular imports are a compile error.
- Imported modules are instantiated once; all importers share the same statics.

---

## A.12 Naming Conventions

| Element | Convention | Examples |
|---------|-----------|----------|
| Primitive types | lowercase | `int`, `float`, `string`, `bool`, `byte`, `char` |
| Struct/sum types | PascalCase | `Point`, `LogEntry`, `JsonValue` |
| Sum type variants (user) | PascalCase | `Circle`, `Rectangle`, `North` |
| Built-in variants | lowercase | `some`, `none`, `ok`, `err` |
| Functions | snake\_case | `read_file`, `to_string`, `parse_row` |
| Variables | snake\_case | `total_count`, `max_value`, `port_str` |
| Modules | dot.separated.lowercase | `math.vector`, `io`, `string_builder` |
| Statics | snake\_case | `default_port`, `max_retries` |

---

## A.13 Numeric Rules

### A.13.1 Overflow and Division

| Condition | Behavior |
|-----------|----------|
| Integer overflow/underflow | Throws `OverflowError` at runtime |
| Integer division by zero | Throws `DivisionByZeroError` |
| Float division by zero | IEEE 754: `infinity`, `neg_infinity`, or `nan` |
| Float modulo by zero | Throws `DivisionByZeroError` |
| Narrowing cast out of range | Throws `OverflowError` |

### A.13.2 Numeric Conversions

All conversions are explicit via `cast<T>`:

```flow
let a: int = 100
let b: int64 = cast<int64>(a)       ; widening, always succeeds
let c: float = cast<float>(a)       ; int to float
let d: int = cast<int>(3.9)         ; truncates toward zero: 3
```

**Exception:** integers of the same signedness widen implicitly when the target is strictly wider.

```flow
let a: int = 100
let b: int64 = a                     ; implicit widening
```

Mixed signedness remains a compile error. Float-to-int and int-to-float require explicit `cast`.

---

## A.14 Equality and Structural Compatibility

| Operator | Name | Semantics |
|----------|------|-----------|
| `==` | Equality | Field-by-field value comparison |
| `===` | Congruence | Same field names and field types (structural shape) |
| `coerce(expr)` | Structural assignment | Field-by-field copy to target type; types must be congruent |

`coerce` does not invoke constructors.

---

## A.15 Standard Library Summary

### A.15.1 `array<T>` API

| Function | Signature |
|----------|-----------|
| `array.push<T>` | `(arr: array<T>, val: T): array<T>` |
| `array.get_any<T>` | `(arr: array<T>, idx: int): T?` |
| `array.size<T>` | `(arr: array<T>): int` |
| `array.concat<T>` | `(a: array<T>, b: array<T>): array<T>` |
| `array.get` | `(arr: array<string>, idx: int): string?` |
| `array.len` | `(arr: array<int>): int` |

### A.15.2 `map<K, V>` API

| Function | Signature |
|----------|-----------|
| `map.new<V>` | `(): map<string, V>` |
| `map.get<V>` | `(m: map<string, V>, key: string): V?` |
| `map.set<V>` | `(m: map<string, V>, key: string, val: V): map<string, V>` |
| `map.remove<V>` | `(m: map<string, V>, key: string): map<string, V>` |
| `map.has<V>` | `(m: map<string, V>, key: string): bool` |
| `map.keys<V>` | `(m: map<string, V>): array<string>` |
| `map.values<V>` | `(m: map<string, V>): array<V>` |
| `map.len<V>` | `(m: map<string, V>): int64` |

### A.15.3 `set<T>` API

| Function | Signature |
|----------|-----------|
| `set.new` | `(): set<T>` |
| `set.from` | `(items: array<T>): set<T>` |
| `s.has` | `(val: T): bool` |
| `s.add` | `(val: T): set<T>` |
| `s.remove` | `(val: T): set<T>` |
| `s.union` | `(other: set<T>): set<T>` |
| `s.intersect` | `(other: set<T>): set<T>` |
| `s.difference` | `(other: set<T>): set<T>` |
| `s.len` | `(): int` |

### A.15.4 `buffer<T>` API

| Function | Signature |
|----------|-----------|
| `buffer.new` | `(): buffer<T>` |
| `buffer.collect` | `(s: stream<T>): buffer<T>` |
| `buffer.with_capacity` | `(n: int): buffer<T>` |
| `buf.push` | `(val: T)` |
| `buf.drain` | `(): stream<T>` |
| `buf.len` | `(): int` |
| `buf.get` | `(i: int): option<T>` |
| `buf.sort_by` | `(f: fn(T, T): int)` |
| `buf.reverse` | `()` |
| `buf.slice` | `(start: int, end: int): buffer<T>` |

### A.15.5 `stream<T>` Helpers

| Function | Signature |
|----------|-----------|
| `stream.chunks` | `(n: int): stream<buffer<T>>` |
| `stream.group_by` | `(f: fn(T): K): stream<(K, buffer<T>)>` |
| `stream.take` | `(n: int): stream<T>` |
| `stream.skip` | `(n: int): stream<T>` |
| `stream.zip<U>` | `(other: stream<U>): stream<(T, U)>` |
| `stream.flatten<U>` | `(): stream<U>` (where `T` is `stream<U>` or `array<U>`) |
| `stream.map<U>` | `(f: fn(T): U): stream<U>` |
| `stream.filter` | `(pred: fn(T): bool): stream<T>` |
| `stream.reduce<U>` | `(init: U, f: fn(U, T): U): U` |

### A.15.6 `collection<K, V>` Interface

```flow
interface collection<K, V> {
    fn get(self, key: K): option<V>
    fn set(self, key: K, val: V): self
    fn keys(self): stream<K>
    fn values(self): stream<V>
    fn has(self, key: K): bool
    fn len(self): int
}
```

---

## A.16 Escape Sequences (Complete)

| Sequence | Character |
|----------|-----------|
| `\n` | Newline (U+000A) |
| `\t` | Tab (U+0009) |
| `\r` | Carriage return (U+000D) |
| `\\` | Backslash |
| `\"` | Double quote |
| `\'` | Single quote |
| `\0` | Null (U+0000) |
| `\{` | Literal `{` (in f-strings) |
| `\u{XXXX}` | Unicode scalar by hex codepoint |

---

## A.17 Reserved Words and Future Considerations

The following identifiers are reserved as keywords even if not yet fully implemented. Using them as identifiers is a compile error:

`alias`, `native`, `record`, `typeof`, `retry`

---

## A.18 Grammar Summary (Informal)

This is an informal EBNF sketch, not a formal grammar. It covers the most common productions.

```
module      ::= module_decl import* decl*
module_decl ::= 'module' dotted_name
import      ::= 'import' dotted_name ( '(' name (',' name)* ')' )?
              | 'import' dotted_name 'as' IDENT

decl        ::= fn_decl | type_decl | interface_decl | alias_decl
fn_decl     ::= 'export'? 'fn' (':pure')? IDENT type_params? '(' params ')' ':' type_expr
                ( '=' expr | block ) ('finally' block)?
type_decl   ::= 'export'? 'type' IDENT type_params? ('fulfills' type_list)?
                '{' field_decl* method* constructor* static_member* '}'
              | 'export'? 'type' IDENT type_params? '='
                ('|' variant_decl)+
interface_decl ::= 'export'? 'interface' IDENT type_params?
                   '{' fn_sig* constructor_sig? '}'
alias_decl  ::= 'export'? 'alias' IDENT type_params? ':' type_expr

type_expr   ::= named_type | generic_type | fn_type | tuple_type
              | type_expr '?' | type_expr ':mut' | type_expr ':imut'
              | type_expr '[' expr ']'

expr        ::= literal | IDENT | expr '.' IDENT | expr '(' args ')'
              | expr '[' expr ']' | expr binop expr | unop expr
              | '\(' params '=>' expr ')' | expr '?' expr ':' expr
              | 'if' '(' expr ')' block ('else' (block | if_expr))?
              | 'match' expr '{' match_arm (',' match_arm)* '}'
              | 'cast' '<' type_expr '>' '(' expr ')'
              | '@' expr | expr '?' | expr '??' expr
              | expr '->' expr | '(' expr ('|' expr)+ ')'
              | 'some' '(' expr ')' | 'ok' '(' expr ')' | 'err' '(' expr ')'
              | type_name '{' field_init (',' field_init)* (',' '..' expr)? '}'
              | '[' (expr (',' expr)*)? ']' | '(' expr ',' expr (',' expr)* ')'

stmt        ::= 'let' IDENT (':' type_expr)? '=' expr
              | target '=' expr | target '+=' expr | target '-=' expr
              | target '*=' expr | target '/=' expr
              | target '++' | target '--'
              | 'return' expr? | 'yield' expr
              | 'break' | 'continue' | 'throw' expr
              | 'if' '(' expr ')' block ('else' (block | if_stmt))?
              | 'while' '(' expr ')' block ('finally' block)?
              | 'for' '(' IDENT ':' type_expr 'in' expr ')' block ('finally' block)?
              | 'match' expr '{' match_arm+ '}'
              | try_stmt | expr

try_stmt    ::= 'try' block retry_block* catch_block* finally_block?
retry_block ::= 'retry' IDENT '(' IDENT ':' type_expr (',' 'attempts' ':' expr)? ')' block
catch_block ::= 'catch' '(' IDENT ':' type_expr ')' block
finally_block ::= 'finally' ('(' '?' IDENT ':' type_expr ')')? block

pattern     ::= '_' | literal | IDENT | 'some' '(' IDENT ')' | 'none'
              | 'ok' '(' IDENT ')' | 'err' '(' IDENT ')'
              | IDENT '(' IDENT (',' IDENT)* ')' | '(' pattern (',' pattern)* ')'

match_arm   ::= pattern ':' (expr | block)
```
