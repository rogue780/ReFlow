# Self-Hosted Refcount Cleanup — Design Spec

## Problem

The self-hosted compiler (`self_hosted/lowering.flow`) emits zero refcount release calls. The Python compiler's `lowering.py` has ~200 lines of cleanup machinery that tracks refcounted locals and emits `fl_array_release()`, `fl_string_release()`, etc. at scope exit. The self-hosted lowering never ported this. Result: stage 2 leaks every allocation and OOMs on multi-module programs (~120 MB for a 6-module SSH app before crashing).

## Goal

Port the full refcount cleanup system from `compiler/lowering.py` to `self_hosted/lowering.flow` so that code compiled by the self-hosted compiler has the same release behavior as code compiled by the Python compiler. This includes both the **retain** side (bumping refcounts on shared references) and the **release** side (decrementing refcounts at scope exit).

## What Gets Ported

### 1. State Tracking (new fields on LowerState)

Add these fields to the `LowerState` struct in `lowering.flow`:

```
// Cleanup tracking
scope_depth:int
container_locals:array<ContainerLocal>
struct_field_cleanup:array<StructFieldCleanup>
sum_field_cleanup:array<SumFieldCleanup>
affine_locals:array<AffineLocal>
consumed_bindings:map<string, bool>
struct_handler_emitted:map<string, bool>
```

Supporting types:

```
type ContainerLocal {
    var_name:string
    c_type:lir.LType
    release_fn:string
    depth:int
}

type StructFieldCleanup {
    struct_var:string
    field_name:string
    struct_c_type:lir.LType
    release_fn:string
    depth:int
    block_safe:bool
}

type SumFieldCleanup {
    struct_var:string
    field_name:string
    struct_c_type:lir.LType
    destructor_fn:string
    field_ltype:lir.LType
    depth:int
}

type AffineLocal {
    var_name:string
    c_type:lir.LType
    destructor_fn:string
    depth:int
}
```

All cleanup state is reset at the start of each function body lowering (`lower_fn_def`, `lower_method`).

### 2. Type Classification

**`get_release_fn(t:TCType):option<string>`** — returns the release function name for directly-refcounted types:
- TCString → `"fl_string_release"`
- TCArray → `"fl_array_release"`
- TCMap → `"fl_map_release"`
- TCStream → `"fl_stream_release"`
- TCBuffer → `"fl_buffer_release"`
- TCFn → `"fl_closure_release"`
- Everything else → none

**`get_retain_fn(t:TCType):option<string>`** — returns the retain function name:
- TCString → `"fl_string_retain"`
- TCArray → `"fl_array_retain"`
- TCMap → `"fl_map_retain"`
- TCStream → `"fl_stream_retain"`
- TCBuffer → `"fl_buffer_retain"`
- TCFn → `"fl_closure_retain"`
- Everything else → none

**`is_affine_type(t:TCType):bool`** — classifies types:
- Value types (int, float, bool, byte, char) → false
- Refcounted types (string, array, map, etc.) → false (handled by ARC directly)
- Option/Result → affine if inner is affine
- Struct with any refcounted/affine field → true
- Sum with any affine variant → true
- Everything else → false

**`has_refcounted_fields(t:TCType):bool`** — recursively checks if a type contains any refcounted fields (direct or nested). Uses a visited set to prevent infinite recursion on recursive types.

**`sum_type_has_cleanup_fields(t:TCType):bool`** — checks if a sum type has variants with refcounted fields.

**`is_allocating_expr(expr:ast.Expr, t:TCType):bool`** — determines whether an expression produces a fresh heap allocation or returns a shared reference. This classification controls retain emission and the `block_safe` flag:
- Function calls (ECall, EMethodCall) → true (allocating)
- String/array literals → true (allocating)
- Identifiers, field access, index → false (shared reference)
- Everything else → false (conservative: treat as shared)

**Important:** TypeLit and RecordLit are NOT allocating expressions (they produce compound literals on the stack). They are handled separately in `lower_let` as a distinct case from the allocating check. Misclassifying them as allocating would cause the lowering to skip struct field retains (going down the `block_safe=False` path instead of the retain-at-construction path).

**`is_allocating_lir_expr(expr:lir.LExpr):bool`** — LIR-level version for post-lowering decisions (inject_scope_cleanup hoist check):
- LECall, LEIndirectCall, LECompound → true
- Everything else → false

### 3. Retain-on-Store (the other half of ARC)

Releases without retains cause use-after-free. The retain side must be ported alongside the release side.

**When to emit retains:**

1. **Non-allocating `let` binding of refcounted type**: `let x = param` where `param` is a string/array/map — emit `fl_string_retain(x)` after the var decl.

2. **Non-allocating struct construction**: When a struct is built from non-allocating sources, emit `fl_X_retain(var.field)` for each refcounted field value that is a shared reference.

3. **Return-site retain**: When a function returns a non-allocating expression of refcounted type, emit `fl_X_retain(result)` before the return. This ensures the owned-return convention (callers may release the returned value).

4. **Reassignment retain**: When `:mut` binding is reassigned to a non-allocating source, retain the new value (after releasing the old).

### 4. Registration (in lower_let)

When lowering `let x:T = expr`:

1. **Directly refcounted type** (string, array, map, etc.):
   - Append to `container_locals` with current `scope_depth` and release function
   - If `is_allocating_expr(expr)` is false: emit retain call after var decl
   - If container is an empty array with type annotation: emit `fl_array_set_elem_type` or `fl_array_set_struct_handlers` for proper element cleanup

2. **Struct with refcounted fields**: call `register_struct_field_releases()` which walks DIRECT fields only:
   - For each refcounted field → append to `struct_field_cleanup`
   - For each sum type field with cleanup → append to `sum_field_cleanup`, emit destructor if not already emitted
   - `block_safe` flag based on source:
     - TypeLit/RecordLit → `true` (fields are freshly constructed)
     - Function call result → `false` (may return borrowed fields)
     - Affine move (`let b = a`) → `true`, mark `a` consumed
     - Non-allocating source → emit retain on each refcounted field, `block_safe = true`

3. **Affine sum type with :mut** → append to `affine_locals` (currently disabled in Python compiler via `if False` guard — port as disabled, with comment noting the UAF issue)

### 5. Consumed Binding Tracking

Mark bindings as consumed (skip their cleanup) when:
- Moved into another variable (`let b = a` where a is affine)
- Stored by reference in a container (`array.push_ptr(arr, x)`)
- Returned from function
- Assigned to another binding via `:mut` reassignment

Check `consumed_bindings` map before emitting any release.

### 6. Release-on-Reassignment (for :mut variables)

When a `:mut` variable of refcounted type is reassigned (`x = new_value`):

**Allocating RHS** (function call, literal):
```c
FL_String* _old = x;
x = new_allocating_call();
if (_old != x) fl_string_release(_old);
```

**Non-allocating RHS** (identifier, field access):
```c
FL_String* _old = x;
x = other_var;
if (_old != x) { fl_string_retain(x); fl_string_release(_old); }
```

For FieldAccess targets (`s.field = new_value`): same patterns apply to the field.

For affine `:mut` reassignment: emit destroy-before-reassign using the type's destructor.

### 7. String Temp Hoisting

Intermediate string-returning calls in concat chains (like `a + b + c`) produce temporaries that leak. Port `_hoist_string_temp()`:

When lowering a string concat or function call that returns a string within a larger expression:
1. Evaluate the sub-expression into a temp: `FL_String* _fl_tmp_N = sub_expr;`
2. Register `_fl_tmp_N` in `container_locals` for cleanup
3. Use `_fl_tmp_N` in the parent expression

This ensures intermediate strings are released at scope exit.

### 8. Function-Exit Cleanup (inject_scope_cleanup)

After lowering the entire function body, walk all statements and inject cleanup before each `LSReturn`:

1. Collect variables referenced in the return expression → protect from release
2. Collect "returned field keys" — dotted paths like `s.name` used in compound return literals → skip release
3. Collect "consumed struct bases" — variables whose fields are transferred to the return value → skip field cleanup
4. Check if return expression needs hoisting (references variables that need cleanup but isn't a simple LVar):
   - If yes: emit `tmp = return_expr; cleanup_calls; return tmp;`
   - If no: emit `cleanup_calls; return original_expr;`
5. For void functions: also append cleanup at end of body (no explicit return)

The `containers_only` flag: when recursing into while loop bodies during cleanup injection, set `containers_only=true` to avoid releasing struct fields with borrowed references (only release containers which are safely reference-counted).

Cleanup order:
1. Container locals (depth 0 only for function exit)
2. Struct field releases (all entries, including `block_safe=false`)
3. Sum type field releases
4. Affine local destructors

Skip conditions per variable:
- Not at correct depth
- Referenced in return expression (unless hoisted)
- In `consumed_bindings`
- Embedded in returned struct literal (shallow copy)
- Part of returned field keys (transferred to return value)

Deduplication: maintain `seen_containers`, `seen_fields`, `seen_affine` sets to prevent double-release when the same variable appears at multiple depths.

### 9. Block-Exit Cleanup (emit_block_exit_cleanup)

After lowering an inner block (if body, else body, match arm):

1. Skip if block ends with LSReturn, LSBreak, LSContinue, or `_fl_throw`
2. Skip if `all_paths_exit()` returns true
3. Only process entries registered AFTER the snapshot indices (this block's scope)
4. Only process depth-matching entries
5. Only check variables that have an `LSVarDecl` at the top level of the body
6. **Only emit struct field cleanup for `block_safe=true` entries** (Call results deferred to function exit)
7. Append release calls at end of block body

Uses snapshot-based scoping: save `len(container_locals)`, `len(struct_field_cleanup)`, `len(sum_field_cleanup)` before lowering block, only process entries after those indices.

### 10. Loop-End Cleanup (emit_loop_end_cleanup)

After lowering a for/while loop body:

1. Collect variables stored by reference in containers (push_ptr) → skip these
2. Release all non-consumed, non-push_ptr container locals registered during the loop body
3. Only struct field cleanup with `block_safe=true`
4. Sum field cleanup for matching entries
5. Only entries registered during this loop's body (after snapshot indices)

### 11. Sum Type Handlers (Destructors + Retainers)

For sum types with refcounted variants, emit both a destructor AND retainer:

**Destructor** (`_fl_destroy_TypeName`):
```c
void _fl_destroy_TypeName(void* ptr) {
    TypeName* self = (TypeName*)ptr;
    switch (self->tag) {
        case 0: {
            fl_string_release(self->Variant.name);
            break;
        }
        case 1: {
            fl_array_release(self->Variant.items);
            break;
        }
    }
}
```

**Retainer** (`_fl_retain_TypeName`):
```c
void _fl_retain_TypeName(void* ptr) {
    TypeName* self = (TypeName*)ptr;
    switch (self->tag) {
        case 0: {
            fl_string_retain(self->Variant.name);
            break;
        }
        case 1: {
            fl_array_retain(self->Variant.items);
            break;
        }
    }
}
```

Track in `struct_handler_emitted` to avoid duplicates. Emitted as top-level `LFnDef` nodes added to the LModule.

### 12. Struct Handlers (Destructors + Retainers)

For structs with refcounted fields, emit destructor/retainer pairs:

**Destructor** (`_fl_destroy_StructName`): release each refcounted field.
**Retainer** (`_fl_retain_StructName`): retain each refcounted field.

Used by:
- `fl_array_set_struct_handlers(arr, destructor, retainer)` — enables arrays of structs to properly manage element lifetimes
- Nested struct field destruction within sum type destructors
- Destroy-before-reassign for affine struct types

### 13. Clone Functions

For affine types, emit `_fl_clone_TypeName(src)` that deep-copies all fields:
- Value fields: copy directly
- Refcounted fields: retain (bump refcount, share reference)
- Affine nested fields: recursively clone

Used when an affine binding is used after being passed to a function (clone on access pattern).

### 14. Discarded Allocating Return Value Release

When a function call returns a refcounted value that is used as an expression statement (result discarded), the return value leaks. Port `_lower_expr_stmt`:

```c
// arr = array.push(arr, x)  -- return value used, no leak
// array.push(arr, x)        -- return value discarded, LEAKS without this
```

When lowering `SExpr` where the expression is a function call returning a refcounted type:
1. Hoist to temp: `FL_String* _fl_tmp_N = call();`
2. Emit the call as a var decl
3. Immediately release: `fl_string_release(_fl_tmp_N);`

This is a high-frequency leak path — any function called for side effects whose return value is refcounted.

### 15. Retain During Struct/Variant Construction

Port `_retain_struct_fields()`: when constructing a struct or variant via TypeLit, RecordLit, or positional construction, retain each refcounted field value that comes from a non-allocating source.

Call sites:
- TypeLit lowering (struct construction `Foo{name: x}`)
- RecordLit lowering
- Positional struct construction in call lowering
- Variant constructors

### 16. String Append Optimization

The release-on-reassignment path (Section 6) has a critical special case: `x = x + y` for `:mut` string variables converts to `fl_string_append(&x, y)` instead of allocating a new string. This avoids allocation when refcount is 1 and bypasses the release-on-reassignment path entirely. Without this, every string append in a loop allocates, releases, and retains — much slower and more leak-prone.

### 17. Bulk String Argument Hoisting

Port `_hoist_string_args()`: before calling non-storing functions like `fl_string_concat`, `fl_string_eq`, hoist ALL string-returning arguments to temps and register for cleanup.

Exclusion list (storing functions where hoisting causes UAF): `fl_array_push_sized`, `fl_map_set`, `fl_map_set_str`, and similar functions that take ownership of the argument.

### 18. Array Element Type Registration

When lowering empty array literals with type annotations, emit runtime calls to register the element type:
- `fl_array_set_elem_type(arr, FL_ELEM_STRING)` for `array<string>`
- `fl_array_set_struct_handlers(arr, destructor, retainer)` for `array<StructType>`

Without this, the runtime cannot retain/release elements during push/copy/free operations.

### 15. Helper Functions

**`collect_referenced_vars(expr:lir.LExpr):map<string, bool>`** — recursively walk LExpr, return all LVar names.

**`collect_returned_field_keys(expr:lir.LExpr):map<string, bool>`** — collect dotted field access patterns in return expressions (e.g., `s.src` → skip release of `s.src`).

**`collect_consumed_struct_bases(expr:lir.LExpr):map<string, bool>`** — collect LVar names used as compound literal field values (transferred to return).

**`collect_push_ptr_vars(stmts:array<lir.LStmtBox>):map<string, bool>`** — find variables stored by reference in containers.

**`collect_retained_vars(stmts:array<lir.LStmtBox>):map<string, bool>`** — find variables that received retain calls.

**`all_paths_exit(stmts:array<lir.LStmtBox>):bool`** — check if all leaf paths end with return/break/continue.

**`emit_struct_field_release(struct_var:string, field_name:string, struct_c_type:lir.LType, release_fn:string):lir.LStmt`** — build `LExprStmt(LCall(release_fn, [field_access]))`. Handles dotted struct_var names by building nested field accesses.

**`emit_sum_field_release(struct_var:string, field_name:string, struct_c_type:lir.LType, destructor_fn:string, field_lt:lir.LType):lir.LStmt`** — build `LExprStmt(LCall(destructor_fn, [&field_access]))`.

**`get_struct_fields_cross_module(t:TCType):map<string, TCType>?`** — resolve struct field definitions across imported modules. The self-hosted lowering already has cross-module resolution infrastructure (`imported_module_keys`, `imported_module_decls`) that this can use.

## Scope-Depth Model

- `scope_depth = 0`: function parameters and top-level locals
- `scope_depth >= 1`: locals inside if/else/match/for/while blocks
- Increment on entering inner block, decrement on exit
- Function-exit cleanup processes depth 0 entries
- Block-exit cleanup processes entries matching the block's depth

## Integration Points in lowering.flow

| Location | What happens |
|----------|-------------|
| `lower_fn_def` / `lower_method` | Reset all cleanup state, set depth=0 |
| `lower_let` | Register cleanup entries, emit retains for non-allocating sources |
| `lower_assign` (`:mut` reassign) | Release old value, retain new if non-allocating, track consumption |
| `lower_return` | Retain non-allocating return values (owned-return convention) |
| `lower_block` | Save snapshots, increment depth, lower stmts, emit block-exit cleanup, decrement depth |
| `lower_if` / `lower_match` | Manage snapshots for each arm/body |
| `lower_for` / `lower_while` | Save snapshots, lower body, emit loop-end cleanup |
| After full function body lowered | Call `inject_scope_cleanup` to insert pre-return releases |
| String concat / call lowering | Hoist intermediate string temps, register for cleanup |
| Empty array literal with type ann | Emit `fl_array_set_elem_type` / `fl_array_set_struct_handlers` |

## Edge Cases and Guards

### Duplicate Variable Deduplication
When the same variable name is declared at different scope depths (e.g., `raw` in both branches of an if/else), keep the shallowest-depth entry in `container_locals`. Without this, the variable is double-released at function exit.

### :mut ref Guard for Release-on-Reassignment
The release-on-reassignment and destroy-before-reassign paths must check whether the RHS call passes the target variable by `:mut` reference. If so, skip the release — the callee handles cleanup internally through the pointer. Guard: `not call_passes_var_by_mut_ref(rhs_expr, target_name)`.

### sum_field_cleanup Population
`sum_field_cleanup` is populated for direct sum-typed locals, NOT for sum-type fields found during `register_struct_field_releases`. The Python compiler explicitly does not register scope-exit cleanup for sum-type fields within structs because local variables hold shallow copies with shared heap-boxed pointers — destroying them at scope exit would double-release internals. `register_struct_field_releases` only ensures handlers are emitted (for array element destructors) via `get_or_emit_sum_type_handlers`.

### Void Function Trailing Cleanup
Both `lower_fn_def` and `lower_method` need trailing cleanup for void functions (no explicit return). After `inject_scope_cleanup` processes return statements, append depth-0 releases at the end of the body for functions that may fall through without returning.

### Sequencing: Tail Return Injection Before Cleanup
For expression-body functions, `inject_tail_returns` converts the last expression into an `LSReturn` (with retain for non-allocating expression bodies). This runs BEFORE `inject_scope_cleanup`. The implementer must respect this ordering: tail return injection first (with retain), then scope cleanup injection.

## What This Does NOT Change

- LIR node definitions in `lir.flow` — no new node types needed
- Emitter in `emitter.flow` — cleanup LIR is just `LExprStmt(LCall(...))`, already supported
- Runtime — all release/destroy/retain functions already exist
- Python compiler — no changes needed

## Testing

After implementation:
1. `make test` must pass (Python compiler unchanged)
2. Rebuild stage 1 → stage 2 with 0 clang errors
3. Stage 2 compiles hello-world: memory should drop from ~11 MB to ~1-2 MB
4. Stage 2 compiles SSH app without OOM
5. ASAN on stage 2 binary: verify release calls appear in emitted C, no UAF
6. Diff test: compare cleanup calls in C emitted by Python compiler vs self-hosted for a small test program — should be equivalent
7. ASAN on compiled user programs: verify no UAF from retain/release mismatches

## Known Limitation

Nested struct field cleanup only handles DIRECT fields. Deeply nested refcounted fields (e.g., `ParseResult.parsed_module.decls[i].body`) require recursive destructors, which risk double-free when structs are passed by value. This is a pre-existing limitation shared with the Python compiler, not introduced by this port.

Affine local destruction (Section 4, item 3) is ported as disabled (matching the Python compiler's `if False` guard) due to UAF issues. The comment in the Python code explains the problem; the self-hosted code should carry the same comment.
