# Affine Ownership Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement affine (move) semantics for structs with refcounted fields, fixing ~1.42 MB of memory leaks in the self-hosted compiler.

**Architecture:** The lowering pass classifies types as value/refcounted/affine/trivial. Affine types use move-on-assignment (source consumed, no retain). A `_consumed_bindings` set replaces the narrower `_transferred_struct_vars` mechanism. Clone functions are generated for `@expr` on affine types. Container element destructors and sum type destructors are enabled for all affine types.

**Tech Stack:** Python 3.12 (compiler), C11 (runtime/generated code), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-03-12-affine-ownership-design.md`

**Skills:** @compiler-invariants @c-runtime @test-first @flow-spec

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `compiler/lowering.py` | Type classification, move tracking, clone gen, cleanup | Modify |
| `compiler/emitter.py` | Emit clone function definitions | Modify (minor) |
| `compiler/typechecker.py` | Consumed-binding enforcement (Phase 2) | Modify (later) |
| `tests/unit/test_lowering.py` | Unit tests for affine classification + move | Modify |
| `tests/programs/affine_move_basic.flow` | E2E: basic move and clone | Create |
| `tests/expected_stdout/affine_move_basic.txt` | Expected output | Create |
| `tests/programs/affine_clone.flow` | E2E: @copy on structs | Create |
| `tests/expected_stdout/affine_clone.txt` | Expected output | Create |
| `tests/programs/affine_container.flow` | E2E: container element cleanup | Create |
| `tests/expected_stdout/affine_container.txt` | Expected output | Create |
| `tests/programs/affine_map.flow` | E2E: map with affine values | Create |
| `tests/expected_stdout/affine_map.txt` | Expected output | Create |
| `tests/programs/affine_container_get.flow` | E2E: container get clone | Create |
| `tests/expected_stdout/affine_container_get.txt` | Expected output | Create |
| `self_hosted/*.flow` | Update for move compliance | Modify |

---

## Chunk 1: Type Classification

### Task 1: Add `_is_affine_type()` to lowering.py

**Files:**
- Modify: `compiler/lowering.py:2117-2136` (near `_has_refcounted_fields`)
- Test: `tests/unit/test_lowering.py`

- [ ] **Step 1: Write failing tests for type classification**

Add to `tests/unit/test_lowering.py`:

```python
class TestAffineClassification(unittest.TestCase):
    """Test _is_affine_type classification logic."""

    def test_value_types_not_affine(self):
        """int, float, bool, byte, char are NOT affine."""
        m = lower("fn do_stuff():int { return 0 }")
        low = _get_lowerer_for_test("fn do_stuff():int { return 0 }")
        self.assertFalse(low._is_affine_type(TInt(32, True)))
        self.assertFalse(low._is_affine_type(TFloat(64)))
        self.assertFalse(low._is_affine_type(TBool()))
        self.assertFalse(low._is_affine_type(TChar()))
        self.assertFalse(low._is_affine_type(TByte()))

    def test_refcounted_types_not_affine(self):
        """string, array, map are refcounted, not affine."""
        low = _get_lowerer_for_test("fn do_stuff():int { return 0 }")
        self.assertFalse(low._is_affine_type(TString()))
        self.assertFalse(low._is_affine_type(TArray(TInt(32, True))))
        self.assertFalse(low._is_affine_type(TMap(TString(), TInt(32, True))))

    def test_trivial_struct_not_affine(self):
        """Struct with only value fields is trivial, not affine."""
        m = lower("""
            type Point { x:int, y:int }
            fn do_stuff():int { return 0 }
        """)
        low = _get_lowerer_for_test("""
            type Point { x:int, y:int }
            fn do_stuff():int { return 0 }
        """)
        point_type = TNamed("test", "Point", ())
        self.assertFalse(low._is_affine_type(point_type))

    def test_struct_with_string_is_affine(self):
        """Struct with a string field is affine."""
        low = _get_lowerer_for_test("""
            type Token { value:string, line:int }
            fn do_stuff():int { return 0 }
        """)
        token_type = TNamed("test", "Token", ())
        self.assertTrue(low._is_affine_type(token_type))

    def test_struct_with_array_is_affine(self):
        """Struct with an array field is affine."""
        low = _get_lowerer_for_test("""
            type Container { items:array<int> }
            fn do_stuff():int { return 0 }
        """)
        container_type = TNamed("test", "Container", ())
        self.assertTrue(low._is_affine_type(container_type))
```

Note: `_get_lowerer_for_test` is a helper that must be added to `tests/unit/test_lowering.py`:

```python
def _get_lowerer_for_test(source: str) -> "Lowerer":
    """Create a Lowerer instance with pipeline state initialized (but not yet lowered).

    Runs lex→parse→resolve→typecheck, then constructs a Lowerer with
    initialized state so that classification methods like _is_affine_type
    can be called.
    """
    from compiler.lowering import Lowerer
    tokens = Lexer(source, "test.flow").tokenize()
    mod = Parser(tokens, "test.flow").parse()
    resolved = Resolver(mod).resolve()
    typed = TypeChecker(resolved).check()
    lowerer = Lowerer(typed)
    # Run lowering to populate internal state (type decl maps, etc.)
    lowerer.lower()
    return lowerer
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_lowering.py::TestAffineClassification -v`
Expected: FAIL — `_is_affine_type` does not exist

- [ ] **Step 3: Implement `_is_affine_type()`**

Add to `compiler/lowering.py` near `_has_refcounted_fields` (line ~2117):

```python
def _is_affine_type(self, t: Type) -> bool:
    """Return True if t is an affine type (struct/sum with refcounted fields).

    Type classification:
    - Value types (int, float, bool, byte, char): not affine
    - Refcounted types (string, array, map, set, buffer, stream): not affine
    - Trivial structs (only value fields): not affine
    - Structs with ≥1 refcounted/affine field: AFFINE
    - Sum types with ≥1 affine variant: AFFINE
    """
    # Value types
    if isinstance(t, (TInt, TFloat, TBool, TChar, TByte)):
        return False

    # Refcounted heap types — these use ARC, not move semantics
    if isinstance(t, (TString, TArray, TMap, TSet, TStream, TBuffer, TFn)):
        return False

    # Option/Result — check inner types
    if isinstance(t, TOption):
        return self._is_affine_type(t.inner)
    if isinstance(t, TResult):
        return self._is_affine_type(t.ok_type) or self._is_affine_type(t.err_type)

    # Named type (struct or sum) — check fields
    if isinstance(t, TNamed):
        return self._has_refcounted_fields(t)

    # Explicit sum type — check variants
    if isinstance(t, TSum):
        for variant in t.variants:
            if variant.fields:
                for field_type in variant.fields:
                    if self._is_affine_type(field_type) or self._get_release_fn(field_type):
                        return True
        return False

    # Everything else (TTypeVar, TAny, etc.) — not affine
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_lowering.py::TestAffineClassification -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `make test`
Expected: All existing tests pass (no behavior change yet)

- [ ] **Step 6: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py
git commit -m "RT-11: Add _is_affine_type() classification for move semantics"
```

---

## Chunk 2: Clone Generation for Affine Types

### Task 2: Generate clone functions for `@expr` on affine structs

**Files:**
- Modify: `compiler/lowering.py:6646-6680` (`_lower_copy`)
- Modify: `compiler/lowering.py` (add `_generate_clone_fn` method)
- Test: `tests/unit/test_lowering.py`
- Create: `tests/programs/affine_clone.flow`
- Create: `tests/expected_stdout/affine_clone.txt`

- [ ] **Step 1: Write E2E test for @copy on structs**

Create `tests/programs/affine_clone.flow`:

```flow
module tests.affine_clone

import io
import conv

type Token {
    value:string,
    line:int
}

fn print_token(tok:Token):none {
    io.println(f"{tok.value}:{conv.to_string(tok.line)}")
}

fn main():int {
    let tok = Token{value:"hello", line:1}
    let copy = @tok
    print_token(tok)
    print_token(copy)
    return 0
}
```

Create `tests/expected_stdout/affine_clone.txt`:

```
hello:1
hello:1
```

- [ ] **Step 2: Run E2E test to verify it fails**

Run: `python main.py build tests/programs/affine_clone.flow -o /tmp/fl_test && /tmp/fl_test`
Expected: Currently @copy on structs is a no-op (SPEC GAP), so both tokens share the same string pointer. This may or may not crash. If it compiles and runs, the output matches, but ASAN would show issues.

- [ ] **Step 3: Add `_generate_clone_fn` method to lowering.py**

Add a new method to the Lowerer class:

```python
def _generate_clone_fn(self, struct_type: Type, struct_lt: LType) -> str:
    """Generate a _fl_clone_<StructType> function that deep-copies an affine struct.

    The clone function copies the struct by value and retains each refcounted field.
    Returns the mangled function name.
    """
    if not isinstance(struct_lt, LStruct):
        return ""
    c_name = f"_fl_clone_{struct_lt.c_name}"

    # Don't generate duplicates
    if c_name in self._emitted_clone_fns:
        return c_name
    self._emitted_clone_fns.add(c_name)

    # Build the function body: copy struct, retain each refcounted field
    param_name = "_src"
    result_name = "_dst"
    body: list[LStmt] = []

    # let _dst = _src (shallow copy)
    body.append(LVarDecl(c_name=result_name, c_type=struct_lt,
                         init=LVar(param_name, struct_lt)))

    # Retain each refcounted field
    fields = self._get_struct_fields_cross_module(struct_type)
    if fields:
        for fname, ftype in fields.items():
            retain_fn = self._RETAIN_FN.get(type(ftype))
            if retain_fn:
                field_lt = self._lower_type(ftype)
                body.append(LExprStmt(LCall(
                    retain_fn,
                    [LFieldAccess(LVar(result_name, struct_lt), fname, field_lt)],
                    LVoid())))
            # Recursively clone nested affine fields
            elif self._is_affine_type(ftype):
                nested_lt = self._lower_type(ftype)
                nested_clone = self._generate_clone_fn(ftype, nested_lt)
                if nested_clone:
                    body.append(LAssign(
                        LFieldAccess(LVar(result_name, struct_lt), fname, nested_lt),
                        LCall(nested_clone, [LFieldAccess(LVar(result_name, struct_lt), fname, nested_lt)], nested_lt)))

    body.append(LReturn(LVar(result_name, struct_lt)))

    self._fn_defs.append(LFnDef(
        c_name=c_name,
        params=[(param_name, struct_lt)],
        ret=struct_lt,
        body=body,
        is_pure=False,
        source_name=f"clone for {struct_lt.c_name}",
    ))
    return c_name
```

Also add to `__init__`:
```python
self._emitted_clone_fns: set[str] = set()
```

- [ ] **Step 4: Update `_lower_copy` to use clone for affine types**

Replace the `case _:` fallback in `_lower_copy` (line ~6677):

```python
            case _:
                # Affine types: generate and call clone function
                if self._is_affine_type(inner_type):
                    lt = self._lower_type(inner_type)
                    clone_fn = self._generate_clone_fn(inner_type, lt)
                    if clone_fn:
                        tmp = self._fresh_temp()
                        self._pending_stmts.append(
                            LVarDecl(c_name=tmp, c_type=lt,
                                     init=LCall(clone_fn, [inner], lt)))
                        return LVar(tmp, lt)
                # Non-affine, non-heap: trivial copy
                return inner
```

- [ ] **Step 5: Run E2E test to verify it passes**

Run: `python main.py build tests/programs/affine_clone.flow -o /tmp/fl_test && /tmp/fl_test`
Expected: Output matches `affine_clone.txt`

- [ ] **Step 6: Run full test suite**

Run: `make test`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add compiler/lowering.py tests/programs/affine_clone.flow tests/expected_stdout/affine_clone.txt
git commit -m "RT-11: Generate clone functions for @expr on affine struct types"
```

---

## Chunk 3: Consumed Binding Tracking

### Task 3: Replace `_transferred_struct_vars` with `_consumed_bindings`

**Files:**
- Modify: `compiler/lowering.py` (all references to `_transferred_struct_vars`)
- Test: `tests/unit/test_lowering.py`

This task renames the existing mechanism and expands it. Currently `_transferred_struct_vars` tracks struct vars inserted into containers. The new `_consumed_bindings` tracks ALL affine bindings that have been moved (container insertion, return, assignment to another binding).

- [ ] **Step 1: Write failing test for consumed binding tracking**

Add to `tests/unit/test_lowering.py`:

```python
class TestConsumedBindings(unittest.TestCase):
    """Test that consumed (moved) bindings skip scope-exit cleanup."""

    def test_returned_affine_struct_consumed(self):
        """Returning an affine struct should consume it (no field releases)."""
        m = lower("""
            type Token { value:string, line:int }
            fn make():Token {
                let tok = Token{value:"hello", line:1}
                return tok
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "make")
        self.assertIsNotNone(fn)
        # The function should NOT have fl_string_release for tok.value
        # because tok is returned (consumed/moved to caller)
        body_str = repr(fn.body)
        self.assertNotIn("fl_string_release", body_str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_lowering.py::TestConsumedBindings -v`
Expected: FAIL — currently the lowering may still generate releases for returned struct fields

- [ ] **Step 3: Rename `_transferred_struct_vars` → `_consumed_bindings`**

In `compiler/lowering.py`, find-and-replace ALL occurrences of `_transferred_struct_vars` with `_consumed_bindings`. This is a pure rename — same semantics, new name. There are ~20 occurrences.

Also address `_collect_transferred_struct_bases` (line ~1578) and `_transferred_struct_bases` — this helper collects LVar names used as compound literal field values during container insertion. Under affine semantics, this is subsumed by `_consumed_bindings` (the entire source is consumed on container push, not just the "base" vars). Rename to `_collect_consumed_struct_bases` for now; in Chunk 8 cleanup, evaluate whether it can be removed entirely once `_consumed_bindings` properly tracks all move sources.

- [ ] **Step 4: Run full test suite to verify rename is clean**

Run: `make test`
Expected: All tests pass (pure rename, no behavior change)

- [ ] **Step 5: Mark returned affine bindings as consumed**

In `_inject_scope_cleanup` (line ~1621), when processing an `LReturn` that returns an `LVar` of an affine type, add the var to `_consumed_bindings`:

Find the section in `_inject_scope_cleanup` that processes returns. Before emitting cleanup, check if the returned expression is a direct LVar of an affine type. If so, add it to consumed_bindings and also add its fields to the skip list.

The key change: in the return path of `_inject_scope_cleanup`, when processing struct field cleanup entries, skip entries whose struct var matches the returned var name (this partially exists via `returned_field_keys` — extend it to fully skip consumed affine structs).

Additionally, in `_lower_fn_decl` around line 1140-1160, when the function body ends with `return varname` and the type is affine, mark `varname` in `_consumed_bindings` so depth-0 cleanup skips it.

- [ ] **Step 6: Mark affine assignment sources as consumed**

In `_lower_let_stmt` (wherever let statements are lowered): when processing `let b = a` where `a` is an `Ident` and the type is affine, add `a`'s C name to `_consumed_bindings`. The assignment is a move — no retain on b's fields, and a's cleanup is skipped.

Look for the let-statement lowering in `_lower_stmt` (around line 2300-2500). After lowering the init expression, if:
1. The init expression was an `Ident` (direct variable reference)
2. The type is affine (via `_is_affine_type`)

Then add the source var's C name to `_consumed_bindings`.

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_lowering.py::TestConsumedBindings -v`
Expected: PASS

Run: `make test`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py
git commit -m "RT-11: Replace _transferred_struct_vars with _consumed_bindings for affine move tracking"
```

---

## Chunk 4: Sum Type Destructors and Container Element Cleanup

### Task 4: Enable destructors for all affine sum types

**Files:**
- Modify: `compiler/lowering.py:2161-2166` (`_SAFE_SUM_TYPE_NAMES`)
- Modify: `compiler/lowering.py:2117` (`_has_refcounted_fields` — extend for sum types)
- Test: `tests/unit/test_lowering.py`

- [ ] **Step 1: Write failing test for sum type destructor generation**

Add to `tests/unit/test_lowering.py`:

```python
class TestSumTypeDestructors(unittest.TestCase):
    """Test that sum types with refcounted variants get destructors."""

    def test_sum_with_string_variant_gets_destructor(self):
        """A sum type with a string-bearing variant should generate a destructor."""
        m = lower("""
            type Item =
                | Text(value:string)
                | Number(n:int)

            fn do_stuff():int {
                let items:array<Item>:mut = []
                return 0
            }
        """)
        # Check that a _fl_destroy_* function exists for Item
        destroy_fns = [fn for fn in m.fn_defs if "_fl_destroy_" in fn.c_name and "Item" in fn.c_name]
        self.assertTrue(len(destroy_fns) > 0, "Expected destructor for sum type Item")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_lowering.py::TestSumTypeDestructors -v`
Expected: FAIL — currently sum type destructors are restricted to `_SAFE_SUM_TYPE_NAMES`

- [ ] **Step 3: Remove `_SAFE_SUM_TYPE_NAMES` restriction**

Replace the `_SAFE_SUM_TYPE_NAMES` set and its usage with `_is_affine_type()`:

In `_has_refcounted_fields` and wherever `_SAFE_SUM_TYPE_NAMES` is checked, replace:
```python
if sum_name in self._SAFE_SUM_TYPE_NAMES:
```
with:
```python
if self._is_affine_type(field_type):
```

Keep one exclusion: `TypeExpr` — this sum type has shared graph issues in the self-hosted compiler that require .flow file changes (Chunk 5). Add a comment:
```python
# TEMPORARY: TypeExpr excluded until self-hosted compiler adds @copy for shared TypeExpr values
_EXCLUDED_SUM_TYPES: set[str] = {"TypeExpr"}
```

**Migration of `_sum_type_has_cleanup_fields`:** This function (line ~2175) is currently gated by `_SAFE_SUM_TYPE_NAMES`. It's called from 6+ locations:
- `_get_or_emit_struct_handlers` (line ~2406): gate for sum type field destructors in struct handlers — **keep**, but replace `_SAFE_SUM_TYPE_NAMES` check inside with `_EXCLUDED_SUM_TYPES` exclusion check
- `_get_or_emit_sum_type_handlers` (line ~2193): gate for generating sum type handler pairs — **keep**, update gate
- `_register_struct_field_releases` and scope cleanup: **keep**, update gate
- `_inject_scope_cleanup`: **keep**, update gate

The migration: replace the `_SAFE_SUM_TYPE_NAMES` whitelist inside `_sum_type_has_cleanup_fields` with a `_EXCLUDED_SUM_TYPES` blocklist. This inverts the logic — all sum types with refcounted variants get cleanup EXCEPT excluded ones. The function itself stays as a low-level helper; `_is_affine_type` is the public classification API.

- [ ] **Step 4: Expand `_has_refcounted_fields` for sum types**

Currently `_has_refcounted_fields` only checks struct fields. Expand it to also check sum type variants:

The existing function checks struct fields via `_get_struct_fields_cross_module`. Keep that path intact, then ADD a new path for sum types after the struct check fails:

```python
def _has_refcounted_fields(self, elem_type: Type) -> bool:
    """Return True if elem_type is a struct/sum with refcounted fields."""
    # --- Existing struct field check (keep unchanged) ---
    fields = self._get_struct_fields_cross_module(elem_type)
    if fields:
        for fname, ftype in fields.items():
            if self._get_release_fn(ftype):
                return True
            if isinstance(ftype, (TNamed, TSum)) and self._has_refcounted_fields(ftype):
                return True
        # struct found but no refcounted fields
        return False

    # --- NEW: Sum type variant check ---
    # Only reached when _get_struct_fields_cross_module returned None (not a struct)
    if isinstance(elem_type, TNamed):
        # Use existing cross-module lookup (lowering.py:2138)
        decl = self._get_sum_type_decl_cross_module(elem_type)
        if decl is not None:
            # decl is a TypeDecl with .variants — each variant has typed fields
            # Walk variant fields using the typed module's type map
            for variant in decl.variants:
                for field in variant.fields:
                    field_type = self._typed.types.get(field)
                    if field_type and (self._get_release_fn(field_type)
                                      or self._has_refcounted_fields(field_type)):
                        return True
            # sum type found but no refcounted variant fields
            return False

    # Neither struct nor sum type
    return False
```

**Important:** The struct path's `return False` at the end of the `if fields:` block is preserved. The sum type check only runs when `fields` is `None` (i.e., `_get_struct_fields_cross_module` didn't find a struct). This prevents accidentally changing the semantics of the struct check path.

Note: `_get_sum_type_decl_cross_module` already exists at lowering.py:2138 and returns a `TypeDecl` or `None`. The variant fields' types are looked up from the typed module's type map.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_lowering.py::TestSumTypeDestructors -v`
Expected: PASS

Run: `make test`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py
git commit -m "RT-11: Enable sum type destructors for all affine sum types"
```

### Task 5: Generate array element destructors for affine types

**Files:**
- Modify: `compiler/lowering.py` (where `fl_array_set_struct_handlers` is generated)
- Create: `tests/programs/affine_container.flow`
- Create: `tests/expected_stdout/affine_container.txt`

- [ ] **Step 1: Write E2E test for array element cleanup**

Create `tests/programs/affine_container.flow`:

```flow
module tests.affine_container

import io
import array
import conv

type Token {
    value:string,
    line:int
}

fn main():int {
    let tokens:array<Token>:mut = []
    tokens = array.push(tokens, Token{value:"hello", line:1})
    tokens = array.push(tokens, Token{value:"world", line:2})
    io.println(f"count: {conv.to_string(array.size(tokens))}")
    // tokens goes out of scope — element destructors should free "hello" and "world"
    return 0
}
```

Create `tests/expected_stdout/affine_container.txt`:

```
count: 2
```

- [ ] **Step 2: Verify current behavior**

Run: `python main.py build tests/programs/affine_container.flow -o /tmp/fl_test && /tmp/fl_test`
Check ASAN: `ASAN_OPTIONS=detect_leaks=1 /tmp/fl_test`
Expected: Currently leaks the string fields of array elements

- [ ] **Step 3: Extend element destructor generation**

Find the code that calls `fl_array_set_struct_handlers` (search for this in lowering.py). Currently it only handles struct types checked by `_has_refcounted_fields`. With the expanded `_has_refcounted_fields` that includes sum types, this should automatically start working for sum type arrays too.

If the handler generation is gated by something other than `_has_refcounted_fields`, update the gate to use `_is_affine_type()`.

- [ ] **Step 4: Run tests and verify ASAN**

Run: `make test`
Expected: All tests pass

Run ASAN test: `python main.py build tests/programs/affine_container.flow -o /tmp/fl_test -fsanitize=address && /tmp/fl_test`
Expected: No leaks for token string fields

- [ ] **Step 5: Commit**

```bash
git add compiler/lowering.py tests/programs/affine_container.flow tests/expected_stdout/affine_container.txt
git commit -m "RT-11: Enable element destructors for arrays of affine types"
```

---

## Chunk 5: Self-Hosted Compiler Updates

### Task 6: Audit and update .flow files for move compliance

**Files:**
- Modify: `self_hosted/*.flow` (multiple files)

This task cannot have fully pre-written code because it requires analyzing the actual .flow source patterns. The steps describe the process.

- [ ] **Step 1: Identify sharing patterns in .flow source**

Search for patterns where a struct with refcounted fields is assigned to multiple bindings or passed to multiple containers:

```bash
# Find let-assignments from identifiers (potential moves)
grep -n 'let .* = [a-z_]*$' self_hosted/*.flow | head -50
```

Focus on:
1. TypeExpr values shared between Symbol structs (resolver)
2. Module/TypedModule values passed to multiple maps
3. Token values extracted and re-used

- [ ] **Step 2: Add @copy where needed**

For each identified sharing pattern, add `@` prefix to create a deep copy:

```flow
// Before (shared):
let sym = Symbol{name:name, type_ann:type_expr}
scope.define(name, sym)
parent_scope.define(name, sym)  // same sym in two scopes!

// After (move-safe):
let sym = Symbol{name:name, type_ann:type_expr}
scope.define(name, @sym)  // clone for first scope
parent_scope.define(name, sym)  // original for second scope
```

- [ ] **Step 3: Remove TypeExpr from exclusion list**

Once all sharing patterns are fixed with @copy, remove TypeExpr from `_EXCLUDED_SUM_TYPES` in lowering.py.

- [ ] **Step 4: Run full test suite**

Run: `make test`
Expected: All tests pass

- [ ] **Step 5: Run ASAN on self-hosted compiler**

```bash
python main.py build self_hosted/driver.flow -o /tmp/fl_driver
ASAN_OPTIONS=detect_leaks=1 /tmp/fl_driver emit-c tests/programs/hello.flow > /dev/null
```

Expected: Significant leak reduction from baseline (1.42 MB → target < 100 KB)

- [ ] **Step 6: Commit**

```bash
git add self_hosted/*.flow compiler/lowering.py
git commit -m "RT-11: Update self-hosted compiler for affine move semantics"
```

---

## Chunk 6: Map val_destructor Fixes

### Task 7: Fix map val_destructor generation for affine types

**Files:**
- Modify: `compiler/lowering.py` (map val_destructor generation, ~line 5004)
- Modify: `compiler/typechecker.py` (map.new type inference, if needed)

- [ ] **Step 1: Diagnose map.new() type inference gap**

The type checker returns `TMap(K, TTypeVar('V'))` for `map.new()` instead of the concrete type from the let-annotation. This blocks val_destructor setup because the lowering sees `TTypeVar` and skips.

Search for the val_destructor generation code:
```bash
grep -n "val_destructor\|val_destroy" compiler/lowering.py
```

- [ ] **Step 2: Work around TTypeVar for map val_destructor**

At the point where val_destructor is set, if the map's value type is `TTypeVar`, fall back to the let-statement's type annotation to get the concrete value type:

```python
# If value type is TTypeVar, try to resolve from the let-binding context
val_type = map_type.value
if isinstance(val_type, TTypeVar) and current_let_type:
    if isinstance(current_let_type, TMap):
        val_type = current_let_type.value
```

- [ ] **Step 3: Generate val_destructor for maps with affine values**

When a map has an affine value type, use `_get_or_emit_struct_handlers` (lowering.py:2361) which returns `(destructor_name, retainer_name)`, then call `fl_map_set_val_destructor` with all 4 required arguments:

```python
if self._is_affine_type(val_type):
    val_lt = self._lower_type(val_type)
    handlers = self._get_or_emit_struct_handlers(val_type, val_lt)
    if handlers:
        destructor, retainer = handlers
        # fl_map_set_val_destructor takes 4 args: map, destructor, retainer, sizeof_val
        stmts.append(LExprStmt(LCall(
            "fl_map_set_val_destructor",
            [map_var,
             LVar(destructor, LPtr(LVoid())),
             LVar(retainer, LPtr(LVoid())),
             LSizeOf(val_lt)],
            LVoid())))
```

Reference: See existing usage at lowering.py:5092-5104 for the exact call pattern.

- [ ] **Step 4: Write E2E test for map with affine values**

Create `tests/programs/affine_map.flow`:

```flow
module tests.affine_map

import io
import map
import conv

type Token {
    value:string,
    line:int
}

fn main():int {
    let m:map<string, Token>:mut = map.new()
    m = map.set(m, "a", Token{value:"hello", line:1})
    m = map.set(m, "b", Token{value:"world", line:2})
    io.println(f"size: {conv.to_string(map.len(m))}")
    // m goes out of scope — val_destructor should free "hello" and "world"
    return 0
}
```

Create `tests/expected_stdout/affine_map.txt`:

```
size: 2
```

- [ ] **Step 5: Run tests and verify ASAN**

Run: `make test`
Expected: All tests pass

Run ASAN test: `python main.py build tests/programs/affine_map.flow -o /tmp/fl_test -fsanitize=address && /tmp/fl_test`
Expected: No leaks for token string fields in map values

- [ ] **Step 6: Commit**

```bash
git add compiler/lowering.py
git commit -m "RT-11: Fix map val_destructor generation for affine value types"
```

---

## Chunk 7: For-Loop Borrow Semantics

### Task 8: For-loop variables borrow container elements

**Files:**
- Modify: `compiler/lowering.py` (for-loop lowering)
- Test: `tests/unit/test_lowering.py`

- [ ] **Step 1: Write test for for-loop borrow**

```python
class TestForLoopBorrow(unittest.TestCase):
    """For-loop vars over containers should borrow, not own."""

    def test_for_loop_no_field_cleanup(self):
        """For-loop variable should NOT have field cleanup at iteration end."""
        m = lower("""
            type Token { value:string, line:int }
            fn process(tokens:array<Token>):none {
                for(tok:Token in tokens) {
                    // tok borrows — no cleanup
                }
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "process")
        self.assertIsNotNone(fn)
        # The for loop body should NOT contain fl_string_release for tok.value
        # because tok is a borrowed iteration variable
```

- [ ] **Step 2: Implement for-loop borrow**

In the for-loop lowering code, when the loop iterates over a container and the element type is affine, do NOT register the loop variable for struct field cleanup. The loop variable borrows the element — the container owns it.

Find the for-loop lowering (search for `ForStmt` or `ForInStmt` handling in `_lower_stmt`). After creating the loop variable, check if the element type is affine. If so, skip the `_register_struct_field_releases` call for the loop variable.

```python
# In for-loop lowering, after declaring the loop variable:
if not self._is_affine_type(elem_type):
    # Non-affine: register normal cleanup
    self._register_struct_field_releases(loop_var_name, elem_type, elem_lt, self._scope_depth)
# Affine: skip registration (loop var borrows the element)
```

- [ ] **Step 3: Run tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py
git commit -m "RT-11: For-loop variables borrow affine elements (no cleanup per iteration)"
```

---

## Chunk 7.5: Function Param Borrow, Container-Access Clone, Spread Move

### Task 8.5a: Function parameters borrow affine structs (no callee cleanup)

**Files:**
- Modify: `compiler/lowering.py` (function param handling in scope cleanup)
- Test: `tests/unit/test_lowering.py`

Per spec Rule 2: function parameters are implicit borrows. The callee receives a stack copy but does NOT own the refcounted fields — no cleanup at callee scope exit for borrowed affine params.

- [ ] **Step 1: Write test for param borrow**

```python
class TestParamBorrow(unittest.TestCase):
    """Function params on affine types should borrow (no field cleanup)."""

    def test_affine_param_no_field_cleanup(self):
        """Affine struct param should NOT get field releases at callee scope exit."""
        m = lower("""
            type Token { value:string, line:int }
            fn process(tok:Token):int {
                return tok.line
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "process")
        self.assertIsNotNone(fn)
        # The function should NOT have fl_string_release for tok.value
        # because tok is a borrowed parameter
        body_str = repr(fn.body)
        self.assertNotIn("fl_string_release", body_str)
```

- [ ] **Step 2: Implement param borrow**

In `_inject_scope_cleanup` or wherever struct field cleanup entries are registered for function parameters: when the parameter type is affine (via `_is_affine_type`), skip registering field cleanup. The caller owns the struct; the callee just borrows.

Find where function parameters are registered for cleanup (likely in the function body lowering preamble). Add a guard:

```python
# Skip field cleanup registration for affine parameters (borrowed, not owned)
if not self._is_affine_type(param_type):
    self._register_struct_field_releases(param_name, param_type, param_lt, self._scope_depth)
```

- [ ] **Step 3: Run tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py
git commit -m "RT-11: Function params borrow affine structs (no callee cleanup)"
```

### Task 8.5b: Container access returns clone for affine elements

**Files:**
- Modify: `compiler/lowering.py` (container get/access lowering)
- Test: `tests/programs/affine_container_get.flow`
- Test: `tests/expected_stdout/affine_container_get.txt`

Per spec Rule 5: `array.get(arr, i)` returns a deep copy for affine elements (all refcounted fields retained). The container retains its original.

- [ ] **Step 1: Write E2E test for container get clone**

Create `tests/programs/affine_container_get.flow`:

```flow
module tests.affine_container_get

import io
import array
import conv

type Token {
    value:string,
    line:int
}

fn main():int {
    let tokens:array<Token>:mut = []
    tokens = array.push(tokens, Token{value:"hello", line:1})
    let got = array.get(tokens, 0)
    match got {
        some(tok): {
            io.println(f"{tok.value}:{conv.to_string(tok.line)}")
        }
        none: {
            io.println("none")
        }
    }
    io.println("done")
    return 0
}
```

Create `tests/expected_stdout/affine_container_get.txt`:

```
hello:1
done
```

- [ ] **Step 2: Verify with ASAN**

The container get for non-pointer types already uses `FL_OPT_DEREF_AS` to get a copy. For affine types, the returned copy needs its refcounted fields retained (since both the container element and the returned copy now reference the same heap data).

Check if the existing `fl_array_get_any` + `FL_OPT_DEREF_AS` pattern already copies the struct by value. If so, add a retain call for each refcounted field of the returned element (using the struct retainer from `_get_or_emit_struct_handlers`).

- [ ] **Step 3: Run tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add compiler/lowering.py tests/programs/affine_container_get.flow tests/expected_stdout/affine_container_get.txt
git commit -m "RT-11: Container get retains refcounted fields for affine elements"
```

### Task 8.5c: Struct spread (`..source`) moves source

**Files:**
- Modify: `compiler/lowering.py` (spread/RecordLit lowering)
- Test: `tests/unit/test_lowering.py`

Per spec Rule 12: `..source` moves all fields from source. Source is consumed.

- [ ] **Step 1: Write test for spread move**

```python
class TestSpreadMove(unittest.TestCase):
    """Struct spread should consume the source."""

    def test_spread_source_consumed(self):
        """Spreading a struct should add the source to consumed bindings."""
        m = lower("""
            type Token { value:string, line:int }
            fn make():Token {
                let tok = Token{value:"hello", line:1}
                let tok2 = Token{..tok, line:2}
                return tok2
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "make")
        self.assertIsNotNone(fn)
        # tok should be consumed by spread — no field releases for tok
        # Only tok2 should be returned (consumed by return)
```

- [ ] **Step 2: Implement spread as move**

In the RecordLit lowering where `..source` is processed: when the source type is affine, add the source var to `_consumed_bindings`. The spread copies all fields by value but doesn't retain — it's a move of the individual fields.

- [ ] **Step 3: Run tests**

Run: `make test`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add compiler/lowering.py tests/unit/test_lowering.py
git commit -m "RT-11: Struct spread (..source) consumes source for affine types"
```

---

## Chunk 8: ASAN Verification and Cleanup

### Task 9: Final ASAN verification and cleanup

**Files:**
- Various cleanup across `compiler/lowering.py`

- [ ] **Step 1: Run ASAN on self-hosted compiler**

```bash
# Build with ASAN
python main.py build self_hosted/driver.flow -o /tmp/fl_driver_asan -fsanitize=address

# Run against a test file
ASAN_OPTIONS=detect_leaks=1 /tmp/fl_driver_asan emit-c self_hosted/typechecker.flow > /dev/null 2> /tmp/asan_report.txt

# Check leak summary
tail -20 /tmp/asan_report.txt
```

Expected: Significant reduction from 1,420,387 bytes baseline. Target: < 100,000 bytes.

- [ ] **Step 2: Audit and remove `_is_allocating_expr` usage**

`_is_allocating_expr` is used in ~20+ locations throughout lowering.py. Under affine semantics, the allocation-vs-reference distinction is replaced by the simpler affine/non-affine classification. For each call site:

1. Search: `grep -n '_is_allocating_expr' compiler/lowering.py`
2. For each occurrence, determine if it's:
   - **For refcounted types (string, array, map):** Keep — ARC still applies
   - **For struct types:** Replace with `_is_affine_type()` check or remove entirely (move semantics handles cleanup)
   - **For return value cleanup:** Remove if `_consumed_bindings` already handles it
3. Do NOT remove `_is_allocating_expr` itself — it's still needed for ARC on refcounted types. Only remove its usage in struct-related contexts.

Key locations to audit (line numbers approximate):
- 1135, 1247: Function return cleanup — replace struct path with consumed binding check
- 1905, 1975: Let-statement retain logic — affine types don't retain on assignment
- 2549: Map/container init — may need to keep for refcounted container init
- 2706, 2785, 2834, 2902: Reassignment paths — affine uses move, not retain/release

- [ ] **Step 3: Remove other dead code**

After confirming the new mechanism works, remove remaining dead code from the old ARC-for-structs approach:
- Remove depth==0 special-case logic if fully replaced by `_consumed_bindings`
- Clean up any remaining `_SAFE_SUM_TYPE_NAMES` references
- Remove `_EXCLUDED_SUM_TYPES` if TypeExpr issue is resolved

- [ ] **Step 4: Run full test suite**

Run: `make test`
Expected: All tests pass

- [ ] **Step 5: Final commit**

```bash
git add compiler/lowering.py
git commit -m "RT-11: Clean up legacy ARC-for-structs mechanisms after affine ownership"
```

---

## Chunk 9: Typechecker Enforcement (Phase 2 — Optional for RT-11)

### Task 10: Add consumed-binding errors in typechecker

**Files:**
- Modify: `compiler/typechecker.py`
- Create: `tests/programs/errors/affine_use_after_move.flow`
- Create: `tests/expected_errors/affine_use_after_move.txt`

This task implements compile-time enforcement of move semantics. It is NOT required for the memory leak fix (the lowering handles that), but it catches bugs at compile time.

- [ ] **Step 1: Create negative test**

Create `tests/programs/errors/affine_use_after_move.flow`:

```flow
module tests.errors.affine_use_after_move

type Token {
    value:string,
    line:int
}

fn main():int {
    let tok = Token{value:"hello", line:1}
    let other = tok
    io.println(tok.value)
    return 0
}
```

Create `tests/expected_errors/affine_use_after_move.txt`:

```
TypeError
binding 'tok' was consumed by move
```

- [ ] **Step 2: Add consumed-binding tracking to typechecker**

In the typechecker, add a `_consumed: dict[str, ASTNode]` that maps consumed binding names to the AST node where they were consumed. When checking an `Ident` reference, look up the binding and check if it's consumed.

- [ ] **Step 3: Error on use of consumed binding**

When an `Ident` references a consumed binding, raise `FlowTypeError` with message indicating the binding was consumed.

- [ ] **Step 4: Run negative test**

Run: `pytest tests/programs/errors/affine_use_after_move.flow -v`
Expected: PASS (compile error matches expected)

- [ ] **Step 5: Add negative test for &expr on affine**

Create `tests/programs/errors/ref_on_affine.flow` and expected error.

- [ ] **Step 6: Run full test suite**

Run: `make test`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add compiler/typechecker.py tests/programs/errors/ tests/expected_errors/
git commit -m "RT-11: Add compile-time consumed-binding enforcement for affine types"
```

---

## Execution Notes

### Priority Order

Chunks 1-5 are the critical path for leak reduction. Execute in order:
1. Type classification (infrastructure)
2. Clone generation (enables @copy)
3. Consumed binding tracking (correct move cleanup)
4. Sum type destructors + element cleanup (biggest leak impact)
5. Self-hosted compiler updates (fix sharing patterns)

Chunks 6-7 are high-impact follow-ups. Chunk 7.5 covers three spec rules (param borrow, container-access clone, spread move). Chunk 8 is cleanup including `_is_allocating_expr` audit. Chunk 9 is optional Phase 2.

### Testing Strategy

- **Unit tests**: Test type classification and consumed binding logic
- **Golden files**: Verify generated C code structure
- **E2E tests**: Verify programs compile and run correctly
- **ASAN**: The ultimate verification — measure leak reduction
- **Negative tests**: Compile errors for move violations (Phase 2)

### Golden File Updates

Every chunk that modifies `lowering.py` may cause golden file (`tests/expected/*.c`) changes. After each `make test` run:

1. Check for golden file failures: `pytest tests/unit/test_golden.py -v` (or equivalent)
2. Regenerate: `python main.py emit-c tests/programs/<name>.flow > tests/expected/<name>.c`
3. **Review the diff carefully** before committing — verify new cleanup/clone calls are correct
4. Commit golden file updates in the same commit as the code change

### Risk Mitigation

- **UAF from shared graphs**: Keep TypeExpr excluded until .flow files are updated
- **Golden file churn**: Expect many golden files to change (new clone functions, different cleanup). Review diffs carefully.
- **Existing test failures**: The consumed binding tracking may change cleanup order. Regenerate golden files after verification.

### Key Invariants (from @compiler-invariants)

- AST nodes are immutable after parsing — all tracking is via side maps
- No pass reaches backward — consumed binding info flows forward only
- Lowering produces LModule — no C syntax in lowering
- Emitter formats LModule to C — no decisions in emitter
