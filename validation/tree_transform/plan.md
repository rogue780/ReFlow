# Validation: Tree Transform (Pattern Matching)

## Category
Language-Specific Features — Pattern Matching

## What It Validates
- Complex pattern matching on deeply nested sum types
- AST-like tree transformation (the core use case for `match`)
- Recursive pattern matching with multiple variants
- Exhaustiveness (compiler rejects incomplete matches)
- Nested match expressions
- Pattern matching as the primary dispatch mechanism
- Building new trees from pattern-matched components

## Why It Matters
Pattern matching on sum types is Flow's primary dispatch mechanism — it
replaces virtual dispatch, visitor patterns, and switch statements. This
validation builds a small expression language (AST), implements an
optimizer that transforms the tree using pattern matching, and an
evaluator that interprets it. This is exactly the pattern the self-hosted
compiler will use, making it a critical validation.

## File
`validation/tree_transform/tree_transform.flow`

## Structure

**Module:** `module validation.tree_transform`
**Imports:** `io`, `conv`

### Types

```flow
type Expr = Lit { value: int }
          | Var { name: string }
          | Add { left: Expr, right: Expr }
          | Mul { left: Expr, right: Expr }
          | Neg { operand: Expr }
          | IfZero { cond: Expr, then_br: Expr, else_br: Expr }
```

```flow
type Env = EmptyEnv | Binding { name: string, value: int, rest: Env }
```

### Functions

1. **`fn:pure eval(expr: Expr, env: Env): int`**
   - Match on all 6 variants
   - `Lit` -> value
   - `Var` -> look up in env
   - `Add` -> eval(left) + eval(right)
   - `Mul` -> eval(left) * eval(right)
   - `Neg` -> 0 - eval(operand)
   - `IfZero` -> if eval(cond) == 0, eval(then_br), else eval(else_br)

2. **`fn:pure env_lookup(env: Env, name: string): int`**
   - Match: `EmptyEnv` -> 0 (default), `Binding` -> if name matches return value, else recurse on rest

3. **`fn:pure simplify(expr: Expr): Expr`**
   - Constant folding optimizer:
   - `Add(Lit(0), x)` -> simplify(x)  (0 + x = x)
   - `Add(x, Lit(0))` -> simplify(x)  (x + 0 = x)
   - `Mul(Lit(0), x)` -> `Lit { value: 0 }`  (0 * x = 0)
   - `Mul(x, Lit(0))` -> `Lit { value: 0 }`
   - `Mul(Lit(1), x)` -> simplify(x)  (1 * x = x)
   - `Mul(x, Lit(1))` -> simplify(x)
   - `Neg(Neg(x))` -> simplify(x)  (double negation)
   - `Neg(Lit(0))` -> `Lit { value: 0 }`
   - `Add(Lit(a), Lit(b))` -> `Lit { value: a + b }`  (constant fold)
   - `Mul(Lit(a), Lit(b))` -> `Lit { value: a * b }`
   - Otherwise: recurse into children and rebuild

4. **`fn:pure expr_to_string(expr: Expr): string`**
   - Pretty-print: `"(+ 1 (* x 2))"`
   - Match on each variant, recursively format

5. **`fn:pure depth(expr: Expr): int`**
   - Tree depth measurement

6. **`fn main(): none`**
   - Build expression trees
   - Print original, simplified, and evaluated forms
   - Demonstrate each simplification rule

## Test Program
`tests/programs/val_tree_transform.flow`

Test cases:
- `eval(Lit(42), empty)` = 42
- `eval(Add(Lit(3), Lit(4)), empty)` = 7
- `eval(Var("x"), {x=5})` = 5
- `eval(IfZero(Lit(0), Lit(1), Lit(2)), empty)` = 1 (then branch)
- `eval(IfZero(Lit(1), Lit(1), Lit(2)), empty)` = 2 (else branch)
- `simplify(Add(Lit(0), Var("x")))` = `Var("x")`
- `simplify(Mul(Lit(0), Var("x")))` = `Lit(0)`
- `simplify(Neg(Neg(Var("x"))))` = `Var("x")`
- `simplify(Add(Lit(3), Lit(4)))` = `Lit(7)`
- `simplify(Mul(Add(Lit(1), Lit(2)), Lit(0)))` = `Lit(0)` (nested)
- `depth(Lit(1))` = 1
- `depth(Add(Lit(1), Add(Lit(2), Lit(3))))` = 3

## Expected Output (test)
```
eval lit: 42
eval add: 7
eval var: 5
eval ifzero true: 1
eval ifzero false: 2
simplify 0+x: x
simplify 0*x: 0
simplify --x: x
simplify 3+4: 7
simplify nested: 0
depth lit: 1
depth nested: 3
to_string: (+ 1 (* x 2))
done
```

## Estimated Size
~180 lines (app), ~90 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Sum type (6 variants) | `Expr` with recursive fields |
| Recursive sum type | `Env = EmptyEnv \| Binding` |
| `match` with destructuring | every function |
| Nested pattern matching | simplify rules |
| `fn:pure` | all tree operations |
| Deep recursion | eval, simplify, to_string |
| String concatenation | expr_to_string formatting |
| Recursive env lookup | `env_lookup` |

## Why This Is Critical
This is the exact pattern the self-hosted Flow compiler will use:
- `Expr` ≈ Flow's AST nodes
- `eval` ≈ the type checker / interpreter
- `simplify` ≈ optimization passes
- `expr_to_string` ≈ error message formatting

If this doesn't work cleanly, the self-hosted compiler can't be written.

## Known Risks
- Nested pattern matching in `simplify` (e.g., matching `Add(Lit(0), x)`)
  requires the compiler to support nested destructuring. If Flow only
  supports flat matches, the rules must be written as nested match
  expressions — more verbose but still functional.
- The `Env` type is a linked list of bindings. Same stack depth concerns
  as the linked list validation.
