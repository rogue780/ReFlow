# Chapter 1: A First Program

The only way to learn a language is to write programs in it. This chapter
gets you writing, compiling, and running Flow programs immediately. By the
end you will have used variables, functions, loops, streams, and
composition --- enough to write real programs, and enough to make the rest
of the book concrete.

---

## 1.1 Hello, World

```flow
module hello

import io (println)

fn main() {
    println("Hello, World!")
}
```

Save this as `hello.flow`. Compile and run it:

```
$ flow run hello.flow
Hello, World!
```

That is the entire program. Four lines of substance, no boilerplate. Let us
take them apart.

**`module hello`** --- Every Flow source file begins with a module
declaration. The module name is an identifier that matches the file's
logical name within the project. A file without a module declaration
compiles with a warning and cannot be imported by other files. For a single
file program, the name does not matter much, but the declaration is
required. Module names can have multiple components separated by dots
(`module math.vector`), reflecting the file's path relative to the project
root. We will return to multi-file programs in Chapter 12.

**`import io (println)`** --- This imports the `println` function from the
`io` module in the standard library. The parenthesized list names exactly
which symbols to import. You could also write `import io` and then call
`io.println(...)`, but selective imports are idiomatic: they make
dependencies explicit and keep the local namespace clean.

Flow has three import forms:

```flow
import io                    ; import all exports, use as io.println(...)
import io (println, print)   ; import specific names into local scope
import io as output          ; alias, use as output.println(...)
```

For now, the second form --- named imports --- is all you need.

**`fn main()`** --- The entry point. Every executable Flow program must
have a `main` function taking no arguments. The return type is omitted here,
which means it returns `none` --- Flow's unit type, representing the absence
of a meaningful value. A `main` function that returns `none` causes the
process to exit with status 0.

**`println("Hello, World!")`** --- A function call. `println` writes a
string to standard output followed by a newline. The string literal uses
double quotes. There is no semicolon at the end of the line --- Flow does
not use semicolons as statement terminators. In Flow, the semicolon is the
comment character:

```flow
; This is a comment. Everything after the semicolon is ignored.
println("Hello, World!")  ; this is also a comment
```

If you have programmed in C, Java, JavaScript, Rust, or Go, the semicolon
as a comment character will feel unfamiliar. You will adjust quickly. The
advantage is that lines of code are visually uncluttered --- no trailing
punctuation on every statement.

There is no block comment syntax. Multi-line comments repeat the semicolon
on each line:

```flow
;================================
; This is a multi-line comment.
; Each line uses a semicolon.
;================================
```

---

## 1.2 Compiling and Running

The Flow toolchain provides four commands.

**`flow run <file>`** compiles the source to a temporary binary and executes
it immediately. This is what you will use most during development:

```
$ flow run hello.flow
Hello, World!
```

Any arguments after the file name are passed through to the program:

```
$ flow run myprogram.flow arg1 arg2
```

**`flow build <file>`** compiles the source to a permanent binary. By
default the output is named after the source file (without the `.flow`
extension). You can specify a different name with `-o`:

```
$ flow build hello.flow
$ ./hello
Hello, World!

$ flow build hello.flow -o greet
$ ./greet
Hello, World!
```

The resulting binary is a standalone executable. It has no dependency on the
Flow toolchain, no runtime interpreter, and no virtual machine. You can copy
it to another machine with the same architecture and run it directly.

**`flow check <file>`** runs the full compiler front end --- lexing,
parsing, name resolution, and type checking --- without generating any
output. Use it when you want to verify that your program is correct
without waiting for C compilation and linking:

```
$ flow check hello.flow
$
```

Silence means success. Errors are printed to standard error with the file
name, line number, and column, so editors and IDEs can jump to the problem.

**`flow emit-c <file>`** outputs the generated C source instead of
compiling it. This is occasionally useful for understanding what the
compiler does, or for debugging subtle issues:

```
$ flow emit-c hello.flow
```

This prints the C translation to standard output. You can redirect it to a
file with `-o`:

```
$ flow emit-c hello.flow -o hello.c
```

You do not need to understand C to use Flow, but seeing the output can
demystify the compilation model. The generated C is not meant to be
beautiful --- it is meant to be correct and fast.

### How Compilation Works

Flow is a compiled language, not an interpreted one. The compiler translates
your source to C, then invokes `clang` to produce a native binary. The
pipeline has several stages, each with a specific job:

```
hello.flow  -->  [lexer]  -->  [parser]  -->  [resolver]
                                                  |
                                            [type checker]
                                                  |
                                             [lowering]
                                                  |
                                              [emitter]  -->  hello.c
                                                                 |
                                                              [clang]  -->  hello (binary)
```

The **lexer** breaks source text into tokens --- keywords, identifiers,
literals, operators. The **parser** arranges tokens into a syntax tree
that represents the structure of the program. The **resolver** binds every
name to its definition: when you write `println`, the resolver figures out
that it refers to the `println` imported from `io`. The **type checker**
verifies that every expression has a consistent type --- that you are not
adding a string to an integer, that function arguments match parameter
types, that all branches of a conditional return the same type.

After type checking, the **lowering** pass translates the typed syntax tree
into a simpler intermediate form, and the **emitter** formats that form as
C source. Finally, `clang` compiles the C to machine code.

All of this happens behind `flow run` and `flow build`. You do not need to
manage any of these steps. The important thing to understand is that Flow
programs are checked thoroughly before any code is generated: if your
program compiles, the types are consistent, every name is defined, and
every function is called with the right number and type of arguments.

Why compile through C rather than directly to machine code? Two reasons.
First, C compilers like `clang` have decades of optimization work behind
them. By emitting C, Flow gets high-quality code generation for free.
Second, C is a widely understood target. If something goes wrong at the
lowest level, the generated C is readable and debuggable --- it is not a
black box. This is a practical choice, not an ideological one.

---

## 1.3 A Temperature Converter

The canonical second program in any language prints a temperature conversion
table. Here is a version that converts Celsius to Fahrenheit in steps of
10 degrees:

```flow
module temperature

import io (println)

fn main() {
    let celsius: int:mut = 0
    while (celsius <= 100) {
        let fahrenheit: float = cast<float>(celsius) * 9.0 / 5.0 + 32.0
        println(f"{celsius}\t{fahrenheit}")
        celsius += 10
    }
}
```

```
$ flow run temperature.flow
0	32.0
10	50.0
20	68.0
30	86.0
40	104.0
50	122.0
60	140.0
70	158.0
80	176.0
90	194.0
100	212.0
```

Several new features appear here. We will cover each in turn.

**`let celsius: int:mut = 0`** declares a mutable integer variable. The
`:mut` qualifier after the type is what makes it mutable. Without it, the
binding would be immutable and any attempt to reassign it would be a
compile error. The initial value is `0`.

**`while (celsius <= 100) { ... }`** is a while loop. The condition is
evaluated before each iteration. The body executes as long as the
condition is true. The parentheses around the condition are required.

**`cast<float>(celsius)`** converts the integer `celsius` to a floating
point number. Flow does not perform implicit numeric conversions between
integers and floats --- you must be explicit. The `cast<T>` operator takes a
type parameter in angle brackets and the value to convert in parentheses.
Widening conversions (like `int` to `float`) always succeed. Narrowing
conversions (like `float` to `int`) truncate toward zero: `cast<int>(3.9)`
produces `3`.

**`f"{celsius}\t{fahrenheit}"`** is a string interpolation expression. The
`f` prefix marks it as an f-string. Expressions inside `{...}` are
evaluated and converted to their string representations. The `\t` is a
tab character. F-strings can contain any expression, not just variable
names:

```flow
let x = 42
println(f"double: {x * 2}, half: {x / 2}")
```

This prints `double: 84, half: 21`. You can also use plain string
concatenation with the `+` operator:

```flow
let greeting = "Hello" + ", " + "World!"
```

F-strings are generally preferred for readability.

**`celsius += 10`** is an update operator. It adds 10 to `celsius` and
stores the result back. This is equivalent to `celsius = celsius + 10`.
The update operators `+=`, `-=`, `*=`, `/=`, `++`, and `--` are all
available, but only on `:mut` bindings.

Why does the program use `cast<float>` instead of just writing `celsius *
9.0 / 5.0 + 32.0`? Because `celsius` is an `int` and `9.0` is a `float`.
Flow does not silently coerce integers to floats in arithmetic. The types of
both operands must match. The explicit cast makes the conversion visible.
This is a deliberate design choice: silent numeric coercions are a
well-documented source of bugs in C, JavaScript, and other languages. Flow
requires you to say what you mean.

Here is a version of the same program that uses a helper function to make
the conversion formula reusable:

```flow
module temperature_v2

import io (println)

fn to_fahrenheit(celsius: int): float {
    return cast<float>(celsius) * 9.0 / 5.0 + 32.0
}

fn main() {
    let c: int:mut = 0
    while (c <= 100) {
        println(f"{c}\t{to_fahrenheit(c)}")
        c += 10
    }
}
```

The output is identical, but now the conversion logic lives in a named
function that can be tested, reused, and understood independently of the
loop that calls it.

---

## 1.4 Variables and Mutability

Flow bindings are immutable by default:

```flow
let x = 42
let name = "Flow"
let pi: float = 3.14159
```

The `let` keyword introduces a binding. The type can be annotated explicitly
(`let x: int = 42`) or inferred from the value (`let x = 42`). Type
inference is local: the compiler looks at the right-hand side and
determines the type. You never need to annotate a local variable if the
type is obvious from context, but you always can.

The basic types you will use in this chapter are:

| Type | Description | Example Literal |
|------|-------------|-----------------|
| `int` | 32-bit signed integer | `42`, `-7`, `1_000_000` |
| `float` | 64-bit floating point | `3.14`, `-0.5`, `1.0` |
| `bool` | Boolean | `true`, `false` |
| `string` | UTF-8 string | `"hello"`, `f"x={x}"` |

Chapter 2 covers the full set of numeric types, including `int64`, `byte`,
`uint`, `float32`, and the widening and narrowing rules between them.

Immutable means immutable. Once bound, the value cannot change:

```flow
let x = 42
x = 43       ; compile error: cannot assign to immutable binding 'x'
```

This is not a suggestion from the compiler. It is an error, and the program
will not compile.

To make a binding mutable, add `:mut` after the type:

```flow
let x: int:mut = 0
x = 42       ; ok
x += 10      ; ok
x++          ; ok: x is now 53
```

The `:mut` qualifier is part of the type annotation, not the variable name.
When you write `let x: int:mut = 0`, you are saying "`x` is a mutable
`int`." The compiler tracks mutability as part of the type.

When using type inference with mutable bindings, you still need the type
annotation because `:mut` has no place to attach without it:

```flow
let x: int:mut = 0     ; mutable, type annotated
let y = 42              ; immutable, type inferred
```

Here is a summary of the update operators:

| Operator | Meaning | Example |
|----------|---------|---------|
| `=`      | Assignment | `x = 10` |
| `+=`     | Add and assign | `x += 5` |
| `-=`     | Subtract and assign | `x -= 3` |
| `*=`     | Multiply and assign | `x *= 2` |
| `/=`     | Divide and assign | `x /= 4` |
| `++`     | Increment by one | `x++` |
| `--`     | Decrement by one | `x--` |

All of these are only valid on `:mut` bindings. Using any of them on an
immutable binding is a compile error.

Mutable strings work too:

```flow
let msg: string:mut = "hello"
msg = msg + " world"
println(msg)  ; prints "hello world"
```

Why default to immutable? Because immutable data is easier to reason about.
It cannot change out from under you. It can be shared across threads without
locks. It can be passed to functions without worrying about aliasing. When
you do need mutation, `:mut` makes it visible at the declaration site ---
you can see at a glance which bindings change and which do not. This is one
of the organizing principles of Flow: mutation is allowed, but it is always
explicit and always local.

---

## 1.5 Reading Input

So far our programs have produced output but not consumed input. Let us
build an interactive temperature converter that reads a value from the user.

The `io` module provides `read_line`, which reads one line of text from
standard input. The `conv` module provides parsing functions that convert
strings to numbers. Here is the program:

```flow
module interactive_temp

import io (println, read_line)
import conv (string_to_int)

fn main() {
    println("Enter a temperature in Celsius:")
    let line: string = read_line() ?? ""
    let celsius: int = string_to_int(line) ?? 0
    let fahrenheit: float = cast<float>(celsius) * 9.0 / 5.0 + 32.0
    println(f"{celsius} C = {fahrenheit} F")
}
```

```
$ flow run interactive_temp.flow
Enter a temperature in Celsius:
37
37 C = 98.6 F
```

Two new ideas appear here.

**`read_line()`** returns `string?`, not `string`. The `?` suffix is
syntactic sugar for `option<string>` --- a type that is either `some(value)`
or `none`. `read_line` returns `none` when there is no more input (end of
file). This is Flow's way of representing values that might be absent: not
with null pointers, not with sentinel values, but with a type that forces
you to handle the absence case.

**`??`** is the null coalescing operator. `read_line() ?? ""` means: if
`read_line()` returns `some(s)`, use `s`; if it returns `none`, use `""`
instead. The right-hand side is only evaluated when the left is `none`
(short-circuit semantics).

The same pattern applies to `string_to_int`. Its signature is
`fn string_to_int(s: string): int?` --- it returns `some(n)` if the string
is a valid integer, and `none` if it is not. Writing `string_to_int(line)
?? 0` means: parse the string, and if parsing fails, default to 0.

Here is a more complete interactive program that handles both integer and
floating point input:

```flow
module converter

import io (println, print, read_line)
import conv (string_to_float)

fn main() {
    print("Celsius: ")
    let input: string = read_line() ?? ""
    let celsius: float = string_to_float(input) ?? 0.0
    let fahrenheit: float = celsius * 9.0 / 5.0 + 32.0
    println(f"{celsius} C = {fahrenheit} F")
}
```

Note the use of `print` instead of `println` for the prompt --- `print`
writes without a trailing newline, so the cursor stays on the same line as
the prompt text.

This is a first taste of how Flow handles the absence of values. We will
not go deeper into `option<T>` here --- Chapter 7 covers it in full,
including pattern matching with `match` and conditional unwrapping with
`if let`. For now, `??` is enough to get interactive programs working.

---

## 1.6 Functions

We have been calling functions. Now let us write some.

A function in Flow has a name, a parameter list with types, a return type,
and a body:

```flow
fn fahrenheit(celsius: int): float {
    return cast<float>(celsius) * 9.0 / 5.0 + 32.0
}
```

Every parameter must have a type annotation. The return type follows the
closing parenthesis of the parameter list, after a colon. The `return`
keyword sends a value back to the caller.

For functions whose body is a single expression, there is a shorter
**expression form**:

```flow
fn fahrenheit(celsius: int): float = cast<float>(celsius) * 9.0 / 5.0 + 32.0
```

The `= expression` form replaces the braces and the `return`. It means the
same thing. Use it when the function fits comfortably on one line.

Here is a complete program using named functions:

```flow
module functions_demo

import io (println)

fn double(x: int): int = x * 2

fn square(x: int): int = x * x

fn factorial(n: int): int {
    if (n <= 1) {
        return 1
    }
    return n * factorial(n - 1)
}

fn classify(n: int): string {
    if (n < 0) {
        return "negative"
    } else if (n == 0) {
        return "zero"
    }
    return "positive"
}

fn main() {
    println(f"double(5) = {double(5)}")
    println(f"square(7) = {square(7)}")
    println(f"factorial(10) = {factorial(10)}")
    println(f"classify(-3) = {classify(-3)}")
    println(f"classify(0) = {classify(0)}")
    println(f"classify(42) = {classify(42)}")
}
```

```
$ flow run functions_demo.flow
double(5) = 10
square(7) = 49
factorial(10) = 3628800
classify(-3) = negative
classify(0) = zero
classify(42) = positive
```

A few things to notice.

**Recursion works.** `factorial` calls itself. Flow has no special syntax
for recursion --- if a function is in scope, it can be called, including by
itself. The recursive calls continue until `n <= 1`, at which point the
base case returns `1` and the chain unwinds.

**Multiple return paths.** `classify` has three `return` statements in
different branches. Each branch returns a `string`, so the return type is
`string`. The compiler checks that all paths return a value of the declared
type. If you forget a return path --- say you delete the final `return
"positive"` --- the compiler will tell you.

**Expression form vs. block form.** `double` and `square` use `= expr`.
`factorial` and `classify` use `{ ... return ... }`. The choice is
stylistic. Expression form is shorter for simple transformations. Block form
is necessary when you need conditionals, loops, or multiple statements.

Functions that perform side effects without producing a useful value return
`none`:

```flow
fn greet(name: string): none {
    println(f"Hello, {name}!")
}
```

The return type `none` is Flow's equivalent of `void` in C or `Unit` in
Kotlin. You can omit the explicit `return` at the end of a `none`-returning
function; the compiler inserts it automatically.

Functions with multiple parameters work as you would expect:

```flow
fn add(x: int, y: int): int = x + y

fn max_of(a: int, b: int): int {
    if (a > b) {
        return a
    }
    return b
}

fn clamp(value: int, low: int, high: int): int {
    if (value < low) {
        return low
    } else if (value > high) {
        return high
    }
    return value
}
```

Flow also has an `if`/`else` expression form. Since `if`/`else` produces
a value when both branches have the same type, `max_of` could also be
written:

```flow
fn max_of(a: int, b: int): int {
    let result = if (a > b) { a } else { b }
    return result
}
```

Or with the ternary operator:

```flow
fn max_of(a: int, b: int): int = a > b ? a : b
```

All three forms are equivalent. Use whichever is clearest for the case at
hand.

---

## 1.7 A Taste of Streams

Streams are one of Flow's distinctive features. A `stream<T>` is a lazy
sequence that produces values one at a time. The producer suspends on each
`yield` and resumes when the consumer asks for the next value. Nothing is
computed until something pulls from the stream.

Here is a function that produces a stream of integers:

```flow
fn range(n: int): stream<int> {
    let i: int:mut = 0
    while (i < n) {
        yield i
        i++
    }
}
```

`range(5)` does not produce an array of five integers. It produces a stream
that, when consumed, will yield 0, then 1, then 2, then 3, then 4. The
return type `stream<int>` tells you this: the function produces integers
lazily, not all at once.

The `yield` keyword is what makes this a stream function. Each time
execution reaches `yield i`, the current value of `i` is emitted to the
consumer and the function suspends. When the consumer requests the next
value, execution resumes at the statement after `yield` --- in this case,
`i++` --- and continues until the next `yield` or until the function
returns.

The primary way to consume a stream is a `for` loop:

```flow
for (i: int in range(5)) {
    println(f"{i}")
}
```

This prints:

```
0
1
2
3
4
```

The `for` loop pulls one value at a time from the stream. On each
iteration, `i` is bound to the next value. When the stream is exhausted
--- when the `while` loop inside `range` finishes --- the `for` loop ends.

Here is a slightly more interesting stream that generates the Fibonacci
sequence:

```flow
fn fibonacci(max: int): stream<int> {
    let a: int:mut = 0
    let b: int:mut = 1
    while (a <= max) {
        yield a
        let next = a + b
        a = b
        b = next
    }
}
```

And consuming it:

```flow
for (n: int in fibonacci(100)) {
    println(f"{n}")
}
```

This prints `0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89` --- all Fibonacci
numbers up to 100, one per line. The stream produces them lazily: at no
point does the entire list exist in memory.

Now let us build a word counter. This program splits a string into words,
streams them one at a time, and counts them:

```flow
module word_count

import io (println)
import string (split)

fn words(text: string): stream<string> {
    let parts: array<string> = split(text, " ")
    for (word: string in parts) {
        yield word
    }
}

fn count(s: stream<string>): int {
    let n: int:mut = 0
    for (_: string in s) {
        n++
    }
    return n
}

fn main() {
    let text = "the quick brown fox jumps over the lazy dog"
    let n = count(words(text))
    println(f"word count: {n}")
}
```

```
$ flow run word_count.flow
word count: 9
```

`words` takes a string, splits it on spaces into an array using the
`string` module's `split` function, then yields each element as a stream.
The `for` loop inside `words` iterates over the array, and `yield` emits
each word one at a time.

`count` takes a stream of strings and counts how many values it produces.
The underscore `_` in the `for` loop means "bind the value but do not use
it." The loop simply increments `n` for each value, and when the stream
ends, `n` holds the total count.

In `main`, `count(words(text))` calls `words` to produce a stream, then
passes that stream to `count`. The values flow lazily: `words` yields one
word, `count` receives it and increments, `words` yields the next, and so
on.

Streams can also be used to build other streams. Here is a function that
takes a stream of strings and produces a stream containing only the
non-empty ones:

```flow
fn non_empty(s: stream<string>): stream<string> {
    for (item: string in s) {
        if (item != "") {
            yield item
        }
    }
}
```

This pattern --- consuming a stream with `for`, applying some logic, and
yielding a subset or transformation --- is the fundamental building block
of stream processing. You will see it repeatedly throughout this book.

We will not go deeper into streams here. Chapter 9 covers stream helpers
like `map`, `filter`, `take`, and `reduce`, and Chapter 10 covers
concurrent streams with coroutines. For now, the important idea is: streams
are lazy sequences produced by `yield` and consumed by `for`.

---

## 1.8 Composition: Your First Pipeline

The nested function call `count(words(text))` reads inside-out: you start
at the innermost call (`words`), then work outward (`count`). This is
fine for two functions, but it becomes hard to read as chains grow longer.
Consider `format(validate(parse(clean(input))))` --- the data flows right
to left, the opposite of how you read.

Flow's **composition operator** `->` rewrites nested calls as a
left-to-right pipeline:

```flow
fn main() {
    let text = "the quick brown fox jumps over the lazy dog"
    let n = text -> words -> count
    println(f"word count: {n}")
}
```

`text -> words -> count` means: take `text`, pass it to `words`, then pass
the result to `count`. It is exactly equivalent to `count(words(text))`,
but the data flows left to right on the page, matching the order of
execution. You read the pipeline the way the data moves.

Here is a simpler numeric example:

```flow
module compose_demo

import io (println)

fn double(x: int): int = x * 2

fn square(x: int): int = x * x

fn negate(x: int): int = 0 - x

fn main() {
    ; Nested calls: read inside-out
    let a = negate(square(double(5)))

    ; Composition: read left to right
    let b = 5 -> double -> square -> negate

    println(f"nested:      {a}")
    println(f"composition: {b}")
}
```

```
$ flow run compose_demo.flow
nested:      -100
composition: -100
```

Both produce the same result. `5 -> double -> square -> negate` pushes `5`
onto an implicit value stack, then `double` consumes it and pushes `10`,
then `square` consumes `10` and pushes `100`, then `negate` consumes `100`
and pushes `-100`.

Composition works with functions of any arity. When a function takes two
arguments, the two preceding values on the stack are consumed:

```flow
fn add(x: int, y: int): int = x + y

fn main() {
    ; 3 and 4 are pushed, add consumes both, double consumes the result
    let result = 3 -> 4 -> add -> double
    println(f"result: {result}")  ; 14
}
```

`3 -> 4 -> add -> double` pushes `3`, pushes `4`, then `add` (arity 2)
pops both and pushes `7`, then `double` pops `7` and pushes `14`.

The composition operator is not syntactic sugar for method chaining or
simple piping as in Unix shells. It is a general-purpose mechanism based on
a value stack that connects values to functions. It extends naturally to
fan-out (splitting a value to multiple functions in parallel) and streaming
--- topics covered in Chapters 4, 9, and 10.

To give you a preview of fan-out, here is a taste:

```flow
fn add(x: int, y: int): int = x + y

fn main() {
    ; Fan-out: 5 is passed to both double and square,
    ; their results feed into add
    let result = 5 -> (double | square) -> add
    println(f"result: {result}")  ; double(5) + square(5) = 10 + 25 = 35
}
```

The `(double | square)` notation means: send the incoming value to both
`double` and `square`, independently. Their results (two values) are pushed
onto the stack, and `add` (arity 2) consumes both. This is Chapter 4
material; mentioning it here just to show where composition leads.

For now, use `->` whenever you find yourself writing deeply nested function
calls. It is the most distinctive feature of Flow's syntax, and it becomes
second nature quickly.

---

## 1.9 For and While

You have already seen both loop forms. Let us collect the details in one
place.

**`while` loops** execute a body as long as a condition is true:

```flow
let i: int:mut = 0
while (i < 10) {
    println(f"{i}")
    i++
}
```

The condition is checked before each iteration, including the first. If the
condition is false initially, the body never executes. The parentheses
around the condition are required.

An infinite loop uses `while (true)`:

```flow
while (true) {
    ; runs until break or the program exits
}
```

**`for` loops** iterate over a collection or stream:

```flow
let names: array<string> = ["alice", "bob", "carol"]
for (name: string in names) {
    println(f"hello, {name}")
}
```

The loop variable (`name`) is bound to each element in turn. The type
annotation (`: string`) is required --- Flow does not infer `for` loop
variable types. When the collection or stream is exhausted, the loop ends.

Both loops support **`break`** and **`continue`**:

```flow
; Find the first negative number
let nums = [3, 7, -2, 5, -8]
let found: int:mut = 0
for (n: int in nums) {
    if (n < 0) {
        found = n
        break     ; exit the loop immediately
    }
}
println(f"first negative: {found}")
```

```flow
; Sum only odd numbers from 1 to 9
let total: int:mut = 0
let i: int:mut = 0
while (i < 10) {
    i++
    if (i % 2 == 0) {
        continue  ; skip even numbers, jump to next iteration
    }
    total += i
}
println(f"sum of odds 1..9: {total}")  ; 25
```

`break` exits the innermost enclosing loop. `continue` skips the rest of
the current iteration and proceeds to the next one. Both apply to `while`
and `for` loops.

A `for` loop can iterate over both arrays and streams, and the syntax is
identical. This is intentional: you should be able to switch a data source
from an array to a stream (or vice versa) without changing the consuming
code.

Here is one more example that ties loops and mutable variables together ---
computing a sum:

```flow
module sum_table

import io (println)

fn main() {
    let n: int:mut = 1
    let total: int:mut = 0
    while (n <= 10) {
        total += n
        println(f"sum of 1..{n} = {total}")
        n++
    }
}
```

```
$ flow run sum_table.flow
sum of 1..1 = 1
sum of 1..2 = 3
sum of 1..3 = 6
sum of 1..4 = 10
sum of 1..5 = 15
sum of 1..6 = 21
sum of 1..7 = 28
sum of 1..8 = 36
sum of 1..9 = 45
sum of 1..10 = 55
```

Two mutable variables, one loop, string interpolation to observe the
running total. This is the kind of program you should be able to write
without hesitation after reading this chapter.

---

## 1.10 Putting It Together

Here is a slightly longer program that uses most of what we have covered.
It prints a FizzBuzz table --- a classic exercise where multiples of 3
print "Fizz", multiples of 5 print "Buzz", multiples of both print
"FizzBuzz", and everything else prints the number:

```flow
module fizzbuzz

import io (println)

fn fizzbuzz(n: int): string {
    if (n % 15 == 0) {
        return "FizzBuzz"
    } else if (n % 3 == 0) {
        return "Fizz"
    } else if (n % 5 == 0) {
        return "Buzz"
    }
    return f"{n}"
}

fn range(start: int, end_val: int): stream<int> {
    let i: int:mut = start
    while (i <= end_val) {
        yield i
        i++
    }
}

fn main() {
    for (i: int in range(1, 20)) {
        println(fizzbuzz(i))
    }
}
```

```
$ flow run fizzbuzz.flow
1
2
Fizz
4
Buzz
Fizz
7
8
Fizz
Buzz
11
Fizz
13
14
FizzBuzz
16
17
Fizz
19
Buzz
```

This program brings together functions (`fizzbuzz`), streams (`range`),
`for` loops, string interpolation, conditionals, and the modulo operator.
The `range` function here takes two arguments --- a start and end value ---
making it more general than our earlier single-argument version.

The same program rewritten with composition in `main`:

```flow
fn main() {
    for (i: int in range(1, 20)) {
        let label = i -> fizzbuzz
        println(label)
    }
}
```

Composition and regular function calls are interchangeable. `i -> fizzbuzz`
is the same as `fizzbuzz(i)`. Use whichever is clearer. For a single
function call, the regular form is usually simpler. Composition pays off
when you chain three or more functions, or when the pipeline structure makes
the data flow easier to follow.

---

## 1.11 What Goes Wrong

Every chapter in this book ends with a section on common errors. The Flow
compiler catches problems early and reports them clearly. Here are the
mistakes you are most likely to make in your first programs, and what the
compiler tells you.

**Forgetting the module declaration:**

```flow
import io (println)
fn main() { println("hi") }
```

The compiler issues a warning that the file has no module declaration.
While this does not prevent compilation for standalone programs, it is
required for any file that other modules will import. Always include it.

**Assigning to an immutable binding:**

```flow
let x = 42
x = 43
```

```
error[TypeError]: cannot assign to immutable binding 'x'
  --> test.flow:3:1
```

The fix: declare `x` with `:mut` if you intend to change it.

**Mixing integer and float arithmetic:**

```flow
let x: int = 42
let y: float = x * 1.5
```

```
error[TypeError]: binary operator '*' requires matching types, got int and float
  --> test.flow:3:20
```

The fix: use `cast<float>(x) * 1.5`.

**Calling a function with wrong argument types:**

```flow
fn double(x: int): int = x * 2
let result = double("hello")
```

The compiler reports a type mismatch: `double` expects `int`, but received
`string`. Flow functions have rigid type signatures --- there is no
implicit coercion between unrelated types.

**Using an imported name without importing it:**

```flow
module test
fn main() {
    println("hello")
}
```

```
error[ResolveError]: undefined name 'println'
  --> test.flow:4:5
```

The fix: add `import io (println)` at the top.

**Forgetting the return type on a function:**

```flow
fn double(x: int) = x * 2
```

Flow requires an explicit return type on every function. Unlike some
languages where the compiler silently infers return types, Flow makes the
contract visible at the declaration site. The fix:

```flow
fn double(x: int): int = x * 2
```

**Using `yield` outside a stream function:**

```flow
fn broken(x: int): int {
    yield x    ; compile error
    return x
}
```

`yield` is only valid in functions that return `stream<T>`. If the return
type is `int`, `yield` makes no sense and the compiler rejects it.

These errors are your allies. They catch mistakes at compile time, before
your program runs. The discipline of reading and understanding compiler
errors is one of the most productive habits you can develop. The compiler
is not complaining --- it is telling you exactly what went wrong and where.

---

## 1.12 Summary

This chapter covered the ground-level mechanics of Flow:

- **Modules and imports.** Every file declares a module. Imports bring
  standard library and project functions into scope.
- **`fn main()`** is the entry point of every executable program.
- **`flow run`, `flow build`, `flow check`, `flow emit-c`** are the four
  compiler commands.
- **Comments** use `;` (semicolon), not `//`.
- **`let` bindings** are immutable by default. `:mut` opts into mutability.
- **Type inference** works for local variables; explicit annotations are
  always available.
- **`cast<T>`** performs explicit numeric conversions.
- **String interpolation** with `f"..."` embeds expressions in strings.
- **`while` and `for`** are the loop constructs. `break` and `continue`
  control iteration.
- **Functions** use `fn` with mandatory parameter types and return type.
  Expression form (`= expr`) is available for single-expression bodies.
- **Streams** are lazy sequences produced by `yield` and consumed by `for`.
- **Composition** with `->` chains values and functions left to right.
- **`option<T>`** and `??` handle values that might be absent.

Chapter 2 goes deeper into types: integers of various widths, floats,
booleans, bytes, strings, and the rules that govern conversions between
them. Chapter 3 introduces function purity and the guarantees that pure
functions provide. Chapter 4 returns to composition and develops it into
a full pipeline model with fan-out and parallel execution.

---

## Exercises

**1.** Modify the temperature table from Section 1.3 to convert from
Fahrenheit to Celsius. Print Fahrenheit values from 32 to 212 in steps
of 20. The formula is: C = (F - 32.0) * 5.0 / 9.0. Remember to use
`cast<float>` for the integer-to-float conversion.

**2.** Write a program that prints the first 20 Fibonacci numbers, one per
line. The Fibonacci sequence starts with 0, 1, and each subsequent number
is the sum of the two preceding ones: 0, 1, 1, 2, 3, 5, 8, 13, ...

Use a `while` loop with two mutable variables `a` and `b`. Print `a` on
each iteration, then update: `let next = a + b`, `a = b`, `b = next`.

**3.** Write a function `fn is_palindrome(s: string): bool` that checks
whether a string reads the same forward and backward. Use the `string`
module's `len` and `char_at` functions. `char_at(s, i)` returns `char?`,
so you will need `??` to handle the `none` case.

**4.** Rewrite the Fibonacci program from Exercise 2 as a stream. Write a
function `fn fibs(max: int): stream<int>` that yields Fibonacci numbers
up to (and including) `max`. In `main`, consume the stream with a `for`
loop and print each value.

**5.** Write a function `fn sum_stream(s: stream<int>): int` that consumes
a stream and returns the sum of its values. Then write a `range` function
that yields integers from 1 through n. Use composition to compute the sum
of the first 100 integers: `100 -> range -> sum_stream`. The result should
be 5050.

**6.** Write a program that reads lines from standard input until the user
enters an empty line, then prints the number of lines entered. You will
need `read_line` from `io`, a `while (true)` loop, a `break`, and a
mutable counter.

**7.** Write a function `fn power(base: int, exp: int): int` that computes
`base` raised to the `exp` power using a `while` loop (not recursion).
Test it by printing `power(2, 10)` --- the result should be 1024.

**8.** Combine streams and composition: write a function
`fn evens(n: int): stream<int>` that yields even numbers from 0 to n, and
a function `fn sum_stream(s: stream<int>): int`. Compute
`20 -> evens -> sum_stream` and print the result. Verify it is 110
(0 + 2 + 4 + ... + 20).
