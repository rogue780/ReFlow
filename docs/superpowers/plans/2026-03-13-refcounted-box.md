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

Add after the numeric conversion declarations (line 223), before the Built-in Interface Helpers section (line 225):

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

Add after the `fl_string_release` function (line 76), before `fl_string_copy` (line 78):

```c
/* ── Box ─────────────────────────────────────────────────────────────── */

FL_Box* fl_box_new(fl_int64 size) {
    FL_Box* box = (FL_Box*)malloc(sizeof(FL_Box) + size);
    if (!box) fl_panic("fl_box_new: out of memory");
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

Also update the struct definition field type. In `_lower_sum_type_decl` at line 1357 of `compiler/lowering.py`, change:

```python
# Before:
if self._is_recursive_sum_field(f_type, td.name, ftype_expr):
    field_lt = LPtr(field_lt)

# After:
if self._is_recursive_sum_field(f_type, td.name, ftype_expr):
    field_lt = LPtr(LStruct("FL_Box"))
```

This must happen in the same step as the constructor change — the struct definition must declare `FL_Box*` fields to match the `FL_Box*` values the constructor assigns.

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

- [ ] **Step 5: Verify heap-boxing site (line ~8919) — no change needed**

Line 8919 is in `_heap_box_struct`, which heap-boxes structs for generic container `void*` parameters (e.g., `array.push` with a sum type value). This is NOT for recursive sum types — leave it unchanged.

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
        self.assertIn("fl_box_retain", c_code)
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

## Chunk 5: ASAN Verification

### Task 5: Run ASAN and verify leak reduction

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

- [ ] **Step 4: Write test for destroy-before-reassign**

Add to `tests/unit/test_lowering.py`:

```python
class TestDestroyBeforeReassign(unittest.TestCase):
    """Reassignment of :mut affine bindings should destroy the old value first."""

    def test_mut_affine_reassign_emits_destroy(self):
        """Reassigning a :mut sum type variable should emit a destructor call before the assignment."""
        source = """
            type Expr {
                ELit(value:int),
                EUnary(op:string, inner:Expr)
            }
            fn process():int {
                let e:Expr:mut = Expr.ELit(value:1)
                e = Expr.ELit(value:2)
                return 0
            }
            fn do_stuff():int { return 0 }
        """
        m = lower(source)
        c_code = emit(m)
        # Should have a destroy call before the reassignment
        self.assertIn("_fl_destroy_", c_code)
```

Run: `pytest tests/unit/test_lowering.py::TestDestroyBeforeReassign -v`
Expected: FAIL (destroy-before-reassign not yet implemented)

- [ ] **Step 5: Re-enable destroy-before-reassign for :mut affine bindings**

Re-apply the logic from reverted commit `7486110`. In `_lower_assign` (line ~2858 of `compiler/lowering.py`), after the release-on-reassignment block (line ~2867-2896), add a block for affine types:

```python
        # Destroy-before-reassign for :mut affine (sum type) bindings.
        # With FL_Box, this is safe: releasing the old value just decrements
        # refcounts on recursive fields. If other copies exist, the box survives.
        if (isinstance(stmt.target, Ident)
                and self._is_affine_type(self._type_of(stmt.target))
                and not self._call_passes_var_by_mut_ref(stmt.value, stmt.target.name)):
            target_type = self._type_of(stmt.target)
            # Check if RHS references the target variable (self-referencing)
            rhs_refs_target = self._collect_referenced_vars(stmt.value) & {stmt.target.name}
            if not rhs_refs_target:
                dest_fn = self._get_destructor_fn(target_type)
                if dest_fn:
                    stmts.append(LExprStmt(LCall(
                        dest_fn,
                        [LAddrOf(target, LPtr(target.c_type))],
                        LVoid())))
```

Add a `_collect_referenced_vars` helper that walks the AST to collect all `Ident` names used in an expression (to detect when the RHS references the target variable, in which case we must NOT destroy before reassign).

Run: `make test`
Expected: All tests pass

- [ ] **Step 6: Run ASAN again after reassign fix**

```bash
python main.py emit-c self_hosted/driver.flow > /tmp/fl_driver_asan.c
clang -O0 -g -fsanitize=address -I runtime -o /tmp/fl_driver_asan /tmp/fl_driver_asan.c runtime/flow_runtime.c -lm
ASAN_OPTIONS=detect_leaks=1 /tmp/fl_driver_asan emit-c self_hosted/typechecker.flow > /dev/null 2> /tmp/asan_final.txt
tail -5 /tmp/asan_final.txt
```

- [ ] **Step 7: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py tests/expected/
git commit -m "RT-11: Re-enable destroy-before-reassign for :mut affine bindings (safe with FL_Box)"
```

---

## Execution Notes

### Priority Order

Tasks 1-4 form the critical path. Execute in order:
1. Runtime FL_Box (foundation — no lowering changes)
2. LBoxDeref LIR node (infrastructure — no behavior change)
3. Variant constructor allocation + struct field types (malloc → fl_box_new, Type* → FL_Box*)
4. Sum type destructor (destroy-only → fl_box_release)
5. ASAN verification + destroy-before-reassign re-enablement

Tasks 3-4 will cause cascading golden file updates. It may be practical to combine them into a single commit if the golden file churn is too noisy to review incrementally.

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
