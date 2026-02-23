# ReFlow Bootstrap: Self-Hosted Compiler Plan

## Overview

This document is the complete task-level plan for rewriting the ReFlow compiler in ReFlow and bootstrapping it. The Python compiler (Epics 0–10 of `reflow_compiler_plan.md`) is the reference implementation. This plan takes it from reference to self-hosted.

The bootstrap proceeds in three phases:

1. **Extend the standard library** — the compiler needs string operations, file I/O, and process execution that do not yet exist in the runtime or stdlib.
2. **Rewrite every compiler module in ReFlow** — same pipeline, same algorithms, same output. The ReFlow compiler must produce identical C output to the Python compiler on all test programs.
3. **Verify the bootstrap** — compile the ReFlow compiler with itself and confirm the output is stable (stage 2 = stage 3).

The self-hosted compiler lives in `self_hosted/` and is organized as ReFlow modules mirroring `compiler/`:

```
self_hosted/
  errors.reflow          → error types
  tokens.reflow          → Token and TokenType
  ast.reflow             → AST node sum types
  types.reflow           → Type hierarchy
  lir.reflow             → LIR node sum types
  symbols.reflow         → Symbol, Scope, ResolvedModule
  mangler.reflow         → name mangling
  lexer.reflow           → source → tokens
  parser.reflow          → tokens → AST
  resolver.reflow        → AST → ResolvedModule
  typechecker.reflow     → ResolvedModule → TypedModule
  lowering.reflow        → TypedModule → LModule
  emitter.reflow         → LModule → C string
  driver.reflow          → pipeline orchestration
  main.reflow            → CLI entry point
```

The compiler is compiled with the Python compiler:
```
python main.py build self_hosted/main.reflow -o reflowc
```

---

## Conventions for This Document

- **Epic**: A major phase of the bootstrap.
- **Story**: A coherent unit of work within an epic.
- **Ticket**: A single implementable task with a clear definition of done.
- Tickets are numbered `RB-EPIC-STORY-TICKET`, e.g., `RB-0-0-1`.
- Tickets marked `[BLOCKER]` must be complete before the next epic can begin.
- The Python compiler is the reference throughout. "Same behavior" means normalized-identical C output for the same ReFlow input (see Parity Testing Strategy below).
- All ReFlow source in this plan uses the frozen language spec — no new language features are added.

---

## Key Design Decisions

These decisions affect every module in the self-hosted compiler and must be understood before any implementation begins.

### Node Identity

The Python compiler uses AST nodes as dictionary keys via Python's identity-based `__hash__`. ReFlow has no equivalent. Instead, every AST node, Type, and LIR node receives a unique integer `id` field assigned during construction. Side maps use `map<int, T>` keyed by node ID.

A global counter (module-level static or passed through context) assigns IDs:

```
type ASTNode = {
    id: int
    line: int
    col: int
}
```

The `id` is assigned by the parser (for AST nodes), the type checker (for Type nodes), and the lowerer (for LIR nodes). Each pass maintains its own counter.

### Sum Types for Node Hierarchies

Python uses `isinstance` dispatch on class hierarchies. ReFlow uses `match` on sum types. Each node hierarchy becomes a sum type:

```
type Expr =
    | IntLit(id: int, line: int, col: int, value: int, suffix: string?)
    | FloatLit(id: int, line: int, col: int, value: float, suffix: string?)
    | BoolLit(id: int, line: int, col: int, value: bool)
    | StringLit(id: int, line: int, col: int, value: string)
    | Ident(id: int, line: int, col: int, name: string, module_path: array<string>)
    | BinOp(id: int, line: int, col: int, op: string, left: Expr, right: Expr)
    ...
```

### No Mutation of AST Nodes

Same invariant as the Python compiler: AST nodes are immutable after parsing. Downstream passes use side maps (`map<int, Symbol>`, `map<int, Type>`) keyed by node ID.

### Context Objects Instead of Class State

Python uses `self._field` for mutable state inside compiler passes. ReFlow has no classes with mutable instance state in the same way. Instead, each pass uses a mutable context record:

```
type LexerCtx = {
    source: string
    filename: string
    pos: int:mut
    line: int:mut
    col: int:mut
    tokens: buffer<Token>:mut
}
```

Functions take `ctx: LexerCtx:mut` as their first parameter.

### String Building

The emitter builds a C source string. Python uses `list[str]` with `join`. ReFlow uses `buffer<string>` with `push` and a final join operation. The `string.join` stdlib function joins an array of strings with a separator.

---

## Parity Testing Strategy

The parity test (`verify_parity.py`) compares C output from the Python compiler and the ReFlow compiler. The comparison uses **normalized parity**, not byte-for-byte identity. Before diffing, both outputs are passed through a normalizer that:

1. Replaces temp variable names (`_rf_tmp_42`, `_rf_e_7`) with sequential counters (`_rf_tmp_0`, `_rf_tmp_1`, ...) per function scope.
2. Strips trailing whitespace from each line.
3. Normalizes line endings to `\n`.

The normalizer does **not** alter:
- Mangled names (these must match exactly — any divergence is a real bug)
- Struct field names and ordering
- Forward declaration order (this must match — it reflects the compilation order)
- Literal values, operator choices, or control flow structure

Rationale: true byte-for-byte identity is fragile and produces false negatives when temp variable counters drift due to harmless differences in expression evaluation order. Normalized parity catches all real bugs (wrong names, wrong types, wrong control flow, missing declarations) while tolerating the one class of difference that is semantically irrelevant.

---

---

# EPIC 0: Python Compiler Prerequisites

The Python compiler cannot compile a multi-file ReFlow program, and it has not been tested with recursive sum types. Both are required before any self-hosted compiler code can be written. These tickets extend the Python compiler — not the ReFlow code.

---

## Story 0-0: Multi-File Compilation

**RB-0-0-1** `[BLOCKER]`
Implement multi-file compilation in the Python compiler (deferred ticket RT-9-2-1). The self-hosted compiler is 14 `.reflow` files that import each other. The Python compiler must:

1. Accept a root module file as input.
2. Parse the root module. For each `import` declaration that is not a stdlib module, resolve it to a `.reflow` file relative to the root module's directory.
3. Recursively parse and resolve all transitive imports, building a dependency graph.
4. Detect circular imports and report a `ResolveError`.
5. Process modules in dependency order (leaves first): resolve, type-check, lower, emit each module.
6. Concatenate all emitted C into a single `.c` file (or pass multiple `.c` files to clang).
7. Link against the runtime and produce a single binary.

The driver's `_discover_imports` currently only looks in `stdlib/`. Extend it to also look in the filesystem relative to the source file. Stdlib modules take priority over filesystem modules with the same name.

**Definition of done**: `python main.py build self_hosted/main.reflow -o reflowc` compiles all 14 modules and produces a binary, once those modules have content.

**RB-0-0-2** `[BLOCKER]`
Write tests for multi-file compilation:
- Create `tests/programs/multi/main.reflow` that imports `tests/programs/multi/helper.reflow`.
- `helper.reflow` exports a function. `main.reflow` calls it and prints the result.
- Verify `python main.py build tests/programs/multi/main.reflow` compiles, links, and runs correctly.
- Verify circular imports between two files produce a `ResolveError`.

**RB-0-0-3** `[BLOCKER]`
Update `emit_only` and `check_only` to also handle multi-file programs. When the root module imports non-stdlib modules, all imported modules must be emitted (for `emit_only`) or checked (for `check_only`).

---

## Story 0-1: Recursive Sum Type Support

**RB-0-1-1** `[BLOCKER]`
The self-hosted compiler uses recursive sum types: `Expr` contains `BinOp` which has fields of type `Expr`. In C, a tagged union struct cannot contain an instance of itself (incomplete type). The generated C must use pointers for recursive variant fields.

Write a test program `tests/programs/recursive_sum.reflow`:
```
module recursive_sum

import io

type Tree =
    | Leaf(value: int)
    | Node(left: Tree, right: Tree)

fn sum_tree(t: Tree): int {
    match t {
        Leaf(v): return v
        Node(l, r): return sum_tree(l) + sum_tree(r)
    }
}

fn main(): none {
    let tree = Node(Node(Leaf(1), Leaf(2)), Leaf(3))
    io.println(f"Sum: {sum_tree(tree)}")
}
```

Compile with the Python compiler. If the emitter produces invalid C (incomplete type error from clang), fix it before proceeding. The fix likely requires:
- Detecting which sum type fields are self-referential (field type == enclosing sum type)
- Emitting those fields as pointers in the C struct
- Emitting heap allocation when constructing recursive variants
- Adjusting match lowering to dereference pointer fields

**RB-0-1-2**
Add the recursive sum type test to both the golden file tests (expected C output) and E2E tests (expected stdout: `Sum: 6`).

**RB-0-1-3**
Verify that mutually recursive sum types also work. Write a test with two types that reference each other:
```
type Expr =
    | Lit(value: int)
    | Add(left: Expr, right: Expr)
    | Neg(inner: Expr)
```
This tests self-recursion within a single sum type. If the compiler needs to handle mutual recursion between separate types (type A contains type B, type B contains type A), add that support and test it.

---

---

# EPIC 1: Standard Library Extensions

Before writing any compiler code in ReFlow, the standard library must be extended with string operations, character utilities, file I/O, and process execution. These are implemented as C runtime functions with native ReFlow wrappers.

---

## Story 1-1: String Operations

**RB-1-1-1** `[BLOCKER]`
Add `rf_string_char_at` to the C runtime. Signature:
```c
RF_Option_ptr rf_string_char_at(RF_String* s, rf_int64 idx);
```
Returns `some(char)` if `idx` is within bounds (byte index into UTF-8), `none` otherwise. For the bootstrap compiler, all source files are ASCII, so byte indexing is sufficient. Document this as a known simplification.

Create `stdlib/string.reflow` with:
```
module string

export fn char_at(s: string, idx: int): char? = native "rf_string_char_at"
```

**RB-1-1-2** `[BLOCKER]`
Add `rf_string_substring` to the C runtime. Signature:
```c
RF_String* rf_string_substring(RF_String* s, rf_int64 start, rf_int64 end);
```
Returns a new string from byte offset `start` (inclusive) to `end` (exclusive). Panics if `start > end` or `end > len`. Add to `stdlib/string.reflow`:
```
export fn substring(s: string, start: int, end_idx: int): string = native "rf_string_substring"
```

**RB-1-1-3** `[BLOCKER]`
Add `rf_string_index_of` to the C runtime. Signature:
```c
RF_Option_ptr rf_string_index_of(RF_String* haystack, RF_String* needle);
```
Returns `some(int)` with the byte offset of the first occurrence, or `none` if not found. Add to `stdlib/string.reflow`:
```
export fn index_of(s: string, needle: string): int? = native "rf_string_index_of"
```

**RB-1-1-4**
Add `rf_string_contains` to the C runtime. Returns `true` if `needle` appears anywhere in `s`. Add to `stdlib/string.reflow`:
```
export fn contains(s: string, needle: string): bool = native "rf_string_contains"
```

**RB-1-1-5**
Add `rf_string_starts_with` and `rf_string_ends_with` to the C runtime. Add to `stdlib/string.reflow`:
```
export fn starts_with(s: string, prefix: string): bool = native "rf_string_starts_with"
export fn ends_with(s: string, suffix: string): bool = native "rf_string_ends_with"
```

**RB-1-1-6**
Add `rf_string_split` to the C runtime. Signature:
```c
RF_Array* rf_string_split(RF_String* s, RF_String* sep);
```
Returns an `array<string>`. If `sep` is empty, splits into individual characters. Add to `stdlib/string.reflow`:
```
export fn split(s: string, sep: string): array<string> = native "rf_string_split"
```

**RB-1-1-7**
Add `rf_string_trim`, `rf_string_trim_left`, `rf_string_trim_right` to the C runtime. Trims ASCII whitespace (space, tab, newline, carriage return). Add to `stdlib/string.reflow`:
```
export fn trim(s: string): string = native "rf_string_trim"
export fn trim_left(s: string): string = native "rf_string_trim_left"
export fn trim_right(s: string): string = native "rf_string_trim_right"
```

**RB-1-1-8**
Add `rf_string_replace` to the C runtime. Replaces all occurrences of `old` with `new_str`. Add to `stdlib/string.reflow`:
```
export fn replace(s: string, old: string, new_str: string): string = native "rf_string_replace"
```

**RB-1-1-9**
Add `rf_string_join` to the C runtime. Signature:
```c
RF_String* rf_string_join(RF_Array* parts, RF_String* sep);
```
Joins an array of strings with separator. Add to `stdlib/string.reflow`:
```
export fn join(parts: array<string>, sep: string): string = native "rf_string_join"
```

**RB-1-1-10**
Add `rf_string_to_lower` and `rf_string_to_upper` to the C runtime. ASCII-only (sufficient for the compiler). Add to `stdlib/string.reflow`:
```
export fn to_lower(s: string): string = native "rf_string_to_lower"
export fn to_upper(s: string): string = native "rf_string_to_upper"
```

---

## Story 1-2: Character Utilities

**RB-1-2-1** `[BLOCKER]`
Add character classification functions to the C runtime:
```c
rf_bool rf_char_is_digit(rf_char c);
rf_bool rf_char_is_alpha(rf_char c);
rf_bool rf_char_is_alphanumeric(rf_char c);
rf_bool rf_char_is_whitespace(rf_char c);
```
These operate on the `rf_char` type (uint32_t Unicode scalar). For the bootstrap, ASCII classification is sufficient: `is_digit` checks `'0'–'9'`, `is_alpha` checks `'a'–'z'` and `'A'–'Z'` and `'_'`, `is_alphanumeric` is `is_alpha || is_digit`, `is_whitespace` checks space, tab, newline, carriage return.

Create `stdlib/char.reflow`:
```
module char

export pure fn is_digit(c: char): bool = native "rf_char_is_digit"
export pure fn is_alpha(c: char): bool = native "rf_char_is_alpha"
export pure fn is_alphanumeric(c: char): bool = native "rf_char_is_alphanumeric"
export pure fn is_whitespace(c: char): bool = native "rf_char_is_whitespace"
```

**RB-1-2-2**
Add `rf_char_to_int` and `rf_int_to_char` to the C runtime. These are trivial casts between `rf_char` (uint32_t) and `rf_int` (int32_t). Add to `stdlib/char.reflow`:
```
export pure fn to_code(c: char): int = native "rf_char_to_int"
export pure fn from_code(n: int): char = native "rf_int_to_char"
```

**RB-1-2-3**
Add `rf_char_to_string` to the C runtime. Converts a single char to a one-character string. Add to `stdlib/char.reflow`:
```
export pure fn to_string(c: char): string = native "rf_char_to_string"
```

---

## Story 1-3: File I/O

**RB-1-3-1** `[BLOCKER]`
Add `rf_read_file` to the C runtime. Signature:
```c
RF_Option_ptr rf_read_file(RF_String* path);
```
Opens the file at `path`, reads its entire contents into a new `RF_String*`, and returns `some(string)`. If the file cannot be opened or read, returns `none`. Update `stdlib/io.reflow`:
```
export fn read_file(path: string): string? = native "rf_read_file"
```

**RB-1-3-2** `[BLOCKER]`
Add `rf_write_file` to the C runtime. Signature:
```c
rf_bool rf_write_file(RF_String* path, RF_String* contents);
```
Writes `contents` to `path`, creating or overwriting the file. Returns `true` on success, `false` on failure. Update `stdlib/io.reflow`:
```
export fn write_file(path: string, contents: string): bool = native "rf_write_file"
```

---

## Story 1-4: Process Execution

**RB-1-4-1** `[BLOCKER]`
Add `rf_run_process` to the C runtime. Signature:
```c
rf_int rf_run_process(RF_String* command, RF_Array* args);
```
Forks and executes the command with the given arguments. Returns the process exit code. Stdout and stderr are inherited (passed through to the calling process). This is used by the driver to shell out to `clang`. Implementation uses `fork`/`exec` on Unix or `posix_spawn`. Update `stdlib/sys.reflow`:
```
export fn run_process(command: string, args: array<string>): int = native "rf_run_process"
```

**RB-1-4-2**
Add `rf_run_process_capture` to the C runtime. Same as `rf_run_process` but captures stderr into a string. Signature:
```c
RF_Option_ptr rf_run_process_capture(RF_String* command, RF_Array* args);
```
Returns `some(string)` containing stderr on non-zero exit, `none` on success. Update `stdlib/sys.reflow`:
```
export fn run_process_capture(command: string, args: array<string>): string? = native "rf_run_process_capture"
```

---

## Story 1-5: Temporary File Support

**RB-1-5-1** `[BLOCKER]`
Add `rf_tmpfile_create` and `rf_tmpfile_remove` to the C runtime. The driver needs to write generated C to a temp file before passing it to clang.
```c
RF_String* rf_tmpfile_create(RF_String* suffix, RF_String* contents);
void       rf_tmpfile_remove(RF_String* path);
```
`rf_tmpfile_create` creates a temp file with the given suffix, writes `contents`, and returns the path. `rf_tmpfile_remove` deletes the file. Update `stdlib/io.reflow`:
```
export fn tmpfile_create(suffix: string, contents: string): string = native "rf_tmpfile_create"
export fn tmpfile_remove(path: string): none = native "rf_tmpfile_remove"
```

---

## Story 1-6: Path Utilities

**RB-1-6-1**
Add path manipulation functions to the C runtime:
```c
RF_String* rf_path_join(RF_String* a, RF_String* b);
RF_String* rf_path_stem(RF_String* path);      /* "foo/bar.reflow" → "bar" */
RF_String* rf_path_parent(RF_String* path);    /* "foo/bar.reflow" → "foo" */
RF_String* rf_path_with_suffix(RF_String* path, RF_String* suffix);
RF_String* rf_path_cwd(void);
RF_String* rf_path_resolve(RF_String* path);   /* absolute path */
```
Create `stdlib/path.reflow`:
```
module path

export fn join(a: string, b: string): string = native "rf_path_join"
export fn stem(p: string): string = native "rf_path_stem"
export fn parent(p: string): string = native "rf_path_parent"
export fn with_suffix(p: string, suffix: string): string = native "rf_path_with_suffix"
export fn cwd(): string = native "rf_path_cwd"
export fn resolve(p: string): string = native "rf_path_resolve"
```

---

## Story 1-7: Tests

**RB-1-7-1**
Write unit tests for all new string operations: `char_at`, `substring`, `index_of`, `contains`, `starts_with`, `ends_with`, `split`, `trim`, `replace`, `join`, `to_lower`, `to_upper`. Each function gets at least one positive and one edge-case test.

**RB-1-7-2**
Write unit tests for character utilities: `is_digit`, `is_alpha`, `is_alphanumeric`, `is_whitespace`, `to_code`, `from_code`, `to_string`.

**RB-1-7-3**
Write integration tests for file I/O: `read_file` on an existing file, `read_file` on a nonexistent file (returns `none`), `write_file` creating a new file, `write_file` overwriting.

**RB-1-7-4**
Write integration tests for process execution: `run_process("echo", ["hello"])` returns 0, `run_process("false", [])` returns non-zero.

**RB-1-7-5**
Write integration tests for path utilities: `join`, `stem`, `parent`, `with_suffix`, `cwd`, `resolve`.

---

---

# EPIC 2: Language Freeze & Project Setup

Freeze the language, establish the self-hosted compiler directory structure, and create the verification infrastructure.

---

## Story 2-1: Language Freeze

**RB-2-1-1** `[BLOCKER]`
Document the frozen feature set in `FROZEN.md` at the project root. List every language feature the self-hosted compiler will use and every feature it will not use. The compiler uses:

**Used:**
- Primitive types: `int`, `int64`, `float`, `bool`, `char`, `byte`, `string`, `none`
- Container types: `array<T>`, `map<K,V>`, `set<T>`, `buffer<T>`, `option<T>`, `result<T,E>`, tuples
- Sum types with payload and unit variants
- Pattern matching with exhaustiveness checking
- Functions: named, pure, lambdas, methods, native
- Control flow: `if`/`else`, `while`, `for`, `match`, `break`, `return`
- Operators: arithmetic, comparison, logical, string concatenation, `?` propagation, `??` null coalesce
- F-strings
- Module system: `module`, `import`, `export`
- Mutability: `:mut`, `:imut`, `@copy`
- Type statics
- Generics

**Not used (and therefore not required to compile the compiler):**
- Streams and `yield`
- Composition chains (`->`)
- Fan-out (`|`, `<:(`)
- Coroutines (`:< `)
- Try/catch/retry/throw
- Interfaces and `fulfills`
- Constructors
- Struct spread (`..source`)
- Coerce and cast

This distinction matters: the self-hosted compiler only needs to correctly compile the subset it uses. Full language support is added iteratively after the bootstrap succeeds.

**RB-2-1-2**
No new language features, no new syntax, and no new semantics may be added to the spec after this ticket is complete. All subsequent work is implementation of the existing spec.

---

## Story 2-2: Project Structure

**RB-2-2-1** `[BLOCKER]`
Create the `self_hosted/` directory with empty `.reflow` files for each module:

```
self_hosted/
  errors.reflow
  tokens.reflow
  ast.reflow
  types.reflow
  lir.reflow
  symbols.reflow
  mangler.reflow
  lexer.reflow
  parser.reflow
  resolver.reflow
  typechecker.reflow
  lowering.reflow
  emitter.reflow
  driver.reflow
  main.reflow
```

Each file has a `module self_hosted.<name>` declaration. The top-level `main.reflow` has `module self_hosted.main`.

**RB-2-2-2**
Create `tests/bootstrap/` directory. This is where bootstrap-specific tests live: programs that verify the self-hosted compiler produces identical output to the Python compiler.

**RB-2-2-3**
Create `tests/bootstrap/verify_parity.py`. This script:
1. Takes a `.reflow` source file as input.
2. Runs `python main.py emit-c <file>` to get the Python compiler's C output.
3. Runs `./reflowc emit-c <file>` to get the ReFlow compiler's C output.
4. Diffs the two outputs.
5. Exits 0 if identical, 1 if different, printing the diff.

**RB-2-2-4**
Add Makefile targets:
- `make bootstrap-build` — compiles `self_hosted/main.reflow` to `reflowc` using the Python compiler.
- `make bootstrap-verify` — runs `verify_parity.py` on all test programs.
- `make bootstrap-stage2` — uses `reflowc` to compile `self_hosted/main.reflow` to `reflowc_stage2`.
- `make bootstrap-stage3` — uses `reflowc_stage2` to compile `self_hosted/main.reflow` to `reflowc_stage3`.
- `make bootstrap-check` — diffs `reflowc_stage2` output vs `reflowc_stage3` output on all test programs.

---

---

# EPIC 3: Core Data Types

Define all data types the compiler uses as ReFlow sum types and records. These are pure data definitions with no logic — the ReFlow equivalent of `ast_nodes.py`, the Type hierarchy in `typechecker.py`, and the LIR nodes in `lowering.py`.

This epic has no dependencies other than the language being frozen. All types are defined before any compiler logic is written.

---

## Story 3-1: Error Types

**RB-3-1-1** `[BLOCKER]`
In `self_hosted/errors.reflow`, define the error types as a sum type:

```
module self_hosted.errors

export type ErrorKind =
    | LexError
    | ParseError
    | ResolveError
    | TypeError
    | EmitError

export type CompilerError = {
    kind: ErrorKind
    message: string
    file: string
    line: int
    col: int
}
```

Define a helper function `format_error(e: CompilerError): string` that produces `"file:line:col: ErrorKind: message"`.

---

## Story 3-2: Token Types

**RB-3-2-1** `[BLOCKER]`
In `self_hosted/tokens.reflow`, define `TokenType` as a sum type with all 118 token variants. Group them logically:

```
module self_hosted.tokens

export type TokenType =
    ; Keywords
    | KW_MODULE | KW_IMPORT | KW_EXPORT | KW_FN | KW_PURE | KW_TYPE
    | KW_INTERFACE | KW_ALIAS | KW_LET | KW_MUT | KW_IMUT | KW_IF
    | KW_ELSE | KW_WHILE | KW_FOR | KW_IN | KW_MATCH | KW_RETURN
    | KW_BREAK | KW_YIELD | KW_TRY | KW_CATCH | KW_RETRY | KW_THROW
    | KW_FINALLY | KW_TRUE | KW_FALSE | KW_NONE | KW_SOME | KW_OK
    | KW_ERR | KW_SELF | KW_STATIC | KW_CONSTRUCTOR | KW_FULFILLS
    | KW_AS | KW_COERCE | KW_CAST | KW_TYPEOF | KW_SNAPSHOT | KW_NATIVE
    | KW_OPTION | KW_RESULT | KW_STREAM | KW_BUFFER | KW_MAP | KW_SET
    | KW_ARRAY | KW_INT | KW_INT16 | KW_INT32 | KW_INT64
    | KW_UINT | KW_UINT16 | KW_UINT32 | KW_UINT64
    | KW_FLOAT | KW_FLOAT32 | KW_FLOAT64 | KW_BOOL | KW_BYTE
    | KW_CHAR | KW_STRING | KW_RECORD | KW_COPY
    ; Operators
    | ARROW | FAT_ARROW | PARALLEL_FANOUT | SUBTYPE | DOTDOT
    | PLUS_EQ | MINUS_EQ | STAR_EQ | SLASH_EQ
    | PLUS_PLUS | MINUS_MINUS | STAR_STAR | SLASH_SLASH
    | EQ_EQ | BANG_EQ | EQ_EQ_EQ | LT_EQ | GT_EQ
    | AMP_AMP | PIPE_PIPE | QUESTION_QUESTION
    ; Punctuation
    | LPAREN | RPAREN | LBRACE | RBRACE | LBRACKET | RBRACKET
    | COLON | SEMICOLON | COMMA | DOT | EQ | BANG | QUESTION
    | PLUS | MINUS | STAR | SLASH | PERCENT | LT | GT | PIPE
    | AMP | AT | BACKSLASH | HASH
    ; Literals
    | INT_LIT | FLOAT_LIT | BOOL_LIT | STRING_LIT | CHAR_LIT
    | FSTRING_START | FSTRING_TEXT | FSTRING_EXPR_START
    | FSTRING_EXPR_END | FSTRING_END
    ; Other
    | IDENT | COMMENT | NEWLINE | EOF
```

**RB-3-2-2**
Define the `Token` record and the keyword lookup map:

```
export type Token = {
    type: TokenType
    value: string
    line: int
    col: int
    file: string
}

export fn keyword_lookup(name: string): TokenType?
```

`keyword_lookup` checks the name against a `map<string, TokenType>` built once as a module-level static and returns `some(token_type)` if it is a keyword, `none` if it is an identifier.

---

## Story 3-3: AST Node Types

**RB-3-3-1** `[BLOCKER]`
In `self_hosted/ast.reflow`, define `TypeExpr` as a sum type:

```
module self_hosted.ast

export type TypeExpr =
    | NamedType(id: int, line: int, col: int, name: string, module_path: array<string>)
    | GenericType(id: int, line: int, col: int, base: TypeExpr, args: array<TypeExpr>)
    | OptionType(id: int, line: int, col: int, inner: TypeExpr)
    | FnType(id: int, line: int, col: int, params: array<TypeExpr>, ret: TypeExpr)
    | TupleType(id: int, line: int, col: int, elements: array<TypeExpr>)
    | MutType(id: int, line: int, col: int, inner: TypeExpr)
    | ImutType(id: int, line: int, col: int, inner: TypeExpr)
    | SumTypeExpr(id: int, line: int, col: int, variants: array<SumVariantDecl>)
```

**RB-3-3-2** `[BLOCKER]`
Define `Expr` as a sum type with all 35 expression variants:

```
export type Expr =
    | IntLit(id: int, line: int, col: int, value: int, suffix: string?)
    | FloatLit(id: int, line: int, col: int, value: float, suffix: string?)
    | BoolLit(id: int, line: int, col: int, value: bool)
    | StringLit(id: int, line: int, col: int, value: string)
    | FStringExpr(id: int, line: int, col: int, parts: array<FStringPart>)
    | CharLit(id: int, line: int, col: int, value: char)
    | NoneLit(id: int, line: int, col: int)
    | Ident(id: int, line: int, col: int, name: string, module_path: array<string>)
    | BinOp(id: int, line: int, col: int, op: string, left: Expr, right: Expr)
    | UnaryOp(id: int, line: int, col: int, op: string, operand: Expr)
    | Call(id: int, line: int, col: int, callee: Expr, args: array<Expr>)
    | MethodCall(id: int, line: int, col: int, receiver: Expr, method: string, args: array<Expr>)
    | FieldAccess(id: int, line: int, col: int, receiver: Expr, field: string)
    | IndexAccess(id: int, line: int, col: int, receiver: Expr, index: Expr)
    | Lambda(id: int, line: int, col: int, params: array<Param>, body: Expr)
    | TupleExpr(id: int, line: int, col: int, elements: array<Expr>)
    | ArrayLit(id: int, line: int, col: int, elements: array<Expr>)
    | RecordLit(id: int, line: int, col: int, fields: array<(string, Expr)>)
    | TypeLit(id: int, line: int, col: int, type_name: string, fields: array<(string, Expr)>, spread: Expr?)
    | IfExpr(id: int, line: int, col: int, condition: Expr, then_branch: Block, else_branch: Block?)
    | MatchExpr(id: int, line: int, col: int, subject: Expr, arms: array<MatchArm>)
    | CompositionChain(id: int, line: int, col: int, elements: array<ChainElement>)
    | ChainElement(id: int, line: int, col: int, expr: Expr)
    | FanOut(id: int, line: int, col: int, branches: array<Expr>, parallel: bool)
    | TernaryExpr(id: int, line: int, col: int, condition: Expr, then_expr: Expr, else_expr: Expr)
    | CopyExpr(id: int, line: int, col: int, inner: Expr)
    | SomeExpr(id: int, line: int, col: int, inner: Expr)
    | OkExpr(id: int, line: int, col: int, inner: Expr)
    | ErrExpr(id: int, line: int, col: int, inner: Expr)
    | CoerceExpr(id: int, line: int, col: int, inner: Expr, target_type: TypeExpr)
    | CastExpr(id: int, line: int, col: int, inner: Expr, target_type: TypeExpr)
    | SnapshotExpr(id: int, line: int, col: int, inner: Expr)
    | PropagateExpr(id: int, line: int, col: int, inner: Expr)
    | NullCoalesce(id: int, line: int, col: int, left: Expr, right: Expr)
    | TypeofExpr(id: int, line: int, col: int, inner: Expr)

export type FStringPart =
    | TextPart(value: string)
    | ExprPart(expr: Expr)
```

**RB-3-3-3** `[BLOCKER]`
Define `Stmt` as a sum type with all 17 statement variants:

```
export type Stmt =
    | LetStmt(id: int, line: int, col: int, name: string, type_ann: TypeExpr?, value: Expr, is_mut: bool)
    | AssignStmt(id: int, line: int, col: int, target: Expr, value: Expr)
    | UpdateStmt(id: int, line: int, col: int, target: Expr, op: string, value: Expr?)
    | ReturnStmt(id: int, line: int, col: int, value: Expr?)
    | YieldStmt(id: int, line: int, col: int, value: Expr)
    | ThrowStmt(id: int, line: int, col: int, exception: Expr)
    | BreakStmt(id: int, line: int, col: int)
    | ExprStmt(id: int, line: int, col: int, expr: Expr)
    | IfStmt(id: int, line: int, col: int, condition: Expr, then_branch: Block, else_branch: Block?)
    | WhileStmt(id: int, line: int, col: int, condition: Expr, body: Block, finally_block: Block?)
    | ForStmt(id: int, line: int, col: int, var_name: string, var_type: TypeExpr?, iterable: Expr, body: Block, finally_block: Block?)
    | MatchStmt(id: int, line: int, col: int, subject: Expr, arms: array<MatchArm>)
    | TryStmt(id: int, line: int, col: int, body: Block, retry_blocks: array<RetryBlock>, catch_blocks: array<CatchBlock>, finally_block: Block?)
    | BlockStmt(id: int, line: int, col: int, block: Block)

export type Block = {
    stmts: array<Stmt>
    finally_block: Block?
}

export type MatchArm = {
    pattern: Pattern
    body: Block
}
```

**RB-3-3-4** `[BLOCKER]`
Define `Pattern` as a sum type:

```
export type Pattern =
    | WildcardPattern(id: int, line: int, col: int)
    | LiteralPattern(id: int, line: int, col: int, value: Expr)
    | BindPattern(id: int, line: int, col: int, name: string)
    | SomePattern(id: int, line: int, col: int, inner_var: string)
    | NonePattern(id: int, line: int, col: int)
    | OkPattern(id: int, line: int, col: int, inner_var: string)
    | ErrPattern(id: int, line: int, col: int, inner_var: string)
    | VariantPattern(id: int, line: int, col: int, variant_name: string, bindings: array<string>)
    | TuplePattern(id: int, line: int, col: int, elements: array<Pattern>)
```

**RB-3-3-5** `[BLOCKER]`
Define `Decl` as a sum type:

```
export type Decl =
    | ModuleDecl(id: int, line: int, col: int, path: array<string>)
    | ImportDecl(id: int, line: int, col: int, path: array<string>, names: array<string>?, alias: string?)
    | FnDecl(id: int, line: int, col: int, name: string, type_params: array<string>,
             params: array<Param>, return_type: TypeExpr?, body: Block?,
             is_pure: bool, is_export: bool, is_static: bool,
             finally_block: Block?, native_name: string?)
    | TypeDecl(id: int, line: int, col: int, name: string, type_params: array<string>,
               fields: array<FieldDecl>, methods: array<FnDecl>,
               constructors: array<ConstructorDecl>, static_members: array<StaticMemberDecl>,
               interfaces: array<string>, is_export: bool, is_sum_type: bool,
               variants: array<SumVariantDecl>?)
    | InterfaceDecl(id: int, line: int, col: int, name: string, type_params: array<string>,
                    methods: array<FnDecl>, is_export: bool)
    | AliasDecl(id: int, line: int, col: int, name: string, type_params: array<string>,
                target: TypeExpr, is_export: bool)

export type Param = {
    name: string
    type_ann: TypeExpr?
    is_mut: bool
    is_imut: bool
}

export type FieldDecl = {
    name: string
    type_ann: TypeExpr
    is_mut: bool
}

export type SumVariantDecl = {
    name: string
    fields: array<FieldDecl>?
}

export type StaticMemberDecl = {
    name: string
    type_ann: TypeExpr
    value: Expr
    is_mut: bool
}

export type ConstructorDecl = {
    name: string
    params: array<Param>
    return_type: TypeExpr?
    body: Block
}
```

**RB-3-3-6**
Define the top-level `Module` record:

```
export type Module = {
    path: array<string>
    imports: array<Decl>
    decls: array<Decl>
    filename: string
}
```

---

## Story 3-4: Type System Types

**RB-3-4-1** `[BLOCKER]`
In `self_hosted/types.reflow`, define the `Type` sum type with all 28 variants:

```
module self_hosted.types

export type Type =
    ; Primitives
    | TInt(width: int, signed: bool)
    | TFloat(width: int)
    | TBool
    | TChar
    | TByte
    | TString
    | TNone
    ; Containers
    | TOption(inner: Type)
    | TResult(ok_type: Type, err_type: Type)
    | TTuple(elements: array<Type>)
    | TArray(element: Type)
    | TStream(element: Type)
    | TBuffer(element: Type)
    | TMap(key: Type, value: Type)
    | TSet(element: Type)
    ; Functions
    | TFn(params: array<Type>, ret: Type, is_pure: bool)
    ; Structured
    | TRecord(fields: array<(string, Type)>)
    | TNamed(module_path: string, name: string, type_args: array<Type>)
    | TAlias(name: string, underlying: Type)
    | TSum(name: string, variants: array<TVariant>)
    | TVariant(name: string, fields: array<(string, Type)>)
    ; Special
    | TTypeVar(name: string)
    | TAny
```

**RB-3-4-2**
Define supporting type structures:

```
export type TypeEnv = map<string, Type>

export type TypeInfo = {
    name: string
    type_params: array<string>
    fields: map<string, Type>
    field_mutability: map<string, bool>
    methods: map<string, Type>
    statics: map<string, Type>
    constructors: map<string, Type>
    is_sum_type: bool
    sum_type: Type?
}

export type TypedModule = {
    module: Module
    resolved: ResolvedModule
    types: map<int, Type>
    warnings: array<string>
}
```

**RB-3-4-3**
Implement `apply_env(t: Type, env: TypeEnv): Type` — recursively substitutes type variables using the given environment. This is a pure function that pattern-matches on every `Type` variant.

---

## Story 3-5: LIR Node Types

**RB-3-5-1** `[BLOCKER]`
In `self_hosted/lir.reflow`, define the LIR type hierarchy:

```
module self_hosted.lir

export type LType =
    | LInt(width: int, signed: bool)
    | LFloat(width: int)
    | LBool | LChar | LByte
    | LPtr(inner: LType)
    | LStruct(c_name: string)
    | LVoid
    | LFnPtr(params: array<LType>, ret: LType)
```

**RB-3-5-2** `[BLOCKER]`
Define `LExpr` with all 17 variants:

```
export type LExpr =
    | LLit(value: string, c_type: LType)
    | LVar(c_name: string, c_type: LType)
    | LCall(fn_name: string, args: array<LExpr>, c_type: LType)
    | LIndirectCall(fn_ptr: LExpr, args: array<LExpr>, c_type: LType)
    | LBinOp(op: string, left: LExpr, right: LExpr, c_type: LType)
    | LUnary(op: string, operand: LExpr, c_type: LType)
    | LFieldAccess(obj: LExpr, field: string, c_type: LType)
    | LArrow(ptr: LExpr, field: string, c_type: LType)
    | LIndex(arr: LExpr, idx: LExpr, c_type: LType)
    | LCast(inner: LExpr, c_type: LType)
    | LAddrOf(inner: LExpr, c_type: LType)
    | LDeref(inner: LExpr, c_type: LType)
    | LCompound(fields: array<(string, LExpr)>, c_type: LType)
    | LCheckedArith(op: string, left: LExpr, right: LExpr, c_type: LType)
    | LSizeOf(target: LType, c_type: LType)
    | LArrayData(elements: array<LExpr>, elem_type: LType, c_type: LType)
    | LTernary(cond: LExpr, then_expr: LExpr, else_expr: LExpr, c_type: LType)
```

**RB-3-5-3** `[BLOCKER]`
Define `LStmt` with all 11 variants:

```
export type LStmt =
    | LVarDecl(c_name: string, c_type: LType, init: LExpr?)
    | LAssign(target: LExpr, value: LExpr)
    | LReturn(value: LExpr?)
    | LIf(cond: LExpr, then_body: array<LStmt>, else_body: array<LStmt>?)
    | LWhile(cond: LExpr, body: array<LStmt>)
    | LBlock(stmts: array<LStmt>)
    | LExprStmt(expr: LExpr)
    | LGoto(label: string)
    | LLabel(name: string)
    | LSwitch(value: LExpr, cases: array<(int, array<LStmt>)>, default: array<LStmt>?)
    | LBreak
```

**RB-3-5-4**
Define top-level LIR structures:

```
export type LTypeDef = {
    c_name: string
    fields: array<(string, LType)>
}

export type LFnDef = {
    c_name: string
    params: array<(string, LType)>
    ret: LType
    body: array<LStmt>
    is_pure: bool
    source_name: string
}

export type LStaticDef = {
    c_name: string
    c_type: LType
    init: LExpr?
    is_mut: bool
}

export type LModule = {
    type_defs: array<LTypeDef>
    fn_defs: array<LFnDef>
    static_defs: array<LStaticDef>
    entry_point: string?
}
```

---

## Story 3-6: Symbol & Scope Types

**RB-3-6-1** `[BLOCKER]`
In `self_hosted/symbols.reflow`, define resolver data types:

```
module self_hosted.symbols

export type SymbolKind =
    | SKLocal | SKParam | SKFn | SKType | SKInterface
    | SKAlias | SKStatic | SKImport | SKConstructor

export type Symbol = {
    name: string
    kind: SymbolKind
    decl_id: int
    type_ann_id: int?
    is_mut: bool
    native_name: string?
}

export type Scope = {
    bindings: map<string, Symbol>:mut
    parent_id: int?
    is_function_boundary: bool
}

export type ModuleScope = {
    module_path: array<string>
    exports: map<string, Symbol>
}

export type ResolvedModule = {
    module: Module
    symbols: map<int, Symbol>
    captures: map<int, array<Symbol>>
    module_scope: ModuleScope
}
```

Note: `Scope` uses an `int` parent ID instead of a direct reference, since the scope stack is managed as a `map<int, Scope>` arena. This avoids recursive type references.

---

## Story 3-7: ID Allocator

**RB-3-7-1**
Define a simple ID allocator type used by all passes:

```
export type IdAllocator = {
    next_id: int:mut
}

export fn new_id_allocator(): IdAllocator = IdAllocator { next_id: 0 }
export fn alloc_id(a: IdAllocator:mut): int {
    let id = a.next_id
    a.next_id = a.next_id + 1
    return id
}
```

This replaces the Python pattern of using object identity for dict keys.

---

---

# EPIC 4: Name Mangler

Reimplement `compiler/mangler.py` in ReFlow. Pure string operations. This is the simplest compiler module and a good first test of writing ReFlow code that matches the Python compiler's output.

---

## Story 4-1: Mangling Functions

**RB-4-1-1** `[BLOCKER]`
In `self_hosted/mangler.reflow`, implement `mangle(module_path: string, type_name: string?, fn_name: string?): string`. Rules:
- Prefix: `rf_`
- Dots in module path become underscores
- Type name appended after module
- Function/method name appended after type
- Example: `mangle("math.vector", some("Vec3"), some("dot"))` → `"rf_math_vector_Vec3_dot"`

**RB-4-1-2**
Implement `mangle_builtin_type(type_name: string): string`. Maps ReFlow type names to C typedefs: `"int"` → `"rf_int"`, `"string"` → `"RF_String*"`, `"bool"` → `"rf_bool"`, `"none"` → `"void"`, etc.

**RB-4-1-3**
Implement stream and closure frame manglers:
- `mangle_stream_frame(module_path: string, fn_name: string): string` → `"_rf_frame_<module>_<fn>"`
- `mangle_stream_next(module_path: string, fn_name: string): string` → `"_rf_next_<module>_<fn>"`
- `mangle_stream_free(module_path: string, fn_name: string): string` → `"_rf_free_<module>_<fn>"`
- `mangle_closure_frame(module_path: string, fn_name: string, lambda_id: int): string` → `"_rf_closure_<module>_<fn>_<id>"`

**RB-4-1-4**
Implement C reserved word checking. Maintain a set of C reserved words. If any component of a mangled name (after the `rf_` prefix) collides with a C keyword, the `rf_` prefix prevents collision. Document this invariant.

---

## Story 4-2: Mangler Tests

**RB-4-2-1**
Write a test program that calls the ReFlow mangler and the Python mangler on the same inputs and diffs the output. Test cases: module-only, module+type, module+type+method, top-level function, builtin types, stream frames, closure frames.

---

---

# EPIC 5: Lexer

Reimplement `compiler/lexer.py` in ReFlow. Character-by-character scanning that produces a `list[Token]` identical to the Python lexer's output.

---

## Story 5-1: Scanner Infrastructure

**RB-5-1-1** `[BLOCKER]`
Define the `LexerCtx` type and core scanner primitives:

```
type LexerCtx = {
    source: string
    filename: string
    pos: int:mut
    line: int:mut
    col: int:mut
    tokens: buffer<Token>:mut
    fstring_depth: int:mut
    fstring_brace_depths: buffer<int>:mut
}
```

Implement:
- `fn at_end(ctx: LexerCtx): bool` — `ctx.pos >= string.len(ctx.source)`
- `fn peek(ctx: LexerCtx): char?` — return current char without consuming
- `fn peek_ahead(ctx: LexerCtx, offset: int): char?` — lookahead
- `fn advance(ctx: LexerCtx:mut): char` — consume and return current char, update line/col
- `fn match_char(ctx: LexerCtx:mut, expected: char): bool` — consume if matches
- `fn add_token(ctx: LexerCtx:mut, type: TokenType, value: string): none`

**RB-5-1-2**
Implement `fn tokenize(source: string, filename: string): array<Token>`. Main entry point. Loops calling `scan_token` until EOF. Appends `Token(EOF, "", line, col, filename)` at the end.

---

## Story 5-2: Keywords and Identifiers

**RB-5-2-1**
Build the keyword map as a `map<string, TokenType>` static. All 54 keywords from the Python `_KEYWORDS` dict.

**RB-5-2-2**
Implement `fn scan_identifier(ctx: LexerCtx:mut): none`. Scans `[a-zA-Z_][a-zA-Z0-9_]*`, looks up in keyword map. Emits either the keyword token type or `IDENT`.

---

## Story 5-3: Literal Scanning

**RB-5-3-1**
Implement `fn scan_number(ctx: LexerCtx:mut): none`. Handles:
- Decimal integers: `42`, `1_000_000`
- Hex integers: `0xFF`, `0xff`
- Floats: `3.14`, `1.0e10`, `.5`
- Integer suffixes: `42i64`, `42u32`
- Float suffixes: `3.14f32`

Emits `INT_LIT` or `FLOAT_LIT` with the raw string as value.

**RB-5-3-2**
Implement `fn scan_string(ctx: LexerCtx:mut): none`. Handles:
- Opening and closing `"`
- Escape sequences: `\n`, `\t`, `\\`, `\"`, `\'`, `\0`, `\r`, `\u{XXXX}`
- Unterminated string → `LexError`
Emits `STRING_LIT` with the interpreted value.

**RB-5-3-3**
Implement `fn scan_char(ctx: LexerCtx:mut): none`. Handles `'x'` and `'\n'` style character literals with the same escape handling as strings. Emits `CHAR_LIT`.

**RB-5-3-4**
Implement `fn scan_escape(ctx: LexerCtx:mut): char`. Shared escape sequence interpreter used by both string and char scanning.

---

## Story 5-4: F-String Scanning

**RB-5-4-1**
Implement `fn scan_fstring(ctx: LexerCtx:mut): none`. Handles:
- `f"` prefix → emit `FSTRING_START`
- Text segments → emit `FSTRING_TEXT`
- `{` → emit `FSTRING_EXPR_START`, push brace depth, switch to normal lexing
- `}` (matching depth) → emit `FSTRING_EXPR_END`, pop brace depth, resume f-string text
- Closing `"` → emit `FSTRING_END`
- Nested f-strings are supported via `fstring_depth` counter and `fstring_brace_depths` stack.

---

## Story 5-5: Operators and Comments

**RB-5-5-1**
Implement `fn scan_operator(ctx: LexerCtx:mut): none`. Maximal munch for all multi-character operators. Check 3-char first (`===`, `<:(`), then 2-char (`->`, `=>`, `==`, `!=`, `<=`, `>=`, `??`, `&&`, `||`, `..`, `++`, `--`, `**`, `//`, `+=`, `-=`, `*=`, `/=`, `:<`), then single-char.

**RB-5-5-2**
Implement `fn scan_comment(ctx: LexerCtx:mut): none`. Semicolon to end-of-line. Emit `COMMENT` token.

---

## Story 5-6: Error Handling

**RB-5-6-1**
Handle all lexer error cases by returning `result<array<Token>, CompilerError>`:
- Unrecognized character → `LexError`
- Unterminated string literal → `LexError`
- Unterminated f-string → `LexError`
- Malformed hex literal → `LexError`
- Unterminated character literal → `LexError`

---

## Story 5-7: Lexer Tests

**RB-5-7-1**
Write a test program that runs both the Python lexer and ReFlow lexer on a set of inputs and verifies they produce identical token sequences. Test inputs: all keywords, all operators, numeric literals with underscores and suffixes, string escapes, f-strings with nesting, character literals, comments, multiline source.

**RB-5-7-2**
Write negative tests: unterminated string, unrecognized character, malformed hex literal.

---

---

# EPIC 6: Parser

Reimplement `compiler/parser.py` in ReFlow. Pratt precedence climbing parser that produces an AST Module identical to the Python parser's output. This is the largest single module (~2,400 lines in Python) and will expand to approximately 4,000–5,000 lines in ReFlow.

---

## Story 6-1: Parser Infrastructure

**RB-6-1-1** `[BLOCKER]`
Define the `ParserCtx` type:

```
type ParserCtx = {
    tokens: array<Token>
    filename: string
    pos: int:mut
    ids: IdAllocator:mut
}
```

Implement token management:
- `fn peek(ctx: ParserCtx): Token` — skip comments/newlines, return current
- `fn peek2(ctx: ParserCtx): Token` — 2-ahead lookahead
- `fn advance(ctx: ParserCtx:mut): Token` — consume and return
- `fn expect(ctx: ParserCtx:mut, type: TokenType): result<Token, CompilerError>` — consume or error
- `fn check(ctx: ParserCtx, type: TokenType): bool` — test without consuming
- `fn match_token(ctx: ParserCtx:mut, types: array<TokenType>): Token?` — consume if matches any
- `fn skip_comments(ctx: ParserCtx:mut): none`
- `fn skip_newlines(ctx: ParserCtx:mut): none`

**RB-6-1-2**
Implement error recovery: `fn synchronize(ctx: ParserCtx:mut): none`. On parse error, skip tokens until a synchronization point (newline, `}`, EOF, keyword that starts a declaration).

---

## Story 6-2: Top-Level Declarations

**RB-6-2-1** `[BLOCKER]`
Implement `fn parse(tokens: array<Token>, filename: string): result<Module, CompilerError>`. Entry point. Calls `parse_module_decl`, then loops calling `parse_import_decl` and `parse_decl` until EOF.

**RB-6-2-2**
Implement `fn parse_module_decl(ctx: ParserCtx:mut): result<Decl, CompilerError>`. Parses `module path.to.module`.

**RB-6-2-3**
Implement `fn parse_import_decl(ctx: ParserCtx:mut): result<Decl, CompilerError>`. Handles:
- `import path.to.module`
- `import path.to.module (Name1, Name2)`
- `import path.to.module as alias`

**RB-6-2-4**
Implement `fn parse_fn_decl(ctx: ParserCtx:mut): result<Decl, CompilerError>`. Handles:
- Optional `export`, `pure`, `static` modifiers
- Generic type parameters: `fn name<T, U>(...)`
- Parameters with type annotations and mutability
- Return type
- Three body forms: `{ block }`, `= expression`, `= native "c_name"`
- Optional `finally` block

**RB-6-2-5**
Implement `fn parse_type_decl(ctx: ParserCtx:mut): result<Decl, CompilerError>`. Handles:
- Product types: `type Name { field: Type, ... }`
- Sum types: `type Name = | Variant1 | Variant2(field: Type)`
- Methods inside type body
- Constructors inside type body
- Static members
- `fulfills Interface` clause

**RB-6-2-6**
Implement `fn parse_interface_decl(ctx: ParserCtx:mut): result<Decl, CompilerError>` and `fn parse_alias_decl(ctx: ParserCtx:mut): result<Decl, CompilerError>`.

---

## Story 6-3: Type Expression Parsing

**RB-6-3-1**
Implement `fn parse_type_expr(ctx: ParserCtx:mut): result<TypeExpr, CompilerError>`. Entry point for type parsing. Handles:
- Primitive names: `int`, `string`, `bool`, etc.
- Named types: `Vec3`, `math.vector.Vec3`
- Generic types: `option<int>`, `map<string, int>`, `result<T, E>`
- Function types: `fn(int, string): bool`
- Tuple types: `(int, string, bool)`
- Option shorthand: `int?` → `OptionType(NamedType("int"))`
- Mutability: `T:mut`, `T:imut`

---

## Story 6-4: Statement Parsing

**RB-6-4-1**
Implement `fn parse_block(ctx: ParserCtx:mut): result<Block, CompilerError>`. Parses `{ stmt; stmt; ... }`.

**RB-6-4-2**
Implement `fn parse_stmt(ctx: ParserCtx:mut): result<Stmt, CompilerError>`. Dispatcher that checks the current token and routes to the appropriate parser:
- `let` → `parse_let_stmt`
- `return` → `parse_return_stmt`
- `yield` → `parse_yield_stmt`
- `throw` → `parse_throw_stmt`
- `break` → `parse_break_stmt`
- `if` → `parse_if_stmt`
- `while` → `parse_while_stmt`
- `for` → `parse_for_stmt`
- `match` → `parse_match_stmt`
- `try` → `parse_try_stmt`
- Otherwise → expression statement or assignment

**RB-6-4-3**
Implement all individual statement parsers:
- `parse_let_stmt`: `let name: Type = expr`, `let name: Type:mut = expr`
- `parse_if_stmt`: `if condition { ... } else if ... else { ... }`
- `parse_while_stmt`: `while condition { ... } finally { ... }`
- `parse_for_stmt`: `for(var: Type in iterable) { ... } finally { ... }`
- `parse_match_stmt`: `match subject { pattern: body, ... }`
- `parse_try_stmt`: `try { ... } retry fn (ex: Type, attempts: N) { ... } catch (ex: Type) { ... } finally (? ex: Exception) { ... }`
- `parse_return_stmt`, `parse_yield_stmt`, `parse_throw_stmt`, `parse_break_stmt`

**RB-6-4-4**
Handle assignment and update statements. After parsing an expression, check if the next token is `=`, `+=`, `-=`, `*=`, `/=`, `++`, or `--`. If so, parse as assignment or update.

---

## Story 6-5: Expression Parsing (Pratt)

**RB-6-5-1** `[BLOCKER]`
Implement the Pratt precedence climbing parser. Define a precedence table mapping operators to their binding power:

```
Level 1:  -> (composition)
Level 2:  ? : (ternary)
Level 3:  ?? (null coalesce)
Level 4:  || (logical or)
Level 5:  && (logical and)
Level 6:  ==, !=, === (equality)
Level 7:  <, >, <=, >= (comparison)
Level 8:  +, - (additive)
Level 9:  *, /, //, % (multiplicative)
Level 10: ** (power, right-associative)
Level 11: -, !, @ (unary prefix)
Level 12: ?, ., (), [] (postfix)
Level 13: literals, identifiers, grouping (atoms)
```

Implement `fn parse_expr(ctx: ParserCtx:mut): result<Expr, CompilerError>` and `fn parse_expr_bp(ctx: ParserCtx:mut, min_bp: int): result<Expr, CompilerError>`.

**RB-6-5-2**
Implement `fn parse_primary(ctx: ParserCtx:mut): result<Expr, CompilerError>`. Handles:
- Integer, float, string, char, bool literals
- `none` literal
- Identifiers (with optional module path)
- Parenthesized expressions and tuple literals
- Array literals: `[expr, expr, ...]`
- Lambda: `\(params => body)`
- `if` expression
- `match` expression
- `some(expr)`, `ok(expr)`, `err(expr)`
- `@expr` (copy)
- Unary operators: `-expr`, `!expr`

**RB-6-5-3**
Implement infix operator parsing within the Pratt loop:
- Binary operators: `+`, `-`, `*`, `/`, `//`, `%`, `**`, `==`, `!=`, `===`, `<`, `>`, `<=`, `>=`, `&&`, `||`, `??`
- Composition: `->` chains
- Fan-out: `|` and `<:(`

**RB-6-5-4**
Implement postfix operator parsing:
- Function call: `expr(args)`
- Method call: `expr.method(args)`
- Field access: `expr.field`
- Index access: `expr[index]`
- Propagation: `expr?`
- Ternary: `expr ? true_branch : false_branch`

---

## Story 6-6: Pattern Parsing

**RB-6-6-1**
Implement `fn parse_pattern(ctx: ParserCtx:mut): result<Pattern, CompilerError>`. Handles all 9 pattern types:
- `_` → `WildcardPattern`
- Integer/string/bool literal → `LiteralPattern`
- `some(name)` → `SomePattern`
- `none` → `NonePattern`
- `ok(name)` → `OkPattern`
- `err(name)` → `ErrPattern`
- `VariantName` or `VariantName(bindings)` → `VariantPattern`
- `(p1, p2, ...)` → `TuplePattern`
- `name` → `BindPattern`

Implement `fn parse_match_arm(ctx: ParserCtx:mut): result<MatchArm, CompilerError>`.

---

## Story 6-7: Parser Tests

**RB-6-7-1**
Write parity tests: parse the same source with both the Python and ReFlow parsers. Since AST structures differ in representation, serialize both to a canonical JSON-like format and diff. Test all declaration types.

**RB-6-7-2**
Write parity tests for all expression types, focusing on operator precedence edge cases: `a + b * c`, `a -> f -> g`, `x ?? y ?? z`, `a ? b : c ? d : e`.

**RB-6-7-3**
Write negative tests: unexpected token, missing closing brace, missing type annotation where required.

---

---

# EPIC 7: Resolver

Reimplement `compiler/resolver.py` in ReFlow. Scope chain management, symbol table construction, and lambda capture tracking.

---

## Story 7-1: Scope Management

**RB-7-1-1** `[BLOCKER]`
Implement scope chain using a `map<int, Scope>` arena:

```
type ResolverCtx = {
    module: Module
    symbols: map<int, Symbol>:mut
    captures: map<int, array<Symbol>>:mut
    scopes: map<int, Scope>:mut
    current_scope_id: int:mut
    scope_counter: int:mut
    type_member_scopes: map<string, int>:mut
    static_member_scopes: map<string, int>:mut
    imported_modules: map<string, ModuleScope>
    filename: string
}
```

Implement:
- `fn enter_scope(ctx: ResolverCtx:mut, is_function_boundary: bool): none`
- `fn exit_scope(ctx: ResolverCtx:mut): none`
- `fn define(ctx: ResolverCtx:mut, name: string, sym: Symbol): result<none, CompilerError>`
- `fn lookup(ctx: ResolverCtx, name: string): Symbol?` — walks scope chain
- `fn lookup_local(ctx: ResolverCtx, name: string): Symbol?` — current scope only

---

## Story 7-2: Pre-pass and Declaration Registration

**RB-7-2-1** `[BLOCKER]`
Implement `fn pre_pass(ctx: ResolverCtx:mut): result<none, CompilerError>`. First pass over all declarations:
- Register all top-level functions as symbols
- Register all type declarations
- Register all interfaces and aliases
- Build type member scopes (fields + methods) for each type
- Build static member scopes for each type

This pre-pass enables forward references: function A can call function B even if B is defined after A.

**RB-7-2-2**
Implement `fn resolve_imports(ctx: ResolverCtx:mut): result<none, CompilerError>`. For each import:
- Look up in `imported_modules`
- For named imports (`import mod (A, B)`), verify each name exists in the module's exports
- For namespace imports (`import mod`), register the module name in scope
- For aliased imports (`import mod as m`), register the alias

---

## Story 7-3: Name Resolution

**RB-7-3-1** `[BLOCKER]`
Implement `fn resolve_expr(ctx: ResolverCtx:mut, expr: Expr): result<none, CompilerError>`. Pattern-match on all 35 Expr variants. For each `Ident`, look up the name in scope and record the binding in `ctx.symbols`. For `FieldAccess`, check static member scopes. For `Lambda`, set up capture tracking.

**RB-7-3-2**
Implement `fn resolve_stmt(ctx: ResolverCtx:mut, stmt: Stmt): result<none, CompilerError>`. Pattern-match on all Stmt variants. `LetStmt` defines a new binding in the current scope. `ForStmt` enters a new scope with the loop variable. `IfStmt`, `WhileStmt`, `MatchStmt` enter new scopes for their bodies.

**RB-7-3-3**
Implement lambda capture tracking:
- When entering a lambda body, start tracking references to outer variables
- When exiting, record the captured variable list in `ctx.captures` keyed by the lambda's node ID
- Only variables from enclosing function scopes can be captured (not module-level)

**RB-7-3-4**
Implement `fn resolve_decl(ctx: ResolverCtx:mut, decl: Decl): result<none, CompilerError>`. For `FnDecl`: enter scope, define parameters, resolve body, exit scope. For `TypeDecl`: enter type scope, define `self`, resolve method bodies.

---

## Story 7-4: Resolver Entry Point

**RB-7-4-1** `[BLOCKER]`
Implement `fn resolve(module: Module, imported_modules: map<string, ModuleScope>): result<ResolvedModule, CompilerError>`. Full entry point:
1. Create context
2. Pre-pass
3. Resolve imports
4. Resolve all declarations
5. Build module scope (exports)
6. Return `ResolvedModule`

---

## Story 7-5: Resolver Tests

**RB-7-5-1**
Write parity tests: resolve the same source with both compilers. Compare the `symbols` map (key = node ID, value = symbol name + kind). Focus on: forward references, lambda captures, static member access, import visibility.

**RB-7-5-2**
Write negative tests: undefined variable, use of `self` outside method, import of nonexistent module.

---

---

# EPIC 8: Type Checker

Reimplement `compiler/typechecker.py` in ReFlow. This is the most complex module: 1,769 lines in Python, ~28 Type variants, type inference, unification, exhaustiveness checking, purity verification, and stream consumption tracking.

---

## Story 8-1: Type Registry

**RB-8-1-1** `[BLOCKER]`
Define the `TypeCheckerCtx` type:

```
type TypeCheckerCtx = {
    resolved: ResolvedModule
    types: map<int, Type>:mut
    type_registry: map<string, TypeInfo>:mut
    current_return_type: Type:mut
    in_pure_fn: bool:mut
    consumed_streams: set<string>:mut
    purity_map: map<string, bool>:mut
    warnings: buffer<string>:mut
    filename: string
}
```

**RB-8-1-2** `[BLOCKER]`
Implement `fn build_type_registry(ctx: TypeCheckerCtx:mut): result<none, CompilerError>`. Scan all `TypeDecl` nodes, building a `TypeInfo` for each:
- Extract fields and their types
- Extract methods and their function types
- Extract static members
- Extract constructors
- For sum types, build the `TSum` with its `TVariant` entries

**RB-8-1-3**
Implement `fn register_builtins(ctx: TypeCheckerCtx:mut): none`. Register built-in types and their methods: `string.len`, `array.len`, `array.push`, `map.get`, `map.set`, `map.has`, `map.keys`, etc.

---

## Story 8-2: Type Resolution

**RB-8-2-1** `[BLOCKER]`
Implement `fn resolve_type_expr(ctx: TypeCheckerCtx, texpr: TypeExpr): result<Type, CompilerError>`. Converts AST type annotations to internal `Type` values:
- `NamedType("int")` → `TInt(32, true)`
- `NamedType("string")` → `TString`
- `NamedType("Vec3")` → `TNamed("", "Vec3", [])`
- `GenericType(NamedType("option"), [NamedType("int")])` → `TOption(TInt(32, true))`
- `OptionType(inner)` → `TOption(resolve(inner))`
- `FnType(params, ret)` → `TFn(resolve_each(params), resolve(ret), false)`
- `TupleType(elems)` → `TTuple(resolve_each(elems))`
- `MutType(inner)` / `ImutType(inner)` → resolve inner (mutability tracked separately)

**RB-8-2-2**
Implement `fn apply_env(t: Type, env: TypeEnv): Type`. Recursively walks a Type, replacing `TTypeVar(name)` with `env[name]` where present. Must handle all 28 Type variants.

**RB-8-2-3**
Implement `fn unify(t1: Type, t2: Type): result<Type, CompilerError>`. Type unification:
- Same primitive → ok
- `TAny` unifies with anything → returns the other
- `TTypeVar` → bind
- `TOption(a)` with `TOption(b)` → `TOption(unify(a, b))`
- `TArray(a)` with `TArray(b)` → `TArray(unify(a, b))`
- `TFn` → unify params and return type
- Otherwise → `TypeError`

---

## Story 8-3: Expression Type Inference

**RB-8-3-1** `[BLOCKER]`
Implement `fn infer_expr(ctx: TypeCheckerCtx:mut, expr: Expr): result<Type, CompilerError>`. Pattern-match on all 35 Expr variants. Core rules:

- `IntLit(_, _, _, value, none)` → `TInt(32, true)`
- `IntLit(_, _, _, value, some("i64"))` → `TInt(64, true)`
- `FloatLit` → `TFloat(64)` (or 32 with suffix)
- `BoolLit` → `TBool`
- `StringLit` → `TString`
- `NoneLit` → `TOption(TAny)` (resolved from context)
- `Ident` → look up in symbols, return its type
- `BinOp("+", left, right)` → infer both, check compatible, return result type
- `Call(callee, args)` → infer callee, check it's `TFn`, check arity, check param types

**RB-8-3-2**
Implement type inference for compound expressions:
- `IfExpr` → infer both branches, unify
- `MatchExpr` → infer subject, check patterns, infer all arm bodies, unify
- `Lambda` → infer params from annotations or context, infer body
- `TupleExpr` → `TTuple(infer each element)`
- `ArrayLit` → `TArray(unify all elements)`
- `FieldAccess` → look up field on receiver type
- `MethodCall` → look up method on receiver type, apply generic substitution
- `IndexAccess` → check receiver is array/map, return element type

**RB-8-3-3**
Implement type inference for special expressions:
- `SomeExpr(inner)` → `TOption(infer(inner))`
- `OkExpr(inner)` → `TResult(infer(inner), TAny)` (resolved from function return type)
- `ErrExpr(inner)` → `TResult(TAny, infer(inner))`
- `PropagateExpr(inner)` → check inner is `TResult`, return ok type
- `NullCoalesce(left, right)` → check left is `TOption`, unify inner with right
- `TernaryExpr` → check condition is bool, unify branches

---

## Story 8-4: Statement Type Checking

**RB-8-4-1**
Implement `fn check_stmt(ctx: TypeCheckerCtx:mut, stmt: Stmt): result<none, CompilerError>`. Pattern-match on all Stmt variants:
- `LetStmt` → infer value type, check against annotation if present, option auto-lifting
- `AssignStmt` → check target is mutable, check value type matches
- `ReturnStmt` → check value type matches function return type
- `IfStmt` → check condition is bool, check both branches
- `WhileStmt` → check condition is bool
- `ForStmt` → check iterable type, bind loop variable
- `MatchStmt` → check exhaustiveness
- `ExprStmt` → infer type (for side effects)

---

## Story 8-5: Exhaustiveness Checking

**RB-8-5-1** `[BLOCKER]`
Implement exhaustiveness checking for `match` on sum types. Given a sum type with variants `[A, B, C]` and match arms covering `[A, B]`, report `TypeError: match on T is not exhaustive: missing variant 'C'`.

**RB-8-5-2**
Implement exhaustiveness checking for `match` on `option<T>`. Arms must cover both `some(x)` and `none`. If only `some` is covered, report `TypeError: match on option is not exhaustive`.

**RB-8-5-3**
Implement exhaustiveness checking for `match` on `result<T, E>`. Arms must cover both `ok(x)` and `err(e)`.

---

## Story 8-6: Purity and Stream Checking

**RB-8-6-1**
Implement purity checking. When `in_pure_fn` is true:
- Any call to a non-pure function → `TypeError`
- Build a `purity_map` by scanning all function declarations and their `is_pure` flags

**RB-8-6-2**
Implement stream single-consumer checking. Track consumed stream bindings in `consumed_streams`. If a stream variable is used after being consumed, report `TypeError`.

---

## Story 8-7: Auto-Lifting

**RB-8-7-1**
Implement option auto-lifting. In `check_stmt` for `LetStmt`, if the annotation type is `TOption(T)` and the value type is `T` (not `TOption`), wrap the value in `SomeExpr`. Record the wrapping in the types map so lowering can emit `RF_SOME`.

---

## Story 8-8: Type Checker Entry Point and Tests

**RB-8-8-1** `[BLOCKER]`
Implement `fn check(resolved: ResolvedModule): result<TypedModule, CompilerError>`. Full entry point:
1. Build type registry
2. Register builtins
3. Check all function bodies
4. Return `TypedModule`

**RB-8-8-2**
Write parity tests: type-check the same source with both compilers. Compare the `types` map (node ID → type string representation). Focus on: generics, option auto-lifting, method resolution, exhaustiveness.

**RB-8-8-3**
Write negative tests: type mismatch, non-exhaustive match, pure violation, double stream consumption.

---

---

# EPIC 9: Lowering

Reimplement `compiler/lowering.py` in ReFlow. This is the largest module (2,925 lines in Python). It transforms the typed AST into LIR, managing type registries for options, results, tuples, and sum types.

---

## Story 9-1: Type Lowering and Registries

**RB-9-1-1** `[BLOCKER]`
Define the `LowererCtx` type:

```
type LowererCtx = {
    typed: TypedModule
    module_path: string
    filename: string
    type_defs: buffer<LTypeDef>:mut
    fn_defs: buffer<LFnDef>:mut
    static_defs: buffer<LStaticDef>:mut
    option_registry: map<string, string>:mut
    result_registry: map<string, string>:mut
    tuple_registry: map<string, string>:mut
    sum_registry: map<string, string>:mut
    tmp_counter: int:mut
    pending_stmts: buffer<LStmt>:mut
    current_fn_return_type: Type:mut
}
```

**RB-9-1-2** `[BLOCKER]`
Implement `fn lower_type(ctx: LowererCtx:mut, t: Type): LType`. Maps high-level types to LIR types:
- `TInt(w, s)` → `LInt(w, s)`
- `TFloat(w)` → `LFloat(w)`
- `TBool` → `LBool`, `TChar` → `LChar`, `TByte` → `LByte`
- `TString` → `LPtr(LStruct("RF_String"))`
- `TArray(e)` → `LPtr(LStruct("RF_Array"))`
- `TStream(e)` → `LPtr(LStruct("RF_Stream"))`
- `TBuffer(e)` → `LPtr(LStruct("RF_Buffer"))`
- `TMap(k, v)` → `LPtr(LStruct("RF_Map"))`
- `TSet(e)` → `LPtr(LStruct("RF_Set"))`
- `TNone` → `LVoid`
- `TOption(inner)` → `LStruct(register_option_type(ctx, inner))`
- `TResult(ok, err)` → `LStruct(register_result_type(ctx, ok, err))`
- `TTuple(elems)` → `LStruct(register_tuple_type(ctx, elems))`
- `TNamed(mod, name, args)` → `LStruct(mangle(mod, name, none))`
- `TFn(params, ret, _)` → `LFnPtr(lower_each(params), lower(ret))`

**RB-9-1-3**
Implement registry functions:
- `fn register_option_type(ctx: LowererCtx:mut, inner: LType): string` — check if already registered, if not generate struct with `tag` (LByte) and `value` (inner), add to `type_defs`, return C name
- `fn register_result_type(ctx: LowererCtx:mut, ok: LType, err: LType): string` — struct with `tag`, `ok_val`, `err_val`
- `fn register_tuple_type(ctx: LowererCtx:mut, elems: array<LType>): string` — struct with `_0`, `_1`, ... fields

**RB-9-1-4**
Implement `fn fresh_temp(ctx: LowererCtx:mut): string`. Returns `"_rf_tmp_N"` with incrementing counter.

---

## Story 9-2: Declaration Lowering

**RB-9-2-1** `[BLOCKER]`
Implement `fn lower_fn_decl(ctx: LowererCtx:mut, decl: FnDecl): result<none, CompilerError>`. Lowers one function:
1. Mangle the function name
2. Lower parameter types
3. Lower return type
4. Set `current_fn_return_type`
5. Lower the body block
6. Create `LFnDef` and add to `fn_defs`

For native functions: no body to lower. The function is handled at call sites (direct call to native name).

**RB-9-2-2**
Implement `fn lower_type_decl(ctx: LowererCtx:mut, decl: TypeDecl): result<none, CompilerError>`. For product types: create `LTypeDef` with lowered fields. For sum types: create tagged union struct with variant-specific fields. Lower methods as separate `LFnDef` entries with mangled names including the type.

**RB-9-2-3**
Implement `fn lower_static_decl(ctx: LowererCtx:mut, member: StaticMemberDecl, type_name: string): result<none, CompilerError>`. Lower the static member's type and initial value. Create `LStaticDef`.

---

## Story 9-3: Statement Lowering

**RB-9-3-1** `[BLOCKER]`
Implement `fn lower_stmt(ctx: LowererCtx:mut, stmt: Stmt): result<array<LStmt>, CompilerError>`. Pattern-match on all Stmt variants. A single ReFlow statement may produce multiple LIR statements (e.g., checked arithmetic needs temp variables).

**RB-9-3-2**
Implement lowering for each statement type:
- `LetStmt` → `LVarDecl` with option auto-lifting (wrap in `LCompound` with RF_SOME if needed)
- `AssignStmt` → `LAssign`
- `ReturnStmt` → `LReturn`
- `IfStmt` → `LIf` with lowered condition and branches
- `WhileStmt` → `LWhile`
- `ForStmt` → lower to `LWhile` with index variable (for arrays) or stream next loop (for streams)
- `MatchStmt` → `LSwitch` for sum types, nested `LIf` for other match subjects
- `ExprStmt` → `LExprStmt`

**RB-9-3-3**
Implement `fn lower_block(ctx: LowererCtx:mut, block: Block): result<array<LStmt>, CompilerError>`. Lower each statement, collecting pending statements generated during expression lowering.

---

## Story 9-4: Expression Lowering

**RB-9-4-1** `[BLOCKER]`
Implement `fn lower_expr(ctx: LowererCtx:mut, expr: Expr): result<LExpr, CompilerError>`. Pattern-match on all 35 Expr variants. Core cases:

- `IntLit` → `LLit(string value, LInt)`
- `FloatLit` → `LLit(string value, LFloat)`
- `BoolLit` → `LLit("true"/"false", LBool)`
- `StringLit` → `LCall("rf_string_from_cstr", [LLit(escaped, ...)], LPtr(LStruct("RF_String")))`
- `Ident` → `LVar(mangled_name, type)`
- `BinOp` on integers → `LCheckedArith` for `+`, `-`, `*`; explicit div-zero check for `/`, `%`
- `BinOp` on floats → `LBinOp`
- `BinOp` on strings (`+`) → `LCall("rf_string_concat", ...)`
- `Call` → `LCall(mangled_name, lowered_args, return_type)` or `LCall(native_name, ...)` for native functions
- `MethodCall` → `LCall(mangled_method_name, [receiver, ...args], return_type)`
- `FieldAccess` → `LFieldAccess` or `LArrow` depending on pointer vs value
- `Lambda` → closure frame struct + function pointer (advanced — may defer)

**RB-9-4-2**
Implement lowering for compound expressions:
- `IfExpr` → `LTernary` for simple cases, temp variable + `LIf` for blocks
- `MatchExpr` → temp variable + `LSwitch`/`LIf` chain
- `TupleExpr` → `LCompound` with `_0`, `_1`, ... fields
- `ArrayLit` → `LArrayData` + `LCall("rf_array_new", ...)`
- `FStringExpr` → chain of `rf_string_concat` calls with `rf_*_to_string` for non-string parts
- `TypeLit` → `LCompound` with field names and lowered values

**RB-9-4-3**
Implement lowering for option/result operations:
- `SomeExpr` → `LCompound({tag: 1, value: inner})`
- `OkExpr` → `LCompound({tag: 0, ok_val: inner})` using `current_fn_return_type`
- `ErrExpr` → `LCompound({tag: 1, err_val: inner})` using `current_fn_return_type`
- `NoneLit` → `LCompound({tag: 0})` with concrete option type
- `PropagateExpr` → temp var + `LIf(tag == 1, return err, use ok_val)`
- `NullCoalesce` → `LTernary(opt.tag == 1, opt.value, default)`

---

## Story 9-5: Match Lowering

**RB-9-5-1**
Implement match lowering for sum types. Convert `match subject { Variant1(x): ..., Variant2: ..., _ : ... }` to:
```
LSwitch(subject.tag, [
    (0, [LVarDecl(x, subject.Variant1_field), ...body1]),
    (1, [...body2]),
], default_body)
```

**RB-9-5-2**
Implement match lowering for option types. `some(x)` → tag == 1, bind value. `none` → tag == 0.

**RB-9-5-3**
Implement match lowering for result types. `ok(x)` → tag == 0, bind ok_val. `err(e)` → tag == 1, bind err_val.

---

## Story 9-6: Variant Constructor Lowering

**RB-9-6-1**
Implement lowering for variant constructors. When a call like `Circle(5.0)` is resolved to a sum type variant constructor, lower it to a compound literal:
```
LCompound({tag: variant_index, radius: 5.0}, LStruct(mangled_sum_type_name))
```

For unit variants used as identifiers (e.g., `North`), lower to:
```
LCompound({tag: variant_index}, LStruct(mangled_sum_type_name))
```

---

## Story 9-7: Lowerer Entry Point and Tests

**RB-9-7-1** `[BLOCKER]`
Implement `fn lower(typed: TypedModule): result<LModule, CompilerError>`. Full entry point:
1. Create context
2. Lower all type declarations
3. Lower all function declarations
4. Lower all static members
5. Detect entry point (function named `main`)
6. Return `LModule`

**RB-9-7-2**
Write parity tests: lower the same typed module with both compilers. Compare the LModule structure. Focus on: option/result struct generation, name mangling, checked arithmetic, f-string lowering.

---

---

# EPIC 10: C Emitter

Reimplement `compiler/emitter.py` in ReFlow. Pure formatting of LIR to C source string. This module makes no decisions — it is a deterministic, line-by-line translation.

---

## Story 10-1: Output Infrastructure

**RB-10-1-1** `[BLOCKER]`
Define the `EmitterCtx` type:

```
type EmitterCtx = {
    module: LModule
    source_file: string
    out: buffer<string>:mut
    indent_level: int:mut
    tmp_counter: int:mut
    deferred_static_inits: buffer<(string, string)>:mut
}
```

Implement helpers:
- `fn emit(ctx: EmitterCtx:mut, s: string): none` — append raw text
- `fn emitln(ctx: EmitterCtx:mut, s: string): none` — append indented line with newline
- `fn indent(ctx: EmitterCtx:mut): none` — increase indent level
- `fn dedent(ctx: EmitterCtx:mut): none` — decrease indent level
- `fn fresh_temp(ctx: EmitterCtx:mut): string` — `"_rf_e_N"` counter
- `fn indent_str(ctx: EmitterCtx): string` — return current indent as spaces

---

## Story 10-2: Type and Expression Formatting

**RB-10-2-1** `[BLOCKER]`
Implement `fn format_type(t: LType): string`. Maps LIR types to C type strings:
- `LInt(32, true)` → `"rf_int"`
- `LFloat(64)` → `"rf_float"`
- `LBool` → `"rf_bool"`
- `LPtr(inner)` → `format_type(inner) + "*"`
- `LStruct(name)` → name
- `LVoid` → `"void"`
- `LFnPtr(params, ret)` → function pointer syntax

**RB-10-2-2** `[BLOCKER]`
Implement `fn format_expr(expr: LExpr): string`. Pattern-match on all 17 LExpr variants:
- `LLit(v, _)` → `v`
- `LVar(name, _)` → `name`
- `LCall(fn, args, _)` → `"fn(arg1, arg2, ...)"`
- `LBinOp(op, l, r, _)` → `"(l op r)"`
- `LFieldAccess(obj, field, _)` → `"obj.field"`
- `LArrow(ptr, field, _)` → `"ptr->field"`
- `LCast(inner, t)` → `"((type)inner)"`
- `LCompound(fields, t)` → `"(type){.f1 = v1, .f2 = v2}"`
- `LCheckedArith(op, l, r, t)` → emit temp var + `RF_CHECKED_ADD/SUB/MUL` macro call
- `LTernary(c, t, f, _)` → `"(c ? t : f)"`

---

## Story 10-3: Statement Formatting

**RB-10-3-1** `[BLOCKER]`
Implement `fn emit_stmt(ctx: EmitterCtx:mut, stmt: LStmt): none`. Pattern-match on all 11 LStmt variants:
- `LVarDecl(name, type, init)` → `"type name = init;"` or `"type name;"`
- `LAssign(target, value)` → `"target = value;"`
- `LReturn(value)` → `"return value;"` or `"return;"`
- `LIf(cond, then, else)` → `"if (cond) { ... } else { ... }"`
- `LWhile(cond, body)` → `"while (cond) { ... }"`
- `LSwitch(value, cases, default)` → `"switch (value) { case N: ... break; }"`
- `LGoto(label)` → `"goto label;"`
- `LLabel(name)` → `"name:"`
- `LBreak` → `"break;"`
- `LExprStmt(expr)` → `"expr;"`

---

## Story 10-4: Top-Level Emission

**RB-10-4-1** `[BLOCKER]`
Implement `fn emit_module(module: LModule, source_file: string): string`. Full emission:
1. Emit header comment with source file name
2. Emit `#include "reflow_runtime.h"`
3. Emit forward declarations for all structs
4. Emit forward declarations for all functions
5. Emit type definitions (struct bodies)
6. Emit static definitions (with deferred string inits)
7. Emit function definitions
8. Emit `_rf_init_statics()` if any deferred inits exist
9. Emit `main()` wrapper if entry point exists

**RB-10-4-2**
Handle deferred static initialization for string fields:
- If a static is `RF_String*` type with an init, declare as `NULL` and defer init to `_rf_init_statics()`
- `_rf_init_statics()` is called from `main()` before the entry point function

---

## Story 10-5: Emitter Tests

**RB-10-5-1** `[BLOCKER]`
Golden file parity test: for each test program in `tests/programs/`, run both the Python and ReFlow emitters and diff the C output after normalization (see Parity Testing Strategy). This is the critical acceptance test for the entire bootstrap.

**RB-10-5-2**
Test edge cases: empty function body, deeply nested if/else, large switch statement, many temp variables, string literal with special characters.

---

---

# EPIC 11: Driver & CLI

Reimplement `compiler/driver.py` and `main.py` in ReFlow. Pipeline orchestration, stdlib module loading, temporary file management, and clang invocation.

---

## Story 11-1: Pipeline Orchestration

**RB-11-1-1** `[BLOCKER]`
Implement `fn run_pipeline(source_path: string): result<(string, TypedModule), CompilerError>` in `self_hosted/driver.reflow`. Steps:
1. `io.read_file(source_path)` → get source string
2. Compute display path
3. Lex: `lexer.tokenize(source, display_path)`
4. Parse: `parser.parse(tokens, display_path)`
5. Discover and load stdlib imports
6. Resolve: `resolver.resolve(module, imported_modules)`
7. Type check: `typechecker.check(resolved)`
8. Return `(display_path, typed_module)`

**RB-11-1-2**
Implement `fn discover_imports(module: Module): map<string, ModuleScope>`. For each import in the module:
- Check if it's a known stdlib module (`io`, `sys`, `conv`, `string`, `char`, `path`)
- If so, load and resolve the stdlib module file
- Return the map of module scopes

**RB-11-1-3**
Implement `fn load_stdlib_module(module_name: string): result<ModuleScope, CompilerError>`. Locates the stdlib `.reflow` file relative to the compiler binary, reads it, lexes, parses, and resolves it.

---

## Story 11-2: Build Commands

**RB-11-2-1** `[BLOCKER]`
Implement `fn compile_source(source_path: string, output: string?, verbose: bool): int`:
1. Run pipeline
2. Lower: `lowering.lower(typed)`
3. Emit: `emitter.emit_module(lmodule, display_path)`
4. Write C to temp file: `io.tmpfile_create(".c", c_source)`
5. Determine output path (default: source stem)
6. Locate runtime `.c` and include dir
7. Call clang: `sys.run_process("clang", ["-std=c11", "-Wall", "-Wextra", "-o", output, temp, runtime_c, "-I", runtime_include])`
8. Clean up temp file
9. Return exit code

**RB-11-2-2**
Implement `fn emit_only(source_path: string, output: string?, verbose: bool): int`:
1. Run pipeline
2. Lower
3. Emit
4. If output is specified, write to file; otherwise write to stdout
5. Return 0

**RB-11-2-3**
Implement `fn check_only(source_path: string, verbose: bool): int`:
1. Run pipeline (through type checking)
2. Return 0 on success

---

## Story 11-3: CLI Entry Point

**RB-11-3-1** `[BLOCKER]`
Implement `fn main(): none` in `self_hosted/main.reflow`:
1. Parse command-line arguments: `sys.args()`
2. Dispatch to `compile_source`, `emit_only`, or `check_only` based on subcommand
3. Catch `CompilerError`, format with `format_error`, print to stderr, exit 1

The CLI accepts:
- `reflowc build <file>` — compile to binary
- `reflowc emit-c <file>` — emit C only
- `reflowc check <file>` — type check only
- `--output <path>` — output path for build/emit-c
- `--verbose` — print generated C to stderr

**RB-11-3-2**
Implement argument parsing without a library. Walk `sys.args()`, match on known subcommands and flags. Unknown flags → print usage and exit 1.

---

## Story 11-4: Driver Tests

**RB-11-4-1**
Test `compile_source` on `hello.reflow` — verify it produces a working binary.

**RB-11-4-2**
Test `emit_only` on `hello.reflow` — verify the C output matches the Python compiler's output.

**RB-11-4-3**
Test `check_only` on valid and invalid programs — verify exit codes.

---

---

# EPIC 12: Integration Testing

Systematic verification that the self-hosted compiler produces identical output to the Python compiler on every test program.

---

## Story 12-1: Golden File Parity

**RB-12-1-1** `[BLOCKER]`
Run `verify_parity.py` on all programs in `tests/programs/`. For each one:
- Python compiler emits C to stdout
- ReFlow compiler emits C to stdout
- Both outputs are passed through the normalizer (see Parity Testing Strategy above)
- Normalized diff must be empty

Fix any discrepancies found. Common sources of divergence:
- Mangled name differences (real bug — fix immediately)
- Struct field order differences (real bug — fix immediately)
- Forward declaration order differences (real bug — match Python's order)
- Missing or extra type definitions (real bug — registry logic mismatch)

Temp variable numbering differences are tolerated by the normalizer and are not bugs.

**RB-12-1-2**
Run parity on all 15 example programs in `examples/`. These are more complex than test programs and exercise more language features.

---

## Story 12-2: End-to-End Execution Parity

**RB-12-2-1** `[BLOCKER]`
For each test program with an `expected_stdout` file:
1. Compile with the Python compiler → run → capture stdout
2. Compile with the ReFlow compiler → run → capture stdout
3. Diff must be empty (stdout is not normalized — it must match exactly)

**RB-12-2-2**
For each negative test program in `tests/programs/errors/`:
1. Run through the Python compiler → capture error
2. Run through the ReFlow compiler → capture error
3. Error type and message prefix must match

---

## Story 12-3: Compiler Feature Coverage

**RB-12-3-1**
Create a test program that uses every language feature the self-hosted compiler uses:
- Sum types with payload and unit variants
- Recursive sum types (Expr containing Expr fields)
- Pattern matching on sum types, options, results
- Maps, arrays, buffers, sets
- F-strings
- Mutable local variables
- Generics
- Multi-file module imports
- Static members
- Native function calls
- Recursive functions

Compile and run with both compilers. Verify identical output.

**RB-12-3-2**
Create a stress test: a ReFlow program with 100+ functions, deeply nested match expressions, large sum types. Verify the ReFlow compiler handles it without stack overflow or performance degradation.

---

## Story 12-4: Debugging Infrastructure

**RB-12-4-1**
Before proceeding to EPIC 13, confirm that the self-hosted compiler supports all three CLI subcommands:
- `reflowc build <file>` — produces a binary
- `reflowc emit-c <file>` — emits C source to stdout (critical for debugging)
- `reflowc check <file>` — type checks only (critical for narrowing bugs to a specific pass)

These are implemented in EPIC 11 (RB-11-2-1, RB-11-2-2, RB-11-2-3). This ticket verifies they work correctly on the self-hosted compiler's own source files.

**RB-12-4-2**
Document the debugging workflow for stage 2/3 failures in `self_hosted/DEBUGGING.md`:
1. Run `reflowc emit-c <failing_file>` and `python main.py emit-c <failing_file>` — diff the C output to find structural divergence.
2. Run `reflowc check <failing_file>` to verify the type checker agrees. If it disagrees, the bug is in the type checker.
3. If the C output differs, use the normalized diff to identify which function, struct, or expression diverges.
4. Bisect: comment out half the functions in the failing module and recompile to narrow the scope.
5. If the C is identical but the binary behaves differently: the bug is in the C runtime, not the compiler. Build both with `-g` and compare in a debugger.

---

---

# EPIC 13: Bootstrap Verification

The final milestone. Compile the ReFlow compiler with itself and verify the output is stable.

---

## Story 13-1: Stage 2 — Python Compiles ReFlow Compiler

**RB-13-1-1** `[BLOCKER]`
Compile the self-hosted compiler using the Python compiler:
```
python main.py build self_hosted/main.reflow -o reflowc_stage2
```

This produces the first self-hosted binary. It must:
- Compile without errors
- Pass `reflowc_stage2 check` on all test programs
- Produce identical C output to the Python compiler on all test programs

---

## Story 13-2: Stage 3 — Self-Hosted Compiler Compiles Itself

**RB-13-2-1** `[BLOCKER]`
Compile the self-hosted compiler using `reflowc_stage2`:
```
./reflowc_stage2 build self_hosted/main.reflow -o reflowc_stage3
```

This is the bootstrap test. `reflowc_stage3` must:
- Compile without errors
- Produce identical C output to `reflowc_stage2` on all test programs

**RB-13-2-2** `[BLOCKER]`
Verify output stability: run both `reflowc_stage2` and `reflowc_stage3` on all test programs and diff the C output. Note: for stage 2 vs stage 3 comparison, the diff **must** be byte-for-byte identical (no normalization). Both compilers are the same source code compiled by different binaries — if the output differs at all, there is a determinism bug in the compiler that produces different code depending on how it was compiled. This is the strictest test in the entire bootstrap.

---

## Story 13-3: Full Test Suite with Stage 2

**RB-13-3-1**
Run the complete test suite (`make test`) using `reflowc_stage2` as the compiler instead of the Python compiler. All tests must pass:
- Golden file tests: C output matches expected
- E2E tests: compiled programs produce correct stdout
- Negative tests: invalid programs produce correct error messages
- Unit tests: N/A (these test Python code, not the binary)

**RB-13-3-2**
Run the E2E test suite using `reflowc_stage3` as the compiler. All tests must pass identically to stage 2.

---

## Story 13-4: Archive and Declare Victory

**RB-13-4-1**
Move the Python compiler source to `bootstrap/python/`:
```
bootstrap/
  python/
    compiler/
    main.py
    requirements.txt
```

Update `README.md` to reflect that the canonical compiler is now `reflowc` (the self-hosted binary). The Python compiler is preserved for historical bootstrapping but is no longer maintained.

**RB-13-4-2**
Add `make bootstrap` target to the Makefile that performs the full bootstrap verification:
1. Build stage 2 from Python
2. Build stage 3 from stage 2
3. Verify stage 2 and stage 3 produce identical output
4. Run full test suite with stage 2

**RB-13-4-3**
Update `CLAUDE.md` to reflect the new project state: the compiler is self-hosted, the Python source is archived, and all future development happens in ReFlow.

---

---

# Dependency Map

```
EPIC 0 (Python Compiler Prerequisites)
  └─ must complete before all other epics
  └─ RB-0-0-1 (multi-file compilation) gates every epic that writes .reflow code
  └─ RB-0-1-1 (recursive sum types) gates EPIC 3 (Core Data Types)

EPIC 1 (Standard Library Extensions)
  └─ must complete before EPIC 5 (Lexer) and EPIC 11 (Driver)

EPIC 2 (Language Freeze & Setup)
  └─ must complete before EPIC 3 (Data Types)

EPIC 3 (Core Data Types)
  └─ must complete before EPIC 4 (Mangler), EPIC 5 (Lexer), EPIC 6 (Parser)

EPIC 4 (Name Mangler)
  └─ must complete before EPIC 9 (Lowering)

EPIC 5 (Lexer)
  └─ must complete before EPIC 6 (Parser)

EPIC 6 (Parser)
  └─ must complete before EPIC 7 (Resolver)

EPIC 7 (Resolver)
  └─ must complete before EPIC 8 (Type Checker)

EPIC 8 (Type Checker)
  └─ must complete before EPIC 9 (Lowering)

EPIC 9 (Lowering)
  └─ must complete before EPIC 10 (Emitter)

EPIC 10 (C Emitter)
  └─ must complete before EPIC 11 (Driver)

EPIC 11 (Driver & CLI)
  └─ must complete before EPIC 12 (Integration Testing)

EPIC 12 (Integration Testing)
  └─ must complete before EPIC 13 (Bootstrap Verification)

EPIC 13 (Bootstrap Verification)
  └─ final milestone
```

### Parallelism Opportunities

- EPIC 1 (stdlib) and EPIC 2 (freeze) can proceed in parallel (both depend only on EPIC 0).
- EPIC 4 (mangler) can proceed in parallel with EPICs 5–6 (lexer/parser), since it has no dependency on them.
- Within EPIC 3, all story groups (tokens, AST, types, LIR, symbols) are independent and can be written in parallel.

---

# Estimated Ticket Counts

| Epic | Stories | Tickets |
|------|---------|---------|
| 0: Python Compiler Prerequisites | 2 | 6 |
| 1: Standard Library Extensions | 7 | 24 |
| 2: Language Freeze & Setup | 2 | 6 |
| 3: Core Data Types | 7 | 18 |
| 4: Name Mangler | 2 | 5 |
| 5: Lexer | 7 | 14 |
| 6: Parser | 7 | 21 |
| 7: Resolver | 5 | 10 |
| 8: Type Checker | 8 | 19 |
| 9: Lowering | 7 | 19 |
| 10: C Emitter | 5 | 8 |
| 11: Driver & CLI | 4 | 11 |
| 12: Integration Testing | 4 | 8 |
| 13: Bootstrap Verification | 4 | 8 |
| **Total** | **71** | **177** |

---

# Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Feature subset insufficient | High — compiler needs a feature it can't compile | Freeze feature list early (RB-2-1-1). Write compiler code that uses only frozen features. |
| C output diverges on temp variables | Low — cosmetic difference | Use normalized parity (see Parity Testing Strategy). Only structural differences are bugs. |
| Recursive sum types produce invalid C | High — blocks all AST definitions | Validate in EPIC 0 (RB-0-1-1). Fix the Python emitter before writing any self-hosted code. |
| Multi-file compilation breaks | High — blocks entire bootstrap | Validate in EPIC 0 (RB-0-0-1). Test with a 2-module program before attempting 14 modules. |
| Circular module dependency | High — self-hosted compiler can't import its own modules | Compiler modules form a DAG. Enforce no circular imports in project structure. |
| Missing stdlib function discovered late | Medium — blocks progress | Audit all Python stdlib usage (dict, list, str methods, pathlib, subprocess, tempfile) during EPIC 1 and add ReFlow equivalents before writing compiler code. |
| Type checker too complex | Medium — most bug-prone module | Implement incrementally with parity tests at each step. The Python compiler serves as oracle. |
| Debugging stage 2 failures | Medium — hard to diagnose without tools | The self-hosted compiler implements `--emit-c` and `--check` (EPIC 11). Use these to inspect intermediate output and narrow bugs to specific pipeline stages. |
| Performance — ReFlow compiler slower than Python | Low — only matters for bootstrap | Acceptable for bootstrap. Optimize after the compiler is self-hosted. |
