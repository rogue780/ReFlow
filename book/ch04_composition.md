# Chapter 4: Composition

Chapters 1 through 3 introduced programs, values, and functions. You can now write functions that take inputs and produce outputs. This chapter shows you how to connect them.

Most languages compose functions by nesting calls: `square(double(5))`. The innermost call runs first, the outermost runs last, and you read the expression inside-out. With two functions this is tolerable. With five it is not. With ten, mixed with conditionals and intermediate bindings, the structure is buried under syntax.

Flow takes a different approach. The `->` operator chains values and functions left to right. `5 -> double -> square` means the same thing as `square(double(5))`, but you read it in the order things happen: start with 5, double it, square the result. This is not syntactic sugar over method calls. It is the primary way you build programs in Flow.

This chapter covers linear composition, fan-out, parallel execution, auto-mapping over streams, and the patterns that emerge when you combine them. By the end, you will be writing programs as pipelines --- sequences of small, testable stages connected by arrows.

---

## 4.1 The Arrow Operator (`->`)

### 4.1.1 Values and Functions in a Chain

Start with two functions:

```flow
fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
```

Both take one integer and return one integer. To double 5 and then square the result:

```flow
let result = 5 -> double -> square
```

This evaluates left to right. `5` flows into `double`, producing `10`. `10` flows into `square`, producing `100`. The value of `result` is `100`.

The equivalent nested call is:

```flow
let result = square(double(5))
```

Same result. But read both lines again. The arrow version matches the description: "double 5, then square it." The nested version reverses the order: the last operation to run (`square`) appears first.

With two functions the difference is small. Add a third:

```flow
fn:pure negate(x: int): int = 0 - x

let result = 5 -> double -> square -> negate
; negate(square(double(5))) = negate(100) = -100
```

The arrow version still reads as a sequence of steps. The nested version requires you to find the innermost parenthesis and work outward. The gap widens with every additional stage.

Here is a complete program:

```flow
module composition_demo
import io (println)

fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
fn:pure negate(x: int): int = 0 - x

fn main() {
    let a = 5 -> double              ; 10
    let b = 5 -> double -> square    ; 100
    let c = 5 -> square -> double    ; 50

    println(f"a = {a}")
    println(f"b = {b}")
    println(f"c = {c}")

    ; Order matters: double then square is not square then double
    let d = 5 -> double -> square -> negate  ; -100
    println(f"d = {d}")
}
```

Notice that `b` and `c` differ. `5 -> double -> square` doubles first (10), then squares (100). `5 -> square -> double` squares first (25), then doubles (50). The arrow preserves evaluation order visually. There is no ambiguity about what runs when.

### 4.1.2 The Value Stack

The arrow operator works on an implicit **value stack**. The rule is simple:

- When the chain encounters a **value**, it pushes the value onto the stack.
- When the chain encounters a **function** of arity N, it pops N values from the stack, calls the function, and pushes the result.

For a single-argument function, this behaves exactly like piping: `x -> f` pops `x`, calls `f(x)`, pushes the result. But the stack model extends naturally to functions that take more than one argument.

Consider a function that adds two numbers:

```flow
fn:pure add(x: int, y: int): int = x + y
```

`add` has arity 2. It needs two values on the stack. You provide them by pushing two values before calling it:

```flow
let result = 3 -> 4 -> add
; Stack trace:
;   push 3     → stack: [3]
;   push 4     → stack: [3, 4]
;   add (arity 2) pops 3 and 4, pushes 7 → stack: [7]
; result = 7
```

This is equivalent to `add(3, 4)`. The values are consumed left to right: `3` becomes the first argument, `4` becomes the second.

You can continue the chain after consuming values:

```flow
fn:pure double(x: int): int = x * 2

let result = 3 -> 4 -> add -> double
; Stack trace:
;   push 3     → stack: [3]
;   push 4     → stack: [3, 4]
;   add        → stack: [7]
;   double     → stack: [14]
; result = 14
```

Equivalent to `double(add(3, 4))`. Four stages, no nesting.

Here is a longer example with mixed arities:

```flow
fn:pure add(x: int, y: int): int = x + y
fn:pure square(x: int): int = x * x
fn:pure mul(x: int, y: int): int = x * y

let result = 3 -> 4 -> add -> 2 -> mul
; Stack trace:
;   push 3     → stack: [3]
;   push 4     → stack: [3, 4]
;   add        → stack: [7]
;   push 2     → stack: [7, 2]
;   mul        → stack: [14]
; result = 14
```

Values and functions can be interleaved freely. The stack grows when values are pushed and shrinks when functions consume them. The only requirement is that the stack has enough values when a function needs them, and that exactly one value remains when the chain ends.

### 4.1.3 Arity Matching

The compiler checks that every function in a chain has enough values on the stack to satisfy its arity. If you write:

```flow
let bad = 3 -> add   ; compile error
```

The compiler rejects this. `add` requires 2 arguments but only 1 value is on the stack.

This checking is static. The compiler traces the stack depth at each stage of the chain and rejects mismatches before the program runs. You cannot accidentally call a two-argument function with one value or a one-argument function with two.

Every function in Flow returns exactly one value. There is no void return. Functions that perform side effects and have no meaningful result return `none`. The value `none` participates in the stack like any other value --- it can be pushed, consumed, and passed along.

The stack must contain exactly one value when the chain ends. If you push two values and never consume the second, the compiler rejects the chain. If a function consumes all values and you try to continue the chain with a function that expects input, the compiler catches that too. The stack discipline ensures that every composition chain is well-formed.

### 4.1.4 Composition in Expression-Bodied Functions

Composition chains can be used as the body of expression-bodied functions. This produces very concise definitions:

```flow
fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
fn:pure add(x: int, y: int): int = x + y

fn:pure process(x: int, y: int): int = x -> y -> add -> double -> square
```

`process` is a single expression: push `x`, push `y`, add them, double the result, square it. The function reads as a direct description of its computation. No `return` statement, no curly braces, no intermediate bindings.

This style works particularly well for pure transformation functions where the body is a straight-line pipeline. For functions with branching, loops, or multiple statements, the block form with `return` is more appropriate.

### 4.1.5 When to Use Composition

Not every function call needs an arrow. `add(3, 4)` is perfectly readable as a direct call. The arrow earns its place when you have a sequence of transformations --- when the output of one step is the input to the next.

A useful heuristic: if you would write a chain of nested calls, or a sequence of `let` bindings where each binding uses only the previous one, a composition chain is likely clearer:

```flow
; Nested calls: read inside-out
let result = format(validate(parse(clean(input))))

; Intermediate bindings: readable but verbose
let cleaned = clean(input)
let parsed = parse(cleaned)
let validated = validate(parsed)
let result = format(validated)

; Composition: left to right, no intermediates
let result = input -> clean -> parse -> validate -> format
```

All three are equivalent. The composition version carries the least syntactic weight and the most direct correspondence to the sequence of operations.

Direct calls are fine when there is no chain --- when a function takes explicit arguments that do not come from a prior transformation. Use `add(3, 4)` rather than `3 -> 4 -> add` when the values are literals or unrelated variables. Use composition when data flows through a series of transformations. The two styles coexist naturally:

```flow
fn process(data: string, threshold: int): int =
    data -> parse -> filter(\(r: record => r.score > threshold)) -> count
```

Here `threshold` is an argument to the lambda, not a value flowing through the pipeline. The pipeline chains transformations on `data`; the threshold is configuration. Mixing direct arguments and composition is idiomatic.

---

## 4.2 Fan-Out (`|`)

Linear chains handle the common case: one value flows through a series of functions. But sometimes you need to send the same value to multiple functions and combine the results. This is **fan-out**.

### 4.2.1 Splitting Data to Multiple Functions

The `|` operator inside parentheses splits a value across multiple branches:

```flow
fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
fn:pure add(x: int, y: int): int = x + y

let result = 5 -> (double | square) -> add
```

Here is what happens:

1. `5` is pushed onto the stack.
2. `(double | square)` is a fan-out group. The value `5` is sent to both `double` and `square`.
3. `double(5)` produces `10`. `square(5)` produces `25`.
4. The two results are pushed onto the stack left to right: `[10, 25]`.
5. `add` (arity 2) pops both and produces `35`.

The result is `35`. Equivalent to `add(double(5), square(5))`.

Each branch in a fan-out receives the same input. Each branch produces exactly one result (because every function returns exactly one value). The results are pushed in the order the branches appear, left to right.

### 4.2.2 Arity Checking

The compiler enforces that the number of results produced by a fan-out matches the arity of the next function in the chain. A fan-out with two branches produces two values. The next function must take two parameters:

```flow
fn:pure mul(x: int, y: int): int = x * y

fn good(x: int): int = x -> (double | square) -> mul
; fan-out produces 2 values, mul takes 2: ok

fn bad(x: int): int = x -> (double | square | negate) -> mul
; compile error: fan-out produces 3 values, mul takes 2
```

If you have three branches, you need a function that takes three arguments:

```flow
fn:pure sum3(a: int, b: int, c: int): int = a + b + c

fn ok(x: int): int = x -> (double | square | negate) -> sum3
; fan-out produces 3, sum3 takes 3: ok
```

The rule is straightforward: the number of branches must equal the arity of the consuming function. The compiler checks this statically.

### 4.2.3 Long-Form Fan-Out

The shorthand form sends one value to all branches. The long form lets each branch have its own input chain:

```flow
fn:pure square(x: int): int = x * x
fn:pure double(x: int): int = x * 2
fn:pure mul(x: int, y: int): int = x * y

let result = (3 -> square | 7 -> double) -> mul
; square(3) = 9, double(7) = 14, mul(9, 14) = 126
```

Each branch is an independent chain. The left branch pushes `3` and applies `square`. The right branch pushes `7` and applies `double`. Their results feed `mul`.

This is useful when the inputs to a multi-argument function come from different sources or different transformations:

```flow
fn:pure normalize(x: float, min: float, max: float): float =
    (x - min) / (max - min)

; Both min and max are derived from the same dataset, but via different functions
let normalized = (value -> identity | data -> find_min | data -> find_max) -> normalize
```

### 4.2.4 Chaining After Fan-Out

Fan-out does not end a chain. The combined result flows to the next stage, which can be another function, another fan-out, or both:

```flow
fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
fn:pure mul(x: int, y: int): int = x * y

fn pipeline(x: int): int = x -> (double | square) -> mul -> square
; mul(double(x), square(x)) then square the result
; x=3: mul(6, 9) = 54, square(54) = 2916
```

The chain reads naturally: fan out `x` to `double` and `square`, multiply the results, then square the product. Four operations, one line, no nesting.

---

## 4.3 Lambdas in Composition

Named functions work well for reusable operations, but sometimes you need a one-off transformation that does not merit a name. Flow's lambda expressions fill this role.

### 4.3.1 Lambda Syntax

A lambda is written with a backslash, parameters, a `=>` separator, and a body:

```flow
let double = \(x: int => x * 2)
let add = \(x: int, y: int => x + y)
```

The type is inferred: `double` has type `fn(int): int`, and `add` has type `fn(int, int): int`. You can annotate explicitly if you prefer:

```flow
let double: fn(int): int = \(x: int => x * 2)
```

Lambdas work directly in composition chains:

```flow
let result = 5 -> \(x: int => x * 2) -> \(x: int => x * x)
; result = 100
```

This is equivalent to the named-function version from Section 4.1. In practice, you use named functions for stages that appear in multiple chains and lambdas for one-off transformations.

### 4.3.2 Capturing Values

Lambdas capture variables from the enclosing scope. Immutable values are captured by reference. Mutable values are captured by copy --- a snapshot at the time the lambda is created:

```flow
fn make_adder(n: int): fn(int): int {
    return \(x: int => x + n)   ; captures n by reference (immutable)
}

fn main() {
    let add5 = make_adder(5)
    let result = 10 -> add5      ; 15
}
```

This is how you create specialized functions from general ones. `make_adder` returns a new function that adds a fixed amount. The returned lambda captures `n` and uses it every time it is called.

Capture integrates naturally with composition:

```flow
fn scale_and_offset(factor: int, offset: int): fn(int): int {
    return \(x: int => x * factor + offset)
}

fn main() {
    let transform = scale_and_offset(3, 10)
    let result = 5 -> transform -> \(x: int => x * x)
    ; transform(5) = 5 * 3 + 10 = 25, then square: 625
}
```

### 4.3.3 Lambdas with Higher-Order Functions

Functions that accept other functions as parameters are called **higher-order functions**. They appear frequently in composition chains, especially for filtering and transforming:

```flow
fn filter<T>(pred: fn(T): bool, s: stream<T>): stream<T> {
    for (item: T in s) {
        if (pred(item)) { yield item }
    }
}
```

When you use `filter` in a chain, you pass the predicate as an argument and the stream flows in from the chain:

```flow
; filter(is_valid) is a partial call: the predicate is bound,
; the stream argument comes from the chain
src -> read_lines -> filter(\(line: string => line != ""))
```

The lambda `\(line: string => line != "")` serves as the predicate. It is defined inline, at the point of use, because it is specific to this pipeline.

### 4.3.4 Function Types

Function types describe the signature of a function value. They are written as `fn(param_types): return_type`:

```flow
fn(int): int               ; takes int, returns int
fn(int, int): bool          ; takes two ints, returns bool
fn(string): stream<int>     ; takes string, returns stream of ints
```

You use function types when declaring parameters that accept functions:

```flow
fn apply_twice(x: int, f: fn(int): int): int = x -> f -> f
```

This function takes a value and a function, applies the function twice, and returns the result. The composition chain `x -> f -> f` pushes `x`, applies `f` (consuming `x`, producing a result), then applies `f` again.

```flow
fn main() {
    let result = apply_twice(3, \(x: int => x * 2))
    ; 3 -> double -> double = 12
}
```

Function types make composition modular. You can write generic pipeline stages that accept their behavior as a parameter, then assemble them into specific pipelines at the call site.

---

## 4.4 Parallel Fan-Out (`<:(| |)`)

Fan-out with `|` is sequential: the runtime evaluates branches one after another. When branches are independent and expensive --- calling a remote service, computing a hash, validating against a complex rule --- you want them to run concurrently.

**Parallel fan-out** uses the `<:(...)` syntax:

```flow
fn process(data: record): output =
    data -> <:(validate | compute_hash | extract_id) -> build_output
```

The runtime may schedule each branch on a separate thread. The branches execute concurrently, their results are collected in order, and the next stage receives them exactly as it would with sequential fan-out. From the perspective of the rest of the chain, parallel fan-out behaves identically to sequential fan-out. The difference is performance.

### 4.4.1 Safety Requirements

Concurrent execution introduces the possibility of data races. Flow prevents them with two rules enforced at compile time:

**Rule 1: The input must be immutable.** Since all values in Flow are immutable by default, this is usually satisfied automatically. If you try to pass a `:mut` binding into a parallel fan-out, the compiler rejects it.

**Rule 2: The branch functions must be safe for concurrent execution.** The compiler accepts two kinds of functions in parallel fan-out:

- **Pure functions** (`fn:pure`). These are always safe. They cannot access mutable state, perform I/O, or observe anything outside their parameters. Two pure functions running concurrently on the same immutable input cannot interfere with each other.

- **Non-pure functions** that take only `:imut` parameters and do not access mutable statics. These functions may perform I/O or other effects, but they cannot read or write shared mutable state.

```flow
fn:pure validate(data: record): bool { ... }     ; pure: always safe
fn:pure compute_hash(data: record): int { ... }   ; pure: always safe

fn log_and_extract(data: record): string {        ; not pure, but safe:
    io.log(f"processing {data.id}")               ;   takes immutable input,
    return data.id                                 ;   no mutable statics
}

; All three are safe in parallel fan-out
fn process(data: record): result =
    data -> <:(validate | compute_hash | log_and_extract) -> combine
```

If a branch function accesses a mutable static variable or takes a `:mut` parameter, the compiler rejects the parallel fan-out. You must either make the function pure, restructure to avoid mutable state, or fall back to sequential fan-out.

### 4.4.2 When to Use Parallel Fan-Out

Parallel execution has overhead: thread scheduling, synchronization when collecting results. For cheap functions (arithmetic, field access, simple predicates), sequential fan-out is faster. Use parallel fan-out when individual branches are expensive enough that concurrent execution outweighs the overhead.

Good candidates for parallel fan-out:

- Network calls (validation against an external service)
- Cryptographic operations (hashing, signing)
- Complex computations on large data (statistical analysis, compression)

A useful rule: if each branch takes milliseconds or more, parallel fan-out helps. If branches take microseconds, sequential fan-out is likely faster.

### 4.4.3 Purity and Memoization

The runtime may memoize `pure` function results within a composition chain. If two fan-out branches call the same pure function on the same value, the result is computed once and shared. The cache is per-element and released when the element leaves the pipeline.

This means you can structure your fan-out for clarity without worrying about redundant computation:

```flow
fn:pure extract_name(r: record): string { ... }
fn:pure extract_age(r: record): int { ... }
fn:pure format_entry(name: string, age: int): string {
    return f"{name} ({age})"
}

fn display(r: record): string =
    r -> (extract_name | extract_age) -> format_entry
```

If `extract_name` and `extract_age` share internal sub-computations (both parse the same field, for instance), the runtime can cache and share those results. You write the pipeline for readability; the runtime handles the optimization.

---

## 4.5 Auto-Mapping with Streams

Composition becomes genuinely powerful when combined with streams. A `stream<T>` is a lazy sequence of values produced one at a time. Streams are covered in depth in Chapter 9. Here we introduce the single feature that makes them work seamlessly in composition chains: **auto-mapping**.

### 4.5.1 The Auto-Mapping Rule

When a `stream<T>` flows into a function that expects `T` (not `stream<T>`), the chain automatically maps the function over each element of the stream. The result is a `stream<U>` where `U` is the function's return type.

```flow
fn:pure parse(line: string): record { ... }

; read_lines returns stream<string>
; parse expects string (not stream<string>)
; auto-mapping: parse is applied to each element
; result: stream<record>
src -> read_lines -> parse
```

Without auto-mapping, you would need to write an explicit loop or call a `map` function:

```flow
; Without auto-mapping (hypothetical)
src -> read_lines -> stream.map(parse)
```

Auto-mapping eliminates this boilerplate. Every eager function that takes a `T` and returns a `U` works in a streaming pipeline without modification. You write the function for a single value; composition handles the iteration.

The significance of this rule is easy to understate. In most languages, writing a function that processes one item and writing a function that processes a collection are separate activities. You write `parse(line)` for one string and `lines.map(parse)` for a list of strings. The collection version wraps the single-item version in collection-specific machinery. If you switch from a list to an iterator to a stream, you rewrite the wrapping.

In Flow, you write `parse` for one string. When a `stream<string>` flows into it, the composition chain handles the rest. If you later change the upstream to produce an `array<string>` that is converted to a stream, `parse` does not change. If you add another stage before `parse`, `parse` does not change. Each function is concerned only with its own transformation, and the chain manages how values get to it.

### 4.5.2 What Auto-Maps and What Does Not

The rule is precise. Auto-mapping fires when the chain passes a `stream<T>` to a function whose parameter type is `T`. Functions that already expect a stream receive it directly:

```flow
fn:pure parse(line: string): record { ... }
fn is_valid(r: record): bool { ... }
fn filter<T>(pred: fn(T): bool, s: stream<T>): stream<T> { ... }
fn count<T>(s: stream<T>): int { ... }

fn pipeline(src: string): int =
    src -> read_lines -> parse -> filter(is_valid) -> count
```

Here is what happens at each stage:

| Stage | Input type | Function signature | Auto-map? | Output type |
|-------|------------|--------------------|-----------|-------------|
| `read_lines` | `string` | `fn(string): stream<string>` | No | `stream<string>` |
| `parse` | `stream<string>` | `fn(string): record` | Yes | `stream<record>` |
| `filter(is_valid)` | `stream<record>` | `fn(fn(T): bool, stream<T>): stream<T>` | No | `stream<record>` |
| `count` | `stream<record>` | `fn(stream<T>): int` | No | `int` |

`parse` is auto-mapped because it takes `string` but receives `stream<string>`. `filter` and `count` take `stream<T>` directly, so they receive the stream as-is.

This distinction is what makes composition pipelines ergonomic. You do not need two versions of every function --- one for single values and one for streams. A function that works on one value works on a stream of values, automatically.

### 4.5.3 Fan-Out with Streams

Fan-out in a streaming context applies at the element level. Each element independently fans into all branches:

```flow
fn:pure extract_id(line: string): string { ... }
fn:pure parse_body(line: string): body { ... }
fn:pure build_record(id: string, body: body): record { ... }

fn process(src: string): stream<record> =
    src -> read_lines -> (extract_id | parse_body) -> build_record
```

For each string in the stream, `extract_id` and `parse_body` are both called. Their results feed `build_record`. The output is a `stream<record>` --- one record per input line.

This is auto-mapping and fan-out combined. The stream distributes elements; fan-out distributes each element to multiple functions; the results are collected and passed downstream. The chain reads as a description of what happens to each element.

### 4.5.4 Chaining Multiple Auto-Mapped Stages

Multiple auto-mapped stages can appear consecutively in a chain. Each one transforms the stream element-by-element:

```flow
fn:pure trim_whitespace(s: string): string { ... }
fn:pure to_lowercase(s: string): string { ... }
fn:pure parse_int(s: string): int { ... }

fn pipeline(src: string): stream<int> =
    src -> read_lines -> trim_whitespace -> to_lowercase -> parse_int
```

`read_lines` produces a `stream<string>`. `trim_whitespace`, `to_lowercase`, and `parse_int` are all auto-mapped in sequence. Each takes a single value and produces a single value; the stream threading is implicit. The result is a `stream<int>`.

Compare this with the equivalent in a language without auto-mapping:

```
lines = read_lines(src)
trimmed = lines.map(trim_whitespace)
lowered = trimmed.map(to_lowercase)
parsed = lowered.map(parse_int)
```

Four statements, four temporary variables, four explicit `.map` calls. The Flow version is one line that reads as a sequence of transformations. The difference compounds with pipeline length.

---

## 4.6 Building Real Pipelines

The preceding sections introduced composition features in isolation. This section combines them into complete, working programs.

### 4.6.1 A Text Processing Pipeline

The following program takes a sentence, splits it into words, normalizes each word, filters out short words, and prints the results:

```flow
module text_pipeline
import io (println)
import string (split, trim, to_upper)

fn:pure normalize(word: string): string = to_upper(trim(word))

fn:pure is_long(word: string): bool = string.len(word) > 3

fn words(text: string): stream<string> {
    let parts = split(text, " ")
    for (w: string in parts) {
        yield w
    }
}

fn main() {
    let text = "  the quick brown fox jumps over the lazy dog  "

    ; Composition pipeline: split into words, normalize, filter, print
    for (w: string in text -> words -> normalize -> filter(is_long)) {
        println(w)
    }
}
```

Trace through the pipeline:

1. `text -> words` splits the string into a `stream<string>` of individual words.
2. `-> normalize` is auto-mapped: `normalize` takes `string`, receives `stream<string>`, so it is applied to each element. Result: `stream<string>` of uppercased, trimmed words.
3. `-> filter(is_long)` receives `stream<string>` directly (no auto-map). It yields only words longer than 3 characters.
4. The `for` loop consumes the resulting stream and prints each word.

Output:

```
QUICK
BROWN
JUMPS
OVER
LAZY
```

Notice that `normalize` was written for a single string. It knows nothing about streams. Composition made it work in a streaming context without modification.

### 4.6.2 A Data Validation Pipeline

Fan-out is natural for validation: run multiple checks on the same input and combine the results.

```flow
module validation
import io (println)
import string (len, contains)

fn:pure check_length(s: string): bool = len(s) > 0

fn:pure check_format(s: string): bool = contains(s, "@")

fn:pure combine_checks(a: bool, b: bool): bool = a && b

fn:pure validate_email(email: string): bool =
    email -> (check_length | check_format) -> combine_checks

fn main() {
    println(f"test@example.com: {validate_email(\"test@example.com\")}")
    println(f"empty string: {validate_email(\"\")}")
    println(f"no-at-sign: {validate_email(\"no-at-sign\")}")
}
```

`validate_email` fans the input to two checks and combines the results. Adding a third check requires only adding a branch and updating the combiner:

```flow
fn:pure check_has_dot(s: string): bool = contains(s, ".")

fn:pure combine3(a: bool, b: bool, c: bool): bool = a && b && c

fn:pure validate_email(email: string): bool =
    email -> (check_length | check_format | check_has_dot) -> combine3
```

The pipeline grows by adding stages, not by restructuring existing code. Each check is independent, testable in isolation, and reusable in other pipelines.

This pattern --- fan-out to multiple validators, combine results --- appears frequently in real applications. Form validation, data quality checks, configuration verification: any situation where multiple independent conditions must all hold. The fan-out makes the independence of the checks explicit. The combiner makes the aggregation policy explicit. Changing from "all must pass" to "at least one must pass" means changing the combiner, not the checks:

```flow
fn:pure any_check(a: bool, b: bool): bool = a || b

fn:pure passes_either(email: string): bool =
    email -> (check_length | check_format) -> any_check
```

### 4.6.3 Numeric Transformations

Composition handles numeric processing naturally:

```flow
module numeric_pipeline
import io (println)
import math (abs)

fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
fn:pure add(x: int, y: int): int = x + y
fn:pure sub(x: int, y: int): int = x - y

fn main() {
    ; Pipeline: double and square 5, then add the results
    let a = 5 -> (double | square) -> add
    println(f"(double | square) -> add: {a}")  ; 35

    ; Longer pipeline: different transforms, subtract, absolute value
    let b = 7 -> (double | square) -> sub -> abs
    println(f"(double | square) -> sub -> abs: {b}")  ; |14 - 49| = 35

    ; Multi-value pipeline
    let c = 3 -> 4 -> add -> double -> square
    println(f"3 -> 4 -> add -> double -> square: {c}")  ; square(double(7)) = 196
}
```

### 4.6.4 Combining Patterns

Real programs use linear composition, fan-out, lambdas, and auto-mapping together. Here is a pipeline that processes a list of numbers:

```flow
module combined_pipeline
import io (println)

fn:pure double(x: int): int = x * 2
fn:pure is_positive(x: int): bool = x > 0

fn numbers(): stream<int> {
    let data = [-3, -1, 0, 2, 4, 7, -5, 10]
    for (n: int in data) {
        yield n
    }
}

fn:pure sum_stream(s: stream<int>): int {
    let total: int:mut = 0
    for (n: int in s) {
        total += n
    }
    return total
}

fn main() {
    ; Double each number, keep positives, sum them
    let result = numbers() -> double -> filter(is_positive) -> sum_stream
    println(f"sum of positive doubles: {result}")
    ; doubles: [-6, -2, 0, 4, 8, 14, -10, 20]
    ; positives: [4, 8, 14, 20]
    ; sum: 46
}
```

The pipeline reads as a sentence: take the numbers, double each one, filter to keep positives, sum the result. Each stage is a small function. Each function is testable independently. The composition chain connects them.

---

## 4.7 Composition and Purity

Chapter 3 introduced pure functions and the `fn:pure` annotation. Composition is where purity pays off.

### 4.7.1 Pure Pipelines

A composition chain where every stage is pure is itself pure. The compiler can verify this, optimize aggressively, and guarantee that the chain has no side effects:

```flow
fn:pure double(x: int): int = x * 2
fn:pure square(x: int): int = x * x
fn:pure add(x: int, y: int): int = x + y

fn:pure transform(x: int): int = x -> (double | square) -> add
```

`transform` can be marked `fn:pure` because every function it calls is pure. If you tried to include a non-pure function in the chain, the compiler would reject the `fn:pure` annotation.

Pure pipelines are safe to:

- **Memoize**: call with the same input, get the same output, skip the computation.
- **Parallelize**: run in parallel fan-out without synchronization.
- **Reorder**: the compiler can rearrange stages if it can prove the result is unchanged (though it rarely needs to).

### 4.7.2 Mixed Pipelines

Not every pipeline is pure. I/O, logging, network calls --- these are effects, and they belong in pipelines too. The key is that purity is tracked per-function, not per-pipeline:

```flow
fn:pure parse(line: string): record { ... }
fn:pure validate(r: record): bool { ... }
fn save(r: record): record { ... }         ; not pure: writes to disk

fn pipeline(src: string): stream<record> =
    src -> read_lines -> parse -> filter(validate) -> save
```

`parse` and `validate` are pure. `save` is not. The pipeline as a whole is not pure, but the compiler still knows which stages are safe to cache, safe to parallelize, and safe to reason about in isolation. The pure stages get the benefits of purity; the impure stages are clearly marked by the absence of `fn:pure`.

---

## 4.8 What Goes Wrong

### 4.8.1 Arity Mismatch

The most common composition error is an arity mismatch --- the number of values on the stack does not match the function's parameter count:

```flow
fn:pure add(x: int, y: int): int = x + y

let bad = 5 -> add   ; compile error: add expects 2 arguments, stack has 1
```

The fix: ensure the right number of values are on the stack before the function. Either push another value or use a different function:

```flow
let good = 5 -> 10 -> add     ; add(5, 10) = 15
```

### 4.8.2 Fan-Out Arity Mismatch

A fan-out group produces as many values as it has branches. The next function must accept exactly that many:

```flow
fn:pure mul(x: int, y: int): int = x * y

fn bad(x: int): int = x -> (double | square | negate) -> mul
; compile error: fan-out produces 3 values, mul takes 2
```

The fix: match the number of branches to the consuming function's arity, or change the consuming function:

```flow
fn:pure sum3(a: int, b: int, c: int): int = a + b + c

fn good(x: int): int = x -> (double | square | negate) -> sum3
```

### 4.8.3 Type Mismatch in Chain

Each stage's output type must match the next stage's input type:

```flow
fn:pure double(x: int): int = x * 2
fn:pure to_upper(s: string): string { ... }

let bad = 5 -> double -> to_upper  ; compile error: to_upper expects string, got int
```

The chain produces an `int` from `double`, but `to_upper` expects a `string`. The compiler reports this as a type error at the exact stage where the mismatch occurs.

The fix: insert a conversion or use a function with the right type:

```flow
fn:pure to_string(x: int): string { ... }

let good = 5 -> double -> to_string -> to_upper
```

### 4.8.4 Mutable Input to Parallel Fan-Out

Parallel fan-out requires immutable input:

```flow
let data: record:mut = get_record()
let bad = data -> <:(validate | hash)   ; compile error: mutable input to parallel fan-out
```

The fix: use an immutable binding, or make a copy:

```flow
let data: record = get_record()          ; immutable by default
let good = data -> <:(validate | hash)   ; ok
```

### 4.8.5 Impure Function in Parallel Fan-Out

Functions in parallel fan-out must be pure or must not access mutable statics:

```flow
let counter: int:mut = 0

fn increment_counter(x: record): record {
    counter += 1    ; accesses mutable static
    return x
}

let bad = data -> <:(validate | increment_counter)
; compile error: increment_counter accesses mutable state
```

The fix: restructure to avoid mutable shared state, or use sequential fan-out:

```flow
; Sequential fan-out: no concurrency, no data race risk
let ok = data -> (validate | increment_counter) -> combine
```

### 4.8.6 Reading Error Messages

The compiler's error messages for composition chains include the stage number and the types involved. When you see an error like:

```
TypeError: composition stage 3: expected fn(int): _, got fn(string): string
```

count the stages from left to right in your chain. Stage 1 is the first value or function after the initial push. Stage 3 is three steps in. The error tells you the type that arrived at that stage and the type the function expected. This is usually enough to locate the mismatch.

For fan-out errors, the message includes the branch count and the consuming function's arity:

```
TypeError: fan-out produces 3 values, but next function takes 2 parameters
```

These errors are always static. You will never encounter a composition type error at runtime. If the program compiles, the types align at every stage.

---

## 4.9 Thinking in Pipelines

Composition is not a feature you bolt onto programs written in another style. It is a way of thinking about program structure.

### 4.9.1 Decompose Into Stages

When you approach a problem, think about the transformations the data undergoes. Each transformation is a stage. Each stage is a function. The pipeline connects them.

Consider parsing a CSV file:

1. Read lines from the file.
2. Skip the header line.
3. Split each line by commas.
4. Parse each field into a typed record.
5. Validate each record.
6. Collect valid records.

Each step is a function. The pipeline is:

```flow
path -> read_lines -> stream.skip(1) -> split_fields -> parse_record
     -> filter(is_valid) -> buffer.collect
```

You did not need to think about loops, intermediate variables, or error accumulation. You described the transformation, and composition assembled it.

### 4.9.2 Test Each Stage

Because each stage is an independent function, you can test it independently:

```flow
; Test parse_record on a single line
let record = parse_record("Alice,30,Engineering")
assert(record.name == "Alice")
assert(record.age == 30)

; Test is_valid on a single record
assert(is_valid(record) == true)
assert(is_valid(Record { name: "", age: -1, dept: "" }) == false)
```

You do not need to set up a file, read lines, or build a full pipeline to test one stage. This is the practical benefit of composition: small functions, small tests, confidence that the pipeline works because each piece works.

### 4.9.3 Reuse Across Pipelines

A function written for one pipeline works in any pipeline that needs the same transformation. `normalize` from Section 4.6.1 works anywhere you need to uppercase and trim a string. `validate_email` from Section 4.6.2 works anywhere you need email validation. You build a library of stages and assemble them into new pipelines as needed.

This is what "composition-first" means. The primary unit of reuse in Flow is the function. The primary mechanism of assembly is the arrow. Programs grow by adding stages, not by extending classes or configuring frameworks.

### 4.9.4 Evolving a Pipeline

Pipelines evolve by adding, removing, or replacing stages. Consider a pipeline that reads log entries and counts errors:

```flow
fn count_errors(path: string): int =
    path -> read_lines -> parse_log_entry -> filter(is_error) -> count
```

Requirements change. Now you need to count only errors from the last 24 hours. You add a stage:

```flow
fn count_recent_errors(path: string): int =
    path -> read_lines -> parse_log_entry -> filter(is_recent) -> filter(is_error) -> count
```

One stage added, nothing else changed. `parse_log_entry`, `is_error`, and `count` are untouched. The original `count_errors` still works and can remain in the codebase for cases that do not need the recency filter.

Now you need to deduplicate entries before counting:

```flow
fn count_unique_recent_errors(path: string): int =
    path -> read_lines -> parse_log_entry -> filter(is_recent)
         -> filter(is_error) -> deduplicate -> count
```

Another stage added. The pipeline grows linearly with requirements. There is no explosion of intermediate types, no redesign of a class hierarchy, no refactoring of nested control flow. Each requirement maps to a stage, and the chain connects them.

### 4.9.5 Reading Composition Chains

When you encounter a composition chain in code you did not write, read it left to right. Each `->` is a step. Each function name describes what happens at that step. The types flow forward: the output type of each stage is the input type of the next.

If the chain is long, look at the first and last stages. The first stage tells you what the pipeline starts with. The last stage tells you what it produces. The stages in between are the transformation. A chain like:

```flow
path -> read_lines -> parse -> validate -> transform -> serialize -> write_output
```

starts with a file path and ends by writing output. The middle stages parse, validate, transform, and serialize. You can understand the pipeline's purpose without reading any function body. When you need to understand a specific stage, you read that one function --- not the entire pipeline.

---

## 4.10 Summary

The `->` operator is the foundation of Flow programming. It chains values and functions left to right, replacing nested calls with sequential reading.

The **value stack** model governs how values flow through a chain. Values are pushed; functions consume by arity and push their result. The compiler checks arity statically.

**Fan-out** (`|`) splits one value to multiple functions. The results are collected and passed to the next stage. The compiler checks that the number of branches matches the consuming function's arity.

**Parallel fan-out** (`<:(|)`) runs branches concurrently. Input must be immutable. Branch functions must be pure or must not access mutable statics.

**Auto-mapping** bridges eager functions and streams. When a `stream<T>` flows into a function expecting `T`, the function is applied to each element. Every eager function works in a streaming pipeline without modification.

**Lambdas** provide inline functions for one-off transformations. They capture values from the enclosing scope and participate in composition chains like any other function.

**Purity** compounds through composition. Pure pipelines are safe to memoize, parallelize, and reason about locally.

The composition model encourages a specific way of building programs: decompose into small stages, connect them with arrows, test each stage independently, reuse stages across pipelines. This is not the only way to write Flow programs, but it is the way the language was designed to be used.

---

## Exercises

**1.** Write a program with a function `sum3(a: int, b: int, c: int): int` that adds three values. Use it with a three-branch fan-out:

```flow
let result = 5 -> (triple | square | negate) -> sum3
```

where `triple(x) = x * 3`, `square(x) = x * x`, and `negate(x) = 0 - x`. Verify that the result is `15 + 25 + (-5) = 35`.

**2.** Build a pipeline that takes a sentence as a string, splits it into words, filters out words with 3 or fewer characters, and joins the remaining words back into a string separated by spaces. Use composition throughout.

**3.** Rewrite the following nested expression as a composition chain:

```flow
let result = to_string(abs(negate(double(square(3)))))
```

Verify that both produce the same result.

**4.** Build a validation pipeline with fan-out that checks three properties of a username string: length is at least 3 characters, length is at most 20 characters, and the string does not contain a space. Write a `validate_username` function that uses a three-branch fan-out and a `combine3` function. Test it with valid and invalid inputs.

**5.** (Challenge) Write a program that processes an array of integers through a composition pipeline: double each number, filter to keep only positive values, and sum the result. Use a function that yields elements from the array to create a stream, auto-mapping for the doubling stage, `filter` for the predicate, and a summing function that consumes the stream. Test with the input `[-3, -1, 0, 2, 4, 7, -5, 10]` and verify the result is `46`.
