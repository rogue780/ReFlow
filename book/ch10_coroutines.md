# Chapter 10: Coroutines and Concurrency

Chapter 9 introduced streams: lazy, pull-based sequences that produce one
value at a time on the caller's thread. The consumer drives execution. The
producer suspends on each `yield` and does nothing until the consumer asks
for the next value. This is simple, efficient, and single-threaded.

But sometimes single-threaded is not enough. You have a producer that reads
from the network and a consumer that writes to disk. If both run on the same
thread, the consumer waits while the producer blocks on I/O, and the
producer waits while the consumer flushes buffers. Neither can make progress
while the other is busy.

Flow solves this with one operator: `:<`. It takes any stream-producing
function and runs it on a separate thread, with a bounded channel connecting
the producer to the consumer. The producer pushes values into the channel as
fast as it can. The consumer pulls values out as fast as it can. The channel
handles synchronization. That is the entire concurrency model.

There are no locks to acquire, no mutexes to manage, no condition variables
to signal. You write the same stream functions from Chapter 9 and add two
characters to the call site. The runtime does the rest.

---

## 10.1 From Streams to Coroutines

### 10.1.1 The `:<` Operator

Here is a stream function that counts upward from a starting value:

```flow
fn counter(start: int): stream<int> {
    let i: int:mut = start
    while (true) {
        yield i
        i = i + 1
    }
}
```

Consumed directly, this runs on the caller's thread:

```flow
let s = counter(1)
for (n: int in s) {
    println(f"{n}")       ; 1, 2, 3, ... one at a time, same thread
}
```

Now launch it as a coroutine:

```flow
let gen :< counter(1)
```

That is the only change. The `:<` operator:

1. Creates a bounded channel internally (default capacity 64).
2. Spawns a new thread that runs `counter(1)`.
3. Each `yield` in the producer pushes a value into the channel. If the
   channel is full, the producer blocks until the consumer reads a value.
4. Returns immediately with a **coroutine handle**.

The handle is how you interact with the producer from the consumer side:

```flow
match gen.next() {
    some(v): { println(f"got: {v}") }    ; "got: 1"
    none: {}
}
```

The producer is now running concurrently. While you process value 1, the
producer may have already computed values 2 through 65 and buffered them
in the channel. When you call `.next()` again, the value is already
waiting --- no blocking, no waiting for computation.

A complete program:

```flow
module coroutine_demo
import io (println)

fn counter(start: int): stream<int> {
    let i: int:mut = start
    while (i < start + 5) {
        yield i
        i = i + 1
    }
}

fn main() {
    let gen :< counter(10)

    while (!gen.done()) {
        match gen.next() {
            some(v): { println(f"{v}") }
            none: {}
        }
    }
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

The same `counter` function works both ways: consumed directly as a lazy
stream, or launched as a coroutine with `:<`. The function does not know
or care which mode it is running in. The `yield` statement has the same
semantics either way --- it produces a value and suspends. The difference
is in the plumbing: direct consumption suspends via a state machine on the
caller's thread; coroutine launch pushes into a channel on a separate
thread.

### 10.1.2 Channels and Backpressure

The bounded channel is the key to Flow's concurrency safety. It enforces
two rules:

**Full channel, producer blocks.** If the producer yields faster than the
consumer reads, the channel fills up. The next `yield` blocks the producer
thread until the consumer calls `.next()` and frees a slot. This prevents
unbounded memory growth. A producer that generates a billion values will
never consume more memory than the channel capacity allows.

**Empty channel, consumer blocks.** If the consumer calls `.next()` and
the channel is empty, the consumer thread blocks until the producer yields
a value. This is how the two threads synchronize without explicit
coordination.

The result is automatic backpressure. Fast producers slow down. Slow
consumers speed up (they never wait longer than necessary). The channel
capacity determines how far ahead the producer can run. No tuning is
required for correctness; tuning affects only throughput.

Consider a pipeline where the producer reads lines from a large file and
the consumer parses each line:

```flow
fn read_lines(path: string): stream<string> {
    let handle = file.open(path)
    for (line: string in handle) {
        yield line
    }
}

fn main() {
    let lines :< read_lines("data.csv")

    while (!lines.done()) {
        match lines.next() {
            some(line): {
                let record = parse(line)
                process(record)
            }
            none: {}
        }
    }
}
```

The producer reads ahead by up to 64 lines (the default channel capacity).
If parsing is slower than reading, the producer blocks after filling the
channel. If reading is slower than parsing, the consumer blocks waiting for
the next line. Neither thread wastes CPU spinning, and neither thread
accumulates unbounded data.

### 10.1.3 Channel Capacity with `[N]`

The default channel capacity is 64. You can specify a different capacity
by annotating the stream return type with `[N]`:

```flow
fn tight_producer(): stream<int>[1] {
    ; capacity 1: producer and consumer lock-step
    let i: int:mut = 0
    while (i < 100) {
        yield i
        i = i + 1
    }
}

fn big_buffer(): stream<int>[256] {
    ; capacity 256: producer can run far ahead
    let i: int:mut = 0
    while (i < 1000) {
        yield i
        i = i + 1
    }
}
```

A capacity of 1 creates tight synchronization: the producer can advance
exactly one step ahead of the consumer. After yielding a value, the
producer blocks until the consumer reads it. This is useful when each value
is expensive to produce and you want to minimize wasted work.

A larger capacity lets the producer run ahead, smoothing out latency
variations. If the producer occasionally stalls (waiting for a network
response, say), a large buffer keeps the consumer fed from previously
buffered values. If the consumer occasionally stalls (writing a batch to
disk), a large buffer keeps the producer from blocking.

The `[N]` annotation is a runtime hint. It does not affect the type. For
type-checking purposes, `stream<int>[1]` and `stream<int>[256]` are both
`stream<int>`. You can pass a `stream<int>[128]` function to any context
that expects `stream<int>`. The capacity is a performance knob, not a type
constraint.

`N` can be any integer expression:

```flow
fn producer(buf_size: int): stream<int>[buf_size] {
    yield 42
}
```

When `[N]` is omitted, the default capacity of 64 is used.

---

## 10.2 The Coroutine Handle

When you write `let gen :< some_function(args)`, the variable `gen` is a
coroutine handle. It exposes up to four methods, depending on how the
coroutine function is defined.

### 10.2.1 `.next()` and `.done()`

`.next()` returns `option<T>`, where `T` is the yield type of the stream
function. It blocks the calling thread if the channel is empty and the
producer is still running. It returns `none` only when both conditions
hold: the producer has finished (returned or fallen off the end of the
function) **and** all buffered values have been consumed.

`.done()` returns `bool`. It is `true` when the producer has finished and
the channel has been fully drained. While buffered values remain, `.done()`
returns `false` even if the producer thread has already exited.

The idiomatic consumption loop:

```flow
let gen :< producer()

while (!gen.done()) {
    match gen.next() {
        some(v): { process(v) }
        none: {}
    }
}
```

The `none` arm in the match is necessary because `.done()` and `.next()`
are not atomic. Between checking `.done()` (which returned `false` because
buffered values existed) and calling `.next()`, the last value may have
been consumed by another path. In practice, for single-consumer coroutines
the `none` arm rarely fires, but it must be present for the match to be
exhaustive.

You can also consume without `.done()`, using `.next()` alone:

```flow
let gen :< counter(1)

let a = gen.next()    ; some(1)
let b = gen.next()    ; some(2)
let c = gen.next()    ; some(3)
```

This is useful when you know how many values to expect, or when you want
to pull values on demand rather than draining the entire stream.

### 10.2.2 `.poll()` for Non-Blocking Access

`.poll()` is the non-blocking counterpart of `.next()`. It checks the
channel without waiting. If a value is available, it returns `some(v)`. If
the channel is empty --- whether because the producer has not yielded yet
or because the consumer has caught up --- it returns `none` immediately.

```flow
let gen :< slow_producer()

match gen.poll() {
    some(v): { println(f"ready: {v}") }
    none: { println("nothing yet") }
}
```

`.poll()` does **not** distinguish between "nothing available yet" and
"producer finished." To check whether the producer is done, use `.done()`.
A `none` from `.poll()` means "no value right now"; a `true` from
`.done()` means "no values ever again."

`.poll()` is essential for event loops that monitor multiple coroutines
without blocking on any single one:

```flow
fn main() {
    let a :< producer_a()
    let b :< producer_b()

    while (!a.done() || !b.done()) {
        match a.poll() {
            some(v): { handle_a(v) }
            none: {}
        }
        match b.poll() {
            some(v): { handle_b(v) }
            none: {}
        }
    }
}
```

This loop checks both coroutines on each iteration. It processes whichever
has a value ready, skips whichever does not, and exits when both are done.
No thread blocks. No value waits longer than one loop iteration.

---

## 10.3 Receivable Coroutines

The coroutines shown so far are one-directional: the producer yields values
and the consumer reads them. But some problems require two-way
communication. A worker needs to receive commands. An accumulator needs to
receive numbers. A server needs to receive requests.

Flow handles this with **receivable coroutines**: coroutine functions whose
first parameter is a `stream<S>`. That parameter is the **inbox**.

### 10.3.1 The Inbox Parameter

A receivable coroutine has a specific signature: its first parameter is a
stream, and its return type is also a stream. The first parameter is the
inbox (values flowing *into* the coroutine); the return type is the outbox
(values flowing *out*):

```flow
fn echo(inbox: stream<string>): stream<string> {
    for (msg: string in inbox) {
        yield "echo: " + msg
    }
}
```

The inbox is consumed inside the function just like any other stream ---
with `for-in`, with `.next()`, with any stream operation. The difference
is in how it gets created. When you launch a receivable coroutine, the
runtime creates the inbox channel automatically:

```flow
let w :< echo()
```

Notice that `echo` takes one parameter (`inbox: stream<string>`), but the
call site passes zero arguments. The inbox is implicit. The runtime creates
a bounded channel for it and wires it to the coroutine handle's `.send()`
method.

If the function has additional parameters after the inbox, you pass them
normally:

```flow
fn processor(inbox: stream<string>, prefix: string): stream<string> {
    for (msg: string in inbox) {
        yield prefix + msg
    }
}

let p :< processor(">>")    ; "inbox" is auto-created; ">>" maps to prefix
```

### 10.3.2 Sending with `.send()`

The `.send()` method pushes a value into the coroutine's inbox:

```flow
let w :< echo()
w.send("hello")
w.send("world")
```

The type of `.send()` is derived from the inbox parameter. If the first
parameter is `stream<string>`, then `.send()` accepts `string`. Passing
the wrong type is a compile error.

Like the output channel, the inbox channel is bounded. If the inbox is
full, `.send()` blocks the calling thread until the coroutine reads a
value. Backpressure works in both directions.

### 10.3.3 Bidirectional Communication

Combining `.send()` and `.next()` gives you a request-response pattern:

```flow
module echo_demo
import io (println)

fn echo(inbox: stream<string>): stream<string> {
    for (msg: string in inbox) {
        yield "echo: " + msg
    }
}

fn main() {
    let w :< echo()

    w.send("hello")
    match w.next() {
        some(v): { println(v) }    ; "echo: hello"
        none: {}
    }

    w.send("world")
    match w.next() {
        some(v): { println(v) }    ; "echo: world"
        none: {}
    }
}
```

The consumer sends a value, then reads the response. The coroutine
receives a value, transforms it, and yields the result. The two threads
alternate, communicating through their respective channels.

The types are independent. The inbox type and the outbox type can be
completely different:

```flow
fn accumulator(inbox: stream<int>): stream<string> {
    let total: int:mut = 0
    for (n: int in inbox) {
        total = total + n
        yield f"running total: {total}"
    }
}
```

Here `.send()` accepts `int` and `.next()` returns `option<string>`. The
coroutine maintains state (the running total) that persists across
messages.

A summary of the type relationships:

| Method | Type | Direction |
|--------|------|-----------|
| `.send(val)` | `S` from first param `stream<S>` | consumer to producer |
| `.next()` | `option<Y>` from return `stream<Y>` | producer to consumer |
| `yield val` | `Y` | producer emits |
| inbox consumption | `S` | producer receives |

If the first parameter is **not** `stream<S>`, the coroutine is
**send-less**. Calling `.send()` on a send-less coroutine handle is a
compile error.

---

## 10.4 Coroutine Wiring

Individual coroutines are useful. Chains of coroutines are powerful. When
one coroutine's output feeds directly into another coroutine's input, you
have a concurrent pipeline where every stage runs on its own thread.

### 10.4.1 Direct Wiring: Coroutine to Coroutine

If you have a producer coroutine and a receivable coroutine, you can wire
them together by passing the producer's handle as the first argument to
the receivable coroutine:

```flow
module wiring_demo
import io (println)

fn producer(start: int): stream<int> {
    let i: int:mut = start
    while (i < start + 3) {
        yield i
        i = i + 1
    }
}

fn doubler(inbox: stream<int>): stream<int> {
    for (val: int in inbox) {
        yield val * 2
    }
}

fn main() {
    let p :< producer(10)
    let d :< doubler(p)        ; wired: producer's output feeds doubler's input

    while (!d.done()) {
        match d.next() {
            some(v): { println(f"doubled: {v}") }
            none: {}
        }
    }
}
```

Output:

```
doubled: 20
doubled: 22
doubled: 24
```

What happens here: `producer(10)` runs on thread A, yielding 10, 11, 12
into its output channel. `doubler(p)` runs on thread B, reading from that
same channel, doubling each value, and yielding the results into its own
output channel. The main thread reads from `d`'s output channel.

Three threads, two channels, zero explicit synchronization. The bounded
channels handle all coordination.

You can wire as many stages as you want:

```flow
fn tripler(inbox: stream<int>): stream<int> {
    for (val: int in inbox) {
        yield val * 3
    }
}

fn main() {
    let p :< producer(1)
    let d :< doubler(p)
    let t :< tripler(d)      ; producer -> doubler -> tripler

    while (!t.done()) {
        match t.next() {
            some(v): { println(f"{v}") }
            none: {}
        }
    }
}
```

Each stage runs on its own thread. The producer generates values, the
doubler transforms them, the tripler transforms them again. Four threads
total (including main), three channels. The data flows through the pipeline
concurrently, with each stage processing a different element at the same
time.

---

## 10.5 Pipelines and Worker Pools

Direct wiring works, but the syntax gets repetitive when you have many
stages. Flow provides a pipeline syntax that expresses the same thing more
concisely.

### 10.5.1 The Pipeline Syntax (`->`)

Instead of wiring stages manually:

```flow
let p :< producer()
let d :< doubler(p)
let a :< adder(d)
```

You can write:

```flow
let result :< producer() -> doubler() -> adder()
```

This is syntactic sugar. The compiler desugars it into the same sequence
of coroutine launches and direct wiring. Each stage runs on its own thread.
The output of each stage feeds the input of the next.

A complete example:

```flow
module pipeline_demo
import io (println)

fn producer(): stream<int> {
    let i: int:mut = 1
    while (i <= 4) {
        yield i
        i = i + 1
    }
}

fn doubler(inbox: stream<int>): stream<int> {
    for (val: int in inbox) {
        yield val * 2
    }
}

fn adder(inbox: stream<int>): stream<int> {
    for (val: int in inbox) {
        yield val + 100
    }
}

fn main() {
    let result :< producer() -> doubler() -> adder()

    ; produces: 1*2+100=102, 2*2+100=104, 3*2+100=106, 4*2+100=108
    while (!result.done()) {
        match result.next() {
            some(v): { println(f"{v}") }
            none: {}
        }
    }
}
```

Output:

```
102
104
106
108
```

The pipeline reads left to right: produce integers, double them, add 100.
Three stages, three threads, two channels. The consumer (main) reads from
the final stage.

The first stage in a pipeline is the source. It does not need to be
receivable --- it just needs to return `stream<T>`. Every subsequent stage
must be receivable: its first parameter must be `stream<T>` where `T`
matches the yield type of the preceding stage.

If the types do not align, the compiler rejects the pipeline. If
`producer()` yields `stream<int>` and the next stage expects
`stream<string>`, you get a type error at compile time.

### 10.5.2 Elastic Pools with `* N`

Sometimes one stage in a pipeline is the bottleneck. The producer generates
values fast, the consumer drains them fast, but the middle stage --- say,
a CPU-intensive transformation --- cannot keep up. The solution is to run
multiple workers for that stage.

The `* N` syntax creates an elastic pool:

```flow
let result :< producer() -> transform() * 5 -> consumer()
```

This creates five `transform` workers. The runtime distributes incoming
values from the producer across the five workers. Each worker runs on its
own thread. Their outputs are merged into a single channel feeding the
next stage.

A concrete example:

```flow
module pool_demo
import io (println)

fn producer(): stream<int> {
    let i: int:mut = 1
    while (i <= 6) {
        yield i
        i = i + 1
    }
}

fn squarer(inbox: stream<int>): stream<int> {
    for (val: int in inbox) {
        yield val * val
    }
}

fn main() {
    let result :< producer() -> squarer() * 3

    ; 3 squarer workers process the 6 values
    let count: int:mut = 0
    while (!result.done()) {
        match result.next() {
            some(v): { count = count + 1 }
            none: {}
        }
    }
    println(f"processed: {count}")    ; "processed: 6"
}
```

With three workers, up to three values can be squared simultaneously. The
total number of results is the same (6), but the wall-clock time for
CPU-bound work is roughly divided by the number of workers.

**Order is not preserved.** When multiple workers process values
concurrently, results arrive in whatever order the workers finish. If
worker 2 finishes squaring its value before worker 1, worker 2's result
appears first in the output channel. If your pipeline requires ordered
output, either use a single worker (no `* N`) or add a reordering stage
downstream.

`N` can be any integer expression:

```flow
let workers = 8
let result :< source() -> heavy_compute() * workers -> sink()
```

You can apply `* N` to any stage except the first (which is the source and
is always a single producer). Multiple stages can have pools:

```flow
let result :< source() -> parse() * 4 -> validate() * 2 -> write()
```

This creates four parsers and two validators, with a single source and a
single writer. Seven threads total (4 + 2 + 1 source, plus the writer if
it is a receivable stage consumed by main).

---

## 10.6 Exception Propagation Across Threads

Exceptions in coroutines follow a simple rule: if the producer throws, the
exception is captured and re-thrown on the consumer's thread when
`.next()` is called.

```flow
module exception_demo
import io (println)

type ParseError fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor from_raw(m: string, p: string): ParseError {
        return ParseError {
            msg: m,
            payload: p,
            original_payload: p
        }
    }

    fn message(self): string  { return self.msg }
    fn data(self): string     { return self.payload }
    fn original(self): string { return self.original_payload }
}

fn failing_producer(): stream<int> {
    yield 1
    yield 2
    throw ParseError.from_raw("bad data", "raw input")
}

fn main() {
    let gen :< failing_producer()

    match gen.next() {
        some(v): { println(f"got: {v}") }    ; "got: 1"
        none: {}
    }

    match gen.next() {
        some(v): { println(f"got: {v}") }    ; "got: 2"
        none: {}
    }

    ; The next call re-throws the exception on this thread
    try {
        match gen.next() {
            some(v): { println(f"got: {v}") }
            none: { println("done") }
        }
    } catch (ex: ParseError) {
        println(f"caught: {ex.message()}")    ; "caught: bad data"
    }
}
```

The first two `.next()` calls return the buffered values normally. The
third call encounters the exception. It does not return `none` --- it
throws `ParseError` on the consumer's thread, exactly as if the consumer
had called the failing code directly.

This preserves the illusion of sequential execution for error handling.
You can wrap coroutine consumption in `try`/`catch`/`retry` using the same
patterns from Chapter 7. The exception carries all its data across the
thread boundary: `message`, `data`, and `original` are all available on the
consumer side.

### 10.6.1 Exceptions in Pipelines

In a multi-stage pipeline, an exception propagates stage by stage. If the
middle stage throws, the next stage sees the exception when it calls
`.next()` on the middle stage's output. If that stage does not catch it, the
exception surfaces when the consumer reads from the final stage.

The practical effect: wrap the final `.next()` call in a `try` block and
you catch exceptions from any stage in the pipeline. You do not need to
instrument each stage individually.

---

## 10.7 Coroutine Lifetime

A coroutine's producer thread runs until one of three things happens:

1. **The function returns.** The stream is closed normally. Remaining
   buffered values can still be read by the consumer. After the last
   buffered value is consumed, `.next()` returns `none` and `.done()`
   returns `true`.

2. **The stream is exhausted.** A finite loop in the producer completes.
   Same behavior as returning.

3. **An exception is thrown.** The producer thread terminates. The
   exception is captured and delivered on the next `.next()` call.

When the coroutine handle goes out of scope and is released, the runtime
closes both the output channel and the inbox channel (if the coroutine is
receivable), then joins the producer thread. If the producer is blocked on
a full channel or waiting on an empty inbox, the close unblocks it.

This means you do not need to manually shut down coroutines. When the
handle leaves scope, cleanup happens automatically. A receivable coroutine
that is blocked in `for (msg in inbox)` will unblock and exit when the
inbox channel closes.

### 10.7.1 Ownership Across Threads

Values passed to a coroutine follow Flow's ownership rules (Chapter 8):

- **Immutable data** is shared via reference count increment. No copying,
  no locking. Both the spawning scope and the coroutine can read the data
  freely.

- **Mutable data** is moved. The spawning scope loses access. The
  coroutine owns it exclusively.

- **Yielded values** transfer ownership through the channel to the
  consumer. Value types (int, float, bool, byte) are implicitly copied.
  Reference types transfer their reference count.

- **Sent values** (via `.send()`) transfer ownership through the inbox
  channel to the producer, following the same rules.

```flow
let config = load_config()              ; immutable
let a :< process(config, chunk_1)       ; config is shared, not copied
let b :< process(config, chunk_2)       ; same config, refcount incremented
; both coroutines read config concurrently --- safe, no locks
```

---

## 10.8 Streams vs. Coroutines

This table summarizes the differences. Both use `yield`, both produce
`stream<T>`. The execution model is what changes.

| | `stream<T>` (direct) | `let c :< fn()` (coroutine) |
|---|---|---|
| **Execution** | Lazy, pull-based, same thread | Eager, push-based, separate thread |
| **Yield** | Suspends via state machine, resumes on next pull | Pushes into channel, blocks if full |
| **Backpressure** | Inherent (consumer drives) | Channel capacity (producer blocks when full) |
| **Bidirectional** | No | Yes, if first param is `stream<S>` |
| **Use when** | Simple transformations, composition chains | Concurrent I/O, parallel computation, bidirectional communication |

The key insight: **the same function works in both modes.** A function
that returns `stream<T>` can be consumed directly (lazy, same thread) or
launched with `:<` (eager, new thread). You do not write separate
implementations for sequential and concurrent use. You write stream
functions, and the call site decides the execution model.

This is why coroutines are not a separate feature bolted onto the
language. They are streams with a different execution strategy. Everything
you learned about streams in Chapter 9 --- `yield`, `return`, `for-in`
consumption, single-consumer rule --- applies unchanged. The `:<` operator
adds threading, channels, and bidirectional communication. Nothing else
changes.

---

## 10.9 Patterns for Concurrent Programs

### 10.9.1 Producer-Consumer

The most common pattern: one coroutine produces data, another consumes it.

```flow
module producer_consumer
import io (println)

fn produce_data(): stream<int> {
    let i: int:mut = 0
    while (i < 10) {
        yield i * i
        i = i + 1
    }
}

fn main() {
    let data :< produce_data()
    let sum: int:mut = 0

    while (!data.done()) {
        match data.next() {
            some(v): { sum = sum + v }
            none: {}
        }
    }

    println(f"sum of squares: {sum}")    ; "sum of squares: 285"
}
```

The producer and consumer run on separate threads. The producer computes
squares while the consumer accumulates them. The channel synchronizes
access. No shared mutable state, no locks.

### 10.9.2 Fan-Out Workers

When you need to process a stream of tasks concurrently, use a pipeline
with a worker pool:

```flow
module fanout_demo
import io (println)

fn tasks(): stream<int> {
    let i: int:mut = 1
    while (i <= 20) {
        yield i
        i = i + 1
    }
}

fn heavy_work(inbox: stream<int>): stream<int> {
    for (task: int in inbox) {
        ; simulate expensive computation
        let result: int:mut = 0
        let j: int:mut = 0
        while (j < task * 1000) {
            result = result + j
            j = j + 1
        }
        yield result
    }
}

fn main() {
    ; 4 workers process 20 tasks concurrently
    let results :< tasks() -> heavy_work() * 4

    let count: int:mut = 0
    while (!results.done()) {
        match results.next() {
            some(v): { count = count + 1 }
            none: {}
        }
    }
    println(f"completed: {count} tasks")
}
```

Four threads run `heavy_work` simultaneously. The runtime distributes
tasks from the source across the workers. Results arrive as they complete,
not necessarily in order.

### 10.9.3 Event Loops with `.poll()`

When you need to monitor multiple coroutines without blocking:

```flow
module event_loop
import io (println)

fn sensor_a(): stream<int> {
    let i: int:mut = 0
    while (i < 5) {
        yield i * 10
        i = i + 1
    }
}

fn sensor_b(): stream<int> {
    let i: int:mut = 0
    while (i < 5) {
        yield i * 100
        i = i + 1
    }
}

fn main() {
    let a :< sensor_a()
    let b :< sensor_b()

    while (!a.done() || !b.done()) {
        if (!a.done()) {
            match a.poll() {
                some(v): { println(f"sensor A: {v}") }
                none: {}
            }
        }
        if (!b.done()) {
            match b.poll() {
                some(v): { println(f"sensor B: {v}") }
                none: {}
            }
        }
    }
}
```

The main thread polls both sensors on each iteration. It processes
whichever has data ready and skips whichever does not. This is the
foundation of event-driven programming in Flow: non-blocking reads from
multiple concurrent sources.

### 10.9.4 Request-Response Server

Receivable coroutines make natural servers:

```flow
module server_demo
import io (println)

fn command_handler(inbox: stream<string>): stream<string> {
    for (cmd: string in inbox) {
        if (cmd == "ping") {
            yield "pong"
        } else if (cmd == "time") {
            yield "1234567890"
        } else {
            yield f"unknown command: {cmd}"
        }
    }
}

fn main() {
    let server :< command_handler()

    server.send("ping")
    match server.next() {
        some(v): { println(v) }    ; "pong"
        none: {}
    }

    server.send("time")
    match server.next() {
        some(v): { println(v) }    ; "1234567890"
        none: {}
    }

    server.send("quit")
    match server.next() {
        some(v): { println(v) }    ; "unknown command: quit"
        none: {}
    }
}
```

The server coroutine runs on its own thread, processing commands as they
arrive. The main thread sends commands and reads responses. The bounded
channels ensure neither side races ahead of the other.

---

## 10.10 Summary

Flow's concurrency model has exactly one primitive: the `:<` operator.
Everything else --- channels, backpressure, bidirectional communication,
pipelines, worker pools --- is built from that foundation.

The key ideas:

- **`:<` launches a stream function on a new thread.** The producer pushes
  into a bounded channel; the consumer pulls from it. Backpressure is
  automatic.

- **Channel capacity is tunable with `[N]`.** The default is 64. A
  capacity of 1 creates lock-step synchronization. A larger capacity
  smooths latency.

- **`.next()` blocks, `.poll()` does not.** Use `.next()` for sequential
  consumption, `.poll()` for event loops.

- **Receivable coroutines have an inbox.** If the first parameter is
  `stream<S>`, the runtime creates an inbox channel. `.send()` pushes
  into it. The coroutine reads from it with `for-in`.

- **Direct wiring connects coroutines.** Pass a coroutine handle to a
  receivable coroutine's launch to feed one into the other.

- **Pipeline syntax (`->`) chains stages.** Each stage runs on its own
  thread. `* N` creates worker pools for a stage.

- **Exceptions propagate across threads.** If the producer throws, the
  consumer sees the exception on the next `.next()` call.

- **Coroutines clean up automatically.** When the handle leaves scope, the
  runtime closes channels and joins the thread.

The same stream function works in both modes --- lazy or coroutine --- with
no changes to its implementation. The call site decides. Write stream
functions; deploy them however makes sense.

---

## Exercises

**1.** Write a producer that generates the first `n` Fibonacci numbers, where
`n` is a parameter. Launch it as a coroutine and consume the first 20
values, printing each one.

```flow
module fib_exercise
import io (println)

fn fibonacci(n: int): stream<int> {
    let a: int:mut = 0
    let b: int:mut = 1
    let count: int:mut = 0
    while (count < n) {
        yield a
        let temp = a + b
        a = b
        b = temp
        count = count + 1
    }
}

fn main() {
    let fibs :< fibonacci(20)

    while (!fibs.done()) {
        match fibs.next() {
            some(v): { println(f"{v}") }
            none: {}
        }
    }
}
```

**2.** Write a receivable coroutine that acts as an accumulator. It receives
integers via `.send()` and yields the running total after each one.

```flow
module accumulator_exercise
import io (println)

fn accumulator(inbox: stream<int>): stream<int> {
    let total: int:mut = 0
    for (n: int in inbox) {
        total = total + n
        yield total
    }
}

fn main() {
    let acc :< accumulator()

    acc.send(10)
    match acc.next() {
        some(v): { println(f"total: {v}") }    ; "total: 10"
        none: {}
    }

    acc.send(25)
    match acc.next() {
        some(v): { println(f"total: {v}") }    ; "total: 35"
        none: {}
    }

    acc.send(5)
    match acc.next() {
        some(v): { println(f"total: {v}") }    ; "total: 40"
        none: {}
    }
}
```

**3.** Wire three coroutines in a pipeline using both direct wiring and
pipeline syntax. The stages: generate integers 1 through 10, double each
value, then add 1 to each value. Verify both approaches produce the same
results.

```flow
module pipeline_exercise
import io (println)

fn generate(): stream<int> {
    let i: int:mut = 1
    while (i <= 10) {
        yield i
        i = i + 1
    }
}

fn doubler(inbox: stream<int>): stream<int> {
    for (v: int in inbox) {
        yield v * 2
    }
}

fn increment(inbox: stream<int>): stream<int> {
    for (v: int in inbox) {
        yield v + 1
    }
}

fn main() {
    ; Pipeline syntax
    let result :< generate() -> doubler() -> increment()

    while (!result.done()) {
        match result.next() {
            some(v): { println(f"{v}") }    ; 3, 5, 7, 9, 11, 13, 15, 17, 19, 21
            none: {}
        }
    }
}
```

**4.** Build a worker pool that squares numbers concurrently. Generate 100
numbers, distribute them across 4 workers, and count the total results.

```flow
module pool_exercise
import io (println)

fn numbers(): stream<int> {
    let i: int:mut = 1
    while (i <= 100) {
        yield i
        i = i + 1
    }
}

fn square(inbox: stream<int>): stream<int> {
    for (n: int in inbox) {
        yield n * n
    }
}

fn main() {
    let results :< numbers() -> square() * 4

    let count: int:mut = 0
    let total: int:mut = 0
    while (!results.done()) {
        match results.next() {
            some(v): {
                count = count + 1
                total = total + v
            }
            none: {}
        }
    }
    println(f"processed {count} values, sum = {total}")
}
```

**5. (Challenge)** Build a concurrent prime sieve using coroutine wiring.
The classic Sieve of Eratosthenes can be expressed as a chain of filters:
the first stage generates integers starting from 2, each subsequent stage
filters out multiples of a discovered prime.

```flow
module sieve_exercise
import io (println)

; Generate integers from start upward
fn integers(start: int): stream<int> {
    let i: int:mut = start
    while (i <= 100) {
        yield i
        i = i + 1
    }
}

; Filter: pass through only values not divisible by prime
fn sieve_filter(inbox: stream<int>, prime: int): stream<int> {
    for (n: int in inbox) {
        if (n % prime != 0) {
            yield n
        }
    }
}

fn main() {
    ; Start with integers from 2
    let source :< integers(2)

    ; Collect primes up to 100
    ; Each discovered prime creates a new filter stage
    let primes: array<int>:mut = []
    let current :< integers(2)

    ; Read the first value: it is prime
    ; Wire a filter, read the next prime, wire another filter, etc.
    ;
    ; For a fixed sieve, manually wire the first few stages:
    let stage1 :< integers(2)

    match stage1.next() {
        some(p): {
            println(f"prime: {p}")    ; 2
            let stage2 :< sieve_filter(stage1, p)

            match stage2.next() {
                some(p2): {
                    println(f"prime: {p2}")    ; 3
                    let stage3 :< sieve_filter(stage2, p2)

                    match stage3.next() {
                        some(p3): {
                            println(f"prime: {p3}")    ; 5
                            let stage4 :< sieve_filter(stage3, p3)

                            ; Continue reading primes from the filtered stream
                            while (!stage4.done()) {
                                match stage4.next() {
                                    some(v): { println(f"prime: {v}") }
                                    none: {}
                                }
                            }
                        }
                        none: {}
                    }
                }
                none: {}
            }
        }
        none: {}
    }
}
```

This last exercise illustrates the power of coroutine wiring: each filter
stage runs on its own thread, and the data flows through a chain of
concurrent filters. The nesting is a consequence of Flow's scoping rules
--- each new coroutine handle must remain in scope while the downstream
stages use it. In a real program, you would likely use an array of handles
or a recursive function to manage the chain dynamically.
