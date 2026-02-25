# Validation: Stream Pipeline (Producer/Consumer)

## Category
Language-Specific Features — Concurrency

## What It Validates
- Flow's first-class streaming system (`stream<T>`, `yield`, `for..in`)
- Producer/consumer patterns using coroutines
- Multiple concurrent streams interleaved
- Stream composition and chaining
- Backpressure behavior (consumer controls pace)
- `send` for bidirectional stream communication
- Stream termination and cleanup
- Fan-out: one producer, multiple consumers

## Why It Matters
Streams are Flow's primary concurrency primitive (no threads, no async/await).
This is the most important language-specific validation — if streams don't
work correctly for producer/consumer patterns, Flow's concurrency story
is broken. This program validates that streams can replace threads for
data pipeline workloads.

## File
`validation/stream_pipeline/stream_pipeline.flow`

## Structure

**Module:** `module validation.stream_pipeline`
**Imports:** `io`, `conv`, `string`, `array`

### Streams

1. **`fn counter(start: int, end_val: int): stream<int>`**
   - Yields integers from start to end_val inclusive
   - Tests basic producer pattern

2. **`fn filter_even(source: stream<int>): stream<int>`**
   - Consumes source, yields only even values
   - Tests stream-of-stream composition

3. **`fn map_double(source: stream<int>): stream<int>`**
   - Consumes source, yields each value * 2
   - Tests transformation stage

4. **`fn take_n(source: stream<int>, n: int): stream<int>`**
   - Yields first n values from source, then stops
   - Tests early termination

5. **`fn accumulate(source: stream<int>): stream<int>`**
   - Running sum: yields cumulative total at each step
   - Tests stateful stream processing

6. **`fn merge_streams(a: stream<int>, b: stream<int>): stream<int>`**
   - Interleaves values from two streams (round-robin)
   - Tests multiple stream consumption

7. **`fn echo_server(): stream<string>`**
   - Uses `inbox` / `send` pattern
   - Receives strings, yields them back uppercased
   - Tests bidirectional communication

### Functions

8. **`fn collect_to_array(source: stream<int>): array<int>`**
   - Drains a stream into an array for verification

9. **`fn main(): none`**
   - Pipeline 1: counter -> filter_even -> map_double -> collect
   - Pipeline 2: counter -> take_n -> accumulate -> collect
   - Pipeline 3: merge two counters -> collect
   - Pipeline 4: echo_server with send/receive
   - Print results for each

## Test Program
`tests/programs/val_stream_pipeline.flow`

Tests:
- counter(1, 5) produces [1, 2, 3, 4, 5]
- filter_even on [1,2,3,4,5] produces [2, 4]
- map_double on [2, 4] produces [4, 8]
- Full pipeline counter(1,10) -> filter_even -> map_double: [4, 8, 12, 16, 20]
- take_n(counter(1,100), 3) produces [1, 2, 3]
- accumulate on [1, 2, 3] produces [1, 3, 6]
- merge of counter(1,3) and counter(10,12): interleaved [1, 10, 2, 11, 3, 12]

## Expected Output (test)
```
counter: [1, 2, 3, 4, 5]
even: [2, 4]
double: [4, 8]
pipeline: [4, 8, 12, 16, 20]
take 3: [1, 2, 3]
accum: [1, 3, 6]
merge: [1, 10, 2, 11, 3, 12]
done
```

## Estimated Size
~140 lines (app), ~90 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| `stream<T>` | every producer function |
| `yield` | producing values |
| `for (x in stream)` | consuming values |
| Stream composition | chaining filter/map/take |
| `send` / `inbox` | bidirectional echo server |
| Early termination | take_n stops consuming |
| `:mut` variables | accumulator state |
| `array.push_int` | collecting stream output |
| Stream as parameter | higher-order stream functions |

## Known Risks
- Stream composition (stream consuming another stream) may not be
  supported if streams are single-consumer and the compiler enforces
  linear ownership at the type level. If so, the filter/map chain
  needs a different pattern.
- `merge_streams` requires polling two streams alternately. If Flow
  doesn't support non-blocking stream reads, round-robin interleaving
  may not be possible. This would be a significant finding.
- `inbox` for `send` is only available inside stream functions in
  specific contexts. Verify the pattern works.
