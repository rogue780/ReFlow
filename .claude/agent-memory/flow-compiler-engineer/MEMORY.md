# Flow Compiler Engineer — Memory

## Critical Bugs Found

### `_wrap_mut_args` segfault: `:mut` map/array param forwarding (lowering.py:2742)
**Bug**: When a `:mut map<K,V>` param `env` is referenced inside the function body, the
lowering emits `LDeref(LVar("env", LPtr(LPtr(LStruct("FL_Map")))), LPtr(LStruct("FL_Map")))` = `(*env)`.
When THIS dereferenced expression is passed to ANOTHER `:mut map` param (e.g., recursive call),
`_wrap_mut_args` sees `isinstance(arg_ct, LPtr) = True` and "passes directly" — but the emitted
C is `(*env)` = `FL_Map*`, not `env` = `FL_Map**`. The callee receives `FL_Map*` where it
expects `FL_Map**`, reads garbage as a pointer, segfaults in fl_map_has/fl_map_set.

**Root cause traced to**: `_lower_expr` for EIdent of a `:mut` param where param type is
`LPtr(LPtr(LStruct("FL_Map")))`: `not isinstance(p_lt.inner, LStruct)` = True (inner is LPtr,
not LStruct), so it emits `LDeref(...)`. The resulting c_type is `LPtr(LStruct("FL_Map"))`.
`_wrap_mut_args` then sees this LPtr and thinks "already a pointer, forward directly".

**Fix in `_wrap_mut_args`** (before `isinstance(arg_ct, LPtr): continue` check):
```python
# If arg is a LDeref of a :mut param variable, forward the raw pointer (FL_Map**)
if (isinstance(arg, LDeref) and isinstance(arg.inner, LVar)
        and arg.inner.c_name in self._mut_params):
    result[i] = arg.inner  # pass FL_Map** directly, not (*env)
    continue
```

**Confirmed crash point**: `match_type_env` in self_hosted/typechecker.flow — crash inside
`fl_map_has_str` when recursing from TCArray/TCOption arms. `(*env)` (FL_Map*) gets treated
as FL_Map** → `(**env)` reads refcount field (=1) as pointer → dereferences address 0x1+8=0x9
→ SIGSEGV.

**Symptom**: Segfault in fl_map_has with address ~0x9.

## Scope Corruption in self-hosted typechecker (typechecker.flow)
`extern_fn_decl_type()` temporarily adds type vars to scope (via scope_define) then decrements
scope_count to "remove" them. But scope_names is append-only — it never shrinks. This creates a
mismatch: scope_names grows by k+1 entries per extern fn<T> while scope_count grows by only 1.
Result: scope_names[i] != the expected name for the type at scope_types["s_i"] after the first
extern generic fn is processed.

**Effect**: scope_lookup for module-level names returns wrong types (e.g., "push" returns
TCFn(push_float) instead of TCFn(push)). DOES NOT cause segfault by itself — types are wrong
but not crash-causing. The real segfault is from _wrap_mut_args in the Python compiler.

## Self-Hosted Lowering: TypeExpr Nodes NOT in type_map (by design)
The Python typechecker does NOT store types for TypeExpr (type annotation) nodes in the types dict.
This is by design — comment in Python lowering says: "TypeExpr nodes are not stored in the typechecker's types dict."
Python lowering's `_type_of_return` falls back to `_resolve_type_ann` when type_of returns None.

**Bug in self-hosted**: `type_of_return` called `type_of(st, ast.type_expr_id(ret_type))` which always returns TCAny
for TypeExpr nodes → all function return types were `void*`.

**Fix**: Change `type_of_return` to call `resolve_type_ann(st, ret_type)` which has AST fallback.
Also: `resolve_type_ann_ast` for `TNamedType` must return `TCNamed("", name, [])` not `TCTypeVar(name)`
for user-defined types (TCTypeVar lowers to void*, TCNamed goes through lower_named_type correctly).

**Similar issues**: Variadic params in `lower_fn_decl` also need `is_variadic` check to wrap
in `TCArray` — otherwise `..parts:string` becomes `FL_String*` instead of `FL_Array*`.

## Self-Hosted Driver: Extern-Only Stdlib Modules Not in efn_map
`stdlib_needs_compilation()` returns false for extern-only modules (like `array.flow` which has
only `extern fn` decls). These are excluded from the compilable modules list passed to
`lower_and_emit_all`. But their extern fn c_name mappings are needed for call site resolution
(e.g., `array.size` → `fl_array_len_int`).

**Bug**: `build_extern_fn_map` only scanned compilable modules → `fl_array_size` generated instead of `fl_array_len_int`.

**Fix**: `extend_extern_fn_map_from_typed(efn_map, ds.cache_typed)` called in `lower_and_emit_all` to
also include extern fn c_names from all cached TypedModules (including non-compilable stdlib).

## Self-Hosted: fl_array_get_safe element_size==8 Pitfall (lir.flow LStmtListBox)
`fl_array_get_safe` in `flow_runtime.c` has a special path: when `element_size == sizeof(void*) == 8`,
it treats the stored bytes as a pointer and dereferences (`*(void**)ptr`), returning the pointed-to
value. This is for pointer arrays (strings, etc.). But structs that happen to be exactly 8 bytes
(e.g., `LStmtListBox{stmts:array<LStmtBox>}` — one pointer field) get corrupted by this path.

**Fix**: Add a `_pad:int` field to any struct used in an `array<struct>` where `sizeof(struct) == 8`.
This makes `sizeof == 16`, bypassing the special path. See `lir.flow` comment on `LStmtListBox`.

**Symptom**: Segfault inside `emit_switch` when accessing `case_bodies[i]` — the read struct has
a corrupted `stmts` pointer (pointing into `FL_Array` internals instead of a valid array).

**Rule**: ALWAYS check that any struct stored in an `array<T>` has `sizeof(T) != sizeof(void*)`.

## Self-Hosted Typechecker: Decl ID Collision Bug
**Bug**: `find_decl_by_id(s, id)` iterates ALL imported modules and returns the first match.
Since each module's parser assigns IDs starting from 0, the same `decl_id` can exist in multiple
modules (e.g., `array.get` id=46 and `json.int_val` id=46).

**Symptom**: Wrong type inferred for method calls like `array.get(parts, i)` → inferred as `JsonValue`
instead of `option<string>` → crash in `check_exhaustiveness`.

**Fix (commit 55d3a90)**:
1. Added `module_key:string` to `Symbol` struct in `resolver.flow` (default `""`)
2. When copying module exports into `type_member_scopes` (both alias and non-alias), use
   `copy_symbol_with_mk(es, module_key)` to stamp the source module onto each symbol
3. Updated `find_decl_by_id` and `find_extern_decl_by_id` to accept `module_key:string`;
   when non-empty, search ONLY that module (avoiding cross-module collision)
4. Updated all 3 call sites in EMethodCall/ECall/EIdent handlers to pass `sym.module_key`

**Key insight**: `type_member_scopes` symbols are COPIED from ModuleScope.exports which have
module_key="" by default. Must set module_key when copying into type_member_scopes.

## Key Design: scope_names vs scope_count
The TCState scope uses:
- scope_names: array<string> — append-only, never shrunk
- scope_types: map<string, TCTypeBox> — keyed by "s_N" where N = scope_count at define time
- scope_count: int — watermark, the effective scope size
scope_lookup scans scope_names[0..scope_count-1] backward, matching by name.
scope_define appends to scope_names AND sets scope_types["s_{scope_count}"], then increments scope_count.
The "remove" pattern (decrement scope_count without shrinking scope_names) leaves stale entries.
