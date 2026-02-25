# Validation: FizzBuzz

## Category
Fundamental Correctness & Syntax

## What It Validates
- Basic control flow: `if`/`else if`/`else` chains
- Integer arithmetic and modulo operator (`%`)
- Loop constructs (`while` with counter)
- String output via `io.println`
- Integer-to-string conversion via `conv.to_string`
- String concatenation
- Mutable local variables (`:mut`)
- Comparison operators (`==`)

## Why It Matters
FizzBuzz is the simplest possible program that exercises conditionals, loops,
arithmetic, and output together. If this doesn't compile and run correctly,
nothing else will.

## File
`validation/fizzbuzz/fizzbuzz.flow`

## Structure

**Module:** `module validation.fizzbuzz`
**Imports:** `io`, `conv`

### Functions

1. **`fn:pure fizzbuzz(n: int): string`**
   - If `n % 15 == 0` return `"FizzBuzz"`
   - Else if `n % 3 == 0` return `"Fizz"`
   - Else if `n % 5 == 0` return `"Buzz"`
   - Else return `conv.to_string(n)`

2. **`fn main(): none`**
   - Loop from 1 to 100 inclusive
   - Print `fizzbuzz(i)` for each

## Test Program
`tests/programs/val_fizzbuzz.flow`

Calls `fizzbuzz` on specific values and prints results:
- `fizzbuzz(1)` -> `"1"`
- `fizzbuzz(3)` -> `"Fizz"`
- `fizzbuzz(5)` -> `"Buzz"`
- `fizzbuzz(15)` -> `"FizzBuzz"`
- `fizzbuzz(97)` -> `"97"`
- `fizzbuzz(30)` -> `"FizzBuzz"`
- `fizzbuzz(99)` -> `"Fizz"`
- `fizzbuzz(100)` -> `"Buzz"`

## Expected Output (test)
```
1
Fizz
Buzz
FizzBuzz
97
FizzBuzz
Fizz
Buzz
done
```

## Estimated Size
~30 lines (app), ~25 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `fn:pure` | fizzbuzz function |
| `if`/`else if`/`else` | branching logic |
| `%` (modulo) | divisibility check |
| `while` loop | counting loop |
| `conv.to_string` | int to string |
| `:mut` binding | loop counter |
