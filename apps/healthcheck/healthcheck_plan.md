# Plan: Concurrent URL Health Checker

## Overview

A concurrent URL health checker that spawns coroutine workers to probe a list
of endpoints. Demonstrates the split between `result<T, E>` for expected HTTP
outcomes (like 404s) and exceptions for unexpected network failures that warrant
retry with corrective logic. A receivable coroutine aggregates results via
bidirectional communication.

**File:** `apps/healthcheck/healthcheck.flow`

**Usage:**
```
python main.py run apps/healthcheck/healthcheck.flow
```

**Example output:**
```
[HC] Starting health check for 5 targets...
[HC] Checking: http://localhost:9000/api/health
[HC] OK: http://localhost:9000/api/health (200, 12ms)
[HC] Checking: http://localhost:9000/api/users
[HC] OK: http://localhost:9000/api/users (200, 23ms)
[HC] Checking: http://badhost:1234/missing
[HC] RETRY connect (attempt 1): increasing timeout 1000 -> 2000
[HC] RETRY connect (attempt 2): increasing timeout 2000 -> 4000
[HC] FAIL: http://badhost:1234/missing (ConnectionException after 3 attempts)
[HC] Checking: http://localhost:9000/api/nothing
[HC] WARN: http://localhost:9000/api/nothing (404 - expected failure, not an exception)
[HC] Checking: http://localhost:9000/api/slow
[HC] RETRY connect (attempt 1): increasing timeout 1000 -> 2000
[HC] OK: http://localhost:9000/api/slow (200, 1823ms)
[HC] --- Report ---
[HC] Passed: 3
[HC] Failed: 1
[HC] Warnings: 1
[HC] Total: 5
```

**Stdlib modules used:** `net`, `io`, `string`, `array`, `conv`, `map`, `time`

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

- Tickets are numbered `HC-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Data Types & Exception Types

---

## Story 1-1: Health Check Types

**HC-1-1-1** `[BLOCKER]`
Define the core data types:
```
type HealthTarget {
    url: string,
    expected_status: int,
    timeout_ms: int
}

type CheckStatus =
    | Pass(int, int)       ; (status_code, latency_ms)
    | Fail(string)         ; error_message
    | Warn(int, string)    ; (status_code, reason)

type CheckResult {
    target: HealthTarget,
    status: CheckStatus
}

type Report {
    passed: int,
    failed: int,
    warnings: int,
    total: int
}
```

`CheckStatus` is a sum type: `Pass` for successful checks, `Fail` for
permanent failures, `Warn` for expected-but-notable outcomes (e.g., 404).

**Definition of done:** Types compile and can be constructed in a test function.

---

## Story 1-2: Exception Types

**HC-1-2-1** `[BLOCKER]`
Define exception types for network failures:
```
type ConnectionException fulfills Exception<HealthTarget> {
    msg: string,
    payload: HealthTarget:mut,
    original_payload: HealthTarget,

    constructor from_target(m: string, t: HealthTarget): ConnectionException {
        return ConnectionException {
            msg: m,
            payload: t,
            original_payload: t
        }
    }

    fn message(self): string         { return self.msg }
    fn data(self): HealthTarget      { return self.payload }
    fn original(self): HealthTarget  { return self.original_payload }
}

type TimeoutException fulfills Exception<HealthTarget> {
    msg: string,
    payload: HealthTarget:mut,
    original_payload: HealthTarget,

    constructor from_target(m: string, t: HealthTarget): TimeoutException {
        return TimeoutException {
            msg: m,
            payload: t,
            original_payload: t
        }
    }

    fn message(self): string         { return self.msg }
    fn data(self): HealthTarget      { return self.payload }
    fn original(self): HealthTarget  { return self.original_payload }
}
```

The `payload` is `:mut` so retry blocks can increase the timeout in `ex.data`.

**Definition of done:** Exception types compile. Can be thrown and caught.

---

# EPIC 2: URL Producer (Coroutine)

---

## Story 2-1: Target Producer

**HC-2-1-1** `[BLOCKER]`
Implement a coroutine that yields `HealthTarget` records from a config list:
```
fn produce_targets(): stream<HealthTarget> {
    let targets = array.of(
        HealthTarget { url: "http://localhost:9000/api/health", expected_status: 200, timeout_ms: 1000 },
        HealthTarget { url: "http://localhost:9000/api/users",  expected_status: 200, timeout_ms: 1000 },
        HealthTarget { url: "http://badhost:1234/missing",      expected_status: 200, timeout_ms: 1000 },
        HealthTarget { url: "http://localhost:9000/api/nothing", expected_status: 404, timeout_ms: 1000 },
        HealthTarget { url: "http://localhost:9000/api/slow",    expected_status: 200, timeout_ms: 1000 }
    )

    for (t: HealthTarget in targets) {
        yield t
    }
}
```

**HC-2-1-2**
Spawn as a coroutine:
```
let targets :< produce_targets() with capacity(2)
```

**Definition of done:** Coroutine yields all targets. Consumer reads and prints
each URL.

---

# EPIC 3: Health Checker

---

## Story 3-1: Connection & Check Function

**HC-3-1-1** `[BLOCKER]`
Implement `check_target` that connects to a URL and returns a `result<CheckResult, string>`.
Throws `ConnectionException` for network failures, `TimeoutException` for timeouts.
Returns `result` for expected HTTP outcomes:
```
fn check_target(target: HealthTarget): result<CheckResult, string> {
    ; parse URL to extract host and port
    let host = parse_host(target.url)
    let port = parse_port(target.url)
    let path = parse_path(target.url)

    let start = time.now_ms()

    ; connect — throws ConnectionException on failure
    let sock = net.connect(host, port)
    match sock {
        some(s): {
            net.set_timeout(s, target.timeout_ms)

            ; send HTTP GET
            let request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\n\r\n"
            let wrote = net.write_string(s, request)
            if !wrote {
                net.close(s)
                throw ConnectionException.from_target("write failed", target)
            }

            ; read response
            let response = net.read(s, 4096)
            net.close(s)

            let elapsed = time.now_ms() - start

            match response {
                some(data): {
                    let status_code = parse_http_status(data)
                    if status_code == target.expected_status {
                        return ok(CheckResult {
                            target: target,
                            status: Pass(status_code, elapsed)
                        })
                    } else {
                        return ok(CheckResult {
                            target: target,
                            status: Warn(status_code, f"expected {conv.to_string(target.expected_status)}")
                        })
                    }
                }
                none: {
                    throw TimeoutException.from_target("read timed out", target)
                }
            }
        }
        none: {
            throw ConnectionException.from_target(f"cannot connect to {host}:{conv.to_string(port)}", target)
        }
    }
}
```

**HC-3-1-2**
Implement URL parsing helpers:
```
fn:pure parse_host(url: string): string { ... }
fn:pure parse_port(url: string): int { ... }
fn:pure parse_path(url: string): string { ... }
fn:pure parse_http_status(response: string): int { ... }
```

**Definition of done:** `check_target` correctly handles: successful connection
with expected status (returns `ok` with `Pass`), unexpected status (returns `ok`
with `Warn`), connection failure (throws `ConnectionException`), timeout (throws
`TimeoutException`).

---

# EPIC 4: Aggregator (Receivable Coroutine)

---

## Story 4-1: Bidirectional Aggregator

**HC-4-1-1** `[BLOCKER]`
Implement a receivable coroutine that receives `CheckResult` records via
`.send()` and yields a final `Report`:
```
fn result_aggregator(inbox: stream<CheckResult>): stream<Report> {
    let passed = 0
    let failed = 0
    let warnings = 0

    for (r: CheckResult in inbox) {
        match r.status {
            Pass(_, _):   { passed = passed + 1 }
            Fail(_):      { failed = failed + 1 }
            Warn(_, _):   { warnings = warnings + 1 }
        }
    }

    yield Report {
        passed: passed,
        failed: failed,
        warnings: warnings,
        total: passed + failed + warnings
    }
}
```

**HC-4-1-2**
Wire the aggregator:
```
let agg :< result_aggregator() with capacity(4)
; ... for each check result:
agg.send(result)
; ... when all checks done, read report:
match agg.next() {
    some(report): { print_report(report) }
    none: {}
}
```

**Definition of done:** Aggregator correctly counts pass/fail/warn via `.send()`
and yields accurate `Report` via `.next()`.

---

# EPIC 5: Pipeline with Try/Retry/Catch

---

## Story 5-1: Main Pipeline with Error Recovery

**HC-5-1-1** `[BLOCKER]`
Assemble the full pipeline in `main()`:
```
fn main(): void {
    let targets :< produce_targets() with capacity(2)
    let agg :< result_aggregator() with capacity(4)

    io.println(f"[HC] Starting health check...")

    for (target: HealthTarget in targets) {
        io.println(f"[HC] Checking: {target.url}")

        try {
            let result = check_target(target)
            match result {
                ok(r): {
                    match r.status {
                        Pass(code, ms): {
                            io.println(f"[HC] OK: {target.url} ({conv.to_string(code)}, {conv.to_string(ms)}ms)")
                        }
                        Warn(code, reason): {
                            io.println(f"[HC] WARN: {target.url} ({conv.to_string(code)} - {reason})")
                        }
                        Fail(msg): {
                            io.println(f"[HC] FAIL: {target.url} ({msg})")
                        }
                    }
                    agg.send(r)
                }
                err(e): {
                    io.println(f"[HC] ERROR: {e}")
                    agg.send(CheckResult { target: target, status: Fail(e) })
                }
            }

        } retry check_target (ex: ConnectionException, attempts: 3) {
            ; increase timeout on each retry
            io.println(f"[HC] RETRY connect (attempt): increasing timeout")
            ex.data = HealthTarget {
                timeout_ms: ex.data.timeout_ms * 2,
                ..ex.data
            }

        } retry check_target (ex: TimeoutException, attempts: 2) {
            ; double the timeout
            io.println(f"[HC] RETRY timeout: doubling timeout to {conv.to_string(ex.data.timeout_ms * 2)}ms")
            ex.data = HealthTarget {
                timeout_ms: ex.data.timeout_ms * 2,
                ..ex.data
            }

        } catch (ex: ConnectionException) {
            io.println(f"[HC] FAIL: {ex.data.url} ({ex.message()} after retries)")
            agg.send(CheckResult { target: target, status: Fail(ex.message()) })

        } catch (ex: TimeoutException) {
            io.println(f"[HC] FAIL: {ex.data.url} (timed out after retries)")
            agg.send(CheckResult { target: target, status: Fail("timeout") })

        } finally (? ex: Exception) {
            ; nothing to clean up
        }
    }

    ; read final report
    match agg.next() {
        some(report): {
            io.println("[HC] --- Report ---")
            io.println(f"[HC] Passed: {conv.to_string(report.passed)}")
            io.println(f"[HC] Failed: {conv.to_string(report.failed)}")
            io.println(f"[HC] Warnings: {conv.to_string(report.warnings)}")
            io.println(f"[HC] Total: {conv.to_string(report.total)}")
        }
        none: {
            io.println("[HC] No report available")
        }
    }
}
```

Key showcases:
- **`result<T, E>` vs exceptions**: HTTP 404 is a `Warn` via result, not an
  exception. Network failures are exceptions with retry.
- **Multiple retry blocks**: `ConnectionException` and `TimeoutException` get
  separate retry logic, both targeting `check_target`.
- **`ex.data` mutation with struct spread**: Retry increases timeout by
  modifying `ex.data` using `..ex.data` spread.
- **Exception propagation to catch**: After retries exhausted, catch logs
  and sends a `Fail` result to the aggregator.
- **Receivable coroutine**: Aggregator receives results via `.send()`.

**Definition of done:** Full pipeline runs end-to-end against a simulated set
of targets (or actual localhost server if available).

---

# EPIC 6: Reporter with Fan-out

---

## Story 6-1: Result Fan-out

**HC-6-1-1**
Create a display function and fan-out the check result to both display and
aggregation:
```
fn display_result(r: CheckResult): void {
    match r.status {
        Pass(code, ms): {
            io.println(f"  PASS {r.target.url} [{conv.to_string(code)}] {conv.to_string(ms)}ms")
        }
        Warn(code, reason): {
            io.println(f"  WARN {r.target.url} [{conv.to_string(code)}] {reason}")
        }
        Fail(msg): {
            io.println(f"  FAIL {r.target.url} - {msg}")
        }
    }
}
```

Where possible, use fan-out composition:
```
; Conceptual: result -> (display_result | agg.send)
```

Document any gaps with fan-out to coroutine `.send()`.

**Definition of done:** Results are both displayed and aggregated.

---

# EPIC 7: Testing

---

## Story 7-1: End-to-End Test

**HC-7-1-1**
Create `tests/programs/app_healthcheck.flow` — a self-contained test that
starts a trivial TCP server on localhost, runs the health checker against it,
and verifies output.

**HC-7-1-2**
Create `tests/expected_stdout/app_healthcheck.txt` with expected output.

**Definition of done:** `make test` passes with the golden file test.

---

## Dependency Map

```
EPIC 1 (Types) → EPIC 2 (Producer) → EPIC 3 (Checker) → EPIC 4 (Aggregator)
                                                               ↓
EPIC 5 (Pipeline/Try/Retry/Catch) ← ← ← ← ← ← ← ← ← ← ← ←
         ↓
EPIC 6 (Reporter/Fan-out) → EPIC 7 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **Coroutines (`:< `)** | `produce_targets` producer, `result_aggregator` receivable |
| **Receivable coroutine (`.send()`)** | Aggregator receives `CheckResult` records |
| **`.next()` / `.done()`** | Consuming targets, reading final report |
| **`with capacity(n)`** | Bounded channels on producer and aggregator |
| **Backpressure** | Producer blocks when target buffer full |
| **Exception propagation** | `ConnectionException` / `TimeoutException` thrown and caught |
| **`try/retry/catch/finally`** | Full error recovery pipeline |
| **Multiple `retry` blocks** | Separate retry for connection and timeout exceptions |
| **`ex.data` mutation** | Increasing timeout in retry block |
| **`ex.original`** | Comparing original vs corrected target |
| **Struct spread (`..ex.data`)** | Creating modified HealthTarget in retry |
| **`result<T, E>`** | Expected HTTP outcomes (pass/warn) |
| **`?` propagation** | Potential use in helper functions |
| **Sum types** | `CheckStatus` with `Pass`, `Fail`, `Warn` variants |
| **Pattern matching** | Dispatching on `CheckStatus`, `option<T>`, `result` |
| **`fn:pure`** | URL parsing helpers |
| **`net` module** | TCP connect, read, write, set_timeout, close |
| **`time` module** | Latency measurement |
| **`conv` module** | Integer/string conversion |
| **`string` module** | URL parsing, HTTP response parsing |
| **`map<string, int>`** | Could be used for per-host stats |
| **`io` module** | Printing status and report |
