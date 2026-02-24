# Parallel Data Enrichment

A data enrichment pipeline that runs three independent computations on each
input value **concurrently** using Flow's parallel fan-out operator `<:()`,
then combines the results. Also demonstrates coroutine-based stream production.

## Run it

```bash
python main.py build examples/parallel_enrich.flow -o /tmp/parallel_enrich && /tmp/parallel_enrich
```

## What it does

The program enriches four data points (values: 90, 45, 20, 75) by computing
three derived properties for each:

| Enrichment | Formula | Purpose |
|------------|---------|---------|
| `compute_score` | `value * 3 + 1` | Numeric scoring |
| `categorize` | `>80 = "high"`, `>40 = "medium"`, else `"low"` | Classification |
| `compute_hash` | `value * 31 + 17` | Hash computation |

The program runs this two ways:

### Part 1 — Parallel fan-out

```flow
let output = v -> <:(compute_score | categorize | compute_hash) -> format_result
```

The `<:()` operator spawns all three functions as concurrent coroutines. Each
receives the same input `v`, runs on its own thread, and the runtime collects
all three results before passing them to `format_result(score, category, hash)`.

All three functions are marked `fn:pure`, which is required for parallel
fan-out (ensures thread safety).

### Part 2 — Coroutine stream

```flow
let source :< produce_values()
```

The `:< ` operator spawns `produce_values()` on a separate thread. The main
thread pulls values one at a time with `source.next()`, processing each while
the producer may be preparing the next value.

## Expected output

```
=== Parallel Enrichment ===
alpha: score=271 cat=high hash=2807
beta: score=136 cat=medium hash=1412
gamma: score=61 cat=low hash=637
delta: score=226 cat=medium hash=2342
=== Coroutine Stream ===
alpha: score=271 cat=high hash=2807
beta: score=136 cat=medium hash=1412
gamma: score=61 cat=low hash=637
delta: score=226 cat=medium hash=2342
```

Both parts produce identical results — the parallel fan-out version just runs
the three enrichments concurrently instead of sequentially.

## Language features demonstrated

| Feature | Where |
|---------|-------|
| Parallel fan-out `<:(a \| b \| c)` | 3-branch concurrent enrichment |
| `fn:pure` | All enrichment functions — required for parallel safety |
| Coroutines `:< ` | `produce_values()` spawned on separate thread |
| `.next()` / `.done()` | Manual stream consumption with match |
| `stream<int>` | `produce_values` yields ints via `yield` |
| Composition chains `->` | Fan-out piped into `format_result` |
| Record types | `Record` for structured input data |

## How to modify

- Add more enrichment functions to the fan-out — just add another branch
  and update `format_result` to accept the additional parameter.
- Change `produce_values` to generate more data or read from a different
  source.
- Replace the sequential Part 2 with parallel fan-out to compare
  performance on larger datasets.
