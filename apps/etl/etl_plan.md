# Plan: ETL Data Pipeline

## Overview

A data pipeline that extracts CSV-formatted employee records from a simulated
data source (coroutine producer), transforms and validates each row through a
composition chain, and loads results into an aggregation sink. Demonstrates
coroutines for concurrent production, composition chains for pipeline stages,
try/retry/catch for error recovery, and fan-out for multi-sink output.

**File:** `apps/etl/etl.flow`

**Usage:**
```
python main.py run apps/etl/etl.flow
```

**Example output:**
```
[ETL] Starting pipeline...
[ETL] Processing: Alice,Engineering,95000
[ETL] Processing: Bob,Marketing,bad_salary
[ETL] RETRY parse_row (attempt 1): sanitizing "bad_salary" -> "0"
[ETL] Processing: Charlie,Engineering,87000
[ETL] Processing: ???,Sales,72000
[ETL] RETRY validate_row (attempt 1): replacing empty name with "UNKNOWN"
[ETL] Processing: Diana,x,91000
[ETL] RETRY validate_row (attempt 1): unknown dept "x", using "Other"
[ETL] RETRY validate_row (attempt 2): still invalid
[ETL] CATCH ValidationError: permanently bad record, quarantining
[ETL] --- Summary ---
[ETL] Total processed: 4
[ETL] Errors: 1
[ETL] Avg salary: 86000
[ETL] By department: Engineering=2, Marketing=1, Sales=1
```

**Stdlib modules used:** `io`, `string`, `array`, `conv`, `map`

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

- Tickets are numbered `ETL-EPIC-STORY-TICKET`.
- Tickets marked `[BLOCKER]` must be complete before the next story can begin.

---

# EPIC 1: Data Types & Exception Types

---

## Story 1-1: Record Types

**ETL-1-1-1** `[BLOCKER]`
Define the raw and parsed record types:
```
type RawRow {
    line_num: int,
    content: string
}

type Employee {
    name: string,
    department: string,
    salary: float
}

type Summary {
    total: int,
    errors: int,
    salary_sum: float,
    dept_counts: map<string, int>
}
```

**Definition of done:** Types compile and can be constructed in a test function.

---

## Story 1-2: Exception Types

**ETL-1-2-1** `[BLOCKER]`
Define exception types following the `Exception<T>` interface:
```
type ParseException fulfills Exception<string> {
    msg: string,
    payload: string:mut,
    original_payload: string,

    constructor from_raw(m: string, p: string): ParseException {
        return ParseException {
            msg: m,
            payload: p,
            original_payload: p
        }
    }

    fn message(self): string  { return self.msg }
    fn data(self): string     { return self.payload }
    fn original(self): string { return self.original_payload }
}

type ValidationException fulfills Exception<Employee> {
    msg: string,
    payload: Employee:mut,
    original_payload: Employee,

    constructor from_employee(m: string, e: Employee): ValidationException {
        return ValidationException {
            msg: m,
            payload: e,
            original_payload: e
        }
    }

    fn message(self): string    { return self.msg }
    fn data(self): Employee     { return self.payload }
    fn original(self): Employee { return self.original_payload }
}
```

**Definition of done:** Exception types compile. Can be thrown and caught in a
trivial try/catch block.

---

# EPIC 2: Extractor (Coroutine Producer)

---

## Story 2-1: CSV Data Source

**ETL-2-1-1** `[BLOCKER]`
Implement a stream function that yields raw CSV rows:
```
fn csv_source(): stream<RawRow> {
    let data = array.of(
        "Alice,Engineering,95000",
        "Bob,Marketing,bad_salary",
        "Charlie,Engineering,87000",
        ",,72000",
        "Diana,x,91000",
        "Eve,Sales,68000"
    )
    let i = 0
    for (line: string in data) {
        i = i + 1
        yield RawRow { line_num: i, content: line }
    }
}
```

**ETL-2-1-2** `[BLOCKER]`
Spawn the source as a coroutine with bounded capacity:
```
let source :< csv_source() with capacity(4)
```

Consume with a loop:
```
let row: option<RawRow> = source.next()
match row {
    some(r): { ... process r ... }
    none:    { ... done ... }
}
```

**Definition of done:** Coroutine yields all rows. Consumer reads them all and
prints each. Backpressure verified by using `capacity(1)`.

---

# EPIC 3: Parser & Validator

---

## Story 3-1: Row Parser

**ETL-3-1-1** `[BLOCKER]`
Implement `parse_row` that splits a CSV string and constructs an Employee.
Throws `ParseException` on malformed data:
```
fn parse_row(raw: RawRow): Employee {
    let parts = string.split(raw.content, ",")
    if array.length(parts) != 3 {
        throw ParseException.from_raw(
            f"expected 3 fields, got {array.length(parts)}",
            raw.content
        )
    }
    let salary = conv.parse_float(array.get(parts, 2) ?? "0")
    match salary {
        some(s): {
            return Employee {
                name: array.get(parts, 0) ?? "",
                department: array.get(parts, 1) ?? "",
                salary: s
            }
        }
        none: {
            throw ParseException.from_raw(
                f"invalid salary: {array.get(parts, 2) ?? \"?\"}",
                raw.content
            )
        }
    }
}
```

**Definition of done:** `parse_row` correctly parses valid rows and throws
`ParseException` for rows with non-numeric salary fields.

---

## Story 3-2: Row Validator

**ETL-3-2-1** `[BLOCKER]`
Implement `validate_row` that checks business rules. Throws
`ValidationException` on invalid data:
```
fn validate_row(e: Employee): Employee {
    let valid_depts = array.of("Engineering", "Marketing", "Sales", "HR", "Other")
    if string.length(e.name) == 0 {
        throw ValidationException.from_employee("empty name", e)
    }
    if !array.contains(valid_depts, e.department) {
        throw ValidationException.from_employee(
            f"unknown department: {e.department}", e
        )
    }
    if e.salary < 0.0 {
        throw ValidationException.from_employee("negative salary", e)
    }
    return e
}
```

**Definition of done:** `validate_row` passes valid employees and throws
`ValidationException` for invalid ones.

---

# EPIC 4: Transformer

---

## Story 4-1: Pure Transformations

**ETL-4-1-1**
Implement pure transformation functions using struct spread:
```
fn:pure normalize_name(e: Employee): Employee =
    Employee { name: string.trim(e.name), ..e }

fn:pure normalize_dept(e: Employee): Employee =
    Employee { department: string.upper(string.slice(e.department, 0, 1))
               + string.slice(e.department, 1, string.length(e.department)),
               ..e }

fn:pure apply_tax(e: Employee): Employee =
    Employee { salary: e.salary * 0.85, ..e }
```

**ETL-4-1-2**
Compose transformations into a single pipeline step:
```
fn:pure transform(e: Employee): Employee =
    e -> normalize_name -> normalize_dept -> apply_tax
```

**Definition of done:** `transform` chains all three pure functions. Input/output
verified with a test employee.

---

# EPIC 5: Loader with Fan-out

---

## Story 5-1: Aggregator (Receivable Coroutine)

**ETL-5-1-1** `[BLOCKER]`
Implement a receivable coroutine that accumulates statistics. It receives
`Employee` records via `.send()` and yields a final `Summary` when done:
```
fn aggregator(inbox: stream<Employee>): stream<Summary> {
    let total = 0
    let salary_sum = 0.0
    let dept_counts: map<string, int> = map.new()

    for (e: Employee in inbox) {
        total = total + 1
        salary_sum = salary_sum + e.salary
        let cur = map.get(dept_counts, e.department) ?? 0
        dept_counts = map.set(dept_counts, e.department, cur + 1)
    }

    yield Summary {
        total: total,
        errors: 0,
        salary_sum: salary_sum,
        dept_counts: dept_counts
    }
}
```

**ETL-5-1-2**
Wire the aggregator:
```
let agg :< aggregator() with capacity(8)
; ... for each valid employee:
agg.send(employee)
; ... when done:
let summary = agg.next()
```

**Definition of done:** Aggregator receives employees via `.send()` and yields
a correct `Summary` via `.next()`.

---

## Story 5-2: Print Sink

**ETL-5-2-1**
Implement a formatter that prints each processed employee:
```
fn print_employee(e: Employee): void {
    io.println(f"[ETL] Loaded: {e.name} | {e.department} | {conv.to_string(e.salary)}")
}
```

**Definition of done:** Each valid employee is printed to stdout.

---

## Story 5-3: Fan-out Wiring

**ETL-5-3-1**
Fan out each valid employee to both the printer and the aggregator:
```
; Conceptual: employee -> (print_employee | send_to_agg)
```

Since `send_to_agg` is a side-effecting call to `agg.send()`, this may need
to be done imperatively rather than with the `|` operator. Document if
fan-out to a coroutine `.send()` is a gap.

**Definition of done:** Each valid employee reaches both sinks.

---

# EPIC 6: Pipeline Assembly with Try/Retry/Catch

---

## Story 6-1: Main Pipeline

**ETL-6-1-1** `[BLOCKER]`
Assemble the full pipeline in `main()` with try/retry/catch:
```
fn main(): void {
    io.println("[ETL] Starting pipeline...")
    let source :< csv_source() with capacity(4)
    let agg :< aggregator() with capacity(8)
    let error_count = 0

    ; process each row from the coroutine
    for (raw: RawRow in source) {
        try {
            let result = raw -> parse_row -> validate_row -> transform
            print_employee(result)
            agg.send(result)

        } retry parse_row (ex: ParseException, attempts: 2) {
            ; sanitize: replace non-numeric salary with "0"
            io.println(f"[ETL] RETRY parse_row: sanitizing '{ex.data}'")
            ex.data = string.replace(ex.data, array.get(string.split(ex.data, ","), 2) ?? "", "0")

        } retry validate_row (ex: ValidationException, attempts: 2) {
            ; correct: fill missing name, default unknown dept
            io.println(f"[ETL] RETRY validate_row: correcting '{ex.message()}'")
            if string.length(ex.data.name) == 0 {
                ex.data = Employee { name: "UNKNOWN", ..ex.data }
            }
            if !is_valid_dept(ex.data.department) {
                ex.data = Employee { department: "Other", ..ex.data }
            }

        } catch (ex: ParseException) {
            io.println(f"[ETL] CATCH ParseException: {ex.message()}")
            io.println(f"[ETL]   original: {ex.original}, last attempt: {ex.data}")
            error_count = error_count + 1

        } catch (ex: ValidationException) {
            io.println(f"[ETL] CATCH ValidationException: {ex.message()}")
            error_count = error_count + 1

        } finally (? ex: Exception) {
            if ex {
                io.println(f"[ETL] Row failed after retries")
            }
        }
    }

    ; read summary from aggregator
    match agg.next() {
        some(s): {
            io.println("[ETL] --- Summary ---")
            io.println(f"[ETL] Total processed: {conv.to_string(s.total)}")
            io.println(f"[ETL] Errors: {conv.to_string(error_count)}")
            io.println(f"[ETL] Avg salary: {conv.to_string(s.salary_sum / conv.to_float(s.total))}")
        }
        none: {
            io.println("[ETL] No summary available")
        }
    }
}
```

**Definition of done:** Full pipeline runs end-to-end. Good rows are parsed,
validated, transformed, and aggregated. Bad rows trigger retry with corrective
logic. Permanently bad rows are caught and counted.

---

# EPIC 7: Testing

---

## Story 7-1: End-to-End Test

**ETL-7-1-1**
Create `tests/programs/app_etl.flow` — a non-interactive version that runs the
full pipeline on hardcoded data and prints all output.

**ETL-7-1-2**
Create `tests/expected_stdout/app_etl.txt` with expected output covering:
- Successful rows processed
- Retry attempts (parse and validation)
- Catch for permanently bad rows
- Final summary statistics

**Definition of done:** `make test` passes with the golden file test.

---

## Dependency Map

```
EPIC 1 (Types) → EPIC 2 (Extractor) → EPIC 3 (Parser/Validator) → EPIC 4 (Transformer)
                                                                         ↓
EPIC 5 (Loader/Fan-out) ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
         ↓
EPIC 6 (Pipeline Assembly) → EPIC 7 (Testing)
```

---

## Language Features Exercised

| Feature | Where |
|---------|-------|
| **Coroutines (`:< `)** | `csv_source` producer, `aggregator` receivable coroutine |
| **`with capacity(n)`** | Bounded channels on both coroutines |
| **`.next()` / `.send()`** | Consuming producer, feeding aggregator |
| **Receivable coroutines** | `aggregator` has `inbox: stream<Employee>` |
| **Backpressure** | Producer blocks when channel full |
| **Composition chains (`->`)** | `raw -> parse_row -> validate_row -> transform` |
| **`try/retry/catch/finally`** | Full exception handling with corrective retry |
| **Multiple `retry` blocks** | Separate retry for `parse_row` and `validate_row` |
| **Multiple `catch` blocks** | Separate catch for `ParseException` and `ValidationException` |
| **`ex.data` mutation** | Correcting payload in retry blocks |
| **`ex.original`** | Logging the original failing value |
| **`Exception<T>` interface** | Custom exception types with `fulfills` |
| **`fn:pure`** | Transformer functions are pure |
| **Struct spread (`..e`)** | Transformer creates modified copies |
| **Sum types** | N/A (stretch: `result<Employee, string>` for validation) |
| **`match`** | Coroutine `.next()` result dispatch |
| **`option<T>` / `??`** | Safe array access, map lookup |
| **`map<string, int>`** | Department count aggregation |
| **`for-in` on streams** | Consuming inbox in aggregator |
| **`conv` module** | Float parsing, string conversion |
| **`string` module** | Split, trim, replace |
| **`array` module** | Construction, access, contains |
| **`io` module** | Printing output |
