# Chapter 9: Streams

Most programs deal with sequences. A log file is a sequence of lines. A
network connection is a sequence of packets. A database query is a sequence
of rows. The question is how you represent that sequence in memory.

One option is to materialize it: read every line into an array, collect every
packet into a buffer, fetch every row into a list. This works for small data.
It fails for large data, because you run out of memory. And it fails for
infinite data, because there is no array large enough.

The other option is to process one element at a time. Read a line, process
it, discard it, read the next. This is what streams do. A `stream<T>` is a
lazy, pull-based sequence that produces values one at a time. Nothing runs
until a consumer asks for the next value. Only one value exists in memory at
any moment. The producer suspends after each `yield` and resumes when the
consumer pulls again.

This chapter covers how to write stream-producing functions, how to consume
streams, how to transform them with helpers like `map`, `filter`, and
`reduce`, how to materialize them into buffers when you must, and how to
use streams in composition chains. By the end you will be able to build
data-processing pipelines that handle datasets larger than memory, process
infinite sequences, and compose cleanly from small, reusable parts.

---

## 9.1 What Streams Are

### 9.1.1 Lazy, Pull-Based Evaluation

A stream-producing function looks like any other function, except its
return type is `stream<T>` and its body uses `yield` instead of (or in
addition to) `return`:

```flow
fn range(n: int): stream<int> {
    let i: int:mut = 0
    while (i < n) {
        yield i
        i++
    }
}
```

Calling `range(1000000)` does not produce a million integers. It produces
a stream --- a suspended computation that, when asked, will yield `0`, then
`1`, then `2`, and so on up to `999999`. Each value is produced on demand.
Between yields, the function is suspended: its local variables (`i`, in
this case) are preserved, and execution resumes exactly where it left off
when the consumer pulls the next value.

This is the fundamental property of streams: **nothing runs until a
consumer asks for values.** The producer is driven entirely by the
consumer's demand. If the consumer stops after 10 values, the producer
never computes the 11th. If the consumer never starts, the producer never
runs at all.

The consequence is that only one value exists in transit at any moment.
A stream of a million integers uses the same amount of memory as a stream
of ten. The cost is proportional to what you consume, not what the producer
could produce.

This pull-based model gives you **backpressure** for free. Backpressure
means the producer cannot outrun the consumer. If the consumer is slow,
the producer waits. If the consumer is fast, the producer runs as fast as
it can. There is no unbounded buffer growing between them, no dropped
messages, no out-of-memory crash from a fast producer overwhelming a slow
consumer. The rate of production is always governed by the rate of
consumption.

In single-threaded streams (the default), backpressure is trivially
enforced: the producer literally cannot run until the consumer resumes it.
Chapter 10 covers threaded streams via coroutines, where backpressure is
enforced through bounded channels.

### 9.1.2 Single-Consumer Semantics

A stream can be consumed exactly once by exactly one consumer. This is not
a limitation --- it is a design invariant that enables the ownership model
to work. When a value is yielded, ownership transfers from the producer to
the consumer. There is no second consumer to fight over that ownership.

```flow
let s = range(10)
for (n: int in s) {
    println(f"{n}")
}

// s is now exhausted. It cannot be iterated again.
```

Attempting to consume a stream twice is a compile error where the compiler
can detect it:

```flow
let s = range(10)
let a = s -> count  // s consumed here
let b = s -> count  // compile error: s already consumed
```

If you need the same data twice, materialize the stream into a buffer
(Section 9.5), copy the buffer, and drain each copy independently:

```flow
let s = range(10)
let buf: buffer<int>:mut = buffer.collect(s)
let a = (@buf).drain() -> count  // copy of buffer, drained
let b = buf.drain() -> count  // original buffer, drained
```

The `@` operator copies the buffer. Each copy drains independently. The
stream itself is consumed only once --- by `buffer.collect`.

The single-consumer rule may feel restrictive at first. In practice, it
eliminates an entire class of bugs: race conditions on shared iterators,
double-consumption of network streams, and the subtle state corruption
that happens when two consumers advance the same cursor. When you need
sharing, you buffer explicitly. The intent is visible in the code.

### 9.1.3 Single-Threaded by Default

Streams are single-threaded. The producer and consumer run on the same
thread, taking turns. When the consumer calls `.next()` or enters a `for`
loop iteration, execution transfers to the producer. When the producer
yields, execution transfers back to the consumer. They interleave but
never overlap.

This means a stream function cannot run concurrently with its consumer.
There is no parallelism. The producer is suspended while the consumer
processes the value, and the consumer is suspended while the producer
computes the next value.

For many workloads, this is exactly right. A log parser does not need
concurrency; it needs to read lines and process them. Single-threaded
streams have no synchronization overhead, no locks, no atomic operations.
They are the fastest way to process sequential data.

When you do need the producer and consumer to run concurrently --- for
example, when the producer does network I/O and the consumer does CPU
work --- you use the `:<` coroutine operator (Chapter 10). This runs the
producer on a separate thread with a bounded channel between them. The
stream interface does not change; only the scheduling model does.

---

## 9.2 Writing Stream Functions

### 9.2.1 The `yield` Statement

`yield` is the core of every stream function. It emits a value to the
consumer and suspends execution. When the consumer pulls the next value,
execution resumes at the statement after `yield`:

```flow
fn countdown(from: int): stream<int> {
    let i: int:mut = from
    while (i > 0) {
        yield i
        i--
    }
}
```

`countdown(3)` yields `3`, then `2`, then `1`, then the while loop
condition fails and the function returns normally, closing the stream.

The function's local state is fully preserved between yields. Any mutable
variables, loop counters, or partially-constructed values remain intact.
The function resumes exactly where it suspended, as if no time had passed.

A stream function can yield infinitely:

```flow
fn fibonacci(): stream<int> {
    let a: int:mut = 0
    let b: int:mut = 1
    while (true) {
        yield a
        let next = a + b
        a = b
        b = next
    }
}
```

This function never terminates on its own. It yields Fibonacci numbers
forever. The consumer decides when to stop. This is safe because the
producer only runs when the consumer pulls. An infinite stream that nobody
consumes uses no resources.

```flow
// Print the first 10 Fibonacci numbers
for (n: int in fibonacci().take(10)) {
    println(f"{n}")
}
```

Output:

```
0
1
1
2
3
5
8
13
21
34
```

The `.take(10)` helper (Section 9.4) wraps the stream and stops pulling
after 10 values. The infinite `fibonacci` function never knows it was
cut short.

State is maintained between yields, which means you can build complex
stateful producers. Here is a function that yields running averages:

```flow
fn running_average(s: stream<float>): stream<float> {
    let sum: float:mut = 0.0
    let count: int:mut = 0
    for (val: float in s) {
        sum += val
        count++
        yield sum / cast<float>(count)
    }
}
```

Each yield emits the current average. The `sum` and `count` accumulate
across pulls. The consumer sees a stream of progressively refined
averages.

### 9.2.2 Early Termination with `return`

A `return` inside a stream function closes the stream without emitting a
value. The consumer sees the stream as exhausted:

```flow
fn read_until_blank(lines: stream<string>): stream<string> {
    for (line: string in lines) {
        if (line == "") {
            return
        }
        yield line
    }
}
```

If the input stream contains `"hello"`, `"world"`, `""`, `"ignored"`, the
output stream yields `"hello"` and `"world"`, then stops. The `"ignored"`
line is never read.

`return` is also useful for guard clauses at the top of a stream function:

```flow
fn positive_only(n: int): stream<int> {
    if (n <= 0) { return }
    let i: int:mut = 1
    while (i <= n) {
        yield i
        i++
    }
}
```

`positive_only(0)` produces an empty stream. `positive_only(3)` yields
`1`, `2`, `3`.

### 9.2.3 Cleanup with Finally

Stream functions often acquire resources --- file handles, network
connections, database cursors --- that must be released when the stream
closes. Function-level `finally` handles this:

```flow
fn read_lines(path: string): stream<string> {
    let handle = file.open(path)
    for (line: string in handle) {
        yield line
    }
} finally {
    handle.close()
}
```

The `finally` block runs when the stream closes, regardless of how it
closes:

- The producer runs to completion (exhausts the for loop).
- The producer hits a `return` and terminates early.
- The consumer stops pulling (breaks out of its loop, calls `.take(n)`,
  or simply goes out of scope).

This last case is critical. When a consumer abandons a stream, the
producer's `finally` block still runs. The file handle is closed even if
the consumer only read three lines of a million-line file:

```flow
fn main() {
    // Read only the header line
    let lines = read_lines("data.csv")
    match lines.next() {
        some(header): println(f"Header: {header}"),
        none: println("Empty file")
    }
    // lines goes out of scope here.
    // The finally block in read_lines runs: handle.close()
}
```

Without `finally`, the file handle would leak. This is Flow's mechanism
for deterministic resource cleanup in streaming contexts. Every stream
function that opens a resource should close it in a `finally` block.

Multiple cleanup actions go in the same `finally`:

```flow
fn transfer_data(src: string, dst: string): stream<string> {
    let input = file.open(src)
    let output = file.open(dst)
    for (line: string in input) {
        file.write(output, line)
        yield line
    }
} finally {
    file.close(input)
    file.close(output)
}
```

---

## 9.3 Consuming Streams

A stream is inert until consumed. There are two ways to consume one:
`for` loops and manual iteration with `.next()`.

### 9.3.1 `for` Loops

The `for` loop is the standard way to consume a stream. It pulls one
value at a time and binds it to the loop variable:

```flow
for (n: int in range(5)) {
    println(f"{n}")
}
```

Output:

```
0
1
2
3
4
```

The loop runs until the stream is exhausted. Each iteration pulls the
next value, binds it, executes the body, then pulls again. The type
annotation on the loop variable (`: int`) is required.

`for` works identically on arrays and streams. This is by design ---
you can switch between them without changing the consuming code:

```flow
let data: array<int> = [10, 20, 30]

// Consuming an array
for (n: int in data) {
    println(f"{n}")
}

// Consuming a stream that yields the same values
for (n: int in range(3).map(\(x: int => (x + 1) * 10))) {
    println(f"{n}")
}
```

You can use `break` and `continue` inside a `for` loop over a stream:

```flow
fn find_first_negative(s: stream<int>): int {
    for (n: int in s) {
        if (n >= 0) { continue }
        return n
    }
    return 0  // no negative found
}
```

When you `break` out of a `for` loop that consumes a stream, the stream
is abandoned. If the stream function has a `finally` block, it runs.

A `for` loop over a stream also supports `finally`, which runs after
the stream is exhausted or after a `break`:

```flow
let total: int:mut = 0
for (n: int in range(100)) {
    total += n
    if (total > 500) { break }
} finally {
    println(f"processed until total exceeded 500: {total}")
}
```

The `finally` block on the `for` loop is separate from any `finally` on
the stream function. Both run: the loop's `finally` runs first (because
it is the inner scope), then the stream function's `finally` runs (as
the stream is abandoned).

### 9.3.2 Manual Iteration with `.next()`

For fine-grained control, call `.next()` on a stream directly. It returns
`option<T>` --- `some(value)` if a value is available, `none` if the
stream is exhausted:

```flow
let fib = fibonacci()

match fib.next() {
    some(v): println(f"first: {v}"),
    none: println("empty")
}

match fib.next() {
    some(v): println(f"second: {v}"),
    none: println("empty")
}
```

Output:

```
first: 0
second: 1
```

Each `.next()` call advances the stream by one position. The stream
remembers where it left off. This is useful when you need to treat
the first element differently, peek at values before committing to a
loop, or interleave consumption with other logic:

```flow
fn parse_header_and_rows(lines: stream<string>): stream<record> {
    // First line is the header
    let header_opt = lines.next()
    match header_opt {
        none: return,
        some(header): {
            let columns = parse_header(header)
            // Remaining lines are data rows
            for (line: string in lines) {
                yield parse_row(columns, line)
            }
        }
    }
}
```

The function calls `.next()` once to get the header, then switches to a
`for` loop for the remaining rows. Both operations consume the same
stream. The header is pulled manually; the rows are pulled by the loop.

---

## 9.4 Stream Helpers

Stream helpers are methods called on stream values. They transform,
filter, and fold streams without requiring you to write explicit loops.
Most return a new stream (they are lazy), so you can chain them. A few
--- like `reduce` --- consume the stream and return a single value.

### 9.4.1 `map`, `filter`, `reduce`

These are the three workhorses of stream processing. If you have used
functional programming in any language, you know them already. The
difference in Flow is that they are lazy: `map` and `filter` return
streams, not arrays.

**`map`** transforms each element by applying a function:

```flow
let squares = range(5).map(\(x: int => x * x))
// yields: 0, 1, 4, 9, 16
```

The function receives one element and returns one element. The types
can differ --- `map` is how you change the element type of a stream:

```flow
let labels = range(5).map(\(x: int => f"item {x}"))
// yields: "item 0", "item 1", "item 2", "item 3", "item 4"
// type: stream<string>
```

`map` is lazy. Calling `.map(...)` on a stream returns a new stream
immediately, without consuming any elements. The transformation function
runs only when the consumer pulls a value from the mapped stream.

**`filter`** keeps elements that satisfy a predicate and discards the rest:

```flow
let evens = range(10).filter(\(x: int => x % 2 == 0))
// yields: 0, 2, 4, 6, 8
```

The predicate receives one element and returns `bool`. Elements where the
predicate returns `true` pass through; elements where it returns `false`
are silently discarded. The output stream has the same element type as
the input but potentially fewer elements.

Like `map`, `filter` is lazy. It does not scan the entire stream upfront.
When the consumer pulls, `filter` pulls from the upstream stream
repeatedly until it finds an element that passes the predicate, then
yields that element.

**`reduce`** folds the stream to a single value. It takes an initial
accumulator and a combining function that receives the current accumulator
and the next element, and returns the new accumulator:

```flow
let sum = range(10).reduce(0, \(acc: int, x: int => acc + x))
// sum is 45
```

The initial value (`0`) is the starting accumulator. For each element,
the combining function produces a new accumulator. When the stream is
exhausted, the final accumulator is returned.

`reduce` is a **terminal operation** --- it consumes the entire stream
and returns a single value, not a stream. This is an important
distinction. After `reduce`, there is no stream left. The result is
a plain value.

Common uses of `reduce`:

```flow
// Sum
let sum = range(10).reduce(0, \(acc: int, x: int => acc + x))

// Product
let product = range(1, 6).reduce(1, \(acc: int, x: int => acc * x))

// String concatenation
let csv = names.reduce("", \(acc: string, name: string =>
    if (acc == "") { name } else { f"{acc},{name}" }
))

// Find maximum
let max = range(10).reduce(0, \(acc: int, x: int =>
    if (x > acc) { x } else { acc }
))
```

These three compose naturally:

```flow
// Sum of squares of even numbers from 0 to 9
let result = range(10)
    .filter(\(x: int => x % 2 == 0))
    .map(\(x: int => x * x))
    .reduce(0, \(acc: int, x: int => acc + x))

println(f"{result}")  // 120
```

The chain reads top to bottom: start with 0..9, keep the evens, square
them, sum the squares. Each step is lazy except `reduce`, which drives
the entire chain. When `reduce` pulls from `map`, `map` pulls from
`filter`, `filter` pulls from `range`. Values flow one at a time through
the entire chain. There is no intermediate array of evens, no
intermediate array of squares. Just one value traveling through the
pipeline per pull.

This is worth emphasizing. In a language with eager evaluation, the
equivalent code would create an array of evens, then an array of squares,
then sum the squares --- three passes over the data and two temporary
arrays. Here, there is one pass and zero temporary collections. The
laziness is not an optimization hint; it is the default execution model.

### 9.4.2 `take`, `skip`, `zip`

**`take(n)`** yields the first `n` elements and then closes the stream:

```flow
// First 5 Fibonacci numbers
for (n: int in fibonacci().take(5)) {
    println(f"{n}")
}
```

Output:

```
0
1
1
2
3
```

`take` is how you make infinite streams safe. `fibonacci()` yields
forever, but `fibonacci().take(5)` yields exactly 5 values and stops.

**`skip(n)`** discards the first `n` elements and yields the rest:

```flow
// Skip the first 10, then take the next 5
for (n: int in range(100).skip(10).take(5)) {
    println(f"{n}")
}
```

Output:

```
10
11
12
13
14
```

`skip` and `take` combine to select a window. `.skip(10).take(5)` is the
equivalent of "elements 10 through 14" in a zero-indexed sequence.

**`zip`** pairs elements from two streams:

```flow
let numbers = range(5)
let squares = range(5).map(\(x: int => x * x))

for (pair: (int, int) in numbers.zip(squares)) {
    match pair {
        (a, b): println(f"{a} -> {b}")
    }
}
```

Output:

```
0 -> 0
1 -> 1
2 -> 4
3 -> 9
4 -> 16
```

`zip` yields pairs until either stream is exhausted. If one stream is
shorter, the remaining elements of the longer stream are discarded:

```flow
// range(3) exhausts first, so only 3 pairs are produced
let short_zip = range(3).zip(range(100))
for (pair: (int, int) in short_zip) {
    match pair {
        (a, b): println(f"{a}, {b}")
    }
}
```

Output:

```
0, 0
1, 1
2, 2
```

A common use of `zip` is to pair indices with values:

```flow
fn enumerate(s: stream<string>): stream<(int, string)> {
    let indices = naturals()  // 0, 1, 2, ...
    return indices.zip(s)
}

for (pair: (int, string) in enumerate(read_lines("data.txt"))) {
    match pair {
        (i, line): println(f"line {i}: {line}")
    }
}
```

### 9.4.3 `chunks`, `group_by`, `flatten`

These helpers address common data-processing patterns that require
grouping or restructuring elements.

**`chunks(n)`** groups elements into fixed-size buffers:

```flow
// Process data in batches of 3
for (batch: buffer<int> in range(10).chunks(3)) {
    println(f"batch of {batch.len()} items")
}
```

Output:

```
batch of 3 items
batch of 3 items
batch of 3 items
batch of 1 items
```

The last chunk may be smaller than `n` if the stream's length is not
evenly divisible. Each chunk is a `buffer<T>`, which supports random
access, sorting, and other operations (Section 9.5).

Chunking is useful for batch processing: insert rows into a database
1000 at a time, send network packets in groups, or parallelize work
across fixed-size batches.

**`group_by`** groups elements by a key function. It returns a stream
of `(key, buffer)` pairs:

```flow
type Sale { category: string, amount: int }

fn sales_by_category(sales: stream<Sale>): stream<(string, buffer<Sale>)> {
    return sales.group_by(\(s: Sale => s.category))
}
```

Each pair contains the key and a buffer of all elements with that key.
This is useful for aggregation:

```flow
fn category_totals(src: string): stream<(string, int)> =
    src -> read_sales
        -> stream.group_by(\(s: Sale => s.category))
        -> for(group: (string, buffer<Sale>)) {
            let (cat, buf) = group
            let total: int:mut = 0
            for (s: Sale in buf.drain()) {
                total += s.amount
            }
            yield (cat, total)
        }
```

Note that `group_by` must buffer all elements for each group. For large
datasets with many distinct keys, this can use significant memory. If
the data is already sorted by the grouping key, consider processing
groups manually with a state-tracking loop instead.

**`flatten`** collapses nested streams (or arrays) by one level:

```flow
fn all_words(files: stream<string>): stream<string> {
    return files
        .map(\(path: string => read_lines(path)))
        .flatten()
}
```

If `files` yields three file paths, and each `read_lines` produces a
stream of lines, the intermediate result is `stream<stream<string>>`.
`flatten()` collapses it to `stream<string>`, yielding all lines from
all files in sequence.

`flatten` also works when the inner type is `array<T>`:

```flow
fn all_items(groups: stream<array<int>>): stream<int> {
    return groups.flatten()
}
```

---

## 9.5 Buffers: Materializing Streams

Streams are powerful because they are lazy. But some operations require
the full dataset: sorting needs all elements before it can produce output;
random access needs the data in memory; reversing a sequence requires
knowing the last element first. For these cases, Flow provides `buffer<T>`.

A `buffer<T>` is a mutable, in-memory container. It is the bridge between
the lazy world of streams and the eager world of random-access collections.

### 9.5.1 Collecting into a Buffer

`buffer.collect` consumes an entire stream and materializes it:

```flow
let buf: buffer<int>:mut = buffer.collect(range(10))
println(f"collected {buf.len()} items")
```

Output:

```
collected 10 items
```

The stream is fully consumed. The buffer contains all 10 values. You can
now access them by index, sort them, slice them, or drain them back into
a stream.

You can also build a buffer incrementally:

```flow
let buf: buffer<string>:mut = buffer.new()
buf.push("first")
buf.push("second")
buf.push("third")
println(f"{buf.len()} items")  // 3
```

`buffer.new()` creates an empty buffer. `push` appends one element.
Buffers grow dynamically. If a buffer exceeds available memory, it throws
`BufferOverflowError`.

For known sizes, `buffer.with_capacity` avoids incremental reallocation:

```flow
let buf: buffer<int>:mut = buffer.with_capacity(1000)
```

### 9.5.2 Random Access

`buf.get(i)` returns `option<T>`:

```flow
let buf: buffer<int>:mut = buffer.collect(range(5))

match buf.get(2) {
    some(v): println(f"element 2: {v}"),  // element 2: 2
    none: println("out of bounds")
}

match buf.get(99) {
    some(v): println(f"element 99: {v}"),
    none: println("out of bounds")  // out of bounds
}
```

There is no unchecked indexing. Every access returns an option. This is
the same pattern as array access (Chapter 2).

### 9.5.3 Sorting, Slicing, Reversing

Buffers support in-place mutation:

```flow
let buf: buffer<int>:mut = buffer.collect(range(5))

// Reverse in place
buf.reverse()
// buf is now [4, 3, 2, 1, 0]

// Sort with a comparison function
buf.sort_by(\(a: int, b: int => a - b))
// buf is now [0, 1, 2, 3, 4]
```

The `sort_by` comparator returns a negative integer if the first argument
should sort before the second, zero if they are equal, and a positive
integer if the first should sort after the second. This is the standard
three-way comparison convention.

`slice` extracts a sub-buffer (half-open interval):

```flow
let buf: buffer<int>:mut = buffer.collect(range(10))
let middle: buffer<int>:mut = buf.slice(3, 7)
// middle contains [3, 4, 5, 6]
println(f"{middle.len()}")  // 4
```

### 9.5.4 Draining Back to a Stream

`drain()` converts a buffer back into a stream, consuming the buffer:

```flow
fn sort_descending(s: stream<int>): stream<int> {
    let buf: buffer<int>:mut = buffer.collect(s)
    buf.sort_by(\(a: int, b: int => b - a))
    return buf.drain()
}
```

After `drain()`, the buffer is consumed. You cannot use it again. This
enforces the single-ownership principle: the data exists in the buffer or
in the stream, not both.

The pattern of collect-transform-drain is the standard way to insert an
eager operation into a lazy pipeline:

```flow
fn sort_by_date(events: stream<Event>): stream<Event> {
    let buf: buffer<Event>:mut = buffer.collect(events)
    buf.sort_by(\(a: Event, b: Event => a.timestamp - b.timestamp))
    return buf.drain()
}
```

From the outside, `sort_by_date` looks like a `stream -> stream`
function. The buffering is an implementation detail. Callers compose it
like any other stream function:

```flow
fn pipeline(src: string): stream<Event> =
    src -> read_events -> sort_by_date -> filter(is_important)
```

### 9.5.5 When to Buffer

Buffer when you must. Prefer streams when you can. The decision tree is
simple:

- **Need random access?** Buffer.
- **Need sorting?** Buffer.
- **Need the full dataset before producing output?** Buffer.
- **Processing elements one at a time?** Stream.
- **Unknown or infinite input?** Stream (with `take` or `filter` to bound it).

The cost of buffering is memory proportional to the dataset size. The
cost of streaming is constant memory. For a million-row CSV file, streaming
processes one row at a time. Buffering loads all million rows into memory.
The right choice depends on the operation, not a blanket preference.

---

## 9.6 Streams in Composition Chains

Streams and composition are designed to work together. Chapter 4 introduced
the `->` operator for chaining functions. With streams, composition becomes
a full data-processing pipeline model.

### 9.6.1 Auto-Mapping

When a stream flows into a function that expects a single element (not a
stream), the composition chain automatically maps that function over each
element:

```flow
fn:pure double(x: int): int = x * 2

// double expects int, not stream<int>
// composition auto-maps it over the stream
let result = range(5) -> double
// result is a stream<int> yielding: 0, 2, 4, 6, 8
```

This is a key design decision. It means every eager function is
automatically usable in a streaming pipeline. You do not need to write a
stream-aware version of `double`. The composition operator handles the
adaptation.

When a function expects a stream, it receives the stream directly:

```flow
fn count(s: stream<int>): int {
    let n: int:mut = 0
    for (_: int in s) { n++ }
    return n
}

// count expects stream<int>, receives it directly
let n = range(100) -> count
// n is 100
```

The compiler distinguishes these cases by the parameter type. If the
downstream function takes `T`, auto-map. If it takes `stream<T>`, pass
directly. This distinction is resolved at compile time; there is no
runtime dispatch.

To make this concrete, consider a pipeline with both kinds of functions:

```flow
fn:pure parse_int(s: string): int = conv.string_to_int(s) ?? 0
fn sum(s: stream<int>): int = s.reduce(0, \(a: int, b: int => a + b))

let result = "numbers.txt" -> read_lines -> parse_int -> sum
```

Here `read_lines` returns `stream<string>`. `parse_int` takes `string`
(not `stream<string>`), so it is auto-mapped: applied to each element,
producing `stream<int>`. `sum` takes `stream<int>`, so it receives the
stream directly and consumes it. The result is a single `int`.

Without auto-mapping, you would need to write a stream-aware version of
every function you want to use in a pipeline. Auto-mapping eliminates
that boilerplate. A function that works on one element automatically
works on a stream of elements.

### 9.6.2 Multi-Stage Pipelines

Composition chains can mix stream-producing, stream-transforming, and
stream-consuming functions freely:

```flow
fn parse(line: string): record { ... }
fn is_valid(r: record): bool { ... }
fn count(s: stream<record>): int { ... }

fn pipeline(src: string): int =
    src -> read_lines -> parse -> filter(is_valid) -> count
```

Reading this chain left to right:

1. `src` is a `string`.
2. `read_lines` takes a `string` and returns `stream<string>`.
3. `parse` takes a `string` (not a stream). Auto-mapped: applied to each line, producing `stream<record>`.
4. `filter(is_valid)` takes a `stream<record>` and returns `stream<record>`.
5. `count` takes a `stream<record>` and returns `int`.

The result is an `int`. The entire pipeline is lazy up to `count`, which
is the terminal operation that drives the chain. When `count` pulls from
`filter`, `filter` pulls from `parse`, `parse` pulls from `read_lines`,
and `read_lines` reads the next line from the file. One line flows through
the entire pipeline per pull. Memory usage is constant regardless of file
size.

### 9.6.3 Composable `for`

A `for` block can appear inside a composition chain. It consumes the
incoming stream, iterates, and its `yield` statements produce an output
stream:

```flow
fn process(data: array<int>): stream<string> =
    data -> for(x: int) {
        let doubled = x * 2
        yield f"val: {doubled}"
    } -> filter(\(s: string => s != "val: 4"))
```

The `for` block acts as an inline stream transformation. It receives
each element, performs computation, and yields results into the next
stage. This is useful for transformations that are too complex for a
simple `map` lambda but not worth extracting into a named function.

Without a body, `for` decomposes a collection into a stream:

```flow
fn process(data: array<int>): stream<int> =
    data -> for(x: int) -> double -> square
```

Here `for(x: int)` converts the array into a stream of individual
elements, which then flow through `double` and `square` via auto-mapping.

### 9.6.4 Building Real Pipelines

Here is a complete example that ties together stream functions, helpers,
composition, and buffers:

```flow
module log_analyzer

import io (println)
import file (read_lines)
import string (contains, split)

type LogEntry { level: string, message: string }

fn parse_log(line: string): LogEntry {
    let parts = split(line, " ")
    let level = parts.get(0) ?? "UNKNOWN"
    let message = parts.get(1) ?? ""
    return LogEntry { level: level, message: message }
}

fn:pure is_error(entry: LogEntry): bool = entry.level == "ERROR"

fn count(s: stream<LogEntry>): int {
    let n: int:mut = 0
    for (_: LogEntry in s) { n++ }
    return n
}

fn main() {
    let error_count = "server.log"
        -> read_lines
        -> parse_log
        -> filter(is_error)
        -> count

    println(f"Errors: {error_count}")
}
```

The pipeline reads lines from a file, parses each line into a log entry,
filters for errors, and counts them. The file could be gigabytes.
Memory usage is constant. Each line flows through the pipeline and is
discarded before the next is read.

Notice how the pipeline mixes function types naturally:

- `read_lines` is a stream-producing function (`string -> stream<string>`).
- `parse_log` is an eager function (`string -> LogEntry`), auto-mapped over the stream.
- `filter(is_error)` is a stream-transforming function (`stream<LogEntry> -> stream<LogEntry>`).
- `count` is a stream-consuming function (`stream<LogEntry> -> int`).

Each function was written independently with no awareness of the others.
Composition wires them together. Auto-mapping bridges the eager/stream
boundary. The result reads like a description of what the pipeline does,
not how it does it.

This is the payoff of Flow's stream design. Small, focused functions ---
many of them pure --- compose into pipelines that process data of
arbitrary size with constant memory. The pipeline is the program.

---

## 9.7 Ownership and Streams

Streams interact with Flow's ownership system in specific ways that are
worth understanding explicitly.

### 9.7.1 Yielded Values Transfer Ownership

When a stream function yields a value, ownership of that value transfers
to the consumer. For value types (int, float, bool, byte), this is a
trivial copy. For heap-allocated types (strings, structs, arrays),
ownership moves:

```flow
fn generate_names(): stream<string> {
    let name = "Alice"
    yield name
    // name is still accessible here because strings are immutable
    // and shared via reference counting

    let data: array<int>:mut = [1, 2, 3]
    yield_data(data)
    // for mutable data, ownership would transfer to the consumer
}
```

If you need to yield a value and continue using it, use the copy operator
`@`:

```flow
fn repeat_value(val: string, n: int): stream<string> {
    let i: int:mut = 0
    while (i < n) {
        yield @val  // copy yielded, function retains val
        i++
    }
}
```

For immutable data, `@` is cheap (it increments a reference count). For
mutable data, `@` performs a deep copy. The distinction matters when
streaming large mutable structures.

### 9.7.2 Stream Parameters and Lifetime

When a stream-producing function takes parameters, those parameters stay
owned by the function for the stream's entire lifetime. The function is
a suspended frame holding its captured variables:

```flow
fn lines_of(content: string): stream<string> {
    let parts = string.split(content, "\n")
    for (line: string in parts) {
        yield line
    }
}
```

The `content` parameter is owned by `lines_of` from the moment the
stream is created until it is fully consumed or abandoned. The caller
cannot use `content` while the stream is active. Ownership reverts only
when the stream closes.

This means you cannot do this:

```flow
let text = "hello\nworld"
let s = lines_of(text)
// text is borrowed by lines_of for the stream's lifetime
println(text)  // ok: text is immutable, shared via refcount
```

For immutable data, this is transparent --- immutable values are shared
freely. For mutable data, the parameter is moved into the stream
function, and the caller loses access until the stream is fully consumed.

### 9.7.3 The Single-Consumer Rule Revisited

The single-consumer rule is not just about preventing double-iteration.
It is a consequence of ownership. A stream is an active computation with
state. If two consumers could pull from the same stream, they would
contend over which one gets each value. With ownership-based semantics,
there is no safe way to share that state without locks or copying.

The pattern for sharing data across multiple consumers is always the same:
materialize, copy, drain:

```flow
let data = expensive_computation()
let buf: buffer<Result>:mut = buffer.collect(data)
let analysis_a = (@buf).drain() -> analyze_for_trends
let analysis_b = buf.drain() -> analyze_for_outliers
```

Each consumer gets its own stream from its own buffer. No sharing, no
contention, no surprises.

---

## 9.8 Putting It Together

Here is a larger example that demonstrates most of the stream features
from this chapter. It reads a stream of integers, computes statistics in
a single pass, and uses buffering only where necessary:

```flow
module stream_demo

import io (println)

fn range(start: int, end: int): stream<int> {
    let i: int:mut = start
    while (i < end) {
        yield i
        i++
    }
}

fn:pure is_even(x: int): bool = x % 2 == 0
fn:pure square(x: int): int = x * x

fn main() {
    // Chain of helpers: filter, map, take
    let result = range(0, 100)
        .filter(\(x: int => is_even(x)))
        .map(\(x: int => square(x)))
        .take(10)
        .reduce(0, \(acc: int, x: int => acc + x))

    println(f"Sum of first 10 even squares: {result}")
    // 0 + 4 + 16 + 36 + 64 + 100 + 144 + 196 + 256 + 324 = 1140

    // Manual iteration
    let fib = fibonacci()
    let first = fib.next() ?? 0
    let second = fib.next() ?? 0
    println(f"First two Fibonacci: {first}, {second}")

    // Buffering for sort
    let sorted = range(0, 10)
        .map(\(x: int => 9 - x))
    let buf: buffer<int>:mut = buffer.collect(sorted)
    buf.sort_by(\(a: int, b: int => a - b))
    for (n: int in buf.drain()) {
        println(f"{n}")
    }

    // Zip two streams
    let names: array<string> = ["Alice", "Bob", "Carol"]
    let scores = range(90, 93)
    for (pair: (string, int) in names.zip(scores)) {
        match pair {
            (name, score): println(f"{name}: {score}")
        }
    }
}

fn fibonacci(): stream<int> {
    let a: int:mut = 0
    let b: int:mut = 1
    while (true) {
        yield a
        let next = a + b
        a = b
        b = next
    }
}
```

---

## 9.9 Summary

Streams are lazy, pull-based sequences. The producer runs only when the
consumer asks for the next value. Only one value is in transit at a time.
Memory usage is constant regardless of the sequence length.

A stream function returns `stream<T>` and uses `yield` to emit values.
`return` closes the stream. `finally` ensures cleanup runs regardless of
how the stream terminates.

Streams are single-consumer. A stream is consumed once by one consumer.
To reuse data, materialize it into a buffer with `buffer.collect`, copy
it, and drain the copies.

Stream helpers --- `map`, `filter`, `reduce`, `take`, `skip`, `zip`,
`chunks`, `group_by`, `flatten` --- compose lazily (except `reduce`,
which is terminal). They chain naturally: `.filter(...).map(...).take(n)`.

Buffers are mutable containers for materializing stream data. They support
random access, sorting, slicing, and reversing. `drain()` converts a
buffer back into a stream.

In composition chains, streams integrate seamlessly. Functions expecting
a single element are auto-mapped over the stream. Functions expecting
a stream receive it directly. Composable `for` blocks provide inline
stream transformations.

Chapter 10 introduces coroutines: the `:<` operator that runs a stream
producer on a separate thread, adding concurrency to the pull-based model
without changing the stream interface.

---

## Exercises

**1. Infinite Primes**

Write a function `fn primes(): stream<int>` that yields prime numbers
in ascending order. Use a trial division approach: for each candidate
number starting at 2, test divisibility against all previously found
primes up to the square root of the candidate. Use a mutable buffer
to accumulate known primes.

Test it by printing the first 20 primes:

```flow
for (p: int in primes().take(20)) {
    println(f"{p}")
}
```

Expected: 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53,
59, 61, 67, 71.

**2. CSV Row Stream**

Write a function `fn csv_rows(path: string): stream<array<string>>` that
reads a file line by line, skips the header (first line), splits each
subsequent line on commas, and yields each row as an array of strings.
Use `.next()` to consume the header and a `for` loop for the remaining
lines. Add a `finally` block to close the file handle.

**3. Sliding Window**

Write a function `fn window(s: stream<int>, n: int): stream<buffer<int>>`
that yields sliding windows of size `n` over a stream. For input
`[1, 2, 3, 4, 5]` with `n = 3`, yield buffers containing `[1, 2, 3]`,
`[2, 3, 4]`, `[3, 4, 5]`.

Hint: maintain a buffer and use `push` and `slice`.

**4. Batch Sort**

Write a function that sorts a large stream by processing it in chunks.
Use `.chunks(100)` to break the stream into batches, sort each batch
with `sort_by`, and drain each sorted batch into the output stream. The
result is a stream of locally-sorted batches (not globally sorted --- a
full external sort is a harder problem).

```flow
fn batch_sort(s: stream<int>): stream<int> {
    for (chunk: buffer<int> in s.chunks(100)) {
        chunk.sort_by(\(a: int, b: int => a - b))
        for (n: int in chunk.drain()) {
            yield n
        }
    }
}
```

Test it with `range(0, 1000).map(\(x: int => 999 - x))` and verify
that each batch of 100 is sorted.

**5. Pipeline: Filter, Transform, Count**

Build a pipeline that reads lines from a file, filters for lines
containing a search term, transforms each matching line to uppercase,
and counts the results. Write it two ways: once with explicit stream
functions and `for` loops, and once with composition and stream helpers.
Verify both produce the same count.

```flow
// Version 1: explicit
fn search_count_v1(path: string, term: string): int {
    let n: int:mut = 0
    for (line: string in read_lines(path)) {
        if (string.contains(line, term)) {
            n++
        }
    }
    return n
}

// Version 2: composition
fn search_count_v2(path: string, term: string): int =
    path -> read_lines
         -> filter(\(line: string => string.contains(line, term)))
         -> count
```
