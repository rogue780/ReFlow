# jsonq — JSON Query Tool

A command-line tool for querying and transforming JSON files. Reads a JSON
file (or stdin), evaluates dot-path expressions, and prints results.
Pipe-friendly, composable, zero-config.

## Usage

```bash
# Extract a field
python main.py run apps/jsonq/jsonq.reflow -- data.json "name"

# Read from stdin
cat data.json | python main.py run apps/jsonq/jsonq.reflow -- - "name"

# Multiple queries
python main.py run apps/jsonq/jsonq.reflow -- data.json "name" "age" "city"

# Pretty-print objects/arrays
python main.py run apps/jsonq/jsonq.reflow -- data.json "config" --pretty
```

## Query Syntax

| Pattern | Description | Example |
|---------|-------------|---------|
| `key` | Object field access | `"name"` -> `Alice` |
| `a.b.c` | Nested access | `"address.city"` -> `New York` |
| `0` | Array index | `"users.0.email"` -> `alice@example.com` |
| `#` | Length (array, object, or string) | `"users.#"` -> `3` |
| `*` | Wildcard (iterate array elements) | `"users.*.name"` -> one result per element |
| `?type` | Type introspection | `"name?type"` -> `string` |
| (empty) | Root document | `""` -> entire JSON |

### Type Names

`?type` returns one of: `string`, `number`, `boolean`, `null`, `array`, `object`.

### Wildcards

`*` iterates all elements of an array. Remaining path segments apply to each
element. Results print one per line:

```bash
jsonq data.json "users.*.name"
# Alice
# Bob
# Charlie
```

Nested wildcards work: `"data.*.items.*.id"` iterates at both levels.

## Output Format

- **Strings** print without quotes (pipe-friendly)
- **Numbers, booleans, null** print as JSON literals
- **Objects and arrays** print as compact JSON (or indented with `--pretty`)

## Error Handling

- Missing path: prints nothing to stdout, error to stderr, exits 1
- File not found: error to stderr, exits 1
- Invalid JSON: error to stderr, exits 1
- Malformed query (double dots, leading/trailing dots): error to stderr, exits 1

## Comparison to jq

This is a simple path extractor, not a full query language. It handles the
most common use case — extracting values by path — without jq's learning
curve. For filtering, mapping, and complex transformations, use jq.
