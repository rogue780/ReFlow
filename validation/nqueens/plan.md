# Validation: N-Queens Solver

## Category
Performance & Algorithmic Benchmark

## What It Validates
- Recursion depth and correctness (backtracking search)
- Array operations at scale (`array.push_int`, `array.get_int`, `array.len`)
- Integer arithmetic in tight loops
- Absolute value computation (or manual `if` for distance)
- Function call overhead (many recursive calls)
- Pure function performance (no side effects in solver)
- CPU-intensive computation correctness

## Why It Matters
N-Queens is the classic backtracking benchmark. For N=8, there are 92
solutions; for N=12, there are 14,200. This validates that Flow can handle
deep recursion with array state threading, and that the generated C code
is efficient enough to solve N=12 in reasonable time. It also tests that
checked arithmetic doesn't introduce unacceptable overhead.

## File
`validation/nqueens/nqueens.flow`

## Structure

**Module:** `module validation.nqueens`
**Imports:** `io`, `conv`, `array`, `sys`

### Functions

1. **`fn:pure is_safe(queens: array<int>, row: int, col: int): bool`**
   - Check all placed queens (0..row-1)
   - Same column check: `queens[i] == col`
   - Diagonal check: `abs(queens[i] - col) == abs(i - row)`
   - Uses `array.get_int` for each placed queen

2. **`fn:pure abs_int(n: int): int`**
   - Manual absolute value: `if (n < 0) { return 0 - n } else { return n }`

3. **`fn:pure solve(queens: array<int>, row: int, n: int): int`**
   - If `row == n`, return 1 (found a solution)
   - For each col in 0..n-1:
     - If `is_safe(queens, row, col)`, recurse with col added
   - Return total count of solutions found

4. **`fn:pure count_solutions(n: int): int`**
   - Entry point: `solve([], 0, n)`

5. **`fn print_first_solution(n: int): none`**
   - Modified solve that prints the board on first solution found
   - Uses `Q` and `.` characters

6. **`fn main(): none`**
   - Parse N from args (default 8)
   - Print solution count
   - Print first solution as board
   - Optionally print elapsed time

## Test Program
`tests/programs/val_nqueens.flow`

Tests with known answers:
- N=1: 1 solution
- N=4: 2 solutions
- N=5: 10 solutions
- N=8: 92 solutions
- Verify `is_safe` directly: safe position returns true, unsafe returns false

## Expected Output (test)
```
n=1: 1
n=4: 2
n=5: 10
n=8: 92
safe (0,0) []: true
safe (1,0) [0]: false
safe (1,2) [0]: true
done
```

## Estimated Size
~90 lines (app), ~50 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `fn:pure` | solver is purely functional |
| Recursion | backtracking search |
| `array<int>` | queen column positions per row |
| `array.push_int` | threading state through recursion |
| `array.get_int` | accessing placed queens |
| `while` loop | column iteration in solve |
| Checked arithmetic | abs, comparisons |
| `sys.clock_ms` | performance timing (app only) |

## Performance Targets
- N=8 (92 solutions): < 100ms
- N=12 (14,200 solutions): < 5s
- If these are exceeded significantly, investigate checked arithmetic
  overhead or array copy costs.

## Known Risks
- `array.push_int` creates a new array each time. For N=12, this is
  many allocations. Performance may be worse than mutable-array languages.
- Checked arithmetic (`FL_CHECKED_ADD/SUB`) adds overhead per operation.
  In a tight recursive loop, this could be measurable.
