# Validation: Binary Trees (Memory Allocation Stress)

## Category
Performance & Algorithmic Benchmark

## What It Validates
- Rapid allocation and deallocation of many small objects
- GC / allocator stress testing (thousands of tree nodes)
- Recursive construction and destruction of balanced binary trees
- Memory consumption under pressure
- Runtime stability over extended allocation periods
- Sum type allocation patterns at scale

## Why It Matters
This is adapted from the Computer Language Benchmarks Game "binary-trees"
benchmark. It creates and discards millions of tree nodes to stress the
memory allocator. Since Flow compiles to C with manual memory management
(malloc/free via the runtime), this tests whether the runtime leaks memory,
handles allocation pressure gracefully, and whether the generated code
patterns cause fragmentation.

## File
`validation/binary_trees/binary_trees.flow`

## Structure

**Module:** `module validation.binary_trees`
**Imports:** `io`, `conv`, `sys`

### Types

```flow
type Tree = Leaf | Branch { left: Tree, right: Tree }
```

Note: Unlike the BST, this tree stores no data — it's purely structural,
designed to test allocation patterns.

### Functions

1. **`fn:pure make_tree(depth: int): Tree`**
   - If depth == 0, return `Leaf`
   - Else return `Branch { left: make_tree(depth - 1), right: make_tree(depth - 1) }`
   - Creates 2^(depth+1) - 1 nodes

2. **`fn:pure node_count(tree: Tree): int`**
   - `Leaf` -> 1, `Branch` -> 1 + count(left) + count(right)

3. **`fn:pure check(tree: Tree): int`**
   - Checksum: `Leaf` -> 1, `Branch` -> 1 + check(left) + check(right)
   - (Same as node_count — the point is the traversal, not the value)

4. **`fn benchmark(max_depth: int): none`**
   - For each depth from 4 to max_depth (step 2):
     - Create `2^(max_depth - depth + 4)` trees of the given depth
     - Sum their checksums
     - Print iteration count and checksum
   - Also create one "long-lived" tree at max_depth that persists
     throughout (tests that GC doesn't collect live objects)

5. **`fn main(): none`**
   - Parse max_depth from args (default 10)
   - Run benchmark
   - Print timing

## Test Program
`tests/programs/val_binary_trees.flow`

Use small depth (4) for fast deterministic test:
- make_tree(0) -> Leaf, node_count 1
- make_tree(1) -> Branch with 2 Leaves, node_count 3
- make_tree(3) -> 15 nodes
- make_tree(4) -> 31 nodes
- Stress: create 100 trees of depth 4, verify all have check 31

## Expected Output (test)
```
depth 0: 1
depth 1: 3
depth 3: 15
depth 4: 31
stress 100x: ok
done
```

## Estimated Size
~70 lines (app), ~50 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Recursive sum type | `Tree = Leaf \| Branch` |
| Deep recursion | 2^depth recursive calls in make_tree |
| Pattern matching | node_count, check |
| `fn:pure` | all tree operations |
| `while` loop | iteration counts in benchmark |
| `sys.clock_ms` | timing |
| `:mut` counters | iteration and sum accumulators |

## Performance Targets
- Depth 10: < 1s
- Depth 15: < 10s
- Depth 18+: may require minutes — useful for stress testing but not
  for CI

## Known Risks
- Flow has no garbage collector — it compiles to C with malloc. Unless
  the runtime has reference counting or arena allocation, trees are
  leaked when they go out of scope. This is expected and acceptable
  for a benchmark, but documents a real limitation.
- Stack overflow at high depths (>20). C default stack is typically 8MB.
- Each Branch node allocates two pointers plus a tag. At depth 20,
  that's ~2M nodes * ~24 bytes = ~48MB. Should be fine.
