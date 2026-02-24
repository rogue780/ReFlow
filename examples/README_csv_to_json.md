# CSV-to-JSON Transformer

A data transformation pipeline that parses CSV rows, validates them against a
schema, and outputs JSON objects. Malformed rows are sanitized and retried once
before being skipped.

## Run it

```bash
python main.py build examples/csv_to_json.reflow -o /tmp/csv_to_json && /tmp/csv_to_json
```

## What it does

The program processes a hardcoded CSV dataset with a header row and four data
rows:

```
name,age,city
Alice,30,NYC
Bob,,London
,bad,data
Charlie,25,Paris
```

For each data row it:

1. **Splits** the line on commas into fields.
2. **Validates** that all required fields (here, `name`) are non-empty.
3. **Converts** valid rows to a JSON object string using `string_builder`.
4. On failure, **sanitizes** the line (strips quotes, trims whitespace) and
   retries once. If it still fails, prints a `SKIP` message.

## Expected output

```
{"name":"Alice","age":"30","city":"NYC"}
{"name":"Bob","age":null,"city":"London"}
SKIP row 3: missing required field 'name' at row 3
{"name":"Charlie","age":"25","city":"Paris"}
```

- Row 2 (`Bob,,London`) passes because `name` is present; the empty `age`
  field becomes `null` in JSON.
- Row 3 (`,bad,data`) fails because the required `name` field is empty. The
  sanitized version still has an empty name, so it's skipped.

## Language features demonstrated

| Feature | Where |
|---------|-------|
| Record types | `Schema`, `CsvRow` |
| `fn:pure` functions | `parse_row`, `validate`, `to_json`, `escape_json`, `sanitize` |
| `option<T>` / `??` | `array.get(cols, i) ?? ""` for safe array access |
| Exception retry pattern | Nested `try/catch` — outer catch sanitizes and retries |
| `string_builder` | `to_json` builds JSON efficiently with `sb.new()` / `sb.append` / `sb.build` |
| Stdlib modules | `string`, `array`, `conv`, `string_builder` |

## How to modify

- Change the `lines` array in `main()` to use different CSV data.
- Add more column names to the `required` array in the `Schema` to make
  validation stricter.
- Edit `to_json` to change the output format (e.g. add indentation).
