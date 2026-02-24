# Log Ingestion Pipeline

An ETL pipeline that ingests log lines in three different formats, normalizes
them into a common `LogEntry` record, routes each entry through multiple
processing sinks via fan-out, and filters alerts by severity.

## Run it

```bash
python main.py build examples/log_pipeline.flow -o /tmp/log_pipeline && /tmp/log_pipeline
```

## What it does

The program processes five hardcoded log lines in three formats:

| Format | Example | Detection |
|--------|---------|-----------|
| Key-value | `ts=2024-01-01 level=ERROR src=api msg=timeout` | Starts with `ts=` |
| CSV | `2024-01-01,INFO,db,connected` | Contains a comma |
| Simple | `2024-01-01 web WARN slow_query` | Fallback |

For each line it:

1. **Detects** the format using `string.starts_with` and `string.contains`.
2. **Parses** it into a `LogEntry` with timestamp, severity, source, and message.
3. **Validates** that timestamp and source are non-empty (corrupt lines are
   caught and skipped).
4. **Fan-out** — sends the entry to two sinks simultaneously using Flow's
   sequential fan-out syntax:
   ```
   entry -> (write_archive | update_stats) -> combine_output
   ```
   This calls `write_archive(entry)` and `update_stats(entry)`, then passes
   both results to `combine_output`.
5. **Filters** — prints an `ALERT` line for entries with severity ERROR or WARN.

## Expected output

```
ARCHIVE: [2024-01-01] api timeout
STATS: severity=ERROR source=api
ALERT: ERROR from api: timeout
ARCHIVE: [2024-01-01] db connected
STATS: severity=INFO source=db
ARCHIVE: [2024-01-01] web slow_query
STATS: severity=WARN source=web
ALERT: WARN from web: slow_query
SKIP: empty source
ARCHIVE: [2024-01-02] api retry
STATS: severity=WARN source=api
ALERT: WARN from api: retry
```

- The `corrupt???` line parses but has an empty source field, triggering the
  catch block.
- Only ERROR and WARN entries produce ALERT lines.

## Language features demonstrated

| Feature | Where |
|---------|-------|
| Record types | `Severity`, `LogEntry` with nested struct field |
| Sequential fan-out `(a \| b)` | `entry -> (write_archive \| update_stats) -> combine_output` |
| Composition chains `->` | Fan-out result piped into `combine_output` |
| `fn:pure` functions | All parsers and sinks are pure |
| `try/catch` | Malformed lines caught and reported |
| String pattern dispatch | `starts_with` / `contains` for format detection |
| `option<T>` / `??` | Safe array access for parsed fields |

## How to modify

- Add new log formats by writing a new `parse_*` function and adding a
  detection rule in `detect_and_parse`.
- Add more sinks by extending the fan-out: `(write_archive | update_stats | new_sink)`.
  You'll need a 3-argument combiner function after the fan-out.
- Change severity filtering by adjusting the `entry.severity.level <= 1` check.
