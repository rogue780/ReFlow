# ReFlow Stdlib Generics: Streamline Plan

## Overview

ReFlow's stdlib has ~35 type-suffixed duplicate functions across five modules:
`abs_int`/`abs_float`, `min_int`/`min_float`, `sort_ints`/`sort_strings`/
`sort_floats`, `assert_eq_int`/`assert_eq_string`/`assert_eq_bool`, and
`int_to_string`/`float_to_string`/`bool_to_string`. Users must remember
which suffix to use, and every new numeric type requires duplicating every
function.

This plan defines **four core interfaces** (`Comparable`, `Numeric`,
`Equatable`, `Showable`), registers built-in types as fulfilling them,
implements body-level method resolution for bounded generics, adds
compile-time monomorphization, and rewrites the affected stdlib modules
to use generic functions.

**Before:**
```
math.min_int(a, b)
math.min_float(a, b)
sort.sort_ints(arr)
sort.sort_strings(arr)
testing.assert_eq_int(expected, actual, msg)
testing.assert_eq_string(expected, actual, msg)
conv.int_to_string(n)
conv.float_to_string(f)
```

**After:**
```
math.min(a, b)
sort.sort(arr)
testing.assert_eq(expected, actual, msg)
conv.to_string(val)
```

The concrete type determines which specialization is called. The compiler
monomorphizes at each call site — no runtime dispatch, no vtables, no
overhead beyond what the type-specific functions already had.

## Conventions

- **Epic**: A major phase of work. Epics are sequential unless noted.
- **Story**: A cohesive group of tickets within an epic.
- **Ticket**: A single unit of work. Each ticket produces one testable change.
- **ID format**: `SG-EPIC-STORY-TICKET` (e.g., `SG-1-2-3`)
- **`[BLOCKER]`**: Must complete before any ticket in the next story/epic.

## Prerequisites

- **Bounded generics plan (BG-\*)** must be fully complete. This plan depends
  on: `TypeParam` in the AST, parser support for `T fulfills Interface`,
  call-site bound validation, and the refactored fulfillment-checking logic.
- The `Comparable` interface is referenced in the spec (lines 1003, 931) but
  not defined as a standalone interface. This plan defines it.
- The current lowering uses type erasure (`TTypeVar` → `void*`). This plan
  adds monomorphization as a parallel strategy for bounded generic functions
  whose bodies call interface methods.

---

# EPIC 0: Specification

Spec changes come first. Every implementation ticket references a spec section.

## Story 0-1: Core Interfaces

**SG-0-1-1** `[BLOCKER]`
Add four core interfaces to `reflow_spec.md`, in the Interfaces section
after "Generic Interfaces" (line 990).

These are language-level built-in interfaces — they exist without an
`interface` declaration in user code, like `Exception<T>` does today.

```
; Ordering comparison. Returns negative if self < other, zero if equal,
; positive if self > other.
interface Comparable {
    pure fn compare(self, other: self): int
}

; Arithmetic operations on numeric types.
interface Numeric {
    pure fn negate(self): self
    pure fn add(self, other: self): self
    pure fn sub(self, other: self): self
    pure fn mul(self, other: self): self
}

; Value equality.
interface Equatable {
    pure fn equals(self, other: self): bool
}

; Human-readable string conversion.
interface Showable {
    pure fn to_string(self): string
}
```

**Design decisions documented in the spec section:**

1. `self` as a type annotation in interface method parameters means "the
   implementing type." This is consistent with `self` as a return type
   (already in the spec at line 978). When `int fulfills Comparable`, the
   method signature becomes `compare(self: int, other: int): int`.

2. These interfaces have no constructors and no static methods. The `Numeric`
   interface intentionally omits `zero()` — a static factory would require
   static method dispatch, which is deferred. Functions that need a zero
   value (like `sum`) accept it as an explicit parameter.

3. Built-in types fulfill these interfaces via compiler registration, not
   source-level `fulfills` declarations. The compiler synthesizes the method
   implementations from primitive operators.

**SG-0-1-2** `[BLOCKER]`
Add a "Built-in Fulfillments" subsection documenting which built-in types
fulfill which interfaces:

| Type | Comparable | Numeric | Equatable | Showable |
|------|:---:|:---:|:---:|:---:|
| `int` | yes | yes | yes | yes |
| `int64` | yes | yes | yes | yes |
| `float` | yes | yes | yes | yes |
| `string` | yes (lexicographic) | — | yes | yes (identity) |
| `bool` | — | — | yes | yes |
| `char` | yes (byte value) | — | yes | yes |
| `byte` | yes | — | yes | yes |

Document the operator mappings:
- `int.compare(other)` → `(self < other) ? -1 : (self > other) ? 1 : 0`
- `int.negate()` → `-self`
- `int.add(other)` → `self + other`
- `int.equals(other)` → `self == other`
- `int.to_string()` → calls `rf_int_to_string`
- (Analogous for float, string, etc.)

## Story 0-2: Stdlib Spec Update

**SG-0-2-1** `[BLOCKER]`
Update `stdlib_spec.md` with generic function signatures. For each affected
module, replace the type-specific functions with generic equivalents:

**math module** — replace 7 type-specific functions with 4 generic ones:

| Before | After |
|--------|-------|
| `abs_int(n: int): int` | `abs<T fulfills (Numeric, Comparable)>(n: T): T` |
| `abs_float(f: float): float` | *(collapsed into `abs`)* |
| `min_int(a: int, b: int): int` | `min<T fulfills Comparable>(a: T, b: T): T` |
| `max_int(a: int, b: int): int` | `max<T fulfills Comparable>(a: T, b: T): T` |
| `min_float(a: float, b: float): float` | *(collapsed into `min`)* |
| `max_float(a: float, b: float): float` | *(collapsed into `max`)* |
| `clamp_int(val: int, lo: int, hi: int): int` | `clamp<T fulfills Comparable>(val: T, lo: T, hi: T): T` |

Functions that are inherently float-specific stay unchanged: `floor`, `ceil`,
`round`, `pow`, `sqrt`, `log`.

**sort module** — replace 3 type-specific functions with 1 generic:

| Before | After |
|--------|-------|
| `sort_ints(arr: array<int>): array<int>` | `sort<T fulfills Comparable>(arr: array<T>): array<T>` |
| `sort_strings(arr: array<string>): array<string>` | *(collapsed into `sort`)* |
| `sort_floats(arr: array<float>): array<float>` | *(collapsed into `sort`)* |

`sort_by<T>` and `reverse<T>` are already generic and stay unchanged.

**testing module** — replace 4 type-specific asserts with 1 generic:

| Before | After |
|--------|-------|
| `assert_eq_int(expected: int, actual: int, msg: string): void` | `assert_eq<T fulfills (Equatable, Showable)>(expected: T, actual: T, msg: string): void` |
| `assert_eq_int64(expected: int64, actual: int64, msg: string): void` | *(collapsed into `assert_eq`)* |
| `assert_eq_string(expected: string, actual: string, msg: string): void` | *(collapsed into `assert_eq`)* |
| `assert_eq_bool(expected: bool, actual: bool, msg: string): void` | *(collapsed into `assert_eq`)* |

`assert_eq_float` stays as `assert_approx` (epsilon comparison is a
different operation, not generic equality).

**conv module** — replace 4 `*_to_string` functions with 1 generic:

| Before | After |
|--------|-------|
| `int_to_string(n: int): string` | `to_string<T fulfills Showable>(val: T): string` |
| `int64_to_string(n: int64): string` | *(collapsed into `to_string`)* |
| `float_to_string(f: float): string` | *(collapsed into `to_string`)* |
| `bool_to_string(b: bool): string` | *(collapsed into `to_string`)* |

`string_to_int`, `string_to_int64`, `string_to_float` stay unchanged —
parsing is inherently type-specific (each target type has different rules
and error modes).

**Summary:**

| Module | Before | After | Removed |
|--------|:---:|:---:|:---:|
| math | 13 | 10 | 3 |
| sort | 5 | 3 | 2 |
| testing | 10 | 7 | 3 |
| conv | 7 | 4 | 3 |
| **Total** | **35** | **24** | **11** |

---

# EPIC 1: Core Interfaces in Compiler

Register the four core interfaces and built-in type fulfillments in the
type checker. This is the same pattern used for `Exception<T>` today.

## Story 1-1: Interface Registration

**SG-1-1-1** `[BLOCKER]`
Register the four core interfaces in `_register_builtin_interfaces` in
`compiler/typechecker.py`.

Extend the existing method (line 486) to register all four interfaces
after the `Exception` registration:

```python
def _register_builtin_interfaces(self) -> None:
    """Register built-in interfaces."""
    # Exception<T> (existing)
    self._interface_registry["Exception"] = InterfaceInfo(...)

    # Comparable
    self._interface_registry["Comparable"] = InterfaceInfo(
        name="Comparable",
        type_params=[],
        methods={
            "compare": TFn((TSelf(),), TInt(32, True), True),
        },
        constructor_name=None,
        constructor_sig=None,
    )

    # Numeric
    self._interface_registry["Numeric"] = InterfaceInfo(
        name="Numeric",
        type_params=[],
        methods={
            "negate": TFn((), TSelf(), True),
            "add": TFn((TSelf(),), TSelf(), True),
            "sub": TFn((TSelf(),), TSelf(), True),
            "mul": TFn((TSelf(),), TSelf(), True),
        },
        constructor_name=None,
        constructor_sig=None,
    )

    # Equatable
    self._interface_registry["Equatable"] = InterfaceInfo(
        name="Equatable",
        type_params=[],
        methods={
            "equals": TFn((TSelf(),), TBool(), True),
        },
        constructor_name=None,
        constructor_sig=None,
    )

    # Showable
    self._interface_registry["Showable"] = InterfaceInfo(
        name="Showable",
        type_params=[],
        methods={
            "to_string": TFn((), TString(), True),
        },
        constructor_name=None,
        constructor_sig=None,
    )
```

**SG-1-1-2**
Add `TSelf` type to the type system in `compiler/typechecker.py`.

`TSelf` represents the implementing type within an interface definition.
When checking fulfillment, `TSelf` is substituted with the concrete type.

```python
@dataclass
class TSelf(Type):
    """The implementing type in an interface method signature."""
    pass
```

Add to `_substitute_type` (or create if needed): when substituting types
in an interface method signature for a concrete type, replace `TSelf` with
the concrete type. This is the same substitution path used for `TTypeVar`
in generic interfaces.

## Story 1-2: Built-in Type Fulfillments

**SG-1-2-1** `[BLOCKER]`
Add a `_register_builtin_fulfillments` method to the type checker.

This method runs after `_register_types` and `_register_builtin_interfaces`,
and records which built-in types fulfill which interfaces. The data structure
is a mapping from type name to a list of fulfilled interface names:

```python
def _register_builtin_fulfillments(self) -> None:
    """Record which built-in types fulfill core interfaces."""
    self._builtin_fulfillments: dict[str, list[str]] = {
        "int":    ["Comparable", "Numeric", "Equatable", "Showable"],
        "int64":  ["Comparable", "Numeric", "Equatable", "Showable"],
        "float":  ["Comparable", "Numeric", "Equatable", "Showable"],
        "string": ["Comparable", "Equatable", "Showable"],
        "bool":   ["Equatable", "Showable"],
        "char":   ["Comparable", "Equatable", "Showable"],
        "byte":   ["Comparable", "Equatable", "Showable"],
    }
```

Wire this into the initialization sequence (line 385), after
`_register_builtin_interfaces()`.

**SG-1-2-2** `[BLOCKER]`
Update `_check_type_satisfies_bound` (from BG-2-2-2) to consult
`_builtin_fulfillments`.

Before checking methods on a type, first check if the type is a built-in
with a registered fulfillment for the bound interface. If so, the bound
is satisfied without method-by-method checking.

```python
def _check_type_satisfies_bound(self, concrete, bound_expr, node, tp_name):
    iface_name = ...  # resolve bound_expr to interface name
    type_name = self._type_name(concrete)  # e.g., "int", "float"

    # Fast path: built-in fulfillment
    if type_name in self._builtin_fulfillments:
        if iface_name in self._builtin_fulfillments[type_name]:
            return  # satisfied

    # Slow path: check methods (existing logic from BG-2-4-1)
    ...
```

**SG-1-2-3**
Add a `_builtin_method_sigs` registry mapping `(type_name, method_name)`
to `TFn` signatures.

This is needed by Epic 2 (body-level method resolution) so the type checker
knows the signatures of synthetic methods on built-in types:

```python
def _register_builtin_method_sigs(self) -> None:
    """Register method signatures for built-in types."""
    int_t = TInt(32, True)
    int64_t = TInt(64, True)
    float_t = TFloat(64)
    string_t = TString()
    bool_t = TBool()

    self._builtin_method_sigs: dict[tuple[str, str], TFn] = {
        # int
        ("int", "compare"): TFn((int_t,), int_t, True),
        ("int", "negate"): TFn((), int_t, True),
        ("int", "add"): TFn((int_t,), int_t, True),
        ("int", "sub"): TFn((int_t,), int_t, True),
        ("int", "mul"): TFn((int_t,), int_t, True),
        ("int", "equals"): TFn((int_t,), bool_t, True),
        ("int", "to_string"): TFn((), string_t, True),
        # int64
        ("int64", "compare"): TFn((int64_t,), int_t, True),
        ("int64", "negate"): TFn((), int64_t, True),
        ("int64", "add"): TFn((int64_t,), int64_t, True),
        ("int64", "sub"): TFn((int64_t,), int64_t, True),
        ("int64", "mul"): TFn((int64_t,), int64_t, True),
        ("int64", "equals"): TFn((int64_t,), bool_t, True),
        ("int64", "to_string"): TFn((), string_t, True),
        # float
        ("float", "compare"): TFn((float_t,), int_t, True),
        ("float", "negate"): TFn((), float_t, True),
        ("float", "add"): TFn((float_t,), float_t, True),
        ("float", "sub"): TFn((float_t,), float_t, True),
        ("float", "mul"): TFn((float_t,), float_t, True),
        ("float", "equals"): TFn((float_t,), bool_t, True),
        ("float", "to_string"): TFn((), string_t, True),
        # string
        ("string", "compare"): TFn((string_t,), int_t, True),
        ("string", "equals"): TFn((string_t,), bool_t, True),
        ("string", "to_string"): TFn((), string_t, True),
        # bool
        ("bool", "equals"): TFn((bool_t,), bool_t, True),
        ("bool", "to_string"): TFn((), string_t, True),
    }
```

## Story 1-3: Tests

**SG-1-3-1**
Add typechecker tests for built-in interface registration.

New `TestBuiltinInterfaces` class in `tests/unit/test_typechecker.py`:

| Test | Assertion |
|------|-----------|
| `test_comparable_registered` | `"Comparable"` in interface registry, has `compare` method |
| `test_numeric_registered` | `"Numeric"` in interface registry, has 4 methods |
| `test_equatable_registered` | `"Equatable"` in interface registry, has `equals` method |
| `test_showable_registered` | `"Showable"` in interface registry, has `to_string` method |

**SG-1-3-2**
Add typechecker tests for built-in fulfillments.

| Test | Assertion |
|------|-----------|
| `test_int_fulfills_comparable` | Bound check passes for `int` with `Comparable` |
| `test_int_fulfills_numeric` | Bound check passes for `int` with `Numeric` |
| `test_string_fulfills_equatable` | Bound check passes for `string` with `Equatable` |
| `test_bool_not_comparable` | Bound check fails for `bool` with `Comparable` |
| `test_string_not_numeric` | Bound check fails for `string` with `Numeric` |

---

# EPIC 2: Body-Level Method Resolution

This is the deferred feature from the bounded generics plan. Inside a bounded
generic function body, the type checker must resolve method calls on type
variables by consulting the bounds' interface definitions.

## Story 2-1: Type Checker — Method Resolution on TTypeVar

**SG-2-1-1** `[BLOCKER]`
Add `_resolve_method_on_typevar` to the type checker.

When the type checker encounters a `MethodCall` where the receiver type is
`TTypeVar`, it currently fails with "no method on type variable." Instead,
it should:

1. Look up which `TypeParam` owns the type variable (by name).
2. Resolve each bound to an interface via `_interface_registry`.
3. Search all bound interfaces for the method name.
4. If found, return the method's `TFn` signature with `TSelf` replaced
   by the `TTypeVar`.

```python
def _resolve_method_on_typevar(
    self,
    tv: TTypeVar,
    method_name: str,
    node: ASTNode,
) -> TFn | None:
    """Resolve a method call on a type variable using its bounds."""
    # Find the TypeParam for this type variable
    tp = self._find_type_param(tv.name)
    if tp is None or not tp.bounds:
        return None

    for bound_expr in tp.bounds:
        iface_name = self._resolve_interface_name(bound_expr)
        iface = self._interface_registry.get(iface_name)
        if iface is None:
            continue
        if method_name in iface.methods:
            sig = iface.methods[method_name]
            # Replace TSelf with the type variable
            return self._substitute_self(sig, tv)

    return None
```

**SG-2-1-2**
Wire `_resolve_method_on_typevar` into the `MethodCall` handler.

In `_infer_expr_inner`, the `MethodCall` case (around line 1001) currently
handles: namespace functions, type methods, and interface methods. Add a
new branch before the "no method" error:

```python
case MethodCall():
    receiver_type = self._infer_expr(node.receiver)
    ...
    # Existing branches: namespace, type methods, etc.

    # NEW: method on type variable via bounds
    if isinstance(receiver_type, TTypeVar):
        sig = self._resolve_method_on_typevar(
            receiver_type, node.method, node)
        if sig is not None:
            # Type-check arguments against sig
            self._check_call_args(sig, arg_types, node)
            return sig.return_type
```

**SG-2-1-3**
Add `_find_type_param` helper to locate the `TypeParam` for a type variable.

The type checker needs to walk up the scope to find the enclosing function
or type declaration that introduced the type parameter:

```python
def _find_type_param(self, name: str) -> TypeParam | None:
    """Find the TypeParam that introduced a type variable by name."""
    if self._current_fn_decl is not None:
        for tp in self._current_fn_decl.type_params:
            if tp.name == name:
                return tp
    # Also check enclosing type declaration if inside a method
    if self._current_type_decl is not None:
        for tp in self._current_type_decl.type_params:
            if tp.name == name:
                return tp
    return None
```

**SG-2-1-4**
Add `_substitute_self` helper that replaces `TSelf` with a concrete type
or type variable in a `TFn` signature.

```python
def _substitute_self(self, sig: TFn, replacement: Type) -> TFn:
    """Replace TSelf with a concrete type in a method signature."""
    new_params = tuple(
        replacement if isinstance(p, TSelf) else p for p in sig.params
    )
    new_ret = replacement if isinstance(sig.return_type, TSelf) else sig.return_type
    return TFn(new_params, new_ret, sig.is_pure)
```

This is intentionally shallow — `TSelf` only appears at the top level of
interface method signatures (not nested inside `TArray`, `TOption`, etc.)
for the four core interfaces. A recursive version can be added later if
needed.

## Story 2-2: Tests

**SG-2-2-1**
Add positive tests for body-level method resolution.

New `TestBodyLevelResolution` class in `tests/unit/test_typechecker.py`:

| Test | Program | Assertion |
|------|---------|-----------|
| `test_compare_in_bounded_body` | `fn f<T fulfills Comparable>(a: T, b: T): int { return a.compare(b) }` | Typechecks without error, return type is `int` |
| `test_negate_in_bounded_body` | `fn f<T fulfills Numeric>(a: T): T { return a.negate() }` | Typechecks, return type matches `T` |
| `test_equals_in_bounded_body` | `fn f<T fulfills Equatable>(a: T, b: T): bool { return a.equals(b) }` | Typechecks, return type is `bool` |
| `test_to_string_in_bounded_body` | `fn f<T fulfills Showable>(a: T): string { return a.to_string() }` | Typechecks, return type is `string` |
| `test_multi_bound_methods` | `fn f<T fulfills (Numeric, Comparable)>(a: T, b: T): T { ... }` | Can call both `compare` and `negate` on `T` |

**SG-2-2-2**
Add negative tests for body-level method resolution.

| Test | Program | Expected Error |
|------|---------|----------------|
| `test_unbounded_method_call` | `fn f<T>(a: T): int { return a.compare(a) }` | TypeError: no method `compare` |
| `test_wrong_bound_method` | `fn f<T fulfills Equatable>(a: T): T { return a.negate() }` | TypeError: no method `negate` (Equatable has no `negate`) |
| `test_method_wrong_arg_type` | `fn f<T fulfills Comparable>(a: T): int { return a.compare(42) }` | TypeError: argument type mismatch (expected `T`, got `int`) |

---

# EPIC 3: Monomorphization

When the lowering encounters a call to a bounded generic function whose body
calls interface methods on type variables, it generates a specialized copy
of the function for each concrete type combination used at call sites.

This epic is the most complex part of the plan. It spans six stories:
mangling, deep type substitution, site collection, function re-lowering,
synthetic built-in method lowering, and tests.

## Story 3-1: Mangler

**SG-3-1-1** `[BLOCKER]`
Add `mangle_monomorphized` to `compiler/mangler.py`.

```python
def mangle_monomorphized(module: str, fn_name: str,
                         type_args: list[str]) -> str:
    """Mangle a monomorphized function name.

    Example: math, min, ["int"] → rf_math_min__int
    Example: math, min, ["float"] → rf_math_min__float
    Example: testing, assert_eq, ["int"] → rf_testing_assert_eq__int

    The double underscore separates the function name from the type
    specialization suffix.
    """
    parts = module.replace(".", "_")
    suffix = "_".join(type_args)
    return f"{_PREFIX}{parts}_{fn_name}__{suffix}"
```

## Story 3-2: Deep Type Substitution

Monomorphization requires replacing `TTypeVar` with concrete types throughout
the entire type tree — not just at the top level. This is distinct from the
type checker's shallow `_substitute_self` (which only handles `TSelf` at the
top level of interface signatures).

**SG-3-2-1** `[BLOCKER]`
Add `_deep_substitute` utility to `compiler/lowering.py`.

```python
def _deep_substitute(self, ty: Type, env: dict[str, Type]) -> Type:
    """Recursively replace TTypeVar with concrete types."""
    match ty:
        case TTypeVar(name) if name in env:
            return env[name]
        case TArray(elem):
            return TArray(self._deep_substitute(elem, env))
        case TStream(elem):
            return TStream(self._deep_substitute(elem, env))
        case TBuffer(elem):
            return TBuffer(self._deep_substitute(elem, env))
        case TOption(inner):
            return TOption(self._deep_substitute(inner, env))
        case TResult(ok, err):
            return TResult(
                self._deep_substitute(ok, env),
                self._deep_substitute(err, env),
            )
        case TMap(key, val):
            return TMap(
                self._deep_substitute(key, env),
                self._deep_substitute(val, env),
            )
        case TSet(elem):
            return TSet(self._deep_substitute(elem, env))
        case TTuple(elems):
            return TTuple(tuple(
                self._deep_substitute(e, env) for e in elems
            ))
        case TFn(params, ret, is_pure):
            return TFn(
                tuple(self._deep_substitute(p, env) for p in params),
                self._deep_substitute(ret, env),
                is_pure,
            )
        case TNamed(name, args):
            return TNamed(name, [
                self._deep_substitute(a, env) for a in args
            ])
        case _:
            return ty  # TInt, TFloat, TString, TBool, etc. — leaf types
```

This handles every type constructor in the type system. If new type
constructors are added later, this function must be updated.

**SG-3-2-2**
Add `_build_substituted_type_map` helper that applies `_deep_substitute`
across all entries in `TypedModule.types` that belong to a given function's
AST subtree.

This produces a substituted type map that the re-lowering uses instead of
the original `TypedModule.types`. The original is never mutated.

```python
def _build_substituted_type_map(
    self,
    fn_decl: FnDecl,
    env: dict[str, Type],
) -> dict[ASTNode, Type]:
    """Create a copy of the type map with TTypeVar replaced by concrete types."""
    substituted = {}
    for node, ty in self._typed.types.items():
        substituted[node] = self._deep_substitute(ty, env)
    return substituted
```

Note: this substitutes all entries, not just those belonging to `fn_decl`.
That's correct — the lowering only reads entries for nodes it's currently
processing, and the extra substitutions are harmless.

## Story 3-3: Monomorphization Site Collection

**SG-3-3-1** `[BLOCKER]`
Add a pre-pass in `compiler/lowering.py` that collects monomorphization
sites.

Before lowering function bodies, scan all `Call` and `MethodCall` nodes
in the `TypedModule`. For each call to a bounded generic function, determine
the concrete type arguments at each call site. Build a map:

```python
@dataclass
class MonoSite:
    fn_decl: FnDecl
    type_env: dict[str, Type]  # e.g., {"T": TInt(32, True)}
    mangled_name: str          # e.g., "rf_math_min__int"

# key: (module, fn_name, tuple(concrete_type_names))
# value: MonoSite
self._mono_sites: dict[tuple[str, str, tuple[str, ...]], MonoSite] = {}
```

To infer the concrete type arguments, the pre-pass uses the same logic
as `_infer_type_env_from_call` (from the BG typechecker work) — matching
argument types from `TypedModule.types` against the function's declared
parameter types to extract the type variable bindings. Since the
typechecker has already validated the bounds, the lowering only needs the
type environment inference, not the bounds validation.

Implementation note: the lowering may re-implement the type env inference
locally rather than importing from `typechecker.py`, since no pass should
call into another pass. The logic is simple: walk the declared parameter
types, match `TTypeVar` positions against the concrete argument types.

**SG-3-3-2**
Handle the case where the same generic function is called with different
concrete types in the same module.

For example, if a program calls both `math.min(3, 7)` and
`math.min(1.5, 0.5)`, the pre-pass must collect two `MonoSite` entries:

- `("math", "min", ("int",))` → `rf_math_min__int`
- `("math", "min", ("float",))` → `rf_math_min__float`

Both specialized functions are emitted as separate `LFunction` nodes.
Duplicate call sites with the same concrete types are deduplicated by the
map key — only one specialization is generated per unique type combination.

## Story 3-4: Function Re-Lowering

This is the core of monomorphization. For each unique `MonoSite`, it lowers
the generic function body with concrete types substituted throughout.

**SG-3-4-1** `[BLOCKER]`
Add `_lower_monomorphized_fn` to `compiler/lowering.py`.

```python
def _lower_monomorphized_fn(self, site: MonoSite) -> LFunction:
    """Lower a generic function body with concrete type substitutions."""
    fn_decl = site.fn_decl
    env = site.type_env

    # 1. Build substituted type map
    sub_types = self._build_substituted_type_map(fn_decl, env)

    # 2. Save and swap the type map
    original_types = self._typed.types
    self._typed.types = sub_types

    # 3. Lower parameters with concrete types
    params = []
    for p in fn_decl.params:
        concrete_type = sub_types.get(p, original_types.get(p))
        params.append(LParam(p.name, self._type_to_c(concrete_type)))

    # 4. Lower the body — method calls on now-concrete types
    #    resolve through standard method resolution + synthetic
    #    built-in method lowering (Story 3-5)
    body = self._lower_block(fn_decl.body)

    # 5. Restore original type map
    self._typed.types = original_types

    # 6. Determine return type
    ret_type = self._deep_substitute(
        original_types.get(fn_decl, TVoid()), env
    )

    return LFunction(
        name=site.mangled_name,
        params=params,
        return_type=self._type_to_c(ret_type),
        body=body,
    )
```

The key insight: after type substitution, method calls like `a.compare(b)`
where `a: T` become `a.compare(b)` where `a: int`. The existing lowering
for method calls on concrete built-in types (Story 3-5) handles these
without any special monomorphization logic in the method call handler.

**Closures inside monomorphized bodies** do not need separate
monomorphization. Since the type substitution replaces all `TTypeVar`
references before lowering, closure parameter types are already concrete.
For example, in `sort`'s body:
```
sort_by(arr, fn(a: T, b: T): int { a.compare(b) })
```
After substitution with `T → int`:
```
sort_by(arr, fn(a: int, b: int): int { a.compare(b) })
```
The closure is lowered normally. `a.compare(b)` on `int` resolves through
the synthetic built-in method path. No separate closure monomorphization
pass is needed.

**SG-3-4-2** `[BLOCKER]`
Rewrite call sites to use the monomorphized function name.

When lowering a `Call` to a bounded generic function, look up the call's
concrete type arguments in `_mono_sites` and emit `LCall` with the
monomorphized mangled name:

```python
# Instead of: LCall("rf_math_min", [a, b])
# Emit:       LCall("rf_math_min__int", [a, b])
```

The lookup key is `(module, fn_name, tuple(type_names))`, derived from
the call-site argument types via the same type inference used in the
pre-pass.

**SG-3-4-3**
Skip emitting the generic (unspecialized) version of a monomorphized
function.

When a bounded generic function has been monomorphized, do not emit an
`LFunction` for the generic version — it would contain unresolved
`TTypeVar` references that can't be lowered to C. Only the specialized
versions are emitted. The lowering maintains a set of "monomorphized
function names" and skips them during the normal function lowering pass.

## Story 3-5: Synthetic Built-in Method Lowering

**SG-3-5-1** `[BLOCKER]`
Lower interface method calls on built-in types to C operations.

When the lowering encounters a method call on a concrete built-in type that
corresponds to a synthetic interface method, emit the appropriate C
operation. **Integer arithmetic uses checked operations** per the spec's
overflow-checking requirement. Float arithmetic uses plain C operators.

The dispatch table maps `(type_name, method_name)` to a lowering strategy:

```python
@dataclass
class BuiltinMethodOp:
    kind: str    # "checked_binop", "binop", "unary", "call", "compare"
    op: str      # C operator, macro name, or function name

BUILTIN_METHOD_OPS: dict[tuple[str, str], BuiltinMethodOp] = {
    # --- Comparable.compare ---
    # Numeric types: inline ternary  (a < b ? -1 : (a > b ? 1 : 0))
    ("int", "compare"):     BuiltinMethodOp("compare", "<"),
    ("int64", "compare"):   BuiltinMethodOp("compare", "<"),
    ("float", "compare"):   BuiltinMethodOp("compare", "<"),
    ("char", "compare"):    BuiltinMethodOp("compare", "<"),
    ("byte", "compare"):    BuiltinMethodOp("compare", "<"),
    # String: runtime function
    ("string", "compare"):  BuiltinMethodOp("call", "rf_string_cmp"),

    # --- Numeric.add --- CHECKED for integers, plain for float
    ("int", "add"):         BuiltinMethodOp("checked_binop", "RF_CHECKED_ADD"),
    ("int64", "add"):       BuiltinMethodOp("checked_binop", "RF_CHECKED_ADD"),
    ("float", "add"):       BuiltinMethodOp("binop", "+"),

    # --- Numeric.sub --- CHECKED for integers, plain for float
    ("int", "sub"):         BuiltinMethodOp("checked_binop", "RF_CHECKED_SUB"),
    ("int64", "sub"):       BuiltinMethodOp("checked_binop", "RF_CHECKED_SUB"),
    ("float", "sub"):       BuiltinMethodOp("binop", "-"),

    # --- Numeric.mul --- CHECKED for integers, plain for float
    ("int", "mul"):         BuiltinMethodOp("checked_binop", "RF_CHECKED_MUL"),
    ("int64", "mul"):       BuiltinMethodOp("checked_binop", "RF_CHECKED_MUL"),
    ("float", "mul"):       BuiltinMethodOp("binop", "*"),

    # --- Numeric.negate ---
    ("int", "negate"):      BuiltinMethodOp("unary", "-"),
    ("int64", "negate"):    BuiltinMethodOp("unary", "-"),
    ("float", "negate"):    BuiltinMethodOp("unary", "-"),

    # --- Equatable.equals ---
    ("int", "equals"):      BuiltinMethodOp("binop", "=="),
    ("int64", "equals"):    BuiltinMethodOp("binop", "=="),
    ("float", "equals"):    BuiltinMethodOp("binop", "=="),
    ("bool", "equals"):     BuiltinMethodOp("binop", "=="),
    ("char", "equals"):     BuiltinMethodOp("binop", "=="),
    ("byte", "equals"):     BuiltinMethodOp("binop", "=="),
    ("string", "equals"):   BuiltinMethodOp("call", "rf_string_eq"),

    # --- Showable.to_string ---
    ("int", "to_string"):     BuiltinMethodOp("call", "rf_int_to_string"),
    ("int64", "to_string"):   BuiltinMethodOp("call", "rf_int64_to_string"),
    ("float", "to_string"):   BuiltinMethodOp("call", "rf_float_to_string"),
    ("bool", "to_string"):    BuiltinMethodOp("call", "rf_bool_to_string"),
    ("string", "to_string"):  BuiltinMethodOp("call", "_rf_identity_string"),
    ("char", "to_string"):    BuiltinMethodOp("call", "rf_char_to_string"),
    ("byte", "to_string"):    BuiltinMethodOp("call", "rf_byte_to_string"),
}
```

Lowering logic by `kind`:

- `"checked_binop"`: emit the `RF_CHECKED_*` macro pattern — declare a
  temp variable, call the macro, use the temp. This is the same pattern
  already used for regular `+`/`-`/`*` on integers throughout the lowering.
  Example: `a.add(b)` on `int` → `RF_CHECKED_ADD(a, b, &_rf_tmp_1)`.
- `"binop"`: emit `((a) op (b))` directly. Used for float arithmetic and
  all equality comparisons.
- `"unary"`: emit `(-(a))`. Used for `negate` on all numeric types.
- `"compare"`: emit `((a) < (b) ? -1 : ((a) > (b) ? 1 : 0))`.
- `"call"`: emit `LCall(fn_name, [args])`.

**SG-3-5-2**
Add `_rf_compare` macro and `_rf_identity_string` to the runtime.

```c
/* Comparable.compare for numeric/char/byte types */
#define _rf_compare(a, b) ((a) < (b) ? -1 : ((a) > (b) ? 1 : 0))

/* Showable.to_string for string (identity — retains and returns self) */
static inline RF_String* _rf_identity_string(RF_String* s) {
    rf_string_retain(s);
    return s;
}
```

; NOTE: The self-hosted compiler could optimize away _rf_identity_string
; by detecting that string.to_string() is identity and eliding the call.
; For the reference compiler, the extra retain/return is correct and the
; overhead is negligible.

No `_rf_add`/`_rf_sub`/`_rf_mul` macros are needed — integer arithmetic
goes through the existing `RF_CHECKED_ADD`/`SUB`/`MUL` macros, and float
arithmetic uses plain C operators emitted directly by the lowering.

**SG-3-5-3**
Add `rf_char_to_string` and `rf_byte_to_string` to the runtime if not
already present. These are needed for the `Showable` fulfillment on `char`
and `byte`.

## Story 3-6: Tests

**SG-3-6-1**
Add a golden file test for a monomorphized function.

`tests/programs/mono_min.reflow`:
```
module mono_min

pure fn min<T fulfills Comparable>(a: T, b: T): T {
    return if a.compare(b) <= 0 then a else b
}

fn main(): void {
    let x = min(3, 7)
    let y = min(1.5, 0.5)
    io.println(conv.to_string(x))
    io.println(conv.to_string(y))
}
```

`tests/expected_stdout/mono_min.txt`:
```
3
0.500000
```

Verify in the generated C (`tests/expected/mono_min.c`) that two
specialized functions exist: one operating on `rf_int` (using the
`_rf_compare` ternary), one on `rf_float`.

**SG-3-6-2**
Add a golden file test for monomorphized `assert_eq`.

`tests/programs/mono_assert.reflow`:
```
module mono_assert

fn assert_eq<T fulfills (Equatable, Showable)>(expected: T, actual: T, msg: string): void {
    if !expected.equals(actual) {
        io.eprintln(f"FAIL: {msg}: expected {expected.to_string()}, got {actual.to_string()}")
        sys.exit(1)
    }
}

fn main(): void {
    assert_eq(42, 42, "int equality")
    assert_eq("hello", "hello", "string equality")
    io.println("all passed")
}
```

`tests/expected_stdout/mono_assert.txt`:
```
all passed
```

**SG-3-6-3**
Add a golden file test that verifies checked arithmetic in monomorphized
code.

`tests/programs/mono_checked_add.reflow`:
```
module mono_checked_add

pure fn add_generic<T fulfills Numeric>(a: T, b: T): T {
    return a.add(b)
}

fn main(): void {
    let x = add_generic(3, 4)
    let y = add_generic(1.5, 2.5)
    io.println(conv.to_string(x))
    io.println(conv.to_string(y))
}
```

`tests/expected_stdout/mono_checked_add.txt`:
```
7
4.000000
```

Verify in the generated C that the `int` specialization uses
`RF_CHECKED_ADD` (not plain `+`), while the `float` specialization uses
plain `+`.

**SG-3-6-4**
Add a negative compile test: method call on unbounded type variable.

`tests/programs/errors/unbounded_method_call.reflow`:
```
module unbounded_method_call

fn bad<T>(a: T): int {
    return a.compare(a)
}

fn main(): void { }
```

`tests/expected_errors/unbounded_method_call.txt`:
```
TypeError
no method 'compare'
```

---

# EPIC 4: Stdlib Rewrite

With the compiler infrastructure in place, rewrite the affected stdlib
modules. Each module is an independent ticket — they can be done in any
order.

## Story 4-1: math Module

**SG-4-1-1** `[BLOCKER]`
Rewrite `stdlib/math.reflow` with generic functions.

**Before** (current file):
```
module math

export pure fn abs_int(n: int): int = native "rf_math_abs_int"
export pure fn abs_float(f: float): float = native "rf_math_abs_float"
export pure fn min_int(a: int, b: int): int = native "rf_math_min_int"
export pure fn max_int(a: int, b: int): int = native "rf_math_max_int"
export pure fn min_float(a: float, b: float): float = native "rf_math_min_float"
export pure fn max_float(a: float, b: float): float = native "rf_math_max_float"
export pure fn clamp_int(val: int, lo: int, hi: int): int = native "rf_math_clamp_int"
export pure fn floor(f: float): float = native "rf_math_floor"
export pure fn ceil(f: float): float = native "rf_math_ceil"
export pure fn round(f: float): float = native "rf_math_round"
export pure fn pow(base: float, exp: float): float = native "rf_math_pow"
export pure fn sqrt(f: float): float = native "rf_math_sqrt"
export pure fn log(f: float): float = native "rf_math_log"
```

**After:**
```
module math

export pure fn abs<T fulfills (Numeric, Comparable)>(n: T): T {
    let neg = n.negate()
    return if n.compare(neg) < 0 then neg else n
}

export pure fn min<T fulfills Comparable>(a: T, b: T): T {
    return if a.compare(b) <= 0 then a else b
}

export pure fn max<T fulfills Comparable>(a: T, b: T): T {
    return if a.compare(b) >= 0 then a else b
}

export pure fn clamp<T fulfills Comparable>(val: T, lo: T, hi: T): T {
    return max(min(val, hi), lo)
}

; Float-specific (inherently float operations)
export pure fn floor(f: float): float = native "rf_math_floor"
export pure fn ceil(f: float): float = native "rf_math_ceil"
export pure fn round(f: float): float = native "rf_math_round"
export pure fn pow(base: float, exp: float): float = native "rf_math_pow"
export pure fn sqrt(f: float): float = native "rf_math_sqrt"
export pure fn log(f: float): float = native "rf_math_log"
```

Note: `abs` uses `n.compare(n.negate())` instead of `n.compare(zero)`,
avoiding the need for a static `zero()` method. For `n = 3`:
`3.compare(-3) = 1 > 0 → return 3`. For `n = -3`:
`(-3).compare(3) = -1 < 0 → return 3`. Correct.

; NOTE: abs(INT_MIN) overflows on negate because -(-2147483648) has no
; int32 representation. The existing rf_math_abs_int has the same UB via
; C's abs(). This is a known edge case — not introduced by this change.
; The self-hosted compiler could add a dedicated INT_MIN check if desired.

**SG-4-1-2**
Remove the now-unused C runtime functions from `runtime/reflow_runtime.c`
and `runtime/reflow_runtime.h`:

- `rf_math_abs_int`
- `rf_math_abs_float`
- `rf_math_min_int`
- `rf_math_max_int`
- `rf_math_min_float`
- `rf_math_max_float`
- `rf_math_clamp_int`

Also remove their declarations from `runtime/reflow_runtime.h`.

The monomorphized versions are generated by the compiler from the ReFlow
bodies and use the `_rf_compare` / `_rf_negate` macros directly.

**SG-4-1-3**
Update all call sites in test programs and examples.

Search for `math.abs_int`, `math.min_int`, etc., across all `.reflow` files
and update to `math.abs`, `math.min`, etc. The call site syntax changes but
the behavior is identical — the compiler monomorphizes to the same operations.

## Story 4-2: sort Module

**SG-4-2-1**
Rewrite `stdlib/sort.reflow` with a generic `sort` function.

**Before:**
```
module sort

export pure fn sort_ints(arr: array<int>): array<int> = native "rf_sort_ints"
export pure fn sort_strings(arr: array<string>): array<string> = native "rf_sort_strings"
export pure fn sort_floats(arr: array<float>): array<float> = native "rf_sort_floats"
export pure fn reverse(arr: array<int>): array<int> = native "rf_array_reverse"
```

**After:**
```
module sort

export pure fn sort<T fulfills Comparable>(arr: array<T>): array<T> {
    return sort_by(arr, fn(a: T, b: T): int { a.compare(b) })
}

export pure fn sort_by<T>(arr: array<T>, cmp: fn(T, T): int): array<T> = native "rf_sort_array_by"
export pure fn reverse<T>(arr: array<T>): array<T> = native "rf_array_reverse"
```

Note: `sort_by` and `reverse` remain `native` because they are type-erased
operations (they operate on `void*` elements and don't need to know the
element type). Only `sort` needs monomorphization because its body calls
`a.compare(b)`.

The lambda `fn(a: T, b: T): int { a.compare(b) }` inside `sort` does not
need separate monomorphization. When `sort` is monomorphized to `sort__int`,
the type substitution replaces `T → int` throughout the body *before*
lowering, so the lambda becomes `fn(a: int, b: int): int { a.compare(b) }`
with concrete types. The regular lambda lowering handles it, and
`a.compare(b)` on `int` resolves through the synthetic built-in method
path (SG-3-5-1). See SG-3-4-1 for the full explanation.

**SG-4-2-2**
Remove the now-unused C runtime functions from both
`runtime/reflow_runtime.c` and `runtime/reflow_runtime.h`:

- `rf_sort_ints`
- `rf_sort_strings`
- `rf_sort_floats`

Ensure `rf_sort_array_by` and `rf_array_reverse` remain (they are the
generic implementations that take a comparator closure or operate on
raw element data).

**SG-4-2-3**
Update all call sites: `sort.sort_ints(arr)` → `sort.sort(arr)`, etc.

## Story 4-3: testing Module

**SG-4-3-1**
Rewrite `stdlib/testing.reflow` with a generic `assert_eq`.

**Before:**
```
module testing

export fn assert_true(val: bool, msg: string): void = native "rf_test_assert_true"
export fn assert_false(val: bool, msg: string): void = native "rf_test_assert_false"
export fn assert_eq_int(expected: int, actual: int, msg: string): void = native "rf_test_assert_eq_int"
export fn assert_eq_int64(expected: int64, actual: int64, msg: string): void = native "rf_test_assert_eq_int64"
export fn assert_eq_string(expected: string, actual: string, msg: string): void = native "rf_test_assert_eq_string"
export fn assert_eq_bool(expected: bool, actual: bool, msg: string): void = native "rf_test_assert_eq_bool"
export fn fail(msg: string): void = native "rf_test_fail"
```

**After:**
```
module testing

export fn assert_true(val: bool, msg: string): void = native "rf_test_assert_true"
export fn assert_false(val: bool, msg: string): void = native "rf_test_assert_false"

export fn assert_eq<T fulfills (Equatable, Showable)>(expected: T, actual: T, msg: string): void {
    if !expected.equals(actual) {
        let detail = f"expected {expected.to_string()}, got {actual.to_string()}"
        fail(f"{msg}: {detail}")
    }
}

export fn assert_approx(expected: float, actual: float, epsilon: float, msg: string): void {
    let diff = math.abs(expected.sub(actual))
    if diff.compare(epsilon) > 0 {
        fail(f"{msg}: expected {conv.to_string(expected)} ± {conv.to_string(epsilon)}, got {conv.to_string(actual)}")
    }
}

export fn fail(msg: string): void = native "rf_test_fail"
```

**SG-4-3-2**
Remove the now-unused C runtime functions from both
`runtime/reflow_runtime.c` and `runtime/reflow_runtime.h`:

- `rf_test_assert_eq_int`
- `rf_test_assert_eq_int64`
- `rf_test_assert_eq_string`
- `rf_test_assert_eq_bool`

Keep `rf_test_assert_true`, `rf_test_assert_false`, and `rf_test_fail`.

**SG-4-3-3**
Update all call sites: `testing.assert_eq_int(a, b, msg)` →
`testing.assert_eq(a, b, msg)`, etc.

## Story 4-4: conv Module

**SG-4-4-1**
Rewrite `stdlib/conv.reflow` with a generic `to_string`.

**Before:**
```
module conv

export pure fn int_to_string(n: int): string = native "rf_int_to_string"
export pure fn int64_to_string(n: int64): string = native "rf_int64_to_string"
export pure fn float_to_string(f: float): string = native "rf_float_to_string"
export pure fn bool_to_string(b: bool): string = native "rf_bool_to_string"

export pure fn string_to_int(s: string): int? = native "rf_string_to_int_opt"
export pure fn string_to_int64(s: string): int64? = native "rf_string_to_int64_opt"
export pure fn string_to_float(s: string): float? = native "rf_string_to_float_opt"
```

**After:**
```
module conv

export pure fn to_string<T fulfills Showable>(val: T): string {
    return val.to_string()
}

; Parsing remains type-specific (different rules per type)
export pure fn string_to_int(s: string): int? = native "rf_string_to_int_opt"
export pure fn string_to_int64(s: string): int64? = native "rf_string_to_int64_opt"
export pure fn string_to_float(s: string): float? = native "rf_string_to_float_opt"
```

The `to_string` generic function is trivial — it just delegates to the
interface method. Its value is providing a uniform calling convention:
`conv.to_string(val)` instead of knowing which `*_to_string` to call.

; NOTE: The monomorphized version of to_string<int> generates a function
; whose body immediately calls rf_int_to_string — one extra indirection.
; The self-hosted compiler could inline this trivial wrapper. For the
; reference compiler, the indirection is correct and the overhead is
; negligible (one function call, no allocation).

Note: the underlying C functions (`rf_int_to_string`, etc.) remain in the
runtime — they are called by the `Showable.to_string` synthetic method
lowering (SG-3-3-1). They are no longer directly referenced from ReFlow
source, but the compiler still emits calls to them in monomorphized code.

**SG-4-4-2**
Update all call sites across test programs and examples.

The f-string interpolation (`f"value: {x}"`) already uses the compiler's
internal `to_string` dispatch and is unaffected. Only explicit calls like
`conv.int_to_string(n)` need updating to `conv.to_string(n)`.

## Story 4-5: Update stream Module

**SG-4-5-1**
In `stdlib_spec.md`, replace `sum_int` with a note that `sum` requires
a `Numeric` bound and an explicit initial value:

```
fn sum<T fulfills Numeric>(src: stream<T>, zero: T): T {
    return reduce(src, zero, fn(acc: T, val: T): T { acc.add(val) })
}
```

This is deferred from implementation until the stream stdlib module
(`stdlib/stream.reflow`) is created. Document the planned signature in
the spec only.

---

# EPIC 5: Validation and Cleanup

## Story 5-1: Full Test Suite

**SG-5-1-1** `[BLOCKER]`
Run `make test` and verify all tests pass with zero failures.

Verify:
- All existing tests still pass (no regressions from interface changes)
- All new monomorphization golden file tests pass
- All new negative compile tests pass
- All updated call sites in test programs work correctly

**SG-5-1-2**
Add end-to-end integration tests that exercise the full rewritten stdlib.

`tests/programs/stdlib_generic_math.reflow`:
```
module stdlib_generic_math

fn main(): void {
    ; Generic math functions work with both int and float
    io.println(conv.to_string(math.abs(-5)))
    io.println(conv.to_string(math.abs(-3.14)))
    io.println(conv.to_string(math.min(10, 3)))
    io.println(conv.to_string(math.max(1.0, 2.0)))
    io.println(conv.to_string(math.clamp(15, 0, 10)))
}
```

`tests/expected_stdout/stdlib_generic_math.txt`:
```
5
3.140000
3
2.000000
10
```

`tests/programs/stdlib_generic_sort.reflow`:
```
module stdlib_generic_sort

fn main(): void {
    let ints = sort.sort([3, 1, 4, 1, 5])
    let strs = sort.sort(["banana", "apple", "cherry"])
    ; ... print results
}
```

## Story 5-2: Cleanup

**SG-5-2-1**
Verify all dead C runtime functions were removed during Epic 4.

Each per-module ticket in Epic 4 (SG-4-1-2, SG-4-2-2, SG-4-3-2) owns
removing its module's dead functions at rewrite time. This ticket is a
final verification pass — grep the runtime for the full list of functions
that should no longer exist and confirm they are gone:

- `rf_math_abs_int`, `rf_math_abs_float`
- `rf_math_min_int`, `rf_math_max_int`, `rf_math_min_float`, `rf_math_max_float`
- `rf_math_clamp_int`
- `rf_sort_ints`, `rf_sort_strings`, `rf_sort_floats`
- `rf_test_assert_eq_int`, `rf_test_assert_eq_int64`,
  `rf_test_assert_eq_string`, `rf_test_assert_eq_bool`

If any remain (e.g., a ticket was missed), remove them here.

Confirm that all underlying utility functions the monomorphized code calls
are still present: `rf_int_to_string`, `rf_string_cmp`, `rf_string_eq`,
`rf_float_to_string`, `rf_bool_to_string`, `rf_int64_to_string`, etc.

**SG-5-2-2**
Verify the bootstrap constraint: every construct used in the rewritten
stdlib has a ReFlow-language equivalent. The monomorphization strategy
must be replicable in the self-hosted compiler (Epic 11). Document the
monomorphization algorithm in a comment at the top of the lowering
monomorphization code.

---

# Files Modified

| File | Change |
|------|--------|
| `reflow_spec.md` | Add 4 core interface definitions, built-in fulfillment table, `self`-as-type-annotation semantics |
| `stdlib_spec.md` | Replace type-specific function signatures with generic equivalents |
| `compiler/typechecker.py` | Add `TSelf` type; register 4 interfaces and built-in fulfillments; add `_resolve_method_on_typevar`, `_find_type_param`, `_substitute_self`; wire body-level resolution into `MethodCall` handler |
| `compiler/mangler.py` | Add `mangle_monomorphized` |
| `compiler/lowering.py` | Add `_deep_substitute`, `_build_substituted_type_map`, monomorphization pre-pass (`_mono_sites`), `_lower_monomorphized_fn`, call-site rewriting, synthetic built-in method lowering (`BUILTIN_METHOD_OPS`) |
| `runtime/reflow_runtime.h` | Add `_rf_compare` macro, `_rf_identity_string` inline, `rf_char_to_string`/`rf_byte_to_string` if missing; remove 14 dead function declarations |
| `runtime/reflow_runtime.c` | Add `rf_char_to_string`/`rf_byte_to_string` if missing; remove 14 dead function implementations |
| `stdlib/math.reflow` | Rewrite: 13 functions → 10 (4 generic + 6 float-specific) |
| `stdlib/sort.reflow` | Rewrite: 4 functions → 3 (1 generic + 2 native generic) |
| `stdlib/testing.reflow` | Rewrite: 7 functions → 5 (1 generic + 1 float-specific + 3 native) |
| `stdlib/conv.reflow` | Rewrite: 7 functions → 4 (1 generic + 3 native parse) |
| `tests/unit/test_typechecker.py` | Add ~18 new tests (interface registration, fulfillments, body-level resolution) |
| `tests/programs/` | Add 4+ new test programs (mono_min, mono_assert, mono_checked_add, stdlib_generic_*); update all existing programs that call renamed functions |
| `tests/expected_stdout/` | Add expected output for new test programs |
| `tests/programs/errors/` | Add 1+ negative compile test |
| `tests/expected_errors/` | Add expected error files |

# Files NOT Modified

| File | Reason |
|------|--------|
| `compiler/lexer.py` | No new tokens needed |
| `compiler/parser.py` | Bounded generics syntax already supported (BG plan) |
| `compiler/ast_nodes.py` | `TypeParam` already exists (BG plan) |
| `compiler/resolver.py` | Does not reference `type_params` or method signatures |
| `compiler/emitter.py` | Monomorphized `LFunction` nodes look like regular functions to the emitter |
| `compiler/errors.py` | `TypeError` is already sufficient |

---

# Dependency Map

```
Bounded Generics Plan (BG-*)
  └─ must be FULLY COMPLETE before this plan starts

EPIC 0 (Specification)
  └─ must complete before EPIC 1

EPIC 1 (Core Interfaces in Compiler)
  └─ depends on EPIC 0
  └─ must complete before EPIC 2

EPIC 2 (Body-Level Method Resolution)
  └─ depends on EPIC 1
  └─ must complete before EPIC 3

EPIC 3 (Monomorphization)
  └─ depends on EPIC 2
  └─ must complete before EPIC 4

EPIC 4 (Stdlib Rewrite)
  └─ depends on EPIC 3
  └─ stories 4-1 through 4-5 are independent of each other

EPIC 5 (Validation and Cleanup)
  └─ depends on all of EPIC 4
  └─ final milestone
```

All epics are sequential. Within EPIC 4, the individual module rewrites
(stories 4-1 through 4-5) are independent and can be done in any order.

---

# Ticket Counts

| Epic | Stories | Tickets |
|------|---------|---------|
| 0: Specification | 2 | 3 |
| 1: Core Interfaces in Compiler | 3 | 7 |
| 2: Body-Level Method Resolution | 2 | 6 |
| 3: Monomorphization | 6 | 15 |
| 4: Stdlib Rewrite | 5 | 12 |
| 5: Validation and Cleanup | 2 | 4 |
| **Total** | **20** | **47** |

---

# Risk: `self` as Type Annotation

The core interfaces use `self` as a type annotation for non-receiver
parameters (e.g., `compare(self, other: self): int`). The spec currently
uses `self` only as a receiver and as a return type. Using it as a
parameter type is a natural extension but requires:

1. Parser support for `self` in type expression position
2. Type checker support for resolving `self` to the implementing type

If this proves too complex for the bootstrap, the fallback is to use the
Kotlin-style pattern with a self-referential type parameter:

```
interface Comparable<T> {
    pure fn compare(self, other: T): int
}
```

Where `int fulfills Comparable<int>`, `float fulfills Comparable<float>`,
etc. This works with existing generics infrastructure but requires each
fulfillment to repeat the type name.

---

# Verification

After all tickets are complete:

```bash
make test                                    # all tests pass, zero failures
pytest tests/unit/test_typechecker.py -v     # including new interface/resolution tests
pytest tests/unit/test_lowering.py -v        # including monomorphization tests
```

Verify manually:
- `math.min(3, 7)` compiles and returns `3` (int specialization)
- `math.min(1.5, 0.5)` compiles and returns `0.5` (float specialization)
- `sort.sort([3, 1, 2])` compiles and returns `[1, 2, 3]`
- `sort.sort(["b", "a"])` compiles and returns `["a", "b"]`
- `testing.assert_eq(42, 42, "ok")` compiles without error
- `testing.assert_eq("a", "b", "fail")` compiles and fails at runtime with message
- Generated C contains separate functions `rf_math_min__int` and `rf_math_min__float`
