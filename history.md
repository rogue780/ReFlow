# Bootstrap Fix History

## Session: 2026-03-13/14

### Problem: Self-hosted compiler can't bootstrap (compile itself)

Stage 1 (Python → binary) works. Stage 2 (self-hosted compiles itself) produces C
but clang rejects it. Working through codegen bugs one by one.

---

### Fix 1: Extern fn map ID collision (commit 337e99a)
**Problem**: All extern fn names wrong (string.char_at → fl_sys_args)
**Root cause**: Bare decl_id as map key — collisions across modules
**Fix**: Composite key `module_path + ":" + decl_id`
**Result**: Eliminated 40+ wrong function name errors

### Fix 2: Char literal lowering (commit 9ce30ba)
**Problem**: `'47'` instead of `47` for char codepoints
**Root cause**: `lower_expr` for ECharLit wrapped value in single quotes
**Fix**: Remove quote wrapping, emit plain integer

### Fix 3: Variadic call arg packing (commit 9ce30ba)
**Problem**: `path.join(a, b)` passed individual args instead of array
**Root cause**: Self-hosted lowering had no variadic packing
**Fix**: Added `pack_variadic_args()`, check TCFn.is_variadic

### Fix 4: cast<T> target type resolution (commit 579d439)
**Problem**: All casts emitted as `(void*)` instead of correct type
**Root cause**: Typechecker returned TCAny for ECast (couldn't access cast_targets)
**Fix**: Thread cast_targets from ParseResult through driver → lowering → LowerState

### Fix 5: None literal specialization (commit cff1486)
**Problem**: `return none` emitted as `(FL_Option_ptr){.tag=0}` instead of `(FL_Option_int){.tag=0}`
**Root cause**: `lower_none_lit` matched on `TCOption(inner)` which failed for imported sum type variants
**Fix**: Use `lower_type(st, current_ret_type)` directly, check result starts with `FL_Option_`

### Fix 6: ++/-- operators (commit cff1486)
**Problem**: `i++` emitted as `i ++ 1` (invalid C)
**Root cause**: SUpdate lowering used raw `op` string (`"++"`) instead of `"+"`
**Fix**: Map `++` to `+`, `--` to `-`, use LECheckedArith for int types

### Fix 7: Recursive sum type fields — FL_Box* (commit 14d39b4)
**Problem**: `LExprBox` fields in LExpr variants caused "incomplete type" errors
**Root cause**: Self-hosted lowering emitted recursive fields by value, not as FL_Box*
**Fix**: `is_recursive_sum_field` now detects indirect recursion (FooBox → Foo pattern), emits `FL_Box*`

**FAILED APPROACH**: Adding `LEBoxDeref` LIR variant caused memory corruption (sum type struct size change). Reverted.

### Fix 8: conv.to_string monomorphization (commit 18224f5)
**Problem**: `conv.to_string(n)` emitted as `fl_conv_to_string` (undeclared)
**Root cause**: Self-hosted compiler can't monomorphize generic functions

**FAILED APPROACH 1**: Nested if — `if(method_name == "to_string") { if(rname == "conv") { ... } }` — Python compiler codegen bug: inner if uses raw `==` instead of `fl_string_eq` for string comparison.

**FAILED APPROACH 2**: Combined && — `if(method_name == "to_string" && rname == "conv")` — Python compiler generates `fl_string_eq` for first operand but raw `==` for second.

**WORKING APPROACH**: Concatenate strings — `let mono_check = method_name + ":" + resolved_mod; if(mono_check == "to_string:conv")` — single string comparison avoids the bug.

**Also needed**: Added `conv.to_string__int()` as explicit function in stdlib/conv.flow so the function body exists.

### Fix 9: :mut parameter forwarding (commit 35f1cf2)
**Problem**: `emit_raw(st, text)` emitted as `emit_raw((*st), text)` — deref'd pointer
**Root cause**: `lower_ident` always derefs :mut params; no re-wrapping for :mut→:mut calls
**Fix**: Added `wrap_mut_call_args()` which unwraps LDeref for :mut target params. Added `find_fn_decl_by_id()` and `ast.is_mut_type_ann()`.

### Fix 10: Generic type arg resolution (commit cff1486)
**Problem**: `option<int>` resolved inner type as TCAny
**Root cause**: `resolve_type_ann_ast` for TGenericType used `tc_any()` for type args
**Fix**: Recursively resolve type args for option, result, array, map

---

## Current blocker: array.put monomorphization

### The problem
`array.put(arr, idx, val)` emits as `fl_array_put(arr, idx, val)` — unmonomorphized.
Should emit `fl_array_put__string(arr, idx, val)`.

### What's been built (commit d6c04f4)
- `infer_T_suffix_from_array_arg()` — extracts element type
- `record_mono_site()` — deduplicates monomorphization sites
- `emit_array_put_fn()` — hand-coded LIR body for array.put<T>
- Emission phase in `lower()` that generates monomorphized functions
- Extern fn collision guard in mc_sym path

### What doesn't work yet
The monomorphization check in `lower_method_call` is placed in the **namespace function call path** (SK_IMPORT check on the receiver EIdent). But `array.put` calls NEVER REACH this path.

**Finding**: The Python compiler doesn't compile the namespace path code at all — the `mono_check`, `mono_array_check` variables don't appear in the compiled C output. This means the control flow never enters the `if(s.kind == SK_IMPORT)` block.

**Hypothesis**: The mc_sym path at line 3009 handles `array.put` and returns via the extern fn lookup (even though `put` is a FnDecl, not ExternFnDecl). OR the receiver `EIdent("array")` match doesn't fire because the receiver's symbol lookup returns `none`.

### Next step
Move the monomorphization check INTO the mc_sym path (where the MethodCall's symbol is found), rather than in the separate namespace path. The mc_sym has `ms.module_key` and `ms.name` which can identify `array.put` calls.

### Finding: array.put goes through lower_call's module-qualified path
`array.put(arr, idx, val)` is parsed as `EMethodCall` but the call
actually goes through `lower_call`'s `if(array.size(cmod) > 0)` path
because the resolver creates `ECall(callee: EIdent(name:"put", module_path:["array"]))`.
The mc_sym path in lower_method_call and the namespace SK_IMPORT path are both
dead code — NEVER compiled by the Python compiler.

### Finding: NULL string from mc_sym extern fn collision guard
The `is_actually_extern` guard added to lower_method_call's mc_sym path
causes NULL string concatenation during self-compilation. The `string.contains`
call or the map.get lookups produce NULL intermediaries. The guard needs to
be simplified or removed.

### Finding: array.put goes through BOTH lower_call AND lower_method_call
The parser can create EITHER ECall(EIdent(cmod=["array"]), ...) OR
EMethodCall(EIdent("array"), "put", ...) for `array.put(...)`.
- ECall with cmod → goes to lower_call's module-qualified path (line ~2881)
- EMethodCall → goes to lower_method_call's namespace SK_IMPORT path
The Python compiler generates code for the METHOD CALL path but NOT the
module-qualified call path (it's dead code per the Python compiler's analysis).
So monomorphization must go in the METHOD CALL path.

### Finding: record_mono_site causes NULL concat in method_call path
Calling `record_mono_site` from the SK_IMPORT namespace path in
lower_method_call causes `fl_string_concat: NULL argument` during
self-compilation. The function itself is correct, but something about
the calling context produces NULL — likely `mono_type_suffix` or
`mangler.mangle_monomorphized` receives a partially NULL argument.
This needs debugging with a simpler approach — perhaps just append
the suffix directly without calling record_mono_site.

### Finding: lex error from semicolons in Flow
Flow does NOT use semicolons. Writing `x = a; y = b` causes LexError.
Must split into separate statements.

### Finding: struct comparison with == fails in C
Can't compare LType structs with `==` in generated C. Use string
checks or other comparison methods instead.

### Finding: Creating LExprBox during match destructuring crashes
Creating new `lir.le_box(...)` (which allocates FL_Box) during
match destructuring of an LExpr value causes `malloc(): unaligned tcache chunk`.
This happens because the match subject's FL_Box is being read while new FL_Box
allocations change the heap state. Can't add FL_BOX_DEREF for recursive fields
at the match destructuring site — need a different approach entirely.

Possible fix: emit the FL_BOX_DEREF in the EMITTER (not the lowering) when
it detects that a match-bound variable came from a FL_Box* field. This avoids
creating new LIR nodes during lowering.

### Finding: Array literal [str] causes NULL in method call context
Creating array literals like `[mc_put_suffix]` or `["T"]` in the
SK_IMPORT namespace method call path causes NULL concat during
self-compilation. Building arrays with push (`arr = []; arr = push(arr, x)`)
works. Similarly, creating `MonoSite{...}` structs crashes. The
method call path has some context issue with complex value construction.

### Finding: Adding functions to stdlib/array.flow causes generic compilation
Adding ANY new function to stdlib/array.flow that calls other array
functions makes the Python compiler compile ALL functions including
unresolvable generics like `put<T>`, causing `fl_array_T` type errors.
Non-generic stdlib functions must be in a separate module or use
runtime functions directly.

### Approaches NOT to retry
1. Nested string if — Python compiler codegen bug with inner if using `==`
2. `&&` with two string comparisons — Python compiler uses `==` for second operand
3. Adding new LIR variants (LEBoxDeref) — causes memory corruption from struct size change
4. Placing monomorphization in the namespace SK_IMPORT path — code is dead/unreachable
