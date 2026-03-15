# Self-Hosted Refcount Cleanup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the full refcount cleanup system from `compiler/lowering.py` to `self_hosted/lowering.flow` so the self-hosted compiler emits retain/release calls, eliminating memory leaks.

**Architecture:** Add cleanup tracking state to `LowerState`, type classification helpers, and cleanup emission at function-exit, block-exit, and loop-end points. The lowering emits `LExprStmt(LECall("fl_X_release", [...]))` nodes — no new LIR types needed, the existing emitter handles them transparently.

**Tech Stack:** Flow language (self_hosted/lowering.flow), Python compiler for building stage 1, clang for stage 2, ASAN for verification.

**Spec:** `docs/superpowers/specs/2026-03-15-self-hosted-refcount-cleanup-design.md`

**Reference implementation:** `compiler/lowering.py` (lines 733-756 init, 1684-1874 inject_scope_cleanup, 2199-2332 helpers, 2766-2900 emit helpers, 3284-3542 block/loop cleanup)

---

## Chunk 1: Foundation — State, Types, Classification

### Task 1: Add cleanup supporting types to lowering.flow

**Files:**
- Modify: `self_hosted/lowering.flow:23-105` (LowerState struct)

- [ ] **Step 1: Add cleanup data types before LowerState**

Add these types BEFORE the LowerState struct (around line 20):

```flow
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

- [ ] **Step 2: Add cleanup fields to LowerState**

Add these fields at the end of the LowerState struct (before the closing `}`):

```flow
    // Refcount cleanup tracking
    scope_depth:int
    container_locals:array<ContainerLocal>
    struct_field_cleanup:array<StructFieldCleanup>
    sum_field_cleanup:array<SumFieldCleanup>
    affine_locals:array<AffineLocal>
    consumed_bindings:map<string, bool>
    struct_handler_emitted:map<string, bool>
```

- [ ] **Step 3: Initialize cleanup fields in the `lower()` entry point**

Find the `lower()` function that creates the initial LowerState. Add initialization for all new fields:

```flow
    scope_depth: 0,
    container_locals: [],
    struct_field_cleanup: [],
    sum_field_cleanup: [],
    affine_locals: [],
    consumed_bindings: map.new(),
    struct_handler_emitted: map.new(),
```

- [ ] **Step 4: Reset cleanup state in lower_fn_decl (~line 1206)**

After the existing save/restore lines for `let_var_ltypes` and `mut_param_names`, add:

```flow
    // Save cleanup state
    let saved_scope_depth:int = st.scope_depth
    let saved_container_locals:array<ContainerLocal> = st.container_locals
    let saved_struct_field_cleanup:array<StructFieldCleanup> = st.struct_field_cleanup
    let saved_sum_field_cleanup:array<SumFieldCleanup> = st.sum_field_cleanup
    let saved_affine_locals:array<AffineLocal> = st.affine_locals
    let saved_consumed:map<string, bool> = st.consumed_bindings

    // Reset for new function
    st.scope_depth = 0
    st.container_locals = []
    st.struct_field_cleanup = []
    st.sum_field_cleanup = []
    st.affine_locals = []
    st.consumed_bindings = map.new()
```

And restore before the function returns (~line 1259):

```flow
    // Restore cleanup state
    st.scope_depth = saved_scope_depth
    st.container_locals = saved_container_locals
    st.struct_field_cleanup = saved_struct_field_cleanup
    st.sum_field_cleanup = saved_sum_field_cleanup
    st.affine_locals = saved_affine_locals
    st.consumed_bindings = saved_consumed
```

- [ ] **Step 5: Build and verify**

```bash
source .venv/bin/activate
python main.py build self_hosted/driver.flow -o flowc_bs1
./flowc_bs1 emit-c self_hosted/driver.flow --stdlib stdlib -o stage2.c
python fix_stage2.py stage2.c
clang -w -I runtime stage2.c runtime/flow_runtime.c -o flowc_bs2 -lm -lpthread
```

Expected: 0 clang errors (no behavioral change yet, just added fields).

- [ ] **Step 6: Commit**

```bash
git add self_hosted/lowering.flow
git commit -m "refcount: add cleanup tracking types and state to LowerState"
```

### Task 2: Add type classification helpers

**Files:**
- Modify: `self_hosted/lowering.flow` (add functions after existing helpers, ~line 250)

- [ ] **Step 1: Add get_release_fn**

```flow
fn get_release_fn(t:typechecker.TCType):option<string> {
    match(t) {
        TCString: { return some("fl_string_release") }
        TCArray(e): { return some("fl_array_release") }
        TCMap(k, v): { return some("fl_map_release") }
        TCStream(e): { return some("fl_stream_release") }
        TCBuffer(e): { return some("fl_buffer_release") }
        TCFn(p, r, pu, va): { return some("fl_closure_release") }
        _: { return none }
    }
}
```

- [ ] **Step 2: Add get_retain_fn**

```flow
fn get_retain_fn(t:typechecker.TCType):option<string> {
    match(t) {
        TCString: { return some("fl_string_retain") }
        TCArray(e): { return some("fl_array_retain") }
        TCMap(k, v): { return some("fl_map_retain") }
        TCStream(e): { return some("fl_stream_retain") }
        TCBuffer(e): { return some("fl_buffer_retain") }
        TCFn(p, r, pu, va): { return some("fl_closure_retain") }
        _: { return none }
    }
}
```

- [ ] **Step 3: Add is_allocating_expr**

Reference: `compiler/lowering.py:2888-2899`

```flow
fn is_allocating_expr(expr:ast.Expr):bool {
    match(expr) {
        ECall(id, l, c, callee, args): { return true }
        EMethodCall(id, l, c, recv, method, args): { return true }
        EStringLit(id, l, c, v): { return true }
        EArrayLit(id, l, c, elems): { return true }
        EFString(id, l, c, parts): { return true }
        ECopy(id, l, c, inner): { return true }
        _: { return false }
    }
}
```

Note: TypeLit and RecordLit are intentionally NOT allocating — they produce stack compound literals. They are handled as a separate case in lower_let.

- [ ] **Step 4: Add has_refcounted_fields (cross-module struct field walk)**

This function walks a struct's DIRECT fields and checks if any are refcounted. Uses the existing `imported_module_decls` infrastructure for cross-module resolution.

```flow
fn has_refcounted_fields(st:LowerState:mut, t:typechecker.TCType):bool {
    // Get struct fields from type declarations
    let fields:array<ast.FieldDecl> = get_type_fields(st, t)
    let i:int:mut = 0
    while(i < array.size(fields)) {
        let f:ast.FieldDecl = array.get_any(fields, i) ?? ast.default_field_decl()
        let ft:typechecker.TCType = typechecker.resolve_field_type(st.typed, f)
        match(get_release_fn(ft)) {
            some(rfn): { return true }
            none: {}
        }
        i = i + 1
    }
    return false
}
```

The `get_type_fields` helper resolves type declarations across modules — implement based on the existing cross-module resolution in `get_sum_variant_field_name` (~line 718).

- [ ] **Step 5: Add is_affine_type**

Reference: `compiler/lowering.py:2294-2332`

```flow
fn is_affine_type(st:LowerState:mut, t:typechecker.TCType):bool {
    match(t) {
        TCInt(w, s): { return false }
        TCFloat(w): { return false }
        TCBool: { return false }
        TCChar: { return false }
        TCByte: { return false }
        TCPtr: { return false }
        TCString: { return false }
        TCArray(e): { return false }
        TCMap(k, v): { return false }
        TCStream(e): { return false }
        TCBuffer(e): { return false }
        TCFn(p, r, pu, va): { return false }
        TCOption(inner): { return is_affine_type(st, inner) }
        TCResult(ok_t, err_t): { return is_affine_type(st, ok_t) || is_affine_type(st, err_t) }
        TCNamed(mp, n, ta): { return has_refcounted_fields(st, t) }
        TCSumType(n, mp, vars): { return has_refcounted_fields(st, t) }
        _: { return false }
    }
}
```

- [ ] **Step 6: Build and verify**

Same build pipeline as Task 1 Step 5. Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git commit -m "refcount: add type classification helpers (release_fn, retain_fn, is_affine, is_allocating)"
```

### Task 3: Add LIR emission helpers

**Files:**
- Modify: `self_hosted/lowering.flow` (after type classification helpers)

- [ ] **Step 1: Add collect_referenced_vars**

Walk an LExpr tree and return all LEVar names:

```flow
fn collect_referenced_vars(e:lir.LExpr):map<string, bool> {
    let result:map<string, bool>:mut = map.new()
    match(e) {
        LEVar(cn, ct): { result = map.set(result, cn, true) }
        LECall(fn_name, args, ct): {
            let i:int:mut = 0
            while(i < array.size(args)) {
                let arg:lir.LExprBox = array.get_any(args, i) ?? lir.le_box(lir.placeholder_expr())
                let sub:map<string, bool> = collect_referenced_vars(lir.le_unbox(arg))
                // merge sub into result
                i = i + 1
            }
        }
        LEFieldAccess(obj, f, ct): {
            let sub:map<string, bool> = collect_referenced_vars(lir.le_unbox(obj))
            // merge sub into result
        }
        LEBinOp(op, l, r, ct): {
            // merge both sides
        }
        _: {}
    }
    return result
}
```

- [ ] **Step 2: Add emit_release_call helper**

Build `LExprStmt(LECall(release_fn, [LEVar(var_name, c_type)]))`:

```flow
fn emit_release_call(var_name:string, c_type:lir.LType, release_fn:string, line:int):lir.LStmt {
    return lir.LSExprStmt(
        expr: lir.LECall(
            fn_name: release_fn,
            args: [lir.le_box(lir.LEVar(c_name:var_name, c_type:c_type))],
            c_type: lir.LVoid
        ),
        source_line: line
    )
}
```

- [ ] **Step 3: Add emit_retain_call helper**

Same pattern but with retain function:

```flow
fn emit_retain_call(var_name:string, c_type:lir.LType, retain_fn:string, line:int):lir.LStmt {
    return lir.LSExprStmt(
        expr: lir.LECall(
            fn_name: retain_fn,
            args: [lir.le_box(lir.LEVar(c_name:var_name, c_type:c_type))],
            c_type: lir.LVoid
        ),
        source_line: line
    )
}
```

- [ ] **Step 4: Add emit_struct_field_release helper**

Build `LExprStmt(LECall(release_fn, [LEFieldAccess(LEVar(struct_var), field_name)]))`:

```flow
fn emit_struct_field_release(struct_var:string, field_name:string, struct_c_type:lir.LType, release_fn:string, line:int):lir.LStmt {
    let access:lir.LExpr = lir.LEFieldAccess(
        obj: lir.le_box(lir.LEVar(c_name:struct_var, c_type:struct_c_type)),
        field: field_name,
        c_type: lir.LPtr(inner:lir.LVoid)
    )
    return lir.LSExprStmt(
        expr: lir.LECall(fn_name:release_fn, args:[lir.le_box(access)], c_type:lir.LVoid),
        source_line: line
    )
}
```

- [ ] **Step 5: Add all_paths_exit helper**

Check if a statement list always exits via return/break/continue:

```flow
fn all_paths_exit(stmts:array<lir.LStmtBox>):bool {
    if(array.size(stmts) == 0) { return false }
    let last:lir.LStmtBox = array.get_any(stmts, array.size(stmts) - 1) ?? lir.LStmtBox{ls:lir.placeholder_stmt()}
    match(last.ls) {
        LSReturn(hv, v, sl): { return true }
        LSBreak(sl): { return true }
        LSContinue(sl): { return true }
        LSIf(cond, then_body, else_body, sl): {
            return all_paths_exit(then_body) && all_paths_exit(else_body)
        }
        _: { return false }
    }
}
```

- [ ] **Step 6: Build and verify**

Same pipeline. Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git commit -m "refcount: add LIR emission helpers (release, retain, field release, collect vars)"
```

## Chunk 2: Registration — lower_let and lower_assign

### Task 4: Register container locals in lower_let

**Files:**
- Modify: `self_hosted/lowering.flow` (lower_let function, ~line 1692)

- [ ] **Step 1: Add cleanup registration after var decl creation**

In `lower_let`, after the `LSVarDecl` is created and `let_var_ltypes` is updated, add:

```flow
    // Register cleanup for refcounted types
    let val_type:typechecker.TCType = type_of(st, id)
    match(get_release_fn(val_type)) {
        some(rfn): {
            let lt:lir.LType = lower_type(st, val_type)
            st.container_locals = array.push(st.container_locals, ContainerLocal{
                var_name: name, c_type: lt, release_fn: rfn, depth: st.scope_depth
            })
            // Retain for non-allocating sources
            if(is_allocating_expr(val) == false) {
                match(get_retain_fn(val_type)) {
                    some(retain_fn): {
                        result = array.push(result, lir.LStmtBox{ls:
                            emit_retain_call(name, lt, retain_fn, line)
                        })
                    }
                    none: {}
                }
            }
        }
        none: {}
    }
```

- [ ] **Step 2: Add struct field cleanup registration**

After the container local check, add struct field registration for types with refcounted fields:

```flow
    // Register struct field cleanup for types with refcounted fields
    match(get_release_fn(val_type)) {
        some(rfn): {} // Already handled as container local
        none: {
            if(has_refcounted_fields(st, val_type)) {
                let lt:lir.LType = lower_type(st, val_type)
                let block_safe:bool:mut = false
                match(val) {
                    ETypeLit(tid, tl, tc, tn, tf, hs, sp): { block_safe = true }
                    ERecordLit(tid, tl, tc, rf): { block_safe = true }
                    _: {
                        if(is_allocating_expr(val)) {
                            block_safe = false
                        } else {
                            block_safe = true
                            // Emit retains for shared fields
                        }
                    }
                }
                register_struct_field_releases(st, name, val_type, lt, st.scope_depth, block_safe)
            }
        }
    }
```

- [ ] **Step 3: Implement register_struct_field_releases**

Reference: `compiler/lowering.py:2199-2240`

```flow
fn register_struct_field_releases(st:LowerState:mut, var_name:string, val_type:typechecker.TCType, c_type:lir.LType, depth:int, block_safe:bool):none {
    let fields:array<ast.FieldDecl> = get_type_fields(st, val_type)
    let i:int:mut = 0
    while(i < array.size(fields)) {
        let f:ast.FieldDecl = array.get_any(fields, i) ?? ast.default_field_decl()
        let ft:typechecker.TCType = resolve_field_type_from_decl(st, f)
        match(get_release_fn(ft)) {
            some(rfn): {
                st.struct_field_cleanup = array.push(st.struct_field_cleanup, StructFieldCleanup{
                    struct_var: var_name, field_name: f.name,
                    struct_c_type: c_type, release_fn: rfn,
                    depth: depth, block_safe: block_safe
                })
            }
            none: {}
        }
        i = i + 1
    }
}
```

- [ ] **Step 4: Build and verify**

Same pipeline. Expected: 0 errors. Stage 2 now registers cleanup entries but doesn't emit them yet.

- [ ] **Step 5: Commit**

```bash
git commit -m "refcount: register container locals and struct field cleanup in lower_let"
```

### Task 5: Release-on-reassignment in lower_assign

**Files:**
- Modify: `self_hosted/lowering.flow` (lower_assign, ~line 1761)

- [ ] **Step 1: Add release-before-assign for :mut refcounted variables**

In `lower_assign`, before emitting the LSAssign, check if target is a refcounted :mut binding:

```flow
    let target_type:typechecker.TCType = type_of(st, id)
    let result:array<lir.LStmtBox>:mut = []

    match(get_release_fn(target_type)) {
        some(rfn): {
            let lt:lir.LType = lower_type(st, target_type)
            let target_name:string = // extract name from target expr
            // Save old value
            let old_tmp:string = fresh_temp(st)
            result = array.push(result, lir.LStmtBox{ls: lir.LSVarDecl(
                c_name:old_tmp, c_type:lt, has_init:true,
                init:lir.LEVar(c_name:target_name, c_type:lt), source_line:line
            )})
            // Emit the assignment
            result = array.push(result, lir.LStmtBox{ls: lir.LSAssign(target:lt_expr, value:lv, source_line:line)})
            // Release old if different from new
            // if (_old != target) { release(_old); }
            // For non-allocating RHS, also retain new
            if(is_allocating_expr(val) == false) {
                match(get_retain_fn(target_type)) {
                    some(retain_fn): {
                        result = array.push(result, lir.LStmtBox{ls:
                            emit_retain_call(target_name, lt, retain_fn, line)
                        })
                    }
                    none: {}
                }
            }
            result = array.push(result, lir.LStmtBox{ls:
                emit_release_call(old_tmp, lt, rfn, line)
            })
            return result
        }
        none: {}
    }
    // Fallback: original assign
    return [lir.LStmtBox{ls: lir.LSAssign(target:lt_expr, value:lv, source_line:line)}]
```

- [ ] **Step 2: Build and verify**

- [ ] **Step 3: Commit**

```bash
git commit -m "refcount: release-on-reassignment for :mut refcounted bindings"
```

## Chunk 3: Cleanup Emission — Function-Exit and Block-Exit

### Task 6: Function-exit cleanup (inject_scope_cleanup)

**Files:**
- Modify: `self_hosted/lowering.flow` (add new function, call from lower_fn_decl)

This is the most complex piece. Reference: `compiler/lowering.py:1684-1874`

- [ ] **Step 1: Add inject_scope_cleanup function**

This function walks the lowered function body and inserts cleanup calls before each LSReturn:

```flow
fn inject_scope_cleanup(st:LowerState:mut, stmts:array<lir.LStmtBox>):array<lir.LStmtBox> {
    let result:array<lir.LStmtBox>:mut = []
    let i:int:mut = 0
    while(i < array.size(stmts)) {
        let sb:lir.LStmtBox = array.get_any(stmts, i) ?? lir.LStmtBox{ls:lir.placeholder_stmt()}
        match(sb.ls) {
            LSReturn(has_val, val, sl): {
                // Collect vars referenced in return expr
                let referenced:map<string, bool>:mut = map.new()
                if(has_val) {
                    referenced = collect_referenced_vars(val)
                }
                // Build cleanup calls
                let cleanup:array<lir.LStmtBox> = build_fn_exit_cleanup(st, referenced, sl)
                // Append cleanup before return
                let ci:int:mut = 0
                while(ci < array.size(cleanup)) {
                    result = array.push(result, array.get_any(cleanup, ci) ?? lir.LStmtBox{ls:lir.placeholder_stmt()})
                    ci = ci + 1
                }
                result = array.push(result, sb)
            }
            LSIf(cond, then_body, else_body, sl): {
                // Recurse into if branches
                let new_then:array<lir.LStmtBox> = inject_scope_cleanup(st, then_body)
                let new_else:array<lir.LStmtBox> = inject_scope_cleanup(st, else_body)
                result = array.push(result, lir.LStmtBox{ls: lir.LSIf(cond:cond, then_body:new_then, else_body:new_else, source_line:sl)})
            }
            LSSwitch(val, tags, bodies, default_body, sl): {
                // Recurse into switch cases
                // ... similar pattern
                result = array.push(result, sb)
            }
            LSBlock(inner, sl): {
                let new_inner:array<lir.LStmtBox> = inject_scope_cleanup(st, inner)
                result = array.push(result, lir.LStmtBox{ls: lir.LSBlock(stmts:new_inner, source_line:sl)})
            }
            _: {
                result = array.push(result, sb)
            }
        }
        i = i + 1
    }
    return result
}
```

- [ ] **Step 2: Add build_fn_exit_cleanup helper**

Builds the actual release calls for function exit:

```flow
fn build_fn_exit_cleanup(st:LowerState:mut, referenced:map<string, bool>, line:int):array<lir.LStmtBox> {
    let result:array<lir.LStmtBox>:mut = []
    let seen:map<string, bool>:mut = map.new()

    // Release container locals (depth 0)
    let ci:int:mut = 0
    while(ci < array.size(st.container_locals)) {
        let cl:ContainerLocal = array.get_any(st.container_locals, ci) ?? ContainerLocal{var_name:"", c_type:lir.LVoid, release_fn:"", depth:0}
        if(cl.depth == 0 && map.has(st.consumed_bindings, cl.var_name) == false && map.has(referenced, cl.var_name) == false && map.has(seen, cl.var_name) == false) {
            result = array.push(result, lir.LStmtBox{ls: emit_release_call(cl.var_name, cl.c_type, cl.release_fn, line)})
            seen = map.set(seen, cl.var_name, true)
        }
        ci = ci + 1
    }

    // Release struct fields
    let sfi:int:mut = 0
    while(sfi < array.size(st.struct_field_cleanup)) {
        let sf:StructFieldCleanup = array.get_any(st.struct_field_cleanup, sfi) ?? StructFieldCleanup{struct_var:"", field_name:"", struct_c_type:lir.LVoid, release_fn:"", depth:0, block_safe:false}
        if(map.has(st.consumed_bindings, sf.struct_var) == false && map.has(referenced, sf.struct_var) == false) {
            result = array.push(result, lir.LStmtBox{ls: emit_struct_field_release(sf.struct_var, sf.field_name, sf.struct_c_type, sf.release_fn, line)})
        }
        sfi = sfi + 1
    }

    return result
}
```

- [ ] **Step 3: Call inject_scope_cleanup from lower_fn_decl**

In `lower_fn_decl`, after `let lbody = lower_block(st, body)`, add:

```flow
    lbody = inject_scope_cleanup(st, lbody)
```

Also add void-function trailing cleanup: if the function returns void and the last statement is not a return, append depth-0 cleanup at the end.

- [ ] **Step 4: Build and verify**

Full pipeline rebuild. Expected: 0 clang errors. Stage 2 now emits release calls at function exit.

- [ ] **Step 5: Verify cleanup appears in emitted C**

```bash
./flowc_bs2 emit-c /tmp/test_hello.flow --stdlib stdlib -o /tmp/test_out.c
grep 'release' /tmp/test_out.c
```

Expected: should see `fl_string_release` and/or `fl_array_release` calls.

- [ ] **Step 6: Commit**

```bash
git commit -m "refcount: function-exit cleanup — inject_scope_cleanup before every return"
```

### Task 7: Block-exit cleanup

**Files:**
- Modify: `self_hosted/lowering.flow` (lower_block, lower_if_stmt, lower_while, lower_for)

- [ ] **Step 1: Add snapshot-based scoping to lower_block**

Before lowering inner blocks, save snapshot indices. After lowering, emit block-exit cleanup for entries registered during the block:

```flow
fn lower_block(st:LowerState:mut, stmts:array<ast.Stmt>):array<lir.LStmtBox> {
    let cl_snapshot:int = array.size(st.container_locals)
    let sf_snapshot:int = array.size(st.struct_field_cleanup)
    st.scope_depth = st.scope_depth + 1

    // ... existing loop that lowers each statement ...

    // Emit block-exit cleanup
    if(all_paths_exit(result) == false) {
        emit_block_exit_cleanup(st, result, cl_snapshot, sf_snapshot, st.scope_depth)
    }

    st.scope_depth = st.scope_depth - 1
    return result
}
```

- [ ] **Step 2: Add emit_block_exit_cleanup function**

Reference: `compiler/lowering.py:3284-3377`

```flow
fn emit_block_exit_cleanup(st:LowerState:mut, body:array<lir.LStmtBox>:mut, cl_snap:int, sf_snap:int, depth:int):none {
    // Release container locals registered after snapshot
    let ci:int:mut = cl_snap
    while(ci < array.size(st.container_locals)) {
        let cl:ContainerLocal = array.get_any(st.container_locals, ci) ?? ContainerLocal{var_name:"", c_type:lir.LVoid, release_fn:"", depth:0}
        if(cl.depth == depth && map.has(st.consumed_bindings, cl.var_name) == false) {
            body = array.push(body, lir.LStmtBox{ls: emit_release_call(cl.var_name, cl.c_type, cl.release_fn, 0)})
        }
        ci = ci + 1
    }

    // Release block_safe struct fields registered after snapshot
    let sfi:int:mut = sf_snap
    while(sfi < array.size(st.struct_field_cleanup)) {
        let sf:StructFieldCleanup = array.get_any(st.struct_field_cleanup, sfi) ?? StructFieldCleanup{struct_var:"", field_name:"", struct_c_type:lir.LVoid, release_fn:"", depth:0, block_safe:false}
        if(sf.depth == depth && sf.block_safe && map.has(st.consumed_bindings, sf.struct_var) == false) {
            body = array.push(body, lir.LStmtBox{ls: emit_struct_field_release(sf.struct_var, sf.field_name, sf.struct_c_type, sf.release_fn, 0)})
        }
        sfi = sfi + 1
    }
}
```

- [ ] **Step 3: Apply snapshot scoping to lower_if_stmt**

Save/restore snapshots before/after each branch of the if statement.

- [ ] **Step 4: Build and verify**

- [ ] **Step 5: Commit**

```bash
git commit -m "refcount: block-exit cleanup with snapshot-based scoping"
```

## Chunk 4: Remaining Mechanisms

### Task 8: Return-site retain

**Files:**
- Modify: `self_hosted/lowering.flow` (lower_return, ~line 1818)

- [ ] **Step 1: Add retain for non-allocating return values**

In `lower_return`, when the return value is a non-allocating expression of refcounted type:

```flow
    if(has_val && is_allocating_expr(val_expr) == false) {
        let ret_type:typechecker.TCType = type_of(st, id)
        match(get_retain_fn(ret_type)) {
            some(retain_fn): {
                let lt:lir.LType = lower_type(st, ret_type)
                result = array.push(result, lir.LStmtBox{ls: emit_retain_call(ret_name, lt, retain_fn, line)})
            }
            none: {}
        }
    }
```

- [ ] **Step 2: Build and verify**
- [ ] **Step 3: Commit**

### Task 9: Discarded return value release (lower_expr_stmt)

**Files:**
- Modify: `self_hosted/lowering.flow` (SExpr case in lower_stmt, ~line 1658)

- [ ] **Step 1: Add release for discarded allocating return values**

When the expression is a function call returning a refcounted type:

```flow
    SExpr(id, line, col, expr): {
        let le:lir.LExpr = lower_expr(st, expr)
        let expr_type:typechecker.TCType = type_of(st, id)
        match(get_release_fn(expr_type)) {
            some(rfn): {
                if(is_allocating_expr(expr)) {
                    let tmp:string = fresh_temp(st)
                    let lt:lir.LType = lower_type(st, expr_type)
                    return [
                        lir.LStmtBox{ls: lir.LSVarDecl(c_name:tmp, c_type:lt, has_init:true, init:le, source_line:line)},
                        lir.LStmtBox{ls: emit_release_call(tmp, lt, rfn, line)}
                    ]
                }
            }
            none: {}
        }
        return [lir.LStmtBox{ls: lir.LSExprStmt(expr:le, source_line:line)}]
    }
```

- [ ] **Step 2: Build and verify**
- [ ] **Step 3: Commit**

### Task 10: Sum type destructors and struct handlers

**Files:**
- Modify: `self_hosted/lowering.flow` (add destructor generation)

- [ ] **Step 1: Add generate_destroy_fn for sum types**

Generate `_fl_destroy_TypeName` that switches on tag and releases refcounted fields per variant. Reference: `compiler/lowering.py:2356-2450`.

- [ ] **Step 2: Add generate_destroy_fn for structs**

Generate `_fl_destroy_StructName` that releases each refcounted field. Reference: `compiler/lowering.py:2531-2660`.

- [ ] **Step 3: Add generate_retain_fn for both**

Generate `_fl_retain_TypeName` / `_fl_retain_StructName` that retains each refcounted field.

- [ ] **Step 4: Emit handler functions as LFnDef nodes in LModule**

Add generated destructor/retainer functions to `st.fn_defs`.

- [ ] **Step 5: Build and verify**
- [ ] **Step 6: Commit**

### Task 11: Loop-end cleanup

**Files:**
- Modify: `self_hosted/lowering.flow` (lower_for, lower_while)

- [ ] **Step 1: Add loop-end cleanup**

After lowering loop body, emit cleanup for container locals and block_safe struct fields registered during the body. Reference: `compiler/lowering.py:3443-3536`.

- [ ] **Step 2: Build and verify**
- [ ] **Step 3: Commit**

### Task 12: String temp hoisting

**Files:**
- Modify: `self_hosted/lowering.flow` (string concat lowering)

- [ ] **Step 1: Add string temp hoisting for concat chains**

When lowering `fl_string_concat(a, b)` where `a` or `b` is a string-returning call, hoist to a temp and register for cleanup.

- [ ] **Step 2: Build and verify**
- [ ] **Step 3: Commit**

## Chunk 5: Integration Testing and Verification

### Task 13: Full pipeline verification

- [ ] **Step 1: Run make test**

```bash
make test
```

Expected: 1162 tests pass (Python compiler unchanged).

- [ ] **Step 2: Rebuild stage 1 → stage 2**

```bash
source .venv/bin/activate
python main.py build self_hosted/driver.flow -o flowc_bs1
./flowc_bs1 emit-c self_hosted/driver.flow --stdlib stdlib -o stage2.c
python fix_stage2.py stage2.c
clang -w -I runtime stage2.c runtime/flow_runtime.c -o flowc_bs2 -lm -lpthread
```

Expected: 0 clang errors.

- [ ] **Step 3: Memory test — hello world**

```bash
/usr/bin/time -v ./flowc_bs2 emit-c /tmp/test_hello.flow --stdlib stdlib -o /dev/null 2>&1 | grep "Maximum resident"
```

Expected: significantly less than 11 MB (target: 1-3 MB).

- [ ] **Step 4: Memory test — SSH app**

```bash
/usr/bin/time -v ./flowc_bs2 emit-c ssh/ssh.flow --stdlib stdlib -o /tmp/ssh_test.c 2>&1 | grep -E "Maximum|error"
```

Expected: completes without OOM. Target: under 20 MB.

- [ ] **Step 5: ASAN verification**

```bash
clang -w -fsanitize=address -g -I runtime stage2.c runtime/flow_runtime.c -o flowc_bs2_asan -lm -lpthread
./flowc_bs2_asan emit-c /tmp/test_hello.flow --stdlib stdlib -o /dev/null 2>&1 | head -20
```

Expected: no UAF, no stack-use-after-return.

- [ ] **Step 6: Verify cleanup in emitted C**

```bash
./flowc_bs2 emit-c /tmp/test_hello.flow --stdlib stdlib -o /tmp/test_out.c
grep -c 'release\|retain' /tmp/test_out.c
```

Expected: non-zero count of release and retain calls.

- [ ] **Step 7: Final commit**

```bash
git commit -m "refcount: full cleanup system verified — stage 2 emits retain/release"
```
