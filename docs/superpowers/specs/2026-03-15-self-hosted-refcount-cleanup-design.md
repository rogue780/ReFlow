# Self-Hosted Refcount Cleanup — Design Spec

## Problem

The self-hosted compiler (`self_hosted/lowering.flow`) emits zero refcount release calls. The Python compiler's `lowering.py` has ~200 lines of cleanup machinery that tracks refcounted locals and emits `fl_array_release()`, `fl_string_release()`, etc. at scope exit. The self-hosted lowering never ported this. Result: stage 2 leaks every allocation and OOMs on multi-module programs (~120 MB for a 6-module SSH app before crashing).

## Goal

Port the full refcount cleanup system from `compiler/lowering.py` to `self_hosted/lowering.flow` so that code compiled by the self-hosted compiler has the same release behavior as code compiled by the Python compiler.

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

### 2. Type Classification

Port `_is_affine_type()` and `_get_release_fn()`:

**`get_release_fn(t:typechecker.TCType):string?`** — returns the release function name for directly-refcounted types:
- TCString → `"fl_string_release"`
- TCArray → `"fl_array_release"`
- TCMap → `"fl_map_release"`
- TCStream → `"fl_stream_release"`
- TCBuffer → `"fl_buffer_release"`
- TCFn → `"fl_closure_release"`
- Everything else → none

**`is_affine_type(t:typechecker.TCType):bool`** — classifies types:
- Value types (int, float, bool, byte, char) → false
- Refcounted types (string, array, map, etc.) → false (handled by ARC)
- Option/Result → affine if inner is affine
- Struct with any refcounted/affine field → true
- Sum with any affine variant → true
- Everything else → false

**`has_refcounted_fields(t:typechecker.TCType):bool`** — recursively checks if a type contains any refcounted fields (direct or nested).

**`sum_type_has_cleanup_fields(t:typechecker.TCType):bool`** — checks if a sum type has variants with refcounted fields.

### 3. Registration (in lower_let)

When lowering `let x:T = expr`:

1. **Directly refcounted type** (string, array, map, etc.): append to `container_locals` with current `scope_depth` and the appropriate release function.

2. **Struct with refcounted fields**: call `register_struct_field_releases()` which walks DIRECT fields only:
   - For each refcounted field → append to `struct_field_cleanup`
   - For each sum type field with cleanup → append to `sum_field_cleanup`, emit destructor if not already emitted
   - `block_safe` flag based on source:
     - TypeLit/RecordLit → `true`
     - Function call result → `false`
     - Affine move (`let b = a`) → `true`, mark `a` consumed

3. **Affine sum type with :mut** → append to `affine_locals`

### 4. Consumed Binding Tracking

Mark bindings as consumed (skip their cleanup) when:
- Moved into another variable (`let b = a` where a is affine)
- Stored by reference in a container (`array.push_ptr(arr, x)`)
- Returned from function
- Assigned to another binding via `:mut` reassignment

Check `consumed_bindings` map before emitting any release.

### 5. Function-Exit Cleanup (inject_scope_cleanup)

After lowering the entire function body, walk all statements and inject cleanup before each `LSReturn`:

1. Collect variables referenced in the return expression → protect from release
2. Check if return expression needs hoisting (references variables that need cleanup):
   - If yes: emit `tmp = return_expr; cleanup_calls; return tmp;`
   - If no: emit `cleanup_calls; return original_expr;`
3. For void functions: append cleanup at end of body

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

### 6. Block-Exit Cleanup (emit_block_exit_cleanup)

After lowering an inner block (if body, else body, match arm, for body):

1. Skip if block ends with LSReturn, LSBreak, LSContinue, or `_fl_throw`
2. Only process entries registered AFTER the snapshot indices (this block's scope)
3. Only process depth-matching entries
4. **Only emit struct field cleanup for `block_safe=true` entries**
5. Append release calls at end of block body

Uses snapshot-based scoping: save `len(container_locals)`, `len(struct_field_cleanup)`, `len(sum_field_cleanup)` before lowering block, only process entries after those indices.

### 7. Loop-End Cleanup (emit_loop_end_cleanup)

After lowering a for/while loop body:

1. Collect variables that received retain calls in the body
2. Collect variables stored by reference in containers (push_ptr) → skip these
3. Only release container locals that were retained (balance the retain)
4. Only struct field cleanup with `block_safe=true`
5. Only entries registered during this loop's body

### 8. Sum Type Destructors (generate_destroy_fn)

For sum types with refcounted variants, emit a destructor function:

```c
void _fl_destroy_TypeName(void* ptr) {
    TypeName* self = (TypeName*)ptr;
    switch (self->tag) {
        case 0: {  // VariantWithStringField
            fl_string_release(self->Variant.name);
            break;
        }
        case 1: {  // VariantWithArrayField
            fl_array_release(self->Variant.items);
            break;
        }
        // ... etc
    }
}
```

Track in `struct_handler_emitted` to avoid duplicates. The destructor is emitted as a top-level `LFnDef` added to the LModule.

### 9. Helper Functions

**`collect_referenced_vars(expr:lir.LExpr):map<string, bool>`** — recursively walk LExpr, return all LVar names.

**`collect_returned_field_keys(expr:lir.LExpr):map<string, bool>`** — collect dotted field access patterns in return expressions (e.g., `s.src` → skip release of `s.src`).

**`collect_consumed_struct_bases(expr:lir.LExpr):map<string, bool>`** — collect LVar names used as compound literal field values (transferred to return).

**`collect_push_ptr_vars(stmts:array<lir.LStmtBox>):map<string, bool>`** — find variables stored by reference in containers.

**`collect_retained_vars(stmts:array<lir.LStmtBox>):map<string, bool>`** — find variables that received retain calls.

**`all_paths_exit(stmts:array<lir.LStmtBox>):bool`** — check if all leaf paths end with return/break/continue.

**`emit_struct_field_release(struct_var:string, field_name:string, struct_c_type:lir.LType, release_fn:string):lir.LStmt`** — build `LExprStmt(LCall(release_fn, [field_access]))`.

**`emit_sum_field_release(struct_var:string, field_name:string, struct_c_type:lir.LType, destructor_fn:string, field_lt:lir.LType):lir.LStmt`** — build `LExprStmt(LCall(destructor_fn, [&field_access]))`.

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
| `lower_let` | Register cleanup entries based on type/source |
| `lower_block` | Save snapshots, increment depth, lower stmts, emit block-exit cleanup, decrement depth |
| `lower_if` / `lower_match` / `lower_for` / `lower_while` | Manage snapshots for each arm/body |
| After full function body lowered | Call `inject_scope_cleanup` to insert pre-return releases |
| `lower_assign` (`:mut` reassign) | Emit destroy-before-reassign for affine, track consumption |

## What This Does NOT Change

- LIR node definitions in `lir.flow` — no new node types needed
- Emitter in `emitter.flow` — cleanup LIR is just `LExprStmt(LCall(...))`, already supported
- Runtime — all release/destroy functions already exist
- Python compiler — no changes needed

## Testing

After implementation:
1. `make test` must pass (Python compiler unchanged)
2. Rebuild stage 1 → stage 2 with 0 clang errors
3. Stage 2 compiles hello-world: memory should drop from ~11 MB to ~1-2 MB
4. Stage 2 compiles SSH app without OOM
5. ASAN on stage 2 binary shows release calls in the emitted C

## Known Limitation

Nested struct field cleanup only handles DIRECT fields. Deeply nested refcounted fields (e.g., `ParseResult.parsed_module.decls[i].body`) require recursive destructors, which risk double-free when structs are passed by value. This is a pre-existing limitation shared with the Python compiler, not introduced by this port.
