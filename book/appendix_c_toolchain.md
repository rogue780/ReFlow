# Appendix C: The Flow Toolchain

This appendix covers installation, compilation, and project organization.
It is a practical reference; for language semantics, see the preceding
chapters and Appendix A.

---

## C.1 Installing Flow

Flow compiles source to C, then invokes a C compiler to produce a native
binary. You need three things on your system before you start.

**Prerequisites:**

- A C compiler: `clang` (recommended) or `gcc`, supporting C11 or later.
- Python 3.10 or later (for the reference compiler).
- `make` (optional, for running the test suite).

On macOS, `clang` ships with Xcode Command Line Tools. On Linux, install
it through your package manager:

```bash
// Debian / Ubuntu
sudo apt install clang python3 python3-venv

// Fedora
sudo dnf install clang python3

// macOS (Xcode CLT includes clang)
xcode-select --install
```

**Clone the repository:**

```bash
git clone https://github.com/flowlang/flow.git
cd flow
```

**Set up the virtual environment:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows, replace `source .venv/bin/activate` with `.venv\Scripts\activate`.

**Verify the installation:**

```bash
flow --version
```

If this prints a version string, you are ready. If the `flow` command is
not found, make sure the virtual environment is activated and the
repository's `main.py` is on your PATH (or invoke it directly with
`python main.py`).

You can also verify that the C compiler is available:

```bash
clang --version
```

If `clang` is not installed or not on your PATH, `flow build` and
`flow run` will fail at the linking stage. `flow check` and `flow emit-c`
do not require a C compiler.

---

## C.2 Compiling Programs

The `flow` command has four subcommands. Each runs a different slice of
the compiler pipeline.

### `flow build` --- compile to binary

```bash
flow build program.flow
```

This runs the full pipeline: lexing, parsing, name resolution, type
checking, lowering, C emission, and finally invokes `clang` to produce
a native binary. The output file is named after the source file with the
`.flow` extension removed:

```bash
flow build server.flow  // produces ./server
flow build hello.flow  // produces ./hello
```

Use `-o` to specify a different output path:

```bash
flow build server.flow -o bin/myserver
```

Use `--verbose` (or `-v`) to print the generated C to stderr before
compiling. This is useful when debugging codegen issues:

```bash
flow build program.flow -v
```

### `flow run` --- compile and execute

```bash
flow run program.flow
```

This compiles the source to a temporary binary, executes it, and cleans
up. It is the most convenient command during development --- one step from
source to output. Any arguments after the file name are passed through to
the program:

```bash
flow run echo.flow hello world
```

The exit code of `flow run` is the exit code of the compiled program.

### `flow emit-c` --- emit C source only

```bash
flow emit-c program.flow
```

This runs the pipeline through C emission and prints the generated C to
stdout. It does not invoke `clang`. Use `-o` to write to a file instead:

```bash
flow emit-c program.flow -o program.c
```

This is useful for inspecting what the compiler generates, diagnosing type
layout issues, or feeding the C output to a different compiler or build
system. The generated C is not intended to be pretty, but it is readable
and corresponds directly to the Flow source.

### `flow check` --- type-check without compiling

```bash
flow check program.flow
```

This runs the front end --- lexing, parsing, name resolution, and type
checking --- without generating any output. It is the fastest way to
validate a program because it skips C emission and clang entirely.

Silence means success:

```bash
$ flow check program.flow
$
```

`flow check` validates:

- **Lexical correctness** --- no invalid characters or unterminated string
  literals.
- **Parse correctness** --- the source conforms to Flow's grammar.
- **Name resolution** --- every name refers to a defined symbol; no
  undefined variables, no duplicate definitions, no circular imports.
- **Type correctness** --- all expressions have consistent types; function
  arguments match parameter types; return types are honored.
- **Purity constraints** --- pure functions do not call impure ones;
  immutable bindings are not assigned.
- **Exhaustiveness** --- `match` expressions cover all variants of a sum
  type or option.

Use `flow check` for fast feedback loops during editing, for CI pipelines
that only need to verify correctness, and for editor integrations that
report diagnostics.

---

## C.3 Running Programs

After `flow build`, the output is a standalone native binary with no
external dependencies (beyond the system's C standard library and
pthreads). Run it directly:

```bash
./program
```

**Exit codes.** A program that returns normally from `main` exits with
code 0. A runtime panic (division by zero, array index out of bounds,
integer overflow) prints a message to stderr and exits with a non-zero
code. Unhandled exceptions also print to stderr with the exception type,
message, and the location where the exception was thrown:

```
PANIC: IndexOutOfBoundsError at program.flow:12
  index 5 out of bounds for array of length 3
```

The binary links the Flow runtime statically. You can copy it to another
machine with the same OS and architecture and run it without installing
Flow.

**Standard I/O.** Flow programs read from stdin and write to stdout and
stderr using the standard POSIX conventions. Piping and redirection work
as expected:

```bash
echo "input data" | ./program > output.txt
```

**Signals.** A program interrupted with Ctrl-C exits with code 130 (the
standard convention for SIGINT). The runtime does not install custom signal
handlers; the operating system's default behavior applies.

---

## C.4 Checking Types

`flow check` is the lightweight alternative to `flow build`. It runs the
same front-end passes --- the same lexer, parser, resolver, and type
checker --- but stops before lowering and C emission. Because it never
invokes `clang`, it completes in a fraction of the time a full build takes.

Error messages include the file path, line number, and column number:

```
error[TypeError]: binary operator '+' requires matching types, got int and string
  --> math.flow:7:18
```

The format is consistent across all error categories:

| Error kind | Meaning |
|------------|---------|
| `LexError` | Invalid character or unterminated literal |
| `ParseError` | Syntax error |
| `ResolveError` | Undefined name, duplicate definition, import failure |
| `TypeError` | Type mismatch, purity violation, missing return, non-exhaustive match |

Every error points to the exact source location. Editors that parse the
`--> file:line:col` format can jump directly to the problem.

Multiple errors are reported in a single run. The compiler does not stop
at the first error within a single pass --- it collects as many
diagnostics as it can and reports them all. However, errors in an earlier
pass (e.g., a parse error) prevent later passes from running, so you may
see additional errors appear after fixing the first batch.

When working on a large project, `flow check` is the tool to reach for
first. It answers the question "does my program type-check?" without the
overhead of generating and compiling C.

---

## C.5 Project Structure Conventions

A single-file Flow program needs nothing but a `.flow` file with a
`fn main()`. Multi-file projects follow a convention where module names
mirror the directory structure.

```
my_project/
    main.flow  // entry point: module main, fn main()
    config.flow  // module config
    models/
        user.flow  // module models.user
        order.flow  // module models.order
    services/
        auth.flow  // module services.auth
        billing.flow  // module services.billing
    tests/
        test_auth.flow  // test programs (compiled independently)
        test_billing.flow
```

**Module declarations match file paths.** A file at `models/user.flow`
declares `module models.user`. The compiler infers the project root from
the module path and uses it to resolve imports:

```flow
// In services/auth.flow
module services.auth

import models.user (User)
import io (println)

fn authenticate(u: User): bool {
    // ...
}
```

`import models.user (User)` tells the compiler to find `models/user.flow`
relative to the project root, parse it, and make the `User` type
available in the current module.

**One `fn main()` per program.** Only the root module --- the file you pass
to `flow build` or `flow run` --- should define `main`. Imported modules
provide types and functions but do not define entry points.

**Standard library imports are resolved automatically.** When you write
`import io (println)`, the compiler finds the `io` module in its built-in
standard library directory, not on the filesystem relative to your project.
User-defined modules and standard library modules share the same import
syntax but are resolved from different roots.

**Test files are separate programs.** Test files in a `tests/` directory
are compiled and run independently. Each test file has its own
`fn main()` that exercises the module under test. There is no built-in
test runner; you compile and run each test file with `flow run`:

```bash
flow run tests/test_auth.flow
```

A minimal project with a single source file needs no directory structure
at all:

```bash
// Write the program
// hello.flow:
//   module hello
//   import io (println)
//   fn main() { println("Hello!") }

flow run hello.flow
```

As the project grows, split code into modules by domain. The compiler
handles the rest.

**Circular imports are rejected.** If module A imports module B and module
B imports module A, the compiler reports a `ResolveError` with the cycle
path. Flow requires a strict dependency tree --- no cycles. If two modules
need to share types, extract the shared types into a third module that
both import.

**Build artifacts.** `flow build` produces a single binary. There are no
intermediate `.o` files, no build cache, and no incremental compilation.
The compiler generates one C file containing all modules, compiles it in
one invocation of `clang`, and produces one executable. For programs of
moderate size this is fast enough. For very large programs, `flow check`
during development and `flow build` for final output is the recommended
workflow.
