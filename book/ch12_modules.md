# Chapter 12: Modules and Programs

Every program in this book so far has been a single file. That works for
exercises and demonstrations. It does not work for programs that do anything
real. A web server, a compiler, a data pipeline --- these have too many
concerns for one file to hold. You need a way to split a program into pieces,
give each piece a name, control what is visible from outside, and connect the
pieces together.

Flow's module system is that mechanism. It is simple: every file declares a
module, modules export what they want to be public, and other modules import
what they need. There are no packages, no namespaces nested inside files, no
access modifiers beyond public and private. One file, one module, one
declaration.

This chapter covers how modules work, how imports bring names into scope, how
exports control visibility, how the compiler handles shared state across
modules, what happens when imports form a cycle, and how to organize a
multi-file project.

---

## 12.1 Module Declaration

Every `.flow` file begins with a module declaration:

```flow
module math.vector
```

This line does three things. It names the module. It establishes the namespace
that other files use when they import it. And it tells the compiler where to
find the file on disk: `math.vector` corresponds to `math/vector.flow`,
relative to the project root.

The module name and the file path must agree. If you put `module math.vector`
in a file at `utils/geometry.flow`, the compiler will reject it. The module
name is not an arbitrary label --- it is a contract between the file and the
project layout.

Here is a complete module:

```flow
module math.vector

export type Vec3 { x: float, y: float, z: float }

export fn dot(a: Vec3, b: Vec3): float =
    a.x * b.x + a.y * b.y + a.z * b.z

export fn scale(v: Vec3, s: float): Vec3 =
    Vec3 { x: v.x * s, y: v.y * s, z: v.z * s }

fn length_squared(v: Vec3): float =
    dot(v, v)
```

Four declarations. Three are exported, one is not. The exported names ---
`Vec3`, `dot`, `scale` --- are visible to any module that imports
`math.vector`. The private function `length_squared` is an implementation
detail. It can be called from within `math.vector` but not from outside.

### What Happens Without a Declaration

If you omit the `module` line, the compiler issues a warning. The file
compiles, but it cannot be imported by any other file. This is acceptable for
a top-level `main.flow` that serves as the program entry point and does not
need to be imported. It is not acceptable for any file that other files depend
on.

The rule is straightforward: if the file will ever be imported, give it a
module declaration. If not, you can omit it, but the warning will remind you
that you have chosen to make the file unreachable from the rest of the project.

---

## 12.2 Imports

Imports bring names from other modules into the current file. Flow provides
three forms, each suited to a different situation.

### 12.2.1 Namespace Import

```flow
import math.vector
```

This imports all exported names from `math.vector` and places them under the
namespace `vector` --- the last component of the import path. You access them
with a dot:

```flow
import math.vector

fn main() {
    let v = vector.Vec3 { x: 1.0, y: 2.0, z: 3.0 }
    let w = vector.Vec3 { x: 4.0, y: 5.0, z: 6.0 }
    let d = vector.dot(v, w)
    println(f"dot product: {d}")
}
```

The namespace is always the last component. `import graphics.rendering.shader`
makes exports available as `shader.compile`, `shader.Link`, and so on. You do
not write `graphics.rendering.shader.compile` --- that would defeat the
purpose.

Namespace imports are the safest default. They keep the origin of each name
visible at the call site. When you read `vector.dot(v, w)`, you know `dot`
comes from the `vector` module without checking the import list.

### 12.2.2 Selective Import

```flow
import math.vector (Vec3, dot, scale)
```

This brings `Vec3`, `dot`, and `scale` directly into scope. No namespace
prefix, no dot:

```flow
import math.vector (Vec3, dot, scale)

fn main() {
    let v = Vec3 { x: 1.0, y: 2.0, z: 3.0 }
    let w = Vec3 { x: 4.0, y: 5.0, z: 6.0 }
    let d = dot(v, w)
    println(f"dot product: {d}")
}
```

Selective imports are explicit about what you use. If the module exports
twenty functions and you need two, the import line communicates that clearly.
They also prevent name collisions: you choose which names to bring in, and
names you do not import cannot clash with your local definitions.

The tradeoff is that the call site loses context. When you write `dot(v, w)`,
nothing at the call site tells you which module `dot` came from. For common
names like `dot`, `length`, or `count`, this can matter. For distinctive names
like `Vec3`, it matters less.

Use selective imports when the names are distinctive enough that their origin
is obvious, or when you use them so frequently that the namespace prefix would
be noise.

### 12.2.3 Alias Import

```flow
import math.vector as vec
```

This works like a namespace import, but with a name you choose instead of the
last path component:

```flow
import math.vector as vec

fn main() {
    let v = vec.Vec3 { x: 1.0, y: 2.0, z: 3.0 }
    let scaled = vec.scale(v, 2.0)
    println(f"scaled x: {scaled.x}")
}
```

Aliases serve two purposes. First, they shorten long namespace names.
`import data.processing.transforms as xform` is more comfortable to type than
`transforms.normalize` repeated thirty times in a file. Second, they resolve
ambiguity when two modules share the same last component:

```flow
import graphics.shader as gshader
import compute.shader as cshader

fn main() {
    let gs = gshader.compile("vertex.glsl")
    let cs = cshader.compile("reduce.cl")
}
```

Without aliases, both would try to use the namespace `shader`, which would be
a collision. The alias gives each a distinct prefix.

### Mixing Import Styles

You can use different import styles for different modules in the same file.
Each import statement is independent:

```flow
import math.vector (Vec3, dot)     ; selective: use these constantly
import math.matrix as mat          ; alias: use occasionally, keep prefix
import io                          ; namespace: use io.println, io.read_line
```

There is no restriction on combining styles. Choose whichever form makes the
code clearest at each call site.

### 12.2.4 Import Resolution

Imports are resolved by relative path from the project root. The compiler
takes the import path, replaces dots with directory separators, appends
`.flow`, and looks for the file. `import math.vector` resolves to
`math/vector.flow`. `import taskman.services.auth` resolves to
`taskman/services/auth.flow`.

The standard library modules --- `io`, `math`, `string`, `conv`, `array`,
`map`, `net`, `time`, `json` --- are resolved from the compiler's built-in
library path, not the project root. You do not need to create an `io.flow`
file in your project; `import io` finds the standard library automatically.

If the file does not exist, the compiler reports it:

```
error: module not found: 'math.vector'
  --> main.flow:2:1
  note: expected file at 'math/vector.flow'
```

This error is one of the most common when starting a multi-file project. The
fix is almost always one of: the file does not exist yet, the file exists but
at a different path, or the module declaration inside the file does not match
the import path.

---

## 12.3 Exports and Visibility

By default, every declaration in a module is private. The `export` keyword
makes a declaration visible to importers. Without it, the name exists only
within the file.

```flow
module auth

import crypto (hash_password, verify_password)

; Public: other modules can call this
export fn authenticate(user: string, password: string): bool {
    let stored = lookup_hash(user)
    return verify_password(password, stored)
}

; Public: other modules can use this type
export type Credentials {
    username: string,
    token: string
}

; Private: only this module can call this
fn lookup_hash(user: string): string {
    ; implementation detail: read from database
    return "stored_hash_placeholder"
}

; Private: internal constant
let MAX_ATTEMPTS: int = 5
```

The rules:

- `export fn` makes a function importable.
- `export type` makes a type importable, including its constructors and fields.
- `fn` without `export` is module-private.
- `type` without `export` is module-private.

There is no `protected`, no `internal`, no fine-grained access control. A
declaration is either public or private. This is a deliberate simplification.
The module boundary is the only visibility boundary. If you need finer
separation, split the module.

### What Gets Exported With a Type

When you export a type, its fields and any associated functions that are also
marked `export` become visible. The type name alone is not useful without the
ability to construct values and access fields:

```flow
module shapes

export type Circle {
    radius: float
}

export fn area(c: Circle): float = 3.14159 * c.radius * c.radius

fn internal_helper(c: Circle): float = c.radius * 2.0
```

An importer can use `Circle`, construct `Circle { radius: 5.0 }`, access
`.radius`, and call `area`. They cannot call `internal_helper`.

### The Error You Will See

If you try to use a name that exists in a module but is not exported, the
compiler tells you:

```
error: 'lookup_hash' is not exported from module 'auth'
  --> server.flow:7:5
```

This is not the same as "name not found." The compiler knows the name exists;
it is telling you the author of that module chose not to make it public. The
fix is either to export it (if you control the module) or to find a different
approach (if you do not).

---

## 12.4 Module Instantiation and Shared State

A module is instantiated exactly once, regardless of how many other modules
import it. If `server.flow` imports `config` and `admin.flow` also imports
`config`, there is one instance of `config`. Both modules see the same
values.

For immutable data, this is unremarkable. A constant is a constant. For
mutable statics, it matters:

```flow
; config.flow
module config

export type DB {
    static host: string:mut = "localhost",
    static port: int:mut = 5432
}
```

```flow
; server.flow
module server

import config (DB)

fn connect(): string {
    return f"connecting to {DB.host}:{DB.port}"
}
```

```flow
; admin.flow
module admin

import config (DB)

fn override_host(h: string) {
    DB.host = h
}
```

When `admin.override_host("production.db.example.com")` runs, `DB.host`
changes. The next call to `server.connect` sees the new value. There is no
copy --- both modules refer to the same static field on the same type instance.

This is shared mutable state. Flow does not hide it behind a service locator
or dependency injection framework. The sharing is explicit: both modules
import `config`, both use `DB.host`, and the type's `:mut` annotation makes
the mutability visible. But explicit does not mean safe. If two coroutines
running on separate threads both access `DB.host`, you have a data race. Treat
mutable statics with the same discipline you would apply to any shared mutable
state in a concurrent system.

For configuration that is set once at startup and read many times afterward,
mutable statics work well. For state that changes frequently or is accessed
from multiple threads, consider passing values explicitly through function
parameters or using streams for coordination.

### Why Single Instantiation Matters

If modules were instantiated per-importer, each would get its own copy of the
static fields. Changing `DB.host` in `admin.flow` would have no effect on
`server.flow`. This is how some languages handle module imports (notably,
creating new instances on each require). Flow chose the opposite: one instance,
shared state. The tradeoff is simplicity versus safety. One instance means you
do not have to think about which copy you are modifying. But it also means
changes propagate everywhere, which can be surprising if you did not realize
the state was shared.

The practical advice: keep mutable statics to a minimum. Use them for
configuration, feature flags, and process-wide state that is genuinely
global. For anything else, pass values through function parameters. The extra
typing is worth the clarity.

---

## 12.5 Circular Import Detection

Circular imports are a compile error. If `a.flow` imports `b` and `b.flow`
imports `a`, the compiler rejects both files and reports the cycle:

```
error: circular import detected: a -> b -> a
```

The compiler traces the full chain. For longer cycles, you see the full path:

```
error: circular import detected: orders -> inventory -> pricing -> orders
```

Cycles do not happen by accident in small projects. They appear when two
modules evolve independently and gradually accumulate cross-dependencies. The
typical pattern: module A defines a type that module B needs, and module B
defines a function that module A needs.

The solution is always the same: extract the shared dependency into a third
module.

### Before: Circular

```flow
; orders.flow
module orders
import inventory (check_stock)

export type Order { item: string, quantity: int }

export fn place(o: Order): bool {
    return check_stock(o.item, o.quantity)
}
```

```flow
; inventory.flow
module inventory
import orders (Order)         ; circular: orders already imports inventory

export fn check_stock(item: string, qty: int): bool {
    ; ...
    return true
}

export fn pending_orders(): array<Order> {
    ; needs the Order type
    return []
}
```

### After: Extracted

```flow
; types.flow
module types

export type Order { item: string, quantity: int }
```

```flow
; orders.flow
module orders
import types (Order)
import inventory (check_stock)

export fn place(o: Order): bool {
    return check_stock(o.item, o.quantity)
}
```

```flow
; inventory.flow
module inventory
import types (Order)

export fn check_stock(item: string, qty: int): bool {
    return true
}

export fn pending_orders(): array<Order> {
    return []
}
```

The `Order` type now lives in `types.flow`. Both `orders` and `inventory`
import it from there. The cycle is broken. The general principle: shared types
go in their own module, and modules that operate on those types import them
from a common source.

### Recognizing Cycles Early

Cycles are easier to prevent than to fix. A few habits help:

- Before adding an import, check whether the target module already imports
  (directly or transitively) from the current module. If it does, the new
  import will create a cycle.
- Keep types in dedicated modules that import nothing. A type module that
  has no imports can never be part of a cycle.
- When two modules need to call each other's functions, it is usually a sign
  that they should be one module, or that a third module should mediate
  between them.

The compiler catches cycles at compile time, not at runtime, so you will
never ship a program with a circular dependency. But the error message
appears only after you have written the code. Thinking about the dependency
graph before writing the import statement saves time.

---

## 12.6 Scoping Rules

Flow's scoping rules determine what names are visible inside a function. They
are strict, and understanding them prevents a class of bugs that plague
languages with more permissive scoping.

### 12.6.1 What Functions Can Access

A function body can refer to exactly these categories of names:

**Parameters.** The function's own parameters are in scope throughout the body:

```flow
fn greet(name: string): string {
    return f"Hello, {name}!"
}
```

**Local variables.** Variables declared with `let` inside the function body:

```flow
fn area(radius: float): float {
    let pi = 3.14159
    return pi * radius * radius
}
```

**Imported names.** Functions and types brought into scope by `import`
statements at the top of the file:

```flow
import math (sqrt)

fn distance(x: float, y: float): float {
    return sqrt(x * x + y * y)
}
```

**Static type members.** Fields and methods accessed through the type name:

```flow
import config (DB)

fn connection_string(): string {
    return f"{DB.host}:{DB.port}"
}
```

That is the complete list. Notably absent:

**No global variables.** Flow has no file-level `let` bindings that functions
can read. There is no equivalent of Python's module-level variables or C's
file-scope globals. If a function needs a value, it comes through a parameter,
an import, or a static member.

**No enclosing function scope.** A nested function (if one existed) cannot
reach into its parent function's variables. Functions are not closures over
their enclosing scope.

**Lambdas are the exception.** A lambda can capture anything in the scope
where it is defined, including the enclosing function's parameters and locals.
This was covered in Chapter 4. The distinction matters: named functions
(`fn`) cannot capture surrounding locals; lambdas (`\(...)`) can.

### 12.6.2 Shadowing

Inner scopes can shadow outer names. The outer name becomes inaccessible
within the inner scope, and no warning is emitted:

```flow
fn example() {
    let x = 10
    println(f"{x}")        ; 10

    if (true) {
        let x = 20         ; shadows outer x
        println(f"{x}")    ; 20
    }

    println(f"{x}")        ; 10 again: inner x is out of scope
}
```

Shadowing works everywhere: inside `if` blocks, `for` loops, `match` arms,
and nested blocks. The shadowed name is not destroyed --- it simply cannot be
reached until the inner scope ends.

Parameters shadow imported names:

```flow
import math (sqrt)

fn sqrt(x: int): int {
    ; this function shadows the imported sqrt
    ; within this file, sqrt refers to this function
    return x
}
```

This is legal but inadvisable. The compiler does not warn, because shadowing
is sometimes intentional. But shadowing an imported name silently changes the
meaning of every call site in the file that uses that name. If you find
yourself doing this, rename the function.

Shadowing across nested scopes is more common and less dangerous:

```flow
fn process(items: array<string>) {
    for (item: string in items) {
        let item = f"processed: {item}"   ; shadows loop variable
        println(item)
    }
}
```

The `let item` inside the loop body shadows the `item` bound by the `for`
loop. This is a reasonable pattern when you want to transform a value and
continue using the same name. But if it makes the code harder to follow, use
a different name.

### 12.6.3 No Parent Accessor

There is no syntax to reach a shadowed name. Once `x` is shadowed, the outer
`x` is gone until the inner scope ends. Other languages have `this.x`,
`super.x`, or `outer.x`. Flow does not. If you need both values, use
different names.

---

## 12.7 Organizing a Multi-Module Program

A realistic project has many modules. Here is a structure for a task
management application:

```
taskman/
    main.flow                   ; module taskman.main
    config.flow                 ; module taskman.config
    models/
        task.flow               ; module taskman.models.task
        user.flow               ; module taskman.models.user
    storage/
        memory.flow             ; module taskman.storage.memory
    services/
        tasks.flow              ; module taskman.services.tasks
        auth.flow               ; module taskman.services.auth
```

Each directory maps to a segment of the module path. Each file declares its
full module name. Let us walk through the code.

### The Models

Types live in their own modules, free of logic:

```flow
; models/task.flow
module taskman.models.task

export type Priority = Low | Medium | High

export type Task {
    id: int,
    title: string,
    done: bool,
    priority: Priority
}
```

```flow
; models/user.flow
module taskman.models.user

export type User {
    id: int,
    name: string,
    email: string
}
```

These modules export only types. They import nothing. This is a common
pattern: pure data definitions at the bottom of the dependency graph, with no
imports of their own, so they can never be part of a cycle.

### Configuration

```flow
; config.flow
module taskman.config

export type App {
    static max_tasks: int = 100,
    static app_name: string = "TaskMan"
}
```

Static fields on an exported type provide named, typed configuration that
any module can import and read. Because `max_tasks` is not `:mut`, it cannot
be changed after initialization.

### Storage

```flow
; storage/memory.flow
module taskman.storage.memory

import taskman.models.task (Task)

export fn store(t: Task): bool {
    ; persist the task
    return true
}

export fn find_by_id(id: int): Task? {
    ; look up a task, return none if not found
    return none
}
```

The storage module imports the `Task` type from the models layer. It does not
import services or the main module. Dependencies point downward: services
depend on storage, storage depends on models. Never the reverse.

### Services

```flow
; services/tasks.flow
module taskman.services.tasks

import taskman.models.task (Task, Priority)
import taskman.storage.memory as store
import taskman.config (App)

export fn create_task(title: string, priority: Priority): Task? {
    let t = Task {
        id: next_id(),
        title: title,
        done: false,
        priority: priority
    }
    let ok = store.store(t)
    if (ok) {
        return some(t)
    }
    return none
}

fn next_id(): int {
    ; private helper: generate unique IDs
    return 1
}
```

The service module imports from both models and storage. `next_id` is private
--- callers of the service do not need to know how IDs are generated.

### The Entry Point

```flow
; main.flow
module taskman.main

import io (println)
import taskman.models.task (Task, Priority)
import taskman.services.tasks as tasks

fn main() {
    let t = tasks.create_task("Write chapter 12", Priority.High)
    match (t) {
        some(task) => println(f"Created: {task.title}"),
        none => println("Failed to create task")
    }
}
```

The main module sits at the top of the dependency graph. It imports services,
which import storage and models. The dependency arrows all point in one
direction. There are no cycles.

### The Dependency Graph

```
main
  └── services.tasks
  │     ├── models.task
  │     ├── storage.memory
  │     │     └── models.task
  │     └── config
  └── models.task
```

Every arrow points downward. Models depend on nothing. Storage depends on
models. Services depend on models, storage, and config. Main depends on
services and models. This is the standard pattern for well-organized
Flow projects.

When the graph gets complicated, apply these guidelines:

1. **Types at the bottom.** Pure data types should have no imports. They are
   the leaves of the dependency tree.

2. **One direction.** Dependencies flow from high-level modules (entry points,
   services) to low-level modules (types, utilities). If you find a low-level
   module importing a high-level one, extract the shared dependency.

3. **Small modules.** A module with fifty exported functions is hard to use and
   hard to maintain. Split it. A module with three to ten exports is typical.

4. **Descriptive paths.** `taskman.models.task` is better than `taskman.task`
   or `types`. The path should tell the reader what category of code the
   module contains, not just what it is about.

### Common Mistakes

**Importing but not exporting.** You write a useful function, import the
module elsewhere, and get an error saying the name is not exported. The
function exists, but you forgot `export`. This is the most common module error
in new projects.

**Module name does not match file path.** You move a file to a new directory
but forget to update the `module` declaration. The compiler rejects the
import because the file path and the declared name disagree.

**Importing a name that does not exist.** You write
`import math.vector (Vec3, cross)` but the module only exports `Vec3`, `dot`,
and `scale`. The compiler tells you `cross` is not found in `math.vector`.
Check the module's exports.

**Namespace collision with bare imports.** Two bare imports that share a last
path component (`import graphics.shader` and `import compute.shader`) collide
on the namespace `shader`. Use alias imports to distinguish them.

**Accidentally shadowing an import.** You define a local function named `len`
in a module that imports `string (len)`. Every call to `len` in the file now
refers to your local function, not the standard library one. The compiler does
not warn. If the types happen to match, the program compiles and silently does
the wrong thing.

---

## 12.8 Summary

Flow's module system is minimal by design. There is one mechanism for
organizing code (modules), one for controlling visibility (export), and three
ways to bring names into scope (namespace, selective, alias imports). There
are no nested namespaces within files, no re-exports, no conditional imports.

The key rules:

- Every file declares `module <name>` at the top. The name matches the file
  path.
- Only `export`-marked declarations are visible to importers. Everything else
  is private.
- Namespace import (`import a.b`) uses the last path component as the prefix.
  Selective import (`import a.b (X, Y)`) brings names directly into scope.
  Alias import (`import a.b as c`) lets you choose the prefix.
- A module is instantiated once. All importers share the same static values.
  Mutable statics are shared state.
- Circular imports are a compile error. The fix is always to extract shared
  types into a separate module.
- Functions can access parameters, locals, imports, and static type members.
  They cannot access enclosing function scopes (lambdas can). There are no
  global variables.
- Shadowing is silent and total within the inner scope. There is no syntax to
  reach a shadowed name.

The module system does not try to enforce architectural patterns. It gives you
a flat namespace of modules, a binary visibility switch, and a rule against
cycles. The rest --- dependency direction, layer separation, interface
boundaries --- is up to you. The tooling keeps you honest about cycles. The
discipline of keeping dependencies pointing one direction is yours to
maintain.

---

## Exercises

**1.** Take the following single-file program and split it into three modules:
one for the type, one for the logic, and one for `main`. Each module should
be in its own file. The logic module imports the type module, and main imports
both.

```flow
module monolith

import io (println)

type Rect { width: float, height: float }

fn area(r: Rect): float = r.width * r.height

fn perimeter(r: Rect): float = 2.0 * (r.width + r.height)

fn main() {
    let r = Rect { width: 5.0, height: 3.0 }
    println(f"area: {area(r)}")
    println(f"perimeter: {perimeter(r)}")
}
```

Your three files should be:
- `shapes/rect.flow` (module `shapes.rect`, exports `Rect`)
- `shapes/calc.flow` (module `shapes.calc`, exports `area` and `perimeter`)
- `main.flow` (imports from both)

**2.** Create a module `counter.flow` that exports an `increment` function and
a `get_count` function, but keeps the actual count as a private static member.
Write a `main.flow` that calls `increment` three times and prints the result
of `get_count`. Verify that the count is 3.

```flow
; counter.flow
module counter

export type State {
    static value: int:mut = 0
}

export fn increment() {
    State.value = State.value + 1
}

export fn get_count(): int {
    return State.value
}
```

```flow
; main.flow
module main

import io (println)
import counter (increment, get_count)

fn main() {
    increment()
    increment()
    increment()
    println(f"count: {get_count()}")
}
```

**3.** Write two modules, `format.flow` and `report.flow`, that both import
the same `config` module. The config module has a mutable static `separator`
field (default `", "`). Write `main.flow` that changes the separator to
`" | "` and then calls functions from both modules to verify they both see the
new value.

**4.** Design a module structure for a TODO application with the following
requirements:
- A `Todo` type with `id`, `title`, `done` fields
- An in-memory store that can add, complete, and list todos
- A command-line interface that reads user input and dispatches to the store

Draw the dependency graph first, then write the module declarations and import
statements for each file. You do not need to implement the function bodies ---
the structure is the exercise.

**5.** The following two modules have a circular import. Identify the cycle and
refactor the code to eliminate it. All existing functionality must be
preserved.

```flow
; users.flow
module users
import permissions (Role)

export type User { name: string, role: Role }

export fn create(name: string): User {
    return User { name: name, role: Role.Viewer }
}
```

```flow
; permissions.flow
module permissions
import users (User)

export type Role = Admin | Editor | Viewer

export fn can_edit(u: User): bool {
    match (u.role) {
        Admin => return true,
        Editor => return true,
        Viewer => return false
    }
}
```

The cycle is `users -> permissions -> users`. Extract the shared types into a
`types.flow` module so that both `users` and `permissions` import from
`types` instead of from each other.
