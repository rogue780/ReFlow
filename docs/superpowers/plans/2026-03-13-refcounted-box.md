# FL_Box Refcounted Recursive Pointer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw `malloc`'d recursive sum type pointers with refcounted `FL_Box` wrappers, eliminating ~1.48 MB of memory leaks.

**Architecture:** Add `FL_Box` (refcount + flexible array data) to the C runtime. Change lowering.py to emit `fl_box_new` instead of `malloc`, `fl_box_retain`/`fl_box_release` instead of raw pointer sharing/leaking. Add `LBoxDeref` LIR node so the emitter produces `FL_BOX_DEREF(ptr, T)` instead of `(*ptr)`.

**Tech Stack:** Python compiler (lowering.py, emitter.py, ast_nodes.py), C runtime (flow_runtime.h/c)

**Spec:** `docs/superpowers/specs/2026-03-13-refcounted-box-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|---------------|--------|
| `runtime/flow_runtime.h` | Runtime type declarations | Add `FL_Box` struct, 3 function declarations, `FL_BOX_DEREF` macro |
| `runtime/flow_runtime.c` | Runtime implementations | Implement `fl_box_new`, `fl_box_retain`, `fl_box_release` |
| `compiler/lowering.py` | LIR node definitions + typed AST → LIR | Add `LBoxDeref` dataclass. Change variant constructor, sum type handlers, match-binding dereference, heap-boxing to use `FL_Box` |
| `compiler/emitter.py` | LIR → C source | Handle `LBoxDeref` → `FL_BOX_DEREF(ptr, T)` |
| `tests/unit/test_lowering.py` | Unit tests for lowering | Tests for box allocation, box deref, box release in sum destructors |
| Golden files (`tests/expected/*.c`) | Expected C output | Mass update — every test with recursive sum types |

---

## Chunk 1: Runtime FL_Box

### Task 1: Add FL_Box to the C runtime

**Files:**
- Modify: `runtime/flow_runtime.h`
- Modify: `runtime/flow_runtime.c`
- Test: `make test` (existing tests still pass — no lowering changes yet)

- [ ] **Step 1: Add FL_Box struct and declarations to flow_runtime.h**

Add after the FL_String section (~line 224), before the Array section:

```c
/* ========================================================================
 *  Box — Refcounted heap box for recursive sum type fields
 * ======================================================================== */

typedef struct FL_Box {
    _Atomic fl_int64 refcount;
    fl_byte data[];   /* flexible array member — holds the boxed value */
} FL_Box;

FL_Box* fl_box_new(fl_int64 size);
void    fl_box_retain(FL_Box* box);
void    fl_box_release(FL_Box* box, void (*destructor)(void*));

#define FL_BOX_DEREF(box, T) (*(T*)((box)->data))
```

- [ ] **Step 2: Implement FL_Box functions in flow_runtime.c**

Add after the string functions (~line 77), before the array section:

```c
/* ── Box ─────────────────────────────────────────────────────────────── */

FL_Box* fl_box_new(fl_int64 size) {
    FL_Box* box = (FL_Box*)malloc(sizeof(FL_Box) + size);
    if (!box) { fprintf(stderr, "fl_box_new: out of memory\n"); exit(1); }
    atomic_store(&box->refcount, 1);
    return box;
}

void fl_box_retain(FL_Box* box) {
    if (!box) return;
    atomic_fetch_add(&box->refcount, 1);
}

void fl_box_release(FL_Box* box, void (*destructor)(void*)) {
    if (!box) return;
    if (atomic_fetch_sub(&box->refcount, 1) == 1) {
        if (destructor) destructor(box->data);
        free(box);
    }
}
```

- [ ] **Step 3: Run tests**

Run: `make test`
Expected: All 1159 tests pass (no lowering changes yet, runtime additions are unused)

- [ ] **Step 4: Commit**

```bash
git add runtime/flow_runtime.h runtime/flow_runtime.c
git commit -m "RT-11: Add FL_Box refcounted heap box to runtime"
```

---

## Chunk 2: LBoxDeref LIR Node

### Task 2: Add LBoxDeref to LIR and emitter

**Files:**
- Modify: `compiler/lowering.py:194-246` (LIR dataclass definitions)
- Modify: `compiler/emitter.py:687-698` (LDeref/LOptDerefAs emission)
- Test: `make test`

- [ ] **Step 1: Add LBoxDeref dataclass to lowering.py**

Add after `LDeref` (line 197), before `LCompound` (line 200):

```python
@dataclass
class LBoxDeref(LExpr):
    """Dereference an FL_Box pointer: FL_BOX_DEREF(inner, boxed_type).

    Emits: FL_BOX_DEREF(inner, boxed_type)
    Used for recursive sum type fields stored in FL_Box.
    """
    inner: LExpr          # The FL_Box* expression
    boxed_type: LType     # The type stored in the box (e.g., LStruct("Expr"))
    c_type: LType         # Same as boxed_type (the result of dereferencing)
```

- [ ] **Step 2: Add LBoxDeref to emitter imports**

In `compiler/emitter.py` line 15, add `LBoxDeref` to the import list from `compiler.lowering`:

```python
    LFieldAccess, LArrow, LIndex, LCast, LAddrOf, LDeref, LBoxDeref,
```

- [ ] **Step 3: Add LBoxDeref emission case in emitter**

In `compiler/emitter.py`, after the `LDeref` case (line 688), add:

```python
            case LBoxDeref(inner=inner, boxed_type=bt):
                return f"FL_BOX_DEREF({self._emit_expr(inner)}, {self._emit_ltype(bt)})"
```

- [ ] **Step 4: Add LBoxDeref to the lambda rewriter**

In `compiler/lowering.py`, find the `_rewrite_expr` method that handles `LDeref` (line ~8403). Add a case for `LBoxDeref` right after:

```python
            case LBoxDeref(inner=inner, boxed_type=bt, c_type=ct):
                return LBoxDeref(self._rewrite_expr(inner, fv, fc, names), bt, ct)
```

- [ ] **Step 5: Run tests**

Run: `make test`
Expected: All tests pass (LBoxDeref exists but nothing emits it yet)

- [ ] **Step 6: Commit**

```bash
git add compiler/lowering.py compiler/emitter.py
git commit -m "RT-11: Add LBoxDeref LIR node and emitter support"
```

---

## Chunk 3: Variant Constructor — fl_box_new

### Task 3: Change variant constructor allocation from malloc to fl_box_new

**Files:**
- Modify: `compiler/lowering.py:5030-5077` (`_lower_variant_ctor`)
- Test: `tests/unit/test_lowering.py`
- Test: Golden files

This is the core change. Every recursive sum type field allocation changes from:
```c
Type* tmp = (Type*)malloc(sizeof(Type));
(*tmp) = value;
```
To:
```c
FL_Box* tmp = fl_box_new(sizeof(Type));
FL_BOX_DEREF(tmp, Type) = value;
```

- [ ] **Step 1: Write unit test for box allocation**

Add to `tests/unit/test_lowering.py`:

```python
class TestBoxAllocation(unittest.TestCase):
    """Recursive sum type fields should use FL_Box instead of raw malloc."""

    def test_recursive_field_uses_fl_box(self):
        """A sum type with a recursive pointer field should emit fl_box_new."""
        source = """
            type Expr {
                ELit(value:int),
                EUnary(op:string, inner:Expr)
            }
            fn make():Expr {
                return Expr.EUnary(op:"+", inner:Expr.ELit(value:42))
            }
            fn do_stuff():int { return 0 }
        """
        m = lower(source)
        c_code = emit(m)
        self.assertIn("fl_box_new", c_code)
        self.assertNotIn("(Expr*)malloc", c_code)
        self.assertIn("FL_BOX_DEREF", c_code)
```

Note: You'll need `emit()` helper — check if it exists in test_lowering.py. If not, add:

```python
from compiler.emitter import Emitter

def emit(m):
    """Emit C code from a lowered module."""
    return Emitter().emit(m)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_lowering.py::TestBoxAllocation -v`
Expected: FAIL — still emits `malloc`

- [ ] **Step 3: Implement box allocation in _lower_variant_ctor**

In `compiler/lowering.py`, find the recursive field allocation block (~lines 5063-5077). Change:

```python
                # BEFORE (lines 5063-5077):
                ptr_type = LPtr(alloc_lt)
                # Type* tmp = (Type*)malloc(sizeof(Type));
                self._pending_stmts.append(LVarDecl(
                    c_name=tmp,
                    c_type=ptr_type,
                    init=LCast(
                        LCall("malloc", [LSizeOf(alloc_lt)], LPtr(LVoid())),
                        ptr_type),
                ))
                # *tmp = arg;
                self._pending_stmts.append(LAssign(
                    LDeref(LVar(tmp, ptr_type), alloc_lt),
                    arg,
                ))
                inner_fields.append((fname, LVar(tmp, ptr_type)))
```

To:

```python
                # FL_Box* tmp = fl_box_new(sizeof(Type));
                box_ptr_type = LPtr(LStruct("FL_Box"))
                self._pending_stmts.append(LVarDecl(
                    c_name=tmp,
                    c_type=box_ptr_type,
                    init=LCall("fl_box_new",
                               [LSizeOf(alloc_lt)],
                               box_ptr_type),
                ))
                # FL_BOX_DEREF(tmp, Type) = arg;
                self._pending_stmts.append(LAssign(
                    LBoxDeref(LVar(tmp, box_ptr_type), alloc_lt, alloc_lt),
                    arg,
                ))
                inner_fields.append((fname, LVar(tmp, box_ptr_type)))
```

Also update the field type in the struct definition — the variant's field type for recursive fields changes from `LPtr(sum_lt)` to `LPtr(LStruct("FL_Box"))`. Find where the lowering emits the struct definition for the variant (in `_lower_sum_type_def` or similar) and change the field type for recursive fields.

- [ ] **Step 4: Update match-binding dereference sites**

Change line ~7282-7289:

```python
                                if is_recursive:
                                    # Field is a box — dereference via FL_BOX_DEREF
                                    box_ptr_lt = LPtr(LStruct("FL_Box"))
                                    field_access = LFieldAccess(
                                        LFieldAccess(subj, vname, subj.c_type),
                                        fname, box_ptr_lt)
                                    body.append(LVarDecl(
                                        c_name=binding,
                                        c_type=field_lt,
                                        init=LBoxDeref(field_access, field_lt, field_lt),
                                    ))
```

And similarly at line ~7602-7609:

```python
                                if is_recursive:
                                    box_ptr_lt = LPtr(LStruct("FL_Box"))
                                    field_access = LFieldAccess(
                                        LFieldAccess(subj, vname, subj.c_type),
                                        fname, box_ptr_lt)
                                    body.append(LVarDecl(
                                        c_name=binding, c_type=field_lt,
                                        init=LBoxDeref(field_access, field_lt, field_lt)))
```

- [ ] **Step 5: Update heap-boxing site (line ~8919)**

Check if line 8919 is for recursive sum types. If so, change `LDeref` to `LBoxDeref` and update the allocation to `fl_box_new`. If it's for a different purpose (non-recursive boxing), leave it.

- [ ] **Step 6: Update golden files**

Run: `make test`
Many golden file tests will fail because the generated C changed. For each failing golden file test, regenerate:

```bash
source .venv/bin/activate
# For each failing test, e.g. recursive_sum:
python main.py emit-c tests/programs/recursive_sum.flow > tests/expected/recursive_sum.c
```

Review each golden file diff to verify it shows the expected pattern change:
- `malloc(sizeof(Type))` → `fl_box_new(sizeof(Type))`
- `(*tmp) = value` → `FL_BOX_DEREF(tmp, Type) = value`
- `(*field)` → `FL_BOX_DEREF(field, Type)` in match bindings

- [ ] **Step 7: Run tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py tests/expected/
git commit -m "RT-11: Variant constructor uses fl_box_new instead of raw malloc"
```

---

## Chunk 4: Sum Type Destructor — fl_box_release

### Task 4: Change sum type destructor to use fl_box_release

**Files:**
- Modify: `compiler/lowering.py:2328-2351` (`_get_or_emit_sum_type_handlers`, `is_recursive` branch)
- Test: `tests/unit/test_lowering.py`
- Test: Golden files

The destructor currently calls the inner destroy function on the dereferenced pointer but does not free the pointer. With FL_Box, it calls `fl_box_release(field, destructor_fn)` which decrements the refcount and frees + destroys at 0.

- [ ] **Step 1: Write unit test for box release in destructor**

Add to `tests/unit/test_lowering.py`:

```python
class TestBoxRelease(unittest.TestCase):
    """Sum type destructors should use fl_box_release for recursive fields."""

    def test_destructor_uses_fl_box_release(self):
        """The generated destructor should call fl_box_release, not raw destroy."""
        source = """
            type Expr {
                ELit(value:int),
                EUnary(op:string, inner:Expr)
            }
            fn make():Expr {
                return Expr.ELit(value:42)
            }
            fn do_stuff():int { return 0 }
        """
        m = lower(source)
        c_code = emit(m)
        self.assertIn("fl_box_release", c_code)
        # Should NOT have the old pattern of calling destroy directly on pointer
        # The destroy function still exists — it's passed as callback to fl_box_release
```

- [ ] **Step 2: Implement fl_box_release in destructor**

In `_get_or_emit_sum_type_handlers` (~line 2328), replace the `elif is_recursive:` block:

```python
                    elif is_recursive:
                        # Recursive heap-boxed field: fl_box_release with destructor callback.
                        # The box's refcount determines when to actually free.
                        inner_type = f_type
                        inner_lt = self._lower_type(inner_type)

                        # Get the destructor function name for the boxed type
                        inner_handlers = self._get_or_emit_struct_handlers(
                            inner_type, inner_lt)
                        if inner_handlers:
                            inner_dest, _ = inner_handlers
                        else:
                            inner_dest = destructor  # self-referential

                        destroy_stmts.append(LExprStmt(LCall(
                            "fl_box_release",
                            [field_expr, LVar(inner_dest, LPtr(LVoid()))],
                            LVoid())))
                        retain_stmts.append(LExprStmt(LCall(
                            "fl_box_retain",
                            [field_expr],
                            LVoid())))
```

**Important:** The `field_expr` type also needs updating. Currently at line 2318:
```python
field_expr = LFieldAccess(variant_access, fname, field_lt)
```
When `is_recursive` is True and `field_lt` was `LPtr(sum_lt)`, it needs to become `LPtr(LStruct("FL_Box"))`:

```python
                    if is_recursive:
                        field_lt = LPtr(LStruct("FL_Box"))
```

Add this before `field_expr = LFieldAccess(...)` (or inside the `is_recursive` branch, replacing the current `field_lt = LPtr(field_lt)` at line 2316).

- [ ] **Step 3: Update golden files and run tests**

Run: `make test`
Regenerate failing golden files. Review that destructors now show `fl_box_release(field, _fl_destroy_Type)` instead of `_fl_destroy_Type(field)`.

- [ ] **Step 4: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py tests/expected/
git commit -m "RT-11: Sum type destructor uses fl_box_release for recursive fields"
```

---

## Chunk 5: Sum Type Struct Definitions

### Task 5: Update sum type struct field types from Type* to FL_Box*

**Files:**
- Modify: `compiler/lowering.py` (sum type struct definition emission)
- Test: Golden files

The struct definitions for sum type variants currently declare recursive fields as `Type*`. They need to become `FL_Box*`.

- [ ] **Step 1: Find where variant struct field types are emitted**

Search for where the lowering generates struct definitions for sum type variants. The field type for recursive fields is determined by `_is_recursive_sum_field`. Where the field type is set to `LPtr(field_lt)` for recursive fields, change it to `LPtr(LStruct("FL_Box"))`.

This is likely in `_lower_sum_type_def` or `_emit_sum_type_structs` or wherever `TypeDecl` with variants is lowered to `LTypeDef`.

- [ ] **Step 2: Update field type for recursive fields**

Wherever the sum type struct definition sets the field type for recursive fields, change:

```python
# Before:
field_c_type = LPtr(inner_lt)  # Type* field

# After:
field_c_type = LPtr(LStruct("FL_Box"))  # FL_Box* field
```

- [ ] **Step 3: Update golden files and run tests**

Run: `make test`
Regenerate golden files. Verify struct definitions show `FL_Box*` instead of `Type*`.

- [ ] **Step 4: Commit**

```bash
git add compiler/lowering.py tests/expected/
git commit -m "RT-11: Sum type variant struct fields use FL_Box* for recursive pointers"
```

---

## Chunk 6: ASAN Verification

### Task 6: Run ASAN and verify leak reduction

**Files:**
- No code changes expected (unless ASAN reveals issues to fix)

- [ ] **Step 1: Build with ASAN**

```bash
source .venv/bin/activate
python main.py emit-c self_hosted/driver.flow > /tmp/fl_driver_asan.c
clang -O0 -g -fsanitize=address -I runtime -o /tmp/fl_driver_asan /tmp/fl_driver_asan.c runtime/flow_runtime.c -lm
```

- [ ] **Step 2: Run ASAN on typechecker workload**

```bash
ASAN_OPTIONS=detect_leaks=1 /tmp/fl_driver_asan emit-c self_hosted/typechecker.flow > /dev/null 2> /tmp/asan_box.txt
tail -5 /tmp/asan_box.txt
```

Expected: Significant reduction from 1,480,458 bytes. Target: < 500,000 bytes.
Check: 0 UAF (heap-use-after-free).

- [ ] **Step 3: If UAF found, debug and fix**

UAF would indicate a code path that frees a box while another reference exists. Check:
- Are all shallow copy paths retaining the box?
- Are match bindings retaining (or just borrowing)?
- Is the retainer in `_get_or_emit_sum_type_handlers` correctly calling `fl_box_retain`?

- [ ] **Step 4: Re-enable destroy-before-reassign for :mut affine bindings**

With FL_Box, the previously-reverted destroy-before-reassign is safe. The release just decrements the refcount. Re-implement the logic from the reverted commit `7486110`, but using `fl_box_release` for sum type fields instead of calling the destructor directly.

- [ ] **Step 5: Run ASAN again after reassign fix**

```bash
python main.py emit-c self_hosted/driver.flow > /tmp/fl_driver_asan.c
clang -O0 -g -fsanitize=address -I runtime -o /tmp/fl_driver_asan /tmp/fl_driver_asan.c runtime/flow_runtime.c -lm
ASAN_OPTIONS=detect_leaks=1 /tmp/fl_driver_asan emit-c self_hosted/typechecker.flow > /dev/null 2> /tmp/asan_final.txt
tail -5 /tmp/asan_final.txt
```

- [ ] **Step 6: Commit**

```bash
git add compiler/lowering.py tests/expected/
git commit -m "RT-11: ASAN verification — FL_Box eliminates recursive pointer leaks"
```

---

## Execution Notes

### Priority Order

Tasks 1-5 form the critical path. Execute in order:
1. Runtime FL_Box (foundation — no lowering changes)
2. LBoxDeref LIR node (infrastructure — no behavior change)
3. Variant constructor allocation (the big change — malloc → fl_box_new)
4. Sum type destructor (destroy-only → fl_box_release)
5. Struct field type definitions (Type* → FL_Box*)
6. ASAN verification (measurement + optional reassign fix)

Tasks 3-5 will cause cascading golden file updates. It may be practical to combine them into a single commit if the golden file churn is too noisy to review incrementally.

### Key Invariant

After each task, `make test` must pass with 0 failures. The generated C must compile and run correctly — the FL_Box wrapping is purely a memory management change, not a semantic change.

### Golden File Strategy

Many golden files will change. The pattern to verify in each:
- `malloc(sizeof(Type))` → `fl_box_new(sizeof(Type))`
- `(Type*)malloc` cast removed (fl_box_new returns FL_Box*)
- `(*ptr) = value` → `FL_BOX_DEREF(ptr, Type) = value`
- `(*field)` in match bindings → `FL_BOX_DEREF(field, Type)`
- `_fl_destroy_Type(field)` → `fl_box_release(field, _fl_destroy_Type)`
- `_fl_retain_Type(field)` → `fl_box_retain(field)` for recursive fields
- Struct definitions: `Type* field` → `FL_Box* field`
