# ReFlow Compiler: Full Build Plan

## Overview

This document is a complete task-level plan for building a reference compiler for the ReFlow language. The compiler is written in Python, emits C, and is designed to eventually compile itself (bootstrap). Tasks are organized into Epics, each broken into Stories, each broken into discrete implementable Tickets.

The compiler pipeline is:

```
ReFlow source (.reflow)
  → Lexer       (tokens)
  → Parser      (CST)
  → AST Builder (typed AST nodes)
  → Resolver    (name/scope resolution)
  → Type Checker (inference, constraints, purity, exhaustiveness)
  → Lowering    (AST → explicit IR)
  → C Emitter   (IR → .c files)
  → Driver      (shells out to clang)
```

The runtime is a handwritten C library (`reflow_runtime.h` / `reflow_runtime.c`) that all generated programs link against.

---

## Conventions for This Document

- **Epic**: A major phase of the compiler.
- **Story**: A coherent unit of work within an epic.
- **Ticket**: A single implementable task. Each ticket has a clear definition of done.
- Tickets are numbered `EPIC-STORY-TICKET`, e.g., `RT-1-1` is Runtime, Story 1, Ticket 1.
- Tickets marked `[BLOCKER]` must be complete before the next Epic can begin.

---

---

# EPIC 0: Project Scaffolding

Establish the repository structure, tooling, and conventions before writing any compiler code.

---

## Story 0-1: Repository Layout

**RT-0-1-1** `[BLOCKER]`
Create the top-level repository with the following directory structure:

```
reflow/
  compiler/
    __init__.py
    lexer.py
    parser.py
    ast_nodes.py
    resolver.py
    typechecker.py
    lowering.py
    emitter.py
    driver.py
    errors.py
    mangler.py
  runtime/
    reflow_runtime.h
    reflow_runtime.c
  tests/
    programs/          ; .reflow source files used as test inputs
    expected/          ; expected .c output or expected stdout for each test
    run_tests.py
  grammar/
    reflow.lark
  examples/
    hello.reflow
    fibonacci.reflow
    pipeline.reflow
  main.py              ; CLI entry point
  README.md
```

**RT-0-1-2**
Create `main.py` as the CLI entry point. It should accept:
- `reflow build <file.reflow>` — compile to binary via clang
- `reflow emit-c <file.reflow>` — emit C only, do not compile
- `reflow check <file.reflow>` — type check only, no output
- `--output <path>` flag for the output binary path
- `--verbose` flag that prints the generated C before compiling

**RT-0-1-3**
Create `compiler/errors.py`. Define a base `ReFlowError` dataclass with fields: `message: str`, `file: str`, `line: int`, `col: int`. Define subclasses: `LexError`, `ParseError`, `ResolveError`, `TypeError`, `EmitError`. All compiler errors must use these types. The driver catches them and prints formatted error messages before exiting with code 1.

---

## Story 0-2: Test Infrastructure

**RT-0-2-1** `[BLOCKER]`
Create `tests/run_tests.py`. It discovers all `.reflow` files under `tests/programs/`, compiles each with `reflow emit-c`, and diffs the output against the corresponding file in `tests/expected/`. A test passes if the diff is empty. If no expected file exists, the test is marked as "new" and the generated output is written as the new expected file (golden file pattern). Exit code 0 means all tests pass.

**RT-0-2-2**
Create a `tests/programs/hello.reflow` with a single `pure fn add(x: int, y: int): int = x + y` function. Create its expected C output. This is the canary test that runs throughout all subsequent development.

**RT-0-2-3**
Add a `Makefile` with targets:
- `make test` — runs `tests/run_tests.py`
- `make check` — runs mypy on the compiler source
- `make clean` — removes all generated `.c` and binary files

---

## Story 0-3: Name Mangling

**RT-0-3-1** `[BLOCKER]`
Create `compiler/mangler.py`. Implement `mangle(module: str, type_name: str | None, fn_name: str | None) -> str`. Rules:
- All output identifiers are prefixed with `rf_`
- Dots in module paths become underscores: `math.vector` → `rf_math_vector`
- Type names follow the module: `math.vector.Vec3` → `rf_math_vector_Vec3`
- Methods follow the type: `math.vector.Vec3.dot` → `rf_math_vector_Vec3_dot`
- Top-level functions: `pipeline.orders.run` → `rf_pipeline_orders_run`
- Built-in types are not mangled: `int`, `float`, `bool` etc. map to C types directly

**RT-0-3-2**
Write unit tests for the mangler covering: module-only names, module+type, module+type+method, top-level functions, names with multiple path components, and reserved C identifiers (e.g., a function named `return` should produce a compile error, not silently mangle to a keyword).

---

---

# EPIC 1: Runtime Library

The runtime is a handwritten C header and implementation file that all generated ReFlow programs link against. It must be complete enough to support the type system before the emitter is written.

---

## Story 1-1: Value Type Foundations

**RT-1-1-1** `[BLOCKER]`
In `reflow_runtime.h`, define C type aliases for all ReFlow value types:

```c
#include <stdint.h>
#include <stdbool.h>

typedef int16_t  rf_int16;
typedef int32_t  rf_int;
typedef int32_t  rf_int32;
typedef int64_t  rf_int64;
typedef uint8_t  rf_byte;
typedef uint16_t rf_uint16;
typedef uint32_t rf_uint;
typedef uint32_t rf_uint32;
typedef uint64_t rf_uint64;
typedef float    rf_float32;
typedef double   rf_float;
typedef double   rf_float64;
typedef bool     rf_bool;
typedef uint32_t rf_char;   /* Unicode scalar value */
```

**RT-1-1-2**
Define overflow-checked arithmetic macros for `rf_int` (and variants). Each macro takes two operands and a result pointer. On overflow, they call `rf_panic_overflow()`. Use GCC/Clang `__builtin_add_overflow`, `__builtin_sub_overflow`, `__builtin_mul_overflow`.

```c
#define RF_CHECKED_ADD(a, b, result) \
    do { if (__builtin_add_overflow((a), (b), (result))) rf_panic_overflow(); } while(0)
```

Implement for: add, sub, mul for `rf_int`, `rf_int64`, `rf_uint`, `rf_uint64`.

**RT-1-1-3**
Implement `rf_panic_overflow()`, `rf_panic_divzero()`, `rf_panic_oob()` (out of bounds), and `rf_panic(const char* msg)` in `reflow_runtime.c`. Each prints a formatted message to stderr and calls `exit(1)`. These are the runtime error handlers for the conditions defined in the spec.

---

## Story 1-2: String Representation

**RT-1-2-1** `[BLOCKER]`
Define the string struct and reference counting functions:

```c
typedef struct RF_String {
    rf_int64  refcount;
    rf_int64  len;       /* byte length, not char count */
    char      data[];    /* flexible array member, UTF-8 */
} RF_String;

RF_String* rf_string_new(const char* data, rf_int64 len);
RF_String* rf_string_from_cstr(const char* cstr);
void       rf_string_retain(RF_String* s);
void       rf_string_release(RF_String* s);  /* frees when refcount hits 0 */
RF_String* rf_string_concat(RF_String* a, RF_String* b);
rf_bool    rf_string_eq(RF_String* a, RF_String* b);
rf_int64   rf_string_len(RF_String* s);      /* byte length */
rf_int     rf_string_cmp(RF_String* a, RF_String* b);
```

String literals in generated C use `rf_string_from_cstr("literal")`. The macro `RF_STR("literal")` should expand to a stack-allocated string for constant contexts.

**RT-1-2-2**
Implement `rf_string_new`, `rf_string_from_cstr`, `rf_string_retain`, `rf_string_release`, `rf_string_concat`, `rf_string_eq`, `rf_string_len`, `rf_string_cmp` in `reflow_runtime.c`. The refcount starts at 1 on allocation. `rf_string_release` decrements and frees at 0 using `free()`.

**RT-1-2-3**
Implement string-to-numeric conversions: `rf_string_to_int(RF_String* s, rf_int* out) -> rf_bool` (returns false on parse failure) and corresponding functions for `rf_int64`, `rf_float`. Also implement numeric-to-string: `rf_int_to_string(rf_int v) -> RF_String*` and equivalents for other numeric types.

---

## Story 1-3: Option and Result Types

**RT-1-3-1** `[BLOCKER]`
For each value type, the generated code needs an option struct. Define a macro that generates them:

```c
#define RF_OPTION_TYPE(T, name) \
    typedef struct { rf_byte tag; T value; } name;

RF_OPTION_TYPE(rf_int,    RF_Option_int)
RF_OPTION_TYPE(rf_int64,  RF_Option_int64)
RF_OPTION_TYPE(rf_float,  RF_Option_float)
RF_OPTION_TYPE(rf_bool,   RF_Option_bool)
/* etc. for all value types */

/* For heap types (strings, structs): */
typedef struct { rf_byte tag; void* value; } RF_Option_ptr;
```

Tag values: `0 = none`, `1 = some`.

Define `RF_NONE` (tag=0) and `RF_SOME(v)` (tag=1, value=v) constructors as macros.

**RT-1-3-2**
Define result types using the same macro pattern. Tag values: `0 = ok`, `1 = err`. The emitter will generate specific result struct typedefs per (T, E) combination encountered in the program. Define the macro and instantiate for `(rf_int, RF_String*)` and `(void*, void*)` as baseline examples.

**RT-1-3-3**
Define `rf_option_unwrap_or(opt, default)` and `rf_result_is_ok(res)`, `rf_result_is_err(res)` as macros for use in generated code.

---

## Story 1-4: Array Representation

**RT-1-4-1**
Define the array struct:

```c
typedef struct RF_Array {
    rf_int64  refcount;
    rf_int64  len;
    void*     data;    /* pointer to element storage */
    rf_int64  element_size;
} RF_Array;

RF_Array* rf_array_new(rf_int64 len, rf_int64 element_size, void* initial_data);
void      rf_array_retain(RF_Array* arr);
void      rf_array_release(RF_Array* arr);
void*     rf_array_get_ptr(RF_Array* arr, rf_int64 idx); /* panics on OOB */
RF_Option_ptr rf_array_get_safe(RF_Array* arr, rf_int64 idx);
rf_int64  rf_array_len(RF_Array* arr);
RF_Array* rf_array_push(RF_Array* arr, void* element); /* returns new array */
```

Arrays are immutable. `rf_array_push` returns a new array. OOB access panics.

**RT-1-4-2**
Implement all array functions in `reflow_runtime.c`. `rf_array_new` allocates contiguous storage and copies `initial_data` into it if non-null. `rf_array_get_ptr` does bounds checking and calls `rf_panic_oob()` on failure.

---

## Story 1-5: Stream Representation

**RT-1-5-1** `[BLOCKER]`
Streams are state machines. Define the stream struct:

```c
typedef struct RF_Stream RF_Stream;

typedef RF_Option_ptr (*RF_StreamNext)(RF_Stream* self);
typedef void          (*RF_StreamFree)(RF_Stream* self);

struct RF_Stream {
    RF_StreamNext next_fn;    /* returns some(element) or none on exhaustion */
    RF_StreamFree free_fn;    /* cleanup when stream is abandoned */
    void*         state;      /* pointer to the frame struct for this stream */
    rf_int        refcount;
};

RF_Stream* rf_stream_new(RF_StreamNext next_fn, RF_StreamFree free_fn, void* state);
void       rf_stream_retain(RF_Stream* s);
void       rf_stream_release(RF_Stream* s);
RF_Option_ptr rf_stream_next(RF_Stream* s); /* calls next_fn */
```

Each streaming ReFlow function compiles to: a frame struct holding all locals, a `next` function that takes the frame and returns `RF_Option_ptr`, and a `free` function that releases frame resources.

**RT-1-5-2**
Implement `rf_stream_new`, `rf_stream_retain`, `rf_stream_release`, `rf_stream_next` in `reflow_runtime.c`. When `rf_stream_release` drops the refcount to 0, it calls `free_fn(self)` then `free(self)`.

---

## Story 1-6: Map and Set Stubs

**RT-1-6-1**
Define `RF_Map` as a struct with a void* to an internal hash table implementation. Provide:

```c
RF_Map* rf_map_new(void);
RF_Map* rf_map_set(RF_Map* m, void* key, rf_int64 key_len, void* val);
RF_Option_ptr rf_map_get(RF_Map* m, void* key, rf_int64 key_len);
rf_bool rf_map_has(RF_Map* m, void* key, rf_int64 key_len);
rf_int64 rf_map_len(RF_Map* m);
void    rf_map_retain(RF_Map* m);
void    rf_map_release(RF_Map* m);
```

A simple open-addressing hash table with string keys is sufficient for the bootstrap phase. Mark the file with `/* BOOTSTRAP: replace with production hash map */`.

**RT-1-6-2**
Define `RF_Set` similarly. `rf_set_new`, `rf_set_add`, `rf_set_has`, `rf_set_remove`, `rf_set_len`, `rf_set_retain`, `rf_set_release`. Backed by the same hash table as RF_Map with unit values.

---

## Story 1-7: Buffer Representation

**RT-1-7-1**
Define:

```c
typedef struct {
    rf_int64 refcount;
    rf_int64 len;
    rf_int64 capacity;
    rf_int64 element_size;
    void*    data;
} RF_Buffer;

RF_Buffer* rf_buffer_new(rf_int64 element_size);
RF_Buffer* rf_buffer_with_capacity(rf_int64 cap, rf_int64 element_size);
RF_Buffer* rf_buffer_collect(RF_Stream* s, rf_int64 element_size);
void       rf_buffer_push(RF_Buffer* buf, void* element);
RF_Option_ptr rf_buffer_get(RF_Buffer* buf, rf_int64 idx);
RF_Stream* rf_buffer_drain(RF_Buffer* buf);  /* consumes buf */
rf_int64   rf_buffer_len(RF_Buffer* buf);
void       rf_buffer_sort_by(RF_Buffer* buf, int (*cmp)(void*, void*));
void       rf_buffer_reverse(RF_Buffer* buf);
void       rf_buffer_retain(RF_Buffer* buf);
void       rf_buffer_release(RF_Buffer* buf);
```

`rf_buffer_collect` pulls from a stream until exhaustion, growing the buffer as needed. If memory allocation fails, calls `rf_panic("BufferOverflowError")`.

**RT-1-7-2**
Implement all buffer functions in `reflow_runtime.c`. Use `realloc` for growth with a 2× growth factor. Implement `rf_buffer_drain` by creating a stream whose state is the buffer and whose `next` function walks the index.

---

## Story 1-8: I/O Primitives

**RT-1-8-1**
Define I/O functions:

```c
void       rf_print(RF_String* s);
void       rf_println(RF_String* s);
void       rf_eprint(RF_String* s);
void       rf_eprintln(RF_String* s);
RF_Stream* rf_stdin_stream(void);      /* stream<byte> from stdin */
RF_Option_ptr rf_read_line(void);     /* reads one line, returns Option<RF_String*> */
```

**RT-1-8-2**
Implement all I/O functions. `rf_stdin_stream` returns a stream whose `next` function reads one byte from stdin and returns it as `some(byte)` or `none` on EOF. `rf_read_line` reads until `\n` or EOF, returning a heap-allocated `RF_String*` wrapped in `some`, or `none` on EOF.

---

---

# EPIC 2: Lexer

The lexer takes a ReFlow source file as a string and produces a flat list of typed tokens. It is hand-rolled (no external lexer library).

---

## Story 2-1: Token Types

**RT-2-1-1** `[BLOCKER]`
In `compiler/lexer.py`, define a `TokenType` enum covering all ReFlow tokens:

Keywords: `MODULE`, `IMPORT`, `EXPORT`, `AS`, `ALIAS`, `TYPE`, `TYPEOF`, `MUT`, `IMUT`, `LET`, `FN`, `RETURN`, `YIELD`, `TRY`, `RETRY`, `CATCH`, `FINALLY`, `INTERFACE`, `FULFILLS`, `CONSTRUCTOR`, `SELF`, `FOR`, `IN`, `WHILE`, `IF`, `ELSE`, `MATCH`, `NONE`, `BREAK`, `STATIC`, `PURE`, `RECORD`, `SOME`, `OK`, `ERR`, `COERCE`, `CAST`, `SNAPSHOT`, `THROW`

Operators: `ARROW` (`->`), `FAT_ARROW` (`=>`), `PARALLEL_FANOUT` (`<:(`), `PIPE` (`|`), `QUESTION` (`?`), `DOUBLE_QUESTION` (`??`), `QUESTION_COLON` (`?:`), `TRIPLE_EQ` (`===`), `DOUBLE_EQ` (`==`), `ASSIGN` (`=`), `PLUS_ASSIGN` (`+=`), `MINUS_ASSIGN` (`-=`), `STAR_ASSIGN` (`*=`), `SLASH_ASSIGN` (`/=`), `INCREMENT` (`++`), `DECREMENT` (`--`), `DOUBLE_STAR` (`**`), `DOUBLE_SLASH` (`//`), `COROUTINE` (`:<`), `SPREAD` (`..`), `AND` (`&&`), `OR` (`||`), `BANG` (`!`)

Single chars: `PLUS`, `MINUS`, `STAR`, `SLASH`, `PERCENT`, `LT`, `GT`, `LT_EQ`, `GT_EQ`, `LPAREN`, `RPAREN`, `LBRACE`, `RBRACE`, `LBRACKET`, `RBRACKET`, `COLON`, `COMMA`, `DOT`

Literals: `INT_LIT`, `FLOAT_LIT`, `BOOL_LIT`, `STRING_LIT`, `FSTRING_START`, `FSTRING_END`, `FSTRING_TEXT`, `FSTRING_EXPR_START`, `FSTRING_EXPR_END`, `CHAR_LIT`

Other: `IDENT`, `COMMENT`, `NEWLINE`, `EOF`

**RT-2-1-2**
Define a `Token` dataclass: `type: TokenType`, `value: str`, `line: int`, `col: int`, `file: str`.

---

## Story 2-2: Core Lexer

**RT-2-2-1** `[BLOCKER]`
Implement the `Lexer` class. Constructor takes `source: str`, `filename: str`. Implement `tokenize() -> list[Token]`. The lexer is a single-pass scanner with a position cursor. At each position, try to match the longest possible token (maximal munch).

**RT-2-2-2**
Implement identifier and keyword scanning. After scanning an identifier, check if it is in the keyword map and emit the appropriate keyword token type. Identifiers start with a letter or underscore and continue with letters, digits, or underscores.

**RT-2-2-3**
Implement numeric literal scanning. Integers: optional `0x` hex prefix, digits separated by underscores (`1_000_000`). Floats: digits, dot, digits, optional `e` exponent. Emit `INT_LIT` or `FLOAT_LIT` with the raw string as value.

**RT-2-2-4**
Implement string literal scanning. A string starts with `"` and ends with `"`. Handle escape sequences: `\n`, `\t`, `\\`, `\"`, `\u{XXXXXX}` (Unicode code point). Emit a single `STRING_LIT` token with the interpreted string value.

**RT-2-2-5**
Implement f-string scanning. An f-string starts with `f"`. Emit `FSTRING_START`. Scan text until `{`, emitting `FSTRING_TEXT` tokens. On `{`, emit `FSTRING_EXPR_START`, then switch to normal lexing until the matching `}`, emitting `FSTRING_EXPR_END`. On the closing `"`, emit `FSTRING_END`. Nested braces inside expressions must be tracked (brace depth counter).

**RT-2-2-6**
Implement comment scanning. A comment begins with `;` and runs to end of line. Emit a `COMMENT` token (the parser will discard these). Do not emit `NEWLINE` for a line that is only a comment.

**RT-2-2-7**
Implement operator scanning for all multi-character operators. Prioritize longer matches: `===` before `==`, `->` before `-`, `<:(` as a single token, `:<` before `<`, `..` before `.`, `++` before `+`, `--` before `-`, `**` before `*`, `//` before `/`, `??` before `?`, `&&` before `&`, `||` before `|`.

**RT-2-2-8**
Implement character literal scanning. A char literal is `'x'` where x is a single character or a `\u{XXXXXX}` escape. Emit `CHAR_LIT`.

---

## Story 2-3: Lexer Error Handling

**RT-2-3-1**
On any unrecognized character, raise `LexError` with file, line, col, and a message like `unexpected character 'X'`.

**RT-2-3-2**
On an unterminated string literal (EOF before closing `"`), raise `LexError` with a message like `unterminated string literal`.

**RT-2-3-3**
On an f-string with unmatched braces, raise `LexError`.

---

## Story 2-4: Lexer Tests

**RT-2-4-1**
Write unit tests for the lexer covering: all keywords, all operators, integer literals with underscores, float literals, string literals with all escape sequences, f-strings with simple and nested expressions, character literals, comments, multiline source.

**RT-2-4-2**
Write error case tests: unterminated string, unrecognized character, malformed hex literal.

---

---

# EPIC 3: AST Nodes

Define the full abstract syntax tree as Python dataclasses before writing the parser. Every node in the grammar gets a class.

---

## Story 3-1: Type Expression Nodes

**RT-3-1-1** `[BLOCKER]`
In `compiler/ast_nodes.py`, define type expression nodes. All inherit from `TypeExpr`.

```python
@dataclass
class NamedType(TypeExpr):
    name: str                    # e.g. "int", "string", "LogEntry"
    module_path: list[str]       # e.g. ["math", "vector"] for math.vector.Vec3

@dataclass
class GenericType(TypeExpr):
    base: TypeExpr
    args: list[TypeExpr]         # e.g. option<int> → GenericType("option", [NamedType("int")])

@dataclass
class OptionType(TypeExpr):      # T?
    inner: TypeExpr

@dataclass
class FnType(TypeExpr):
    params: list[TypeExpr]
    ret: TypeExpr

@dataclass
class TupleType(TypeExpr):
    elements: list[TypeExpr]

@dataclass
class MutType(TypeExpr):         # T:mut
    inner: TypeExpr

@dataclass
class ImutType(TypeExpr):        # T:imut
    inner: TypeExpr

@dataclass
class SumType(TypeExpr):
    variants: list['SumVariant']

@dataclass
class SumVariant:
    name: str
    fields: list[tuple[str, TypeExpr]] | None  # None means no payload
```

**RT-3-1-2**
Every AST node must carry `line: int` and `col: int` from the token that started it. Add these fields to the base `ASTNode` class that all nodes inherit from.

---

## Story 3-2: Expression Nodes

**RT-3-2-1** `[BLOCKER]`
Define expression nodes. All inherit from `Expr`.

```python
@dataclass
class IntLit(Expr):
    value: int
    suffix: str | None     # "i64", "u32", etc.

@dataclass
class FloatLit(Expr):
    value: float
    suffix: str | None

@dataclass
class BoolLit(Expr):
    value: bool

@dataclass
class StringLit(Expr):
    value: str

@dataclass
class FStringExpr(Expr):
    parts: list[str | Expr]   # alternating text and expressions

@dataclass
class CharLit(Expr):
    value: int               # Unicode scalar

@dataclass
class NoneLit(Expr):
    pass

@dataclass
class Ident(Expr):
    name: str
    module_path: list[str]

@dataclass
class BinOp(Expr):
    op: str
    left: Expr
    right: Expr

@dataclass
class UnaryOp(Expr):
    op: str
    operand: Expr

@dataclass
class Call(Expr):
    callee: Expr
    args: list[Expr]

@dataclass
class MethodCall(Expr):
    receiver: Expr
    method: str
    args: list[Expr]

@dataclass
class FieldAccess(Expr):
    receiver: Expr
    field: str

@dataclass
class IndexAccess(Expr):
    receiver: Expr
    index: Expr

@dataclass
class Lambda(Expr):
    params: list['Param']
    body: Expr

@dataclass
class TupleExpr(Expr):
    elements: list[Expr]

@dataclass
class ArrayLit(Expr):
    elements: list[Expr]

@dataclass
class RecordLit(Expr):
    fields: list[tuple[str, Expr]]

@dataclass
class TypeLit(Expr):
    type_name: str
    fields: list[tuple[str, Expr]]
    spread: Expr | None       # the ..source expression

@dataclass
class IfExpr(Expr):
    condition: Expr
    then_branch: 'Block'
    else_branch: 'Block | IfExpr | None'

@dataclass
class MatchExpr(Expr):
    subject: Expr
    arms: list['MatchArm']

@dataclass
class CompositionChain(Expr):
    elements: list['ChainElement']

@dataclass
class FanOut(Expr):
    branches: list['ChainBranch']
    parallel: bool

@dataclass
class TernaryExpr(Expr):
    condition: Expr
    then_expr: Expr
    else_expr: Expr

@dataclass
class CopyExpr(Expr):          # @expr
    inner: Expr

@dataclass
class SomeExpr(Expr):
    inner: Expr

@dataclass
class OkExpr(Expr):
    inner: Expr

@dataclass
class ErrExpr(Expr):
    inner: Expr

@dataclass
class CoerceExpr(Expr):
    inner: Expr
    target_type: TypeExpr

@dataclass
class CastExpr(Expr):
    inner: Expr
    target_type: TypeExpr

@dataclass
class SnapshotExpr(Expr):
    inner: Expr

@dataclass
class PropagateExpr(Expr):     # expr?  — result propagation
    inner: Expr

@dataclass
class NullCoalesce(Expr):      # expr ?? expr
    left: Expr
    right: Expr

@dataclass
class TypeofExpr(Expr):
    inner: Expr

@dataclass
class CoroutineStart(Expr):    # let b :< a(x)
    call: Call
```

---

## Story 3-3: Statement Nodes

**RT-3-3-1** `[BLOCKER]`
Define statement nodes. All inherit from `Stmt`.

```python
@dataclass
class LetStmt(Stmt):
    name: str
    type_ann: TypeExpr | None
    value: Expr

@dataclass
class AssignStmt(Stmt):
    target: Expr          # can be Ident or FieldAccess
    value: Expr

@dataclass
class UpdateStmt(Stmt):   # +=, -=, *=, /=, ++, --
    target: Expr
    op: str
    value: Expr | None    # None for ++ and --

@dataclass
class ReturnStmt(Stmt):
    value: Expr | None

@dataclass
class YieldStmt(Stmt):
    value: Expr

@dataclass
class ThrowStmt(Stmt):
    exception: Expr

@dataclass
class BreakStmt(Stmt):
    pass

@dataclass
class ExprStmt(Stmt):
    expr: Expr

@dataclass
class IfStmt(Stmt):
    condition: Expr
    then_branch: 'Block'
    else_branch: 'Block | IfStmt | None'

@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: 'Block'
    finally_block: 'Block | None'

@dataclass
class ForStmt(Stmt):
    var: str
    var_type: TypeExpr | None
    iterable: Expr
    body: 'Block'
    finally_block: 'Block | None'

; C-style for loops removed: ';' is the comment character, creating
; an irreconcilable syntax conflict. Use while loops or for(x in range(...)) instead.

@dataclass
class MatchStmt(Stmt):
    subject: Expr
    arms: list['MatchArm']

@dataclass
class TryStmt(Stmt):
    body: 'Block'
    retry_blocks: list['RetryBlock']
    catch_blocks: list['CatchBlock']
    finally_block: 'FinallyBlock | None'

@dataclass
class Block:
    stmts: list[Stmt]
    finally_block: 'Block | None'     # function-level finally

@dataclass
class MatchArm:
    pattern: 'Pattern'
    body: Expr | Block

@dataclass
class RetryBlock:
    target_fn: str
    exception_var: str
    exception_type: TypeExpr
    attempts: int
    body: Block

@dataclass
class CatchBlock:
    exception_var: str
    exception_type: TypeExpr
    body: Block

@dataclass
class FinallyBlock:
    exception_var: str | None      # None if no `? ex:Exception` binding
    exception_type: TypeExpr | None
    body: Block
```

---

## Story 3-4: Pattern Nodes

**RT-3-4-1**
Define pattern nodes for `match` arms. All inherit from `Pattern`.

```python
@dataclass
class WildcardPattern(Pattern):
    pass                          # _

@dataclass
class LiteralPattern(Pattern):
    value: Expr                   # int, string, bool, none

@dataclass
class BindPattern(Pattern):
    name: str                     # bare identifier: binds the matched value

@dataclass
class SomePattern(Pattern):
    inner_var: str                # some(v)

@dataclass
class NonePattern(Pattern):
    pass                          # none

@dataclass
class OkPattern(Pattern):
    inner_var: str                # ok(v)

@dataclass
class ErrPattern(Pattern):
    inner_var: str                # err(e)

@dataclass
class VariantPattern(Pattern):
    variant_name: str
    bindings: list[str]           # Circle(r) → bindings=["r"]

@dataclass
class TuplePattern(Pattern):
    elements: list[Pattern]
```

---

## Story 3-5: Declaration Nodes

**RT-3-5-1** `[BLOCKER]`
Define top-level declaration nodes. All inherit from `Decl`.

```python
@dataclass
class ModuleDecl(Decl):
    path: list[str]               # ["math", "vector"]

@dataclass
class ImportDecl(Decl):
    path: list[str]
    names: list[str] | None       # None = import all
    alias: str | None

@dataclass
class FnDecl(Decl):
    name: str
    type_params: list[str]
    params: list['Param']
    return_type: TypeExpr
    body: Block | Expr | None     # None for interface declarations
    is_pure: bool
    is_export: bool
    is_static: bool
    finally_block: Block | None

@dataclass
class Param:
    name: str
    type_ann: TypeExpr

@dataclass
class TypeDecl(Decl):
    name: str
    type_params: list[str]
    fields: list['FieldDecl']
    methods: list[FnDecl]
    constructors: list['ConstructorDecl']
    static_members: list['StaticMemberDecl']
    interfaces: list[str]         # names of fulfilled interfaces
    is_export: bool
    is_sum_type: bool
    variants: list['SumVariantDecl']   # for sum types

@dataclass
class FieldDecl:
    name: str
    type_ann: TypeExpr
    is_mut: bool

@dataclass
class ConstructorDecl:
    name: str
    params: list[Param]
    return_type: TypeExpr
    body: Block

@dataclass
class StaticMemberDecl:
    name: str
    type_ann: TypeExpr
    value: Expr | None
    is_mut: bool

@dataclass
class InterfaceDecl(Decl):
    name: str
    type_params: list[str]
    methods: list[FnDecl]
    constructor_sig: 'ConstructorDecl | None'
    is_export: bool

@dataclass
class AliasDecl(Decl):
    name: str
    type_params: list[str]
    target: TypeExpr
    is_export: bool

@dataclass
class Module:
    path: list[str]
    imports: list[ImportDecl]
    decls: list[Decl]
    filename: str

@dataclass
class SumVariantDecl:
    name: str
    fields: list[tuple[str, TypeExpr]] | None
```

---

---

# EPIC 4: Parser

The parser takes a token list and produces a `Module` AST node. Use recursive descent.

---

## Story 4-1: Parser Infrastructure

**RT-4-1-1** `[BLOCKER]`
In `compiler/parser.py`, implement the `Parser` class. Constructor takes `tokens: list[Token]`, `filename: str`. Internal state: `pos: int` (current position). Implement helpers:
- `peek() -> Token` — look at current token without consuming
- `peek2() -> Token` — look two ahead
- `advance() -> Token` — consume and return current token
- `expect(type: TokenType) -> Token` — advance if type matches, else raise `ParseError`
- `check(type: TokenType) -> bool` — true if current token is type
- `match(*types: TokenType) -> bool` — advance and return true if current token is any of types
- `skip_comments()` — skip any COMMENT tokens
- `at_end() -> bool` — true if at EOF

**RT-4-1-2**
Implement `parse() -> Module` as the top-level entry point. It parses the optional `module` declaration, then all `import` declarations, then all top-level declarations until EOF.

---

## Story 4-2: Parsing Declarations

**RT-4-2-1** `[BLOCKER]`
Implement `parse_module_decl() -> ModuleDecl`. Parses `module a.b.c`.

**RT-4-2-2**
Implement `parse_import_decl() -> ImportDecl`. Parses `import a.b.c`, `import a.b.c (X, Y)`, `import a.b.c as alias`.

**RT-4-2-3** `[BLOCKER]`
Implement `parse_fn_decl(is_export, is_static, is_pure) -> FnDecl`. Parses:
- Full body: `fn name<T>(param: Type, ...): ReturnType { ... }`
- Expression body: `fn name(param: Type): ReturnType = expr`
- Interface signature: `fn name(param: Type): ReturnType` (no body)
- With optional function-level `finally` block after the body

**RT-4-2-4**
Implement `parse_type_decl(is_export) -> TypeDecl`. Parses both struct types and sum types. Sum type form: `type Name = | Variant(fields) | Variant2`. Struct form: `type Name { fields, methods, constructors, statics }`.

**RT-4-2-5**
Implement `parse_interface_decl(is_export) -> InterfaceDecl`. Parses interface bodies containing only method signatures and an optional constructor signature.

**RT-4-2-6**
Implement `parse_alias_decl(is_export) -> AliasDecl`. Parses `alias Name<T>: UnderlyingType`.

**RT-4-2-7**
Implement `parse_constructor_decl() -> ConstructorDecl`. Parses `constructor name(params): ReturnType { body }`.

**RT-4-2-8**
Implement `parse_static_member() -> StaticMemberDecl`. Parses `static name: Type = value` and `static name: Type:mut = value`.

---

## Story 4-3: Parsing Statements

**RT-4-3-1** `[BLOCKER]`
Implement `parse_block() -> Block`. Parses `{ stmt* }` followed by an optional function-level `finally { block }`.

**RT-4-3-2** `[BLOCKER]`
Implement `parse_stmt() -> Stmt`. Dispatches to the appropriate statement parser based on the current token. Returns `ExprStmt` for expressions used as statements.

**RT-4-3-3**
Implement `parse_let_stmt() -> LetStmt`. Parses `let name: Type:mut = expr` and `let name = expr`. Handle the full type modifier chain.

**RT-4-3-4**
Implement `parse_if_stmt() -> IfStmt`. Parses `if expr { block } else if ... else { block }`.

**RT-4-3-5**
Implement `parse_while_stmt() -> WhileStmt`. Parses `while expr { block }` with optional trailing `finally { block }`.

**RT-4-3-6**
Implement `parse_for_stmt() -> ForStmt`. Parses iteration form `for(item: T in expr) { block }` with optional `finally`. C-style for loops were removed due to `;` comment syntax conflict.

**RT-4-3-7**
Implement `parse_match_stmt() -> MatchStmt` and `parse_match_expr() -> MatchExpr`. Parses `match expr { pattern : expr_or_block, ... }`.

**RT-4-3-8**
Implement `parse_try_stmt() -> TryStmt`. Parses `try { } retry fn_name (ex: Type, attempts: n) { } catch (ex: Type) { } finally (? ex: Exception) { }`.

**RT-4-3-9**
Implement `parse_return_stmt`, `parse_yield_stmt`, `parse_throw_stmt`, `parse_break_stmt`.

---

## Story 4-4: Parsing Expressions

**RT-4-4-1** `[BLOCKER]`
Implement expression parsing with correct operator precedence using a Pratt parser. Precedence levels (lowest to highest):
1. `??` (null coalesce)
2. `||`
3. `&&`
4. `==`, `===`, `!=`
5. `<`, `>`, `<=`, `>=`
6. `+`, `-`
7. `*`, `/`, `//`, `%`
8. `**`
9. Unary `!`, unary `-`
10. Postfix: `?` (propagation), `.field`, `(args)` (call), `[idx]`
11. Primary: literals, identifiers, `(expr)`, `\(lambda)`

**RT-4-4-2** `[BLOCKER]`
Implement composition chain parsing. A composition chain is a sequence of values and functions separated by `->`. When the parser sees `->` at expression level, it collects all elements into a `CompositionChain`. Fan-out groups `(a | b)` inside chains become `FanOut` nodes. The `<:(a | b)` form sets `parallel=True`.

**RT-4-4-3**
Implement primary expression parsing: literals, identifiers (with optional module path), `(expr)` grouping, lambda `\(params => body)`, array literals `[a, b, c]`, record literals `{ field: expr }`, type construction literals `TypeName { field: expr, ..spread }`, tuple literals `(a, b, c)`, `some(expr)`, `ok(expr)`, `err(expr)`, `coerce(expr)`, `cast<T>(expr)`, `snapshot(expr)`, `typeof(expr)`.

**RT-4-4-4**
Implement f-string expression parsing. Between `FSTRING_START` and `FSTRING_END`, collect `FSTRING_TEXT` tokens as string parts and recursively parse expressions between `FSTRING_EXPR_START` and `FSTRING_EXPR_END`. Produce a `FStringExpr` node.

**RT-4-4-5**
Implement ternary expression parsing: `expr ? expr : expr`. This is right-associative and lower precedence than `||`.

**RT-4-4-6**
Implement pattern parsing for match arms: `_`, literal patterns, `some(v)`, `none`, `ok(v)`, `err(e)`, variant patterns `Circle(r)`, tuple patterns `(a, b)`, and bare identifier bind patterns.

---

## Story 4-5: Parser Error Handling

**RT-4-5-1**
On unexpected token, raise `ParseError` with file, line, col, and a message like `expected ':' but found 'fn' at line 12, col 5`. Include context: what was being parsed.

**RT-4-5-2**
Implement error recovery for block-level parsing: on a parse error inside a statement, skip tokens until a recovery point (next `let`, `fn`, `if`, `return`, `}`, or EOF) and continue parsing. Collect all errors and report them together rather than stopping at the first one.

---

## Story 4-6: Parser Tests

**RT-4-6-1**
Write parse tests for each declaration type. Each test provides a source string and asserts the AST structure is exactly what is expected (compare AST node fields).

**RT-4-6-2**
Write parse tests for all expression forms, including composition chains with fan-out and parallel fan-out.

**RT-4-6-3**
Write parse tests for all statement forms and for match patterns.

**RT-4-6-4**
Write error recovery tests: a source with two errors should produce two `ParseError` objects, not stop at the first.

---

---

# EPIC 5: Name Resolution

The resolver walks the AST and resolves every name to its definition. It builds a symbol table and catches scope violations defined in the spec.

---

## Story 5-1: Symbol Table

**RT-5-1-1** `[BLOCKER]`
In `compiler/resolver.py`, define a `Scope` class. It holds a `dict[str, Symbol]` mapping names to their definitions. Scopes chain: each scope has an optional parent. Implement `define(name, symbol)`, `lookup(name) -> Symbol | None`, `lookup_local(name) -> Symbol | None` (no parent chain).

**RT-5-1-2**
Define a `Symbol` dataclass: `name: str`, `kind: SymbolKind` (enum: `LOCAL`, `PARAM`, `FN`, `TYPE`, `INTERFACE`, `ALIAS`, `STATIC`, `IMPORT`, `CONSTRUCTOR`), `decl: ASTNode`, `type: TypeExpr | None` (populated by type checker later), `is_mut: bool`.

**RT-5-1-3**
Define a `ModuleScope` that holds all exported symbols from a module. The resolver builds one `ModuleScope` per module. The driver loads `ModuleScope`s for all imported modules before resolving the current module.

---

## Story 5-2: Resolution Pass

**RT-5-2-1** `[BLOCKER]`
Implement the `Resolver` class. Constructor takes the `Module` AST. Implement `resolve() -> ResolvedModule`. A `ResolvedModule` wraps the original `Module` and adds a `symbols: dict[ASTNode, Symbol]` map linking every `Ident` node to the `Symbol` it refers to.

**RT-5-2-2** `[BLOCKER]`
Implement a pre-pass that collects all top-level declarations (functions, types, interfaces, aliases) into the module scope before resolving any function bodies. This allows forward references between top-level declarations.

**RT-5-2-3**
Implement resolution of import declarations. For each import, look up the corresponding `ModuleScope` and bring the requested names into the current scope. Raise `ResolveError` if a module is not found or a name is not exported.

**RT-5-2-4** `[BLOCKER]`
Implement function body resolution. For each function: create a new scope with the function's parameters. Resolve all statements in the body. After the function, pop the scope. Enforce: function body cannot access variables from outer function scopes (only lambdas can close over enclosing scopes).

**RT-5-2-5**
Implement lambda capture resolution. When resolving a lambda inside a function body, allow the lambda to reference names from all enclosing function scopes. Record each captured name in a `captures: list[Symbol]` field on the `Lambda` AST node. Mark captured `:mut` bindings as "captured by copy."

**RT-5-2-6**
Implement resolution of type declarations. For each type, create a scope that includes all field names and method names. Resolve method bodies in this scope with `self` bound to the type instance.

**RT-5-2-7**
Implement resolution of static member access. `Config.host` resolves the `Config` type, then looks up `host` in its static member scope. Raise `ResolveError` if either does not exist.

**RT-5-2-8**
Implement resolution of match patterns. For each match arm, create a new scope containing the variables bound by the pattern (e.g., `some(v)` binds `v`). Resolve the arm body in that scope.

---

## Story 5-3: Scope Violation Checks

**RT-5-3-1** `[BLOCKER]`
Enforce: a non-lambda function cannot reference a local variable from its caller's scope. This check is implicit if resolution uses strict scope chaining (lambdas look up the chain, functions do not). Confirm it is enforced with a test.

**RT-5-3-2**
Enforce: the update operators `+=`, `-=`, etc. and `++`/`--` may only be applied to `:mut` bindings. Raise `ResolveError` (or defer to type checker — either is fine, document the choice) if a non-mut binding is updated.

**RT-5-3-3**
Enforce: `self` is only valid inside a type method or constructor body. Raise `ResolveError` if `self` is referenced elsewhere.

**RT-5-3-4**
Enforce: `yield` is only valid inside a function with a `stream<T>` return type. Flag it at resolve time as a soft check (the type checker will confirm the return type).

---

## Story 5-4: Resolver Tests

**RT-5-4-1**
Test that a function referencing an undefined variable raises `ResolveError`.

**RT-5-4-2**
Test that a lambda can capture from an enclosing function scope but a nested named function cannot.

**RT-5-4-3**
Test forward references: function `a` calling function `b` defined later in the file resolves correctly.

**RT-5-4-4**
Test that `self` in a non-method context raises `ResolveError`.

---

---

# EPIC 6: Type Checker

The type checker annotates every expression with a type and enforces all type rules defined in the spec. It operates on the resolved AST.

---

## Story 6-1: Type Representation

**RT-6-1-1** `[BLOCKER]`
In `compiler/typechecker.py`, define the internal type representation. These are distinct from `TypeExpr` AST nodes — they are resolved, concrete types.

```python
@dataclass(frozen=True)
class TInt(Type): width: int; signed: bool   # int, int32, int64, uint...
@dataclass(frozen=True)
class TFloat(Type): width: int               # float32, float64
@dataclass(frozen=True)
class TBool(Type): pass
@dataclass(frozen=True)
class TChar(Type): pass
@dataclass(frozen=True)
class TByte(Type): pass
@dataclass(frozen=True)
class TString(Type): pass
@dataclass(frozen=True)
class TNone(Type): pass
@dataclass(frozen=True)
class TOption(Type): inner: Type
@dataclass(frozen=True)
class TResult(Type): ok_type: Type; err_type: Type
@dataclass(frozen=True)
class TTuple(Type): elements: tuple[Type, ...]
@dataclass(frozen=True)
class TArray(Type): element: Type
@dataclass(frozen=True)
class TStream(Type): element: Type
@dataclass(frozen=True)
class TBuffer(Type): element: Type
@dataclass(frozen=True)
class TMap(Type): key: Type; value: Type
@dataclass(frozen=True)
class TSet(Type): element: Type
@dataclass(frozen=True)
class TFn(Type):
    params: tuple[Type, ...]
    ret: Type
    is_pure: bool
@dataclass(frozen=True)
class TRecord(Type): fields: tuple[tuple[str, Type], ...]
@dataclass(frozen=True)
class TNamed(Type):
    module: str
    name: str
    type_args: tuple[Type, ...]
@dataclass(frozen=True)
class TAlias(Type):
    name: str
    underlying: Type
@dataclass(frozen=True)
class TSum(Type):
    name: str
    variants: tuple['TVariant', ...]
@dataclass(frozen=True)
class TVariant:
    name: str
    fields: tuple[Type, ...] | None
@dataclass(frozen=True)
class TTypeVar(Type): name: str    # unresolved generic parameter
@dataclass(frozen=True)
class TAny(Type): pass             # used only during inference before resolution
```

**RT-6-1-2**
Implement `TypeEnv`: a mapping from `TTypeVar` names to resolved `Type` values. Used during generic instantiation. Implement `apply_env(t: Type, env: TypeEnv) -> Type` that substitutes all type variables in `t` with their bindings in `env`.

---

## Story 6-2: Type Inference Core

**RT-6-2-1** `[BLOCKER]`
Implement `TypeChecker.check(module: ResolvedModule) -> TypedModule`. A `TypedModule` wraps the resolved module and adds `types: dict[ASTNode, Type]` mapping every expression node to its inferred type.

**RT-6-2-2** `[BLOCKER]`
Implement `infer_expr(expr: Expr, env: TypeEnv) -> Type`. This is the central inference function. It pattern-matches on the expression type and delegates to specialized handlers. Every expression must receive a type.

**RT-6-2-3**
Implement type inference for literals: `IntLit → TInt(32, signed=True)` (default), `FloatLit → TFloat(64)`, `BoolLit → TBool()`, `StringLit → TString()`, `CharLit → TChar()`, `NoneLit → TOption(TAny())`.

**RT-6-2-4**
Implement type inference for `BinOp`. Arithmetic ops require both sides to be numeric and the same type; result is the same type. Comparison ops require congruent types; result is `TBool`. `+` on strings produces `TString`. Mixed-type arithmetic is a `TypeError` (no implicit coercion).

**RT-6-2-5**
Implement type inference for function calls. Look up the function's signature, match argument types against parameter types, apply generic substitution if type parameters are present. Return the function's declared return type.

**RT-6-2-6**
Implement type inference for `LetStmt`. If a type annotation is present, infer the value's type and check it matches. If no annotation, infer from the value and record the binding's type in scope.

**RT-6-2-7**
Implement type inference for `IfExpr`. Both branches must have the same type (or one is `none`/`TNone`). The `if`/`else` as expression produces that type. `if` as statement requires branches to be `TNone` or discards the value.

**RT-6-2-8**
Implement type inference for lambdas. Parameter types must be annotated. Infer the body type. Produce `TFn(param_types, body_type, is_pure=False)`. A lambda's purity is inferred from its body in the `pure` check pass.

---

## Story 6-3: Composition Chain Type Checking

**RT-6-3-1** `[BLOCKER]`
Implement `infer_chain(chain: CompositionChain, env: TypeEnv) -> Type`. Walk elements left to right, maintaining a type stack. Rules:
- A value expression: push its type
- A function reference with arity N: pop N types, check against parameter types, push return type
- A fan-out group `(a | b | c)`: each branch independently receives the current stack top, pop it, push all branch result types left to right
- If a `stream<T>` flows into a function expecting `T`: auto-map (wrap in implicit map)

**RT-6-3-2**
Implement auto-mapping in the chain. When a `TStream(T)` is on the stack and the next function expects `T` (not `TStream(T)`), the chain is implicitly mapped: the function is applied element-wise and the result is `TStream(result_type)`.

**RT-6-3-3**
Implement fan-out arity checking. After a fan-out group produces N types on the stack, the next function must have exactly N parameters. Arity mismatch is a `TypeError` with a clear message: `"fan-out produces 3 values but 'mul' accepts 2 parameters"`.

---

## Story 6-4: Sum Type and Option Checking

**RT-6-4-1** `[BLOCKER]`
Implement exhaustiveness checking for `match` on sum types. Collect all variant names of the matched type. Verify each arm's pattern matches a variant. Raise `TypeError` if any variant is unhandled and no `_` wildcard is present. This is a compile error, not a warning.

**RT-6-4-2**
Implement exhaustiveness checking for `match` on `option<T>`. Both `some(v)` and `none` must be handled, or `_` must be present. Compile error if missing.

**RT-6-4-3**
Implement exhaustiveness checking for `match` on `result<T, E>`. Both `ok(v)` and `err(e)` must be handled, or `_` must be present.

**RT-6-4-4**
For `match` on primitive types (int, string, bool), exhaustiveness cannot be fully verified. Emit a compile-time warning if no `_` arm is present. At runtime, an unmatched case calls `rf_panic("match not exhaustive")`.

**RT-6-4-5**
Implement auto-lifting for `option<T>`. When a `T` is assigned or passed where `option<T>` is expected and the context type is statically known, wrap in an implicit `SomeExpr`. Record the lifted node in the typed module so the emitter can generate the right C.

---

## Story 6-5: Ownership and Mutability Checking

**RT-6-5-1** `[BLOCKER]`
Implement mutability checking. Track which bindings are `:mut` in a `mut_env: set[str]`. Raise `TypeError` if:
- An update operator (`+=`, `++`, etc.) is applied to a non-mut binding
- A `:mut` parameter is required but a non-mut binding is passed
- A field marked as immutable is assigned in a method body

**RT-6-5-2**
Implement the `:imut` parameter rule. A function taking `T:imut` accepts any binding. A function taking `T:mut` requires the caller to pass a `:mut` binding (or a `@copy` expression). Raise `TypeError` with message `"cannot pass immutable binding to :mut parameter; use @ to pass a copy"`.

**RT-6-5-3**
Implement stream single-consumer check. Track each `stream<T>` binding. Flag it as consumed when it is passed to a function or used in a chain. Raise `TypeError` if the same stream binding is consumed a second time. This is a conservative check — full data flow analysis is deferred to the self-hosted compiler.

---

## Story 6-6: Purity Checking

**RT-6-6-1** `[BLOCKER]`
Implement purity checking for `pure fn`. Walk the function body and verify:
- Every called function is also marked `pure`
- No mutable statics are read or written
- No I/O functions are called (functions in the `io` module)
- No `snapshot()` calls
- No `:mut` parameters are accepted

Raise `TypeError` for each violation with a message identifying the offending call.

**RT-6-6-2**
Build a global purity map `purity: dict[str, bool]` (mangled name → is_pure) from the bottom up. A function is pure if and only if it is declared `pure` and passes the purity check. Functions that call unknown (imported) functions are not pure unless the import is also declared pure.

---

## Story 6-7: Congruence Checking

**RT-6-7-1**
Implement `is_congruent(a: Type, b: Type) -> bool`. Two types are congruent if they have the same field names and field types (order-independent). Methods do not factor in. Nominal type names do not factor in.

**RT-6-7-2**
Enforce `coerce(expr)` requires the source type and the target type (from the surrounding context or explicit annotation) to be congruent. Raise `TypeError` with `"coerce requires structurally congruent types; source has fields [...] but target expects [...]"`.

**RT-6-7-3**
Enforce `===` operator requires both sides to be structural types (types, records). Applying `===` to primitive types is a `TypeError`.

---

## Story 6-8: Type Checker Tests

**RT-6-8-1**
Test that passing an `int` where `int64` is expected raises `TypeError`.

**RT-6-8-2**
Test that a `match` on a sum type missing a variant raises `TypeError`.

**RT-6-8-3**
Test that a `pure fn` calling a non-pure function raises `TypeError`.

**RT-6-8-4**
Test that consuming the same stream twice raises `TypeError`.

**RT-6-8-5**
Test that `coerce` on non-congruent types raises `TypeError`.

**RT-6-8-6**
Test that fan-out arity mismatch raises `TypeError`.

**RT-6-8-7**
Test that passing an immutable binding to a `:mut` parameter raises `TypeError`.

---

---

# EPIC 7: Lowering

The lowering pass transforms the typed AST into an explicit intermediate form that the C emitter can translate directly. It resolves all ReFlow abstractions into concrete operations.

---

## Story 7-1: Lowering IR Nodes

**RT-7-1-1** `[BLOCKER]`
In `compiler/lowering.py`, define the lowering IR. These are simple nodes that map closely to C constructs. All inherit from `LIR`.

```python
@dataclass
class LModule:
    type_defs: list['LTypeDef']
    fn_defs: list['LFnDef']
    static_defs: list['LStaticDef']

@dataclass
class LTypeDef:
    c_name: str
    fields: list[tuple[str, 'LType']]   # C field name → C type

@dataclass
class LFnDef:
    c_name: str
    params: list[tuple[str, 'LType']]
    ret: 'LType'
    body: list['LStmt']
    is_pure: bool

@dataclass
class LStaticDef:
    c_name: str
    c_type: 'LType'
    init: 'LExpr | None'
    is_mut: bool

# LType: maps ReFlow types to C types
@dataclass
class LInt(LType): width: int; signed: bool
@dataclass
class LFloat(LType): width: int
@dataclass
class LBool(LType): pass
@dataclass
class LPtr(LType): inner: 'LType'    # RF_String*, RF_Array*, etc.
@dataclass
class LStruct(LType): c_name: str
@dataclass
class LVoid(LType): pass

# LStmt
@dataclass
class LVarDecl(LStmt): c_name: str; c_type: LType; init: 'LExpr | None'
@dataclass
class LAssign(LStmt): target: 'LExpr'; value: 'LExpr'
@dataclass
class LReturn(LStmt): value: 'LExpr | None'
@dataclass
class LIf(LStmt): cond: 'LExpr'; then: list[LStmt]; else_: list[LStmt]
@dataclass
class LWhile(LStmt): cond: 'LExpr'; body: list[LStmt]
@dataclass
class LBlock(LStmt): stmts: list[LStmt]
@dataclass
class LExprStmt(LStmt): expr: 'LExpr'
@dataclass
class LGoto(LStmt): label: str
@dataclass
class LLabel(LStmt): name: str
@dataclass
class LSwitch(LStmt): value: 'LExpr'; cases: list[tuple[int, list[LStmt]]]; default: list[LStmt]

# LExpr
@dataclass
class LLit(LExpr): value: str; c_type: LType
@dataclass
class LVar(LExpr): c_name: str; c_type: LType
@dataclass
class LCall(LExpr): fn_name: str; args: list['LExpr']; c_type: LType
@dataclass
class LIndirectCall(LExpr): fn_ptr: 'LExpr'; args: list['LExpr']; c_type: LType
@dataclass
class LBinOp(LExpr): op: str; left: 'LExpr'; right: 'LExpr'; c_type: LType
@dataclass
class LUnary(LExpr): op: str; operand: 'LExpr'; c_type: LType
@dataclass
class LFieldAccess(LExpr): obj: 'LExpr'; field: str; c_type: LType
@dataclass
class LArrow(LExpr): ptr: 'LExpr'; field: str; c_type: LType   # ptr->field
@dataclass
class LIndex(LExpr): arr: 'LExpr'; idx: 'LExpr'; c_type: LType
@dataclass
class LCast(LExpr): inner: 'LExpr'; c_type: LType
@dataclass
class LAddrOf(LExpr): inner: 'LExpr'; c_type: LType
@dataclass
class LDeref(LExpr): inner: 'LExpr'; c_type: LType
@dataclass
class LCompound(LExpr): fields: list[tuple[str, 'LExpr']]; c_type: LType  # struct literal
@dataclass
class LCheckedArith(LExpr):   # calls RF_CHECKED_ADD etc.
    op: str
    left: 'LExpr'
    right: 'LExpr'
    c_type: LType
```

---

## Story 7-2: Type Lowering

**RT-7-2-1** `[BLOCKER]`
Implement `lower_type(t: Type) -> LType`. Maps ReFlow types to C types:

```
TInt(32, signed)  → LInt(32, True)  → "int32_t"
TInt(64, signed)  → LInt(64, True)  → "int64_t"
TFloat(64)        → LFloat(64)      → "double"
TBool             → LBool           → "bool"
TString           → LPtr(LStruct("RF_String"))
TArray(T)         → LPtr(LStruct("RF_Array"))
TStream(T)        → LPtr(LStruct("RF_Stream"))
TBuffer(T)        → LPtr(LStruct("RF_Buffer"))
TMap(K, V)        → LPtr(LStruct("RF_Map"))
TSet(T)           → LPtr(LStruct("RF_Set"))
TNone             → LVoid
TOption(int)      → LStruct("RF_Option_int")
TResult(T, E)     → LStruct(generated_result_name(T, E))
TNamed(m, n, [])  → LStruct(mangle(m, n))
TFn(ps, r, _)     → LPtr(LStruct("closure_struct"))
TTuple(es)        → LStruct(generated_tuple_name(es))
```

**RT-7-2-2**
For user-defined types (`TNamed`), emit a `LTypeDef` with all fields lowered. For sum types, emit a `LTypeDef` with a tag field (`uint8_t tag`) and a union field sized to the largest variant's payload.

**RT-7-2-3**
For each unique `TResult(T, E)` combination encountered in the program, emit exactly one `LTypeDef` with a tag and a union payload. Maintain a registry to avoid duplicates.

**RT-7-2-4**
For each unique `TTuple(es)` combination, emit one `LTypeDef`. For closures, emit one `LTypeDef` per lambda containing the function pointer field and one field per captured variable.

---

## Story 7-3: Expression Lowering

**RT-7-3-1** `[BLOCKER]`
Implement `lower_expr(expr: Expr, types: dict[ASTNode, Type]) -> LExpr`. Maps typed expressions to LIR expressions.

**RT-7-3-2**
Lower arithmetic: use `LCheckedArith` for all integer arithmetic (maps to `RF_CHECKED_ADD` etc.). Use plain `LBinOp` for float arithmetic.

**RT-7-3-3**
Lower composition chains. Flatten `CompositionChain` into a sequence of `LVarDecl` and `LCall` statements with temporary variables. Each stage's result is stored in a fresh temp var that feeds the next stage. Fan-out becomes parallel `LCall`s to each branch, results stored in separate temps.

**RT-7-3-4**
Lower `FStringExpr`. Convert to a sequence of `rf_string_concat` calls: `rf_string_concat(rf_string_concat(part1, to_string(expr1)), part2)`. Each non-string part calls its `.to_string()` equivalent C function.

**RT-7-3-5**
Lower `MatchExpr` on sum types. Emit `LSwitch` on the tag field. Each arm's pattern-bound variables are extracted from the payload union. Wildcard becomes the default case.

**RT-7-3-6**
Lower `MatchExpr` on `option<T>`. Emit `LIf` on the tag field. `none` branch: tag == 0. `some(v)` branch: tag == 1, extract value field, bind to `v`.

**RT-7-3-7**
Lower `PropagateExpr` (`expr?`). Emit: evaluate expr, check if `err`, if so return the `err` immediately (early return), otherwise extract the `ok` value and continue.

**RT-7-3-8**
Lower `CopyExpr` (`@expr`). For immutable heap types: emit `rf_*_retain(ptr); return ptr`. For mutable types: emit a deep copy call. For value types: no-op (value types are already copied).

---

## Story 7-4: Statement Lowering

**RT-7-4-1** `[BLOCKER]`
Implement `lower_stmt(stmt: Stmt, types: dict) -> list[LStmt]`. Returns a list because one ReFlow statement may expand to multiple C statements.

**RT-7-4-2**
Lower `TryStmt`. Implement using `setjmp`/`longjmp` or a simpler approach: each throwable block is wrapped in a function. `retry` is implemented as a loop with a counter. For the bootstrap phase, a straightforward approach: the try block is compiled normally; thrown exceptions unwind via a thread-local exception state struct (`rf_exception_state`). Catching checks the type tag on that struct.

**RT-7-4-3**
Lower `ForStmt` over a stream. Emit a `while` loop that calls `rf_stream_next()` and breaks on `none`. The loop variable is assigned the unwrapped value each iteration.

**RT-7-4-4**
Lower `ForStmt` over an array. Emit a C-style `for` loop with an index variable, using `rf_array_get_ptr` for element access.

**RT-7-4-5**
Lower `WhileStmt`, `IfStmt`, `ReturnStmt`, `YieldStmt`, `BreakStmt`, `ThrowStmt` to their direct LIR equivalents.

---

## Story 7-5: Streaming Function Lowering

**RT-7-5-1** `[BLOCKER]`
A function with return type `stream<T>` is compiled to a state machine. Implement this transformation:

1. Identify all `yield` points and assign each a state number.
2. Create a frame struct `LTypeDef` containing all local variables and a `state` field (`int32_t`).
3. Create a `next` function `(RF_Stream* self) -> RF_Option_ptr` that:
   - Loads the frame from `self->state`
   - Dispatches on the `state` field via `LSwitch`
   - Each state runs code up to the next yield, stores the yielded value, advances state, returns `RF_SOME(value)`
   - The terminal state returns `RF_NONE`
4. Create a `free` function that releases all heap values in the frame and calls `free(frame)`.
5. The original function becomes a factory: allocate the frame, initialize locals, create and return an `RF_Stream*`.

**RT-7-5-2**
Handle `return` inside a streaming function. It must set the state to the terminal value and return `RF_NONE`.

**RT-7-5-3**
Handle function-level `finally` inside a streaming function. The `free` function (called on stream release) must also run the finally block's cleanup code.

---

---

# EPIC 8: C Emitter

The emitter takes a `LModule` and produces a `.c` file as a string. It is entirely mechanical — no decisions, just formatting.

---

## Story 8-1: Emitter Infrastructure

**RT-8-1-1** `[BLOCKER]`
In `compiler/emitter.py`, implement the `Emitter` class. It maintains a string buffer and an indentation level. Implement:
- `emit(s: str)` — append to buffer
- `emitln(s: str)` — append with newline
- `indent()` / `dedent()` — increase/decrease indentation
- `get_output() -> str` — return the buffer

**RT-8-1-2**
Every generated C file starts with a standard header comment:

```c
/* Generated by reflowc - do not edit */
/* Source: <filename.reflow> */
#include "reflow_runtime.h"
```

---

## Story 8-2: Type Emission

**RT-8-2-1** `[BLOCKER]`
Implement `emit_type_def(td: LTypeDef)`. Emit a C struct:

```c
typedef struct {
    rf_int32 tag;
    union {
        <variant_field> variant_name;
        ...
    } payload;
} MangedTypeName;
```

For plain structs (no tag), emit without the union.

**RT-8-2-2**
Emit type forward declarations at the top of the file before any struct definitions. This handles mutual recursion between types.

**RT-8-2-3**
Implement `emit_ltype(t: LType) -> str`. Returns the C type string for use in declarations: `"int32_t"`, `"double"`, `"bool"`, `"RF_String*"`, `"RF_Stream*"`, struct names, etc.

---

## Story 8-3: Function Emission

**RT-8-3-1** `[BLOCKER]`
Implement `emit_fn_def(fn: LFnDef)`. Emit C function signature and body:

```c
/* ReFlow: module.fn_name */
return_type mangled_name(param_type param_name, ...) {
    /* body */
}
```

**RT-8-3-2**
Emit function forward declarations (prototypes) before definitions to handle mutual recursion.

**RT-8-3-3**
Implement `emit_stmt(stmt: LStmt, depth: int)`. Dispatches to specific emitters for each LStmt type.

**RT-8-3-4**
Implement `emit_expr(expr: LExpr) -> str`. Returns a C expression string. For complex expressions that require statements (e.g., `LCheckedArith`), emit the statements first and use a temp variable name as the expression.

**RT-8-3-5**
Emit `LCheckedArith` as a call to the appropriate runtime macro:

```c
rf_int32 _tmp_1;
RF_CHECKED_ADD(lhs, rhs, &_tmp_1);
/* use _tmp_1 as the expression value */
```

**RT-8-3-6**
Emit `LSwitch` as a C `switch` statement with explicit `break` after each case.

**RT-8-3-7**
Emit `LCall` as a direct C function call. Emit `LIndirectCall` as a function pointer call through the closure struct.

**RT-8-3-8**
Implement temp variable name generation. Each call to `fresh_temp() -> str` returns a new unique name like `_rf_tmp_1`, `_rf_tmp_2`, etc. Reset the counter per function.

---

## Story 8-4: Static and Global Emission

**RT-8-4-1**
Implement `emit_static_def(sd: LStaticDef)`. Mutable statics become C globals. Immutable statics become `static const` globals.

```c
/* mutable static */
rf_int32 rf_Config_port = 5432;

/* immutable static */
static const rf_int32 rf_Config_max_retries = 3;
```

---

## Story 8-5: Emitter Tests

**RT-8-5-1**
Golden file test: compile `tests/programs/hello.reflow` (a function `add`), emit C, diff against `tests/expected/hello.c`. The expected C is handwritten to match exactly what the emitter should produce.

**RT-8-5-2**
Test: a function with `option<int>` return type emits the correct struct and tag checks.

**RT-8-5-3**
Test: a streaming function emits a valid state machine struct and `next`/`free` functions.

**RT-8-5-4**
Test: a sum type emits a tagged union struct with one case per variant.

---

---

# EPIC 9: Driver

The driver is the CLI that orchestrates the full pipeline.

---

## Story 9-1: Pipeline Orchestration

**RT-9-1-1** `[BLOCKER]`
Implement `compiler/driver.py`. The `compile(source_path: str, options: Options) -> int` function runs the full pipeline:
1. Read source file
2. Lex → token list
3. Parse → Module AST
4. Resolve → ResolvedModule
5. Type check → TypedModule
6. Lower → LModule
7. Emit → C string
8. Write C to a temp file
9. Shell out to `clang -o output tempfile.c reflow_runtime.c -I runtime/`
10. Delete temp file
11. Return exit code

**RT-9-1-2**
Implement `emit_only(source_path: str, options: Options)`. Runs steps 1–7 and prints the C output to stdout or writes to a file specified by `--output`.

**RT-9-1-3**
Implement `check_only(source_path: str, options: Options)`. Runs steps 1–5 only. Prints success or errors.

**RT-9-1-4**
Implement error formatting. On any `ReFlowError`, print:
```
error[EXXXX]: message
  --> file.reflow:12:5
   |
12 |     let x = bad_call()
   |             ^^^^^^^^
```
Use ANSI color codes if stdout is a TTY.

---

## Story 9-2: Multi-File Compilation

**RT-9-2-1**
Implement module discovery. Given a source file `main.reflow` with `import math.vector`, the driver looks for `math/vector.reflow` relative to the project root. The project root is determined by walking up from the source file until a directory with no parent `module` directory is found, or a `reflow.toml` marker file is present.

**RT-9-2-2**
Implement dependency ordering. Build a directed acyclic graph of module dependencies (import edges). Compile in topological order: dependencies before dependents. Raise `ResolveError` on circular imports with the full cycle in the error message.

**RT-9-2-3**
Implement incremental compilation (optional, mark as enhancement). Cache `.c` output per module with a hash of the source. Skip recompilation if source hash matches cached hash.

---

---

# EPIC 10: End-to-End Test Suite

A suite of complete ReFlow programs that compile and produce correct output.

---

## Story 10-1: Baseline Programs

**RT-10-1-1** `[BLOCKER]`
`tests/programs/hello.reflow`: print "Hello, World!" to stdout. Compiles, links, runs, and produces correct output.

**RT-10-1-2** `[BLOCKER]`
`tests/programs/fibonacci.reflow`: compute the nth Fibonacci number recursively. Tests recursion, integer arithmetic, and basic function calls.

**RT-10-1-3**
`tests/programs/option_test.reflow`: tests `option<T>` creation, matching, `??` operator, and auto-lifting.

**RT-10-1-4**
`tests/programs/result_test.reflow`: tests `result<T, E>` creation, matching, and `?` propagation through a call chain.

**RT-10-1-5**
`tests/programs/sum_type_test.reflow`: defines a `Shape` sum type, implements `area()` via exhaustive `match`.

**RT-10-1-6**
`tests/programs/stream_test.reflow`: creates a stream with `yield`, consumes it with `for`, tests `take` and `filter`.

**RT-10-1-7**
`tests/programs/composition_test.reflow`: tests `->` chains with fan-out, verifies result matches manual equivalent.

**RT-10-1-8**
`tests/programs/map_test.reflow`: creates a `map<string, int>`, inserts, retrieves, checks `has`, iterates keys.

**RT-10-1-9**
`tests/programs/exception_test.reflow`: throws a custom exception, catches it, verifies `ex.data` and `ex.original` are accessible.

**RT-10-1-10**
`tests/programs/retry_test.reflow`: uses `try`/`retry` with a counter to verify the named function is re-invoked the correct number of times.

**RT-10-1-11**
`tests/programs/pure_test.reflow`: a `pure fn` with a full chain, verified to compile. A non-pure call inside a `pure fn` is verified to produce a `TypeError`.

**RT-10-1-12**
`tests/programs/module_test/`: a multi-file program with two modules, one importing from the other. Verifies module resolution, export visibility, and linking.

---

## Story 10-2: Error Case Tests

**RT-10-2-1**
Write negative tests (programs that should fail to compile) for each major error class: type mismatch, non-exhaustive match, pure violation, double stream consumption, `:mut` parameter mismatch, undefined name, circular import.

Each negative test has an `expected_error` file containing the expected error code and message prefix. The test harness verifies the compiler exits with code 1 and the error message matches.

---

---

# EPIC 11: Bootstrap

Rewrite the compiler in ReFlow and compile it with itself.

---

## Story 11-1: Preparation

**RT-11-1-1** `[BLOCKER]`
Freeze the language. No new language features are added after this point until the self-hosted compiler is working. Document the freeze date in `README.md`.

**RT-11-1-2**
Write the full ReFlow standard library interfaces needed by the compiler itself:
- `io.read_file(path: string): result<string, string>`
- `io.write_file(path: string, contents: string): result<none, string>`
- `string.split(sep: string): array<string>`
- `string.starts_with(prefix: string): bool`
- `string.trim(): string`
- `array.map<T, U>(arr: array<T>, f: fn(T): U): array<U>`
- `array.filter<T>(arr: array<T>, f: fn(T): bool): array<T>`
- `sys.exit(code: int)`

These do not need to be fully specified — just enough for the compiler to use them.

---

## Story 11-2: Self-Hosted Compiler Modules

**RT-11-2-1**
Write `compiler/lexer.reflow`. Reimplement the lexer in ReFlow. It must produce identical token sequences to the Python lexer for all test inputs.

**RT-11-2-2**
Write `compiler/ast.reflow`. Define all AST nodes as ReFlow sum types and record types.

**RT-11-2-3**
Write `compiler/parser.reflow`. Reimplement the parser in ReFlow.

**RT-11-2-4**
Write `compiler/resolver.reflow`. Reimplement name resolution.

**RT-11-2-5**
Write `compiler/typechecker.reflow`. Reimplement the type checker.

**RT-11-2-6**
Write `compiler/lowering.reflow`. Reimplement the lowering pass.

**RT-11-2-7**
Write `compiler/emitter.reflow`. Reimplement the C emitter.

**RT-11-2-8**
Write `compiler/driver.reflow`. Orchestrate all passes and shell out to clang.

**RT-11-2-9**
Write `compiler/main.reflow`. Entry point with CLI argument parsing.

---

## Story 11-3: Bootstrap Verification

**RT-11-3-1** `[BLOCKER]`
Compile the self-hosted compiler using the Python compiler:
```
python main.py build compiler/main.reflow -o reflowc_stage2
```
This produces the first self-hosted binary.

**RT-11-3-2** `[BLOCKER]`
Compile the self-hosted compiler using `reflowc_stage2`:
```
./reflowc_stage2 build compiler/main.reflow -o reflowc_stage3
```
If `reflowc_stage2` and `reflowc_stage3` produce identical binaries (bit-for-bit or with deterministic output), the bootstrap is verified. This is the Makefile `make bootstrap` target.

**RT-11-3-3**
Run the full test suite with `reflowc_stage2` as the compiler. All tests that pass with the Python compiler must also pass. Any failure is a bug in the self-hosted compiler.

**RT-11-3-4**
Archive the Python compiler source in `bootstrap/python/` and update `README.md` to reflect that the canonical compiler is now `reflowc_stage2`. The Python compiler is no longer maintained but is preserved for historical bootstrapping.

---

---

# Dependency Map

```
EPIC 0 (Scaffolding)
  └─ must complete before all other epics

EPIC 1 (Runtime)
  └─ must complete before EPIC 8 (C Emitter)

EPIC 2 (Lexer)
  └─ must complete before EPIC 4 (Parser)

EPIC 3 (AST Nodes)
  └─ must complete before EPIC 4 (Parser)

EPIC 4 (Parser)
  └─ must complete before EPIC 5 (Resolver)

EPIC 5 (Resolver)
  └─ must complete before EPIC 6 (Type Checker)

EPIC 6 (Type Checker)
  └─ must complete before EPIC 7 (Lowering)

EPIC 7 (Lowering)
  └─ must complete before EPIC 8 (C Emitter)

EPIC 8 (C Emitter)
  └─ must complete before EPIC 9 (Driver)

EPIC 9 (Driver)
  └─ must complete before EPIC 10 (Tests) and EPIC 11 (Bootstrap)

EPIC 10 (Tests)
  └─ gates EPIC 11 Story 11-3 (Bootstrap Verification)

EPIC 11 (Bootstrap)
  └─ final milestone
```

---

# Estimated Ticket Counts

| Epic | Stories | Tickets |
|------|---------|---------|
| 0: Scaffolding | 3 | 8 |
| 1: Runtime | 8 | 22 |
| 2: Lexer | 4 | 13 |
| 3: AST Nodes | 5 | 8 |
| 4: Parser | 6 | 24 |
| 5: Resolver | 4 | 13 |
| 6: Type Checker | 8 | 23 |
| 7: Lowering | 5 | 20 |
| 8: C Emitter | 5 | 16 |
| 9: Driver | 2 | 7 |
| 10: Tests | 2 | 14 |
| 11: Bootstrap | 3 | 10 |
| **Total** | **55** | **178** |
