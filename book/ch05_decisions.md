# Chapter 5: Making Decisions

Every program past "hello world" needs to choose. Given some input, take one path or another. Given some data, classify it. Given a result, handle the success or deal with the failure.

Flow has three tools for this: `if`/`else`, `match`, and `if let`. It also has two looping constructs: `while` and `for`. This chapter covers all of them.

---

## 5.1 If and Else

The basic conditional looks like every other C-family language:

```flow
fn main() {
    let score = 85

    if (score >= 90) {
        println("excellent")
    } else if (score >= 70) {
        println("good")
    } else {
        println("needs work")
    }
}
```

Parentheses around the condition are required. Braces around the body are required. There is no ambiguity about where the body ends, no dangling-else problem, no need for a convention about single-line bodies. The braces are the convention.

You can chain as many `else if` branches as you need:

```flow
fn classify(temp: float): string {
    if (temp < 0.0) {
        return "freezing"
    } else if (temp < 20.0) {
        return "cold"
    } else if (temp < 30.0) {
        return "warm"
    } else {
        return "hot"
    }
}
```

There is no `elif` or `elsif` keyword. It is always `else if`, two words.

### 5.1.1 If as an Expression

When both branches of an `if`/`else` produce a value of the same type, the entire construct is an expression. You can bind its result:

```flow
fn main() {
    let score = 85
    let grade: string = if (score >= 90) { "A" } else if (score >= 80) { "B" } else { "C" }
    println(grade)
}
```

The last expression in each branch is the value produced by that branch. There is no `return` here --- the block evaluates to its final expression. Both branches must produce the same type. If one branch produces a `string` and the other produces an `int`, the compiler rejects it.

When used as an expression, the `else` branch is mandatory. Without it, the compiler cannot know what value to produce when the condition is false.

```flow
; This is fine --- statement form, no value needed
if (debug) {
    println("debug mode")
}

; This is a compile error --- expression form needs else
; let msg: string = if (debug) { "debug mode" }
```

Expression-form `if` is useful for short, value-producing conditionals. For longer logic with side effects, statement form with explicit `return` reads better.

### 5.1.2 The Ternary Operator

For simple two-way choices, Flow provides the ternary operator:

```flow
fn main() {
    let a = 10
    let b = 20
    let max = a > b ? a : b
    println(f"max: {max}")
}
```

This is shorthand for `if (a > b) { a } else { b }`. The types on both sides of `:` must match, just like expression `if`.

A few common uses:

```flow
fn main() {
    let x = -5
    let abs = x < 0 ? -x : x          ; absolute value
    let sign = x > 0 ? "+" : "-"       ; sign label
    let clamped = x > 100 ? 100 : x    ; upper bound
    println(f"abs={abs} sign={sign} clamped={clamped}")
}
```

The ternary operator nests, but nested ternaries are hard to read. If you find yourself writing `a ? b ? c : d : e`, use `if`/`else if`/`else` instead. The ternary is for the simple case. Let it stay simple.

---

## 5.2 Pattern Matching with `match`

`if`/`else` chains work, but they get awkward when you are testing one value against many possibilities. `match` is the direct tool for that job.

```flow
fn describe(n: int): string {
    return match n {
        0: "zero",
        1: "one",
        2: "two",
        _: "many"
    }
}

fn main() {
    println(describe(0))
    println(describe(2))
    println(describe(99))
}
```

A `match` expression takes a value and tests it against a series of **arms**. Each arm has a pattern, a colon, and a body. Arms are separated by commas. The first arm whose pattern matches wins; its body evaluates and becomes the result of the entire `match`.

The colon is the separator. Not `=>`, not `->`. Just `:`.

`match` is an expression. Like `if`/`else`, it produces a value when every arm produces the same type. You can bind the result, return it, or pass it directly to a function:

```flow
fn main() {
    let n = 7
    let word = match n {
        0: "zero",
        1: "one",
        _: "many"
    }
    println(word)
}
```

### 5.2.1 Matching Literals

The simplest patterns are literal values:

```flow
fn day_type(day: string): string {
    return match day {
        "Saturday": "weekend",
        "Sunday": "weekend",
        _: "weekday"
    }
}

fn main() {
    println(day_type("Monday"))
    println(day_type("Saturday"))
}
```

Each arm is tested in order. `"Saturday"` is checked first, then `"Sunday"`, then `_`. The underscore is the **wildcard** --- it matches anything. Once an arm matches, no further arms are tested.

Order matters. If you put `_` first, it matches everything, and no subsequent arm is ever reached. The wildcard always goes last.

Arms can have block bodies when you need multiple statements:

```flow
fn describe_number(n: int): string {
    match n {
        0: { return "zero" }
        1: { return "one" }
        _: { return "other" }
    }
}
```

When used as an expression (bound to a variable or returned), each arm produces a value and all arms must produce the same type. When used as a statement, each arm can have side effects and does not need to produce a value.

The distinction between expression and statement form follows the same rule as `if`/`else`: if the result is being consumed (assigned, returned, passed as an argument), it is an expression and every arm must produce the same type. If `match` stands alone as a statement, the arms can do whatever they want.

### 5.2.2 Matching on Bool

Booleans have exactly two values, and `match` knows it:

```flow
fn label(active: bool): string {
    return match active {
        true: "active",
        false: "inactive"
    }
}

fn main() {
    println(label(true))
    println(label(false))
}
```

No wildcard needed. `true` and `false` cover every possible boolean value. The compiler knows the match is exhaustive.

This is occasionally clearer than `if`/`else` when you want to emphasize that you are dispatching on a boolean value rather than testing a condition.

### 5.2.3 Binding Patterns

The real power of `match` appears with sum types. Consider a type that represents geometric shapes:

```flow
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)

fn area(s: Shape): float {
    return match s {
        Circle(r): 3.14159 * r * r,
        Rectangle(w, h): w * h
    }
}

fn main() {
    let c = Circle(5.0)
    let r = Rectangle(3.0, 4.0)
    println(f"circle: {area(c)}")
    println(f"rectangle: {area(r)}")
}
```

When you write `Circle(r)`, the pattern does two things. It checks whether `s` is a `Circle`, and if so, it **binds** the circle's radius to the variable `r` inside the arm body. The name `r` is your choice --- it does not have to match the field name in the type definition.

Similarly, `Rectangle(w, h)` binds the width and height to `w` and `h`. The bindings are positional: `w` gets the first field, `h` gets the second.

You can choose any variable names:

```flow
fn describe(s: Shape): string {
    return match s {
        Circle(radius): f"circle with radius {radius}",
        Rectangle(width, height): f"{width} by {height} rectangle"
    }
}
```

If you do not need a field, use `_` in its position:

```flow
fn is_square(s: Shape): bool {
    return match s {
        Circle(_): false,
        Rectangle(w, h): w == h
    }
}
```

Binding patterns only appear inside variant constructors. You cannot write `x: Circle(r)` as you might in some other languages. The pattern is just the constructor and its positional fields.

### 5.2.4 Wildcard Patterns

The underscore `_` matches anything and binds nothing. It serves two roles.

First, as a positional placeholder inside a binding pattern, as shown above with `Circle(_)`.

Second, as a catch-all arm at the end of a match:

```flow
fn category(code: int): string {
    return match code {
        200: "success",
        301: "redirect",
        404: "not found",
        500: "server error",
        _: "unknown"
    }
}
```

For types where the compiler cannot verify exhaustiveness --- integers, floats, strings --- the wildcard is how you handle "everything else." Without it, the compiler issues a warning: there are values you have not covered, and hitting one at runtime will be an error.

### 5.2.5 Exhaustiveness

Flow's compiler checks that every `match` covers all possible values of the matched type. The rules depend on the type.

**Sum types** must be fully covered. Every variant must appear in an arm, or a wildcard `_` must be present. Omitting a variant without a wildcard is a compile error, not a warning:

```flow
type Color = | Red | Green | Blue

fn name(c: Color): string {
    return match c {
        Red: "red",
        Green: "green"
        ; compile error: Blue not handled
    }
}
```

Fix it by adding the missing variant or a wildcard:

```flow
fn name(c: Color): string {
    return match c {
        Red: "red",
        Green: "green",
        Blue: "blue"
    }
}

; Or:
fn name_short(c: Color): string {
    return match c {
        Red: "red",
        _: "other"
    }
}
```

**Booleans** work the same way: `true` and `false` cover all cases. Add both or use `_`.

**Option types** have exactly two cases, `some(v)` and `none`:

```flow
fn unwrap_or_default(opt: option<int>): int {
    return match opt {
        some(v): v,
        none: 0
    }
}
```

**Result types** have exactly two cases, `ok(v)` and `err(e)`:

```flow
fn to_string(res: result<int, string>): string {
    return match res {
        ok(v): f"value: {v}",
        err(e): f"error: {e}"
    }
}
```

**Primitives and strings** cannot be exhaustively checked at compile time. The compiler cannot know whether you have covered every possible integer. If you match on an `int` without a wildcard, the compiler warns you. A value that reaches the match at runtime without hitting any arm produces a runtime error. Use `_` to handle the default case explicitly:

```flow
fn fizzbuzz(n: int): string {
    ; This needs a wildcard --- the compiler cannot know all ints are covered
    let mod3 = n % 3 == 0
    let mod5 = n % 5 == 0
    return match true {
        _ : {
            if (mod3 && mod5) {
                return "fizzbuzz"
            } else if (mod3) {
                return "fizz"
            } else if (mod5) {
                return "buzz"
            } else {
                return f"{n}"
            }
        }
    }
}
```

A cleaner version uses `if`/`else` directly. The point is: when matching on open-ended types, always include `_`.

Here is a summary of what the compiler requires:

| Matched type | Exhaustiveness rule |
|---|---|
| Sum type | All variants, or `_`. Missing variant = compile error. |
| `bool` | `true` and `false`, or `_`. Missing case = compile error. |
| `option<T>` | `some(v)` and `none`, or `_`. Missing case = compile error. |
| `result<T, E>` | `ok(v)` and `err(e)`, or `_`. Missing case = compile error. |
| `int`, `float`, `string` | Cannot be fully checked. Missing `_` = compile warning. Missing match at runtime = runtime error. |

### 5.2.6 Matching on Tuples

Tuples can be destructured in match arms:

```flow
fn describe_pair(t: (int, int)): string {
    return match t {
        (0, 0): "origin",
        (x, 0): f"x-axis at {x}",
        (0, y): f"y-axis at {y}",
        (x, y): f"point at ({x}, {y})"
    }
}
```

Each position in the tuple pattern is itself a pattern: it can be a literal, a binding variable, or `_`. The arms are tested in order, so more specific patterns should come before more general ones. The final `(x, y)` arm here catches everything, acting as the wildcard for the tuple type.

This is how you write a clean FizzBuzz in Flow. Rather than nested `if`/`else`, you compute two boolean flags and match on the pair:

```flow
fn fizzbuzz(n: int): string {
    return match (n % 3 == 0, n % 5 == 0) {
        (true, true): "fizzbuzz",
        (true, false): "fizz",
        (false, true): "buzz",
        (false, false): f"{n}"
    }
}
```

Four arms, four cases, no nesting. The compiler knows `(bool, bool)` has exactly four combinations, so no wildcard is needed.

---

## 5.3 Conditional Binding with `if let`

Full `match` is thorough, but sometimes you only care about one case. You want to check whether an option has a value and use it, or check whether a result succeeded and process the data. Writing a full `match` with an empty arm for the case you don't care about is tedious.

`if let` handles this:

```flow
fn main() {
    let names = ["alice", "bob", "carol"]
    let found: option<string> = find_name(names, "bob")

    if (let some(name) = found) {
        println(f"found: {name}")
    } else {
        println("not found")
    }
}

fn find_name(names: array<string>, target: string): option<string> {
    for (name: string in names) {
        if (name == target) {
            return some(name)
        }
    }
    return none
}
```

The syntax is `if (let pattern = expr)`. If the expression matches the pattern, the body executes with the bound variables in scope. If it does not match, the `else` branch runs (if present).

### Options

The most common use of `if let` is unwrapping options:

```flow
fn greet_user(id: int) {
    if (let some(user) = find_user(id)) {
        println(f"hello, {user}")
    }
    ; if find_user returns none, nothing happens
}
```

Without `if let`, you would write:

```flow
fn greet_user(id: int) {
    match find_user(id) {
        some(user): { println(f"hello, {user}") }
        none: {}
    }
}
```

The `if let` version is shorter, reads more naturally, and avoids the empty `none: {}` arm.

### Results

`if let` works with results too:

```flow
fn process_file(path: string) {
    if (let ok(data) = read_file(path)) {
        println(f"read {string.length(data)} bytes")
    } else {
        println(f"could not read {path}")
    }
}
```

You can also match on the error side:

```flow
fn validate_and_log(input: string) {
    if (let err(e) = validate(input)) {
        println(f"validation failed: {e}")
    }
    ; if validation succeeded, nothing to log
}
```

### When to Use `if let` vs. `match`

Use `if let` when you only care about one variant: "if this is `some`, do something" or "if this is `err`, log it." Use `match` when you need to handle every case, or when you have three or more variants to dispatch on.

`if let` is syntactic sugar. The compiler translates it into a `match` internally:

- `if (let some(x) = expr) { body }` becomes `match expr { some(x): { body }, none: {} }`
- `if (let ok(x) = expr) { body } else { alt }` becomes `match expr { ok(x): { body }, err(_): { alt } }`
- `if (let err(e) = expr) { body }` becomes `match expr { err(e): { body }, ok(_): {} }`

The same exhaustiveness and type rules apply. There is no magic.

### Nesting `if let`

Because `if let` is a regular `if` statement with a pattern in its condition, you can nest them:

```flow
fn process(raw: string) {
    if (let ok(parsed) = parse(raw)) {
        if (let some(header) = find_header(parsed)) {
            println(f"header: {header}")
        } else {
            println("no header found")
        }
    } else {
        println("parse failed")
    }
}
```

This is the natural pattern for chaining fallible operations where each step depends on the previous one. It nests, but the nesting is honest --- each level corresponds to a real decision point. Chapter 7 introduces the `?` operator and result composition, which flatten these chains. For now, nesting works.

---

## 5.4 Loops

Flow has two loop constructs: `while` for condition-based repetition, and `for` for iteration over collections.

### 5.4.1 `while` Loops

A `while` loop repeats its body as long as a condition holds:

```flow
fn main() {
    let i: int:mut = 0
    while (i < 5) {
        println(f"{i}")
        i = i + 1
    }
}
```

Output:

```
0
1
2
3
4
```

The condition is checked before each iteration. If it is false initially, the body never executes.

The loop variable `i` is declared `:mut` because the loop needs to modify it. Immutable variables cannot be reassigned, so `let i: int = 0` followed by `i = i + 1` would be a compile error. This is intentional. Flow makes you be explicit about where mutation happens.

### 5.4.2 `for` Loops and Iteration

A `for` loop iterates over a collection:

```flow
fn main() {
    let numbers = [10, 20, 30]
    for (n: int in numbers) {
        println(f"{n}")
    }
}
```

Output:

```
10
20
30
```

The loop variable `n` is bound to each element in turn. The type annotation on the loop variable is required. Within the body, `n` is immutable --- you cannot modify the element you are iterating over.

`for` works with arrays:

```flow
fn sum(values: array<int>): int {
    let total: int:mut = 0
    for (v: int in values) {
        total = total + v
    }
    return total
}

fn main() {
    let nums = [1, 2, 3, 4, 5]
    println(f"sum: {sum(nums)}")
}
```

Later chapters cover `for` with streams and in composition chains. For now, arrays are enough.

A common question: can you iterate over a range of integers without building an array? Not with `for` alone. Flow's `for` takes a collection, not a range expression. To count from 1 to 10, use `while`:

```flow
fn main() {
    let i: int:mut = 1
    while (i <= 10) {
        println(f"{i}")
        i = i + 1
    }
}
```

Or build a utility function that returns an array:

```flow
fn range(start: int, end: int): array<int> {
    let result: array<int>:mut = []
    let i: int:mut = start
    while (i <= end) {
        result = array.push(result, i)
        i = i + 1
    }
    return result
}

fn main() {
    for (n: int in range(1, 10)) {
        println(f"{n}")
    }
}
```

Chapter 9 introduces streams, which provide a lazy alternative that does not allocate the entire range in memory.

### 5.4.3 `break` and `continue`

`break` exits the innermost loop immediately. `continue` skips the rest of the current iteration and moves to the next.

```flow
fn main() {
    ; Print numbers 1-10, skipping 5, stopping at 8
    let i: int:mut = 0
    while (true) {
        i = i + 1
        if (i == 5) { continue }
        if (i > 8) { break }
        println(f"{i}")
    }
}
```

Output:

```
1
2
3
4
6
7
8
```

`break` and `continue` apply to the innermost enclosing loop. In nested loops, they affect only the inner one:

```flow
fn main() {
    let i: int:mut = 0
    while (i < 3) {
        i = i + 1
        let j: int:mut = 0
        while (j < 3) {
            j = j + 1
            if (j == 2) { continue }  ; skips j==2, not the outer loop
            println(f"({i}, {j})")
        }
    }
}
```

A common idiom is `while (true)` with `break` for loops where the exit condition is tested in the middle:

```flow
fn read_until_quit() {
    while (true) {
        let line = io.read_line()
        if (line == "quit") { break }
        if (line == "") { continue }
        process(line)
    }
}
```

### 5.4.4 Loop Finally Blocks

Both `while` and `for` support an optional `finally` block that runs exactly once when the loop exits, regardless of how it exits:

```flow
fn main() {
    let data = [1, 2, 3, 0, 5, 6]
    let count: int:mut = 0

    for (item: int in data) {
        if (item == 0) { break }
        count = count + 1
    } finally {
        println(f"processed {count} items before stopping")
    }
}
```

Output:

```
processed 3 items before stopping
```

The `finally` block runs after:
- **Normal exhaustion** --- the collection runs out of elements or the `while` condition becomes false.
- **`break`** --- the loop exits early.
- **`continue` on the final iteration** --- the iteration ends, and so does the loop.

This is useful for cleanup. If a loop opens a resource, `finally` is where you close it:

```flow
fn process_lines(path: string) {
    let handle = file.open(path)
    for (line: string in handle) {
        if (line == "END") { break }
        process(line)
    } finally {
        handle.close()
    }
}
```

Whether the loop reads every line or hits `break` early, `handle.close()` runs. Without `finally`, you would need to close the handle after the loop and also inside the `break` path --- duplication that invites bugs.

Note the difference between loop `finally` and exception handling `finally` (covered in Chapter 7). Loop `finally` runs when the loop exits. Exception `finally` runs when a `try` block completes. They are separate mechanisms that happen to share a keyword because they serve the same purpose: guaranteed cleanup.

`while` loops use `finally` the same way:

```flow
fn poll_until_done() {
    let attempts: int:mut = 0
    while (true) {
        attempts = attempts + 1
        let status = check_status()
        if (status == "done") { break }
        if (attempts > 100) { break }
    } finally {
        println(f"polled {attempts} times")
    }
}
```

---

## 5.5 Putting It Together

The constructs in this chapter --- `if`/`else`, `match`, `if let`, `while`, `for`, `break`, `continue`, `finally` --- combine naturally. Most real programs use several of them in the same function. The following examples show how they work together.

```flow
type Grade =
    | Excellent
    | Good
    | NeedsWork

fn classify(score: int): Grade {
    if (score >= 90) {
        return Excellent
    } else if (score >= 70) {
        return Good
    } else {
        return NeedsWork
    }
}

fn label(g: Grade): string {
    return match g {
        Excellent: "A",
        Good: "B",
        NeedsWork: "C"
    }
}

fn main() {
    let scores = [95, 82, 67, 91, 55, 78]
    for (score: int in scores) {
        let grade = classify(score)
        let letter = label(grade)
        println(f"score {score} -> {letter}")
    }
}
```

Output:

```
score 95 -> A
score 82 -> B
score 67 -> C
score 91 -> A
score 55 -> C
score 78 -> B
```

The program uses a sum type with `match` for classification, `for` for iteration, and `if` for the initial range check. Each tool does one thing; the composition is straightforward.

Here is another example that processes a collection of shapes, using `match` both to compute and to label:

```flow
type Shape =
    | Circle(radius: float)
    | Rectangle(width: float, height: float)
    | Triangle(base: float, height: float)

fn area(s: Shape): float {
    return match s {
        Circle(r): 3.14159 * r * r,
        Rectangle(w, h): w * h,
        Triangle(b, h): 0.5 * b * h
    }
}

fn main() {
    let shapes = [
        Circle(5.0),
        Rectangle(3.0, 4.0),
        Triangle(6.0, 8.0)
    ]

    let total: float:mut = 0.0
    for (s: Shape in shapes) {
        let a = area(s)
        let name = match s {
            Circle(_): "circle",
            Rectangle(_, _): "rectangle",
            Triangle(_, _): "triangle"
        }
        println(f"{name}: {a}")
        total = total + a
    } finally {
        println(f"total area: {total}")
    }
}
```

The `finally` block on the `for` loop runs after the loop completes --- whether the array was exhausted or the loop exited early. Here it prints a running total.

The third example uses `if let` to handle optional values in a search:

```flow
type Entry = {
    key: string,
    value: int
}

fn find_entry(entries: array<Entry>, target: string): option<Entry> {
    for (e: Entry in entries) {
        if (e.key == target) {
            return some(e)
        }
    }
    return none
}

fn main() {
    let db = [
        Entry { key: "alpha", value: 1 },
        Entry { key: "beta", value: 2 },
        Entry { key: "gamma", value: 3 }
    ]

    let keys = ["beta", "delta", "alpha"]
    for (k: string in keys) {
        if (let some(entry) = find_entry(db, k)) {
            println(f"{k} -> {entry.value}")
        } else {
            println(f"{k} -> not found")
        }
    }
}
```

Output:

```
beta -> 2
delta -> not found
alpha -> 1
```

---

## 5.6 What Goes Wrong

### Non-exhaustive match on a sum type

```flow
type Light = | Red | Yellow | Green

fn action(l: Light): string {
    return match l {
        Red: "stop",
        Green: "go"
        ; compile error: variant 'Yellow' not handled
    }
}
```

The fix: add the missing variant, or add `_` if you intentionally want a catch-all.

### Missing wildcard on primitive match

```flow
fn to_word(n: int): string {
    return match n {
        1: "one",
        2: "two"
        ; compiler warning: not all int values covered
        ; runtime error if n is anything other than 1 or 2
    }
}
```

The fix: add `_: "unknown"` or whatever default is appropriate.

### Type mismatch in expression `if`

```flow
; compile error: branches produce different types
let x = if (flag) { 42 } else { "hello" }
```

Both branches must produce the same type. If you need different types, you are probably looking for a sum type or `match`.

### Missing `else` in expression `if`

```flow
; compile error: expression if requires else branch
let x: int = if (flag) { 42 }
```

An expression `if` always needs an `else`. The compiler does not invent a default value for you.

### Using `break`/`continue` outside a loop

```flow
fn bad() {
    break  ; compile error: break outside loop
}
```

`break` and `continue` only work inside `while` or `for`. Anywhere else is a compile error.

### Mismatched types across match arms

```flow
fn bad(n: int): string {
    return match n {
        0: "zero",
        1: 1,         ; compile error: arm produces int, expected string
        _: "other"
    }
}
```

When `match` is used as an expression, all arms must produce the same type. The compiler infers the expected type from the first arm and checks the rest against it.

### Unreachable arms after wildcard

```flow
fn redundant(n: int): string {
    return match n {
        _: "default",
        0: "zero"      ; warning: unreachable pattern
    }
}
```

The wildcard matches everything. Any arm after it can never execute. The compiler warns you, but it is not an error. Still, unreachable code is a sign of a mistake. Put `_` last.

### Forgetting `:mut` on a loop counter

```flow
fn main() {
    let i: int = 0
    while (i < 10) {
        println(f"{i}")
        i = i + 1       ; compile error: cannot assign to immutable binding
    }
}
```

This is one of the most common mistakes newcomers hit. In Flow, `let` bindings are immutable unless you write `:mut`. The fix: `let i: int:mut = 0`.

---

## 5.7 Summary

Flow's decision-making tools are small in number and predictable in behavior.

`if`/`else` handles conditional execution. Used as an expression, both branches must produce the same type and the `else` is mandatory. The ternary operator `? :` provides shorthand for the simple case.

`match` dispatches on values. Arms use `:` as the separator, are tested in order, and the first match wins. For sum types, the compiler enforces exhaustiveness: cover every variant or provide `_`. For primitives and strings, `_` is how you handle the unbounded cases.

`if let` is sugar for a one-armed `match`. Use it when you care about a single variant of an option or result.

`while` loops on a condition. `for` iterates over collections. Both support `break`, `continue`, and `finally`. Loop `finally` blocks run exactly once when the loop exits, no matter how.

Chapter 6 introduces the data structures --- structs, sum types, arrays, and maps --- that give `match` its full power.

---

## Exercises

**1. FizzBuzz with match.**

Write a program that prints numbers 1 through 30. For multiples of 3, print "fizz". For multiples of 5, print "buzz". For multiples of both, print "fizzbuzz". Use `match` on a boolean tuple to dispatch the four cases.

```flow
fn fizzbuzz(n: int): string {
    let by3 = n % 3 == 0
    let by5 = n % 5 == 0
    return match (by3, by5) {
        (true, true): "fizzbuzz",
        (true, false): "fizz",
        (false, true): "buzz",
        (false, false): f"{n}"
    }
}

fn main() {
    let i: int:mut = 1
    while (i <= 30) {
        println(fizzbuzz(i))
        i = i + 1
    }
}
```

**2. Calculator dispatch.**

Write a function that takes an operator string (`"+"`, `"-"`, `"*"`, `"/"`) and two floats, then returns the result. Use `match` on the operator. Handle division by zero. Handle unknown operators.

```flow
type CalcResult =
    | Ok(value: float)
    | Error(msg: string)

fn calculate(op: string, a: float, b: float): CalcResult {
    return match op {
        "+": Ok(a + b),
        "-": Ok(a - b),
        "*": Ok(a * b),
        "/": {
            if (b == 0.0) {
                return Error("division by zero")
            } else {
                return Ok(a / b)
            }
        },
        _: Error(f"unknown operator: {op}")
    }
}

fn main() {
    let ops = ["+", "-", "*", "/", "/", "%"]
    let a_vals = [10.0, 20.0, 3.0, 15.0, 7.0, 5.0]
    let b_vals = [5.0, 8.0, 4.0, 3.0, 0.0, 2.0]

    let i: int:mut = 0
    while (i < 6) {
        let result = calculate(ops[i], a_vals[i], b_vals[i])
        match result {
            Ok(v): { println(f"{a_vals[i]} {ops[i]} {b_vals[i]} = {v}") }
            Error(msg): { println(f"{a_vals[i]} {ops[i]} {b_vals[i]} => error: {msg}") }
        }
        i = i + 1
    }
}
```

**3. Command-line menu.**

Build a menu loop that prints options, reads a choice, dispatches with `match`, and exits on "quit". Use `while`, `match`, and `break`.

```flow
fn show_menu() {
    println("--- Menu ---")
    println("1) greet")
    println("2) count")
    println("3) quit")
    println("choice: ")
}

fn main() {
    while (true) {
        show_menu()
        let choice = io.read_line()
        match choice {
            "1": { println("hello, user!") }
            "2": {
                let i: int:mut = 1
                while (i <= 5) {
                    println(f"  {i}")
                    i = i + 1
                }
            }
            "3": { break }
            _: { println("unknown option, try again") }
        }
        println("")
    } finally {
        println("goodbye")
    }
}
```

**4. Chaining optional operations with `if let`.**

Write a series of functions that return `option` values, then chain them together using `if let`. The program looks up a user, then looks up their department, then looks up the department head.

```flow
type User = { name: string, dept_id: int }
type Department = { id: int, name: string, head: string }

fn find_user(name: string): option<User> {
    if (name == "alice") {
        return some(User { name: "alice", dept_id: 1 })
    } else if (name == "bob") {
        return some(User { name: "bob", dept_id: 2 })
    } else {
        return none
    }
}

fn find_department(id: int): option<Department> {
    if (id == 1) {
        return some(Department { id: 1, name: "engineering", head: "carol" })
    } else {
        return none
    }
}

fn lookup_head(username: string): string {
    if (let some(user) = find_user(username)) {
        if (let some(dept) = find_department(user.dept_id)) {
            return f"{username}'s department head is {dept.head}"
        } else {
            return f"department {user.dept_id} not found"
        }
    } else {
        return f"user {username} not found"
    }
}

fn main() {
    println(lookup_head("alice"))
    println(lookup_head("bob"))
    println(lookup_head("eve"))
}
```

Expected output:

```
alice's department head is carol
department 2 not found
user eve not found
```

**5. FizzBuzz with composition and lambdas.**

Rewrite the FizzBuzz from exercise 1 using a pipeline. Generate the range, transform each number with a lambda, and print the results.

```flow
fn fizzbuzz(n: int): string {
    let by3 = n % 3 == 0
    let by5 = n % 5 == 0
    return match (by3, by5) {
        (true, true): "fizzbuzz",
        (true, false): "fizz",
        (false, true): "buzz",
        (false, false): f"{n}"
    }
}

fn range(start: int, end: int): array<int> {
    let result: array<int>:mut = []
    let i: int:mut = start
    while (i <= end) {
        result = array.push(result, i)
        i = i + 1
    }
    return result
}

fn main() {
    let numbers = range(1, 30)
    for (n: int in numbers) {
        println(fizzbuzz(n))
    }
}
```
