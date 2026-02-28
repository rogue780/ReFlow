# Self-Hosted Compiler Bootstrap Plan

This document captures everything needed to rewrite the Flow compiler in Flow,
based on analysis of the current Python compiler and Flow's language capabilities.

---

## Language Readiness Assessment

### What Flow Has (Ready)

| Capability | Used For | Status |
|-----------|----------|--------|
| Recursive sum types | AST node definitions | Tested (`recursive_expr.flow`) |
| Pattern matching on sum types | AST dispatch in every pass | Fully working |
| Generics (`array<T>`, `map<string, V>`) | Token lists, symbol tables, AST children | Working |
| String/char processing | Lexer (char_at, is_digit, is_alpha, substring, index_of, split) | Complete |
| StringBuilder | Emitter (efficient code generation) | Complete |
| File I/O | Reading source files, writing output | Complete |
| Subprocess (`sys.run_process`) | Shelling out to clang/LLVM | Working |
| Command-line args (`sys.args`) | Compiler CLI | Working |
| Multi-module imports | Organizing compiler into files | Working |
| Try/catch/throw | Compiler error handling | Working |
| Immutable data sharing | Side-map pattern (AST stays immutable, passes annotate separately) | Supported by ownership model |

### Stdlib Gaps to Fill Before Bootstrap

| Gap | Impact | Solution |
|-----|--------|----------|
| Maps are string-keyed only | Can't key side-maps by AST node identity | Add integer ID to each AST node at parse time; use `map<string, T>` with stringified IDs. Or add `map_int<V>` to stdlib. |
| No `file.exists(path)` | Must try-open to check file existence | Add native function (1 line of C: `stat()` wrapper) |
| No `path.join(a, b)` | Building import paths from module names | Add to path module or implement in pure Flow with string ops |
| No directory listing | Can't discover stdlib modules dynamically | `path.list_dir` exists but verify it works; hard-code stdlib list as fallback |
| `run_process_capture` is limited | Can't get exit code + output together | Add `run_process_full(cmd, args): ProcessResult` returning exit code + stdout + stderr |
| No `string.char_code_at(s, i)` | Lexer needs numeric char values for ranges | Use `char.to_code(string.char_at(s, i))` — works but verbose |

### Non-Blocking Gaps (Work Around Them)

- **No regex**: Lexer doesn't need regex — hand-written character classification works
- **No hash by identity**: Use string-keyed maps with node IDs
- **No variadic functions**: Use arrays for variable-length argument lists
- **No raw pointers**: Not needed — all data structures are value types or ref-counted

---

## Architecture: Python Compiler → Flow Compiler

The pipeline stages map 1:1:

```
Python                          Flow
──────                          ────
compiler/lexer.py          →    compiler/lexer.flow
compiler/parser.py         →    compiler/parser.flow
compiler/ast_nodes.py      →    compiler/ast_nodes.flow
compiler/resolver.py       →    compiler/resolver.flow
compiler/typechecker.py    →    compiler/typechecker.flow
compiler/lowering.py       →    compiler/lowering.flow
compiler/emitter.py        →    compiler/emitter.flow
compiler/mangler.py        →    compiler/mangler.flow
compiler/errors.py         →    compiler/errors.flow
compiler/driver.py         →    compiler/driver.flow
```

### Key Design Translations

**AST nodes** — Python dataclasses become Flow sum types:

```flow
type Expr =
    | IntLit(value:int, suffix:string?)
    | FloatLit(value:float, suffix:string?)
    | BoolLit(value:bool)
    | StringLit(value:string)
    | Ident(name:string, module_path:array<string>)
    | BinOp(op:string, left:Expr, right:Expr)
    | UnaryOp(op:string, operand:Expr)
    | Call(callee:Expr, args:array<Expr>)
    | FieldAccess(receiver:Expr, field:string)
    | IfExpr(cond:Expr, then_branch:Block, else_branch:Block?)
    // ... etc
```

Every AST node needs a `node_id:int` field for use as a side-map key.

**Side maps** — Python's `dict[ASTNode, Symbol]` becomes `map<string, Symbol>`
keyed by stringified node ID:

```flow
type ResolvedModule {
    module:Module
    symbols:map<string, Symbol>    // keyed by conv.to_string(node.node_id)
}
```

**Pattern matching** — Python's `match` on node types maps directly to Flow `match`:

```flow
fn lower_expr(expr:Expr):LExpr {
    match expr {
        IntLit(value, suffix): { /* ... */ }
        BinOp(op, left, right): { /* ... */ }
        Call(callee, args): { /* ... */ }
        _: { /* ... */ }
    }
}
```

**Error handling** — Python's `raise TypeError(...)` becomes Flow's `throw`:

```flow
type CompileError {
    message:string
    file:string
    line:int
    col:int
}

fn check_type(expr:Expr, expected:Type):Type {
    // ...
    throw CompileError{
        message:"type mismatch",
        file:ctx.filename,
        line:expr.line,
        col:expr.col
    }
}
```

---

## Stdlib Modules to Rewrite in Pure Flow

These modules are currently 100% native C but can be implemented in pure Flow,
reducing the native surface area and proving the language's capabilities:

| Module | Effort | Notes |
|--------|--------|-------|
| `json` | Medium | Recursive descent parser + serializer. ~200-300 lines of Flow. Replace opaque `JsonValue` C type with a Flow sum type. |
| `path` (partially) | Small | String manipulation (stem, parent, extension, join). Keep `list_dir`, `exists`, `is_dir` as native. |
| `string_builder` (partially) | Small | Could use `array<string>` internally with a `build` that joins. Keep native for performance if needed. |
| `sort` | Small | Implement merge sort or quicksort in Flow. |
| `conv` (partially) | Small | `to_string` dispatching, int/float parsing could be Flow. |

### Modules That Must Stay Native

| Module | Reason |
|--------|--------|
| `file` | System calls (open, read, write, close, stat) |
| `net` | BSD sockets (socket, bind, listen, accept, connect) |
| `io` | stdin/stdout/stderr handles |
| `sys` | Process control (fork, exec, exit, args, env) |
| `time` | Clock syscalls (clock_gettime, time, sleep) |
| `random` | /dev/urandom access for seeding |
| `math` | libm functions (sqrt, pow, log, floor, ceil) |

---

## FFI: Linking External Libraries

### Current Model

```flow
export fn listen(addr:string, port:int):Socket? = native "fl_net_listen"
```

All native functions are implemented in `flow_runtime.c`. No way to link external
C libraries.

### Proposed: `import native` Blocks

```flow
import native "libcurl" {
    fn easy_init():CurlHandle = native "curl_easy_init"
    fn easy_perform(h:CurlHandle):int = native "curl_easy_perform"
    fn easy_cleanup(h:CurlHandle) = native "curl_easy_cleanup"
}
```

Compiler collects `import native "libname"` and passes `-lname` to the linker.
This works for both C backend (`-lcurl` to clang) and LLVM backend (`-lcurl` to
the linker, with `declare` directives in IR).

### Opaque Handle Types

For C libraries, Flow needs opaque types that wrap pointers without exposing
their internals:

```flow
type CurlHandle = native   // opaque, passed by pointer, no field access
```

The compiler treats these as `void*` in generated code. They can be stored,
passed to functions, and compared for equality, but not destructured.

---

## Bootstrap Sequence

### Phase 1: Reduce Native Surface
- Rewrite `json` module in pure Flow (sum type replaces opaque C type)
- Rewrite pure-logic parts of `path`, `conv`, `sort` in Flow
- Add missing stdlib functions (`file.exists`, `path.join`, `run_process_full`)

### Phase 2: Write the Compiler
- Start with `ast_nodes.flow` (sum type definitions)
- Then `errors.flow` (simple struct type)
- Then `mangler.flow` (pure string manipulation)
- Then `lexer.flow` (string + char processing)
- Then `parser.flow` (recursive descent, builds AST)
- Then `resolver.flow` (name binding with side maps)
- Then `typechecker.flow` (type inference + checking)
- Then `lowering.flow` (typed AST → LIR)
- Then `emitter.flow` (LIR → C string via StringBuilder)
- Then `driver.flow` (orchestration + subprocess)
- Finally `main.flow` (CLI argument parsing)

### Phase 3: Bootstrap
1. Build compiler with Python: `python main.py build compiler/main.flow -o flowc`
2. Build compiler with itself: `./flowc build compiler/main.flow -o flowc2`
3. Verify: `diff <(./flowc emit-c compiler/main.flow) <(./flowc2 emit-c compiler/main.flow)`
4. If identical output, bootstrap is complete

### Phase 4: LLVM Backend
- Replace `emitter.flow` (C output) with `emitter_llvm.flow` (LLVM IR output)
- Add LLVM debug metadata for stack traces (replaces shadow stack)
- Use `import native` for linking external libraries
- Archive the Python compiler

---

## Design Decision: Monotonic AST Node IDs

**Problem:** Python uses `object.__hash__` (memory address) for AST nodes as dictionary
keys. Flow doesn't have identity-based hashing. Using `(line, col)` is NOT unique —
nested expressions share source positions.

**Decision:** Every AST node in the self-hosted compiler gets an `id:int` field, assigned
by a monotonic counter during parsing. The counter starts at 1 and increments for each
node created.

**Side-map pattern:**
```flow
// Instead of Python's dict[ASTNode, Symbol]:
type ResolvedModule {
    module:Module
    symbols:map<string, Symbol>    // keyed by conv.to_string(node.id)
}

// Lookup:
let sym = map.get(symbols, conv.to_string(expr.id)) ?? default_symbol
```

**Why this works:**
- Monotonic integers are deterministic and portable (no platform-specific hashing)
- `conv.to_string(id)` is cheap for small integers
- The self-hosted parser is the only place that assigns IDs, so uniqueness is guaranteed
- No compiler changes needed for the Python compiler — it continues using identity hashing

**Validated by:** `tests/programs/app_node_id_test.flow` — prototype demonstrating the
map-keyed-by-int-string pattern works end-to-end.

---

## Verification Checklist

Before starting the self-hosted compiler, confirm these work in Flow:

- [ ] Recursive sum type with 20+ variants (simulates AST)
- [ ] Pattern match on recursive sum type with nested bindings
- [ ] `map<string, V>` with 1000+ entries (simulates symbol table)
- [ ] StringBuilder producing 10000+ line output (simulates emitter)
- [ ] File read + string processing + file write (simulates full pipeline)
- [ ] Multi-module program with 10+ imports (simulates compiler structure)
- [ ] Subprocess execution with exit code check (simulates clang invocation)
- [ ] Error handling with try/catch across module boundaries
