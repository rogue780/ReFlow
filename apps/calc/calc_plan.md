# Plan: Expression Calculator

## Overview

A command-line expression evaluator. Parses arithmetic expressions into a
recursive sum-type AST, then evaluates them. Supports variables, parentheses,
and standard math operators. The primary goal is to showcase **sum types**,
**recursive match**, and **fn:pure** in a clean, self-contained app.

**File:** `apps/calc/calc.flow`

**Usage:**
```
python main.py run apps/calc/calc.flow
```

Interactive REPL:
```
> 2 + 3 * 4
14
> (2 + 3) * 4
20
> let x = 10
x = 10
> x * 2 + 1
21
> x ^ 2
100
> -5 + 3
-2
> quit
```

**Stdlib modules used:** `io`, `string`, `array`, `conv`, `map`, `math`

---

## Gap Discovery Policy

These apps exist to find holes in the language and stdlib. When implementation
hits a point where the natural approach doesn't work — a missing stdlib
function, a type system limitation, an awkward workaround — **stop and report
it** instead of working around it.

Specifically:
1. **Do not silently work around** a missing feature. If you want to write
   `string.char_at(s, i)` and it doesn't exist, that's a finding.
2. **Identify the gap** clearly: what you wanted to do, what's missing, and
   where in the pipeline (stdlib, parser, type system, runtime) the fix belongs.
3. **Propose solutions** — at least two options with tradeoffs. Prefer
   well-engineered fixes (new stdlib function, language feature) over hacks.
4. **Present to the user** before continuing. The user decides whether to
   fix the gap first or defer it.
5. **Document** each gap with a `; GAP: <description>` comment in the app
   source if deferred.

This policy applies to every ticket in this plan.

---

## Conventions

- Tickets are numbered `CALC-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Tokenizer

---

## Story 1-1: Token Types and Scanner

**CALC-1-1-1** `[BLOCKER]`
Define a sum type for tokens:
```
type Token =
    | Number(float)
    | Ident(string)
    | Plus
    | Minus
    | Star
    | Slash
    | Percent
    | Caret
    | LParen
    | RParen
    | Equals
    | Eof
```

**CALC-1-1-2** `[BLOCKER]`
Implement `fn:pure tokenize(input: string): array<Token>`:
- Walk the string character by character.
- Skip whitespace.
- Numbers: scan digits and optional `.` for floats.
- Identifiers: scan `[a-zA-Z_][a-zA-Z0-9_]*`.
- Single-char operators: `+`, `-`, `*`, `/`, `%`, `^`, `(`, `)`, `=`.
- Append `Eof` at the end.
- On unknown character, return an error token or skip with a warning.

**Definition of done:** `tokenize("2 + 3 * x")` returns
`[Number(2.0), Plus, Number(3.0), Star, Ident("x"), Eof]`.

---

# EPIC 2: Parser (Pratt-style precedence climbing)

---

## Story 2-1: AST Definition

**CALC-2-1-1** `[BLOCKER]`
Define the expression AST as a sum type:
```
type Expr =
    | Literal(float)
    | Var(string)
    | Neg(Expr)
    | BinOp(string, Expr, Expr)
```

`BinOp` carries the operator as a string (`"+"`, `"-"`, `"*"`, `"/"`,
`"%"`, `"^"`). This avoids a separate `Op` sum type and keeps things simple.

---

## Story 2-2: Recursive Descent Parser

**CALC-2-2-1** `[BLOCKER]`
Implement parsing with precedence climbing. Operator precedence (low to high):
1. `+`, `-` (left-associative)
2. `*`, `/`, `%` (left-associative)
3. `^` (right-associative — exponentiation)
4. Unary `-` (prefix)
5. Parenthesized groups

Since Flow doesn't have mutable index variables across recursive calls,
thread a `pos: int` through the parser and return `(Expr, int)` tuples
(the parsed expression and the new position).

Functions:
- `fn:pure parse_expr(tokens: array<Token>, pos: int): (Expr, int)`
- `fn:pure parse_additive(tokens: array<Token>, pos: int): (Expr, int)`
- `fn:pure parse_multiplicative(tokens: array<Token>, pos: int): (Expr, int)`
- `fn:pure parse_power(tokens: array<Token>, pos: int): (Expr, int)`
- `fn:pure parse_unary(tokens: array<Token>, pos: int): (Expr, int)`
- `fn:pure parse_primary(tokens: array<Token>, pos: int): (Expr, int)`

`parse_primary` handles:
- `Number(n)` → `Literal(n)`
- `Ident(name)` → `Var(name)`
- `LParen` → recurse into `parse_expr`, expect `RParen`

**CALC-2-2-2**
Implement error handling in the parser:
- Unexpected token → print `"Error: unexpected TOKEN"` and return a
  sentinel value or propagate via `option<(Expr, int)>`.
- Missing closing paren → `"Error: expected ')'"`.

**Definition of done:** `parse_expr(tokenize("(2 + 3) * -4"), 0)` produces
`BinOp("*", BinOp("+", Literal(2), Literal(3)), Neg(Literal(4)))`.

---

# EPIC 3: Evaluator

---

## Story 3-1: Expression Evaluation

**CALC-3-1-1** `[BLOCKER]`
Implement `fn:pure eval(expr: Expr, env: map<string, float>): float`:
```
match expr {
    Literal(n):        n
    Var(name):         map.get(env, name) ?? 0.0
    Neg(inner):        0.0 - eval(inner, env)
    BinOp(op, l, r): {
        let lv = eval(l, env)
        let rv = eval(r, env)
        match op {
            "+": lv + rv
            "-": lv - rv
            "*": lv * rv
            "/": { ... division by zero check ... }
            "%": { ... modulo ... }
            "^": math.pow(lv, rv)
            _:   0.0
        }
    }
}
```

**CALC-3-1-2**
Handle division by zero: when `rv` is `0.0` for `/` or `%`, print
`"Error: division by zero"` and return `0.0`.

**Definition of done:** `eval(parse("2 + 3 * 4"), env)` returns `14.0`.

---

# EPIC 4: REPL

---

## Story 4-1: Read-Eval-Print Loop

**CALC-4-1-1** `[BLOCKER]`
Implement the REPL in `main()`:
- Print `"> "` prompt.
- Read a line with `io.read_line()`.
- On `none` (EOF) or `"quit"` / `"exit"`, break.
- Otherwise, tokenize → parse → eval → print result.
- Loop.

**CALC-4-1-2**
Implement variable assignment:
- Detect `let <name> = <expr>` lines.
- Tokenize as `[Ident("let"), Ident(name), Equals, ...rest...]`.
- Parse the expression after `=`.
- Evaluate and store in the env map.
- Print `"name = value"`.

**CALC-4-1-3**
Implement special commands:
- `vars` — list all defined variables and their values.
- `clear` — reset the environment.
- `help` — print available operators and commands.

**Definition of done:** Full interactive session:
```
> 2 + 3
5
> let x = 10
x = 10
> x * x
100
> vars
x = 10
> quit
```

---

# EPIC 5: Testing

---

## Story 5-1: Self-Test Program

**CALC-5-1-1**
Create `tests/programs/app_calc.flow` — a non-interactive test that:
- Calls tokenize, parse, and eval directly on a set of expressions.
- Prints results for each.
- Covers: basic arithmetic, precedence, parentheses, unary minus,
  exponentiation, variables.

**CALC-5-1-2**
Create `tests/expected_stdout/app_calc.txt` with expected output.

---

## Dependency Map

```
EPIC 1 (Tokenizer) → EPIC 2 (Parser) → EPIC 3 (Evaluator) → EPIC 4 (REPL) → EPIC 5 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **Sum types** | `Token` and `Expr` — the core data model |
| **Recursive match** | `eval()` pattern matches over recursive `Expr` |
| **`fn:pure`** | Tokenizer, parser, and evaluator are all pure |
| **Tuples** | Parser returns `(Expr, int)` position pairs |
| **`option<T>` / `??`** | Variable lookup, `io.read_line()` |
| **`map<string, float>`** | Variable environment |
| **`match` exhaustiveness** | Operator and expression dispatch |
| **Recursion** | Parser and evaluator are mutually recursive |
| **`math` module** | `math.pow` for exponentiation |
| **`conv` module** | Float-to-string for output |
| **`string` module** | Input trimming, splitting |
| **`io` module** | REPL read/print loop |
