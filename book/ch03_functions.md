# Chapter 3: Functions and Purity

A program is a collection of functions. In Flow, every function takes typed parameters, returns exactly one value, and has a body that is either a block of statements or a single expression. There are no varargs and no overloads. Functions support default parameter values and named arguments for flexibility while keeping signatures explicit. A function's signature tells you everything about how to call it and what you get back.

This chapter covers how to define functions, how purity works, how lambdas and closures work, how generics work, and how to pass functions around as values.

---

## 3.1 Defining Functions

### 3.1.1 Block Bodies and Expression Bodies

A function definition starts with `fn`, followed by the name, a parenthesized parameter list, a colon, the return type, and a body. The body comes in two forms.

A **block body** uses braces and contains one or more statements. It must include an explicit `return` on every code path that produces a value:

```flow
fn factorial(n: int): int {
    if (n <= 1) { return 1 }
    return n * factorial(n - 1)
}
```

An **expression body** uses `=` followed by a single expression. The value of that expression is the return value. No `return` keyword, no braces:

```flow
fn add(x: int, y: int): int = x + y
fn square(n: int): int = n * n
fn negate(b: bool): bool = !b
```

Expression bodies are not limited to arithmetic. Any expression that produces the declared return type is valid:

```flow
fn greeting(name: string): string = f"Hello, {name}!"
fn is_positive(n: int): bool = n > 0
```

Use expression bodies when the function is a single computation. Use block bodies when you need multiple steps, local variables, or control flow. The choice is syntactic; the semantics are identical. A good rule of thumb: if the implementation fits in one line without sacrificing readability, use an expression body. If you find yourself chaining ternary-style expressions to avoid braces, use a block body instead.

### 3.1.2 Parameters and Return Types

Every parameter must have a type annotation. Flow does not infer parameter types:

```flow
fn distance(x1: float, y1: float, x2: float, y2: float): float {
    let dx: float = x2 - x1
    let dy: float = y2 - y1
    return math.sqrt(dx * dx + dy * dy)
}
```

The return type is also required. There is no implicit return type, no `void`. If a function exists only for its side effects --- printing, writing to a file, closing a handle --- its return type is `none`:

```flow
fn greet(name: string): none {
    println(f"Hello, {name}!")
}
```

`none` is a type. It has exactly one value. A function that returns `none` still returns; it just returns nothing useful. You cannot bind the result of a `none`-returning function to a variable of any other type.

The explicit return type is a feature, not a burden. When you read a function signature, the return type tells you immediately what the function produces. When you write a function, the return type acts as a contract --- the compiler will reject the function if any code path returns something different. This catches entire categories of bugs at compile time rather than at 3 AM in production.

Every function returns exactly one value. If you need to return multiple values, return a struct:

```flow
type Point { x: float, y: float }

fn midpoint(a: Point, b: Point): Point {
    return Point {
        x: (a.x + b.x) / 2.0,
        y: (a.y + b.y) / 2.0
    }
}
```

### 3.1.3 The `main` Function

Every Flow program has a `main` function. It takes no parameters and returns `none`:

```flow
fn main(): none {
    let result = factorial(10)
    println(f"10! = {result}")
}
```

This is the entry point. The compiler looks for it by name. If your file does not define `main`, it is not a program --- it is a module (covered in Chapter 12).

### 3.1.4 Recursion

Recursion works as expected. There are no special annotations and no trampoline requirements:

```flow
fn gcd(a: int, b: int): int {
    if (b == 0) { return a }
    return gcd(b, a % b)
}

fn fib(n: int): int {
    if (n <= 1) { return n }
    return fib(n - 1) + fib(n - 2)
}
```

Flow does not currently guarantee tail-call optimization. Deep recursion consumes stack. For algorithms that recurse to arbitrary depth, consider an iterative rewrite with a local mutable accumulator:

```flow
fn factorial_iter(n: int): int {
    let acc: int:mut = 1
    let i: int:mut = 2
    while (i <= n) {
        acc = acc * i
        i = i + 1
    }
    return acc
}
```

Both styles are valid. Use whichever reads more clearly for the problem at hand.

A note on mutual recursion: two functions can call each other. Flow does not require forward declarations. The compiler sees all top-level function definitions before checking any function body, so `fn a()` can call `fn b()` and `fn b()` can call `fn a()` regardless of their order in the source file:

```flow
fn is_even(n: int): bool {
    if (n == 0) { return true }
    return is_odd(n - 1)
}

fn is_odd(n: int): bool {
    if (n == 0) { return false }
    return is_even(n - 1)
}
```

This works for any positive `n`. (For large `n`, prefer the modulo operator. The example is pedagogical.)

---

## 3.2 Pure Functions

### 3.2.1 The `fn:pure` Annotation

A function declared with `fn:pure` makes a contract with the compiler: given the same inputs, it will always produce the same output, and it will not change anything outside itself. The compiler enforces this contract. It is not a hint or a comment.

```flow
fn:pure square(x: int): int = x * x

fn:pure celsius_to_fahrenheit(c: float): float = c * 1.8 + 32.0

fn:pure clamp(value: int, low: int, high: int): int {
    if (value < low) { return low }
    if (value > high) { return high }
    return value
}
```

The `pure` modifier appears after the colon in `fn:pure`, the same position as other function modifiers. It works with both block and expression bodies.

### 3.2.2 What Purity Guarantees

The compiler transitively verifies these constraints on every `fn:pure` function:

- **No I/O.** No `println`, no file operations, no network calls.
- **No mutable statics.** No reading or writing module-level mutable state.
- **No calling impure functions.** Every function called from a pure function must itself be pure.
- **No `:mut` parameters.** A pure function cannot accept mutable parameters, because mutating a caller's data is a side effect.
- **Deterministic.** No `random()`, no `time.now()`, no mutable static access.

One rule surprises newcomers: **local mutation is allowed inside a pure function.** As long as the mutation does not escape, purity is preserved:

```flow
fn:pure sum(items: array<int>): int {
    let total: int:mut = 0
    for (item: int in items) {
        total = total + item
    }
    return total
}
```

The `total` variable is mutable, but it is local. It is created when `sum` is called and destroyed when `sum` returns. No outside observer can detect its existence. The function's behavior depends only on `items`, and the same `items` always produces the same result. That is pure.

The compiler checks these rules at compile time. Violations produce clear errors:

```flow
fn:pure bad_square(x: int): int {
    println(f"squaring {x}")  // compile error: println is not pure
    return x * x
}
```

The error tells you which impure operation was found and where. You either remove the impure call or remove the `fn:pure` annotation. There is no escape hatch.

The transitivity rule is the one that catches people most often in practice. If function `a` is pure and calls function `b`, then `b` must also be pure. If `b` calls `c`, then `c` must be pure too. The compiler follows the entire call chain. You cannot hide an impure operation behind several layers of indirection:

```flow
fn helper(x: int): int {
    println(f"debug: {x}")  // impure
    return x
}

fn:pure transform(x: int): int {
    return helper(x) * 2  // compile error: helper is not pure
}
```

The fix is to either mark `helper` as `fn:pure` (which means removing the `println` inside it) or to remove the `fn:pure` from `transform`.

### 3.2.3 When to Use Pure Functions

Mark a function pure when it genuinely is. Do not add `fn:pure` to every function preemptively --- most functions in a real program perform I/O, mutate state, or call functions that do. Pure functions are the right choice for:

**Data transformations.** Functions that take a value and produce a new value:

```flow
fn:pure normalize(s: string): string {
    return string.trim(string.lower(s))
}

fn:pure area(radius: float): float = 3.14159 * radius * radius
```

**Validators.** Functions that check a condition and return a boolean:

```flow
fn:pure is_valid_port(port: int): bool {
    return port > 0 && port <= 65535
}

fn:pure is_palindrome(s: string): bool {
    return s == string.reverse(s)
}
```

**Calculations.** Anything that is straightforwardly mathematical:

```flow
fn:pure lerp(a: float, b: float, t: float): float = a + (b - a) * t

fn:pure manhattan_distance(x1: int, y1: int, x2: int, y2: int): int {
    return math.abs(x1 - x2) + math.abs(y1 - y2)
}
```

Purity also unlocks two concrete benefits at the language level. First, the runtime may memoize pure function results within a composition chain. If two fan-out branches call the same pure function on the same input, the result is computed once. Second, pure functions are safe for parallel fan-out --- the compiler can verify that parallel execution introduces no data races, because pure functions have no shared mutable state.

These benefits matter in Chapters 4 and 10. For now, the takeaway is simple: pure functions are the ones you can trust completely. They do what they say, nothing more.

In a large codebase, purity annotations serve as documentation that the compiler enforces. When you see `fn:pure` in a function signature, you know immediately that calling it has no side effects. You can call it twice, call it zero times, call it in parallel, call it in a test without mocking anything. That guarantee is worth the discipline of maintaining it.

---

## 3.3 Lambdas

### 3.3.1 Lambda Syntax

A lambda is an anonymous function. In Flow, the syntax uses a backslash, parenthesized parameters with types, a fat arrow, and the body expression:

```flow
let inc = \(x: int => x + 1)
let add = \(a: int, b: int => a + b)
let is_even = \(n: int => n % 2 == 0)
```

The backslash is the lambda introducer. The fat arrow `=>` separates parameters from the body. The entire lambda is wrapped in parentheses.

The type of a lambda is inferred from its definition. In the examples above:

- `inc` has type `fn(int): int`
- `add` has type `fn(int, int): int`
- `is_even` has type `fn(int): bool`

You can also write the type explicitly on the binding:

```flow
let inc: fn(int): int = \(x: int => x + 1)
```

Lambdas are values. You can bind them to variables, pass them to functions, return them from functions, and store them in data structures. They are not second-class conveniences; they are the same kind of thing as a named function, without a name.

Why the backslash? It is a nod to the lambda calculus, where the Greek letter lambda introduces an anonymous function. The backslash is a reasonable ASCII approximation that does not collide with any other operator in the language. You get used to it quickly.

A zero-parameter lambda omits the parameter list but keeps the arrow:

```flow
let say_hello = \( => println("hello"))
```

### 3.3.2 Capture Semantics

Lambdas can reference variables from the scope where they are defined. This is what makes them closures --- they "close over" their environment.

```flow
fn make_greeting(salutation: string): fn(string): string {
    return \(name: string => f"{salutation}, {name}!")
}

fn main(): none {
    let greet = make_greeting("Hello")
    println(greet("Alice"))  // Hello, Alice!
    println(greet("Bob"))  // Hello, Bob!
}
```

The lambda inside `make_greeting` captures `salutation`. When `make_greeting` returns, the lambda carries `salutation` with it. Later, when `greet` is called, it still has access to the value.

The capture rules depend on mutability:

**Immutable captures are by reference.** When a lambda captures an immutable variable, it shares a reference to the same value. This is cheap --- no copying --- and safe, because neither the lambda nor the outer scope can mutate it:

```flow
fn make_adder(n: int): fn(int): int {
    return \(x: int => x + n)  // n is immutable, captured by reference
}
```

**Mutable captures are by copy.** When a lambda captures a `:mut` variable, it gets a snapshot of the value at the moment the lambda is created. Changes to the original do not affect the lambda's copy, and the lambda cannot change the original:

```flow
fn example(): none {
    let counter: int:mut = 10
    let snapshot = \( => counter)  // captures counter's value: 10
    counter = 20
    println(f"{snapshot()}")  // prints 10, not 20
}
```

This rule exists because mutable data and sharing do not mix safely. If the lambda could see changes to `counter`, and if the lambda were passed to a concurrent coroutine, you would have a data race. By copying, Flow eliminates that possibility at the language level.

The distinction matters in practice. If you want a lambda to see the "latest" value, keep the value immutable and restructure your code so the lambda is created after the value is finalized. If you want a lambda to carry a frozen snapshot, make the value mutable and let the capture rule do the work.

One consequence of these capture rules: a lambda that captures only immutable values is safe to use in parallel fan-out. The compiler knows this statically. A lambda that captures mutable values by copy is also safe, because it has its own independent copy. There is no configuration, no annotation, no `Sync` or `Send` trait. The rules are baked into the capture mechanism itself.

---

## 3.4 Generic Functions

### 3.4.1 Type Parameters

Sometimes you write a function that does not care about the specific type of its arguments --- it works the same way for `int`, `string`, `Point`, or anything else. Generic functions express this:

```flow
fn identity<T>(x: T): T = x
```

The `<T>` after the function name declares a type parameter. Inside the function, `T` stands for whatever type the caller provides. When called, the compiler infers the concrete type:

```flow
let a: int = identity(42)  // T is int
let b: string = identity("hello")  // T is string
```

You can have multiple type parameters:

```flow
fn pair<A, B>(first: A, second: B): Pair<A, B> {
    return Pair { first: first, second: second }
}
```

Type parameters are placeholders, not types themselves. You cannot call methods on a `T` unless you tell the compiler what methods `T` has. That is what bounded generics are for.

### 3.4.2 Bounded Generics

An unconstrained `T` is opaque. You can pass it around and return it, but you cannot do anything with it --- no comparison, no printing, no arithmetic. To use operations on a generic type, you constrain it with `fulfills`:

```flow
fn max<T fulfills Comparable>(a: T, b: T): T {
    if (a > b) { return a }
    return b
}
```

The `fulfills Comparable` bound tells the compiler: "T must be a type that implements the `Comparable` interface." Because `Comparable` guarantees comparison operators, the `a > b` expression is valid. The compiler checks the bound at each call site:

```flow
let m = max(3, 7)  // int fulfills Comparable: ok
let s = max("abc", "xyz")  // string fulfills Comparable: ok
```

If you call `max` with a type that does not fulfill `Comparable`, you get a compile error naming the type and the missing interface.

A type parameter can have multiple bounds. Parenthesize them:

```flow
fn format_and_hash<T fulfills (Stringable, Hashable)>(val: T): int {
    println(val.to_string())
    return val.hash()
}
```

Without parentheses, a comma after a bound starts a new type parameter. This is the disambiguation rule:

```flow
// Two parameters: T bounded by Comparable, U unbounded
fn wrap<T fulfills Comparable, U>(a: T, b: U): T = a

// One parameter with two bounds
fn process<T fulfills (Comparable, Hashable)>(a: T): int {
    return a.hash()
}
```

The distinction is purely syntactic: parentheses group bounds on one parameter; no parentheses means the comma separates parameters. Read the angle brackets carefully.

### 3.4.3 Generics in Practice

Generic functions appear most often in utility code and collection operations. A few examples to build intuition:

```flow
fn:pure first_or_default<T>(items: array<T>, default: T): T {
    if (array.length(items) == 0) { return default }
    return array.get(items, 0)
}
```

```flow
fn:pure repeat<T>(value: T, n: int): array<T> {
    let result: array<T>:mut = []
    let i: int:mut = 0
    while (i < n) {
        array.push(result, value)
        i = i + 1
    }
    return result
}
```

The power of generics is that you write the logic once and it works for every type that satisfies the constraints. No code duplication, no casting, no runtime type checks.

A word on when to use generics: reach for them when you find yourself writing the same function body for different types. If you have `max_int` and `max_float` and `max_string` that all have the same structure --- compare two values, return the larger --- that is a generic function waiting to happen. If the function bodies actually differ (different comparison logic, different edge cases), keep them separate. Generics are for abstracting over types, not for forcing unrelated code into a shared template.

---

## 3.5 Higher-Order Functions

Functions in Flow are values. A function's type is written with the `fn` keyword, the parameter types in parentheses, a colon, and the return type:

```flow
fn(int): int  // takes an int, returns an int
fn(int, int): int  // takes two ints, returns an int
fn(string): bool  // takes a string, returns a bool
fn(int): fn(int): int  // takes an int, returns a function
```

These types appear in parameter lists, return types, and variable declarations. A function that takes or returns another function is called a **higher-order function**.

### 3.5.1 Functions as Parameters

Passing a function as an argument lets you parameterize behavior:

```flow
fn apply(f: fn(int): int, x: int): int = f(x)

fn:pure double(n: int): int = n * 2
fn:pure negate_int(n: int): int = 0 - n

fn main(): none {
    println(f"{apply(double, 5)}")  // 10
    println(f"{apply(negate_int, 5)}")  // -5
}
```

The `apply` function does not know or care what `f` does. It calls `f` with `x` and returns the result. The caller decides the behavior by choosing which function to pass.

You can pass lambdas directly, without naming them first:

```flow
fn main(): none {
    let result = apply(\(x: int => x * x), 6)
    println(f"{result}")  // 36
}
```

This pattern --- a higher-order function that takes a function argument and applies it --- is the foundation of composition in Flow. Chapter 4 builds extensively on it.

A more realistic example: suppose you have a list of values and you want to transform each one. You could write a transformation function for each specific operation, or you could write one function that accepts the operation as a parameter:

```flow
fn transform_all(items: array<int>, f: fn(int): int): array<int> {
    let result: array<int>:mut = []
    let i: int:mut = 0
    while (i < array.length(items)) {
        array.push(result, f(array.get(items, i)))
        i = i + 1
    }
    return result
}

fn main(): none {
    let numbers = [1, 2, 3, 4, 5]
    let doubled = transform_all(numbers, \(x: int => x * 2))
    let squared = transform_all(numbers, \(x: int => x * x))
    // doubled is [2, 4, 6, 8, 10]
    // squared is [1, 4, 9, 16, 25]
}
```

The `transform_all` function does not know what transformation to apply. The caller provides it. This separation --- the iteration logic in one place, the transformation logic in another --- is what higher-order functions buy you. One function, many behaviors.

### 3.5.2 Functions as Return Values

A function can return a function. This is how you build specialized behavior at runtime:

```flow
fn make_adder(n: int): fn(int): int {
    return \(x: int => x + n)
}

fn main(): none {
    let add5 = make_adder(5)
    let add10 = make_adder(10)
    println(f"{add5(3)}")  // 8
    println(f"{add10(3)}")  // 13
}
```

`make_adder` returns a lambda that closes over `n`. Each call to `make_adder` produces a different function with a different captured value. The returned function is a first-class value: you can store it, pass it, call it later.

### 3.5.3 Combining Higher-Order Functions

Once you can pass and return functions, you can compose them:

```flow
fn apply_twice(f: fn(int): int, x: int): int = f(f(x))

fn:pure increment(n: int): int = n + 1

fn main(): none {
    println(f"{apply_twice(increment, 5)}")  // 7
    println(f"{apply_twice(double, 3)}")  // 12
}
```

Or build more powerful combinators:

```flow
fn compose(f: fn(int): int, g: fn(int): int): fn(int): int {
    return \(x: int => f(g(x)))
}

fn main(): none {
    let double_then_inc = compose(increment, double)
    println(f"{double_then_inc(5)}")  // 11 (double 5 = 10, increment 10 = 11)

    let inc_then_double = compose(double, increment)
    println(f"{inc_then_double(5)}")  // 12 (increment 5 = 6, double 6 = 12)
}
```

The `compose` function takes two functions and returns a new function that applies `g` first, then `f`. The argument order follows mathematical convention: `compose(f, g)` means "f after g."

Notice what is happening here. `compose` does not know what `f` and `g` do. It does not call them. It returns a new function that, when eventually called, will call both in sequence. The returned function is as real as any named function --- it has a type (`fn(int): int`), it can be stored, passed to other functions, or composed again.

This is manual composition. In Chapter 4 you will see Flow's `->` operator, which does this automatically with cleaner syntax. But the principle is the same: small functions combined into larger ones.

---

## 3.6 Function-Level Finally

Some functions acquire resources that must be released regardless of how the function exits --- normally, via early return, or via an exception. Flow provides a `finally` block for this:

```flow
fn process_file(path: string): string {
    let handle = file.open(path)
    let content = file.read(handle)
    return content
} finally {
    file.close(handle)
}
```

The `finally` block appears after the closing brace of the function body. It runs exactly once when the function terminates, no matter how:

- Normal return: `finally` runs after the return value is computed but before it is delivered to the caller.
- Early return: same behavior.
- Exception thrown inside the function: `finally` runs before the exception propagates.
- Consumer abandonment (for stream-producing functions): `finally` runs when the consumer stops pulling.

The `finally` block can reference any variable that is in scope in the function body. In the example above, `handle` is declared in the function body and used in the `finally` block.

This is Flow's mechanism for deterministic cleanup. It replaces the try-finally patterns you may know from other languages, but it is scoped to the function rather than to an arbitrary block. One function, one cleanup block. If you need multiple cleanup actions, put them all in the same `finally`:

```flow
fn transfer(src_path: string, dst_path: string): none {
    let src = file.open(src_path)
    let dst = file.open(dst_path)
    let data = file.read(src)
    file.write(dst, data)
} finally {
    file.close(src)
    file.close(dst)
}
```

Functions that do not acquire resources do not need `finally`. Most functions in a typical program will not have one. Use it when you have a resource with a definite lifetime that must not outlive the function call.

A `finally` block cannot contain a `return` statement. It runs for cleanup, not for producing a result. The function's return value is determined by the main body. The `finally` block fires after that value is computed, does its work, and then the value is delivered to the caller.

This design --- one `finally` per function, always at the top level --- keeps cleanup visible and predictable. You never have to trace through nested try-finally blocks to figure out which cleanup runs in which order. Each function manages its own resources, and the `finally` block is the place where that management lives.

---

## 3.7 Scoping Rules

Functions in Flow have strict scoping. A function can access:

- Its own parameters.
- Local variables declared within its body.
- Imported functions from the module level.
- Static type members via the type name (e.g., `Config.max_retries`).

A function **cannot** access variables from an enclosing function or module-level `let` bindings. This is a deliberate restriction. It means that a function's behavior is determined entirely by its parameters and the functions it calls --- never by ambient state lurking in an outer scope.

Lambdas are the exception. A lambda can access anything in the scope where it is defined, including the enclosing function's parameters and locals. This is what makes lambdas closures, as described in section 3.3.2.

### 3.7.1 Shadowing

Inner scopes silently shadow outer names. No warning is emitted:

```flow
fn example(): none {
    let x: int = 1
    if (true) {
        let x: int = 2  // shadows outer x
        println(f"{x}")  // prints 2
    }
    println(f"{x}")  // prints 1, outer x is unchanged
}
```

Shadowing applies everywhere: blocks, functions, lambdas, match arms. The outer name becomes inaccessible within the inner scope. There is no syntax to reach through a shadow to the original binding.

Shadowing is sometimes useful for narrowing a type or providing a more specific version of a value within a block. But overuse makes code harder to follow. If you find yourself shadowing the same name three levels deep, consider using distinct names instead.

```flow
fn parse_and_validate(raw: string): int {
    let value: int = string.to_int(raw)  // parse the string
    let value: int = clamp(value, 0, 100)  // shadow with clamped version
    return value
}
```

Here the shadowing makes the intent clear: `value` is progressively refined. The raw parsed integer is not accessible after the clamp, which prevents accidentally using the unclamped version.

---

## 3.8 What Goes Wrong

### Purity violations

The most common error when starting with `fn:pure` is calling an impure function:

```flow
fn:pure compute(x: int): int {
    println(f"computing {x}")  // ERROR: println is not pure
    return x * x
}
```

The fix is either to remove the `println` or to remove the `fn:pure` annotation. If you need logging during development, remove `fn:pure`, add the logging, and put `fn:pure` back when you are done. The compiler will remind you if you forget.

### Missing return

Every code path in a block-bodied function must return a value (unless the return type is `none`). The compiler catches unreachable code and missing returns:

```flow
fn classify(n: int): string {
    if (n > 0) { return "positive" }
    if (n < 0) { return "negative" }
    // ERROR: not all code paths return a value
    // (what if n == 0?)
}
```

The fix:

```flow
fn classify(n: int): string {
    if (n > 0) { return "positive" }
    if (n < 0) { return "negative" }
    return "zero"
}
```

### Type mismatches in function calls

Flow checks argument types at every call site. Passing the wrong type is a compile error:

```flow
fn:pure double(n: int): int = n * 2

fn main(): none {
    let x: float = 3.14
    let result = double(x)  // ERROR: expected int, got float
}
```

There is no implicit conversion between `int` and `float`. Use an explicit conversion:

```flow
let result = double(int(x))  // explicit conversion, compiles
```

### Wrong number of arguments

```flow
fn:pure add(x: int, y: int): int = x + y

fn main(): none {
    let r = add(1)  // ERROR: expected 2 arguments, got 1
    let s = add(1, 2, 3)  // ERROR: expected 2 arguments, got 3
}
```

### Returning the wrong type

```flow
fn greet(name: string): int {
    return f"Hello, {name}!"  // ERROR: expected int, got string
}
```

### Lambda capture of mutable variables

This is not an error, but it surprises people:

```flow
fn main(): none {
    let x: int:mut = 1
    let f = \( => x)  // captures x by copy, snapshot is 1
    x = 2
    println(f"{f()}")  // prints 1, not 2
}
```

The lambda captured a copy of `x` at creation time. Subsequent changes to `x` are invisible to `f`. If you want `f` to see the value `2`, create the lambda after the assignment.

### Function type mismatches

When passing functions as arguments, the types must match exactly. A function that takes `fn(int): int` will not accept a function with signature `fn(float): float`, even if the body looks similar:

```flow
fn apply(f: fn(int): int, x: int): int = f(x)
fn:pure half(x: float): float = x / 2.0

fn main(): none {
    let r = apply(half, 5)  // ERROR: expected fn(int): int, got fn(float): float
}
```

The parameter types and return type must all match. This is not subtyping; it is exact structural matching.

### Accessing outer function variables

Named functions cannot access variables from enclosing functions. Only lambdas can:

```flow
fn outer(): none {
    let secret: int = 42

    fn inner(): int {
        return secret  // ERROR: cannot access outer function variable
    }
}
```

If you need `inner` to use `secret`, either pass it as a parameter or use a lambda instead of a named function:

```flow
fn outer(): none {
    let secret: int = 42
    let inner = \( => secret)  // OK: lambda captures from enclosing scope
    println(f"{inner()}")
}
```

### Pure function with `:mut` parameter

A pure function cannot accept mutable parameters:

```flow
fn:pure sort_in_place(items: array<int>:mut): none {
    // ERROR: pure function cannot accept :mut parameter
}
```

The reason is straightforward: mutating a caller's data is a side effect. If `sort_in_place` modifies `items` and the caller can see the change, the function has changed something outside itself. That violates purity. Return a new sorted array instead:

```flow
fn:pure sorted(items: array<int>): array<int> {
    // ... create and return a new sorted array ...
}
```

---

## 3.9 Summary

Functions are the primary unit of organization in Flow. Every function has a name (or is a lambda), takes typed parameters, and returns exactly one typed value. Block bodies use braces and explicit `return`; expression bodies use `=` and implicit return.

Pure functions, annotated with `fn:pure`, are compiler-verified to be deterministic and side-effect-free. They can use local mutation internally but cannot perform I/O, read mutable statics, accept mutable parameters, or call impure functions. Purity enables safe memoization and parallel execution.

Lambdas are anonymous functions written with backslash syntax. They capture immutable variables by reference and mutable variables by copy. This capture rule eliminates data races by construction.

Generic functions use type parameters in angle brackets. Unbounded type parameters are opaque; bounded parameters (with `fulfills`) expose the operations guaranteed by an interface.

Higher-order functions take or return other functions. Function types are written as `fn(ParamTypes): ReturnType`. Combining higher-order functions with lambdas and closures is how Flow builds flexible, reusable abstractions.

Function-level `finally` provides deterministic cleanup. It runs once when the function exits, regardless of how.

Chapter 4 introduces Flow's composition operator, `->`, which chains functions together without the nesting and temporary variables you have seen in this chapter. The patterns here --- small pure functions, higher-order functions, closures --- are exactly the building blocks that composition assembles.

---

## Exercises

**1.** Write a pure function `gcd` that computes the greatest common divisor of two integers using Euclid's algorithm. Test it with several pairs including cases where one argument is zero.

```flow
fn:pure gcd(a: int, b: int): int {
    if (b == 0) { return a }
    return gcd(b, a % b)
}

fn main(): none {
    println(f"gcd(48, 18) = {gcd(48, 18)}")  // 6
    println(f"gcd(100, 75) = {gcd(100, 75)}")  // 25
    println(f"gcd(17, 0) = {gcd(17, 0)}")  // 17
    println(f"gcd(0, 5) = {gcd(0, 5)}")  // 5
}
```

**2.** Write a function `make_multiplier` that takes an integer `factor` and returns a function that multiplies its argument by that factor.

```flow
fn make_multiplier(factor: int): fn(int): int {
    return \(x: int => x * factor)
}

fn main(): none {
    let triple = make_multiplier(3)
    let times10 = make_multiplier(10)
    println(f"triple(7) = {triple(7)}")  // 21
    println(f"times10(7) = {times10(7)}")  // 70
}
```

**3.** Write a generic function `min` that returns the smaller of two values. Use the `Comparable` bound.

```flow
fn min<T fulfills Comparable>(a: T, b: T): T {
    if (a < b) { return a }
    return b
}

fn main(): none {
    println(f"min(3, 7) = {min(3, 7)}")  // 3
    println(f"min(9, 2) = {min(9, 2)}")  // 2
    println(f'min("apple", "banana") = {min("apple", "banana")}')  // apple
}
```

**4.** Write a function `compose` that takes two functions `f: fn(int): int` and `g: fn(int): int` and returns a new function that applies `g` first, then `f`. Verify that `compose(double, increment)(5)` returns `12` and `compose(increment, double)(5)` returns `11`.

```flow
fn:pure double(n: int): int = n * 2
fn:pure increment(n: int): int = n + 1

fn compose(f: fn(int): int, g: fn(int): int): fn(int): int {
    return \(x: int => f(g(x)))
}

fn main(): none {
    let double_after_inc = compose(double, increment)
    let inc_after_double = compose(increment, double)
    println(f"compose(double, increment)(5) = {double_after_inc(5)}")  // 12
    println(f"compose(increment, double)(5) = {inc_after_double(5)}")  // 11
}
```

**5.** Build a small library of pure math functions --- `square`, `cube`, `abs`, `clamp`, `is_even`, `is_odd` --- and write a `main` that demonstrates each one. Then write `apply_if` that takes a predicate `fn(int): bool`, a transform `fn(int): int`, and a value, and applies the transform only if the predicate is true (returning the value unchanged otherwise). Use it to square only even numbers.

```flow
fn:pure square(n: int): int = n * n
fn:pure cube(n: int): int = n * n * n
fn:pure abs(n: int): int {
    if (n < 0) { return 0 - n }
    return n
}
fn:pure clamp(value: int, low: int, high: int): int {
    if (value < low) { return low }
    if (value > high) { return high }
    return value
}
fn:pure is_even(n: int): bool = n % 2 == 0
fn:pure is_odd(n: int): bool = n % 2 != 0

fn apply_if(pred: fn(int): bool, transform: fn(int): int, value: int): int {
    if (pred(value)) { return transform(value) }
    return value
}

fn main(): none {
    // Demonstrate each function
    println(f"square(5) = {square(5)}")  // 25
    println(f"cube(3) = {cube(3)}")  // 27
    println(f"abs(-7) = {abs(-7)}")  // 7
    println(f"clamp(15, 0, 10) = {clamp(15, 0, 10)}")  // 10
    println(f"is_even(4) = {is_even(4)}")  // true
    println(f"is_odd(4) = {is_odd(4)}")  // false

    // apply_if: square only even numbers
    println(f"apply_if(is_even, square, 4) = {apply_if(is_even, square, 4)}")  // 16
    println(f"apply_if(is_even, square, 5) = {apply_if(is_even, square, 5)}")  // 5
}
```
