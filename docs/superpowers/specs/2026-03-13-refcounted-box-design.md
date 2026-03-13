# Design: Refcounted Box for Recursive Sum Type Pointers

**Date:** 2026-03-13
**Status:** Approved
**Branch:** story/RT-11-self-hosted-compiler

---

## Problem Statement

Recursive sum types (e.g., `Expr`, `TypeExpr`, `LType`, `TCType`) have variants
with fields that reference the same type. The compiler heap-boxes these fields
with raw `malloc`:

```c
Expr* left = (Expr*)malloc(sizeof(Expr));
(*left) = value;
```

These pointers have no ownership tracking. When a sum type value is shallow-copied
(by `array.push`, match binding, map storage, or assignment), both copies share
the same raw pointer. The destructor cannot `free()` the pointer because other
copies may still reference it — so it leaks permanently.

This accounts for **~1.48 MB** of leaked memory in the self-hosted compiler
(68,437 allocations). The affine ownership work (move semantics, scope-exit
destroy, consumed-binding tracking) handles structs with refcounted fields
correctly, but recursive sum type pointers are neither refcounted nor
stack-copyable — they fall through every cleanup mechanism.

### Affected Types

| Type | File | Variants with recursive pointers |
|------|------|----------------------------------|
| `Expr` | `self_hosted/ast.flow` | 24 (EBinOp, EUnaryOp, ECall, ...) |
| `TypeExpr` | `self_hosted/ast.flow` | 6 (TOptionType, TGenericType, ...) |
| `Stmt` | `self_hosted/ast.flow` | 12 (SLet, SAssign, SIf, ...) |
| `LExpr` | `self_hosted/lir.flow` | 5 (LEIndirectCall, LECast, ...) |
| `LType` | `self_hosted/lir.flow` | 3 (LPtr, LFnPtr, LStruct) |
| `LStmt` | `self_hosted/lir.flow` | via wrapper boxes |
| `TCType` | `self_hosted/typechecker.flow` | 11 (TCOption, TCResult, ...) |

---

## Solution: `FL_Box` — Refcounted Heap Box

### Runtime Type

Add a generic refcounted box to the runtime, following the existing ARC pattern
used by `FL_String` and `FL_Array`:

```c
typedef struct FL_Box {
    _Atomic fl_int64 refcount;
    fl_byte data[];   // flexible array member — holds the boxed value
} FL_Box;

FL_Box* fl_box_new(fl_int64 size);
void    fl_box_retain(FL_Box* box);
void    fl_box_release(FL_Box* box, void (*destructor)(void*));

#define FL_BOX_DEREF(box, T) (*(T*)((box)->data))
```

- `fl_box_new(size)`: Allocates `sizeof(FL_Box) + size`, sets refcount to 1.
- `fl_box_retain(box)`: Atomic increment of refcount.
- `fl_box_release(box, destructor)`: Atomic decrement. At refcount 0, calls
  `destructor(box->data)` to release the boxed value's internals (strings,
  arrays, nested boxes), then `free(box)`.
- `FL_BOX_DEREF(box, T)`: Dereferences the box as type `T`. Used for both
  read and write access.

### C Layout Change

```c
// Before (raw pointer):
struct Expr_EBinOp {
    fl_int id, line, col;
    FL_String* op;
    Expr* left;       // raw malloc'd pointer, no refcount
    Expr* right;
};

// After (refcounted box):
struct Expr_EBinOp {
    fl_int id, line, col;
    FL_String* op;
    FL_Box* left;     // refcounted, safe to share
    FL_Box* right;
};
```

### Allocation (Variant Constructor)

In `_lower_variant_ctor`, the current pattern:

```c
Expr* _fl_tmp = (Expr*)malloc(sizeof(Expr));
(*_fl_tmp) = value;
```

Becomes:

```c
FL_Box* _fl_tmp = fl_box_new(sizeof(Expr));
FL_BOX_DEREF(_fl_tmp, Expr) = value;
```

### Access (Field Dereference)

Wherever a recursive field is accessed via `LDeref`, the emitter changes from
`(*ptr)` to `FL_BOX_DEREF(ptr, Type)`:

```c
// Before:
Expr subexpr = (*_s->EBinOp.left);

// After:
Expr subexpr = FL_BOX_DEREF(_s->EBinOp.left, Expr);
```

The lowering continues to produce `LDeref` nodes. The emitter detects when the
pointer is an `FL_Box*` and emits the macro form.

### Retain / Release

Recursive pointer fields become refcounted. The lowering treats them like
other refcounted types:

- **Scope-exit release**: `fl_box_release(field, _fl_destroy_Expr)` — decrements
  refcount, destroys + frees at 0.
- **Copy/share retain**: `fl_box_retain(field)` — increments refcount, safe
  sharing.
- **Reassignment**: Release old box, assign new box (same as string/array
  reassignment pattern).

The sum type destructor changes from:

```c
case 7: {  // EBinOp
    fl_string_release(_s->EBinOp.op);
    _fl_destroy_Expr(_s->EBinOp.left);    // destroy contents, leak pointer
    _fl_destroy_Expr(_s->EBinOp.right);
    break;
}
```

To:

```c
case 7: {  // EBinOp
    fl_string_release(_s->EBinOp.op);
    fl_box_release(_s->EBinOp.left, _fl_destroy_Expr);   // destroy + free at rc=0
    fl_box_release(_s->EBinOp.right, _fl_destroy_Expr);
    break;
}
```

### Clone

The clone function changes from shallow-copy-pointer (shared, no retain) to
retain-the-box:

```c
// Before:
Expr _fl_clone_Expr(Expr _src) {
    Expr _dst = _src;
    _fl_retain_Expr(&_dst);  // retains strings/arrays, shares pointers
    return _dst;
}

// After:
Expr _fl_clone_Expr(Expr _src) {
    Expr _dst = _src;
    _fl_retain_Expr(&_dst);  // retains strings/arrays AND boxes
    return _dst;
}
```

The retainer gains `fl_box_retain` calls for recursive fields, matching how it
already calls `fl_string_retain` for string fields. Since box retain is just a
refcount bump, sharing is safe — no deep copy needed.

### Destroy-Before-Reassign

With `FL_Box`, the previously-reverted destroy-before-reassign for `:mut` affine
bindings becomes safe. Releasing the old box just decrements its refcount. If
other copies exist, the box survives. If it's the last reference, it's freed.

---

## Files Changed

| File | Change |
|------|--------|
| `runtime/flow_runtime.h` | Add `FL_Box` struct, function declarations, `FL_BOX_DEREF` macro |
| `runtime/flow_runtime.c` | Implement `fl_box_new`, `fl_box_retain`, `fl_box_release` (~20 lines) |
| `compiler/lowering.py` | Variant constructor: `fl_box_new` instead of `malloc`. Sum type destructor: `fl_box_release` instead of destroy-only. Retainer: `fl_box_retain` for recursive fields. Clone: retain box instead of share pointer. (~100 lines) |
| `compiler/emitter.py` | Emit `FL_BOX_DEREF(ptr, Type)` for `LDeref` on `FL_Box*` (~10 lines) |
| Golden files | Every test with recursive sum types gets updated C output |

**No changes to:**
- `.flow` source files (transparent to Flow programmers)
- Parser, resolver, typechecker
- Flow language spec (this is a compiler implementation detail)

---

## What This Resolves

- **1.48 MB of leaked recursive pointers** → freed when refcount reaches 0
- **Destroy-before-reassign** for `:mut` affine bindings → safe with refcounted boxes
- **Container element cleanup** → box release cascades through all nested pointers
- **Eliminates the "do NOT free" comment** in `_get_or_emit_sum_type_handlers`

## What Remains After This

The only remaining leaks would be structural program-exit leaks — data structures
(maps, arrays) in the self-hosted compiler that aren't explicitly released before
`main()` returns. These are a `.flow` source code concern, not a compiler concern,
and are standard for short-lived compiler processes.
