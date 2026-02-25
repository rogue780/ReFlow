# Validation: Linked List

## Category
Fundamental Correctness — Data Structure Implementation

## What It Validates
- Recursive sum types (the core of Flow's algebraic data types)
- Pattern matching (`match`) on sum type variants
- Recursive functions operating on recursive types
- Generic types (if possible: `list<T>`)
- Option return types for safe access
- Pure function composition
- Memory allocation patterns (many small allocations linked together)

## Why It Matters
A linked list is the canonical test for algebraic data types. It requires
recursive type definitions, pattern matching to destructure, and recursive
functions to traverse. If Flow's sum types and match expressions work
correctly, this should be clean and elegant. If they don't, this will
expose the problems immediately.

## File
`validation/linked_list/linked_list.flow`

## Structure

**Module:** `module validation.linked_list`
**Imports:** `io`, `conv`

### Types

```flow
type IntList = Nil | Cons { head: int, tail: IntList }
```

### Functions

1. **`fn:pure list_new(): IntList`**
   - Returns `Nil`

2. **`fn:pure list_prepend(lst: IntList, val: int): IntList`**
   - Returns `Cons { head: val, tail: lst }`

3. **`fn:pure list_length(lst: IntList): int`**
   - Match: `Nil` -> 0, `Cons` -> 1 + `list_length(tail)`

4. **`fn:pure list_sum(lst: IntList): int`**
   - Match: `Nil` -> 0, `Cons` -> head + `list_sum(tail)`

5. **`fn:pure list_contains(lst: IntList, val: int): bool`**
   - Match: `Nil` -> false, `Cons` -> head == val || `list_contains(tail, val)`

6. **`fn:pure list_reverse(lst: IntList): IntList`**
   - Accumulator-based: `reverse_acc(lst, Nil)`

7. **`fn:pure reverse_acc(lst: IntList, acc: IntList): IntList`**
   - Match: `Nil` -> acc, `Cons` -> `reverse_acc(tail, Cons { head, acc })`

8. **`fn:pure list_nth(lst: IntList, n: int): int?`**
   - Returns option — `none` if out of bounds

9. **`fn list_to_string(lst: IntList): string`**
   - Format: `"[1, 2, 3]"`

10. **`fn main(): none`**
    - Build list, demonstrate all operations, print results

## Test Program
`tests/programs/val_linked_list.flow`

Duplicates types and functions. Tests:
- Empty list length is 0
- Prepend 3 elements, length is 3
- Sum of [1, 2, 3] is 6
- Contains: true for present, false for absent
- Reverse [1, 2, 3] is [3, 2, 1]
- Nth: valid index returns some, out-of-bounds returns none
- to_string formatting

## Expected Output (test)
```
empty length: 0
length: 3
sum: 6
contains 2: true
contains 9: false
reversed: [3, 2, 1]
nth 0: 1
nth 5: none
to_string: [1, 2, 3]
done
```

## Estimated Size
~100 lines (app), ~80 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Recursive sum type | `IntList = Nil \| Cons` |
| `match` expression | every function dispatches on variant |
| `fn:pure` | all list operations are pure |
| Recursion | list traversal is inherently recursive |
| `option<T>` | `list_nth` returns `int?` |
| Pattern matching | destructuring `Cons { head, tail }` |

## Known Risks
- Deep recursion on large lists may stack overflow (C has finite stack).
  Test with modest sizes (< 1000 elements).
- If recursive sum types aren't supported yet, this will fail at parse
  or type-check time — that's a valid finding.
