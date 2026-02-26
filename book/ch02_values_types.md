# Chapter 2: Values and Types

Every program manipulates data. Before you can write functions, compose pipelines, or build concurrent systems, you need to know what kinds of data Flow provides and how the type system governs their use. This chapter covers Flow's primitive types, strings, arrays, tuples, and option types. It also covers type inference, explicit annotations, and the casting system. By the end you will be able to write programs that compute, format, and transform data with confidence about what the compiler will accept and what it will reject.

---

## 2.1 Primitive Types

Flow has five primitive types. They are **value types**: stack-allocated, implicitly copied on assignment and function call, and exempt from ownership tracking. You do not need to think about who owns a value type or when it is freed. The compiler handles all of that automatically.

### 2.1.1 Integers and Sizing

`int` is a 64-bit signed integer. Its range is -2^63 to 2^63-1, which is roughly plus or minus 9.2 quintillion. There is one integer type you need to think about for most programs, and this is it.

```flow
let x: int = 42
let y: int = -17
let z: int = 0
```

The arithmetic operators are what you expect:

```flow
fn main(): int {
    let a: int = 10
    let b: int = 3

    io.println(conv.to_string(a + b))  // 13
    io.println(conv.to_string(a - b))  // 7
    io.println(conv.to_string(a * b))  // 30
    io.println(conv.to_string(a / b))  // 3 (integer division, truncates)
    io.println(conv.to_string(a % b))  // 1 (modulo)

    return 0
}
```

Integer division truncates toward zero. `10 / 3` is `3`, not `3.333...`. The remainder operator `%` gives the modulo: `10 % 3` is `1`. If you want floating-point division, cast both operands to `float` first (Section 2.7 covers casting).

Underscores are allowed in numeric literals for readability. The compiler ignores them:

```flow
let population: int = 8_100_000_000
let big: int = 9_223_372_036_854_775_807  // 2^63 - 1
```

Flow also provides the `**` operator for exponentiation and `</` for floor division:

```flow
fn main(): int {
    io.println(conv.to_string(2 ** 10))  // 1024
    io.println(conv.to_string(10 </ 3))  // 3 (floor division)

    return 0
}
```

The update operators `+=`, `-=`, `*=`, `/=`, `++`, and `--` work on mutable bindings:

```flow
fn main(): int {
    let count: int:mut = 0
    count++  // 1
    count += 5  // 6
    count--  // 5
    count *= 2  // 10
    io.println(conv.to_string(count))  // 10

    return 0
}
```

These operators require a `:mut` binding. Using them on an immutable binding is a compile error.

**Checked arithmetic.** Flow does not silently wrap on overflow. If an integer operation produces a value outside the 64-bit signed range, the program throws an `OverflowError` at runtime:

```flow
fn main(): int {
    let max: int = 9_223_372_036_854_775_807  // 2^63 - 1
    let n = max + 1  // throws OverflowError
    return 0
}
```

This is a deliberate design choice. Silent wraparound is a source of security vulnerabilities and subtle bugs in C and C++ programs. An integer that silently wraps from a large positive number to a large negative number can turn a bounds check into a buffer overflow. If your Flow program overflows, the runtime tells you immediately rather than producing a wrong answer that might propagate silently through the rest of your computation.

Integer division by zero throws `DivisionByZeroError`:

```flow
fn main(): int {
    let x: int = 42 / 0  // throws DivisionByZeroError
    return 0
}
```

There is no mechanism to disable checked arithmetic. If you find yourself hitting overflow, the solution is to rethink the algorithm, not to switch to unchecked math.

### 2.1.2 Floating-Point Numbers

`float` is a 64-bit IEEE 754 double-precision number. If you have used `double` in C, Java, or Go, this is the same thing. It provides approximately 15-17 significant decimal digits of precision.

```flow
let pi: float = 3.14159265358979
let negative: float = -0.5
let one: float = 1.0
```

Float literals require a decimal point. `1.0` is a float; `1` is an int. This distinction matters because the compiler will not implicitly convert an `int` to a `float` in an assignment --- only in mixed arithmetic expressions (see Section 2.7.1).

Standard arithmetic works on floats:

```flow
fn main(): int {
    let a: float = 10.0
    let b: float = 3.0

    io.println(conv.to_string(a + b))  // 13.0
    io.println(conv.to_string(a - b))  // 7.0
    io.println(conv.to_string(a * b))  // 30.0
    io.println(conv.to_string(a / b))  // 3.3333333333333335

    return 0
}
```

Floating-point arithmetic follows IEEE 754 rules, which means division by zero does not throw:

```flow
fn main(): int {
    let a: float = 1.0 / 0.0  // infinity
    let b: float = -1.0 / 0.0  // negative infinity
    let c: float = 0.0 / 0.0  // NaN (not a number)
    return 0
}
```

This is standard behavior across all IEEE 754 implementations. Infinity and NaN propagate through subsequent arithmetic: `infinity + 1.0` is still `infinity`, and any operation involving `NaN` produces `NaN`. If you need to detect these special values, the `math` module provides utilities for that.

There is one exception to the IEEE 754 rule: **float modulo by zero panics**.

```flow
fn main(): int {
    let a: float = 10.5 % 3.0  // 1.5  (uses C's fmod)
    let b: float = -7.5 % 2.0  // -1.5
    let c: float = 1.0 % 0.0  // throws DivisionByZeroError
    return 0
}
```

The rationale is straightforward. IEEE 754 defines infinity and NaN for division because they have useful mathematical properties --- programs that work with limits, singularities, or unbounded ranges rely on them. The modulo-by-zero case has no such utility. The result would be NaN, which almost always indicates a bug rather than a meaningful computation. Flow makes the bug visible immediately.

### 2.1.3 Booleans

`bool` has two values: `true` and `false`. There is nothing surprising here, but the details matter.

```flow
let done: bool = false
let ready: bool = true
```

The logical operators are `&&` (and), `||` (or), and `!` (not):

```flow
fn main(): int {
    let a: bool = true
    let b: bool = false

    io.println(conv.to_string(a && b))  // false
    io.println(conv.to_string(a || b))  // true
    io.println(conv.to_string(!a))  // false

    return 0
}
```

**Short-circuit evaluation.** `&&` and `||` short-circuit. In `a && b`, if `a` is `false`, `b` is never evaluated. In `a || b`, if `a` is `true`, `b` is never evaluated. This matters when `b` has side effects or is expensive to compute. You can rely on short-circuiting for guard patterns:

```flow
fn safe_divide(x: int, y: int): bool {
    // y != 0 is checked first; if false, division never happens
    return y != 0 && (x / y > 10)
}
```

The comparison operators produce booleans:

```flow
fn main(): int {
    io.println(conv.to_string(10 == 10))  // true  (equality)
    io.println(conv.to_string(10 != 5))  // true  (inequality)
    io.println(conv.to_string(3 < 7))  // true  (less than)
    io.println(conv.to_string(3 > 7))  // false (greater than)
    io.println(conv.to_string(5 <= 5))  // true  (less than or equal)
    io.println(conv.to_string(5 >= 6))  // false (greater than or equal)

    return 0
}
```

Comparisons work on all primitive types and on strings (lexicographic ordering). Comparing values of different types is a compile error --- you cannot compare an `int` to a `string`.

### 2.1.4 Bytes

`byte` is an unsigned 8-bit integer, range 0 to 255. It is the unit of raw binary data.

```flow
let b: byte = 255
let zero: byte = 0
```

You will not use `byte` as a standalone type very often. Its primary role is as the element type of byte arrays: `array<byte>`. Byte arrays are the natural representation for binary data --- file contents, network packets, serialized formats:

```flow
fn main(): int {
    let data: array<byte> = string.to_bytes("hello")
    let back: string = string.from_bytes(data)
    io.println(back)  // hello
    return 0
}
```

The `string.to_bytes` and `string.from_bytes` functions convert between strings and their raw byte representations. Chapter 13 uses byte arrays extensively when building a networked application.

---

## 2.2 Strings

Strings are sequences of bytes, heap-allocated and reference-counted when immutable. They are not a primitive type in the same sense as `int` or `bool` --- they live on the heap rather than the stack --- but they are so fundamental to everyday programming that they deserve their own section.

### 2.2.1 String Literals

Strings are double-quoted:

```flow
let greeting: string = "hello, world"
let empty: string = ""
```

The standard escape sequences work:

| Escape | Meaning |
|--------|---------|
| `\n` | newline |
| `\t` | tab |
| `\\` | backslash |
| `\"` | double quote |

```flow
let line: string = "first\nsecond"
let path: string = "C:\\Users\\alice"
let quoted: string = "she said \"hello\""
```

Strings are **immutable**. There is no way to change a character inside an existing string. Operations that appear to modify strings --- trimming, replacing, uppercasing --- return new strings and leave the original untouched. This immutability is what makes strings safe to share across threads and coroutines without copying (a property you will appreciate in Chapters 9 and 10).

### 2.2.2 String Interpolation

Flow supports **f-strings** for embedding expressions inside string literals. Prefix the string with `f` and wrap expressions in `{}`:

```flow
fn main(): int {
    let name: string = "Alice"
    let score: int = 95

    let msg: string = f"Player {name} scored {score} points."
    io.println(msg)  // Player Alice scored 95 points.

    return 0
}
```

Any expression is valid inside the braces. The expression is evaluated and converted to a string automatically:

```flow
fn main(): int {
    let x: int = 10
    let y: int = 20

    io.println(f"{x} + {y} = {x + y}")  // 10 + 20 = 30
    io.println(f"is positive: {x > 0}")  // is positive: true
    io.println(f"half: {cast<float>(x) / 2.0}")  // half: 5.0

    return 0
}
```

F-strings are the preferred way to build output messages, log lines, and formatted data in Flow. They are more readable than concatenation chains and less error-prone than manually calling `conv.to_string` on each value. Use them liberally.

### 2.2.3 String Concatenation

The `+` operator concatenates strings:

```flow
fn main(): int {
    let full: string = "hello" + " " + "world"
    io.println(full)  // hello world

    return 0
}
```

When one operand of `+` is a string and the other is a type that supports string conversion (`int`, `float`, `bool`), the non-string operand is automatically converted:

```flow
fn main(): int {
    let count: int = 42
    let msg: string = "count: " + count  // "count: 42"

    let pi: float = 3.14
    let s: string = "pi = " + pi + "!"  // "pi = 3.14!"

    io.println(msg)
    io.println(s)

    return 0
}
```

This auto-coercion applies only to the `+` operator and only when at least one operand is statically `string`. It does not apply to other operators. For most formatting work, f-strings are clearer, but concatenation with `+` is natural for simple cases like building file paths or joining short fragments.

### 2.2.4 Common String Operations

The `string` module provides the standard set of string manipulation functions. All of them are **pure** --- they return new strings and never modify their arguments.

**Length and substrings:**

```flow
fn main(): int {
    let s: string = "hello, world"

    io.println(conv.to_string(string.len(s)))  // 12
    io.println(string.substring(s, 0, 5))  // hello
    io.println(string.substring(s, 7, 12))  // world

    return 0
}
```

`string.len` returns the byte length. For ASCII text, bytes and characters are the same. For multi-byte UTF-8 sequences they differ --- this is a conscious simplification for the bootstrap compiler.

`string.substring(s, start, end)` uses a half-open interval `[start, end)`. It clamps to bounds rather than throwing, so you do not need to guard against off-by-one errors.

**Searching:**

```flow
fn main(): int {
    let s: string = "hello, world"

    io.println(conv.to_string(string.contains(s, "world")))  // true
    io.println(conv.to_string(string.contains(s, "xyz")))  // false
    io.println(conv.to_string(string.starts_with(s, "hello")))  // true
    io.println(conv.to_string(string.ends_with(s, ".txt")))  // false

    return 0
}
```

**Transformation:**

```flow
fn main(): int {
    io.println(string.to_upper("hello"))  // HELLO
    io.println(string.to_lower("HELLO"))  // hello
    io.println(string.trim("  hello  "))  // hello
    io.println(string.replace("aabaa", "aa", "x"))  // xbx

    return 0
}
```

**Splitting and joining:**

```flow
fn main(): int {
    let csv_line: string = "alice,95,A"
    let parts: array<string> = string.split(csv_line, ",")
    // parts is ["alice", "95", "A"]

    for (p: string in parts) {
        io.println(p)
    }

    // Rejoin with a different separator
    let rejoined: string = string.join(parts, " | ")
    io.println(rejoined)  // alice | 95 | A

    return 0
}
```

`string.split(s, "")` splits into individual bytes. `string.join(parts, sep)` is the inverse of `split`: it concatenates an array of strings with a separator between each pair.

Here is a practical example that parses a simple key-value pair:

```flow
fn parse_pair(line: string): (string, string) {
    let parts: array<string> = string.split(line, "=")
    let key: string = match array.get(parts, 0) {
        some(k) : string.trim(k),
        none    : ""
    }
    let value: string = match array.get(parts, 1) {
        some(v) : string.trim(v),
        none    : ""
    }
    return (key, value)
}

fn main(): int {
    let (k, v) = parse_pair("host = localhost")
    io.println(f"key: '{k}', value: '{v}'")  // key: 'host', value: 'localhost'

    return 0
}
```

---

## 2.3 Arrays

An array is an ordered, indexed collection of values of a single type. Arrays in Flow are immutable by default: operations that add or remove elements produce new arrays.

### 2.3.1 Array Literals

```flow
let nums: array<int> = [1, 2, 3, 4, 5]
let names: array<string> = ["alice", "bob", "carol"]
let empty: array<int> = []
```

The element type is inferred from the contents when unambiguous:

```flow
let inferred = [10, 20, 30]  // inferred as array<int>
```

All elements must be the same type. A heterogeneous literal is a compile error:

```flow
let bad = [1, "two", 3]  // compile error: int and string are not the same type
```

### 2.3.2 Accessing Elements

`array.get` returns an `option` --- either `some(value)` if the index is valid, or `none` if it is out of bounds:

```flow
fn main(): int {
    let nums: array<int> = [10, 20, 30]

    match array.get_int(nums, 0) {
        some(v) : io.println(conv.to_string(v)),  // 10
        none    : io.println("out of bounds")
    }

    match array.get_int(nums, 99) {
        some(v) : io.println(conv.to_string(v)),
        none    : io.println("out of bounds")  // this branch
    }

    return 0
}
```

There is no unchecked indexing operator. Every access goes through `get`, and every `get` returns an option. This eliminates the entire class of index-out-of-bounds crashes at the cost of requiring you to handle the absent case explicitly. If that sounds like more work, it is --- but it is the kind of work that prevents your program from segfaulting in production at 3 AM.

For string arrays, use `array.get` (not `array.get_int`):

```flow
fn main(): int {
    let names: array<string> = ["alice", "bob"]

    match array.get(names, 0) {
        some(name) : io.println(name),  // alice
        none       : io.println("empty")
    }

    return 0
}
```

The `??` operator provides a convenient shorthand when you have a default value:

```flow
fn main(): int {
    let nums: array<int> = [10, 20, 30]
    let val: int = array.get_int(nums, 5) ?? 0  // 0 (out of bounds)

    io.println(conv.to_string(val))

    return 0
}
```

### 2.3.3 Building Arrays

`array.push` adds an element to the end of an array, returning a new array:

```flow
fn main(): int {
    let a: array<int> = [1, 2, 3]
    let b: array<int> = array.push_int(a, 4)

    // a is still [1, 2, 3]
    // b is [1, 2, 3, 4]

    io.println(conv.to_string(array.len(a)))  // 3
    io.println(conv.to_string(array.len(b)))  // 4

    return 0
}
```

`push` does not modify the original array. It creates a new one. The original remains unchanged. This is a fundamental property of immutable data in Flow: operations produce new values rather than modifying existing ones. If you are building up an array incrementally, the typical pattern is:

```flow
fn main(): int {
    let result: array<int>:mut = []

    result = array.push_int(result, 10)
    result = array.push_int(result, 20)
    result = array.push_int(result, 30)

    for (n: int in result) {
        io.println(conv.to_string(n))
    }

    return 0
}
```

Here the `:mut` binding `result` is reassigned to a new array on each push. The old array becomes unreachable and is freed automatically.

### 2.3.4 Array Length

```flow
fn main(): int {
    let nums: array<int> = [10, 20, 30]
    let names: array<string> = ["alice", "bob"]

    io.println(conv.to_string(array.len(nums)))  // 3
    io.println(conv.to_string(array.len_string(names)))  // 2

    return 0
}
```

`array.len` works on integer arrays. `array.len_string` works on string arrays. The generic `array.size<T>` works for any element type.

### 2.3.5 Iterating Over Arrays

The `for` loop iterates over an array's elements:

```flow
fn main(): int {
    let nums: array<int> = [10, 20, 30, 40, 50]

    for (n: int in nums) {
        io.println(conv.to_string(n))
    }

    return 0
}
```

This prints each element on its own line. The variable `n` is scoped to the loop body; it does not exist before the loop or after it.

Here is a complete example that builds an array, iterates over it, and computes a sum:

```flow
fn main(): int {
    let scores: array<int> = [85, 92, 78, 95, 88]
    let total: int:mut = 0

    for (s: int in scores) {
        total += s
    }

    io.println(f"Total: {total}")  // Total: 438
    io.println(f"Count: {array.len(scores)}")  // Count: 5

    return 0
}
```

Nested arrays work as you would expect:

```flow
let matrix: array<array<int>> = [[1, 2], [3, 4], [5, 6]]
```

You can also concatenate two arrays:

```flow
fn main(): int {
    let a: array<int> = [1, 2, 3]
    let b: array<int> = [4, 5, 6]
    let c: array<int> = array.concat(a, b)
    // c is [1, 2, 3, 4, 5, 6]

    io.println(conv.to_string(array.len(c)))  // 6

    return 0
}
```

---

## 2.4 Tuples

A **tuple** is a fixed-size, ordered grouping of values that may have different types. Where arrays hold many values of one type, tuples hold a small number of values of potentially different types.

```flow
let pair: (int, string) = (42, "hello")
let triple: (float, float, float) = (1.0, 2.0, 3.0)
```

### 2.4.1 Accessing Tuple Elements

Tuple elements are accessed by zero-based index using dot notation:

```flow
fn main(): int {
    let pair: (int, string) = (42, "hello")

    let n: int = pair.0  // 42
    let s: string = pair.1  // "hello"

    io.println(conv.to_string(n))  // 42
    io.println(s)  // hello

    return 0
}
```

The indices are compile-time constants, not runtime values. You cannot write `pair.i` where `i` is a variable --- the compiler needs to know the index statically to determine the result type.

### 2.4.2 Destructuring

You can unpack a tuple into individual bindings in a single `let`:

```flow
fn main(): int {
    let pair: (int, string) = (42, "hello")
    let (n, s) = pair

    io.println(conv.to_string(n))  // 42
    io.println(s)  // hello

    return 0
}
```

Destructuring works with any tuple size:

```flow
fn main(): int {
    let triple: (int, float, string) = (1, 2.5, "three")
    let (a, b, c) = triple

    io.println(conv.to_string(a))  // 1
    io.println(conv.to_string(b))  // 2.5
    io.println(c)  // three

    return 0
}
```

### 2.4.3 Tuples as Return Values

Tuples are the standard way to return multiple values from a function:

```flow
fn min_max(items: array<int>): (int, int) {
    let lo: int:mut = 0
    let hi: int:mut = 0
    let first: bool:mut = true

    for (item: int in items) {
        if (first) {
            lo = item
            hi = item
            first = false
        } else {
            if (item < lo) { lo = item }
            if (item > hi) { hi = item }
        }
    }

    return (lo, hi)
}

fn main(): int {
    let data: array<int> = [38, 12, 95, 7, 63]
    let (lo, hi) = min_max(data)

    io.println(f"min: {lo}, max: {hi}")  // min: 7, max: 95

    return 0
}
```

Tuples are for short-lived, anonymous groupings --- especially function returns and intermediate values. When data crosses module boundaries or carries semantic meaning, prefer named types (Chapter 6 covers structs and named types). A good rule of thumb: if you find yourself passing the same tuple type through more than two or three functions, it is time to give it a name.

---

## 2.5 The None Literal and Option Types

Some operations do not always produce a value. Looking up a key in a map, accessing an array by index, or parsing a string might have nothing to return. In languages like Java or Python, this situation is represented by `null` or `None`, and forgetting to check for it is one of the most common sources of runtime crashes. Flow eliminates this class of bug entirely.

### 2.5.1 The Basics

`option<T>` is a type that is either `some(value)` or `none`:

```flow
let x: option<int> = some(5)  // a value is present
let y: option<int> = none  // no value
```

The sugar `T?` is equivalent to `option<T>`. Both notations mean exactly the same thing:

```flow
let x: int? = some(5)  // same as option<int>
let y: int? = none
```

A bare `int` can never be `none`. Only `int?` can. The type system enforces this at compile time, which means you never have to wonder "could this variable be null?" --- the type tells you.

### 2.5.2 Auto-lifting

When the target type is statically known to be `option<T>` and you provide a plain `T`, Flow automatically wraps it in `some`:

```flow
let x: int? = 5  // automatically lifted to some(5)
let y: int? = some(5)  // explicit, same result
let z: int? = none  // no lifting needed
```

This convenience avoids writing `some(...)` everywhere. Auto-lifting also works in function returns and arguments:

```flow
fn maybe_score(): int? {
    return 95  // lifted to some(95)
}
```

Auto-lifting does **not** create `option<option<T>>` by accident. If the source is already an option, no wrapping happens.

### 2.5.3 Pattern Matching on Options

The standard way to handle an option is `match`:

```flow
fn describe(value: int?): string {
    return match value {
        some(v) : f"got {v}",
        none    : "nothing"
    }
}

fn main(): int {
    io.println(describe(some(42)))  // got 42
    io.println(describe(none))  // nothing

    return 0
}
```

The match is **exhaustive**: you must handle both `some` and `none`. If you forget one, the compiler rejects the program.

### 2.5.4 The `??` Operator

The `??` (null coalescing) operator provides a default value when an option is `none`:

```flow
fn main(): int {
    let x: int? = none
    let y: int = x ?? 0  // 0, because x is none

    let a: int? = some(42)
    let b: int = a ?? 0  // 42, because a has a value

    io.println(conv.to_string(y))  // 0
    io.println(conv.to_string(b))  // 42

    return 0
}
```

The right side of `??` is only evaluated if the left side is `none` (short-circuit). This makes it efficient even when the default is expensive to compute.

`??` is particularly useful with array access:

```flow
fn main(): int {
    let scores: array<int> = [85, 92, 78]
    let first: int = array.get_int(scores, 0) ?? 0  // 85
    let missing: int = array.get_int(scores, 99) ?? 0  // 0

    io.println(conv.to_string(first))
    io.println(conv.to_string(missing))

    return 0
}
```

This chapter introduces options only enough to read array access results and understand the type. Chapter 7 covers `option<T>` in full depth --- pattern matching, `if let`, propagation with `?`, and composition with options.

---

## 2.6 Type Annotations and Inference

Flow's type system **infers** types when they are unambiguous. You do not need to annotate every binding. But annotations are required in some places, useful in others, and occasionally essential to communicate your intent to the compiler.

### 2.6.1 Inference at Work

```flow
let x = 42  // inferred as int
let y = 3.14  // inferred as float
let z = "hello"  // inferred as string
let b = true  // inferred as bool
let a = [1, 2, 3]  // inferred as array<int>
```

The compiler examines the right-hand side of each `let` and determines the type. No annotation needed. The inferred type is exactly as if you had written the annotation yourself --- there is no "weaker" or "less precise" inference. `let x = 42` and `let x: int = 42` produce identical compiled code.

### 2.6.2 When Annotations Are Required

**Function parameters and return types** always require annotations. The compiler does not infer types across function boundaries:

```flow
fn add(a: int, b: int): int {
    return a + b
}
```

You cannot write `fn add(a, b)` and expect the compiler to figure it out. Function signatures are contracts between the caller and the implementation. They must be explicit. This is a conscious design decision: it keeps function signatures readable without needing an IDE, and it prevents changes inside a function body from silently altering the function's public interface.

**Empty collections** require annotations because there is no content to infer from:

```flow
let empty: array<int> = []  // annotation required: [] could be array of anything
```

### 2.6.3 When Annotations Are Useful

Even where inference works, annotations serve as documentation and as a check on your assumptions:

```flow
let count: int = 0
let ratio: float = 0.0
let name: string = ""
```

Annotations are also necessary when you want a type different from what would be inferred:

```flow
let x: float = 0  // without annotation, 0 would be inferred as int
let y: int? = 5  // without annotation, 5 would be inferred as int (not option<int>)
```

A reasonable guideline: annotate bindings at the top of a function or when the type is not immediately obvious from the right-hand side. Inside a computation where the types are obvious from context, let inference do its job.

### 2.6.4 Mutable Bindings

By default, `let` bindings are **immutable**. You cannot reassign them:

```flow
let x: int = 5
x = 10  // compile error: x is immutable
```

Add `:mut` to make a binding mutable:

```flow
let x: int:mut = 5
x = 10  // ok
x += 3  // ok, x is now 13
x++  // ok, x is now 14
```

The `:mut` modifier follows the type. When combined with `?`, the `?` comes first:

```flow
let a: int:mut = 0  // mutable int
let b: int?:mut = some(5)  // mutable optional int
```

The order matters. `int:mut?` is a compile error; `int?:mut` is correct. The grammar is: type, then optional `?`, then optional `:mut` or `:imut`.

You can also write `:imut` to explicitly mark a binding as immutable. This has the same effect as the default (no modifier), but makes the immutability visually explicit:

```flow
let x: int = 5  // immutable (default)
let y: int:imut = 5  // explicitly immutable, same as above
let z: int:mut = 5  // mutable
```

Immutability is the default for a reason. Immutable data is simpler to reason about, safe to share across threads without locks, and never surprises you with unexpected changes. Use `:mut` when you need it --- loop counters, accumulators, state that genuinely changes --- but prefer immutable bindings as your starting point. Programs that minimize mutable state are easier to test, easier to debug, and easier to parallelize.

---

## 2.7 Type Conversions and Casting

Flow is strict about types. An `int` is not a `float`, a `float` is not a `string`, and the compiler will not silently convert between them --- with one exception.

### 2.7.1 Implicit Widening

When `int` and `float` appear in the same arithmetic expression, the `int` is implicitly widened to `float`:

```flow
fn main(): int {
    let x: int = 42
    let y: float = 3.14
    let z: float = x + y  // x is widened to float, z is 45.14

    io.println(conv.to_string(z))

    return 0
}
```

This is the only implicit numeric conversion in mixed arithmetic. It is safe because every 64-bit integer value has a representable (if sometimes slightly imprecise) 64-bit float equivalent. The result type of a mixed `int + float` expression is always `float`.

No other implicit conversions exist. `int` does not silently become `string`. `bool` does not silently become `int`. If the compiler cannot prove the conversion is safe and lossless, it rejects it.

### 2.7.2 Explicit Casting with `cast<T>`

`cast<T>(expr)` converts a value to type `T`:

```flow
fn main(): int {
    // int to float
    let a: float = cast<float>(42)  // 42.0

    // float to int (truncates toward zero)
    let b: int = cast<int>(3.7)  // 3
    let c: int = cast<int>(-2.9)  // -2

    io.println(conv.to_string(a))  // 42.0
    io.println(conv.to_string(b))  // 3
    io.println(conv.to_string(c))  // -2

    return 0
}
```

Float-to-int truncates toward zero, not rounds. `cast<int>(3.7)` is `3`, not `4`. `cast<int>(-2.9)` is `-2`, not `-3`. This matches C's behavior and is deterministic regardless of the fractional part.

Narrowing integer casts (converting from a wider to a narrower type) throw `OverflowError` if the value does not fit in the target range:

```flow
let big: int = 9_223_372_036_854_775_807
// Casting this to a 32-bit type would throw OverflowError
```

### 2.7.3 String Conversions

Converting between strings and numbers uses the `conv` module:

```flow
fn main(): int {
    // Number to string
    let s: string = conv.to_string(42)  // "42"
    let t: string = conv.to_string(3.14)  // "3.14"

    io.println(s)
    io.println(t)

    // String to number (returns option, because parsing can fail)
    let n: int? = conv.string_to_int("42")  // some(42)
    let bad: int? = conv.string_to_int("hello")  // none
    let f: float? = conv.string_to_float("3.14")  // some(3.14)

    match n {
        some(v) : io.println(f"parsed: {v}"),  // parsed: 42
        none    : io.println("parse failed")
    }

    match bad {
        some(v) : io.println(f"parsed: {v}"),
        none    : io.println("parse failed")  // parse failed
    }

    return 0
}
```

`conv.string_to_int` and `conv.string_to_float` return options because parsing can fail. A non-numeric string, an empty string, or an overflow all produce `none` rather than throwing an exception. This is the pattern throughout Flow: expected failures return options or results; exceptions are reserved for the unexpected.

---

## 2.8 Numeric Overflow and Division

This section collects the arithmetic edge cases in one place. You have seen pieces of this already; here is the complete picture.

### 2.8.1 Integer Overflow

All integer arithmetic is checked. Overflow throws `OverflowError`:

```flow
fn main(): int {
    let max: int = 9_223_372_036_854_775_807
    let boom = max + 1  // throws OverflowError
    return 0
}
```

This applies to `+`, `-`, `*`, and `**`. Division and modulo cannot overflow except for one edge case: dividing the minimum 64-bit integer (-2^63) by -1 produces a value one larger than the maximum, so it also throws `OverflowError`.

### 2.8.2 Integer Division by Zero

```flow
fn main(): int {
    let x: int = 42 / 0  // throws DivisionByZeroError
    return 0
}
```

Integer modulo by zero also throws `DivisionByZeroError`:

```flow
fn main(): int {
    let x: int = 42 % 0  // throws DivisionByZeroError
    return 0
}
```

### 2.8.3 Float Division by Zero

Float division by zero follows IEEE 754 and does not throw:

```flow
fn main(): int {
    let a: float = 1.0 / 0.0  // infinity
    let b: float = -1.0 / 0.0  // negative infinity
    let c: float = 0.0 / 0.0  // NaN

    return 0
}
```

### 2.8.4 Float Modulo by Zero

Float modulo is the exception to the IEEE 754 rule. It throws:

```flow
fn main(): int {
    let a: float = 10.5 % 3.0  // 1.5 --- this is fine
    let b: float = 1.0 % 0.0  // throws DivisionByZeroError
    return 0
}
```

The summary:

| Operation | Behavior |
|-----------|----------|
| Integer overflow | throws `OverflowError` |
| Integer division by zero | throws `DivisionByZeroError` |
| Integer modulo by zero | throws `DivisionByZeroError` |
| Float division by zero | IEEE 754: infinity or NaN |
| Float modulo by zero | throws `DivisionByZeroError` |

The asymmetry between float division and float modulo is intentional. Float division by zero has well-defined, useful semantics in IEEE 754 that scientific and numerical code relies on. Float modulo by zero produces NaN, which is almost never useful and almost always a bug.

---

## 2.9 What Goes Wrong

This section covers the most common type-related compiler errors you will encounter. Learning to read these errors will save you time.

### Type Mismatch in Assignment

```flow
let x: int = "hello"
// compile error: type mismatch: expected int, got string
```

The fix is obvious once you see it: either change the annotation or change the value. But this error also appears in subtler forms:

```flow
let x: int = 3.14
// compile error: type mismatch: expected int, got float
```

Even though 3.14 is a number, Flow does not implicitly narrow a `float` to an `int`. Use `cast<int>(3.14)` if you want truncation.

### Mutation of Immutable Binding

```flow
let x: int = 5
x = 10
// compile error: cannot assign to immutable binding
```

The fix: declare the binding as `let x: int:mut = 5`.

### Wrong Modifier Order

```flow
let x: int:mut? = some(5)
// compile error: ? must precede :mut
```

The correct order is type, then `?`, then `:mut`:

```flow
let x: int?:mut = some(5)  // correct
```

### Heterogeneous Array

```flow
let bad = [1, "two", 3]
// compile error: array elements must be the same type
```

All array elements must have a single, uniform type. If you need to mix types, use a tuple or a sum type (Chapter 6).

### Missing Function Annotations

```flow
fn add(a, b) {
    return a + b
}
// compile error: function parameters require type annotations
```

Every function parameter needs a type, and every function needs a return type:

```flow
fn add(a: int, b: int): int {
    return a + b
}
```

### Comparing Different Types

```flow
if (42 == "42") { ... }
// compile error: cannot compare int and string
```

Flow does not coerce types for comparison. If you need to compare an int to a string, convert one of them explicitly first.

---

## 2.10 Putting It Together

Here is a complete program that uses most of what this chapter introduced:

```flow
fn format_score(name: string, score: int, max_score: int): string {
    let pct: float = cast<float>(score) / cast<float>(max_score) * 100.0
    let grade: string = if (pct >= 90.0) {
        "A"
    } else {
        if (pct >= 80.0) {
            "B"
        } else {
            if (pct >= 70.0) {
                "C"
            } else {
                "F"
            }
        }
    }
    return f"{name}: {score}/{max_score} ({grade})"
}

fn main(): int {
    let names: array<string> = ["Alice", "Bob", "Carol", "Dave"]
    let scores: array<int> = [92, 85, 78, 61]
    let max_score: int = 100

    let i: int:mut = 0
    for (name: string in names) {
        match array.get_int(scores, i) {
            some(score) : io.println(format_score(name, score, max_score)),
            none        : io.println(f"{name}: no score")
        }
        i++
    }

    // Compute average
    let total: int:mut = 0
    for (s: int in scores) {
        total += s
    }
    let avg: float = cast<float>(total) / cast<float>(array.len(scores))
    io.println(f"Average: {avg}")

    return 0
}
```

Output:

```
Alice: 92/100 (A)
Bob: 85/100 (B)
Carol: 78/100 (C)
Dave: 61/100 (F)
Average: 79.0
```

This program demonstrates:

- Primitive types (`int`, `float`, `string`, `bool`)
- String interpolation with f-strings
- Arrays and `array.get_int` returning an option
- Mutable bindings with `:mut` for the loop counter and accumulator
- Type casting with `cast<float>` for floating-point division
- Pattern matching on options (brief preview of Chapter 7)
- The `for` loop over arrays

---

## 2.11 Summary

Flow's type system is strict but not verbose. The compiler infers types where it can, requires annotations where it must, and rejects ambiguity rather than guessing. The primitive types --- `int`, `float`, `bool`, `byte`, and `string` --- cover the common cases. Arrays hold homogeneous collections with safe, option-returning access. Tuples group small heterogeneous bundles, primarily for function returns. Options represent absent values without null pointers.

Arithmetic is checked: overflow and division by zero are caught at runtime rather than producing garbage. Float arithmetic follows IEEE 754, with the deliberate exception that float modulo by zero panics.

All data is immutable by default. Mutable bindings require `:mut`. This is not a restriction but a default that makes most code simpler to reason about, safer to parallelize, and easier to test.

Chapter 3 introduces functions: how to define them, how to call them, how the type system governs parameters and return values, and what it means for a function to be pure.

---

## Exercises

**1. Temperature Converter**

Write a program with three functions: `celsius_to_fahrenheit`, `fahrenheit_to_celsius`, and `celsius_to_kelvin`. Each takes a `float` and returns a `float`. Write a `main` function that converts 100 degrees Celsius through all three and prints the results using f-strings.

Formulas:
- F = C * 9.0 / 5.0 + 32.0
- C = (F - 32.0) * 5.0 / 9.0
- K = C + 273.15

Expected output for 100.0 Celsius:
```
100.0 C = 212.0 F
212.0 F = 100.0 C
100.0 C = 373.15 K
```

**2. Array Statistics**

Write a function `stats(data: array<int>): (int, int, float)` that returns the minimum, maximum, and average of an array of integers as a tuple. Use destructuring in `main` to unpack the result and print each value. Test it with `[38, 12, 95, 7, 63]`.

Expected output:
```
min: 7
max: 95
avg: 43.0
```

**3. String Reversal**

Write a function `reverse(s: string): string` that returns the reversed version of a string. Use `string.len` and `string.substring` to extract one character at a time and build the reversed string with concatenation. Test it with `"hello"` (expected: `"olleh"`) and `""` (expected: `""`).

**4. Grade Report**

Create two arrays: one of student names (`array<string>`) and one of grades (`array<int>`). Write a function that takes both arrays and a maximum score, then uses string interpolation to print a formatted report like:

```
1. Alice    92  A
2. Bob      85  B
3. Carol    78  C
4. Dave     61  F
```

Use the letter grade logic from Section 2.10. Handle the case where the arrays have different lengths by using `array.get` and printing `"(no data)"` for missing entries.
