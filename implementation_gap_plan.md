# Flow: Spec-to-Implementation Gap Analysis & Plan

## Gap Table

| # | Feature | Spec Section | Pipeline Stage | Current Status | Gap Description |
|---|---------|-------------|----------------|----------------|-----------------|
| 1 | **Lambdas/Closures** | §Functions/Lambdas | Lowering | DONE | Closure frames, capture semantics, higher-order functions all implemented |
| 2 | **Try/Catch** | §Exception Handling | Lowering/Emitter | DONE | Full setjmp/longjmp-based try/catch with type-dispatched catch blocks |
| 3 | **Finally blocks** | §Exception Handling | Lowering/Emitter | DONE | Finally blocks run unconditionally after try/catch completion |
| 4 | **Retry blocks** | §Exception Handling | Lowering/Emitter | DONE | Retry with attempt counting and re-execution of target function |
| 5 | **Throw statement** | §Exception Handling | Lowering | DONE | Throw lowers to fl_throw() with proper exception propagation via longjmp |
| 6 | **Exception types** | §Exception Handling | Typechecker | DONE | Exception<T> interface enforcement with message/data/original method validation |
| 7 | **Coroutine operator (`:< `)** | §Coroutines | Lowering | DONE | `:< ` operator lowers to coroutine handle creation via fl_coroutine_new |
| 8 | **Coroutine methods** | §Coroutines | Typechecker/Lowering | DONE | TCoroutine type with .next(), .send(), .done() methods fully implemented |
| 9 | **TuplePattern in match** | §Pattern Matching | Lowering | DONE | TuplePattern destructuring lowers to field access on tuple struct (.f0, .f1, etc.) |
| 10 | **Parallel fan-out** | §Composition | Lowering/Runtime | DONE | Full pthreads parallel execution with safety validation, atomic refcounts, thread-local exceptions, fl_fanout_run API |
| 11 | **`snapshot()` runtime** | §Snapshot Values | Lowering/Runtime | DONE | Purity enforcement added; pass-through correct for value/immutable-heap types; .refresh() deferred as SPEC GAP (no parallelism) |
| 12 | **`typeof()` runtime** | §typeof | Lowering | DONE | Returns `TString` in typechecker; lowers to `fl_string_from_cstr` with compile-time type name |
| 13 | **Interface fulfillment** | §Interfaces | Typechecker | DONE | `fulfills` clause validates methods against interface contract; missing methods produce TypeError |
| 14 | **Stream helpers** | §Streams | Runtime/Typechecker/Lowering | PARTIAL | `take`, `skip`, `map`, `filter`, `reduce` implemented as built-in stream methods with runtime support; `zip`, `flatten`, `chunks`, `group_by` deferred as SPEC GAP |
| 15 | **`===` congruence op** | §Equality/Congruence | Typechecker/Lowering | NOT IMPL | Used internally for `coerce` but not exposed as operator in expressions |

### Priority Classification

**P0 — Must work for a complete language (blocks real programs):**
- #1 Lambdas/Closures
- #2 Try/Catch
- #3 Finally blocks
- #5 Throw statement
- #9 TuplePattern in match

**P1 — Spec-defined features that should work:**
- #4 Retry blocks
- #6 Exception type validation
- #7 Coroutine operator
- #8 Coroutine methods
- #13 Interface fulfillment validation
- #15 `===` congruence operator

**P2 — Nice to have / can use workarounds:**
- #10 Parallel fan-out (sequential works; true parallelism is runtime optimization)
- #11 `snapshot()` (can use `@copy` as workaround)
- #12 `typeof()` (static type system handles most cases)
- #14 Stream helpers (can write as user-level functions)

---

## Implementation Plan

### Phase 1: Lambda/Closure Support (Gap #1)

**Goal:** `\(x: int => x + 1)` compiles to a working C function pointer with captured variables.

**Design:** Closure = function pointer + environment pointer. The environment is a heap-allocated struct containing captured variables. At call sites, the environment is passed as a hidden first argument.

#### Step 1.1: Add LIR nodes for closures

File: `compiler/lowering.py`

Add new LIR node types:
- `LClosureDef(name, params, body, captures, ret_type)` — the generated C function (takes env* as first param)
- `LClosureCreate(fn_name, env_struct, captures)` — creates closure value (fn ptr + env)
- `LClosureCall(closure_expr, args)` — calls through closure (passes env)

File: `compiler/emitter.py`

Add emission for the new LIR nodes:
- `LClosureDef` → C function with `void* _env` first parameter, cast to env struct inside
- `LClosureCreate` → malloc env struct, populate captures, create `{fn_ptr, env_ptr}` pair
- `LClosureCall` → `closure.fn(closure.env, args...)`

#### Step 1.2: Add closure type representation

File: `runtime/flow_runtime.h`

```c
typedef struct FL_Closure {
    void* fn;      /* function pointer */
    void* env;     /* captured environment */
} FL_Closure;
```

#### Step 1.3: Implement lambda lowering

File: `compiler/lowering.py`

In `_lower_expr` case `Lambda`:
1. Identify captured variables from resolver's capture list
2. Generate env struct type with one field per captured variable
3. Generate a top-level C function that takes `(env*, params...)` and casts env
4. At the lambda expression site, emit env allocation + population + closure creation
5. Return `LClosureCreate(fn_name, env_struct, capture_exprs)`

#### Step 1.4: Implement closure call lowering

File: `compiler/lowering.py`

When a `Call` expression's callee has type `TFn` and the lowered callee is a closure:
- Emit `LClosureCall(callee, args)` instead of `LCall`

#### Step 1.5: Tests

- `tests/programs/lambda_test.flow` — lambda creation, capture, higher-order functions
- `tests/expected/lambda_test.c` — golden file
- `tests/expected_stdout/lambda_test.txt` — execution output

---

### Phase 2: Exception Handling (Gaps #2, #3, #4, #5, #6)

**Goal:** `try { ... } catch (e: MyError) { ... } finally { ... }` works with proper exception propagation and retry.

**Design:** Use `setjmp`/`longjmp` for non-local control transfer. A thread-local exception state stack tracks active try frames. `throw` calls `longjmp` to the nearest enclosing try frame.

#### Step 2.1: Runtime exception infrastructure

File: `runtime/flow_runtime.h`

```c
#include <setjmp.h>

typedef struct FL_ExceptionFrame {
    jmp_buf              jmp;
    struct FL_ExceptionFrame* parent;
    void*                exception;     /* pointer to thrown exception value */
    fl_int               exception_tag; /* type tag for catch dispatch */
} FL_ExceptionFrame;

void  fl_exception_push(FL_ExceptionFrame* frame);
void  fl_exception_pop(void);
void  fl_throw(void* exception, fl_int tag);
```

File: `runtime/flow_runtime.c`

Implement:
- Thread-local `_fl_current_exception_frame` pointer
- `fl_exception_push` — pushes frame onto stack
- `fl_exception_pop` — pops frame
- `fl_throw` — stores exception in current frame, calls `longjmp`

#### Step 2.2: Add LIR nodes for exception handling

File: `compiler/lowering.py`

New LIR statement nodes:
- `LTry(body, catches, finally_body)` — try block with catch dispatch
- `LCatch(exception_var, exception_type_tag, body)` — catch handler
- `LThrow(exception_expr, type_tag)` — throw with type tagging
- `LFinally(body)` — finally cleanup block

#### Step 2.3: Implement try/catch lowering

File: `compiler/lowering.py`

Replace `_lower_try` stub:
1. Lower try body into `LTry.body`
2. For each catch block: lower body, assign type tag, create `LCatch`
3. For finally block: lower body into `LFinally`
4. For retry blocks: generate loop wrapper with attempt counter, re-call target function

#### Step 2.4: Implement throw lowering

File: `compiler/lowering.py`

Replace `_lower_throw` stub:
1. Lower exception expression
2. Determine type tag (integer identifier for the exception type)
3. Emit `LThrow(lowered_expr, type_tag)`

#### Step 2.5: Emit exception handling C code

File: `compiler/emitter.py`

Emit `LTry` as:
```c
FL_ExceptionFrame _ef;
fl_exception_push(&_ef);
if (setjmp(_ef.jmp) == 0) {
    /* try body */
    fl_exception_pop();
} else {
    fl_exception_pop();
    /* catch dispatch: switch on _ef.exception_tag */
    if (_ef.exception_tag == TAG_MyError) {
        MyError* e = (MyError*)_ef.exception;
        /* catch body */
    } else {
        fl_throw(_ef.exception, _ef.exception_tag); /* re-throw */
    }
}
/* finally body (always runs) */
```

Emit `LThrow` as:
```c
fl_throw((void*)&exception_value, TAG_ExceptionType);
```

#### Step 2.6: Retry lowering

For retry blocks, generate:
```c
for (int _retry_count = 0; _retry_count < max_attempts; _retry_count++) {
    FL_ExceptionFrame _ef;
    fl_exception_push(&_ef);
    if (setjmp(_ef.jmp) == 0) {
        result = target_fn(args...);
        fl_exception_pop();
        break;
    } else {
        fl_exception_pop();
        if (_ef.exception_tag == TAG_ExpectedError) {
            /* retry body: mutate ex.data */
        } else {
            fl_throw(_ef.exception, _ef.exception_tag); /* re-throw */
        }
    }
}
```

#### Step 2.7: Interface fulfillment validation (Gap #6, #13)

File: `compiler/typechecker.py`

In `_build_type_registry`, when a `TypeDecl` has `interfaces`:
1. Look up each interface in the registry
2. For each method in the interface, verify the type has a matching method with compatible signature
3. Raise `TypeError` if any method is missing or has wrong signature

#### Step 2.8: Tests

- `tests/programs/exception_test.flow` — try/catch/finally with custom exception type
- `tests/programs/retry_test.flow` — retry with attempt counter and data correction
- `tests/programs/errors/missing_interface_method.flow` — negative test for fulfillment
- Golden files and expected stdout for each

---

### Phase 3: TuplePattern Matching (Gap #9)

**Goal:** `match pair { (x, y): println(f"{x}, {y}") }` works.

#### Step 3.1: Add tuple pattern lowering

File: `compiler/lowering.py`

In all match lowering methods (`_lower_match_generic`, `_lower_match_sum`, etc.), add handling for `TuplePattern`:

1. The subject is a tuple struct (e.g., `FL_Tuple_int_int`)
2. Each element in the pattern binds to the corresponding tuple field (`.f0`, `.f1`, etc.)
3. Generate `LVarDecl` for each bound variable with `init = LFieldAccess(subject, f"f{i}")`

#### Step 3.2: Tests

- `tests/programs/tuple_match_test.flow` — match on tuple values with binding
- Golden file and expected stdout

---

### Phase 4: Coroutine Support (Gaps #7, #8)

**Goal:** `let co :< gen(x)` creates a coroutine handle with `.next()`, `.send()`, `.done()`.

**Design:** A coroutine is a stream with bidirectional communication. The handle wraps an `FL_Stream*` with an additional send channel.

#### Step 4.1: Add `TCoroutine` type

File: `compiler/typechecker.py`

```python
@dataclass
class TCoroutine(Type):
    yield_type: Type   # type yielded by .next()
    send_type: Type    # type accepted by .send()
```

Update `CoroutineStart` type inference: if the call returns `TStream(T)`, the coroutine type is `TCoroutine(yield_type=T, send_type=param_type)`.

#### Step 4.2: Add coroutine runtime support

File: `runtime/flow_runtime.h`

```c
typedef struct FL_Coroutine {
    FL_Stream* stream;
    void*      send_value;    /* value passed via .send() */
    fl_bool    has_send;      /* whether send_value is populated */
    fl_bool    done;          /* coroutine finished */
} FL_Coroutine;

FL_Coroutine* fl_coroutine_new(FL_Stream* stream);
FL_Option_ptr fl_coroutine_next(FL_Coroutine* co);
void          fl_coroutine_send(FL_Coroutine* co, void* value);
fl_bool       fl_coroutine_done(FL_Coroutine* co);
void          fl_coroutine_release(FL_Coroutine* co);
```

#### Step 4.3: Lower coroutine operations

File: `compiler/lowering.py`

- `CoroutineStart(call)` → `LCall("fl_coroutine_new", [lowered_call])` wrapping the stream
- `.next()` on coroutine → `LCall("fl_coroutine_next", [co])`
- `.send(val)` on coroutine → `LCall("fl_coroutine_send", [co, val])`
- `.done()` on coroutine → `LCall("fl_coroutine_done", [co])`

#### Step 4.4: Tests

- `tests/programs/coroutine_test.flow` — create coroutine, call .next(), .send(), .done()
- Golden file and expected stdout

---

### Phase 5: Congruence Operator (Gap #15)

**Goal:** `a === b` compiles and evaluates structural congruence at runtime.

#### Step 5.1: Add `===` to binary operator handling

File: `compiler/typechecker.py`

In `_infer_expr` case `BinOp`, add `===` to comparison operators. Return `TBool()`.

File: `compiler/lowering.py`

In `_lower_binop`, handle `===`:
- For struct types: generate field-by-field type comparison (compile-time check is sufficient since types are statically known — `===` is always `true` for same-type operands and always `false` for different types)
- Emit `LLit("1", LBool())` or `LLit("0", LBool())` based on compile-time type check

#### Step 5.2: Tests

- Unit test in `test_typechecker.py` for `===` type inference
- E2E test showing `===` returns correct bool

---

### Phase 6: Deferred/Lower Priority (Gaps #10, #11, #12, #14)

These features have working workarounds and are lower priority.

#### 6.1: Parallel Fan-out (#10) — DONE

Full pthreads-based parallel execution implemented:
- Thread-local exception frames (`_Thread_local`)
- Atomic reference counting on all heap types (`_Atomic` + `atomic_fetch_add/sub`)
- `FL_FanoutBranch` struct + `fl_fanout_run()` runtime API
- Typechecker safety validation (spec lines 1604-1609): pure always safe, non-pure with `:mut` params rejected, mutable static access rejected
- Lowering generates per-branch `void*(void*)` wrapper functions and `fl_fanout_run()` calls
- `-pthread` added to clang invocation
- `# SPEC GAP: transitive mutable static analysis` — only direct body checked, not transitive callees

#### 6.2: `snapshot()` (#11)

**Decision:** Implement as `@copy` equivalent for now. The `.refresh()` method requires mutable reference tracking that is complex and not needed for bootstrap.

Implementation: In lowering, `SnapshotExpr(target)` → `LCall("fl_snapshot", [lowered_target])` which does a deep copy. Add `fl_snapshot` to runtime as alias for deep copy.

#### 6.3: `typeof()` (#12)

**Decision:** Implement as compile-time string constant. `typeof(expr)` → `fl_string_from_cstr("int")` (the type name as a string). This matches the spec's compile-time semantics.

Implementation: In lowering, `TypeofExpr(inner)` → `LCall("fl_string_from_cstr", [LLit(quoted_type_name)])`.

#### 6.4: Stream Helpers (#14)

**Decision:** Implement as stdlib functions in `stdlib/stream.flow`. These are library code, not compiler features.

Functions to implement:
- `take(s: stream<T>, n: int): stream<T>`
- `skip(s: stream<T>, n: int): stream<T>`
- `map(s: stream<T>, f: fn(T): U): stream<U>`
- `filter(s: stream<T>, pred: fn(T): bool): stream<T>`
- `reduce(s: stream<T>, init: U, f: fn(U, T): U): U`
- `zip(a: stream<T>, b: stream<U>): stream<(T, U)>`
- `flatten(s: stream<stream<T>>): stream<T>`
- `chunks(s: stream<T>, n: int): stream<array<T>>`

**Dependency:** Requires Lambda/Closure support (Phase 1) since most helpers take function parameters.

---

## Implementation Order & Dependencies

```
Phase 1: Lambdas/Closures
    ↓
Phase 2: Exception Handling (independent of Phase 1)
    ↓
Phase 3: TuplePattern (independent, small)
    ↓
Phase 4: Coroutines (depends on stream infrastructure, already done)
    ↓
Phase 5: === Operator (independent, small)
    ↓
Phase 6: Deferred items
  6.4 Stream Helpers (depends on Phase 1: lambdas)
  6.2 snapshot() (independent, small)
  6.3 typeof() (independent, small)
  6.1 Parallel fan-out (deferred to post-bootstrap)
```

Phases 1, 2, 3, and 5 can be done in parallel (no dependencies between them).
Phase 4 can start after Phase 1 if coroutine `.send()` needs closures, otherwise independent.
Phase 6.4 (stream helpers) requires Phase 1.

## Verification Checklist

After all phases complete:
- [ ] `make test` passes with zero failures
- [ ] Every feature in the gap table has at least one positive E2E test
- [ ] Every feature that can fail has at least one negative test
- [ ] All golden files reviewed and committed
- [ ] No SPEC GAP comments remain for implemented features
- [ ] No stub/NULL returns remain in lowering.py for implemented features
