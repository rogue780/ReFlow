# Chapter 7: Absence, Failure, and Recovery

Every program must deal with things going wrong. A lookup returns no result.
A string is not a valid number. A network connection drops. These are
different problems and they deserve different tools. Flow provides three:
**option types** for absence, **result types** for expected failures, and
**exceptions** for exceptional conditions. This chapter covers all three,
shows how they compose, and explains when to reach for each.

---

## 7.1 Option Types

An `option<T>` is a value that is either present or absent. It has two
variants: `some(value)` when the value exists, and `none` when it does not.

### 7.1.1 `some` and `none`

Here is a function that searches an array for a target value and returns
its index, or nothing:

```flow
module option_demo

import io (println)

fn find_index(arr: array<int>, target: int): int? {
    let i: int:mut = 0
    for (x: int in arr) {
        if (x == target) {
            return some(i)
        }
        i++
    }
    return none
}

fn main() {
    let nums = [10, 20, 30, 40, 50]
    let idx = find_index(nums, 30)
    match idx {
        some(i) : println(f"found at index {i}"),
        none    : println("not found")
    }
}
```

```
$ flow run option_demo.flow
found at index 2
```

The return type `int?` is syntactic sugar for `option<int>`. The function
returns `some(i)` when it finds the target and `none` when it does not.
At the call site, `match` forces the caller to handle both cases. The
compiler rejects a match on an option that does not cover both `some` and
`none` (or use a wildcard `_`).

Note what this function does *not* do. It does not return `-1` to mean
"not found." It does not return `null`. It does not throw an exception.
The return type itself tells you that the result might be absent, and the
type system ensures you handle that possibility.

### 7.1.2 The `?` Suffix (Type Sugar)

`T?` is syntactic sugar for `option<T>`. The two forms are interchangeable:

```flow
let a: option<int> = some(42)
let b: int? = some(42)  // same type
let c: option<string> = none
let d: string? = none  // same type
```

Use whichever is clearer in context. `int?` is shorter and reads naturally
in parameter lists and return types. `option<int>` is more explicit and
sometimes clearer in complex generic signatures. In function signatures,
the short form is conventional:

```flow
fn find_user(id: string): User?
fn get_port(config: Config): int?
```

The long form reads better when nesting or when the option itself is the
subject of discussion:

```flow
// option<option<int>> is rare, but possible
let nested: option<option<int>> = some(some(42))
```

Both forms generate the same compiled code. The choice is purely
stylistic.

### 7.1.3 Auto-Lifting

When the compiler knows that the target type is `option<T>` and the source
value is a plain `T`, it automatically wraps the value in `some`. This is
called **auto-lifting**:

```flow
let x: int? = 42  // auto-lifted to some(42)
let y: int? = some(42)  // explicit, same result
```

Auto-lifting also works in return statements and function arguments:

```flow
fn maybe_score(): int? {
    return 95  // lifted to some(95)
}

fn process(x: int?) {
    // ...
}

process(42)  // lifted to some(42)
process(none)  // no lifting needed
```

Auto-lifting does *not* fire in three situations:

1. **The source is already an option.** Assigning an `int?` to an `int?`
   does not produce `option<option<int>>`. No double-wrapping.

2. **The target is a generic type variable.** In `fn wrap<T>(val: T):
   option<T>`, passing an `int` to `val` does not auto-lift because `T`
   could be any type. Use explicit `some(val)`.

3. **Inside a match arm that binds via `some(v)`.** The bound `v` is
   already the inner value. No lifting occurs.

### 7.1.4 Unwrapping Options

There are four ways to extract a value from an option, each suited to
different situations.

**Pattern matching** is the most explicit. It forces you to handle both
cases:

```flow
fn describe(x: int?): string {
    return match x {
        some(v) : f"the value is {v}",
        none    : "no value"
    }
}
```

**The `??` operator** provides a default when the option is `none`:

```flow
let port: int = config_port() ?? 8080
let name: string = user.middle_name ?? "N/A"
```

The right side of `??` is only evaluated when the left side is `none`
(short-circuit semantics). If computing the default is expensive, it does
not pay the cost when the value is present.

**The `?` propagation operator** passes absence upward. When a function
returns an option and calls another function that also returns an option,
`?` unwraps the inner value or immediately returns `none` from the
enclosing function:

```flow
fn double_positive(x: int): int? {
    let v = find_positive(x)?  // if none, return none immediately
    return some(v * 2)
}
```

This is equivalent to:

```flow
fn double_positive(x: int): int? {
    match find_positive(x) {
        some(v) : return some(v * 2),
        none    : return none
    }
}
```

The `?` form is shorter and, once you are used to it, clearer. It works
only inside functions whose return type is `option<T>` (or `T?`). Using
`?` on an option inside a function that returns `int` is a compile error.

**`if let`** is conditional pattern matching. It lets you handle the
`some` case without writing a full `match`:

```flow
if (let some(v) = find_user(id)) {
    println(f"found: {v}")
}
```

With an `else` branch:

```flow
if (let some(v) = find_user(id)) {
    greet(v)
} else {
    println("user not found")
}
```

`if let` is syntactic sugar for a match. The compiler desugars
`if (let some(x) = expr) { body }` into
`match expr { some(x): { body }, none: {} }`. No special machinery is
needed downstream.

### 7.1.5 Chaining Options

The four unwrapping mechanisms combine naturally. Here is a function that
chains multiple option-returning calls:

```flow
module option_chain

import io (println)

type User {
    name: string,
    email: string?
}

fn find_user(id: string): User? {
    if (id == "u1") {
        return some(User { name: "Alice", email: some("alice@example.com") })
    }
    if (id == "u2") {
        return some(User { name: "Bob", email: none })
    }
    return none
}

fn extract_domain(email: string): string? {
    let parts = split(email, "@")
    if (len(parts) == 2) {
        return some(parts[1])
    }
    return none
}

fn get_user_domain(id: string): string? {
    let user = find_user(id)?  // none if user not found
    let email = user.email?  // none if email not set
    let domain = extract_domain(email)? ; none if email malformed
    return some(domain)
}

fn main() {
    println(f"u1: {get_user_domain("u1") ?? "unknown"}")
    println(f"u2: {get_user_domain("u2") ?? "unknown"}")
    println(f"u3: {get_user_domain("u3") ?? "unknown"}")
}
```

```
$ flow run option_chain.flow
u1: example.com
u2: unknown
u3: unknown
```

Three different reasons produce the same result --- `none` --- and the
caller handles all three identically with a single `??`. User `u1` has
an email with a valid domain. User `u2` exists but has no email. User
`u3` does not exist at all. The `?` operator at each step short-circuits
to `none` without the function needing nested `match` expressions.

This is the power of option chaining. Each `?` is a gate: if the value
is absent, the function returns immediately. If present, execution
continues to the next step. The calling code remains flat and linear
regardless of how many optional steps there are.

### 7.1.6 Nullable Mutability

Options and mutability combine as you would expect:

```flow
let x: int?:mut = some(5)  // nullable, mutable
x = none  // now absent
x = 42  // auto-lifted to some(42)

let y: int? = some(5)  // nullable, immutable
// y = none  // compile error: immutable binding
```

The `:mut` qualifier goes after the `?`. The type `int?:mut` is a mutable
binding that holds an `option<int>`.

---

## 7.2 Result Types

An `option<T>` says "there might be no value." It does not say *why*.
When the caller needs to know what went wrong, use `result<T, E>`.

### 7.2.1 `ok` and `err`

`result<T, E>` is a sum type with two variants: `ok(T)` for success and
`err(E)` for failure. The error type `E` is whatever you choose ---
typically `string` for simple cases, or a custom error type for richer
information.

```flow
module result_demo

import io (println)

fn safe_divide(a: int, b: int): result<int, string> {
    if (b == 0) {
        return err("division by zero")
    }
    return ok(a / b)
}

fn main() {
    match safe_divide(10, 3) {
        ok(v)    : println(f"result: {v}"),
        err(msg) : println(f"error: {msg}")
    }

    match safe_divide(10, 0) {
        ok(v)    : println(f"result: {v}"),
        err(msg) : println(f"error: {msg}")
    }
}
```

```
$ flow run result_demo.flow
result: 3
error: division by zero
```

The function's return type tells the caller two things: what the success
value looks like and what the error value looks like. Pattern matching
forces the caller to handle both. The compiler rejects a match on a result
that does not cover both `ok` and `err`.

### 7.2.2 Propagation with `?`

When multiple operations can fail, chaining results with `match` becomes
verbose quickly:

```flow
// Without propagation --- verbose
fn compute(x: int, y: int): result<int, string> {
    match safe_divide(x, y) {
        ok(q)    : return ok(q + 1),
        err(msg) : return err(msg)
    }
}
```

The `?` operator does this automatically:

```flow
fn compute(x: int, y: int): result<int, string> {
    let q = safe_divide(x, y)?  // returns err early if division fails
    return ok(q + 1)
}
```

If `safe_divide` returns `ok(v)`, `?` unwraps it and binds `v` to `q`.
If it returns `err(e)`, `?` immediately returns `err(e)` from the
enclosing function. The error type `E` of the inner call must be
compatible with the error type of the enclosing function.

Propagation chains naturally:

```flow
fn load_and_process(path: string): result<record, string> {
    let raw = read_file(path)?  // propagate if read fails
    let parsed = parse(raw)?  // propagate if parse fails
    let validated = validate(parsed)?  // propagate if validation fails
    return ok(validated)
}
```

Each `?` is an early-exit point. If any step fails, the error propagates
immediately without executing subsequent steps. If all steps succeed, the
function returns the final value wrapped in `ok`.

Compare the two forms side by side. Without `?`, a three-step pipeline
requires three levels of match nesting:

```flow
fn process(path: string): result<Output, string> {
    match read_file(path) {
        err(e) : return err(e),
        ok(raw) : match parse(raw) {
            err(e) : return err(e),
            ok(parsed) : match validate(parsed) {
                err(e) : return err(e),
                ok(valid) : return ok(transform(valid))
            }
        }
    }
}
```

With `?`, the same logic is four lines:

```flow
fn process(path: string): result<Output, string> {
    let raw = read_file(path)?
    let parsed = parse(raw)?
    let valid = validate(parsed)?
    return ok(transform(valid))
}
```

The behavior is identical. The `?` form is not hiding complexity --- it is
the same early-return logic, expressed more directly.

### 7.2.3 Choosing an Error Type

The error type `E` in `result<T, E>` can be anything. The simplest choice
is `string`:

```flow
fn parse_port(s: string): result<int, string> {
    // ...
    return err("port out of range")
}
```

Strings are adequate for small programs and scripts. For larger programs,
consider a custom error type that carries structured information:

```flow
type ConfigError {
    field: string,
    reason: string,
    line_number: int
}

fn parse_config(text: string): result<Config, ConfigError> {
    // ...
    return err(ConfigError {
        field: "port",
        reason: "not a number",
        line_number: 3
    })
}
```

With a structured error, the caller can make programmatic decisions ---
retry only certain fields, format different error messages for users
versus log files, or aggregate errors from multiple sources.

The choice depends on who consumes the error. If the error is logged and
discarded, `string` is fine. If the error influences control flow, a
structured type prevents the caller from parsing error messages.

### 7.2.4 The Null Coalescing Operator `??`

`??` works on results the same way it works on options. If the left side
is `ok(v)`, it unwraps to `v`. If the left side is `err(e)`, it evaluates
and returns the right side:

```flow
let result = safe_divide(10, 0) ?? -1  // -1 because division failed
let value = find_user(id) ?? default_user ; default_user if lookup failed
```

This is useful when you want to absorb the error and continue with a
default value. The error information is discarded. If you need the error,
use `match` or `?` instead.

### 7.2.5 `if let` with Results

The same `if let` syntax that works with options works with results:

```flow
if (let ok(data) = read_file(path)) {
    process(data)
} else {
    println("read failed")
}

if (let err(e) = validate(input)) {
    log_error(e)
}
```

`if (let ok(x) = expr) { body } else { alt }` desugars to
`match expr { ok(x): { body }, err(_): { alt } }`. The `else` branch
handles the `err` case without binding the error value. If you need the
error value, use a full `match`.

`if let` is most useful when you care about only one variant and the other
case is trivial. If both the success and error paths have substantive
logic, a full `match` is clearer:

```flow
match validate(input) {
    ok(clean)  : save(clean),
    err(report) : {
        log(report)
        notify_admin(report)
        quarantine(input)
    }
}
```

### 7.2.6 Result and Option

Options and results are related but distinct. An option says "maybe a
value"; a result says "maybe a value, and if not, here is why." You can
convert between them:

```flow
// Option to result: provide an error message for the none case
fn require_user(id: string): result<User, string> {
    match find_user(id) {
        some(u) : return ok(u),
        none    : return err(f"user {id} not found")
    }
}

// Result to option: discard the error information
fn try_parse(s: string): int? {
    match parse_int(s) {
        ok(n)  : return some(n),
        err(_) : return none
    }
}
```

The `??` operator on a result already performs the second conversion
implicitly --- it discards the error and produces a plain value. But when
you need to stay in the option type (because your function returns
`T?`), the explicit conversion is necessary.

---

## 7.3 Exceptions

Options handle absence. Results handle expected failures. **Exceptions**
handle the rest: infrastructure failures, corrupted data, bugs, and
conditions that might be correctable with retry logic.

The critical distinction is intent. A function returning `result<T, E>`
tells the caller "this might fail, and here is the error type you will
deal with." An exception says "something went wrong that the function
itself cannot handle --- it needs to unwind until someone can."

Use results for failures the caller expects to handle. Use exceptions for
failures that require corrective action, structural recovery, or
escalation.

### 7.3.1 The `Exception<T>` Interface

Exception types in Flow are not special. They are ordinary types that
fulfill the built-in `Exception<T>` interface:

```flow
interface Exception<T> {
    fn message(self): string  // human-readable description
    fn data(self): T  // the payload that caused the failure
    fn original(self): T  // the original payload, read-only
}
```

The interface requires three methods. `message` returns a human-readable
description. `data` returns the failing payload --- and this is the
critical detail --- `data` is mutable in a retry context, so you can
correct the payload before the failing function re-runs. `original`
returns the payload as it was when the exception was first thrown,
unchanged by any retry corrections.

### 7.3.2 Defining Exception Types

An exception type is a regular type with `fulfills Exception<T>`:

```flow
type ParseError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

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

Three things to notice:

1. The `payload` field is `:mut`. This is what makes `ex.data` mutable in
   retry blocks.

2. The `original_payload` field is immutable. It is set once at
   construction time --- both fields receive the same initial value ---
   and never changes.

3. The constructor receives the raw value and stores it in both fields.
   After construction, they diverge: `payload` can be corrected by retry
   logic while `original_payload` preserves the initial state.

Here is a second example with a structured payload:

```flow
type ValidationError fulfills Exception<record> {
    msg: string,
    payload: record:mut,
    original_payload: record,

    constructor from_record(m: string, r: record): ValidationError {
        return ValidationError {
            msg: m,
            payload: r,
            original_payload: r
        }
    }

    fn message(self): string { return self.msg }
    fn data(self): record { return self.payload }
    fn original(self): record { return self.original_payload }
}
```

The pattern is the same regardless of the payload type. The `T` in
`Exception<T>` can be any type: `string`, `record`, `int`, a custom
struct --- whatever makes sense for the domain.

### 7.3.3 `throw`

To throw an exception, use the `throw` keyword followed by an exception
value:

```flow
throw ParseError.from_raw("unexpected token", raw_line)
throw ValidationError.from_record("missing required field", row)
```

You can also throw a plain string. The runtime wraps it in a default
exception type:

```flow
throw "something went wrong"
```

An unhandled `throw` propagates up the call stack until it reaches a
`try`/`catch` block or the program terminates with an unhandled exception
error.

Exceptions propagate automatically. Unlike results, which must be
explicitly propagated with `?` at each call site, an exception unwinds
the call stack silently past any function that does not `try`/`catch` it.
This is both the power and the danger of exceptions. A function five
levels deep can throw, and the exception will pass through four
intermediate functions without any of them mentioning it. This is useful
for truly exceptional conditions where every intermediate function would
just re-throw. It is harmful when used for expected failures, because the
intermediate functions have no indication in their signatures that an
exception might pass through them.

This is why Flow provides three mechanisms. If the failure is expected,
put it in the return type (`result<T, E>`). If it is exceptional, let it
unwind.

### 7.3.4 `try` and `catch`

The `try` block marks a region of code that may throw exceptions. The
`catch` block handles them:

```flow
module try_demo

import io (println)

fn parse(input: string): int {
    if (input == "") {
        throw ParseError.from_raw("empty input", input)
    }
    // ... parsing logic ...
    return 42
}

fn main() {
    try {
        let result = parse("")
        println(f"parsed: {result}")
    } catch (ex: ParseError) {
        println(f"parse failed: {ex.message()}")
    }
}
```

```
$ flow run try_demo.flow
parse failed: empty input
```

When `parse` throws a `ParseError`, execution jumps to the `catch` block.
The exception object is bound to `ex`, and you can call its methods:
`ex.message()`, `ex.data()`, `ex.original()`.

Multiple `catch` blocks can handle different exception types:

```flow
try {
    let result = src -> read_csv -> parse -> validate -> write
} catch (ex: ParseError) {
    println(f"parse error: {ex.message()}")
} catch (ex: ValidationError) {
    println(f"validation error: {ex.message()}")
}
```

The first `catch` whose type matches the thrown exception handles it. If
no `catch` matches, the exception propagates.

### 7.3.5 The `finally` Block

`finally` runs exactly once when the `try` block exits, regardless of
whether it succeeded, was caught, or is propagating an unhandled exception:

```flow
fn process_file(path: string) {
    let handle = open(path)
    try {
        let data = read_all(handle)
        transform(data)
    } catch (ex: ParseError) {
        log(f"parse error: {ex.message()}")
    } finally {
        close(handle)  // always runs
    }
}
```

The `finally` block has an optional exception parameter that lets you
inspect whether an exception occurred:

```flow
try {
    process()
} catch (ex: ParseError) {
    handle(ex)
} finally (? ex: Exception) {
    if (ex) {
        log(f"completed with error: {ex.message()}")
    }
    cleanup()
}
```

The `?` before `ex` indicates the parameter is optional. If the `try`
block succeeded (or the exception was caught), `ex` may be absent. If an
unhandled exception is propagating, `ex` is present.

Key rule: `finally` runs exactly once at termination. It never runs
between retries.

---

## 7.4 The Retry Mechanism

Retry is Flow's distinctive contribution to exception handling. In most
languages, when an operation fails, you either handle the failure or
propagate it. Flow adds a third option: correct the input and try again.

### 7.4.1 Naming the Failing Function

The `retry` block names the specific function to re-invoke:

```flow
try {
    let result = parse(raw_input)
} retry parse (ex: ParseError, attempts: 3) {
    ex.data = sanitize(ex.data)  // correct the payload
    // parse() re-runs with the corrected value
}
```

`retry parse` means: when `parse` throws a `ParseError`, execute this
block, then call `parse` again with the corrected `ex.data`. The
`attempts: 3` clause limits retries to three attempts. After three
failures, the exception either falls through to a `catch` block or
propagates up the call stack.

This is not `catch` followed by a manual re-call. The runtime manages the
retry loop, passes the corrected data to the named function, and feeds its
result back through the rest of the expression. Naming a function that
does not appear in the `try` block is a compile error.

### 7.4.2 Retry in Composition Chains

Retry is especially powerful in composition chains. Consider a data
pipeline:

```flow
try {
    let result = line -> parse -> validate -> write
} retry parse (ex: ParseError, attempts: 3) {
    ex.data = sanitize(ex.data)
}
```

When `parse` throws, the retry block corrects `ex.data` and `parse`
re-runs. If the retry succeeds, its result flows into `validate` and then
`write` as normal. The rest of the chain does not know that a retry
happened.

You can have multiple retry blocks for different functions and different
exception types:

```flow
try {
    let result = src -> read_csv -> parse -> validate -> write
} retry parse (ex: ParseError, attempts: 3) {
    ex.data = sanitize(ex.data)
} retry validate (ex: ValidationError, attempts: 2) {
    ex.data.missing_field = default_value()
}
```

Each retry block is independent. They target different functions and
different exception types. The `attempts` count is per-block: if `parse`
fails three times, its retries are exhausted, but `validate` still has
its own two attempts.

### 7.4.3 Correcting Data in Retry

The retry block has access to two values on the exception object:

- **`ex.data`** is mutable. Modify it before the function re-runs. This
  is the corrected input.

- **`ex.original`** is immutable. It holds the value as it was when the
  exception was first thrown, regardless of how many corrections you have
  made across retry attempts.

```flow
try {
    let result = parse(raw_input)
} retry parse (ex: ParseError, attempts: 3) {
    println(f"attempt failed. original: {ex.original}")
    println(f"current data: {ex.data}")
    ex.data = sanitize(ex.data)
    // parse re-runs with the sanitized value
}
```

On the first retry, `ex.data` and `ex.original` hold the same value ---
the original input that caused the failure. After the retry block modifies
`ex.data`, the second retry attempt (if needed) sees the modified value in
`ex.data` but the original, unchanged value in `ex.original`. This
separation is critical for logging and diagnostics: you always know what
the initial input was, even after multiple correction attempts.

### 7.4.4 Escalation: Retry, Catch, Propagate

When retries are exhausted, the exception escalates to the `catch` block
for the same type. If no `catch` exists, the exception propagates up the
call stack. Here is the full escalation chain:

```flow
try {
    let result = src -> read_csv -> parse -> validate -> write

} retry parse (ex: ParseError, attempts: 3) {
    // Attempt 1: sanitize the input
    // Attempt 2: sanitize again
    // Attempt 3: sanitize one more time
    ex.data = sanitize(ex.data)

} catch (ex: ParseError) {
    // All 3 retries failed. ex.data is the last corrected value.
    // ex.original is the initial failing value.
    log(f"parse failed after 3 attempts.")
    log(f"  original input: {ex.original}")
    log(f"  last attempt:   {ex.data}")

} finally (? ex: Exception) {
    if (ex) {
        log("pipeline completed with errors")
    }
    close_connections()
}
```

The escalation order, spelled out:

1. **Exception thrown:** the `retry` block runs if one matches the
   exception type and names the failing function. `ex.data` is corrected.
   The function re-runs.

2. **Still fails:** the `retry` block runs again, up to the `attempts`
   limit.

3. **Attempts exhausted:** the exception falls through to `catch` if a
   matching `catch` block exists.

4. **No catch:** the exception propagates up the call stack.

5. **`finally` runs exactly once**, after everything else, regardless of
   the outcome.

### 7.4.5 Execution Order

Here is every possible path through a `try`/`retry`/`catch`/`finally`
block:

**Try succeeds:**
```
try -> finally
```

**Retry fixes it:**
```
try -> retry -> (function re-executes successfully) -> finally
```

**Retry exhausted, catch exists:**
```
try -> retry (N times) -> catch -> finally
```

**Retry exhausted, no catch:**
```
try -> retry (N times) -> finally -> exception propagates
```

**No retry, catch exists:**
```
try -> catch -> finally
```

**No retry, no catch:**
```
try -> finally -> exception propagates
```

`finally` always runs. It never runs between retries. If you need logging
between retry attempts, put it in the retry block itself.

### 7.4.6 A Concrete Retry Trace

To make the execution order tangible, here is a small program with print
statements at every stage:

```flow
module retry_trace

import io (println)

type DataError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor create(m: string, p: string): DataError {
        return DataError { msg: m, payload: p, original_payload: p }
    }

    fn message(self): string { return self.msg }
    fn data(self): string { return self.payload }
    fn original(self): string { return self.original_payload }
}

fn process(input: string): string {
    println(f"  process called with: '{input}'")
    if (input != "good") {
        throw DataError.create("bad input", input)
    }
    return f"processed({input})"
}

fn main() {
    try {
        println("1. entering try")
        let result = process("bad")
        println(f"2. success: {result}")

    } retry process (ex: DataError, attempts: 2) {
        println(f"3. retry: original='{ex.original}', data='{ex.data}'")
        ex.data = "still bad"

    } catch (ex: DataError) {
        println(f"4. catch: original='{ex.original}', data='{ex.data}'")

    } finally {
        println("5. finally: cleanup")
    }
}
```

```
$ flow run retry_trace.flow
1. entering try
  process called with: 'bad'
3. retry: original='bad', data='bad'
  process called with: 'still bad'
3. retry: original='bad', data='still bad'
  process called with: 'still bad'
4. catch: original='bad', data='still bad'
5. finally: cleanup
```

Walk through the output line by line:

- The try block runs. `process("bad")` throws.
- Retry attempt 1: `ex.original` is `"bad"`, `ex.data` is `"bad"`. The
  block sets `ex.data` to `"still bad"`. Process re-runs with
  `"still bad"` and throws again.
- Retry attempt 2: `ex.original` is still `"bad"` (never changes).
  `ex.data` is `"still bad"`. The block sets it again. Process re-runs
  and throws again.
- Retries exhausted. The exception falls through to `catch`.
  `ex.original` is `"bad"`. `ex.data` is `"still bad"`.
- `finally` runs once, after `catch`.

Note that `println("2. success: ...")` never executes --- the exception
short-circuits the try block.

---

## 7.5 Choosing an Error Strategy

The three mechanisms serve different purposes. Choosing the right one is
not a matter of taste --- each has a natural domain.

### Option: Value Might Not Exist

Use `option<T>` when the absence of a value is a normal, expected outcome
with no error information needed.

- Looking up a key in a map: it might not be there.
- Searching an array for a value: it might not exist.
- Reading a line from a file: there might be no more lines.
- Getting a configuration setting: it might not be set.

The common thread: there is nothing *wrong*. The value simply might not be
present. The caller does not need to know why --- the answer is "it is
not there."

```flow
fn lookup(users: map<string, User>, id: string): User? {
    return users.get(id)
}
```

### Result: Operation Might Fail in Expected Ways

Use `result<T, E>` when an operation can fail and the caller needs to know
what went wrong.

- Parsing a string as an integer: the string might not be a number, and
  the caller needs the error message.
- Validating user input: validation might fail, and the caller needs to
  know which field failed.
- Writing to a file: the write might fail, and the caller needs to know
  if it was a permissions error or a disk-full error.

The common thread: failure is expected, recoverable, and the error value
carries information the caller will use.

```flow
fn parse_config(text: string): result<Config, string> {
    let lines = split(text, "\n")
    if (len(lines) == 0) {
        return err("empty config file")
    }
    // ... parse lines ...
    return ok(config)
}
```

### Exception: Exceptional Conditions

Use exceptions for conditions outside the expected failure path:

- Infrastructure failures (network drops, disk corruption).
- Data that violates invariants the function cannot check in advance.
- Situations where retry with corrected input might succeed.
- Errors in data pipelines where you want automatic retry and escalation.

The common thread: the function that encounters the problem cannot fix it
locally. It needs to unwind to a caller that has enough context to
recover, retry, or report.

```flow
fn parse_record(raw: string): Record {
    if (raw.contains("\0")) {
        throw ParseError.from_raw("null byte in record", raw)
    }
    // ... parse ...
    return record
}
```

### Comparison Table

| | Option | Result | Exception |
|---|---|---|---|
| **Use for** | Absence | Expected failure | Exceptional conditions |
| **Error info** | None | Error value `E` | Exception object with `message`, `data`, `original` |
| **Propagation** | `?` returns `none` | `?` returns `err(e)` | Automatic stack unwinding |
| **Default value** | `??` | `??` | Not applicable |
| **Pattern match** | `some(v)` / `none` | `ok(v)` / `err(e)` | `catch (ex: Type)` |
| **Retry** | Not applicable | Not applicable | `retry function_name` with mutable `ex.data` |
| **Caller burden** | Must handle or propagate | Must handle or propagate | Optional (`try`/`catch`) |

A rule of thumb: if the caller will handle the case inline with `??` or a
one-arm `match`, use option or result. If the caller will wrap a block of
code in `try` and handle failures structurally, use exceptions.

### A Decision Process

When you are writing a function that can fail, ask these questions in
order:

1. **Is the "failure" just absence?** The key is missing. The search found
   nothing. The input was empty. If there is nothing *wrong* and no
   information to convey, return `option<T>`.

2. **Is the failure expected, and does the caller need details?** The
   string was not valid JSON. The port was out of range. The required
   field was missing. If the caller will branch on the error, return
   `result<T, E>`.

3. **Is the failure unexpected, possibly correctable, or structural?**
   The network dropped mid-transfer. The data contained a null byte that
   should never appear. A downstream service returned a malformed
   response. If the function cannot handle it locally and the failure
   might benefit from retry with corrected data, throw an exception.

If you are unsure between result and exception, lean toward result. A
result in the return type is documentation: it tells every caller that
failure is possible. An exception is invisible in the signature. You can
always catch an exception and convert it to a result at a boundary ---
the reverse is not true.

### Mixed Strategies in a Call Stack

A common architecture uses all three in layers:

- **Leaf functions** (parsers, validators, lookups) return `option<T>` or
  `result<T, E>`. They are pure or nearly pure, and their failures are
  expected.

- **Middle-layer functions** (pipeline stages, service handlers) throw
  exceptions when they encounter conditions they cannot handle. They may
  also accept `result` returns from leaf functions and convert certain
  error cases to exceptions if the error is unrecoverable at that level.

- **Top-level functions** (`main`, request handlers, pipeline runners) use
  `try`/`retry`/`catch` to handle exceptions structurally. They convert
  caught exceptions into results, log entries, or user-facing messages.

This layering keeps each function focused. Leaf functions do not need to
know about retry logic. Top-level functions do not need to pattern-match
on every possible error variant from every leaf. The exception mechanism
bridges the gap.

---

## 7.6 Combining the Three

Real programs use all three mechanisms, often in the same function. Here
is a file processor that uses option for lookup, result for validation,
and exceptions for I/O failures:

```flow
module file_processor

import io (println, read_line, open, close, read_all)

type IOError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor create(m: string, p: string): IOError {
        return IOError { msg: m, payload: p, original_payload: p }
    }

    fn message(self): string { return self.msg }
    fn data(self): string { return self.payload }
    fn original(self): string { return self.original_payload }
}

fn find_config(paths: array<string>): string? {
    // Option: the config file might not exist at any path
    for (p: string in paths) {
        if (file_exists(p)) {
            return some(p)
        }
    }
    return none
}

fn parse_port(s: string): result<int, string> {
    // Result: the string might not be a valid port number
    let n = string_to_int(s) ?? -1
    if (n < 1) {
        return err(f"invalid port: {s}")
    }
    if (n > 65535) {
        return err(f"port out of range: {n}")
    }
    return ok(n)
}

fn load_config(): result<int, string> {
    let paths = ["./config.txt", "/etc/app/config.txt"]
    let path = find_config(paths) ?? ""

    if (path == "") {
        return err("no config file found")
    }

    try {
        // Exception: reading the file might fail
        let contents = read_all(open(path))
        let port = parse_port(contents)?
        return ok(port)
    } catch (ex: IOError) {
        return err(f"IO error: {ex.message()}")
    }
}

fn main() {
    match load_config() {
        ok(port) : println(f"server starting on port {port}"),
        err(msg) : println(f"config error: {msg}")
    }
}
```

Each mechanism does what it does best. `find_config` returns an option
because absence is the normal case when a file does not exist at a given
path. `parse_port` returns a result because invalid input is expected and
the caller needs the error message. The `try`/`catch` handles I/O
exceptions because file reads can fail for reasons beyond the program's
control.

The function `load_config` returns a `result`, translating the exception
into a result at the boundary. This is a common pattern: functions deep in
the call stack throw exceptions; functions closer to the surface catch
them and convert to results for a cleaner API.

---

## 7.7 What Goes Wrong

### Unhandled Option

```flow
fn main() {
    let x: int? = some(42)
    let y: int = x  // compile error: cannot assign int? to int
}
```

An `option<int>` is not an `int`. You must unwrap it with `match`, `??`,
`?`, or `if let`. The compiler rejects implicit unwrapping.

### Non-Exhaustive Match on Option

```flow
match find_user(id) {
    some(u) : process(u)
    // compile error: non-exhaustive match --- missing 'none' arm
}
```

A match on `option<T>` must cover both `some` and `none`, or include a
wildcard `_` arm.

### `?` in Wrong Return Type

```flow
fn get_name(): string {
    let user = find_user(id)?  // compile error: ? requires option return type
    return user.name
}
```

The `?` operator on an `option<T>` requires the enclosing function to
return `option<U>` (or `U?`). On a `result<T, E>`, it requires the
enclosing function to return `result<U, E>` with a compatible error type.

### Incompatible Error Types in `?`

```flow
fn fetch(): result<int, string> {
    let x = parse_int(s)?  // ok: both return result<_, string>
    let y = read_file(path)?  // compile error if read_file returns result<_, IOError>
    return ok(x + y)
}
```

When using `?` with results, the error type of the inner expression must
be compatible with the error type of the enclosing function. If they
differ, convert the error explicitly:

```flow
fn fetch(): result<int, string> {
    let y = match read_file(path) {
        ok(data) : data,
        err(e)   : return err(f"read failed: {e.message()}")
    }
    return ok(42)
}
```

### Unhandled Exception

```flow
fn main() {
    parse(bad_input)  // throws ParseError
    // no try/catch: program terminates with unhandled exception
}
```

An unhandled exception propagates to `main` and terminates the program
with an error message. Unlike results, exceptions do not appear in the
function signature. The programmer is responsible for knowing which
functions may throw. The convention is to document this, but the type
system does not enforce it.

### Retry Naming a Non-Existent Function

```flow
try {
    let x = parse(input)
} retry validate (ex: ParseError, attempts: 3) {
    // compile error: 'validate' does not appear in the try block
    ex.data = sanitize(ex.data)
}
```

The function named in `retry` must appear in the `try` block. Naming a
function that is not called there is a compile error.

### Non-Exhaustive Match on Result

```flow
match safe_divide(10, 3) {
    ok(v) : println(f"result: {v}")
    // compile error: non-exhaustive match --- missing 'err' arm
}
```

Like options, results require exhaustive matching. Both `ok` and `err`
must be covered, or a wildcard `_` arm must be present.

### Modifying `ex.original` in Retry

```flow
try {
    let result = parse(input)
} retry parse (ex: ParseError, attempts: 2) {
    ex.original = "overwrite"  // compile error: ex.original is immutable
    ex.data = sanitize(ex.data)  // ok: ex.data is mutable
}
```

The `original_payload` field is immutable. It preserves the value at throw
time for diagnostics. Only `ex.data` (backed by the `:mut` field `payload`)
can be modified in a retry block.

### Double-Wrapping Options

```flow
let x: int? = some(42)
let y: int? = x  // y is some(42), not some(some(42))
```

This is *not* an error. Auto-lifting does not fire when the source is
already `option<T>`. Assigning `int?` to `int?` is a plain copy. There
is no `option<option<int>>` unless you construct one explicitly. This
comes up most often when refactoring: if you change a function's return
type from `int` to `int?`, callers that assign the result to an `int?`
variable continue to work without changes.

### Using `??` with Mismatched Types

```flow
let x: int = some(42) ?? "default"
// compile error: ?? branches must have the same type
```

The left side of `??` unwraps to `int` (the inner type of `int?`). The
right side must also be `int`. A `string` default for an `int` option is
a type error.

---

## 7.8 A Complete Example: Data Pipeline with Retry

Here is a complete program that reads records, parses them, validates
them, and writes the results. It uses all three error mechanisms and
demonstrates the full retry escalation chain:

```flow
module pipeline

import io (println)

type ParseError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor from_raw(m: string, p: string): ParseError {
        return ParseError { msg: m, payload: p, original_payload: p }
    }

    fn message(self): string { return self.msg }
    fn data(self): string { return self.payload }
    fn original(self): string { return self.original_payload }
}

type Order {
    customer_id: string,
    amount: float
}

fn parse_order(raw: string): Order {
    // Simplified: expects "customer_id,amount"
    let parts = split(raw, ",")
    if (len(parts) != 2) {
        throw ParseError.from_raw("expected 2 fields", raw)
    }
    let id = parts[0]
    let amount = string_to_float(parts[1]) ?? -1.0
    if (amount < 0.0) {
        throw ParseError.from_raw("invalid amount", raw)
    }
    return Order { customer_id: id, amount: amount }
}

fn validate_order(o: Order): result<Order, string> {
    if (o.customer_id == "") {
        return err("missing customer ID")
    }
    if (o.amount <= 0.0) {
        return err(f"invalid amount: {o.amount}")
    }
    return ok(o)
}

fn sanitize(raw: string): string {
    // Strip leading/trailing whitespace, fix common formatting issues
    return trim(raw)
}

fn process_record(raw: string): string? {
    // Option: skip records that fail validation
    try {
        let order = parse_order(raw)
        match validate_order(order) {
            ok(valid) : return some(f"{valid.customer_id}: {valid.amount}"),
            err(msg)  : {
                println(f"  validation error: {msg}")
                return none
            }
        }
    } retry parse_order (ex: ParseError, attempts: 2) {
        println(f"  retrying parse. original: '{ex.original}', corrected: '{sanitize(ex.data)}'")
        ex.data = sanitize(ex.data)
    } catch (ex: ParseError) {
        println(f"  parse failed after retries: {ex.message()}")
        return none
    }
}

fn main() {
    let records = [
        "C001,49.99",
        "  C002 , 29.95 ",
        "bad-record",
        "C003,75.00",
        "",
        "C004,100.50"
    ]

    let processed: int:mut = 0
    let skipped: int:mut = 0

    for (raw: string in records) {
        println(f"processing: '{raw}'")
        match process_record(raw) {
            some(line) : {
                println(f"  ok: {line}")
                processed++
            },
            none : {
                skipped++
            }
        }
    }

    println(f"\nprocessed: {processed}, skipped: {skipped}")
}
```

This program demonstrates the natural layering:

- **Option** (`string?`): `process_record` returns `none` for records
  that should be skipped, whether due to parse failure or validation
  failure. The caller does not need to know why --- it just counts.

- **Result** (`result<Order, string>`): `validate_order` returns detailed
  error information that the caller uses to print a diagnostic message
  before returning `none`.

- **Exception with retry**: `parse_order` throws `ParseError` because
  whitespace issues might be fixable by sanitizing the input. The retry
  block corrects `ex.data` and the parse re-runs. After two attempts, the
  exception falls through to `catch`, which logs the failure and returns
  `none`.

---

## 7.9 Summary

Flow separates error handling into three mechanisms, each with a clear
purpose:

- **`option<T>`** (`T?`) represents absence. A value is either
  `some(value)` or `none`. Unwrap with `match`, `??`, `?`, or `if let`.
  Auto-lifting wraps plain `T` values in `some` when the target type is
  known to be `option<T>`.

- **`result<T, E>`** represents expected failure. An operation returns
  `ok(value)` or `err(error)`. The `?` operator propagates errors up the
  call stack. The `??` operator provides default values.

- **Exceptions** represent exceptional conditions. Types fulfill
  `Exception<T>` with `message`, `data`, and `original` methods. `throw`
  raises an exception. `try`/`catch` handles it. `retry` names a failing
  function, corrects `ex.data`, and re-runs it. `finally` runs exactly
  once at termination.

The three compose naturally. Functions deep in a call stack throw
exceptions; mid-level functions catch them and convert to results;
top-level functions use options to signal "nothing here." The `?` operator
works uniformly on both options and results, making propagation concise.

Chapter 8 introduces ownership and memory management --- how Flow tracks
who owns each value, prevents use-after-move, and manages memory without
a garbage collector.

---

## Exercises

**1.** Write a function `fn safe_parse_int(s: string): result<int, string>`
that returns `ok(n)` if the string is a valid integer and `err(msg)` with a
descriptive message if it is not. Test it with valid input, empty string
input, and non-numeric input.

**2.** Write a chain of three functions that each return `option<T>`, and
use the `?` propagation operator to thread them together. For example:
`find_user(id)?` then `get_email(user)?` then `parse_domain(email)?`. The
enclosing function should return `string?` and the chain should short-circuit
on the first `none`.

**3.** Define a custom `ValidationError` exception type that carries a
`record` payload. Write a `validate` function that throws this exception
when a required field is missing. Write a `try`/`retry` block that
corrects the missing field in `ex.data` and retries up to 2 times.

**4.** Build a small file processor that combines all three mechanisms:
use `option` to look up file paths, `result` to validate file contents,
and exceptions with retry to handle parse errors. The `main` function
should print a summary of what succeeded and what failed.

**5.** Write a program that demonstrates the full escalation chain:
a `try` block with a `retry` block (3 attempts), a `catch` block, and a
`finally` block. Have the retry block print each attempt number using
`ex.original` and `ex.data`. After all retries fail, have the `catch`
block print the final state. Have the `finally` block print "cleanup
complete" regardless of outcome. Run it and verify the execution order
matches the order described in Section 7.4.5.
