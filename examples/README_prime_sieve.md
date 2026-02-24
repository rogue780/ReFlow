# Prime Sieve (Coroutines)

Finds all prime numbers up to 50 using three different approaches, each
demonstrating Flow's coroutine and stream capabilities.

## Run it

```bash
python main.py build examples/prime_sieve.flow -o /tmp/prime_sieve && /tmp/prime_sieve
```

## What it does

The program finds primes up to 50 three ways:

### Approach 1 — Coroutine producer with inline filtering

```flow
let candidates :< integers_from(2, 50)
```

Spawns a coroutine that yields integers 2..50 on a separate thread. The main
thread pulls each candidate with `.next()` and checks `is_prime(n)` inline.

### Approach 2 — Filtered stream function

```flow
let primes :< filter_primes(2, 50)
```

Spawns a single coroutine that internally combines generation and filtering.
The `filter_primes` function iterates through the range and only `yield`s
values that pass `is_prime`. The consumer just prints whatever comes out.

### Approach 3 — Concurrent coroutines on disjoint ranges

```flow
let low  :< filter_primes(2, 25)
let high :< filter_primes(26, 50)
```

Spawns **two** coroutines simultaneously, each covering half the range. Both
run on their own threads. The main thread drains `low` first, then `high`.

## Expected output

```
=== Coroutine sieve ===
2
3
5
7
11
13
17
19
23
29
31
37
41
43
47
=== Filtered stream ===
2
3
5
7
11
13
17
19
23
29
31
37
41
43
47
=== Concurrent coroutines ===
Low primes:
  2
  3
  5
  7
  11
  13
  17
  19
  23
High primes:
  29
  31
  37
  41
  43
  47
```

## Language features demonstrated

| Feature | Where |
|---------|-------|
| Coroutines `:< ` | Spawns stream functions on separate threads |
| `yield` | `integers_from` and `filter_primes` yield values lazily |
| `.next()` / `.done()` | Manual consumption of coroutine output |
| `match some/none` | Pattern matching on option values from `.next()` |
| `fn:pure` | `is_prime` is pure (no side effects) |
| `stream<int>` return type | Functions that produce streams |
| Multiple concurrent coroutines | `low` and `high` run simultaneously |
| `while` with arithmetic conditions | `while (d * d <= n)` in `is_prime` |

## How to modify

- Change the `limit` to find primes in a larger range (e.g. `integers_from(2, 1000)`).
- Split into more ranges for the concurrent approach (e.g. four coroutines
  each covering a quarter of the range).
- Add a `count` variable to track how many primes are found.
