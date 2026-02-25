# Plan: Job Queue Processor

## Overview

A task queue system where a producer coroutine generates jobs and a worker
coroutine processes them with retry logic. Jobs can fail transiently (retry with
corrected data) or permanently (catch and send to dead-letter queue). A
bidirectional worker coroutine receives jobs via `.send()` and yields
`JobResult` records back. Demonstrates backpressure, coroutine lifetime,
composition chains for job processing, and full try/retry/catch error recovery.

**File:** `apps/jobqueue/jobqueue.flow`

**Usage:**
```
python main.py run apps/jobqueue/jobqueue.flow
```

**Example output:**
```
[JQ] Job queue processor starting...
[JQ] Dispatching: ResizeImage("photo_1.jpg", 800, 600)
[JQ] OK: ResizeImage completed for photo_1.jpg
[JQ] Dispatching: SendEmail("alice@example.com", "Welcome!")
[JQ] RETRY send_email (attempt 1): rate limited, switching to backup server
[JQ] OK: SendEmail delivered to alice@example.com
[JQ] Dispatching: GenerateReport("Q4 Sales")
[JQ] OK: GenerateReport completed for Q4 Sales
[JQ] Dispatching: SendEmail("bad@@invalid", "Test")
[JQ] RETRY send_email (attempt 1): fixing address "bad@@invalid" -> "bad@invalid"
[JQ] RETRY send_email (attempt 2): still failing
[JQ] CATCH: SendEmail permanently failed, moving to dead-letter queue
[JQ] Dispatching: ResizeImage("corrupt.dat", 100, 100)
[JQ] CATCH: ResizeImage permanently failed, moving to dead-letter queue
[JQ] --- Stats ---
[JQ] Completed: 3
[JQ] Dead-lettered: 2
[JQ] Total: 5
```

**Stdlib modules used:** `io`, `string`, `array`, `conv`, `map`, `time`

---

## Gap Discovery Policy

These apps exist to find holes in the language and stdlib. When implementation
hits a point where the natural approach doesn't work — a missing stdlib
function, a type system limitation, an awkward workaround — **stop and report
it** instead of working around it.

Specifically:
1. **Do not silently work around** a missing feature. If you want to write
   `string.char_at(s, i)` and it doesn't exist, that's a finding.
2. **Identify the gap** clearly: what you wanted to do, what's missing, and
   where in the pipeline (stdlib, parser, type system, runtime) the fix belongs.
3. **Propose solutions** — at least two options with tradeoffs. Prefer
   well-engineered fixes (new stdlib function, language feature) over hacks.
4. **Present to the user** before continuing. The user decides whether to
   fix the gap first or defer it.
5. **Document** each gap with a `; GAP: <description>` comment in the app
   source if deferred.

This policy applies to every ticket in this plan.

---

## Conventions

- Tickets are numbered `JQ-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Data Types & Exception Types

---

## Story 1-1: Job Types

**JQ-1-1-1** `[BLOCKER]`
Define the job sum type and result types:
```
type Job =
    | ResizeImage(string, int, int)    ; (filename, width, height)
    | SendEmail(string, string)        ; (recipient, body)
    | GenerateReport(string)           ; (report_name)

type JobOutcome =
    | Completed(string)                ; success_message
    | DeadLettered(string)             ; failure_reason

type JobResult {
    job: Job,
    outcome: JobOutcome
}

type Stats {
    completed: int,
    dead_lettered: int,
    total: int
}
```

**Definition of done:** Types compile and can be constructed.

---

## Story 1-2: Exception Types

**JQ-1-2-1** `[BLOCKER]`
Define transient and permanent failure exceptions:
```
type TransientException fulfills Exception<Job> {
    msg: string,
    payload: Job:mut,
    original_payload: Job,

    constructor from_job(m: string, j: Job): TransientException {
        return TransientException {
            msg: m,
            payload: j,
            original_payload: j
        }
    }

    fn message(self): string { return self.msg }
    fn data(self): Job       { return self.payload }
    fn original(self): Job   { return self.original_payload }
}

type PermanentException fulfills Exception<Job> {
    msg: string,
    payload: Job:mut,
    original_payload: Job,

    constructor from_job(m: string, j: Job): PermanentException {
        return PermanentException {
            msg: m,
            payload: j,
            original_payload: j
        }
    }

    fn message(self): string { return self.msg }
    fn data(self): Job       { return self.payload }
    fn original(self): Job   { return self.original_payload }
}
```

**Definition of done:** Exception types compile, can be thrown and caught.

---

# EPIC 2: Job Producer (Coroutine)

---

## Story 2-1: Job Source

**JQ-2-1-1** `[BLOCKER]`
Implement a coroutine that yields jobs from a simulated batch:
```
fn produce_jobs(): stream<Job> {
    let jobs = array.of(
        ResizeImage("photo_1.jpg", 800, 600),
        SendEmail("alice@example.com", "Welcome!"),
        GenerateReport("Q4 Sales"),
        SendEmail("bad@@invalid", "Test"),
        ResizeImage("corrupt.dat", 100, 100)
    )

    for (j: Job in jobs) {
        yield j
    }
}
```

**JQ-2-1-2**
Spawn with bounded capacity to demonstrate backpressure:
```
let jobs :< produce_jobs() with capacity(2)
```

With `capacity(2)`, the producer can only get 2 jobs ahead of the consumer.
If the consumer is busy retrying a failed job, the producer blocks.

**Definition of done:** Coroutine yields all jobs. Consumer reads and prints
each. Backpressure observable with `capacity(1)`.

---

# EPIC 3: Job Processor

---

## Story 3-1: Per-Type Processing Functions

**JQ-3-1-1** `[BLOCKER]`
Implement processing functions for each job type. These simulate real work
and can throw `TransientException` or `PermanentException`:
```
fn process_resize(filename: string, w: int, h: int): string {
    if string.ends_with(filename, ".dat") {
        throw PermanentException.from_job(
            f"corrupt file: {filename}",
            ResizeImage(filename, w, h)
        )
    }
    ; simulate resize work
    return f"resized {filename} to {conv.to_string(w)}x{conv.to_string(h)}"
}

fn process_email(recipient: string, body: string): string {
    if string.contains(recipient, "@@") {
        throw TransientException.from_job(
            f"invalid address: {recipient}",
            SendEmail(recipient, body)
        )
    }
    ; simulate rate limiting on first attempt (use a static counter)
    ; ... simplified: always succeeds on valid address
    return f"sent to {recipient}"
}

fn process_report(name: string): string {
    ; simulate report generation
    return f"generated report: {name}"
}
```

**JQ-3-1-2**
Implement the dispatcher that routes by job type:
```
fn process_job(job: Job): string {
    match job {
        ResizeImage(file, w, h): process_resize(file, w, h)
        SendEmail(to, body):     process_email(to, body)
        GenerateReport(name):    process_report(name)
    }
}
```

**Definition of done:** `process_job` correctly dispatches to per-type handlers.
Handlers throw appropriate exceptions for bad inputs.

---

## Story 3-2: Job Validation

**JQ-3-2-1**
Implement a validation step in the composition chain:
```
fn:pure validate_job(job: Job): Job {
    match job {
        ResizeImage(_, w, h): {
            if w <= 0 || h <= 0 {
                throw PermanentException.from_job("invalid dimensions", job)
            }
            return job
        }
        SendEmail(to, _): {
            if string.length(to) == 0 {
                throw PermanentException.from_job("empty recipient", job)
            }
            return job
        }
        GenerateReport(name): {
            if string.length(name) == 0 {
                throw PermanentException.from_job("empty report name", job)
            }
            return job
        }
    }
}
```

**Definition of done:** Invalid jobs are rejected before processing.

---

# EPIC 4: Worker (Receivable Coroutine)

---

## Story 4-1: Bidirectional Worker

**JQ-4-1-1** `[BLOCKER]`
Implement a receivable coroutine that receives jobs via `.send()` and yields
`JobResult` records:
```
fn worker(inbox: stream<Job>): stream<JobResult> {
    for (job: Job in inbox) {
        try {
            let msg = job -> validate_job -> process_job
            yield JobResult {
                job: job,
                outcome: Completed(msg)
            }

        } retry process_job (ex: TransientException, attempts: 2) {
            ; correct the job data for retry
            match ex.data {
                SendEmail(to, body): {
                    ; fix double @@ -> single @
                    ex.data = SendEmail(string.replace(to, "@@", "@"), body)
                }
                _: {
                    ; no correction possible for other types
                }
            }

        } catch (ex: TransientException) {
            yield JobResult {
                job: ex.original,
                outcome: DeadLettered(ex.message())
            }

        } catch (ex: PermanentException) {
            yield JobResult {
                job: ex.original,
                outcome: DeadLettered(ex.message())
            }
        }
    }
}
```

Key features:
- **Receivable**: `inbox: stream<Job>` makes this a `.send()`-able coroutine
- **try/retry/catch inside coroutine**: Error handling runs per-job within the
  coroutine thread
- **`ex.data` mutation**: Retry corrects the email address using pattern matching
- **Composition chain**: `job -> validate_job -> process_job`
- **`retry` targets `process_job`**: Only retries the processing step, not
  validation

**JQ-4-1-2**
Wire the worker:
```
let w :< worker() with capacity(4)
; send jobs:
w.send(job)
; read results:
match w.next() {
    some(r): { ... }
    none:    { ... }
}
```

**Definition of done:** Worker processes jobs via bidirectional communication.
Transient failures are retried with corrected data. Permanent failures produce
`DeadLettered` results.

---

# EPIC 5: Dead-Letter Queue

---

## Story 5-1: Dead-Letter Logging

**JQ-5-1-1**
Implement a dead-letter logger that records permanently failed jobs:
```
fn log_dead_letter(result: JobResult): void {
    match result.outcome {
        DeadLettered(reason): {
            io.println(f"[JQ] DEAD-LETTER: {job_description(result.job)} - {reason}")
        }
        _: {}
    }
}

fn:pure job_description(job: Job): string {
    match job {
        ResizeImage(f, w, h):   f"ResizeImage({f}, {conv.to_string(w)}, {conv.to_string(h)})"
        SendEmail(to, _):       f"SendEmail({to})"
        GenerateReport(name):   f"GenerateReport({name})"
    }
}
```

**Definition of done:** Dead-lettered jobs are logged with their failure reason.

---

# EPIC 6: Pipeline Assembly

---

## Story 6-1: Main Pipeline with Fan-out

**JQ-6-1-1** `[BLOCKER]`
Assemble the full pipeline:
```
fn main(): void {
    io.println("[JQ] Job queue processor starting...")

    let jobs :< produce_jobs() with capacity(2)
    let w :< worker() with capacity(4)
    let completed = 0
    let dead_lettered = 0

    ; send all jobs to the worker
    for (job: Job in jobs) {
        io.println(f"[JQ] Dispatching: {job_description(job)}")
        w.send(job)

        ; read result (worker yields one result per job)
        match w.next() {
            some(result): {
                match result.outcome {
                    Completed(msg): {
                        io.println(f"[JQ] OK: {msg}")
                        completed = completed + 1
                    }
                    DeadLettered(reason): {
                        io.println(f"[JQ] DEAD-LETTER: {reason}")
                        dead_lettered = dead_lettered + 1
                    }
                }
            }
            none: {
                io.println("[JQ] Worker unexpectedly closed")
            }
        }
    }

    io.println("[JQ] --- Stats ---")
    io.println(f"[JQ] Completed: {conv.to_string(completed)}")
    io.println(f"[JQ] Dead-lettered: {conv.to_string(dead_lettered)}")
    io.println(f"[JQ] Total: {conv.to_string(completed + dead_lettered)}")
}
```

Key design:
- **Synchronized send/receive**: Send a job, immediately read the result. This
  creates a tight request-response pattern via the bidirectional coroutine.
- **Worker handles try/retry/catch internally**: The main loop just dispatches
  and reads outcomes.
- **Backpressure**: `capacity(2)` on the job producer means the producer won't
  outrun the dispatcher. `capacity(4)` on the worker gives a small buffer.

**JQ-6-1-2**
Add fan-out for results to both console and stats:
```
; Conceptual: result -> (log_result | update_stats)
```

Fan-out may need to be imperative if `.send()` doesn't compose with `|`.
Document any gaps found.

**Definition of done:** Full pipeline runs end-to-end. Jobs are dispatched,
processed (with retries for transient failures), dead-lettered for permanent
failures, and stats are printed.

---

# EPIC 7: Testing

---

## Story 7-1: End-to-End Test

**JQ-7-1-1**
Create `tests/programs/app_jobqueue.flow` — a self-contained test version with
known inputs and deterministic output.

**JQ-7-1-2**
Create `tests/expected_stdout/app_jobqueue.txt` with expected output covering:
- Successful job processing (all three types)
- Transient retry with data correction (email address fix)
- Permanent failure dead-lettering (corrupt file)
- Final stats

**Definition of done:** `make test` passes with the golden file test.

---

## Dependency Map

```
EPIC 1 (Types) → EPIC 2 (Producer) → EPIC 3 (Processor) → EPIC 4 (Worker Coroutine)
                                                                    ↓
EPIC 5 (Dead-Letter) ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
         ↓
EPIC 6 (Pipeline Assembly) → EPIC 7 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **Coroutines (`:< `)** | `produce_jobs` producer, `worker` receivable coroutine |
| **Receivable coroutine (`.send()` / `.next()`)** | Worker receives jobs, yields results |
| **`with capacity(n)`** | Bounded channels on producer and worker |
| **Backpressure** | Producer blocks when dispatch buffer full |
| **`try/retry/catch` inside coroutine** | Worker handles errors per-job internally |
| **`retry` with `ex.data` mutation** | Correcting email address in retry block |
| **`ex.original`** | Preserving original job for dead-letter logging |
| **Multiple `catch` blocks** | Separate catch for transient and permanent |
| **`Exception<T>` interface** | Custom exceptions with `fulfills` |
| **Composition chains (`->`)** | `job -> validate_job -> process_job` |
| **Sum types** | `Job` (3 variants), `JobOutcome` (2 variants) |
| **Recursive `match`** | Dispatching on job type and outcome |
| **`fn:pure`** | `validate_job`, `job_description` |
| **Struct spread** | N/A (sum types use constructors) |
| **`option<T>`** | Coroutine `.next()` returns |
| **`string` module** | `contains`, `ends_with`, `replace` |
| **`conv` module** | Integer-to-string for output |
| **`array` module** | Job batch construction |
| **`io` module** | Status printing |
| **Coroutine lifetime** | Worker runs until inbox exhausted |
| **Exception propagation across threads** | Worker thread exceptions → result yields |
