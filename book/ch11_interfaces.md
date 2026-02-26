# Chapter 11: Interfaces and Contracts

Every type you have built so far stands alone. A `Color` struct has fields and methods, but there is no way to say "any type that can convert itself to a string" or "any type that supports comparison." You write concrete types and concrete functions that accept those types. This works until you write your second container, your second serializer, your second sorting algorithm --- and realize the logic is identical, differing only in which methods it calls on the elements.

Interfaces solve this. An interface declares a set of method signatures without implementing them. A type that provides implementations for every method in the interface *fulfills* that interface. Generic functions can then accept any type that fulfills a given interface, and the compiler verifies at each call site that the concrete type satisfies the contract.

Flow's interfaces are simple. There is no inheritance hierarchy, no default implementations, no dynamic dispatch. A type either fulfills an interface or it does not. The compiler checks statically. The cost at runtime is zero.

---

## 11.1 Defining Interfaces

An interface is a named collection of method signatures. It contains no fields, no data, and no function bodies.

### 11.1.1 Method Signatures

```flow
interface Printable {
    fn to_string(self): string
}
```

This declares an interface named `Printable` with a single method: `to_string`, which takes `self` (the implementing type) and returns a `string`. Any type that fulfills `Printable` must provide a `to_string` method with exactly this signature.

Interfaces can require multiple methods. Separate them with commas or newlines:

```flow
interface Describable {
    fn name(self): string,
    fn describe(self): string
}
```

Or equivalently, one method per line:

```flow
interface Describable {
    fn name(self): string
    fn describe(self): string
}
```

Both forms are identical to the compiler. Use whichever reads better for the number of methods involved.

The `self` parameter is special. It refers to whatever concrete type fulfills the interface. When you write `fn to_string(self): string` inside an interface, and a type `Color` fulfills that interface, the method signature becomes `fn to_string(self: Color): string`. You do not write the type of `self` explicitly --- the interface abstracts over it.

The `self` keyword can also appear in non-receiver positions:

```flow
interface Combinable {
    fn combine(self, other: self): self
}
```

Here, `other: self` means "a second value of the same type as the receiver," and the return type `self` means "returns a value of the implementing type." When `int` fulfills `Combinable`, the concrete signature is `fn combine(self: int, other: int): int`.

Methods can take additional parameters of any type:

```flow
interface Encoder {
    fn encode(self, format: string): array<byte>,
    fn size_estimate(self): int
}
```

### 11.1.2 Constructor Constraints

Interfaces can require that a type provide specific constructors:

```flow
interface Parseable<T> {
    constructor from_string(raw: string): self
    fn validate(self): bool
}
```

The `constructor` keyword declares a factory method. The `self` return type means "returns an instance of whatever type fulfills this interface." A type fulfilling `Parseable` must provide a `from_string` constructor that parses a raw string and produces an instance of itself.

Constructor constraints are useful when generic code needs to create instances of unknown types. Without them, a generic function can manipulate values but never construct new ones:

```flow
fn parse_and_validate<T fulfills Parseable>(raw: string): option<T> {
    let val: T = T.from_string(raw)
    if (val.validate()) {
        return some(val)
    }
    return none
}
```

The expression `T.from_string(raw)` is valid because the `Parseable` interface guarantees the constructor exists.

### 11.1.3 Pure Methods in Interfaces

An interface can require that a method be pure:

```flow
interface Hashable {
    fn:pure hash(self): int
}
```

Any type fulfilling `Hashable` must implement `hash` as a `fn:pure` function. The compiler enforces this: if the implementing method performs I/O, mutates external state, or calls impure functions, it is a compile error.

Pure interface methods guarantee that calling the method has no side effects, which is critical for interfaces used in hash maps, sorted containers, and concurrent code:

```flow
interface Transform<T, U> {
    fn:pure apply(self, input: T): U
}
```

Any type fulfilling `Transform` must provide a deterministic `apply` that produces the same output for the same input, every time.

---

## 11.2 Fulfilling Interfaces

A type declares that it fulfills an interface with the `fulfills` keyword in its type declaration. The compiler then verifies that every method in the interface is present with the correct signature.

```flow
type Color fulfills Printable {
    r: int, g: int, b: int

    fn to_string(self): string {
        return f"rgb({self.r}, {self.g}, {self.b})"
    }
}
```

The `Color` type declares fields `r`, `g`, `b` and provides a `to_string` method matching the `Printable` interface. The compiler checks that the method exists, that it takes `self` as the first parameter, and that it returns `string`. If any of these are wrong, compilation fails.

A type can fulfill multiple interfaces by listing them after `fulfills`, separated by commas:

```flow
type Temperature fulfills Printable, Describable {
    celsius: float

    fn to_string(self): string = f"{self.celsius} C"

    fn name(self): string = "Temperature"

    fn describe(self): string {
        if (self.celsius < 0.0) {
            return "freezing"
        } else if (self.celsius < 20.0) {
            return "cold"
        } else if (self.celsius < 30.0) {
            return "warm"
        }
        return "hot"
    }
}
```

All methods from all listed interfaces must be present. Miss one and the compiler tells you which method is missing and which interface requires it.

### Fulfilling Pure Interface Methods

When an interface requires a pure method, the implementing method must also be pure:

```flow
type Pixel fulfills Hashable {
    x: int, y: int

    fn:pure hash(self): int = self.x * 31 + self.y
}
```

Drop the `fn:pure` annotation and the compiler rejects it: the `Hashable` interface requires `hash` to be pure. This is not optional. Purity on an interface method is a contract, not a suggestion.

### What Happens When You Get It Wrong

Missing a method is a compile error:

```flow
interface Measurable {
    fn length(self): int,
    fn width(self): int
}

type Box fulfills Measurable {
    l: int, w: int, h: int

    fn length(self): int = self.l
    // compile error: type 'Box' does not implement 'width' required by 'Measurable'
}
```

Wrong return type is also a compile error:

```flow
type BadBox fulfills Measurable {
    l: int, w: int

    fn length(self): int = self.l
    fn width(self): string = f"{self.w}"
    // compile error: method 'width' returns 'string', expected 'int'
}
```

The errors are specific. They name the type, the interface, the method, and the mismatch. You never have to guess which contract you violated.

---

## 11.3 Built-In Interfaces

Flow provides four interfaces that exist without any `interface` declaration in user code. The compiler registers them and fulfills them automatically for the built-in primitive types. You never write `type int fulfills Comparable` --- the compiler does that for you.

### 11.3.1 `Comparable`

```flow
interface Comparable {
    fn:pure compare(self, other: self): int
}
```

The `compare` method returns a negative integer if `self` is less than `other`, zero if they are equal, and a positive integer if `self` is greater. This single method enables all four comparison operators: `<`, `>`, `<=`, `>=`.

When a type fulfills `Comparable`, you can compare instances with the standard operators:

```flow
type Score fulfills Comparable {
    value: int

    fn:pure compare(self, other: Score): int {
        return self.value - other.value
    }
}

fn main() {
    let a = Score { value: 85 }
    let b = Score { value: 92 }
    if (a < b) {
        println("a is lower")
    }
}
```

The compiler translates `a < b` into a call to `a.compare(b)` and checks whether the result is negative. You write the comparison once, and all four operators work.

`Comparable` is fulfilled automatically by `int`, `int64`, `float`, `string` (lexicographic ordering), `char` (Unicode scalar ordering), and `byte`.

The primary use of `Comparable` is as a bound on generic functions:

```flow
fn max<T fulfills Comparable>(a: T, b: T): T {
    if (a > b) { return a }
    return b
}

fn min<T fulfills Comparable>(a: T, b: T): T {
    if (a < b) { return a }
    return b
}
```

These work with any type that fulfills `Comparable` --- integers, floats, strings, or your own types.

### 11.3.2 `Numeric`

```flow
interface Numeric {
    fn:pure negate(self): self
    fn:pure add(self, other: self): self
    fn:pure sub(self, other: self): self
    fn:pure mul(self, other: self): self
}
```

`Numeric` enables the arithmetic operators `+`, `-`, `*`, and unary `-`. It is fulfilled by `int`, `int64`, and `float`. Notably, `string` and `bool` do not fulfill `Numeric`.

Use it to write generic arithmetic:

```flow
fn:pure sum<T fulfills Numeric>(values: array<T>, zero: T): T {
    let acc: T:mut = zero
    for (v: T in values) {
        acc = acc + v
    }
    return acc
}

fn main() {
    let ints = [1, 2, 3, 4, 5]
    println(f"sum: {sum(ints, 0)}")

    let floats = [1.5, 2.5, 3.0]
    println(f"sum: {sum(floats, 0.0)}")
}
```

Notice the `zero` parameter. `Numeric` intentionally omits a `zero()` factory method. Functions that need a zero value accept it as an explicit parameter rather than conjuring one from the type. This is a deliberate design choice: not every numeric-like type has an obvious zero, and an explicit parameter avoids magical defaults.

### 11.3.3 `Equatable`

```flow
interface Equatable {
    fn:pure equals(self, other: self): bool
}
```

`Equatable` enables the `==` and `!=` operators. It is fulfilled by `int`, `int64`, `float`, `string`, `bool`, `char`, and `byte`.

For user-defined types, fulfilling `Equatable` lets you use `==` and `!=`:

```flow
type Point fulfills Equatable {
    x: int, y: int

    fn:pure equals(self, other: Point): bool {
        return self.x == other.x && self.y == other.y
    }
}

fn main() {
    let a = Point { x: 1, y: 2 }
    let b = Point { x: 1, y: 2 }
    let c = Point { x: 3, y: 4 }
    println(f"a == b: {a == b}")  // true
    println(f"a == c: {a == c}")  // false
    println(f"a != c: {a != c}")  // true
}
```

A generic function that needs equality:

```flow
fn contains<T fulfills Equatable>(items: array<T>, target: T): bool {
    for (item: T in items) {
        if (item == target) { return true }
    }
    return false
}
```

### 11.3.4 `Showable`

```flow
interface Showable {
    fn:pure to_string(self): string
}
```

`Showable` enables conversion to a human-readable string. It is what makes string interpolation work. When you write `f"value: {x}"`, the compiler calls `x.to_string()` to produce the string representation. All primitive types fulfill `Showable`.

`Showable` also enables auto-coercion in string concatenation. When one operand of `+` is a `string` and the other fulfills `Showable`, the compiler inserts a `.to_string()` call automatically:

```flow
let count = 42
let msg = "count: " + count  // "count: 42"
```

For user-defined types:

```flow
type Color fulfills Showable {
    r: int, g: int, b: int

    fn:pure to_string(self): string {
        return f"({self.r}, {self.g}, {self.b})"
    }
}

fn main() {
    let c = Color { r: 255, g: 128, b: 0 }
    println(f"color: {c}")  // color: (255, 128, 0)
}
```

Once `Color` fulfills `Showable`, it works everywhere strings are expected: interpolation, concatenation, generic printing functions.

A generic function that displays any `Showable` value:

```flow
fn display<T fulfills Showable>(label: string, value: T): none {
    println(f"{label}: {value}")
}

fn main() {
    display("count", 42)
    display("pi", 3.14159)
    display("name", "Flow")
}
```

### Built-In Fulfillment Table

Not every primitive type fulfills every interface. Here is the complete table:

| Type | Comparable | Numeric | Equatable | Showable |
|------|:---:|:---:|:---:|:---:|
| `int` | yes | yes | yes | yes |
| `int64` | yes | yes | yes | yes |
| `float` | yes | yes | yes | yes |
| `string` | yes (lexicographic) | --- | yes | yes (identity) |
| `bool` | --- | --- | yes | yes |
| `char` | yes (Unicode scalar) | --- | yes | yes |
| `byte` | yes | --- | yes | yes |

A few things to notice. `bool` is not `Comparable` --- there is no meaningful ordering of `true` and `false`. `string` is not `Numeric` --- you cannot multiply strings. `byte` is `Comparable` but not `Numeric` --- you can order bytes but Flow does not provide arithmetic on them through this interface.

### 11.3.5 `collection<K, V>`

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

`collection` is a generic interface for containers. The standard library types `map<K, V>`, `array<T>` (as `collection<int, T>`), and `buffer<T>` implement it. The six methods provide a uniform API for reading, writing, iterating, and querying size.

`get` returns `option<V>`. An absent key returns `none`, not an exception. This is consistent with Flow's approach to missing values: `option` makes absence explicit and forces the caller to handle it.

The `self` return type on `set` means the method returns a value of the implementing type. For immutable collections, `set` returns a new collection with the updated value. For mutable collections, it returns the same collection after mutation.

Generic functions over collections:

```flow
fn count_entries<K, V>(c: collection<K, V>): int {
    return c.len()
}

fn has_key<K, V>(c: collection<K, V>, key: K): bool {
    return c.has(key)
}
```

These work with any type that fulfills `collection`, whether it is a standard `map`, an `array`, or a custom type you define yourself.

---

## 11.4 Generic Interfaces

Interfaces can be parameterized with type variables, just like types and functions:

```flow
interface Container<T> {
    fn get(self, index: int): option<T>,
    fn len(self): int
}
```

A type fulfilling a generic interface specifies the concrete type:

```flow
type IntStack fulfills Container<int> {
    items: array<int>

    fn get(self, index: int): option<int> {
        if (index >= 0 && index < array.length(self.items)) {
            return some(self.items[index])
        }
        return none
    }

    fn len(self): int = array.length(self.items)
}
```

The type parameter `T` is replaced with `int` throughout. The compiler checks that every method signature matches with `T = int`.

### Bounded Type Parameters on Interfaces

Interface type parameters can carry bounds:

```flow
interface SortedContainer<T fulfills Comparable> {
    fn insert(self, val: T): self,
    fn min(self): option<T>,
    fn max(self): option<T>
}
```

Any type fulfilling `SortedContainer` must supply a concrete type for `T` that itself fulfills `Comparable`. This is checked at the fulfillment site:

```flow
type SortedInts fulfills SortedContainer<int> {
    // ok: int fulfills Comparable
    items: array<int>

    fn insert(self, val: int): SortedInts {
        // insert in sorted order
        let result: array<int>:mut = []
        let inserted: bool:mut = false
        for (item: int in self.items) {
            if (!inserted && val < item) {
                array.push(result, val)
                inserted = true
            }
            array.push(result, item)
        }
        if (!inserted) {
            array.push(result, val)
        }
        return SortedInts { items: result }
    }

    fn min(self): option<int> {
        if (array.length(self.items) == 0) { return none }
        return some(self.items[0])
    }

    fn max(self): option<int> {
        if (array.length(self.items) == 0) { return none }
        return some(self.items[array.length(self.items) - 1])
    }
}
```

If you tried `SortedContainer<bool>`, the compiler would reject it: `bool` does not fulfill `Comparable`.

### Generic Methods Inside Generic Interfaces

An interface can have methods with their own type parameters, independent of the interface's parameters:

```flow
interface Mappable<T> {
    fn map<U>(self, f: fn(T): U): Mappable<U>
}
```

The `map` method introduces its own type parameter `U`. The implementing type must provide a `map` that works for any `U` the caller chooses. This is the pattern behind functors in functional programming, expressed as a straightforward interface.

---

## 11.5 Equality and Congruence

Flow provides two distinct equality-like operators that serve different purposes.

### 11.5.1 `==` (Value Equality)

The `==` operator performs field-by-field value comparison. Two values of the same type are equal if every field is equal:

```flow
type Point { x: int, y: int }

fn main() {
    let a = Point { x: 1, y: 2 }
    let b = Point { x: 1, y: 2 }
    let c = Point { x: 3, y: 4 }

    println(f"a == b: {a == b}")  // true: same field values
    println(f"a == c: {a == c}")  // false: different values
}
```

`a` and `b` are distinct values --- they were constructed separately --- but `==` returns `true` because their fields have the same values. This is value equality, not identity. Flow does not have reference identity in the pointer sense.

For primitive types, `==` does what you expect: `42 == 42` is `true`, `"hello" == "hello"` is `true`, `3.14 == 3.14` is `true`.

Value equality also works across congruent types --- types with the same field names and field types:

```flow
type LogEntry { timestamp: int, source: string }
type EventRecord { source: string, timestamp: int }

fn main() {
    let log = LogEntry { timestamp: 100, source: "us-east-1" }
    let event = EventRecord { source: "us-east-1", timestamp: 100 }

    println(f"log == event: {log == event}")  // true: same field values
}
```

Field order does not matter. What matters is that the field names and types match, and the values are equal.

### 11.5.2 `===` (Structural Congruence)

The `===` operator checks whether two values have the same *structure* --- the same field names and field types. It does not compare field values. It does not compare methods. It checks shape.

```flow
type LogEntry { timestamp: int, source: string }
type EventRecord { source: string, timestamp: int }
type MetricPoint { timestamp: int, value: float }

fn main() {
    let a = LogEntry { timestamp: 100, source: "us-east-1" }
    let b = EventRecord { source: "west-2", timestamp: 200 }
    let c = MetricPoint { timestamp: 100, value: 3.14 }

    println(f"a === b: {a === b}")  // true: same field names and types
    println(f"a === c: {a === c}")  // false: MetricPoint has 'value', not 'source'
}
```

`a === b` is `true` even though the field values are completely different. Both types have fields `timestamp: int` and `source: string`. The structure matches.

`a === c` is `false` because `MetricPoint` has a `value: float` field instead of `source: string`. The structures differ.

### When to Use Which

Use `==` when you care about values: "are these two points the same location?" "does this key match?"

Use `===` when you care about shape: "can I safely coerce one type to another?" "do these two records have compatible fields?" Congruence is most useful as a guard before structural assignment with `coerce`:

```flow
type InputData { x: int, y: int }
type ProcessedData { x: int, y: int }

fn process(input: InputData): ProcessedData {
    // safe: InputData and ProcessedData are congruent
    return coerce(input)
}
```

The `coerce` function performs a field-by-field copy from one type to another. It is a compile error if the types are not congruent. The `===` operator lets you check congruence at runtime when the types are not known statically.

---

## 11.6 Interface Constraints on Generics

The real power of interfaces is in generic code. Without an interface bound, a generic type parameter `T` is opaque --- you can pass it around and return it, but you cannot do anything with it. Interface bounds unlock operations.

### Single Bounds

```flow
fn:pure stringify<T fulfills Showable>(items: array<T>): string {
    let parts: array<string>:mut = []
    for (item: T in items) {
        array.push(parts, item.to_string())
    }
    return string.join(parts, ", ")
}

fn main() {
    let nums = [1, 2, 3]
    println(stringify(nums))  // 1, 2, 3

    let words = ["hello", "world"]
    println(stringify(words))  // hello, world
}
```

The bound `T fulfills Showable` guarantees that `.to_string()` is available on every element. Without the bound, calling `.to_string()` on a `T` would be a compile error.

### Multiple Bounds

When a type parameter needs to satisfy more than one interface, parenthesize the bounds:

```flow
fn find_max_display<T fulfills (Comparable, Showable)>(items: array<T>): string {
    let best: T:mut = items[0]
    for (item: T in items) {
        if (item > best) {
            best = item
        }
    }
    return best.to_string()
}
```

The parentheses are required. Without them, `<T fulfills Comparable, Showable>` would declare two type parameters: `T` bounded by `Comparable`, and an unbounded parameter named `Showable`. This is the disambiguation rule from Chapter 3: parentheses group bounds on one parameter; no parentheses means the comma separates parameters.

```flow
// Two parameters: T bounded by Comparable, U unbounded
fn wrap<T fulfills Comparable, U>(a: T, b: U): T = a

// One parameter with two bounds
fn process<T fulfills (Comparable, Showable)>(a: T): string {
    return a.to_string()
}
```

### Bounds on Type Declarations

Interface bounds work on type declarations too:

```flow
type Box<T fulfills Showable> {
    value: T

    fn display(self): none {
        println(f"Box({self.value})")
    }
}
```

The bound is checked when the type is instantiated:

```flow
let b = Box<int> { value: 42 }  // ok: int fulfills Showable
b.display()  // Box(42)
```

### Bounds on Interface Declarations

Even interfaces can have bounded type parameters, as shown with `SortedContainer` earlier:

```flow
interface Transformer<T fulfills Parseable> {
    fn transform(self, input: T): T
}
```

Any type fulfilling `Transformer` must supply a concrete type for `T` that fulfills `Parseable`.

### Bounds and Type Aliases

```flow
alias Sortable<T fulfills Comparable>: array<T>

fn sort<T fulfills Comparable>(items: Sortable<T>): Sortable<T> {
    // sort the array
    // ...
    return items
}
```

---

## 11.7 The Exception Interface

Chapter 7 covered exceptions from the perspective of throwing and catching. Here is the interface that makes it all work:

```flow
interface Exception<T> {
    fn message(self): string
    fn data(self): T
    fn original(self): T
}
```

Every exception type in Flow fulfills `Exception<T>` for some `T`. The `message` method returns a human-readable description. The `data` method returns the payload that caused the failure --- and this payload is mutable inside `retry` blocks, allowing recovery strategies to modify the data before retrying. The `original` method returns the original, unmodified payload from the moment the exception was thrown.

Defining an exception type is the same as fulfilling any other interface:

```flow
type ParseError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string

    constructor from_raw(m: string, p: string): ParseError {
        return ParseError {
            msg: m,
            payload: p,
            original_payload: p
        }
    }

    fn message(self): string { return self.msg }
    fn data(self): string { return self.payload }
    fn original(self): string { return self.original_payload }
}
```

The compiler verifies that `ParseError` provides all three methods required by `Exception<string>`. The constructor is separate from the interface --- `Exception` does not require any particular constructor --- but it is conventional to provide one.

---

## 11.8 Custom Collections

The `collection<K, V>` interface lets you build custom containers that plug into generic code. Here is a complete example: a bounded buffer that acts as a fixed-size ring buffer.

```flow
type RingBuffer<T> fulfills collection<int, T> {
    items: array<T>,
    capacity: int,
    count: int

    constructor new(cap: int): RingBuffer<T> {
        return RingBuffer<T> {
            items: [],
            capacity: cap,
            count: 0
        }
    }

    fn get(self, key: int): option<T> {
        if (key < 0 || key >= self.count) {
            return none
        }
        return some(self.items[key])
    }

    fn set(self, key: int, val: T): RingBuffer<T> {
        // If at capacity, drop the oldest element
        let new_items: array<T>:mut = self.items
        if (self.count >= self.capacity) {
            // remove first element, append new one
            new_items = array.slice(self.items, 1, array.length(self.items))
            array.push(new_items, val)
            return RingBuffer<T> {
                items: new_items,
                capacity: self.capacity,
                count: self.capacity
            }
        }
        array.push(new_items, val)
        return RingBuffer<T> {
            items: new_items,
            capacity: self.capacity,
            count: self.count + 1
        }
    }

    fn keys(self): stream<int> {
        let i: int:mut = 0
        while (i < self.count) {
            yield i
            i++
        }
    }

    fn values(self): stream<T> {
        for (item: T in self.items) {
            yield item
        }
    }

    fn has(self, key: int): bool {
        return key >= 0 && key < self.count
    }

    fn len(self): int = self.count
}
```

Because `RingBuffer` fulfills `collection<int, T>`, it works with any generic function that accepts a `collection`:

```flow
fn print_all<K, V fulfills Showable>(c: collection<K, V>): none {
    for (v: V in c.values()) {
        println(v.to_string())
    }
}

fn main() {
    let buf: RingBuffer<string>:mut = RingBuffer<string>.new(3)
    buf = buf.set(0, "first")
    buf = buf.set(1, "second")
    buf = buf.set(2, "third")
    buf = buf.set(3, "fourth")  // drops "first"

    println(f"length: {buf.len()}")  // 3
    print_all(buf)  // second, third, fourth
}
```

The `RingBuffer` type handles the bookkeeping of fixed-size storage. The `collection` interface provides the contract that lets it participate in generic code alongside `map`, `array`, and any other type that fulfills the same interface.

---

## 11.9 Static Dispatch

Flow interfaces use static dispatch. When you write a generic function with an interface bound and call it with a concrete type, the compiler knows the exact type at the call site. There is no virtual method table, no runtime lookup, no boxing.

```flow
fn max<T fulfills Comparable>(a: T, b: T): T {
    if (a > b) { return a }
    return b
}

fn main() {
    let m = max(3, 7)  // compiler generates code for max<int>
}
```

When the compiler processes `max(3, 7)`, it infers `T = int`, verifies that `int` fulfills `Comparable`, and generates code equivalent to a non-generic function that compares two integers. There is no indirection. The cost is the same as if you had written a specialized `max_int` function.

This means interfaces are a compile-time mechanism. They constrain what code you can write and guarantee that the methods exist, but they add nothing to the runtime. The generated code is as fast as hand-specialized code.

The trade-off is that you cannot have a variable of "any type that fulfills Comparable" at runtime without knowing the concrete type. Flow does not have interface-typed variables or dynamic dispatch. If you need to store values of different types in the same container and dispatch on them at runtime, use a sum type:

```flow
type Value =
    | IntVal(n: int)
    | StrVal(s: string)
    | FloatVal(f: float)
```

Sum types are the tool for runtime polymorphism. Interfaces are the tool for compile-time polymorphism. Choose the right one for the job.

---

## 11.10 Putting It Together

Here is a larger example that combines interfaces, generics, and the built-in interfaces into a small statistics library:

```flow
module stats

import io (println)

type Stats fulfills Showable {
    count: int,
    total: float,
    minimum: float,
    maximum: float

    fn:pure to_string(self): string {
        let avg: float = self.total / cast<float>(self.count)
        return f"count={self.count}, min={self.minimum}, max={self.maximum}, avg={avg}"
    }
}

fn:pure compute_stats(values: array<float>): Stats {
    let n = array.length(values)
    let total: float:mut = 0.0
    let lo: float:mut = values[0]
    let hi: float:mut = values[0]

    for (v: float in values) {
        total = total + v
        if (v < lo) { lo = v }
        if (v > hi) { hi = v }
    }

    return Stats {
        count: n,
        total: total,
        minimum: lo,
        maximum: hi
    }
}

fn display<T fulfills Showable>(label: string, value: T): none {
    println(f"{label}: {value}")
}

fn main() {
    let temperatures = [22.5, 18.3, 25.1, 19.7, 30.2, 15.8, 27.4]
    let s = compute_stats(temperatures)
    display("Temperature stats", s)
}
```

Output:

```
Temperature stats: count=7, min=15.8, max=30.2, avg=22.714285714285715
```

The `Stats` type fulfills `Showable`, which means it works with any generic function that needs to display values. The `display` function does not know about `Stats` at all --- it accepts any `Showable` type. The compiler wires everything together statically.

---

## 11.11 What Goes Wrong

### Missing method implementation

```flow
interface Storable {
    fn save(self): bool,
    fn load(self): string
}

type Config fulfills Storable {
    data: string

    fn save(self): bool = true
    // compile error: type 'Config' does not implement 'load' required by 'Storable'
}
```

The fix: add the missing method.

### Method signature mismatch

```flow
interface Counter {
    fn increment(self): self
}

type MyCounter fulfills Counter {
    n: int

    fn increment(self): int = self.n + 1
    // compile error: method 'increment' returns 'int', expected 'MyCounter'
}
```

The interface says `increment` returns `self` --- meaning the implementing type. `MyCounter`'s implementation returns `int`, not `MyCounter`. The fix:

```flow
type MyCounter fulfills Counter {
    n: int

    fn increment(self): MyCounter {
        return MyCounter { n: self.n + 1 }
    }
}
```

### Interface bound not satisfied at call site

```flow
fn sort<T fulfills Comparable>(items: array<T>): array<T> {
    // ...
}

type Blob { data: array<byte> }

fn main() {
    let blobs = [Blob { data: [] }]
    sort(blobs)
    // compile error: type 'Blob' does not fulfill 'Comparable'
}
```

The fix: either implement `Comparable` on `Blob` or use a different approach. If `Blob` has no natural ordering, it should not pretend to be comparable.

### Purity violation in interface method

```flow
interface Hashable {
    fn:pure hash(self): int
}

type User fulfills Hashable {
    name: string

    fn hash(self): int {
        println(f"hashing {self.name}")  // ERROR: println is not pure
        return string.length(self.name)
    }
}
```

The `Hashable` interface requires `hash` to be `fn:pure`. The implementation calls `println`, which is impure. The fix: remove the `println` call and mark the method `fn:pure`.

---

## 11.12 Summary

Interfaces define contracts. A type fulfills an interface by implementing all its methods with the correct signatures. The compiler checks this statically --- at compile time, not at runtime.

The four built-in interfaces --- `Comparable`, `Numeric`, `Equatable`, and `Showable` --- are fulfilled automatically by primitive types and can be fulfilled by user-defined types. They enable the comparison, arithmetic, equality, and string-conversion operators respectively.

The `collection<K, V>` interface provides a uniform API for containers. Standard library types fulfill it, and custom types can too.

Generic interfaces accept type parameters. Interface bounds on generic functions, types, and other interfaces restrict type parameters to types that fulfill specific contracts. The disambiguation rule applies: `<T fulfills A, B>` declares two parameters; `<T fulfills (A, B)>` gives one parameter two bounds.

`==` compares values field by field. `===` checks structural congruence --- same field names and types, ignoring values. Use `==` for value comparisons and `===` as a guard before `coerce`.

All dispatch is static. Interfaces add no runtime cost. The compiler resolves everything at compile time and generates specialized code. For runtime polymorphism over heterogeneous types, use sum types.

Chapter 12 introduces modules: how to split a program across files, control visibility, manage imports, and use the standard library.

---

## Exercises

**1.** Define a `Serializable` interface with two methods: `serialize(self): string` and `byte_size(self): int`. Create a `Config` type with fields `host: string` and `port: int` that fulfills `Serializable`. Serialize a `Config` instance and print the result.

```flow
module ex1

import io (println)

interface Serializable {
    fn serialize(self): string,
    fn byte_size(self): int
}

type Config fulfills Serializable {
    host: string,
    port: int

    fn serialize(self): string {
        return f"{self.host}:{self.port}"
    }

    fn byte_size(self): int {
        return string.length(self.serialize())
    }
}

fn main() {
    let cfg = Config { host: "localhost", port: 8080 }
    let data = cfg.serialize()
    println(f"serialized: {data}")
    println(f"byte size: {cfg.byte_size()}")
}
```

**2.** Create a `Score` type with a `value: int` field that fulfills `Comparable`. Write a generic `sort_ascending` function that takes an `array<T fulfills Comparable>` and returns a sorted copy using insertion sort. Test it with an array of `Score` values.

```flow
module ex2

import io (println)

type Score fulfills Comparable {
    value: int

    fn:pure compare(self, other: Score): int {
        return self.value - other.value
    }
}

fn sort_ascending<T fulfills Comparable>(items: array<T>): array<T> {
    let sorted: array<T>:mut = []
    for (item: T in items) {
        // Find insertion point
        let inserted: bool:mut = false
        let result: array<T>:mut = []
        for (existing: T in sorted) {
            if (!inserted && item < existing) {
                array.push(result, item)
                inserted = true
            }
            array.push(result, existing)
        }
        if (!inserted) {
            array.push(result, item)
        }
        sorted = result
    }
    return sorted
}

fn main() {
    let scores = [
        Score { value: 85 },
        Score { value: 42 },
        Score { value: 97 },
        Score { value: 61 },
        Score { value: 73 }
    ]

    let sorted = sort_ascending(scores)
    for (s: Score in sorted) {
        println(f"{s.value}")
    }
}
```

Expected output:

```
42
61
73
85
97
```

**3.** Define a `Shape` interface with `area(self): float` and `perimeter(self): float`. Implement it on `Circle` (with a `radius` field) and `Rectangle` (with `width` and `height` fields). Write a generic function `describe_shape<T fulfills Shape>(s: T): string` that returns a formatted description. Print descriptions for several shapes.

```flow
module ex3

import io (println)
import math (sqrt)

interface Shape {
    fn area(self): float,
    fn perimeter(self): float
}

type Circle fulfills Shape {
    radius: float

    fn area(self): float = 3.14159 * self.radius * self.radius

    fn perimeter(self): float = 2.0 * 3.14159 * self.radius
}

type Rectangle fulfills Shape {
    width: float, height: float

    fn area(self): float = self.width * self.height

    fn perimeter(self): float = 2.0 * (self.width + self.height)
}

fn describe_shape<T fulfills Shape>(s: T): string {
    return f"area={s.area()}, perimeter={s.perimeter()}"
}

fn main() {
    let c = Circle { radius: 5.0 }
    let r = Rectangle { width: 3.0, height: 4.0 }

    println(f"circle: {describe_shape(c)}")
    println(f"rectangle: {describe_shape(r)}")
}
```

Expected output:

```
circle: area=78.53975, perimeter=31.4159
rectangle: area=12.0, perimeter=14.0
```

**4.** Write a generic function `print_all<T fulfills Showable>(items: array<T>): none` that prints every element of an array, one per line. Test it with arrays of integers, strings, and a custom type that fulfills `Showable`.

```flow
module ex4

import io (println)

type Coordinate fulfills Showable {
    x: float, y: float

    fn:pure to_string(self): string {
        return f"({self.x}, {self.y})"
    }
}

fn print_all<T fulfills Showable>(items: array<T>): none {
    for (item: T in items) {
        println(f"{item}")
    }
}

fn main() {
    println("integers:")
    print_all([1, 2, 3, 4, 5])

    println("strings:")
    print_all(["alpha", "beta", "gamma"])

    println("coordinates:")
    print_all([
        Coordinate { x: 1.0, y: 2.0 },
        Coordinate { x: 3.5, y: 7.2 },
        Coordinate { x: 0.0, y: 0.0 }
    ])
}
```

**5.** Implement a `SimpleMap` type that fulfills `collection<string, int>`. Use two parallel arrays --- one for keys, one for values. Implement all six methods of the `collection` interface. Write a `main` that adds entries, looks them up, iterates over keys and values, and prints the length.

```flow
module ex5

import io (println)

type SimpleMap fulfills collection<string, int> {
    map_keys: array<string>,
    map_values: array<int>

    constructor new(): SimpleMap {
        return SimpleMap { map_keys: [], map_values: [] }
    }

    fn get(self, key: string): option<int> {
        let i: int:mut = 0
        for (k: string in self.map_keys) {
            if (k == key) {
                return some(self.map_values[i])
            }
            i++
        }
        return none
    }

    fn set(self, key: string, val: int): SimpleMap {
        // Check if key already exists
        let i: int:mut = 0
        for (k: string in self.map_keys) {
            if (k == key) {
                // Update existing value
                let new_vals: array<int>:mut = self.map_values
                new_vals[i] = val
                return SimpleMap {
                    map_keys: self.map_keys,
                    map_values: new_vals
                }
            }
            i++
        }
        // Append new key-value pair
        let new_keys: array<string>:mut = self.map_keys
        let new_vals: array<int>:mut = self.map_values
        array.push(new_keys, key)
        array.push(new_vals, val)
        return SimpleMap {
            map_keys: new_keys,
            map_values: new_vals
        }
    }

    fn keys(self): stream<string> {
        for (k: string in self.map_keys) {
            yield k
        }
    }

    fn values(self): stream<int> {
        for (v: int in self.map_values) {
            yield v
        }
    }

    fn has(self, key: string): bool {
        for (k: string in self.map_keys) {
            if (k == key) { return true }
        }
        return false
    }

    fn len(self): int = array.length(self.map_keys)
}

fn main() {
    let m: SimpleMap:mut = SimpleMap.new()
    m = m.set("alice", 95)
    m = m.set("bob", 87)
    m = m.set("carol", 91)

    println(f"length: {m.len()}")
    println(f"has alice: {m.has("alice")}")
    println(f"has dave: {m.has("dave")}")

    if (let some(score) = m.get("bob")) {
        println(f"bob's score: {score}")
    }

    println("keys:")
    for (k: string in m.keys()) {
        println(f"  {k}")
    }

    println("values:")
    for (v: int in m.values()) {
        println(f"  {v}")
    }
}
```

Expected output:

```
length: 3
has alice: true
has dave: false
bob's score: 87
keys:
  alice
  bob
  carol
values:
  95
  87
  91
```
