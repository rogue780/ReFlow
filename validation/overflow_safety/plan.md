# Validation: Overflow Safety

## Category
Security & Negative Testing

## What It Validates
- Checked arithmetic: integer overflow detection and panic
- Checked arithmetic: integer underflow detection and panic
- Division by zero handling (int and float)
- Float special values (infinity, NaN behavior)
- Modulo by zero (panics per Known Decision #7)
- Int64 overflow behavior
- Arithmetic in expressions vs assignments
- Overflow in loop counters
- Compiler's `FL_CHECKED_ADD/SUB/MUL` macro correctness

## Why It Matters
Flow compiles to C, which has undefined behavior for signed integer overflow.
Flow's runtime uses checked arithmetic macros that detect overflow and panic
instead. This validation ensures those checks work correctly across all
integer operations and edge cases. A single missed overflow check could
cause silent data corruption or security vulnerabilities.

## File
`validation/overflow_safety/overflow_safety.flow`

## Structure

**Module:** `module validation.overflow_safety`
**Imports:** `io`, `conv`

### Approach
Each test case calls a function that performs an arithmetic operation
expected to overflow/underflow. Since overflow causes a panic (process
termination), the test program can only test one overflow per execution.
The test program tests:
1. Normal arithmetic that does NOT overflow (positive tests)
2. Boundary values that are just within range
3. Document which operations would overflow (as comments)

For the actual overflow tests, use separate small programs or a test
harness that catches panics (if possible).

### Functions

1. **`fn:pure test_add_safe(): none`**
   - `2147483646 + 1` = 2147483647 (INT_MAX - 1 + 1 = INT_MAX, safe)
   - Print result

2. **`fn:pure test_sub_safe(): none`**
   - `-2147483647 - 1` = -2147483648 (INT_MIN + 1 - 1 = INT_MIN, safe)
   - Print result

3. **`fn:pure test_mul_safe(): none`**
   - `46340 * 46340` = 2147395600 (largest int whose square fits in int32)
   - Print result

4. **`fn:pure test_div_safe(): none`**
   - `100 / 3` = 33 (integer division truncates)
   - `-7 / 2` = -3 (truncation toward zero)

5. **`fn:pure test_mod_safe(): none`**
   - `10 % 3` = 1
   - `-10 % 3` = -1 (C99 behavior)

6. **`fn:pure test_float_div_zero(): none`**
   - `1.0 / 0.0` should follow IEEE 754 (infinity, not panic)
   - `0.0 / 0.0` should be NaN
   - Print results (may be "inf", "nan", or platform-specific)

7. **`fn:pure test_float_mod_zero(): none`**
   - `1.0 % 0.0` should panic per Known Decision #7
   - (Cannot test in-process — document as expected panic)

8. **`fn:pure test_boundary_values(): none`**
   - INT_MAX: 2147483647
   - INT_MIN: -2147483648
   - Arithmetic that stays exactly at boundaries

9. **`fn:pure test_int64_safe(): none`**
   - `9223372036854775806 + 1` = INT64_MAX - 1 + 1 (if int64 literals work)
   - Large int64 multiplication

10. **`fn main(): none`**
    - Run all safe tests, print results
    - Document expected panics in comments

### Overflow Test Scripts (separate files)

`validation/overflow_safety/test_add_overflow.flow` — `2147483647 + 1` (should panic)
`validation/overflow_safety/test_sub_overflow.flow` — `-2147483648 - 1` (should panic)
`validation/overflow_safety/test_mul_overflow.flow` — `2147483647 * 2` (should panic)
`validation/overflow_safety/test_div_overflow.flow` — `-2147483648 / -1` (should panic — C UB)
`validation/overflow_safety/test_mod_zero.flow` — `10 % 0` (should panic)

Each is a minimal program that runs one operation. The test harness runs
each, expects a non-zero exit code, and verifies the panic message.

## Test Program
`tests/programs/val_overflow_safety.flow`

Tests only the safe operations:

## Expected Output (test)
```
add safe: 2147483647
sub safe: -2147483648
mul safe: 2147395600
div trunc: 33
div neg: -3
mod: 1
mod neg: -1
float div zero: inf
float div 0/0: nan
boundary max: 2147483647
boundary min: -2147483648
done
```

## Estimated Size
~100 lines (main test), ~10 lines each (5 overflow scripts), ~80 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `FL_CHECKED_ADD` | addition overflow detection |
| `FL_CHECKED_SUB` | subtraction overflow detection |
| `FL_CHECKED_MUL` | multiplication overflow detection |
| `FL_CHECKED_DIV` | division by zero, INT_MIN/-1 |
| `FL_CHECKED_MOD` | modulo by zero |
| `FL_CHECKED_FMOD` | float modulo by zero |
| Integer literals | boundary values |
| `int64` type | 64-bit arithmetic |
| `float` arithmetic | IEEE 754 compliance |
| Panic handling | runtime error on overflow |

## Known Risks
- `INT_MIN / -1` is undefined behavior in C. Flow's `FL_CHECKED_DIV`
  should catch this. If it doesn't, that's a critical security finding.
- Int literal parsing: `2147483647` must be parsed as int without overflow.
  If the parser or lexer overflows during literal parsing, that's a
  compiler bug.
- Float formatting: `inf` and `nan` may print differently on different
  platforms. Use `string.contains` to check rather than exact match.
- Int64 literal support: Flow may not support int64 literals directly.
  If not, test via computation (`let x: int64 = 9223372036854775807`).
