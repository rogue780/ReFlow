---
name: test-first
description: Enforces the testing discipline required for the ReFlow compiler project. Read this skill before starting any ticket that involves writing or modifying compiler code.
---

# Test-First Discipline for the ReFlow Compiler

Tests are not optional and are not something to add after a ticket is "done." A ticket without tests is not done. This skill defines exactly how testing works in this project and what is required before marking any ticket complete.

---

## The Rule

Before marking a ticket complete:

1. Run `make test` from the project root.
2. All tests must pass.
3. At least one test must exercise the new behavior (positive case).
4. If the behavior can fail (error conditions, invalid input), at least one test must exercise the failure (negative case).

If `make test` fails, the ticket is not done regardless of how confident you are in the code.

---

## Test Types and Where They Live

### Unit Tests — `tests/unit/`

For individual functions in the compiler pipeline: lexer token sequences, parser AST shapes, resolver symbol bindings, type checker type inference results, mangler output.

Write unit tests as plain Python using `unittest` or `pytest`. Each test file mirrors the module it tests: `tests/unit/test_lexer.py` tests `compiler/lexer.py`.

**What makes a good unit test:**
- Tests one thing.
- Has a clear name: `test_fstring_nested_braces`, not `test_1`.
- For error cases, asserts the specific error type and checks that `file`, `line`, `col` are populated.
- Does not depend on other tests running first.

### Golden File Tests — `tests/programs/` and `tests/expected/`

For the emitter. Each `.reflow` file in `tests/programs/` has a corresponding `.c` file in `tests/expected/`. The test harness runs the full pipeline on the source, diffs the output against the expected file, and fails if they differ.

**When to update a golden file:**
Only when you intentionally change emitter behavior. When you update a golden file, do it deliberately: generate the new expected output, review it to confirm it is correct, then commit both the emitter change and the updated golden file in the same commit.

Never auto-update golden files without reviewing the diff. The point of golden files is to catch unintended changes.

**Naming convention:** the `.reflow` file and its `.c` file have the same base name.
```
tests/programs/option_test.reflow
tests/expected/option_test.c
```

### End-to-End Tests — `tests/programs/` with `.expected_stdout`

For programs that produce output. Each `.reflow` file can have a corresponding `.expected_stdout` file. The test harness compiles, links, runs the binary, and diffs stdout.

```
tests/programs/hello.reflow
tests/expected_stdout/hello.txt    → "Hello, World!\n"
```

### Negative Tests — `tests/programs/errors/` and `tests/expected_errors/`

For programs that should fail to compile. Each `.reflow` file in `tests/programs/errors/` has a `.expected_error` file in `tests/expected_errors/` containing:
- The expected error class name (e.g., `TypeError`, `ResolveError`)
- A prefix of the expected error message

The test harness verifies the compiler exits with code 1 and the error output contains the expected class and message prefix.

```
tests/programs/errors/missing_match_arm.reflow
tests/expected_errors/missing_match_arm.txt →
    TypeError
    match on Shape is not exhaustive: missing variant 'Triangle'
```

---

## What to Test for Each Epic

### Lexer (Epic 2)
- Each token type with at least one valid example
- All multi-character operators (especially `<:(`, `===`, `:<`, `->`, `??`, `..`)
- F-string with nested expression
- Error cases: unterminated string, unrecognized character

### Parser (Epic 4)
- Each declaration type (fn, type, interface, alias, module, import)
- Composition chain with fan-out
- All statement types
- All expression types including ternary, propagation `?`, null coalesce `??`
- Error recovery: two errors in one file produce two error objects

### Resolver (Epic 5)
- Undefined variable → `ResolveError`
- Forward reference (function A calls function B defined later) → resolves correctly
- Lambda captures from enclosing scope → captures list is correct
- `self` outside method body → `ResolveError`

### Type Checker (Epic 6)
- Type mismatch → `TypeError` with clear message
- Non-exhaustive match on sum type → `TypeError`
- Non-exhaustive match on `option<T>` → `TypeError`
- Non-exhaustive match on primitive → warning only (no error)
- `fn:pure` calling non-pure → `TypeError`
- Double stream consumption → `TypeError`
- `:mut` param with immutable arg → `TypeError`
- Fan-out arity mismatch → `TypeError`
- `coerce` on non-congruent types → `TypeError`
- Auto-lifting: `let x: int? = 5` emits a `SomeExpr` node

### Emitter (Epic 8)
- Golden file test for every distinct language construct
- `option<T>` emits tagged struct with correct tag values (0=none, 1=some)
- `result<T, E>` emits tagged union
- Sum type emits tagged union with one case per variant
- Streaming function emits frame struct + next + free + factory
- Overflow-checked arithmetic emits `RF_CHECKED_ADD` etc.
- F-string emits chain of `rf_string_concat` calls

---

## The Golden File Discipline in Detail

When adding a new language feature to the emitter:

1. Write the `.reflow` test program first.
2. Run the emitter. It will fail or produce wrong output.
3. Fix the emitter until the output is correct.
4. Copy the correct output to `tests/expected/<name>.c`.
5. Run `make test`. The golden file test should now pass.
6. Commit: the `.reflow` source, the `.c` expected file, and the emitter changes together.

When changing existing emitter behavior:

1. Run `make test` before starting. Note which golden tests currently pass.
2. Make your change.
3. Run `make test`. Golden tests will fail for files affected by the change.
4. For each failing golden test, inspect the diff:
   - If the new output is correct: update the expected file deliberately.
   - If the new output is wrong: fix the emitter.
5. Run `make test` again. All tests should pass.

Never run `make update-golden` (or equivalent) blindly without reading every diff.

---

## Running Tests

```bash
make test            # runs all tests
make test-unit       # runs only unit tests
make test-golden     # runs only golden file tests
make test-e2e        # runs only end-to-end execution tests
make test-negative   # runs only negative (expected-error) tests
```

Individual test:
```bash
python -m pytest tests/unit/test_lexer.py::test_fstring_nested_braces -v
```

Regenerate a specific golden file (do this only after confirming the output is correct):
```bash
python main.py emit-c tests/programs/option_test.reflow > tests/expected/option_test.c
```

---

## A Note on Test Quality

A test that always passes regardless of whether the code is correct is worse than no test at all — it gives false confidence. When writing a test, ask: if I introduced a bug here, would this test catch it?

Signs of a weak test:
- It only tests the happy path for a feature that has many error cases.
- It asserts something is not None without checking its value.
- It would pass even if the function returned the wrong type.

Signs of a good test:
- It fails when you introduce a plausible bug in the code it's testing.
- It checks the specific value, not just that something exists.
- Its name describes exactly what it's testing and why.
