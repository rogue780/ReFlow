# Design: Completing Flow's Linear Ownership Model

**Date:** 2026-03-12
**Status:** Approved
**Branch:** story/RT-11-self-hosted-compiler

---

## Problem Statement

The Flow spec defines linear ownership ("every value has exactly one owner") AND ARC
refcounting, but never specifies how they interact for structs containing refcounted
fields. Structs are stack-allocated value types (copied by C memcpy), but their fields
can be heap-allocated refcounted pointers (strings, arrays, maps). Every struct copy
silently aliases heap data with no compiler-visible event.

The ARC section lists 5 rules but leaves 10 critical situations undefined:

1. Struct assignment (`let b = a`) — move or copy-with-retain?
2. Struct return — who retains the fields?
3. Struct in containers — who owns the fields after insertion?
4. Container element cleanup — how are struct elements destroyed?
5. Sum type variant cleanup — how are variant payloads destroyed?
6. Struct field reassignment — release-before-reassign for fields?
7. Struct spread (`..source`) — move or copy?
8. Nested struct cleanup — recursive field release?
9. Borrow+ARC interaction — does borrowing a struct retain its fields?
10. `&` ref on structs — what does refcount increment mean for a stack value?

This causes ~1.42 MB of memory leaks in the self-hosted compiler (ASAN), 12+ special-case
mechanisms in lowering.py, and multiple UAF bugs from incorrect retain/release pairing.

---

## Solution: Affine Types with Move Semantics

### Type Classification

All Flow types are classified into four categories:

| Category | Types | Assignment | Cleanup |
|----------|-------|------------|---------|
| **Value** | int, float, bool, byte, char | Copy (stack) | None |
| **Refcounted** | string, array, map, set, buffer, stream | Retain (ARC) | Release at scope exit |
| **Affine** | Structs with ≥1 refcounted/affine field; sum types with affine variants | **Move** | Destroy (release all fields) |
| **Trivial** | Structs with only value-type fields | Copy (stack) | None |

### Affine Type Rules

1. **Assignment = move.** `let b = a` transfers ownership from `a` to `b`. `a` is
   consumed and cannot be used afterward. The compiler tracks consumed bindings and
   rejects programs that use consumed bindings.

2. **Function parameters = implicit borrow.** `foo(a)` borrows `a` temporarily.
   Ownership reverts when `foo` returns, unless `a` escapes. No retain/release for the
   borrow. The callee receives a stack copy of the struct but does NOT own the
   refcounted fields — no cleanup at callee scope exit for borrowed params.

3. **Return = move.** `return val` moves `val` to the caller. No retain needed. The
   callee's binding is consumed; the caller's binding becomes the new owner.

4. **Container insertion = move.** `array.push(arr, val)` and `map.set(m, k, val)`
   move `val` into the container. `val` is consumed. The container owns the element
   and is responsible for destroying it when the container is released.

5. **Container access = clone.** `array.get(arr, i)` returns a deep copy for affine
   elements (all refcounted fields retained). The container retains its original. This
   is an implicit `@` on the element.

6. **For-loop iteration = borrow.** `for(x in container)` borrows each element. No
   clone, no cleanup per iteration. Efficient read-only access. To own an element
   during iteration, use `let owned = @x`.

7. **Explicit copy.** `@expr` produces a deep copy with all refcounted fields retained.
   Both the original and copy are independently owned. This is a generated
   `_fl_clone_<Type>` call in C.

8. **`&` operator.** Valid only on refcounted types. Not valid on affine types — there
   is no refcount to increment on a stack-allocated struct.

9. **Scope-exit destroy.** When an affine binding goes out of scope, the compiler
   releases each refcounted field. Consumed bindings are skipped.

10. **Sum type destroy.** Switch on the variant tag, destroy the active variant's
    affine/refcounted fields.

11. **Struct construction.** When placing a refcounted value into a struct field
    (`Token{.value = name}`), the value is retained to give the struct its own +1.
    This is unchanged from current ARC behavior — the struct field is a new reference
    to existing heap data.

12. **Struct spread.** `..source` moves all fields from source. Source is consumed.

### What This Resolves

- **No retain inflation:** Moves don't retain. Only one owner exists.
- **No depth restriction:** All scopes use the same rules.
- **Container cleanup works:** Container owns elements → destructor always runs.
- **Sum type destructors safe:** No shared ownership → no UAF from double-destroy.
- **~60% of lowering.py special cases removed.**

### Impact on Self-Hosted Compiler (.flow files)

Most patterns are already compatible:
- Function calls: already borrows. No change.
- Returns: already moves. No change.
- Container push/set: conceptually already moves. No change.
- `let b = a` on structs: now a move. Need `@a` where both are used after.
- For-loops: already read-only. Now formally borrows.

### Impact on Python Compiler (lowering.py)

**Remove:**
- Retain-on-store for struct field copies
- `_transferred_struct_vars` / `_transferred_struct_bases`
- `_is_allocating_expr` heuristic for struct returns
- depth==0 vs depth>0 distinction
- Release-on-reassignment for struct fields

**Keep:**
- ARC for refcounted types (string, array, map)
- Scope-exit releases for refcounted locals
- Release-before-reassign for `:mut` refcounted bindings

**Add:**
- Consumed-binding tracking (resolver/typechecker)
- Generated `_fl_clone_<Type>` functions
- Element destructors for containers of affine types
- Sum type destructors (now safe)

---

## Spec Files to Update

1. **flow_spec.md** — Ownership section: add type classification, clarify struct
   assignment as move, update ARC rules section. Memory Model section: add affine
   type rules.
2. **stdlib_spec.md** — Container modules: document move-on-insert, clone-on-get.
3. **book/ch08_ownership.md** — Add affine types section, update examples, add
   move semantics explanation.
