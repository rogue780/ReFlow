# Validation: Binary Search Tree

## Category
Fundamental Correctness — Data Structure Implementation

## What It Validates
- Recursive sum types with multiple fields
- Deep pattern matching and nested destructuring
- Recursive insert/search/traversal algorithms
- Comparison operators for ordering
- In-order traversal producing sorted output (correctness proof)
- Tree balancing awareness (unbalanced is fine — validates correctness, not performance)
- Array building from recursive traversal

## Why It Matters
A BST is more complex than a linked list: each node has two recursive
children, insert must compare and choose a branch, and in-order traversal
must visit left-root-right. This tests Flow's ability to handle real
recursive data structures with branching logic inside pattern matches.

## File
`validation/binary_search_tree/bst.flow`

## Structure

**Module:** `module validation.bst`
**Imports:** `io`, `conv`, `array`

### Types

```flow
type BST = Empty | Node { value: int, left: BST, right: BST }
```

### Functions

1. **`fn:pure bst_new(): BST`**
   - Returns `Empty`

2. **`fn:pure bst_insert(tree: BST, val: int): BST`**
   - Match `Empty` -> `Node { value: val, left: Empty, right: Empty }`
   - Match `Node` -> if val < value, recurse left; if val > value, recurse right; if equal, return unchanged (no duplicates)

3. **`fn:pure bst_contains(tree: BST, val: int): bool`**
   - Match `Empty` -> false
   - Match `Node` -> compare and recurse

4. **`fn:pure bst_min(tree: BST): int?`**
   - Go left until `Empty`, return deepest left node's value
   - Returns `none` for empty tree

5. **`fn:pure bst_max(tree: BST): int?`**
   - Mirror of min

6. **`fn:pure bst_size(tree: BST): int`**
   - Match: `Empty` -> 0, `Node` -> 1 + size(left) + size(right)

7. **`fn:pure bst_height(tree: BST): int`**
   - Match: `Empty` -> 0, `Node` -> 1 + max(height(left), height(right))

8. **`fn:pure bst_inorder(tree: BST): array<int>`**
   - Returns sorted array via in-order traversal
   - `Empty` -> `[]`, `Node` -> concat(inorder(left), [value], inorder(right))

9. **`fn main(): none`**
   - Insert values in scrambled order, print in-order (should be sorted)
   - Demonstrate all operations

## Test Program
`tests/programs/val_bst.flow`

Insert values: 5, 3, 7, 1, 4, 6, 8, 2

Tests:
- Size is 8
- Contains 4: true, contains 9: false
- Min is 1, max is 8
- In-order traversal: [1, 2, 3, 4, 5, 6, 7, 8]
- Height (this specific tree): 4
- Insert duplicate (5 again): size still 8

## Expected Output (test)
```
size: 8
contains 4: true
contains 9: false
min: 1
max: 8
inorder: [1, 2, 3, 4, 5, 6, 7, 8]
height: 4
dup size: 8
done
```

## Estimated Size
~120 lines (app), ~80 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Recursive sum type | `BST = Empty \| Node { value, left, right }` |
| `match` with nested fields | dispatching on tree structure |
| `fn:pure` | all tree operations are pure |
| Deep recursion | tree traversal |
| `option<T>` | min/max on empty tree |
| `array<int>` + `array.concat` | building sorted output |
| Comparison operators | `<`, `>`, `==` for BST ordering |

## Known Risks
- `array.concat` inside recursion creates O(n^2) array copies for large
  trees. This is a known limitation — validates correctness, not performance.
- If Flow doesn't support recursive sum types with multiple fields per
  variant, this will fail — that's a critical finding.
