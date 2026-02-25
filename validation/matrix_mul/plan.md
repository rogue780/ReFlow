# Validation: Matrix Multiplication

## Category
Performance & Algorithmic Benchmark

## What It Validates
- Nested loop performance (triple-nested while loops)
- Array indexing arithmetic (row * cols + col)
- Floating-point arithmetic accuracy
- Large array allocation and access patterns
- Cache-friendly vs cache-unfriendly access (if column-major transpose is done)
- Numerical stability (comparing float results)
- Mutable variable performance in tight loops

## Why It Matters
Matrix multiplication is the standard numerical benchmark. It's a triple
nested loop with predictable memory access patterns, making it ideal for
measuring the overhead of Flow's generated C code versus hand-written C.
This validates that Flow can handle compute-intensive numerical work and
that the float arithmetic is IEEE 754 compliant.

## File
`validation/matrix_mul/matrix_mul.flow`

## Structure

**Module:** `module validation.matrix_mul`
**Imports:** `io`, `conv`, `array`, `sys`

### Representation
Matrices are stored as flat `array<float>` with row-major layout.
A matrix is represented as a struct:

```flow
type Matrix {
    rows: int,
    cols: int,
    data: array<float>
}
```

### Functions

1. **`fn:pure matrix_new(rows: int, cols: int): Matrix`**
   - Create matrix filled with 0.0
   - Build `data` array with `rows * cols` elements

2. **`fn:pure matrix_get(m: Matrix, row: int, col: int): float`**
   - `array.get_float(m.data, row * m.cols + col) ?? 0.0`

3. **`fn:pure matrix_set(m: Matrix, row: int, col: int, val: float): Matrix`**
   - Return new Matrix with updated data array
   - (This is expensive — O(n) copy — but validates immutable semantics)

4. **`fn:pure matrix_multiply(a: Matrix, b: Matrix): Matrix`**
   - Classic triple loop: for each (i,j), sum a[i,k] * b[k,j] for k
   - Returns new Matrix with result
   - Uses mutable accumulator for dot product

5. **`fn:pure matrix_identity(n: int): Matrix`**
   - N x N identity matrix (1.0 on diagonal)

6. **`fn:pure matrix_equal(a: Matrix, b: Matrix, epsilon: float): bool`**
   - Element-wise comparison within epsilon tolerance

7. **`fn matrix_print(m: Matrix): none`**
   - Print matrix in readable format, one row per line

8. **`fn:pure matrix_from_flat(rows: int, cols: int, data: array<float>): Matrix`**
   - Construct from existing flat array

9. **`fn main(): none`**
   - Multiply two small matrices, print result
   - Verify identity property: A * I = A
   - Time a larger multiplication (e.g., 100x100)

## Test Program
`tests/programs/val_matrix_mul.flow`

Tests:
- 2x2 * 2x2: known result
  ```
  [1, 2]   [5, 6]   [19, 22]
  [3, 4] * [7, 8] = [43, 50]
  ```
- 2x3 * 3x2: dimension compatibility
- Identity: A * I == A
- Zero matrix: A * 0 == 0

## Expected Output (test)
```
2x2 result: [19.0, 22.0, 43.0, 50.0]
2x3 * 3x2 ok: true
identity ok: true
zero ok: true
done
```

## Estimated Size
~140 lines (app), ~80 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Struct type | `Matrix { rows, cols, data }` |
| `array<float>` | flat matrix storage |
| `array.get_float` | element access |
| `array.push_float` | building arrays |
| Triple `while` loop | O(n^3) multiplication |
| `:mut` variables | loop counters, accumulators |
| `fn:pure` | all matrix operations |
| Float arithmetic | `*`, `+` in dot product |
| `sys.clock_ms` | timing (app only) |

## Performance Notes
- `matrix_set` copies the entire array for each element — this makes
  building matrices O(n^2) per row. For the benchmark, build via
  `array.push_float` in a loop instead.
- The pure/immutable style means matrix_multiply creates a new array.
  Compare timing against expected C performance to measure overhead.

## Known Risks
- Building large arrays element-by-element with `array.push_float` is
  O(n^2) total due to copies. For 100x100 matrices (10,000 elements),
  this should still be fast enough.
- Float formatting: `conv.to_string` on floats may produce unexpected
  precision. Use epsilon comparison, not string comparison.
