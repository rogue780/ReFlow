# Chapter 6: Data Structures

The programs in the preceding chapters have used only the built-in types:
integers, floats, booleans, strings, arrays. Real programs need types that
model the problem domain --- patients, invoices, network packets, abstract
syntax trees. This chapter covers how Flow lets you define your own types,
control their construction, and combine them into data that the type system
can reason about.

Flow has three ways to define a named type: **struct types** with named
fields and methods, **sum types** whose values are exactly one of several
variants, and **type aliases** that give a new name to an existing type.
It also has **records** for anonymous structural data. Together these cover
the full range from domain objects with invariants to throwaway intermediate
values in a pipeline.

---

## 6.1 Defining Types

### 6.1.1 Fields and Methods

A type definition introduces a new named type with fields and, optionally,
methods:

```flow
module geometry

import io (println)
import math (sqrt)

type Point {
    x: float,
    y: float,

    fn distance_to(self, other: Point): float {
        let dx = self.x - other.x
        let dy = self.y - other.y
        return sqrt(dx * dx + dy * dy)
    }

    fn magnitude(self): float {
        return sqrt(self.x * self.x + self.y * self.y)
    }
}

fn main() {
    let a = Point { x: 3.0, y: 4.0 }
    let b = Point { x: 0.0, y: 0.0 }
    println(f"a = ({a.x}, {a.y})")
    println(f"distance: {a.distance_to(b)}")
    println(f"magnitude: {a.magnitude()}")
}
```

```
$ flow run geometry.flow
a = (3.0, 4.0)
distance: 5.0
magnitude: 5.0
```

The `type` keyword introduces the name. Inside the braces: fields, then
methods. Fields have a name and a type, separated by a colon. Fields are
separated by commas. Methods are ordinary functions defined inside the type
body.

There is no inheritance in Flow. Types do not extend other types. If you
want shared behavior, use interfaces (Chapter 11) or composition --- put
one type inside another as a field. This is a deliberate restriction.
Inheritance hierarchies are a well-known source of coupling; Flow avoids
them entirely.

A struct literal constructs a value of the type. Every field must be
specified, in any order:

```flow
let p = Point { x: 3.0, y: 4.0 }
let q = Point { y: 0.0, x: 1.0 }   ; order does not matter
```

Omitting a field is a compile error. There are no default values. This
seems strict, but it eliminates a class of bugs where a forgotten field
silently gets a zero or null value. If a type has ten fields, every
construction site names all ten. When you add an eleventh field later, the
compiler flags every site that needs updating.

Field access uses dot syntax:

```flow
let px: float = p.x
let py: float = p.y
```

Types can contain other types as fields. There is no limit to nesting:

```flow
type Line {
    start: Point,
    end_point: Point,

    fn length(self): float = self.start.distance_to(self.end_point)
}

let segment = Line {
    start: Point { x: 0.0, y: 0.0 },
    end_point: Point { x: 3.0, y: 4.0 },
}
println(f"length: {segment.length()}")   ; 5.0
```

### 6.1.2 The `self` Parameter

Methods take `self` as their first parameter. Nothing is implicitly
injected --- `self` is an ordinary parameter whose type is the enclosing
type. It gives the method access to the instance's fields.

```flow
type Circle {
    radius: float,

    fn area(self): float = 3.14159 * self.radius * self.radius

    fn circumference(self): float = 2.0 * 3.14159 * self.radius

    fn scale(self, factor: float): Circle {
        return Circle { radius: self.radius * factor }
    }
}
```

Methods are called with dot syntax. The receiver goes before the dot; the
remaining arguments go in the parentheses:

```flow
let c = Circle { radius: 5.0 }
let a = c.area()              ; 78.53975
let big = c.scale(2.0)       ; Circle { radius: 10.0 }
```

Because `self` is just a function parameter, methods also participate in
composition chains. The two calls below are identical:

```flow
let a1 = c.area()            ; method call syntax
let a2 = c -> area           ; composition syntax
```

This is not a special rule for methods. It is the general composition
rule from Chapter 4: the value on the left becomes the first argument of
the function on the right. Since `self` is the first argument, composition
works naturally.

A method that returns a new value of the same type enables chaining:

```flow
let result = Circle { radius: 1.0 }
    .scale(2.0)
    .scale(3.0)
    .area()
; result is the area of a circle with radius 6.0
```

Notice that `scale` returns a new `Circle` rather than modifying the
existing one. This is the idiomatic pattern in Flow: methods on immutable
types are transformations that produce new values. The original is
unchanged. This plays well with Flow's ownership model (Chapter 8) and
makes method chains easy to reason about --- each step produces a fresh
value that feeds into the next.

### 6.1.3 Per-Field Mutability

Fields are immutable by default. Individual fields may be declared `:mut`,
allowing their values to change after construction:

```flow
module counter

import io (println)

type Counter {
    name: string,
    value: int:mut,

    fn increment(self) {
        self.value++
    }

    fn reset(self) {
        self.value = 0
    }
}

fn main() {
    let c: Counter:mut = Counter { name: "clicks", value: 0 }
    c.increment()
    c.increment()
    c.increment()
    println(f"{c.name}: {c.value}")
    c.reset()
    println(f"{c.name}: {c.value}")
}
```

```
$ flow run counter.flow
clicks: 3
clicks: 0
```

Two conditions must both be met for mutation to succeed:

1. The field must be declared `:mut` in the type definition.
2. The binding that holds the instance must be declared `:mut`.

If the field is `:mut` but the binding is not, mutation is a compile error.
If the binding is `:mut` but the field is not, mutation is also a compile
error. Both gates must open.

```flow
type Record {
    id: int,
    status: string:mut,
}

let r1 = Record { id: 1, status: "pending" }
; r1.status = "done"     ; compile error: r1 is not :mut

let r2: Record:mut = Record { id: 2, status: "pending" }
r2.status = "done"       ; ok: binding is :mut and field is :mut
; r2.id = 3              ; compile error: id is not :mut
```

This two-level design is deliberate. The field declaration says what *can*
change. The binding declaration says what *will* change in this particular
scope. A function that receives a `Record` (without `:mut`) gets a
read-only view of the entire value, even the `:mut` fields. Mutation is
confined to where you explicitly allow it.

Note the asymmetry: `:imut` (immutable) is the default and accepts any
binding. `:mut` requires an explicit `:mut` binding. This means you can
always pass a mutable value to a function that expects an immutable one ---
the function simply cannot mutate it. But you cannot pass an immutable
value to a function that expects a mutable one. The type system prevents
the mutation, not a runtime check.

A practical consequence: when designing a type, mark only the fields that
genuinely need to change as `:mut`. Leave everything else immutable. This
gives callers the most flexibility --- they can pass your type to functions
that do not need mutation without any conversion or copying. The more
fields you mark `:mut`, the more tightly coupled your type becomes to
mutable usage patterns.

---

## 6.2 Constructors

### 6.2.1 Validation Gates

Types may define one or more named constructors. A constructor is a
function that validates its inputs and returns an instance of the type:

```flow
module age

import io (println)

type Age {
    value: int,

    constructor new(n: int): Age {
        if (n < 0) {
            throw "age cannot be negative"
        }
        if (n > 150) {
            throw "age unrealistic"
        }
        return Age { value: n }
    }
}

fn main() {
    let a = Age.new(25)
    println(f"age: {a.value}")
}
```

```
$ flow run age.flow
age: 25
```

Constructors are called through the type name with dot syntax:
`Age.new(25)`. Inside the constructor body, literal construction (`Age {
value: n }`) is available --- this is the only place where the struct
literal is permitted once a constructor exists.

The constructor must return the type it is defined on. The return type
annotation (`: Age`) is explicit and required. The body is an ordinary
function body: it can declare local variables, call other functions, throw
exceptions, and use all the control flow from Chapters 3 and 5. The only
special thing about a constructor is the restriction it places on
construction outside the type.

### 6.2.2 When Constructors Are Required

The rule is absolute: if a type defines *any* constructor, direct literal
construction is forbidden outside the type body. All instances must go
through a constructor.

```flow
type Email {
    address: string,

    constructor parse(raw: string): Email {
        ; simplified validation
        if (!raw.contains("@")) {
            throw "invalid email: missing @"
        }
        return Email { address: raw }
    }
}

let valid = Email.parse("alice@example.com")    ; ok
; let bad = Email { address: "not-an-email" }   ; compile error: must use constructor
```

This is how Flow enforces invariants at the type level. If `Email` always
has an `@` sign, the proof is in the constructor. No code path can create
an `Email` without going through that check. The type name becomes a
guarantee: if you have an `Email`, it passed validation.

The flip side: if a type has no constructors, literal construction is
freely available. Not every type needs validation. A `Point` with `x` and
`y` fields has no invariant to protect --- any pair of floats is valid. Do
not add constructors just because you can. Add them when there is a
constraint to enforce.

```flow
; No constructor needed: all field combinations are valid
type Point { x: float, y: float }
let p = Point { x: 3.0, y: 4.0 }    ; direct construction, fine

; Constructor needed: not all strings are valid emails
type Email {
    address: string,
    constructor parse(raw: string): Email { ... }
}
let e = Email.parse("alice@example.com")   ; must go through constructor
```

### 6.2.3 Multiple Constructors

A type can define as many constructors as it needs. Each has a distinct
name and can accept different parameters:

```flow
type Color {
    r: int,
    g: int,
    b: int,

    constructor rgb(r: int, g: int, b: int): Color {
        if (r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255) {
            throw "color components must be 0-255"
        }
        return Color { r: r, g: g, b: b }
    }

    constructor hex(code: string): Color {
        ; parse hex string into r, g, b
        ; ...
        return Color { r: r, g: g, b: b }
    }

    constructor grayscale(level: int): Color {
        return Color.rgb(level, level, level)
    }
}

let red = Color.rgb(255, 0, 0)
let white = Color.grayscale(255)
```

Constructors can call other constructors. `grayscale` delegates to `rgb`,
which means the range check runs for grayscale values too. This is the
right pattern: put validation in one constructor and have others route
through it.

A more realistic example --- a type representing log entries with multiple
input formats:

```flow
type LogEntry {
    timestamp: int,
    source: string,
    level: string,

    constructor from_raw(ts: int, src: string, lvl: string): LogEntry {
        if (lvl != "DEBUG" && lvl != "INFO" && lvl != "WARN" && lvl != "ERROR") {
            throw f"invalid log level: {lvl}"
        }
        return LogEntry { timestamp: ts, source: src, level: lvl }
    }

    constructor from_string(raw: string): LogEntry {
        let parts: array<string> = raw.split("|")
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

Both constructors feed through `from_raw`, which validates the level. The
`from_string` constructor handles parsing; it does not duplicate the
validation logic. If you later add a new valid level, you change one
constructor.

---

## 6.3 Static Members

Static members belong to the type, not to any instance. They are declared
with the `static` keyword inside the type body and accessed through the
type name:

```flow
module config

import io (println)

type AppConfig {
    static version: string = "2.1.0",
    static max_retries: int = 3,
    static debug: bool:mut = false,

    name: string,
}

fn main() {
    println(f"version: {AppConfig.version}")
    println(f"max retries: {AppConfig.max_retries}")

    AppConfig.debug = true
    println(f"debug mode: {AppConfig.debug}")
}
```

```
$ flow run config.flow
version: 2.1.0
max retries: 3
debug mode: true
```

Static fields can be mutable (`:mut`) or immutable. Mutable statics are
shared state: any code with access to the type can read and write them.

There is one important property of statics across modules. When two modules
import the same type, they share the same static values. The module is
instantiated once; all importers see the same statics. This is explicit ---
you know it is happening because you see `TypeName.field` --- but it is
shared mutable state. Treat it with discipline:

```flow
; file: settings.flow
module settings

export type DB {
    static host: string:mut = "localhost",
    static port: int:mut = 5432,
}
```

```flow
; file: server.flow
module server
import settings (DB)

fn connect_string(): string {
    return f"postgres://{DB.host}:{DB.port}"
}
```

```flow
; file: admin.flow
module admin
import settings (DB)

fn override_host(h: string) {
    DB.host = h    ; server.flow sees this change
}
```

Both `server` and `admin` import `DB`. They get the same `DB.host` and
`DB.port`. When `admin` changes the host, `server` reads the new value.
This is by design, but it requires the same care you would give any shared
mutable state in a concurrent program.

Statics are not global variables. They are namespaced under a type name,
and they are only accessible to code that imports that type. But within
that scope, they are shared. Use immutable statics for constants
(`version`, `max_retries`). Use mutable statics sparingly and only when
you genuinely need cross-module shared state --- configuration overrides,
feature flags, counters. For anything more complex, pass data explicitly
through function parameters.

Note that functions which read or write mutable statics are not pure.
They cannot be marked `pure`, and they cannot be used inside parallel
fan-out expressions (`<:(a | b)`). This is another reason to prefer
immutable statics: they do not restrict how your functions can be composed.

---

## 6.4 Struct Spread (`..`)

When you need a modified copy of a struct, listing every field is tedious
and fragile. The spread operator `..` copies all unspecified fields from an
existing value:

```flow
module spread_demo

import io (println)

type User {
    name: string,
    age: int,
    email: string,
    active: bool,
}

fn main() {
    let alice = User {
        name: "Alice",
        age: 30,
        email: "alice@example.com",
        active: true,
    }

    ; create a copy with only the age changed
    let older = User { age: 31, ..alice }

    println(f"{older.name}, age {older.age}")
    println(f"email: {older.email}")
    println(f"active: {older.active}")
}
```

```
$ flow run spread_demo.flow
Alice, age 31
email: alice@example.com
active: true
```

The explicitly named fields take precedence. Everything else comes from the
spread source. The `..source` must appear last in the field list.

Spread creates a new value. The original is unchanged:

```flow
let deactivated = User { active: false, ..alice }
; alice.active is still true
; deactivated.active is false
```

You can override multiple fields at once:

```flow
let updated = User { age: 31, email: "alice@newhost.com", ..alice }
```

Spread is particularly useful for immutable update patterns. Instead of
making fields mutable and modifying them in place, create a new value with
just the changed fields:

```flow
fn promote_user(u: User): User {
    return User { active: true, ..u }
}

fn rename_user(u: User, new_name: string): User {
    return User { name: new_name, ..u }
}
```

Each function returns a new `User`. The original is untouched. This
pattern scales well: a type with twenty fields can be "updated" by naming
only the one or two fields that change. When you add a new field to the
type later, spread-based code does not need to change --- it automatically
copies the new field from the source.

### Spread Bypasses Constructors

This is the most important thing to know about spread. If the type has
constructors, spread does **not** invoke them. It copies field values
directly, with no validation.

```flow
type PositiveInt {
    value: int,

    constructor new(n: int): PositiveInt {
        if (n <= 0) { throw "must be positive" }
        return PositiveInt { value: n }
    }
}

let good = PositiveInt.new(42)
; This bypasses the constructor — no validation
let bad = PositiveInt { value: -1, ..good }   ; no error at construction
```

Spread is a trusted operation for internal copies. If validation matters,
go through the constructor explicitly. Use spread for convenience when you
know the invariants are preserved --- for instance, when changing a field
that has no constraint, or when copying between values that were already
validated.

The guideline: use spread inside the module that owns the type, where you
understand the invariants. Expose constructors to external callers who
should not bypass validation. This division is natural in Flow's module
system --- code inside the module has access to spread; code outside uses
the public constructors.

---

## 6.5 Sum Types

A sum type defines a value that is exactly one of several named variants.
Where a struct says "this value has all of these fields," a sum type says
"this value is one of these alternatives."

If you have used enums in C, Java, or TypeScript, sum types will feel
familiar but more powerful. Unlike enums, variants can carry data --- each
variant can hold different fields of different types. If you have used
Rust's `enum` or Haskell's algebraic data types, Flow's sum types work
the same way with slightly different syntax.

### 6.5.1 Defining Variants

```flow
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)
    | Triangle(base: float, height: float)
```

Each variant has a name and, optionally, data. `Circle` carries one float.
`Rectangle` carries two. A variant can also carry no data at all:

```flow
type Direction =
    | North
    | South
    | East
    | West
```

Variants without data are called unit variants. They function like
enumeration values in other languages.

Constructing a sum type value uses the variant name directly:

```flow
let s: Shape = Circle(5.0)
let d: Direction = North
let r: Shape = Rectangle(4.0, 6.0)
```

The type of `s` is `Shape`, not `Circle`. A `Shape` variable can hold any
variant. You cannot declare a variable as `Circle` --- the individual
variants are not types. `Shape` is the type; `Circle`, `Rectangle`, and
`Triangle` are its values.

### 6.5.2 Matching Sum Types

The only way to inspect which variant a sum type holds is `match`. A match
expression branches on the variant and destructures its data:

```flow
module shapes

import io (println)

type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)
    | Triangle(base: float, height: float)

fn area(s: Shape): float {
    match s {
        Circle(r): 3.14159 * r * r,
        Rectangle(w, h): w * h,
        Triangle(b, h): 0.5 * b * h,
    }
}

fn describe(s: Shape): string {
    match s {
        Circle(r): f"circle with radius {r}",
        Rectangle(w, h): f"{w} x {h} rectangle",
        Triangle(b, h): f"triangle ({b} base, {h} height)",
    }
}

fn main() {
    let shapes: array<Shape> = [
        Circle(5.0),
        Rectangle(4.0, 6.0),
        Triangle(3.0, 8.0),
    ]

    for (s: Shape in shapes) {
        println(f"{describe(s)}: area = {area(s)}")
    }
}
```

```
$ flow run shapes.flow
circle with radius 5.0: area = 78.53975
4.0 x 6.0 rectangle: area = 24.0
triangle (3.0 base, 8.0 height): area = 12.0
```

In each arm of the match, the variant's fields are bound to local names.
`Circle(r)` binds the radius to `r`. `Rectangle(w, h)` binds width to `w`
and height to `h`. These names are scoped to the arm --- they do not leak
into surrounding code. You can use `_` within a pattern to ignore a field
you do not need:

```flow
fn width_if_rect(s: Shape): float {
    match s {
        Rectangle(w, _): w,
        _: 0.0,
    }
}
```

Match expressions return a value. Every arm must produce the same type.
The compiler uses the match as an expression when it appears in a position
that expects a value --- as the right-hand side of a `let` binding, as a
return value, or as a function argument.

### 6.5.3 Exhaustiveness

The compiler requires that every variant appears in a `match`, or that a
wildcard `_` covers the remaining cases. Missing a variant is a compile
error:

```flow
fn bad_area(s: Shape): float {
    match s {
        Circle(r): 3.14159 * r * r,
        Rectangle(w, h): w * h,
        ; compile error: Triangle not handled
    }
}
```

The wildcard `_` matches anything not explicitly listed:

```flow
fn is_round(s: Shape): bool {
    match s {
        Circle(_): true,
        _: false,
    }
}
```

Use `_` deliberately. If you add a new variant to `Shape` later, matches
with explicit arms will produce compile errors --- telling you exactly
which code needs updating. Matches with `_` will silently accept the new
variant. Both behaviors are useful; choose the one that fits.

The general guideline: use exhaustive matching (no `_`) when the logic
truly depends on every variant. Use `_` when you are testing for one or
two specific variants and everything else gets the same treatment. In the
`is_round` example above, `_` is the right choice --- we only care about
circles. In `area`, exhaustive matching is correct because every variant
needs its own formula.

### 6.5.4 Enum-Style Sum Types

Unit variants (no data) make sum types work like enumerations:

```flow
module directions

import io (println)

type Direction =
    | North
    | South
    | East
    | West

fn opposite(d: Direction): Direction {
    match d {
        North: South,
        South: North,
        East: West,
        West: East,
    }
}

fn name(d: Direction): string {
    match d {
        North: "north",
        South: "south",
        East: "east",
        West: "west",
    }
}

fn main() {
    let d = North
    println(f"{name(d)} -> opposite: {name(opposite(d))}")
}
```

```
$ flow run directions.flow
north -> opposite: south
```

There is no separate `enum` keyword in Flow. Sum types with unit variants
fill that role. The advantage is uniformity: the same `match` syntax works
whether the variants carry data or not.

### 6.5.5 Mixed Variants

A single sum type can mix data-carrying and unit variants:

```flow
type Token =
    | Number(value: float)
    | Plus
    | Minus
    | Star
    | Slash
    | LeftParen
    | RightParen
    | End
```

This is common in parsers, protocol handlers, and state machines. The
data-carrying variants hold payloads; the unit variants are signals.
Matching works the same way --- data-carrying arms destructure, unit arms
do not:

```flow
fn is_operator(t: Token): bool {
    match t {
        Plus: true,
        Minus: true,
        Star: true,
        Slash: true,
        _: false,
    }
}
```

### 6.5.6 Recursive Sum Types

Sum types can refer to themselves, which makes them natural for tree-shaped
data:

```flow
module linked_list

import io (println)

type IntList =
    | Cons(head: int, tail: IntList)
    | Nil

fn sum(list: IntList): int {
    match list {
        Nil: 0,
        Cons(h, t): h + sum(t),
    }
}

fn length(list: IntList): int {
    match list {
        Nil: 0,
        Cons(_, t): 1 + length(t),
    }
}

fn main() {
    let list = Cons(1, Cons(2, Cons(3, Cons(4, Nil))))
    println(f"sum: {sum(list)}")
    println(f"length: {length(list)}")
}
```

```
$ flow run linked_list.flow
sum: 10
length: 4
```

The `Nil` variant is the base case. `Cons` holds a value and a reference to
the rest of the list. Pattern matching drives the recursion: each match on
`Cons(h, t)` peels off one element and recurses on the tail.

Recursive sum types are the standard way to represent tree-shaped data in
Flow: syntax trees, file system hierarchies, JSON documents, nested
menus. The base variant (`Nil`, `Leaf`, `Empty`) terminates the
recursion. The recursive variant (`Cons`, `Node`) references the type
itself. Every function over such a type follows the same structure: match
on the variant, handle the base case directly, and recurse on the
sub-structure.

### 6.5.7 Generic Sum Types

Sum types can be parameterized:

```flow
type Tree<T> =
    | Leaf
    | Node(value: T, left: Tree<T>, right: Tree<T>)

fn depth<T>(t: Tree<T>): int {
    match t {
        Leaf: 0,
        Node(_, l, r): 1 + max(depth(l), depth(r)),
    }
}
```

The type parameter `T` is substituted at each use site. `Tree<int>` is a
tree of integers; `Tree<string>` is a tree of strings. The `depth` function
is generic over any element type because it never inspects the values ---
it only cares about the tree structure.

You have already seen two generic sum types in earlier chapters without
necessarily recognizing them as such: `option<T>` is a sum type with
variants `some(T)` and `none`. `result<T, E>` is a sum type with variants
`ok(T)` and `err(E)`. Chapter 7 covers these in detail. The point here is
that they are not special language primitives --- they are sum types with
the same semantics as any sum type you define yourself.

---

## 6.6 Records

A `record` is an anonymous structural type with named fields. Records need
no type declaration:

```flow
let row: record = { name: "Alice", age: 30, active: true }
let name: string = row.name
let age: int = row.age
```

Records are structurally typed. Two records with the same field names and
types are compatible regardless of where they were created:

```flow
let a: record = { x: 1, y: 2 }
let b: record = { x: 10, y: 20 }
; a and b have the same type: { x: int, y: int }
```

Records are useful for intermediate pipeline data, parsed rows, and
ad-hoc groupings where defining a named type would be overhead for a value
that only lives for a few lines. They are immutable by default, like
everything else in Flow.

The trade-off is clear: records are convenient but anonymous. They have
no constructors, no methods, no validation. They cannot fulfill
interfaces. They are the throwaway containers --- use them for intermediate
data in a pipeline, for parsed rows before they become domain objects,
for grouping a few related values that do not merit a full type definition.
For anything that crosses a module boundary, has invariants, or needs
behavior, use a named type.

---

## 6.7 Type Aliases

An alias gives a distinct name to an existing type. Unlike a type
abbreviation in some languages, a Flow alias is **not** interchangeable
with its underlying type without explicit conversion:

```flow
module physics

import io (println)

alias Meters: float
alias Seconds: float
alias MetersPerSecond: float

fn speed(d: Meters, t: Seconds): MetersPerSecond {
    return d / t
}

fn main() {
    let d: Meters = Meters.from(100.0)
    let t: Seconds = Seconds.from(9.58)
    let v: MetersPerSecond = speed(d, t)
    println(f"speed: {v.value()} m/s")
}
```

```
$ flow run physics.flow
speed: 10.438413... m/s
```

`Meters.from(100.0)` wraps a `float` in the `Meters` alias.
`v.value()` unwraps it back to the underlying `float`. These conversions
are explicit: you cannot pass a bare `float` where a `Meters` is expected,
and you cannot pass a `Meters` where a `Seconds` is expected, even though
both wrap `float`.

This is **dimensional typing**. It catches a class of bugs at compile time
that unit tests often miss --- swapping arguments that happen to share a
primitive type.

```flow
let d: Meters = Meters.from(100.0)
let t: Seconds = Seconds.from(9.58)

; speed(t, d)     ; compile error: Seconds is not Meters
; speed(100.0, t) ; compile error: float is not Meters
```

Aliases can also wrap function types:

```flow
alias Transform<T, U>: fn(stream<T>): stream<U>
```

This is convenient for pipelines where the same function signature appears
repeatedly.

Aliases have zero runtime cost. At the machine level, a `Meters` value is
a `float`. The distinction exists only at compile time, where it catches
type errors. This makes aliases cheap to use --- sprinkle them freely
wherever you have two parameters of the same primitive type that mean
different things.

A word of caution: aliases are distinct types, not subtypes. You cannot
add two `Meters` values directly because `+` is defined on `float`, not
`Meters`. You would need to unwrap, add, and re-wrap. For types that need
arithmetic or other operations, consider using a struct with a single field
and appropriate methods instead of an alias. Aliases are best for values
that are constructed, passed around, and eventually unwrapped --- not for
values that participate in complex expressions.

---

## 6.8 Coerce

When two types have the same fields --- the same names and the same types
--- they are **structurally congruent**. Flow's `===` operator checks
congruence at runtime. The `coerce` function converts a value from one
congruent type to another:

```flow
module coerce_demo

import io (println)

type InputData { x: int, y: int }
type OutputData { x: int, y: int }

type Transformer {
    x: int:mut,
    y: int:mut,

    fn scale(self, factor: int) {
        self.x *= factor
        self.y *= factor
    }
}

fn main() {
    let input = InputData { x: 3, y: 4 }

    ; coerce InputData to Transformer (same fields: x, y)
    let t: Transformer:mut = coerce(input)
    t.scale(10)

    ; coerce Transformer back to OutputData
    let output: OutputData = coerce(t)
    println(f"result: ({output.x}, {output.y})")
}
```

```
$ flow run coerce_demo.flow
result: (30, 40)
```

`coerce` performs a field-by-field copy. The target type is inferred from
the binding's type annotation. The source and target must be structurally
congruent --- same field names, same field types. If they are not, the
compiler rejects the coerce with an error.

Two important properties:

1. **Coerce does not invoke constructors.** If the target type has
   constructors and validation matters, use the constructor explicitly.

2. **Coerce copies methods from the target type.** After coercing
   `InputData` to `Transformer`, the result has `Transformer`'s `scale`
   method. The data comes from the source; the behavior comes from the
   target.

Coerce is most useful in pipeline architectures where data passes through
several processing stages, each modeled as a different type with its own
methods but the same underlying fields. Consider a data processing
pipeline:

```flow
type RawRecord { id: int, value: int }
type ValidatedRecord { id: int, value: int, fn check(self): bool { ... } }
type OutputRecord { id: int, value: int, fn format(self): string { ... } }
```

Data enters as `RawRecord`, gets coerced to `ValidatedRecord` for
checking, then coerced to `OutputRecord` for formatting. The field layout
is the same throughout; the methods change at each stage. This is a
lightweight alternative to inheritance hierarchies for staged processing.

The congruence check is strict. Extra fields, missing fields, or fields
with different types all cause compile errors:

```flow
type A { x: int, y: int }
type B { x: int, y: float }    ; y is float, not int
type C { x: int, y: int, z: int }   ; extra field z

let a = A { x: 1, y: 2 }
; let b: B = coerce(a)  ; compile error: y types differ
; let c: C = coerce(a)  ; compile error: C has field z that A lacks
```

---

## 6.9 Arrays and Maps

Flow has two built-in collection types that appear in nearly every program.
They were briefly introduced in earlier chapters; here we cover them
properly.

### 6.9.1 Arrays

An `array<T>` is an ordered, fixed-size, immutable sequence:

```flow
let nums: array<int> = [1, 2, 3, 4, 5]
let names: array<string> = ["alice", "bob", "carol"]
let empty: array<int> = []
```

All elements must be the same type. A heterogeneous literal is a compile
error.

Arrays are immutable. Operations that appear to modify an array return a
new one:

```flow
import array (push, get, len)

let a: array<int> = [1, 2, 3]
let b: array<int> = array.push(a, 4)    ; [1, 2, 3, 4] — a is unchanged
```

Element access returns `option<T>` because the index might be out of
bounds:

```flow
let first: int? = array.get_int(nums, 0)     ; some(1)
let bad: int? = array.get_int(nums, 99)      ; none
let safe: int = array.get_int(nums, 0) ?? 0  ; 1
```

The `for` loop iterates over array elements directly:

```flow
for (name: string in names) {
    println(name)
}
```

Arrays of any element type --- including user-defined sum types and
structs --- work with the generic `array.push<T>` and `array.get_any<T>`
functions. The compiler handles the underlying boxing automatically.

### 6.9.2 Maps

A `map<K, V>` is a key-value collection. Keys must be hashable (all
primitives and strings qualify):

```flow
import map (new, set, get, has, keys)

let scores: map<string, int> = map.new()
let scores2 = map.set(scores, "alice", 95)
let scores3 = map.set(scores2, "bob", 87)

let alice: int? = map.get(scores3, "alice")   ; some(95)
let carol: int? = map.get(scores3, "carol")   ; none
let safe: int = map.get(scores3, "carol") ?? 0  ; 0
```

Like arrays, maps are immutable by default. `map.set` returns a new map;
the original is unchanged. For a mutable map:

```flow
let scores: map<string, int>:mut = map.new()
scores.insert("alice", 95)
scores.insert("bob", 87)
```

Iterating over map keys:

```flow
let ks: array<string> = map.keys(scores)
for (k: string in ks) {
    let v: int = map.get(scores, k) ?? 0
    println(f"{k}: {v}")
}
```

Maps pair naturally with the types defined in this chapter. A
`map<string, User>` stores users by name. A `map<string, Shape>` stores
shapes by identifier. The generic value-type support means you can use
`int`, `float`, or `bool` as values without extra ceremony.

Both arrays and maps return `option<T>` from their access functions.
This is a recurring pattern in Flow: any operation that might fail returns
an option or a result instead of crashing. Chapter 7 covers the full
range of techniques for working with optional values --- `match`,
`if let`, `??`, and the `?` propagation operator. For now, `??` with a
default value is sufficient for most collection access.

---

## 6.10 Putting It Together

Here is a larger example that combines struct types, sum types, methods,
constructors, and collections:

```flow
module inventory

import io (println)
import array (push, get_any, size)
import map (new, set, get, keys)

type Money {
    cents: int,

    constructor from_dollars(d: float): Money {
        if (d < 0.0) { throw "price cannot be negative" }
        return Money { cents: cast<int>(d * 100.0) }
    }

    fn dollars(self): float = cast<float>(self.cents) / 100.0

    fn add(self, other: Money): Money {
        return Money { cents: self.cents + other.cents }
    }
}

type ItemKind =
    | Physical(weight_grams: int)
    | Digital
    | Service(hours: float)

type Item {
    name: string,
    kind: ItemKind,
    price: Money,

    fn describe(self): string {
        let kind_str = match self.kind {
            Physical(w): f"physical ({w}g)",
            Digital: "digital",
            Service(h): f"service ({h}h)",
        }
        return f"{self.name} [{kind_str}]: ${self.price.dollars()}"
    }
}

fn total_price(items: array<Item>): Money {
    let sum: Money:mut = Money { cents: 0 }
    for (item: Item in items) {
        sum = sum.add(item.price)
    }
    return sum
}

fn main() {
    let items: array<Item> = [
        Item {
            name: "Keyboard",
            kind: Physical(450),
            price: Money.from_dollars(79.99),
        },
        Item {
            name: "E-Book",
            kind: Digital,
            price: Money.from_dollars(14.99),
        },
        Item {
            name: "Consulting",
            kind: Service(2.0),
            price: Money.from_dollars(200.0),
        },
    ]

    for (item: Item in items) {
        println(item.describe())
    }

    let total = total_price(items)
    println(f"total: ${total.dollars()}")
}
```

```
$ flow run inventory.flow
Keyboard [physical (450g)]: $79.99
E-Book [digital]: $14.99
Consulting [service (2.0h)]: $200.0
total: $294.98
```

This program uses all the tools from this chapter:

- `Money` is a struct with a constructor that rejects negative prices and
  a method that formats the value as dollars.
- `ItemKind` is a sum type with three variants: physical items have weight,
  digital items have no extra data, and services have hours.
- `Item` is a struct that contains a sum type field (`kind`) and a struct
  field (`price`). Its `describe` method uses `match` to format the kind.
- `total_price` iterates over an array of items, accumulating a total.

The types work together to make illegal states unrepresentable: you cannot
create a `Money` with a negative amount, and every `Item` has exactly one
kind. The compiler enforces this at every call site.

This is the central design principle behind Flow's type system: encode
your constraints in types, and let the compiler enforce them. A `Money`
value is not "an int that we hope is non-negative" --- it is a value that
has provably passed the constructor's check. An `ItemKind` is not "a
string that might be physical, digital, or service" --- it is exactly one
of three variants, and the compiler ensures your code handles all of them.

The pattern extends naturally. As your program grows, you add more types,
each with its own invariants. The compiler becomes your safety net: it
catches missing match arms when you add a variant, missing fields when you
extend a struct, and type mismatches when you pass the wrong thing. This
is the payoff for the strictness you have seen throughout this chapter.

---

## 6.11 What Goes Wrong

### Missing Fields

```flow
type Point { x: float, y: float }

let p = Point { x: 3.0 }
; compile error: missing field 'y' in Point literal
```

Every field must be specified. There are no defaults and no optional fields.
If you want a field that might be absent, give it an `option<T>` type and
pass `none` explicitly.

### Direct Construction When Constructors Exist

```flow
type Age {
    value: int,
    constructor new(n: int): Age { ... }
}

let a = Age { value: 25 }
; compile error: type Age has constructors; use Age.new()
```

Once any constructor is defined, literal construction outside the type body
is forbidden.

### Non-Exhaustive Match

```flow
type Color = | Red | Green | Blue

fn name(c: Color): string {
    match c {
        Red: "red",
        Green: "green",
        ; compile error: Blue not handled
    }
}
```

Add the missing variant or use `_` to cover the rest.

### Mutation Without `:mut`

```flow
type Counter { value: int:mut }

let c = Counter { value: 0 }
c.value = 1
; compile error: cannot mutate field on immutable binding 'c'
```

The binding must be `:mut` to mutate even `:mut` fields:

```flow
let c: Counter:mut = Counter { value: 0 }
c.value = 1    ; ok
```

### Wrong Variant Data

```flow
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)

let s = Circle(5.0, 3.0)
; compile error: Circle takes 1 argument, got 2
```

Each variant's argument count and types must match its definition.
Similarly, passing a `string` where a variant expects a `float` is a type
error. The variant fields have types just like struct fields.

### Coercing Non-Congruent Types

```flow
type A { x: int, y: int }
type B { x: int, z: int }    ; z, not y

let a = A { x: 1, y: 2 }
let b: B = coerce(a)
; compile error: types A and B are not structurally congruent
```

The field names must match exactly. Renaming a field breaks congruence.

### Spread with Wrong Source Type

```flow
type Point { x: float, y: float }
type Color { r: int, g: int, b: int }

let p = Point { x: 1.0, y: 2.0 }
let c = Color { r: 0, ..p }
; compile error: cannot spread Point into Color
```

The spread source must be the same type as the value being constructed
(or structurally congruent). You cannot spread unrelated types into each
other.

---

## 6.12 Summary

This chapter introduced Flow's type definition facilities:

- **Struct types** group named fields and methods. Fields are immutable by
  default; individual fields can be marked `:mut`. Methods take explicit
  `self` and work with both dot syntax and composition chains.
- **Constructors** are named functions that validate inputs and return
  instances. When any constructor exists, literal construction is disabled.
- **Static members** are type-level fields shared across all code that
  imports the type.
- **Struct spread** (`..`) creates modified copies. It bypasses constructors.
- **Sum types** define values that are exactly one of several variants.
  Pattern matching with `match` is the only way to inspect them. The
  compiler enforces exhaustiveness.
- **Records** are anonymous structural types for intermediate data.
- **Type aliases** give distinct names to existing types, preventing
  accidental interchange.
- **Coerce** converts between structurally congruent types via field-by-field
  copy.
- **Arrays** and **maps** are the built-in collections. Both are immutable
  by default.

Chapter 7 covers absence and failure: `option<T>` for values that might
not exist, `result<T, E>` for operations that might fail, and the
exception model for genuinely exceptional conditions.

---

## Exercises

**1.** Define a `BankAccount` type with fields `owner: string`,
`balance: int` (stored in cents), and `account_id: string`. Add a
constructor `open` that rejects negative initial balances. Add a
`deposit` method and a `withdraw` method. `withdraw` should throw if the
withdrawal would make the balance negative. Write a `main` function that
creates an account, makes several deposits and withdrawals, and prints
the final balance.

**2.** Define a `Shape` sum type with variants `Circle(radius: float)`,
`Rectangle(width: float, height: float)`, and `Square(side: float)`.
Write two functions: `area(s: Shape): float` and
`perimeter(s: Shape): float`. Write a `main` that creates one of each
shape, computes both area and perimeter, and prints the results.

**3.** Define a linked list as a sum type:

```flow
type IntList =
    | Cons(head: int, tail: IntList)
    | Nil
```

Write the following functions: `sum(list: IntList): int`,
`length(list: IntList): int`, `contains(list: IntList, target: int): bool`,
and `reverse(list: IntList): IntList`. Test them in `main`.

**4.** Build an expression tree:

```flow
type Expr =
    | Num(value: int)
    | Add(left: Expr, right: Expr)
    | Mul(left: Expr, right: Expr)
```

Write `fn eval(e: Expr): int` that recursively evaluates the expression.
Write `fn show(e: Expr): string` that produces a parenthesized string
representation (e.g., `"(1 + (2 * 3))"`). Test with the expression
`Add(Num(1), Mul(Num(2), Num(3)))`, which should evaluate to 7 and display
as `"(1 + (2 * 3))"`.

**5.** Use struct spread to implement an immutable update pattern. Define
a `Config` type with fields `host: string`, `port: int`,
`timeout_ms: int`, and `verbose: bool`. Write a function
`fn with_production_defaults(c: Config): Config` that returns a new
`Config` with `host` set to `"production.example.com"` and `verbose` set
to `false`, keeping the other fields from the input. Write a `main`
function that creates a development config, applies the production
defaults, and prints both configs to show the original is unchanged.

**6.** Define type aliases `alias Celsius: float` and
`alias Fahrenheit: float`. Write conversion functions
`fn to_fahrenheit(c: Celsius): Fahrenheit` and
`fn to_celsius(f: Fahrenheit): Celsius`. Verify that passing a raw `float`
or the wrong alias to either function is a compile error.

**7.** Build a simple calculator using sum types. Define a `Token` type:

```flow
type Token =
    | Number(value: float)
    | Plus
    | Minus
    | Star
    | Slash
```

Write a function `fn apply(op: Token, left: float, right: float): float`
that applies the given operator to the two operands, throwing for
`Number` (which is not an operator). Write a `main` function that
evaluates `3.0 + 4.0 * 2.0` by calling `apply` twice and printing the
result.

**8.** Design a small contact book using structs and maps. Define a
`Contact` type with fields `name: string`, `email: string`, and
`phone: string`. Write functions `add_contact`, `find_by_name` (returning
`Contact?`), and `list_all` that works with a `map<string, Contact>`.
Write a `main` function that adds several contacts, looks one up by name,
and lists all contacts.
