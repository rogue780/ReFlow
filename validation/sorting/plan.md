# Validation: Sorting Algorithms

## Category
Performance & Algorithmic Benchmark

## What It Validates
- Array operations at scale (push, get, set, length, concat)
- Algorithm correctness across edge cases (empty, single, sorted, reverse-sorted, duplicates)
- Comparison-based sorting logic
- Recursive and iterative algorithm implementations
- Performance characteristics of immutable array operations
- `fn:pure` functions that build new arrays from existing ones

## Why It Matters
Sorting is a fundamental operation that exercises array manipulation
heavily. Implementing multiple sorting algorithms (insertion sort, merge
sort, quicksort) validates that Flow's array operations are correct and
reveals performance characteristics. The merge sort is particularly
important: it's naturally functional (builds new arrays) and is the
algorithm Flow's stdlib `sort.sort` likely uses.

## File
`validation/sorting/sorting.flow`

## Structure

**Module:** `module validation.sorting`
**Imports:** `io`, `conv`, `array`

### Functions

1. **`fn:pure insertion_sort(arr: array<int>): array<int>`**
   - O(n^2) — iterate, insert each element in correct position
   - Build new sorted array by insertion
   - Simple, tests basic array building

2. **`fn:pure merge_sort(arr: array<int>): array<int>`**
   - Split array in half, recursively sort both halves, merge
   - `merge(left, right)`: two-pointer merge into new array
   - O(n log n) — tests recursive array splitting

3. **`fn:pure merge(left: array<int>, right: array<int>): array<int>`**
   - Two-index merge of sorted arrays

4. **`fn:pure quicksort(arr: array<int>): array<int>`**
   - Choose pivot (first element), partition into less/equal/greater
   - Recursively sort less and greater, concat all three
   - Tests array partitioning and concatenation

5. **`fn:pure is_sorted(arr: array<int>): bool`**
   - Verify each element <= next element

6. **`fn:pure arrays_equal(a: array<int>, b: array<int>): bool`**
   - Element-wise comparison

7. **`fn array_to_string(arr: array<int>): string`**
   - Format: `"[3, 1, 4, 1, 5]"`

8. **`fn main(): none`**
   - Sort several test arrays with all three algorithms
   - Verify all produce same sorted result
   - Time each on a larger array (e.g., 1000 elements)

## Test Program
`tests/programs/val_sorting.flow`

Test cases per algorithm:
- Empty array `[]`
- Single element `[1]`
- Already sorted `[1, 2, 3, 4, 5]`
- Reverse sorted `[5, 4, 3, 2, 1]`
- Duplicates `[3, 1, 4, 1, 5, 9, 2, 6, 5]`
- All same `[7, 7, 7, 7]`

## Expected Output (test)
```
insertion empty: []
insertion single: [1]
insertion sorted: [1, 2, 3, 4, 5]
insertion reverse: [1, 2, 3, 4, 5]
insertion dups: [1, 1, 2, 3, 4, 5, 5, 6, 9]
merge sorted: [1, 2, 3, 4, 5]
merge reverse: [1, 2, 3, 4, 5]
merge dups: [1, 1, 2, 3, 4, 5, 5, 6, 9]
quick sorted: [1, 2, 3, 4, 5]
quick reverse: [1, 2, 3, 4, 5]
quick dups: [1, 1, 2, 3, 4, 5, 5, 6, 9]
all same: [7, 7, 7, 7]
done
```

## Estimated Size
~160 lines (app), ~90 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `array<int>` | all operations |
| `array.push_int` | building sorted arrays |
| `array.get_int` | element access |
| `array.len` | size checking |
| `array.concat` | merging in merge sort, quicksort |
| `fn:pure` | all sorting functions |
| Recursion | merge sort, quicksort |
| `while` loop | insertion sort, merge |
| `:mut` variables | indices, accumulators |
| `option<int>` | safe array access |

## Performance Notes
- Insertion sort is O(n^2) and copies arrays — will be slow for n > 100.
- Merge sort and quicksort use `array.concat` which copies — O(n) per merge.
  Total is O(n log^2 n) due to copy overhead, not O(n log n).
- For validation purposes, n=100 is sufficient. For benchmarking, n=1000.

## Known Risks
- Array slicing: Flow may not have `array.slice(arr, start, end)`. If not,
  splitting an array requires element-by-element copying — still works but
  is verbose. This would be a stdlib gap finding.
- `array.get_int` returns `option<int>` — every access in a sort must
  unwrap with `?? 0`. This is safe but verbose.
