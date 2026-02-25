# Validation: Generic Collections

## Category
Language-Specific Features — Type System

## What It Validates
- Generic type parameters (`<T>`) in struct and function definitions
- Type inference with generics (does the compiler infer T correctly?)
- Generic functions with interface bounds (`T fulfills Showable`)
- Monomorphization: generic code instantiated for int, float, string, struct
- Generic containers holding value types vs pointer types
- Interaction between generics and option types
- Interaction between generics and sum types

## Why It Matters
Generics are essential for reusable data structures. Flow has generics with
interface bounds — this validation ensures they work across multiple
instantiations and that the compiler generates correct monomorphized code
for each type. This is particularly important because the lowering must
handle value-type boxing (Known Decision #8) and non-pointer array push
(Known Decision #9) differently per type.

## File
`validation/generic_collections/generic_collections.flow`

## Structure

**Module:** `module validation.generic_collections`
**Imports:** `io`, `conv`, `string`, `array`, `map`

### Types

```flow
type Stack<T> {
    items: array<T>,
    size: int
}

type Pair<A, B> {
    first: A,
    second: B
}
```

Note: Flow may not support user-defined generic types yet. If `type Stack<T>`
is not supported, use generic functions over the stdlib `array<T>` and `map`
types instead — and document the gap.

### Functions (if user-defined generics work)

1. **`fn:pure stack_new<T>(): Stack<T>`**
   - Returns `Stack { items: [], size: 0 }`

2. **`fn:pure stack_push<T>(s: Stack<T>, val: T): Stack<T>`**
   - Returns new Stack with val appended

3. **`fn:pure stack_pop<T>(s: Stack<T>): (Stack<T>, T?)`**
   - Returns (new stack without top, option of popped value)

4. **`fn:pure stack_peek<T>(s: Stack<T>): T?`**
   - Returns top element without removing

5. **`fn:pure stack_is_empty<T>(s: Stack<T>): bool`**
   - Returns size == 0

### Functions (stdlib generics — always test these)

6. **`fn test_array_int(): none`**
   - `array.push_int`, `array.get_int`, `array.len` — basic int array

7. **`fn test_array_float(): none`**
   - Same with float arrays — tests float boxing path

8. **`fn test_array_string(): none`**
   - String arrays — pointer type, no boxing needed

9. **`fn test_array_bool(): none`**
   - Bool arrays — tests bool boxing path

10. **`fn test_map_string_int(): none`**
    - `map.new()`, `map.set`, `map.get` with string keys, int values
    - Tests value-type boxing in maps

11. **`fn test_map_string_string(): none`**
    - String values — no boxing needed

12. **`fn test_generic_showable<T fulfills Showable>(val: T, expected: string): none`**
    - Call `conv.to_string(val)` and compare with expected
    - Tests bounded generic instantiation

13. **`fn main(): none`**
    - Run all test functions, print results

## Test Program
`tests/programs/val_generic_collections.flow`

Tests:
- Int array: push 3 values, get each, verify
- Float array: push, get, verify
- String array: push, get, verify
- Bool array: push, get, verify
- Map<string, int>: set 3 pairs, get each, verify
- Map<string, string>: set and get
- Bounded generic: to_string on int, float, bool, string
- If user-defined generics work: Stack<int> push/pop/peek

## Expected Output (test)
```
int array: [10, 20, 30]
float array: [1.5, 2.5]
string array: [hello, world]
bool array: [true, false]
map int: a=1 b=2 c=3
map str: x=hello y=world
show int: 42
show float: 3.14
show bool: true
show string: hello
done
```

## Estimated Size
~150 lines (app), ~100 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `array<int/float/string/bool>` | type-specific array ops |
| `map<string, int/string>` | map with different value types |
| `array.push_int/float` | value-type push |
| `array.push` (generic) | pointer-type push |
| `map.set/get` | with boxing for value types |
| `T fulfills Showable` | bounded generic |
| `conv.to_string<T>` | generic to_string |
| `option<T>` | array.get returns option |

## Known Risks
- User-defined generic types (`type Stack<T>`) may not be supported in
  the current compiler. If not, this is a significant finding — document
  it and test only stdlib generics.
- `array<bool>` may have boxing issues (bool is a value type). The
  lowering should use `fl_box_bool` / `fl_opt_unbox_bool`.
- Multi-parameter generics (`Pair<A, B>`) may not be supported. Test
  and document.
