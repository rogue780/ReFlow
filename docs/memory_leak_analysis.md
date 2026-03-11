# Memory Leak Analysis & Refcounting Completion Plan

## Status as of 2026-03-10

### What Was Done (6 commits on `story/RT-11-self-hosted-compiler`)

1. **Struct-construction retains** — `_retain_struct_fields` helper retains borrowed refcounted fields at ALL 6 positional struct/variant construction sites + `_lower_type_lit` (brace construction). Previously only brace construction retained fields.

2. **Scope-exit cleanup for all locals** — ALL refcounted locals (regardless of `:mut`/`:imut`, allocating/non-allocating) are now registered in `_container_locals` for release at scope exit.

3. **Inner-scope cleanup** — `_container_locals` is now a 4-tuple `(name, c_type, release_fn, depth)`. Block-scoped locals at depth > 0 are released when their block exits via `_inject_scope_cleanup`. Void-function trailing cleanup filters to depth-0 only.

4. **String temp hoisting expansion** — `_hoist_string_temp` now hoists ALL string-returning `LCall`s (not just a hardcoded whitelist). Uses `_NON_OWNED_STRING_FNS` exclusion set.

5. **Return-path temp release** — `_post_stmts` (string temp releases) are now inserted BEFORE `LReturn` statements instead of being dropped. Uses `_collect_referenced_vars` to skip temps referenced in the return expression.

6. **In-place string append** — New runtime function `fl_string_append(FL_String** a, FL_String* b)` does in-place realloc when refcount==1. Lowering detects `x = x + y` pattern for `:mut` string bindings and generates `fl_string_append(&x, y)` instead of `fl_string_concat`.

**RSS progression**: 873 MB → 872 → 869 → 851 → 847 → 846 MB (typechecker test)

---

## ASAN Leak Analysis

Running ASAN with `detect_leaks=1` on the self-hosted typechecker test compiling `hello_world.flow`:

**Total: 1,035,247 bytes leaked in 2,989 allocations**

### Breakdown by type:

| Category | Bytes | % | Leak Sites | Description |
|----------|-------|---|------------|-------------|
| Arrays | 795,776 | 76.9% | 486 | Token arrays, AST node arrays, scope arrays |
| Maps | 83,804 | 8.1% | 583 | Scope maps, type registries, symbol tables |
| Strings | 13,973 | 1.3% | 160 | String intermediates in expressions |
| Hash internals | 141,694 | 13.7% | 253 | Backing stores of leaked maps/arrays |

### Top leaking functions:

| Function | map.set leaks | array.push leaks | What's leaking |
|----------|---------------|-------------------|----------------|
| `register_builtin_method_sigs` | 168 | 120 | Method signature maps built per typecheck call |
| `register_builtin_interfaces` | 90 | 81 | Interface registry maps |
| `register_builtin_fulfillments` | 90 | — | Fulfillment maps |
| `lexer.emit` | — | 39 | Token array (grows via push) |
| `resolver.define_symbol` | 12 | 18 | Symbol table maps |
| `typechecker.node_set_type` | 16 | — | Node-type association map |
| `parser.parse_block` | — | 7 | AST block statement arrays |

---

## Root Cause: Incomplete Refcounting

The refcounting system is incomplete in **three specific ways**:

### Gap 1: Struct fields are not released at scope exit

When a local variable holds a struct (like `TypedModule`, `ResolvedModule`, `TCState`), the scope-exit cleanup releases the **top-level local** but does NOT recursively release the struct's **refcounted fields**.

Example:
```flow
fn typecheck_source(src:string):TypedModule {
    let tokens = lexer.tokenize(src, "test.flow")    // tokens: array<Token>
    let result = parser.parse(tokens, "test.flow")    // result: ParseResult (has .parsed_module field with arrays)
    let rm = resolver.resolve(...)                     // rm: ResolvedModule (has maps, arrays inside)
    return typechecker.typecheck(rm, ...)              // returns TypedModule
}
// At scope exit:
// - `tokens` array is released (scope-exit cleanup works for plain arrays)
// - `result` struct is stack-allocated, but its .parsed_module.body (array) is NOT released
// - `rm` struct is stack-allocated, but its .symbols (map), .scope_names (array) etc. are NOT released
```

The lowering generates `fl_array_release(tokens)` at scope exit because `tokens` is a direct array local. But for `result` (a struct), it doesn't know to generate `fl_array_release(result.parsed_module.body)` etc.

**Fix needed**: When a struct local goes out of scope, generate release calls for each of its refcounted fields. This requires the lowering to walk the struct's type definition and emit field-by-field release code.

### Gap 2: Returned struct fields that aren't extracted leak

In `typecheck()`:
```flow
fn typecheck(...):TypedModule {
    let s:TCState:mut = make_state(...)
    // s has ~15 map/array fields
    // ...
    return TypedModule{
        src_module: s.src_module,
        node_types: s.node_types,      // extracted — ownership transfers
        warnings: s.warnings,          // extracted — ownership transfers
        ...
    }
    // At scope exit: s.type_registry, s.iface_registry, s.scope_names,
    // s.scope_type_arr, s.scope_map, s.mod_scope_map — ALL LEAK
    // because they're not in the return value and not explicitly released
}
```

**Fix needed**: Same as Gap 1 — struct field release at scope exit. The fields that are transferred to the return value need to NOT be released (they're now owned by the caller). This is the tricky part: the lowering needs to know which fields were "moved out" vs which are still owned by the struct.

### Gap 3: `array.push` / `map.set` intermediate array versions leak

```flow
let arr:array<Token>:mut = []
arr = array.push(arr, token1)   // old [] leaks
arr = array.push(arr, token2)   // old [token1] leaks
arr = array.push(arr, token3)   // old [token1, token2] leaks
```

Each `array.push` returns a NEW array. The reassignment `arr = new_arr` releases the old `arr` (scope-exit cleanup handles the final value), but the release-on-reassignment pattern in lowering should handle this... Let's verify it does.

**Status**: This MAY already be handled by `_lower_assign` which generates release-before-reassign for refcounted locals. Need to verify with ASAN that this specific pattern doesn't leak.

---

## Implementation Plan for Zero Memory Leaks

### Phase 1: Struct Field Release at Scope Exit (HIGH IMPACT)

**Goal**: When a struct-typed local goes out of scope, release all its refcounted fields.

**Approach**: In the lowering, when generating scope-exit cleanup for a local whose type is a struct (TStruct, TNamed referring to a type with fields), walk the type's field definitions and emit release calls for each refcounted field.

```python
# Pseudocode for the lowering
def _generate_struct_release(self, var_name: str, struct_type: Type) -> list[LStmt]:
    stmts = []
    for field in struct_type.fields:
        field_type = field.type
        release_fn = self._get_release_fn(field_type)
        if release_fn:
            field_access = LFieldAccess(LVar(var_name), field.name)
            stmts.append(LExprStmt(LCall(release_fn, [field_access], LVoid())))
    return stmts
```

**Complications**:
1. Recursive structs (struct A has field of type A) — need cycle detection
2. Fields that were "moved out" into a return value — should NOT be released
3. Sum type variants — each variant may have different fields
4. Nested structs — need recursive descent into struct fields

**Estimated impact**: Would eliminate ~80% of remaining leaks (all the TCState, ResolvedModule, ParseResult field leaks).

### Phase 2: Verify `array.push` / `map.set` Reassignment Release

**Goal**: Confirm that `arr = array.push(arr, val)` properly releases the old array.

**Approach**: Check `_lower_assign` for release-before-reassign logic. If missing, add it.

**Estimated impact**: Would eliminate the remaining array/map growth leaks.

### Phase 3: Release Semantics for Returned Structs

**Goal**: When a function returns a struct, the caller owns it. When the caller is done with it, the struct's fields need release.

**Approach**: This is the same as Phase 1 applied to the caller side — when the TypedModule returned by `typecheck_source()` goes out of scope in `test_int_return()`, its fields should be released.

### Phase 4: In-place `array.push` / `map.set` for `:mut` (OPTIMIZATION)

**Goal**: Like `fl_string_append`, add `fl_array_push_inplace` and `fl_map_set_inplace` that reuse the existing buffer when refcount == 1.

**Approach**: Same pattern as `fl_string_append` — detect `arr = array.push(arr, val)` pattern in lowering and generate `fl_array_push_inplace(&arr, val)`.

**Estimated impact**: Reduces allocation pressure and memory fragmentation. Doesn't fix leaks per se (Phase 2 handles that) but reduces RSS.

---

## Key Files

- `compiler/lowering.py` — All refcounting logic lives here
  - `_container_locals` — tracks locals for scope-exit release (4-tuple: name, c_type, release_fn, depth)
  - `_retain_struct_fields` — retains borrowed fields in struct construction
  - `_inject_scope_cleanup` — generates block-scoped release calls
  - `_get_release_fn` — maps types to release function names
  - `_RETAIN_FN` — maps type classes to retain function names
  - `_is_allocating_expr` — determines if an expression allocates (to avoid double-retain)
  - `_hoist_string_temp` — hoists string-returning calls to temps with scheduled release
- `runtime/flow_runtime.c` — Runtime release functions
  - `fl_array_release` — releases array and its elements (based on elem_type)
  - `fl_map_release` — releases map and its values (based on val_type)
  - `fl_string_release` — decrements refcount, frees at 0
  - `fl_string_append` — in-place string concat for :mut bindings
- `runtime/flow_runtime.h` — Declarations

## Relevant Struct Types That Need Field Release

These are the main structs in the self-hosted compiler that hold refcounted fields and currently leak:

1. **TCState** (`self_hosted/typechecker.flow:189`) — ~15 map/array fields
2. **ResolvedModule** (`self_hosted/resolver.flow`) — symbols map, scope arrays
3. **ParseResult** (`self_hosted/parser.flow`) — parsed_module with body arrays
4. **Module** (`self_hosted/ast.flow`) — body array, imports array
5. **TypedModule** (`self_hosted/typechecker.flow`) — node_types map, warnings array
6. **Token** (`self_hosted/ast.flow`) — value string field
