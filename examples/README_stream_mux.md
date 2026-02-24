# Stream Multiplexer

A content-based router that takes a stream of records and routes each one to a
named destination based on its category field. Output is collected per
destination using a `map<string, string>` and printed in groups.

## Run it

```bash
python main.py build examples/stream_mux.reflow -o /tmp/stream_mux && /tmp/stream_mux
```

## What it does

The program processes six records with different categories:

```
error/1   "disk full"
metric/3  "cpu=72%"
audit/2   "user login"
error/1   "OOM"
metric/3  "mem=85%"
info/4    "startup complete"
```

For each record it:

1. **Routes** — calls `route(r)` which maps the category to a destination name:
   - `"error"` goes to `"alerts"`
   - `"metric"` goes to `"metrics"`
   - `"audit"` goes to `"archive"`
   - everything else goes to `"default"`
2. **Formats** — creates a display string like `[error/1] disk full`.
3. **Collects** — appends the formatted line to the destination's entry in a
   mutable `map<string, string>`, using `map.get` with `??` to handle the
   first-insert case.
4. **Prints** — iterates `map.keys()` and prints each destination's collected
   output under a header.

## Expected output

```
=== archive ===
[audit/2] user login

=== metrics ===
[metric/3] cpu=72%
[metric/3] mem=85%

=== alerts ===
[error/1] disk full
[error/1] OOM

=== default ===
[info/4] startup complete
```

## Language features demonstrated

| Feature | Where |
|---------|-------|
| Record types | `Record` with `category`, `priority`, `data` fields |
| `map<string, string>` | Mutable map for collecting output per destination |
| Map operations | `map.new()`, `map.get`, `map.set`, `map.keys` |
| `option<T>` / `??` | `map.get(destinations, dest) ?? ""` for missing keys |
| `:mut` bindings | `destinations: map<string, string>:mut` |
| `fn:pure` functions | `route` and `format_record` |
| Struct literals in arrays | `[Record { ... }, Record { ... }]` |
| `for` over arrays | `for (r: Record in records)` and `for (key: string in ks)` |

## How to modify

- Add new routing rules by adding cases to the `route` function.
- Change the record structure to include more fields.
- Use the destinations map for further processing instead of just printing
  (e.g. write each destination to a different file using `io.write_file`).
