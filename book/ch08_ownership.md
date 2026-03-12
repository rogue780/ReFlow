# Chapter 8: Ownership and Memory

Every language must answer two questions about data: who can use it, and
when is it freed. Most languages answer the first question loosely ---
anyone with a reference can use anything --- and delegate the second to a
garbage collector that runs at unpredictable times. Flow answers both
questions with one mechanism: **linear ownership**. Every value has
exactly one owner at a time. The owner can use it, pass it around, and
eventually let it go. When the last owner lets go, the value is freed
immediately. No garbage collector. No pauses. No surprises.

This chapter covers how ownership works in practice: how values move
between functions, how the compiler borrows automatically when it can, how
to make explicit copies with `@`, how mutability interacts with ownership,
and how reference counting provides deterministic memory management without
cycles. If you have used Rust, some of this will feel familiar, but Flow's
model is deliberately simpler. If you have not, start here --- the ideas
are concrete and the rules are few.

---

## 8.1 Linear Ownership

### 8.1.1 One Owner at a Time

The fundamental rule is: every value has exactly one owner. When you bind a
value to a name, that name owns it. When you pass it to a function, the
function borrows it temporarily. When you return it from a function, ownership
transfers to the caller. At no point do two scopes simultaneously own the
same value.

Here is the simplest demonstration:

```flow
module ownership_demo

import io (println)

fn consume(data: string): none {
    println(f"consumed: {data}")
}

fn main() {
    let msg = "hello"
    consume(msg)
    // msg is still valid here --- consume borrowed it
    println(msg)
}
```

Wait --- if ownership transfers, why can we still use `msg` after calling
`consume`? Because Flow uses **implicit borrowing** by default. When you
pass a value to a function and the function does not store, return, or yield
it, the function borrows the value temporarily. Ownership reverts to the
caller when the function returns. This is the common case, and Flow handles
it without any annotation from you.

The distinction matters when a value **escapes**. A value escapes a function
when it is returned, yielded to a stream, or stored inside a returned value.
When a value escapes, ownership transfers permanently:

```flow
fn take_and_return(data: string): string {
    return data  // data escapes via return
}

fn main() {
    let a = "hello"
    let b = take_and_return(a)
    // a's ownership transferred to take_and_return,
    // which transferred it out via return to b
    println(b)
}
```

The compiler tracks these transfers statically. You do not annotate
ownership. You do not mark borrows. The compiler reads the code and
determines what happens.

### 8.1.2 Type Classification

Not all types have the same ownership behavior. Flow classifies types into
four categories:

**Value types** (`int`, `float`, `bool`, `byte`, `char`) are stack-allocated
scalars. Assignment copies the bits. No memory management is needed. These are
the simplest types.

**Refcounted types** (`string`, `array<T>`, `map<K,V>`, `set<T>`,
`buffer<T>`, `stream<T>`) are heap-allocated containers with a reference
count. Assignment increments the refcount — both bindings share the same
data. When the last reference goes out of scope, the memory is freed.

**Affine types** are structs that contain at least one refcounted or affine
field, and sum types with affine variants. These are the types where
ownership matters most. Assignment is a **move** — the source binding is
consumed and cannot be used afterward. At scope exit, the compiler destroys
the value by releasing each refcounted field.

**Trivial types** are structs with only value-type fields. They are freely
copyable like value types.

The distinction between refcounted and affine is important. Refcounted types
are heap objects with a reference count — multiple bindings can share the
same data safely. Affine types are stack-allocated structs whose fields may
point to heap data. If you could copy an affine struct freely, two copies
would share the same heap pointers, and both would try to free them at scope
exit — a double-free. Move semantics prevent this by ensuring only one
copy exists at a time.

```flow
type Token {
    value: string,   // refcounted field → Token is affine
    line: int,
    col: int
}

let a = Token { value: "hello", line: 1, col: 1 }
let b = a  // MOVE: b owns the token now
// a is consumed — using a here is a compile error
println(b.value)  // "hello"
```

To keep both bindings valid, use `@` (deep copy):

```flow
let a = Token { value: "hello", line: 1, col: 1 }
let b = @a  // DEEP COPY: b gets an independent copy
println(a.value)  // still valid
println(b.value)  // independent copy
```

### 8.1.3 Implicit Borrowing

Most function calls are borrows. The function uses the value, then gives it
back. Flow detects this automatically:

```flow
fn display(data: Record:imut): none {
    println(f"name: {data.name}")
}

fn main() {
    let rec = Record { name: "Alice" }
    display(rec)  // borrowed, not moved
    println(rec.name)  // still valid
    display(rec)  // borrowed again
    println(rec.name)  // still valid
}
```

During `display`'s execution, `rec` is temporarily owned by `display`.
The caller cannot use `rec` while `display` is running --- but since Flow
is single-threaded within a function body, this restriction is invisible.
When `display` returns, ownership reverts, and `rec` is usable again.

Multiple sequential borrows are fine. Each call borrows, uses, and returns.
The pattern is so common that you rarely need to think about it. The cases
where you do need to think are:

1. When a value **escapes** (return, yield, storage in a returned struct).
2. When a value crosses a **thread boundary** (coroutines).
3. When you need an **independent copy** (`@`).

The rest of this chapter covers these three cases.

### 8.1.4 Ownership Escape

A value escapes when it leaves the function that created it. There are
three ways this happens.

**Return.** The most common escape. Ownership moves to the caller:

```flow
fn create(): Record {
    let r = Record { name: "Bob" }
    return r  // r escapes; caller owns it
}

fn main() {
    let rec = create()
    println(rec.name)  // "Bob"
}
```

**Yield.** In a streaming function, `yield` transfers ownership of the
yielded value to the consumer:

```flow
fn names(): stream<string> {
    yield "Alice"  // consumer owns "Alice"
    yield "Bob"  // consumer owns "Bob"
}

fn main() {
    for (name: string in names()) {
        println(name)
    }
}
```

Each `yield` is an ownership transfer. The streaming function no longer owns
the yielded value after the `yield` completes.

**Storage inside a returned value.** If a value is placed inside a struct
or array that is subsequently returned, the inner value escapes too:

```flow
type Pair {
    first: string,
    second: string
}

fn make_pair(): Pair {
    let a = "left"
    let b = "right"
    return Pair { first: a, second: b }
    // both a and b have escaped via the returned struct
}
```

The rule is transitive: if a container escapes, everything inside it
escapes.

**Container insertion.** Placing an affine value into a container (via
`array.push`, `map.set`, etc.) moves the value into the container. The
original binding is consumed:

```flow
let tok = Token { value: "hello", line: 1, col: 1 }
let tokens: array<Token>:mut = []
tokens = array.push(tokens, tok)  // tok moved into array
// tok is consumed — using tok here is a compile error
```

**Container access.** Retrieving an affine value from a container produces a
deep copy (clone). Each refcounted field in the returned value is
independently retained. The container retains its original:

```flow
let first = array.get(tokens, 0) ?? default_token
// first is an independent copy; the array still holds the original
```

**For-loop borrowing.** When iterating over a container of affine elements,
the loop variable borrows each element — no clone, no cleanup per iteration:

```flow
for (tok: Token in tokens) {
    println(tok.value)  // borrowed: efficient, read-only
}
// tokens still owns all elements
```

To take ownership of an element during iteration, use `@`:

```flow
for (tok: Token in tokens) {
    let owned = @tok  // deep copy: owned is independent
    other_list = array.push(other_list, owned)  // move into other_list
}
```

---

## 8.2 Copy and Reference Operators (`@` and `&`)

Sometimes you need two handles to the same data. Flow provides two operators
for this: `@` for independent mutable copies, and `&` for cheap immutable
references.

### 8.2.1 The `@` Operator: Always a Deep Copy

`@` always produces an independent, mutable-capable copy. For value types
(int, float, bool, byte), the value is duplicated on the stack with no heap
allocation. For heap types (string, array), new memory is allocated and the
data is copied in full.

```flow
let a = "hello"
let b = @a  // new allocation; b is an independent copy
println(a)  // "hello"
println(b)  // "hello"
// a and b are independent; modifying one won't affect the other
```

The same applies to arrays:

```flow
let data = [1, 2, 3, 4, 5]
let copy = @data  // full copy: new allocation with same contents
println(data)  // [1, 2, 3, 4, 5]
println(copy)  // [1, 2, 3, 4, 5]
// data and copy are independent
```

Because `@` always produces an independent copy, it is safe to pass the
result to a `:mut` parameter --- the function gets its own copy that it can
modify freely.

### 8.2.2 The `&` Operator: Cheap Immutable Reference

`&` produces a cheap immutable reference --- a refcount increment that
allows the data to be shared without copying. Both the original and the
reference point to the same underlying memory. `&` is valid only on
immutable bindings of refcounted types; applying `&` to a `:mut` binding
or an affine type is a compile error.

`&` is not valid on affine types (structs with refcounted fields). Affine
types are stack-allocated and have no refcount to increment. To share an
affine value, use `@` (deep copy) or pass it directly to a function
(implicit borrow).

```flow
let a = "hello"
let b = &a  // refcount incremented; a and b share the same memory
println(a)  // "hello"
println(b)  // "hello"
// a and b point to the same memory, but neither can mutate it
```

This is safe because the immutable binding guarantees neither `a` nor `b`
can modify the underlying data. No locks are needed. No defensive copying.
The only cost is a single integer increment.

The same applies to arrays:

```flow
let data = [1, 2, 3, 4, 5]
let alias = &data  // cheap: refcount increment, shared data
println(data)  // [1, 2, 3, 4, 5]
println(alias)  // [1, 2, 3, 4, 5]
// both point to the same underlying array
```

When a reference goes out of scope, the reference count is decremented. When
it reaches zero, the memory is freed immediately. This is **deterministic**
--- you know exactly when memory is reclaimed.

Because `&` shares memory rather than copying it, it cannot satisfy a
`:mut` parameter. A function receiving a `:mut` parameter expects to own or
exclusively access the value. Passing a shared reference would violate this
contract.

### 8.2.3 When to Use `@` vs `&`

**Use `@` when:**
- You need an independent copy that can be mutated.
- You're passing to a `:mut` parameter while retaining your original.
- You're crossing a thread boundary with data that may change.
- You want a frozen copy of changing data (e.g., mutable statics).

```flow
fn store_name(name: string): Record {
    return Record { name: name }  // name escapes
}

fn main() {
    let name = "Alice"
    let rec = store_name(@name)  // pass a deep copy; retain original
    println(name)  // still valid
    println(rec.name)  // "Alice"
}
```

**Use `&` when:**
- You want to share immutable data cheaply (e.g., pass to a read-only
  function without consuming ownership).
- You're certain the binding is immutable.
- You do not need the recipient to own an independent copy.

```flow
fn print_label(s: string): none {
    io.println(s)
}

fn main() {
    let title = "Report"
    print_label(&title)  // cheap ref; title still valid after call
    print_label(&title)  // can share multiple times
}
```

Summary:

| Operator | What it produces | Heap cost | Satisfies `:mut`? | Requires immutable? |
|----------|-----------------|-----------|-------------------|---------------------|
| `@expr`  | Independent deep copy | Allocates | Yes | No |
| `&expr`  | Shared ref (refcount++) | None | No | Yes |

---

## 8.3 Mutability Rules

Flow's mutability system is designed around a simple principle: mutation is
allowed, but it is always explicit and always visible. The default is
immutable. You opt into mutability with `:mut`, and the type system tracks
it through every operation.

### 8.3.1 `:mut` and `:imut` Modifiers

There are two mutability modifiers and one default:

**No modifier (bare).** The default. For variable bindings, this means
immutable. For function parameters, it accepts either mutability:

```flow
let x = 42  // immutable
let y: int = 42  // immutable, explicitly annotated
```

**`:mut`.** The binding is mutable. The owning scope can modify it:

```flow
let x: int:mut = 0
x = 42  // ok
x++  // ok
```

**`:imut`.** Explicitly immutable. On a variable, this is identical to the
bare default. On a function parameter, it means the function promises not to
mutate the value:

```flow
let x: int:imut = 5  // same as `let x: int = 5`
```

The `:imut` modifier is most useful on parameters, where it communicates
intent to the reader and allows the compiler to enforce the promise.

Modifier grammar follows a fixed order: type, then `?` (if optional), then
`:mut` or `:imut`. The order is not commutative:

```flow
int  // immutable int
int?  // immutable optional int
int:mut  // mutable int
int?:mut  // mutable optional int
// int:mut?  // compile error --- ? must precede :mut
```

### 8.3.2 Parameter Mutability

Function parameters have three mutability options, and the rules are
intentionally **asymmetric**.

**`:imut` parameters** accept any binding --- mutable or immutable. The
function cannot mutate the parameter. This is the read-only contract:

```flow
fn display(data: array<int>:imut): none {
    // data cannot be modified here
    for (x: int in data) {
        println(f"{x}")
    }
}

let immutable_data = [1, 2, 3]
display(immutable_data)  // ok

let mutable_data: array<int>:mut = [4, 5, 6]
display(mutable_data)  // also ok --- :imut accepts :mut bindings
```

**`:mut` parameters** require the caller to pass a `:mut` binding. The
function will mutate the parameter, and the caller will see the changes
after the function returns:

```flow
fn increment(x: int:mut): none {
    x++
}

let val: int:mut = 5
increment(val)
// val is now 6 --- mutation was visible
```

This is the write contract. Passing an immutable binding to a `:mut`
parameter is a compile error:

```flow
let val = 5  // immutable
// increment(val)  // compile error: immutable binding cannot fulfill :mut
```

The asymmetry is deliberate. Reading is always safe: an `:imut` parameter
can read any data without risk. Writing requires permission: a `:mut`
parameter demands that the caller explicitly opted into mutation. This
prevents accidental mutation of data the caller believed was stable.

**Bare parameters** (no modifier) accept either mutability, with no
guarantee either way:

```flow
fn flexible(data: array<int>): int {
    // data might or might not be mutated
    // caller accepts either possibility
    return data.length
}
```

To prevent a function from mutating your data when you are unsure of its
contract, pass a copy:

```flow
increment(@val)  // @val creates a mutable copy; original is untouched
// val is still 5
```

### 8.3.3 Mutable Data Cannot Cross Thread Boundaries

This is one of Flow's hardest rules, and one of its most valuable. Mutable
data cannot be shared between threads. The compiler enforces this at every
coroutine boundary.

Coroutines in Flow run on separate threads. When you launch a coroutine
with `:<`, the values you pass to it must be safe to share across threads.
Immutable data is always safe --- it cannot change, so concurrent access is
harmless:

```flow
let config = Config { host: "localhost", port: 8080 }  // immutable
let w :< worker(config)  // ok --- immutable data shared via refcount
```

Mutable data is not safe. Two threads mutating the same value is a data
race. Flow does not add locks or synchronization to make this work. Instead,
it rejects the program:

```flow
let data: Data:mut = Data { count: 0 }
// let w :< worker(data)  // compile error: mutable data cannot cross threads
```

To send mutable data to a coroutine, copy it. Each thread gets an
independent value:

```flow
let data: Data:mut = Data { count: 0 }
let w :< worker(@data)  // ok --- deep copy, independent value
```

After the copy, the original `data` and the coroutine's copy are completely
independent. Changes to one are invisible to the other. This is the only
safe option, and Flow makes it explicit.

The same rule applies to fan-out branches and any other parallel execution
boundary. If data is mutable, it cannot be shared. Period.

---

## 8.4 Reference Counting

Flow uses reference counting for all heap-allocated values. There is no
garbage collector. Memory is reclaimed the instant the last reference to a
value disappears. This section explains how the system works and why it
avoids the problems that plague reference counting in other languages.

### 8.4.1 How It Works

Every heap-allocated refcounted value --- strings, arrays, maps, sets,
buffers, streams --- carries a reference count: a small integer that records
how many bindings currently refer to the value. Affine types (structs with
refcounted fields) do not themselves carry a reference count; they use move
semantics instead, and their refcounted fields are released when the struct
is destroyed.

When you create a value:

```flow
let name = "Alice"  // refcount = 1
```

The reference count starts at 1. The binding `name` is the sole owner.

When you create an immutable reference with `&` on immutable data:

```flow
let alias = &name  // refcount = 2
```

The reference count increments to 2. Both `name` and `alias` point to the
same memory. No data was duplicated.

When a binding goes out of scope:

```flow
fn example(): none {
    let name = "Alice"  // refcount = 1
    let alias = &name  // refcount = 2
    // ... use name and alias ...
}  // alias goes out of scope: refcount = 1
    // name goes out of scope: refcount = 0 → memory freed
```

Each scope exit decrements the reference count. When it reaches zero, the
memory is freed immediately. No deferred collection. No stop-the-world
pause. The program's memory usage is predictable and deterministic.

For values passed to functions, the borrow mechanism means the refcount
does not change during a borrow --- the compiler knows ownership will
revert, so no increment is needed. Refcount operations only occur when
references are actually shared (via `&`) or when values are stored in
data structures.

Primitive types --- `int`, `float`, `bool`, `byte` --- are stack-allocated
and copied by value. They have no reference count. When you write `let b =
a` where `a` is an `int`, the integer is copied directly. There is no heap
allocation and no reference counting overhead.

### 8.4.2 Why Cycles Are Impossible

Reference counting has a well-known weakness: cycles. If A references B and
B references A, neither reference count ever reaches zero, and both values
leak. Languages like Python and Swift that use reference counting need
supplementary cycle detection (Python's `gc` module, Swift's `weak`
references) to handle this.

Flow does not have this problem. Cycles are structurally impossible, and the
guarantee comes from two properties of the language:

**Immutable data cannot form cycles.** To create a cycle, A must reference
B and B must reference A. But if both are immutable, B must exist before A
can reference it, and A must exist before B can reference it. Neither can
be modified after creation to add a back-reference. You cannot point to
something that does not yet exist, and you cannot modify something that
already does. No cycle.

**Mutable data has exactly one owner.** Even with mutation, you cannot
create a cycle because you cannot create a second reference to form one.
A mutable value is owned by exactly one binding. You can mutate its
fields, but you cannot make two mutable values point to each other ---
the second assignment would require sharing, which violates single
ownership.

This is a structural guarantee, not a runtime check. There is no cycle
detector running in the background. There is no weak reference mechanism
to learn. The language's ownership rules eliminate cycles as a category
of bug. Reference counting is sufficient because the only patterns that
would break it cannot be expressed in Flow.

### 8.4.3 Atomic Reference Counting for Threads

When immutable data is shared across coroutine boundaries, the reference
count must be thread-safe. Flow uses atomic operations (hardware-level
compare-and-swap) for all refcount increments and decrements on data that
crosses a `:<` boundary. You do not need to know or care about this ---
the compiler selects atomic operations automatically. The cost is a few
extra CPU cycles per refcount operation compared to a non-atomic increment.
For immutable data shared between two coroutines, this is negligible.

### 8.4.4 Deterministic Destruction

Because memory is freed when the reference count hits zero, Flow programs
have deterministic resource lifetimes. This matters for more than memory.
When a struct goes out of scope, its resources are released in a
predictable order:

```flow
fn process_file(): none {
    let conn = open_connection("db://localhost")
    let data = conn.query("SELECT * FROM users")
    // ... work with data ...
}  // data freed, then conn freed --- deterministic, LIFO order
```

In a garbage-collected language, `conn` might not be freed until the next
GC sweep, potentially holding a database connection open longer than
necessary. In Flow, it is freed the instant `process_file` returns. If
your program opens files, sockets, or database connections, deterministic
destruction means you do not need explicit `close()` calls or `try/finally`
blocks to ensure cleanup.

This determinism also makes performance predictable. There are no GC pauses
that spike latency. Memory is reclaimed incrementally as values go out of
scope, not in bulk during a collection cycle. For latency-sensitive
applications --- servers, real-time data processing --- this is a
significant advantage.

### 8.4.5 What the Compiler Generates

You never write retain or release calls yourself --- the compiler inserts
them automatically. Here is what happens behind the scenes:

**Scope-exit release (refcounted).** When a refcounted local (string, array,
map, set, buffer, stream) goes out of scope --- whether at the end of a
function or at the end of an `if`/`while`/`for` block --- the compiler
inserts a release call. This applies to all refcounted locals, whether
`:mut` or default immutable.

**Scope-exit destroy (affine).** When an affine local (struct with
refcounted fields) goes out of scope, the compiler destroys it by releasing
each refcounted field individually. For sum types with affine variants, the
compiler switches on the variant tag and destroys the active variant's
fields. Consumed bindings (moved to another owner) are skipped.

**Owned returns.** Every function return transfers ownership to the caller.
For refcounted types, the returned value has a refcount of at least 1. If
the function returns an existing variable (not a freshly allocated value),
the compiler inserts a retain before the return so the caller gets its own
+1. For affine types, the return is a move --- the callee's binding is
consumed and no retain is needed.

**Struct-construction retain.** When you place a refcounted value into a
struct field, the struct gets its own +1 via an automatic retain. This
ensures the struct's reference is independent of the original binding:

```flow
let name = "Alice"
let user = User(name, 30)
// name has refcount 2: one for the binding, one for the struct field
// when name goes out of scope, refcount drops to 1 --- the struct survives
```

**Affine move.** When an affine value is assigned to a new binding
(`let b = a`), the compiler transfers ownership. No retain is generated
for the struct or its fields --- the new binding inherits the existing
references. The source binding is consumed and skipped at scope exit.

**Container element destruction.** When a container (array, map) holding
affine elements is released, the compiler generates element destructors
that release each element's refcounted fields. This ensures no leaks when
containers of structs go out of scope.

**Release-before-reassign.** When a `:mut` binding is reassigned, the
compiler releases the old value before storing the new one. For refcounted
types, this is a release call. For affine types, this destroys the old
value (releases all its refcounted fields):

```flow
let items:array<string>:mut = ["a", "b"]
items = array.push(items, "c")
// The old ["a", "b"] array is released before items points to ["a", "b", "c"]
```

**In-place `:mut` string append.** When you write `s = s + rhs` on a
`:mut` string, the compiler optimizes this to an in-place buffer extension
when the string has a refcount of 1. This avoids the O(n^2) cost of
repeated concatenation in loops without requiring `string_builder` for
simple cases.

---

## 8.5 Snapshot Values

Ownership handles the common case: local data flowing through functions and
streams. But some data is global --- configuration values stored as static
fields on types. How do you safely read global mutable state from concurrent
code?

Flow's answer is the `@` (copy) operator.

### 8.5.1 The Problem

Static fields can be mutable:

```flow
type Config {
    static host: string:mut = "localhost",
    static port: int:mut = 5432
}
```

Any function can read `Config.port`. But in concurrent code --- coroutines,
fan-out branches --- reading a mutable static is a data race. One thread
might be updating `Config.port` while another is reading it. Flow does not
add implicit locks. Instead, it requires an explicit deep copy using `@`.

### 8.5.2 Reading Mutable Statics with `@`

The `@` operator takes a deep copy of a mutable static field, producing a
local, independent value:

```flow
fn worker(): stream<string> {
    let port = @Config.port  // deep copy of port at this moment
    while (true) {
        yield f"connecting to port {port}"
    }
}
```

The copy is independent of the source. It does not update when the source
changes. It is a value, not a reference.

This is safe for concurrent code because each thread gets its own copy.
No locks. No synchronization. No shared mutable state.

Reading a mutable static without `@` is a compile error:

```flow
fn bad(): int {
    return Config.port  // compile error: mutable static 'port' must be accessed with @ for thread safety
}
```

### 8.5.3 Refreshing Values

To pick up the latest value of a mutable static, simply take a new `@` copy:

```flow
fn processor(batches: stream<array<Record>>): stream<Record> {
    let port:int:mut = @Config.port
    for (batch: array<Record> in batches) {
        for (rec: Record in batch) {
            yield Record { host: @Config.host, port: port, data: rec.data }
        }
        port = @Config.port  // pick up any config changes between batches
    }
}
```

### 8.5.4 Restrictions

**Pure functions cannot access mutable statics.** A pure function must return
the same result for the same arguments. Since mutable statics represent
global state that may change between calls, even a `@` copy would violate
the purity contract:

```flow
pure fn compute(x: int): int {
    // let port = @Config.port  // compile error: pure function cannot access mutable statics
    return x * 2
}
```

If a pure function needs configuration, pass it as a parameter.

---

## 8.6 Ownership and Streams

Streams deserve special mention because ownership behavior changes depending
on whether the stream is consumed directly or launched as a coroutine.

### 8.6.1 Direct Consumption

When a stream function is called and consumed directly (without `:<`), its
parameters are borrowed for the stream's entire lifetime. The stream is a
suspended frame holding its captured variables. Ownership reverts only when
the stream closes, not on each yield:

```flow
fn enumerate(data: array<string>): stream<string> {
    let i: int:mut = 0
    for (item: string in data) {
        yield f"{i}: {item}"
        i++
    }
}

fn main() {
    let names = ["Alice", "Bob", "Carol"]
    for (line: string in enumerate(names)) {
        println(line)
    }
    // names is accessible again here --- stream closed, borrow ended
    println(f"total: {names.length}")
}
```

During the `for` loop, `names` is borrowed by `enumerate`. The loop
iterates lazily: `enumerate` yields one value, `main` prints it,
`enumerate` yields the next. Throughout this, `names` is held by
`enumerate`. Only when the stream is exhausted does the borrow end.

### 8.6.2 Coroutine Launch

When a stream function is launched as a coroutine with `:<`, the rules
change. The coroutine runs on a separate thread, so the ownership rules
for thread boundaries apply:

```flow
fn process(data: array<string>): stream<string> {
    for (item: string in data) {
        yield f"processed: {item}"
    }
}

fn main() {
    let names = ["Alice", "Bob", "Carol"]  // immutable
    let results :< process(names)  // ok: immutable data, refcount shared
    for (line: string in results) {
        println(line)
    }
}
```

Immutable parameters are shared via refcount increment. The spawning scope
and the coroutine both hold a reference to the same data. This is safe
because neither can modify it.

Mutable parameters are **moved** --- the spawning scope loses access:

```flow
fn mutating_worker(data: Config:mut): stream<string> {
    data.retries++
    yield f"retries: {data.retries}"
}

fn main() {
    let cfg: Config:mut = Config { retries: 3 }
    let w :< mutating_worker(cfg)  // cfg is moved to the coroutine
    // cfg is no longer accessible here
    for (line: string in w) {
        println(line)
    }
}
```

If you need to keep access to mutable data while a coroutine uses it, copy:

```flow
let w :< mutating_worker(@cfg)  // deep copy; cfg is still accessible
```

### 8.6.3 Yielded Values

Each `yield` transfers ownership of the yielded value to the consumer.
For value types (`int`, `float`, `bool`, `byte`), this is a trivial copy.
For heap-allocated types, ownership moves through the channel.

If the producer needs to retain a value after yielding it, use `@`:

```flow
fn generate(): stream<string> {
    let template = "item"
    let i: int:mut = 0
    while (i < 3) {
        yield @template  // yield a copy; retain template
        i++
    }
    // template is still accessible here
}
```

Without `@`, the first `yield template` would transfer ownership, and
subsequent iterations could not use `template`.

---

## 8.7 Ownership at a Glance

The following table summarizes what happens to ownership in every common
operation:

| Action | Effect |
|--------|--------|
| `let b = a` (affine) | Ownership moves from `a` to `b`. `a` is consumed. |
| `let b = a` (refcounted) | `a` is retained (ARC). Both `a` and `b` are valid. |
| `let b = @a` | Independent deep copy of `a`. `b` is always independent. `a` is not consumed. |
| `let b = &a` | Immutable refcounted `a` only: refcount increment, shared data. Not valid on affine types. |
| `foo(a)` | `a` is borrowed by `foo`. Reverts to caller when `foo` returns, unless `a` escapes. |
| `foo(@a)` | A mutable deep copy is passed. Caller retains original `a`. Always independent. |
| `foo(&a)` | An immutable ref is passed (refcount++). Refcounted types only. Cannot satisfy `:mut`. |
| `array.push(arr, a)` (affine) | `a` is moved into the array. `a` is consumed. |
| `array.get(arr, i)` (affine) | Returns a deep copy (clone). Array retains its original. |
| `for(x in arr)` (affine) | `x` borrows each element. No clone, no cleanup per iteration. |
| `yield val` | Ownership of `val` transfers to the consumer. Value types are implicitly copied. |
| `yield @val` | A deep copy is yielded. Producer retains ownership of `val`. |
| `return val` | Ownership of `val` transfers to the caller. Function terminates. |
| `let w :< f(a)` | Immutable `a`: shared via refcount. Mutable `a`: moved, caller loses access. |

Keep this table as a reference. Most of the time, you will not need to
consult it --- the compiler enforces every rule and tells you when you
violate one. But when you are designing a data flow and want to understand
the performance characteristics, the table tells you exactly what happens.

---

## 8.8 Putting It All Together

Here is a complete program that exercises every ownership concept from this
chapter: moves, borrows, copies, mutability constraints, and thread
boundaries.

```flow
module ownership_complete

import io (println)

type Sensor {
    name: string,
    readings: array<float>
}

fn summarize(sensor: Sensor:imut): string {
    // :imut parameter --- borrows, does not consume
    let total: float:mut = 0.0
    for (r: float in sensor.readings) {
        total += r
    }
    let avg = total / cast<float>(sensor.readings.length)
    return f"{sensor.name}: avg={avg}"
}

fn process_batch(sensors: array<Sensor>): stream<string> {
    for (s: Sensor in sensors) {
        yield summarize(s)  // summarize borrows s; yield transfers the string
    }
}

fn main() {
    let sensors = [
        Sensor { name: "temp",     readings: [20.1, 21.3, 19.8] },
        Sensor { name: "humidity", readings: [45.0, 47.2, 44.1] },
        Sensor { name: "pressure", readings: [1013.0, 1012.5, 1014.2] }
    ]

    // Direct consumption: sensors is borrowed for the stream's lifetime
    for (line: string in process_batch(sensors)) {
        println(line)
    }

    // sensors is still valid after the stream closes
    println(f"processed {sensors.length} sensors")

    // Explicit ref for cheap immutable sharing
    let backup = &sensors  // cheap refcount increment (immutable data)
    println(f"backup has {backup.length} sensors")
}
```

The data flows cleanly: `sensors` is created in `main`, borrowed by
`process_batch`, which borrows each sensor to `summarize`. Each summary
string is created by `summarize`, returned (ownership to `process_batch`),
then yielded (ownership to `main`'s `for` loop). When the stream closes,
`sensors` reverts to `main`. The `@sensors` copy is a cheap refcount
increment because the data is immutable.

No explicit memory management. No `free` calls. No garbage collector. The
compiler tracked every ownership transfer, inserted refcount operations
where needed, and freed everything deterministically.

---

## 8.9 What Goes Wrong

### Use After Move

The most common ownership error is using a value after it has been moved.
This applies to affine types (structs with refcounted fields) on assignment,
and to all types when escaping a function:

```flow
// Affine move via assignment:
let tok = Token { value: "hello", line: 1, col: 1 }
let other = tok  // tok is consumed (affine move)
// println(tok.value)  // compile error: tok was consumed by move

// Move via function escape:
fn take(data: array<int>): array<int> {
    return data  // data escapes
}

fn main() {
    let nums = [1, 2, 3]
    let taken = take(nums)
    // println(f"{nums.length}")  // compile error: nums was consumed by take
}
```

The fix: either restructure to avoid the move, or use `@` to create a copy:

```flow
let other = @tok  // deep copy; tok is not consumed
let taken = take(@nums)  // pass a copy; nums is retained
println(f"{nums.length}")  // ok
```

### Immutable Binding to `:mut` Parameter

Passing immutable data to a function that expects to mutate it:

```flow
fn increment(x: int:mut): none {
    x++
}

let val = 5
// increment(val)  // compile error: immutable binding cannot fulfill :mut
```

The fix: either make the binding mutable, or pass a mutable copy:

```flow
let val: int:mut = 5
increment(val)  // ok: val is mutable
// val is now 6
```

### Mutable Data Across Threads

Attempting to share mutable data with a coroutine:

```flow
let config: Config:mut = Config { retries: 3 }
// let w :< worker(config)  // compile error: mutable data cannot cross threads
```

The fix: copy the data:

```flow
let w :< worker(@config)  // ok: deep copy
```

### Mutating an `:imut` Parameter

Trying to modify data inside a function that promised not to:

```flow
fn read_only(data: array<int>:imut): none {
    // data = [4, 5, 6]  // compile error: cannot mutate :imut parameter
}
```

The fix: change the parameter to `:mut` if mutation is intended, or
restructure the function to produce a new value instead of mutating:

```flow
fn transform(data: array<int>:imut): array<int> {
    // return a new array instead of mutating
    return array.map(data, \(x: int => x * 2))
}
```

### Double Consumption of a Stream

Streams are single-consumer. Once consumed, they cannot be consumed again.
This interacts with ownership: the first consumer takes ownership, and
there is nothing left for a second:

```flow
let s = generate_data()
let a = process_a(s)
// let b = process_b(s)  // compile error: s already consumed
```

The fix: buffer the stream and copy the buffer, or restructure the code to
process data in a single pass:

```flow
let s = generate_data()
let buf: buffer<Record>:mut = buffer.collect(s)
let a = (@buf).drain() -> process_a
let b = buf.drain() -> process_b
```

### Mutable Static Access in a Pure Function

Attempting to access a mutable static in a function marked `pure`:

```flow
pure fn get_threshold(): int {
    // let t = @Config.threshold  // compile error: pure functions cannot access mutable statics
    return 100
}
```

The fix: either remove the `pure` annotation (if the function genuinely
needs global state) or pass the value as a parameter:

```flow
pure fn apply_threshold(threshold: int, value: int): bool {
    return value > threshold
}
```

This pattern --- passing configuration as parameters instead of reading
globals --- is idiomatic in Flow. It keeps functions pure and testable.

---

## 8.10 Summary

Flow's ownership model rests on a small set of rules:

- **One owner.** Every value has exactly one owner at any time.
- **Four type categories.** Value types (stack-copied), refcounted types
  (shared via ARC), affine types (moved on assignment), trivial structs
  (stack-copied).
- **Affine = move.** Structs with refcounted fields transfer ownership on
  assignment. The source is consumed. Use `@` for independent copies.
- **Implicit borrowing.** Passing a value to a function borrows it
  temporarily. Ownership reverts when the function returns, unless the
  value escapes. This applies to all type categories.
- **Escape transfers ownership.** `return`, `yield`, container insertion,
  and storage inside a returned value permanently transfer ownership.
- **Container insertion = move.** `array.push` and `map.set` move affine
  values in. Container access returns a clone for affine types.
- **For-loop = borrow.** Loop variables borrow container elements.
  Efficient, no clone per iteration.
- **`@` always deep copies.** `@` produces an independent mutable-capable
  copy for all types. Value types are stack copies; heap types allocate;
  affine types clone (retain each refcounted field).
- **`&` shares immutable refs.** `&` increments the refcount and shares
  the same memory. Refcounted types only. Cannot satisfy `:mut`.
- **`:imut` accepts anything.** An `:imut` parameter borrows read-only
  access from any binding.
- **`:mut` requires `:mut`.** A `:mut` parameter requires the caller to
  pass a mutable binding.
- **No mutable sharing across threads.** Mutable data must be copied before
  crossing a coroutine boundary.
- **Reference counting, no cycles.** Immutable data cannot form cycles.
  Mutable data has one owner. No cycle detector needed.
- **`@` for mutable static reads.** Deep copy of mutable statics,
  safe for concurrent code, required by the compiler.

These rules eliminate use-after-free, double-free, data races, and memory
leaks without a garbage collector. The cost is that you occasionally need to
think about where data goes and who owns it. The benefit is that the
compiler catches every mistake at compile time, before your program runs.

Chapter 9 builds on ownership by introducing streams --- typed channels
where ownership transfers happen continuously as values flow from producer
to consumer.

---

## Exercises

**1.** Write a program that demonstrates ownership transfer. Create a
function `fn take_string(s: string): string` that returns its argument.
Call it from `main`, then attempt to use the original binding afterward.
Observe the compile error. Fix it using `@`.

```flow
module ex_ownership

import io (println)

fn take_string(s: string): string {
    return s
}

fn main() {
    let greeting = "hello"
    let taken = take_string(greeting)
    // Try uncommenting the next line to see the compile error:
    // println(greeting)  // error: greeting was consumed
    println(taken)

    // Fix: use @ to retain the original
    let greeting2 = "world"
    let taken2 = take_string(@greeting2)
    println(greeting2)  // ok: greeting2 was copied, not moved
    println(taken2)
}
```

**2.** Write a program that shows the difference between `@` on immutable
and mutable data. Create a struct `Counter` with a mutable `value` field.
Create an immutable version and a mutable version, copy each with `@`, then
modify the mutable original and show that the copy is independent.

```flow
module ex_copy

import io (println)

type ImmutableRecord {
    name: string
}

type MutableRecord {
    name: string,
    count: int:mut
}

fn main() {
    // Immutable copy: cheap refcount increment
    let a = ImmutableRecord { name: "Alice" }
    let b = @a
    println(f"a.name: {a.name}")  // Alice
    println(f"b.name: {b.name}")  // Alice (same underlying data)

    // Mutable copy: deep copy
    let c: MutableRecord:mut = MutableRecord { name: "Bob", count: 0 }
    let d = @c  // deep copy
    c.count = 42
    println(f"c.count: {c.count}")  // 42
    println(f"d.count: {d.count}")  // 0 --- independent copy
}
```

**3.** Write a program with two coroutines that share immutable
configuration data. Define a `Config` struct with `host` and `port` fields.
Create it once in `main`, then launch two coroutines that both read from it.

```flow
module ex_shared_config

import io (println)

type Config {
    host: string,
    port: int
}

fn worker(id: int, cfg: Config): stream<string> {
    let i: int:mut = 0
    while (i < 3) {
        yield f"worker {id}: connecting to {cfg.host}:{cfg.port}"
        i++
    }
}

fn main() {
    let cfg = Config { host: "localhost", port: 8080 }  // immutable

    // Both coroutines share cfg via refcount --- no copy needed
    let w1 :< worker(1, cfg)
    let w2 :< worker(2, cfg)

    for (msg: string in w1) {
        println(msg)
    }
    for (msg: string in w2) {
        println(msg)
    }
}
```

**4.** Build a struct with mixed mutable and immutable fields. Show which
operations the compiler allows and which it rejects.

```flow
module ex_mixed_fields

import io (println)

type UserProfile {
    id: int,  // immutable: set once
    name: string,  // immutable: set once
    score: int:mut,  // mutable: can be updated
    status: string:mut  // mutable: can be updated
}

fn update_score(profile: UserProfile:mut): none {
    profile.score += 10
    profile.status = "active"
}

fn display(profile: UserProfile:imut): none {
    // read-only access to all fields
    println(f"id={profile.id} name={profile.name} score={profile.score} status={profile.status}")
    // profile.score = 0  // compile error: :imut parameter cannot be mutated
}

fn main() {
    let user: UserProfile:mut = UserProfile {
        id: 1,
        name: "Alice",
        score: 0,
        status: "new"
    }

    display(user)  // :imut accepts :mut binding
    update_score(user)  // :mut parameter requires :mut binding
    display(user)  // score and status changed; id and name unchanged

    // user.id = 2  // compile error: id is not :mut
    // user.name = "Bob"  // compile error: name is not :mut
    user.score = 100  // ok: score is :mut
}
```

**5.** Use `@` in a worker coroutine to safely read changing
configuration. Define a type with a mutable static field, launch a worker
that takes a `@` copy, processes several items, then refreshes.

```flow
module ex_copy_static

import io (println)

type AppConfig {
    static threshold: int:mut = 100
}

fn processor(items: array<int>): stream<string> {
    let thresh = @AppConfig.threshold
    for (item: int in items) {
        if (item > thresh) {
            yield f"{item} exceeds threshold {thresh}"
        } else {
            yield f"{item} within threshold {thresh}"
        }
    }
    // thresh = @AppConfig.threshold would pull the latest value here
}

fn main() {
    let data = [50, 150, 75, 200, 90]
    for (msg: string in processor(data)) {
        println(msg)
    }
}
```
