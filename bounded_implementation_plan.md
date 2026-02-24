# Flow Bounded Generics: Implementation Plan

## Overview

Flow has generics (`<T>`) and interface fulfillment (`type Foo fulfills Bar`),
but these two features are disconnected. There is no way to constrain a type
parameter to types that satisfy a specific interface. This forces the stdlib to
define per-type variants (`abs_int`, `abs_float`, `min_int`, `min_float`) instead
of a single generic function.

This plan adds **bounded generic type parameters** so that generics and interfaces
work together as a unified system. The syntax reuses the existing `fulfills`
keyword:

```
fn abs<T fulfills Numeric>(n: T): T { ... }
fn convert<A fulfills Serializable, B fulfills Parseable>(a: A): B { ... }
type Cache<K fulfills Hashable, V>(data: map<K, V>) { ... }
```

Bounded generics are not a bolt-on feature. They complete the connection between
two existing language systems (generics and interfaces) and are integrated at
every level: specification, AST, parser, type registry, and type checker.

## Conventions

- **Epic**: A major phase of work. Epics are sequential unless noted.
- **Story**: A cohesive group of tickets within an epic.
- **Ticket**: A single unit of work. Each ticket produces one testable change.
- **ID format**: `BG-EPIC-STORY-TICKET` (e.g., `BG-1-2-3`)
- **`[BLOCKER]`**: Must complete before any ticket in the next story/epic.

## Prerequisites

- Epics 2-8 of the compiler plan (RT) must be complete (they are).
- The `fulfills` keyword is already tokenized (`TokenType.FULFILLS`).
- Interface fulfillment validation (`_check_fulfillment`) already works.

---

# EPIC 0: Specification

Spec changes come first. Every implementation ticket references a spec section.

## Story 0-1: Language Specification Update

**BG-0-1-1** `[BLOCKER]`
Add bounded generics to the specification in `flow_spec.md`.

This is not an appendix or addendum. Bounded generics are integrated into the
existing sections:

1. **Extend "Generic Types" (line 898)**: After the existing `Pair<A, B>` example,
   add a bounded example showing a type whose type parameter must fulfill an
   interface:

   ```
   type SortedList<T fulfills Comparable> {
       items: array<T>,

       fn insert(self, val: T): SortedList<T> { ... }
   }
   ```

2. **Extend "Generic Functions" (line 1137)**: After the existing `transform<T, U>`
   example, add bounded function examples:

   ```
   fn max<T fulfills Comparable>(a: T, b: T): T {
       return if a.compare(b) > 0 then a else b
   }

   fn serialize_all<T fulfills Serializable>(items: array<T>): array<string> {
       ...
   }
   ```

3. **Extend "Interfaces" (line 930)**: Add a subsection "Bounded Type Parameters"
   after "Generic Interfaces" (line 964) covering:
   - Syntax: single bound, multiple bounds with parentheses, multiple params
   - Semantics: bounds are checked at call sites and type instantiation sites
   - Interaction with `fulfills` on type declarations (both can coexist)
   - Error behavior: clear compile-time error when a concrete type does not
     satisfy a bound

4. **Syntax summary**: Document all three forms:
   ```
   ; Single bound
   fn foo<T fulfills Printable>(x: T): string { ... }

   ; Multiple bounds on one parameter (parenthesized)
   fn bar<T fulfills (Printable, Hashable)>(x: T): string { ... }

   ; Multiple bounded parameters
   fn baz<A fulfills Serializable, B fulfills Parseable>(a: A): B { ... }

   ; Mixed bounded and unbounded
   fn mix<T fulfills Comparable, U>(a: T, b: U): T { ... }
   ```

5. **Disambiguation rule**: Without parentheses, a comma after a bound name
   starts a new type parameter, not a second bound. This is unambiguous:
   - `<T fulfills A, B>` = two params: `T` with bound `A`, and unbounded `B`
   - `<T fulfills (A, B)>` = one param: `T` with bounds `A` and `B`

---

# EPIC 1: AST and Parser

The AST change is the foundation. Every downstream pass reads the AST, so this
must be done first and done right. The key decision: `TypeParam` is the canonical
representation for type parameters everywhere in the system, not a wrapper bolted
onto an existing string list.

## Story 1-1: AST Foundation

**BG-1-1-1** `[BLOCKER]`
Create the `TypeParam` dataclass in `compiler/ast_nodes.py`.

Insert before `FnDecl` (line 490):

```python
@dataclass
class TypeParam(ASTNode):
    name: str
    bounds: list[TypeExpr]  # empty list = unconstrained
```

`TypeParam` extends `ASTNode` so it carries `line` and `col` for error reporting.
An unconstrained parameter like `T` in `<T>` has `bounds=[]`. A bounded parameter
like `T fulfills Comparable` has `bounds=[NamedType("Comparable")]`.

This is an AST node, not a wrapper. It participates in the AST tree like any
other node.

**BG-1-1-2** `[BLOCKER]`
Update the `type_params` field on all four declaration nodes.

Change in `compiler/ast_nodes.py`:
- `FnDecl.type_params` (line 493): `list[str]` -> `list[TypeParam]`
- `TypeDecl.type_params` (line 513): `list[str]` -> `list[TypeParam]`
- `InterfaceDecl.type_params` (line 550): `list[str]` -> `list[TypeParam]`
- `AliasDecl.type_params` (line 559): `list[str]` -> `list[TypeParam]`

All four declaration types support bounded generics consistently. There is no
declaration type where generics work but bounds do not.

## Story 1-2: Parser Changes

**BG-1-2-1** `[BLOCKER]`
Rewrite `_parse_type_params` in `compiler/parser.py` to produce `list[TypeParam]`.

Replace the current implementation (lines 523-535) with two methods:

```python
def _parse_type_param(self) -> TypeParam:
    """Parse a single type parameter: IDENT [ fulfills BOUND ]"""
    tok = self.expect(TokenType.IDENT)
    bounds: list[TypeExpr] = []
    if self.check(TokenType.FULFILLS):
        self.advance()
        if self.check(TokenType.LPAREN):
            # Multiple bounds: T fulfills (A, B, C)
            self.advance()
            bounds.append(self.parse_type_expr())
            while self.check(TokenType.COMMA):
                self.advance()
                bounds.append(self.parse_type_expr())
            self.expect(TokenType.RPAREN)
        else:
            # Single bound: T fulfills A
            bounds.append(self.parse_type_expr())
    return TypeParam(
        name=tok.value,
        bounds=bounds,
        line=tok.line,
        col=tok.col,
    )

def _parse_type_params(self) -> list[TypeParam]:
    """Parse generic type parameter list: <T, U fulfills V, W>"""
    self.expect(TokenType.LT)
    params: list[TypeParam] = []
    if not self.check(TokenType.GT):
        params.append(self._parse_type_param())
        while self.check(TokenType.COMMA):
            self.advance()
            params.append(self._parse_type_param())
    self.expect(TokenType.GT)
    return params
```

The `_parse_type_param` helper reuses `parse_type_expr()` for the bound, which
means bounds can be any valid type expression including generic interfaces
(`Mappable<int>`, `collection<K, V>`). This is consistent with how the
`fulfills` clause on type declarations already works (parser.py line 589).

**BG-1-2-2**
Update the 4 call sites that receive `_parse_type_params` results.

In `compiler/parser.py`, change the type annotation at each call site:
- Line 467 (`parse_fn_decl`): `type_params: list[str]` -> `type_params: list[TypeParam]`
- Line 581 (`parse_type_decl`): `type_params: list[str]` -> `type_params: list[TypeParam]`
- Line 809 (`parse_interface_decl`): `type_params: list[str]` -> `type_params: list[TypeParam]`
- Line 877 (`parse_alias_decl`): `type_params: list[str]` -> `type_params: list[TypeParam]`

Also update the `_parse_sum_type` (line 605) and `_parse_struct_type` (line 671)
method signatures: `type_params: list[str]` -> `type_params: list[TypeParam]`.

Import `TypeParam` at the top of `parser.py`.

## Story 1-3: Parser Tests

**BG-1-3-1**
Fix existing parser tests in `tests/unit/test_parser.py`.

5 tests assert `type_params == ["T"]` or similar. Update each to check
`TypeParam` objects:

- `test_generic_fn_single_type_param` (line 234):
  `assertEqual(decl.type_params, ["T"])` ->
  `assertEqual(len(decl.type_params), 1)`
  `assertEqual(decl.type_params[0].name, "T")`
  `assertEqual(decl.type_params[0].bounds, [])`

- `test_generic_fn_multiple_type_params` (line 239):
  Check `[0].name == "T"`, `[1].name == "U"`, both with empty bounds.

- `test_fn_no_type_params_by_default` (line 244):
  `assertEqual(decl.type_params, [])` still works (empty list).

- `test_generic_alias` (line 450):
  Check `[0].name == "T"`, `[1].name == "U"`, both with empty bounds.

- `test_alias_no_type_params_by_default` (line 455):
  `assertEqual(decl.type_params, [])` still works.

**BG-1-3-2**
Add new parser tests for bounded generics.

New `TestBoundedGenerics` class in `tests/unit/test_parser.py`:

| Test | Input | Assertion |
|------|-------|-----------|
| `test_single_bound` | `fn f<T fulfills Printable>(): void {}` | 1 param, name="T", 1 bound (NamedType "Printable") |
| `test_no_bound_unchanged` | `fn f<T>(): void {}` | 1 param, name="T", 0 bounds |
| `test_multiple_params_each_bounded` | `fn f<T fulfills A, U fulfills B>(): void {}` | 2 params, each with 1 bound |
| `test_multi_bound_parenthesized` | `fn f<T fulfills (A, B)>(): void {}` | 1 param, 2 bounds |
| `test_generic_interface_bound` | `fn f<T fulfills Mappable<int>>(): void {}` | 1 param, 1 bound (GenericType) |
| `test_bounded_type_decl` | `type Box<T fulfills P> { val: T }` | TypeDecl, 1 param with bound |
| `test_bounded_interface_decl` | `interface Container<T fulfills Comparable> { ... }` | InterfaceDecl, 1 param with bound |
| `test_bounded_alias_decl` | `alias Sorted<T fulfills Comparable>: array<T>` | AliasDecl, 1 param with bound |
| `test_mixed_bounded_unbounded` | `fn f<T fulfills A, U>(): void {}` | 2 params: first bounded, second unbounded |
| `test_disambiguation_comma` | `fn f<T fulfills A, B>(): void {}` | 2 params: `T fulfills A` and unbounded `B` (not `T fulfills (A, B)`) |

---

# EPIC 2: Type System

The type system changes have three layers: (1) registry updates so bounds are
preserved in TypeInfo/InterfaceInfo, (2) bounds validation at call sites and
instantiation sites, and (3) method resolution within bounded generic bodies.

## Story 2-1: Type Registry Updates

**BG-2-1-1** `[BLOCKER]`
Update `TypeInfo` and `InterfaceInfo` in `compiler/typechecker.py` to use
`list[TypeParam]`.

Change the field types:
- `TypeInfo.type_params` (line 295): `list[str]` -> `list[TypeParam]`
- `InterfaceInfo.type_params` (line 310): `list[str]` -> `list[TypeParam]`

Import `TypeParam` at the top of `typechecker.py`.

This is the critical design decision that prevents the feature from feeling
like an afterthought. Bounds are not stripped at the AST-to-registry boundary.
They are preserved in the type registry and available for validation at every
point where type parameters are instantiated.

**BG-2-1-2** `[BLOCKER]`
Update all typechecker code that reads `type_params` as `list[str]`.

Locations that assume `type_params` contains strings:

1. **Line 445** (`_register_types`, sum types):
   `type_params=decl.type_params` — now passes `list[TypeParam]` directly. OK.

2. **Line 469** (`_register_types`, struct types):
   Same — passes directly. OK.

3. **Line 532** (`_build_interface_registry`):
   `type_params=decl.type_params` — passes directly. OK.

4. **Line 591** (`_check_fulfillment`, substitution env):
   ```python
   for param_name, arg_type in zip(iface.type_params, type_args):
       env[param_name] = arg_type
   ```
   Change to:
   ```python
   for tp, arg_type in zip(iface.type_params, type_args):
       env[tp.name] = arg_type
   ```

5. **Line 582** (`_check_fulfillment`, count check):
   `len(iface.type_params)` — works unchanged (len of list).

6. **Any other location** that iterates `type_params` and expects strings:
   search for `.type_params` across the file and update each to use `.name`.

**BG-2-1-3**
Update the hardcoded Exception interface registration.

At line 489:
```python
type_params=["T"]
```
Change to:
```python
type_params=[TypeParam(name="T", bounds=[], line=0, col=0)]
```

## Story 2-2: Bounds Validation at Call Sites

**BG-2-2-1**
Implement `_infer_type_env_from_call` in `compiler/typechecker.py`.

This method takes a `FnDecl` and the concrete argument types from a call site,
and infers which concrete types correspond to each type parameter:

```python
def _infer_type_env_from_call(
    self,
    fn_decl: FnDecl,
    arg_types: list[Type],
) -> TypeEnv:
    """Infer concrete types for type params from call arguments."""
    env: TypeEnv = {}
    tp_names = {tp.name for tp in fn_decl.type_params}
    for param, arg_t in zip(fn_decl.params, arg_types):
        resolved = self._resolve_type_expr(param.type_ann)
        self._match_type_env(resolved, arg_t, env, tp_names)
    return env
```

Add `_match_type_env` as a recursive helper that walks type structure
(`TTypeVar`, `TArray`, `TOption`, `TStream`, `TFn`, `TResult`) to extract
bindings. For example, if the declared param type is `array<T>` and the
argument type is `array<int>`, it binds `T -> TInt(32)`.

**BG-2-2-2**
Implement `_check_type_satisfies_bound` in `compiler/typechecker.py`.

This method checks whether a concrete type satisfies a single bound:

```python
def _check_type_satisfies_bound(
    self,
    concrete: Type,
    bound_expr: TypeExpr,
    node: ASTNode,
    tp_name: str,
) -> None:
    """Verify that concrete type satisfies the interface bound."""
```

Logic:
1. Resolve `bound_expr` to an interface name (and optional type args).
2. Look up the interface in `_interface_registry`.
3. Look up the concrete type in `_type_registry`.
4. Check that the type's methods satisfy all interface method signatures.
5. Reuse the existing method-checking logic from `_check_fulfillment`
   (lines 594-645), extracted into a shared helper to avoid duplication.

Error message format:
```
type 'int' does not fulfill interface 'Printable' required by
type parameter 'T' in call to 'format'
```

The error message names the concrete type, the interface, the type parameter,
and the function being called. This makes bounded generic errors as clear as
regular fulfillment errors.

**BG-2-2-3** `[BLOCKER]`
Implement `_validate_generic_call_bounds` and wire into the type checker.

Top-level orchestrator method:

```python
def _validate_generic_call_bounds(
    self,
    fn_decl: FnDecl,
    arg_types: list[Type],
    node: ASTNode,
) -> None:
    """Check all bounded type params are satisfied at this call site."""
    # Skip if no bounded params
    if not any(tp.bounds for tp in fn_decl.type_params):
        return
    env = self._infer_type_env_from_call(fn_decl, arg_types)
    for tp in fn_decl.type_params:
        if not tp.bounds:
            continue
        concrete = env.get(tp.name)
        if concrete is None or isinstance(concrete, (TAny, TTypeVar)):
            continue  # cannot validate — generic context
        for bound_expr in tp.bounds:
            self._check_type_satisfies_bound(
                concrete, bound_expr, node, tp.name)
```

Wire into `_infer_expr_inner`:

1. **`Call` case** (line 989): After `_check_call_args` succeeds, if the callee
   resolves to a `FnDecl` via the resolver, call `_validate_generic_call_bounds`.

2. **`MethodCall` case** (line 1001): In the namespace function path (lines
   1006-1014), after `_check_call_args`, if `fn_decl` has bounded params, call
   `_validate_generic_call_bounds`.

Both call sites must resolve the callee back to the `FnDecl` AST node. The
resolver already stores the declaration in `resolved_sym.decl`, so this
information is available.

## Story 2-3: Bounds Validation at Instantiation Sites

**BG-2-3-1**
Validate bounds when constructing generic types.

When the type checker encounters a generic type construction like
`SortedList<int> { ... }` or a constructor call like
`SortedList<int>.new(...)`, it must verify that `int` satisfies the bounds
on `SortedList`'s type parameter `T`.

Add validation in `_resolve_type_expr` (or wherever generic type expressions
are resolved): when resolving `GenericType(base, args)`, look up the
`TypeInfo` for `base`, zip `args` with `info.type_params`, and for each
bounded param, call `_check_type_satisfies_bound`.

**BG-2-3-2**
Validate bounds when using generic aliases.

Same as BG-2-3-1 but for `AliasDecl`. When resolving an alias like
`alias Sorted<T fulfills Comparable>: array<T>`, and someone writes
`Sorted<int>`, verify `int fulfills Comparable`.

## Story 2-4: Refactor Fulfillment Checking

**BG-2-4-1**
Extract shared fulfillment logic from `_check_fulfillment`.

The method-checking loop in `_check_fulfillment` (lines 594-645) and the new
`_check_type_satisfies_bound` perform the same validation: "does this type
have all the methods required by this interface, with compatible signatures?"

Extract this into a shared private method:

```python
def _check_methods_satisfy_interface(
    self,
    type_name: str,
    type_methods: dict[str, TFn],
    type_constructors: dict[str, TFn],
    iface: InterfaceInfo,
    iface_name: str,
    type_args: list[Type],
    node: ASTNode,
    context_msg: str,  # e.g., "declares fulfills" or "required by bound"
) -> None:
```

Update `_check_fulfillment` and `_check_type_satisfies_bound` to delegate to
this shared method. This eliminates code duplication and ensures that
fulfillment checking and bounds checking use identical logic.

---

# EPIC 3: Testing and Validation

Comprehensive testing ensures the feature works correctly across all declaration
types and produces clear error messages.

## Story 3-1: Typechecker Unit Tests

**BG-3-1-1**
Add typechecker tests for satisfied bounds.

New `TestBoundedGenericFunctions` class in `tests/unit/test_typechecker.py`:

| Test | Scenario |
|------|----------|
| `test_bounded_call_satisfying_type` | Type fulfills the interface, call succeeds |
| `test_unconstrained_generic_unchanged` | No bounds, no error (backward compat) |
| `test_multi_bound_all_satisfied` | `T fulfills (A, B)`, type fulfills both |
| `test_multiple_bounded_params` | `<T fulfills A, U fulfills B>`, both satisfied |
| `test_bounded_type_decl_construction` | `type Box<T fulfills P> { ... }`, valid instantiation |

Each test defines a minimal interface, a type that fulfills it, and a bounded
generic function or type, then verifies the program typechecks without error.

**BG-3-1-2**
Add typechecker tests for violated bounds.

| Test | Scenario | Expected error |
|------|----------|----------------|
| `test_bounded_call_unsatisfying_type` | Type missing required method | TypeError: does not fulfill |
| `test_multi_bound_partial_failure` | Type fulfills only one of two bounds | TypeError: does not fulfill |
| `test_bounded_type_decl_bad_instantiation` | `Box<int>` where `int` doesn't fulfill bound | TypeError |
| `test_bounded_alias_bad_instantiation` | `Sorted<int>` where `int` doesn't fulfill bound | TypeError |
| `test_unknown_interface_in_bound` | `T fulfills NonExistent` | TypeError: unknown interface |

**BG-3-1-3**
Add typechecker tests for interactions with existing features.

| Test | Scenario |
|------|----------|
| `test_bounded_generic_with_option_return` | `fn f<T fulfills P>(x: T): T?` |
| `test_bounded_generic_with_array_param` | `fn f<T fulfills P>(items: array<T>): void` |
| `test_bounded_with_fulfills_on_type` | Type has both `fulfills` clause and bounded methods |
| `test_bounded_generic_interface_bound` | `<T fulfills Mappable<int>>` with generic interface |

## Story 3-2: Negative Compile Tests

**BG-3-2-1**
Add negative compile test: unsatisfied bound.

`tests/programs/errors/bounded_generic_unsatisfied.flow`:
```
interface Printable {
    fn to_str(self): string
}

type Plain { x: int }

fn format<T fulfills Printable>(val: T): string {
    return val.to_str()
}

fn main(): void {
    let p = Plain { x: 1 }
    format(p)
}
```

`tests/expected_errors/bounded_generic_unsatisfied.txt`:
```
TypeError
does not fulfill interface 'Printable'
```

**BG-3-2-2**
Add negative compile test: unknown interface in bound.

`tests/programs/errors/bounded_generic_unknown_iface.flow`:
```
fn process<T fulfills NonExistent>(val: T): void { }

fn main(): void { }
```

`tests/expected_errors/bounded_generic_unknown_iface.txt`:
```
TypeError
unknown interface 'NonExistent'
```

**BG-3-2-3**
Add negative compile test: wrong type argument count with bounded generic type.

`tests/programs/errors/bounded_generic_wrong_args.flow`:
```
interface Sized {
    fn size(self): int
}

type Container<T fulfills Sized> { item: T }

fn main(): void {
    let c: Container<int, string> = ...
}
```

`tests/expected_errors/bounded_generic_wrong_args.txt`:
```
TypeError
expects 1 type argument(s) but got 2
```

## Story 3-3: Final Validation

**BG-3-3-1**
Run `make test` and verify all tests pass with zero failures.

Verify:
- All existing 886+ tests still pass (no regressions)
- All new bounded generic parser tests pass
- All new bounded generic typechecker tests pass
- All new negative compile tests pass

---

# Future: Body-Level Method Resolution

This section documents the next phase of bounded generics, which is deferred
from this plan but architecturally prepared for.

## The Problem

With this plan's implementation, bounded generics are validated at call sites
and instantiation sites. But inside the body of a bounded generic function,
the type checker cannot resolve methods on the type variable:

```
fn format<T fulfills Printable>(val: T): string {
    return val.to_str()   ; <-- currently fails: no method 'to_str' on TTypeVar
}
```

The type checker sees `val` as `TTypeVar("T")` and cannot resolve `to_str()`.

## Why It's Deferred

Resolving methods on `TTypeVar` requires the type checker to:
1. Look up which `TypeParam` owns the type variable
2. Resolve each bound to an interface
3. Collect all methods from all bounds
4. Check the method call against those signatures
5. Return a result type that may contain `TTypeVar` references

This is straightforward type-checking work, but the lowering pass must also
handle it: a method call on an erased `void*` needs to be dispatched correctly
in C. For the bootstrap compiler's erasure strategy (`TTypeVar` -> `void*`),
this requires either:
- Emitting a cast + direct call (if the method is known at compile time)
- Emitting a vtable lookup (if dynamic dispatch is needed)

The lowering and emitter changes are out of scope for this plan. The
architecture supports adding them: `TypeParam` nodes carry bounds, bounds
map to interfaces, interfaces have method signatures. All the information
needed for body-level resolution is available in the type registry.

## When to Implement

Body-level method resolution should be implemented when:
1. The stdlib wants to define generic functions that call interface methods
2. The self-hosted compiler needs it for its own implementation
3. The lowering strategy for erased generics is finalized

## Architecture Readiness

This plan ensures readiness by:
- Storing `TypeParam` (with bounds) in `TypeInfo` and `InterfaceInfo`
- Making bounds available throughout the type checker, not just at validation
- Using the same fulfillment-checking logic for both `fulfills` clauses and
  bounds, so the semantics are guaranteed to be consistent
- Keeping `TypeParam` as an AST node with line/col for error reporting

---

# Files Modified

| File | Change |
|------|--------|
| `flow_spec.md` | Extend generics and interfaces sections with bounded generics |
| `compiler/ast_nodes.py` | Add `TypeParam` dataclass, change 4 field types |
| `compiler/parser.py` | New `_parse_type_param`, rewrite `_parse_type_params`, update 6 signatures |
| `compiler/typechecker.py` | Update `TypeInfo`/`InterfaceInfo` field types, update all `type_params` reads, add 4 new methods, wire into `Call`/`MethodCall`/type instantiation |
| `tests/unit/test_parser.py` | Fix 5 existing tests, add ~10 new bounded generic tests |
| `tests/unit/test_typechecker.py` | Add ~14 new bounded generic tests |
| `tests/programs/errors/bounded_generic_*.flow` | 3 new error programs |
| `tests/expected_errors/bounded_generic_*.txt` | 3 new expected error files |

# Files NOT Modified

| File | Reason |
|------|--------|
| `compiler/lexer.py` | `fulfills` is already a keyword token |
| `compiler/resolver.py` | Does not reference `type_params` (confirmed by search) |
| `compiler/lowering.py` | Does not reference `type_params` (confirmed by search) |
| `compiler/emitter.py` | No change — generics erase to `void*` for bootstrap |
| `compiler/mangler.py` | No new name forms needed |
| `compiler/errors.py` | `TypeError` is already sufficient |
| `runtime/` | Bounded generics are a compile-time-only feature |

# Dependency Map

```
EPIC 0 (Specification)
  └─ must complete before EPIC 1

EPIC 1 (AST and Parser)
  └─ depends on EPIC 0
  └─ must complete before EPIC 2

EPIC 2 (Type System)
  └─ depends on EPIC 1
  └─ must complete before EPIC 3

EPIC 3 (Testing and Validation)
  └─ depends on EPIC 2
  └─ final milestone
```

All epics are sequential. The AST change propagates through every downstream
component, so there is no parallelism opportunity within this plan.

# Ticket Counts

| Epic | Stories | Tickets |
|------|---------|---------|
| 0: Specification | 1 | 1 |
| 1: AST and Parser | 3 | 6 |
| 2: Type System | 4 | 7 |
| 3: Testing and Validation | 3 | 7 |
| **Total** | **11** | **21** |

# Verification

After all tickets are complete:

```bash
make test                                    # all tests pass, zero failures
pytest tests/unit/test_parser.py -v          # parser tests including bounded generics
pytest tests/unit/test_typechecker.py -v     # typechecker tests including bounds validation
```
