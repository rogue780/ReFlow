---
name: reflow-spec
description: Guides correct implementation of ReFlow language features by surfacing the spec sections and subtle decisions most likely to be misimplemented. Read this skill before implementing any type system, ownership, or semantic feature.
---

# ReFlow Spec Reference Skill

The ReFlow language specification lives at `reflow_spec.md` in the project root. This skill does not replace reading it — it tells you which parts to read and which decisions are most likely to be misunderstood or implemented incorrectly.

---

## Before Implementing Any Language Feature

1. Open `reflow_spec.md`.
2. Find the section that defines the feature you are implementing.
3. Read it fully, including all sub-sections and examples.
4. Read any sections it cross-references.
5. Only then write code.

This takes five minutes and saves hours of debugging subtle semantic bugs.

---

## High-Risk Areas: Read These With Extra Care

The following areas of the spec are most commonly misimplemented because the "obvious" behavior differs from the specified behavior. When working on these, read the spec section twice.

### 1. `:imut` and `:mut` Parameter Passing

The rules are asymmetric and counterintuitive:

- A parameter declared `:imut` accepts **any** binding — mutable or immutable. The function promises not to mutate it.
- A parameter declared `:mut` requires the caller to pass a `:mut` binding. The function may mutate the value and the caller sees the mutations.
- Passing an immutable binding to a `:mut` parameter requires an explicit `@expr` copy operator. The `@` makes a mutable copy.
- If a parameter has no modifier, it behaves like `:imut`.

**Common mistake:** implementing `:imut` as "rejects `:mut` bindings" (the reverse of the correct rule).

Relevant spec section: **Ownership and Borrowing > Parameter Modifiers**

### 2. Option Auto-Lifting

Auto-lifting wraps a plain `T` in `some(T)` when the target type is `option<T>`. It fires **only** when:

- The target type is statically known to be `option<T>`, AND
- The source type is exactly `T` (not already `option<T>`), AND
- The context is not a generic type variable `T` where `T` could be any type

Auto-lifting does **not** fire:
- In generic functions where the type parameter could be any type
- When the source is already `option<T>` (no double-wrapping)
- Inside match arm bodies where `some(v)` binds `v` (already unwrapped)

The type checker must emit an implicit `SomeExpr` node when lifting occurs, so the lowering pass can generate the correct tagged struct.

Relevant spec section: **Null, None, and Option > Auto-lifting Rules**

### 3. Struct Spread and Constructors

The `..source` spread syntax in type construction literals (`TypeName { field: val, ..source }`) copies all fields from `source` into the new value except those explicitly overridden.

Critical rule: **struct spread bypasses constructors**. If a type has named constructors, literal construction is normally disabled. But struct spread in lowering generates a direct struct literal in C — it does not call a constructor. This is intentional and documented.

The emitter generates something like:
```c
MyType result = source;    /* copy all fields */
result.field = val;        /* override specific fields */
```

Do not route spread construction through constructors. Do not emit a constructor call when spreading.

Relevant spec section: **Types > Struct Spread (..)**

### 4. Exception Data: `ex.data` vs `ex.original`

The `Exception<T>` interface has two payload accessors:
- `ex.data(self): T` — the current payload, **mutable in retry blocks**
- `ex.original(self): T` — the original payload at throw time, **always immutable**

In the generated C:
- The concrete exception type has a `:mut` field for `data` (the `payload` field) and an immutable field for `original` (the `original_payload` field).
- In a `retry` block, the emitter must emit code that writes to `payload`, not `original_payload`.
- `original_payload` is set exactly once, at construction time, and is never written again.

The retry mechanism depends on this distinction. If `ex.data` and `ex.original` point to the same field, retry blocks cannot correct the input before re-running the function.

Relevant spec section: **Exception Handling > Defining Exception Types**

### 5. Stream Single-Consumer Enforcement

A `stream<T>` binding may be consumed exactly once. "Consumed" means: passed to a function, used as the source of a `for` loop, passed into a composition chain, or used as the input to `buffer.collect`.

The type checker tracks a `consumed_streams: set[str]` (by binding name) in the current scope. When a stream binding is consumed, add it to the set. If it appears again, raise `TypeError`.

Limitations: this check is **conservative and name-based** for the bootstrap compiler. It does not handle aliasing (`let b = a; consume(a); consume(b)` — this should be caught but the bootstrap checker may miss it). Note aliasing as a known limitation.

Relevant spec section: **Ownership and Borrowing > Stream Single-Consumer**

### 6. `pure` Function Transitive Verification

A function marked `pure` must satisfy all of these simultaneously:
- Every function it calls is also `pure`
- It does not read or write any mutable static member (`Config.host = x` is forbidden)
- It does not call any function in the `io` module
- It does not call `snapshot()`
- It does not accept `:mut` parameters

The check is transitive: if `fn:pure a` calls `fn b`, and `b` calls `io.print`, then `a` fails the purity check even though `a` does not directly call `io.print`.

Build the purity map bottom-up: leaf functions first, callers after. A function with unknown callees (imported from an unanalyzed module) is assumed non-pure unless explicitly declared `pure` in its import.

Relevant spec section: **Philosophy** and **Purity Checking**

### 7. Composition Chain Auto-Mapping

When a `stream<T>` flows into a function that expects `T` (not `stream<T>`), the chain **automatically maps** — the function is applied element-wise and the result is `stream<result_type>`.

This is not an error. It is a core feature. The type checker must detect this case and insert an implicit map node. The lowering pass must expand the implicit map into a streaming function that calls the inner function once per element.

Distinguishing it from a type error: if the function expects `stream<T>` and receives `stream<T>`, no auto-mapping. If the function expects `T` and receives `stream<T>`, auto-map. If the function expects `U` (unrelated to `T`) and receives `stream<T>`, that is a `TypeError`.

Relevant spec section: **Streams > Auto-mapping in Chains**

### 8. Match Exhaustiveness: Sum Types vs Primitives

Exhaustiveness checking is a **compile error** for sum types and **a warning** for primitives:

- Sum type: every variant must be covered or `_` must be present. Missing a variant is `TypeError`.
- `option<T>`: both `some(v)` and `none` must be covered or `_` must be present. Compile error.
- `result<T, E>`: both `ok(v)` and `err(e)` must be covered or `_` must be present. Compile error.
- `int`, `string`, `bool`: exhaustiveness cannot be verified statically. Emit a compiler warning if no `_` arm. At runtime, an unmatched case calls `rf_panic("match not exhaustive")`.

Do not make primitive non-exhaustiveness a compile error. Do not silently ignore it either.

Relevant spec section: **Sum Types > Pattern Matching**, **Null, None, and Option > Pattern Matching**, **Result Type > Pattern Matching**

---

## Reference: Spec Section Map

When implementing a ticket in a given area, these are the primary spec sections to read:

| Area | Spec Section |
|------|-------------|
| Lexer | Comments, Keywords, Operators |
| Modules | Modules (full section) |
| Types | Built-in Types, Numeric Sizing, Value Types, Array Literals |
| Option/None | Null, None, and Option |
| Result | Result Type |
| Sum Types | Sum Types |
| Tuples | Tuples |
| Collections | Collections |
| Ownership | Ownership and Borrowing |
| Functions | Functions, Pure Functions |
| Composition | Composition Chains, Fan-out |
| Streams | Streams, Coroutines |
| Buffers | Buffers |
| Records | Records |
| Interfaces | Interfaces |
| Exceptions | Exception Handling |
| Pattern matching | Match |
| F-strings | String Interpolation |
| Congruence | Equality and Congruence |
| Snapshot | Snapshot Values |
| Typeof | typeof |

---

## When the Spec Is Silent

If the spec does not address a behavior:

1. Do not invent a behavior.
2. Make the safest choice (reject with a clear error rather than silently do something).
3. Add a `# SPEC GAP: <description>` comment in the code.
4. Note it in the PR description.

Spec gaps found during implementation are valuable feedback for the spec. They are not reasons to make something up.
