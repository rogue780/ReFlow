# Validation: JSON Parser

## Category
Standard Library & I/O Stress Test

## What It Validates
- Recursive descent parsing (character-by-character string processing)
- Recursive sum types for JSON value representation
- Complex string manipulation (`string.char_at`, `string.substring`, `string.len`)
- Character classification (`char.is_whitespace`, `char.is_digit`)
- Mutual recursion (parse_value calls parse_object which calls parse_value)
- Option types for parse failure
- Tuple returns for (result, position) pairs
- Array and map building during parsing
- Serialization back to string (round-trip correctness)

## Why It Matters
A hand-written JSON parser is the classic "can your language do real string
processing?" test. It requires recursive descent with backtracking, character-
level access, and building a tree of heterogeneous values. Flow already has a
`json` stdlib module — this validation writes one from scratch to stress the
language's string handling and recursive type capabilities.

## File
`validation/json_parser/json_parser.flow`

## Structure

**Module:** `module validation.json_parser`
**Imports:** `io`, `string`, `conv`, `array`, `map`

### Types

```flow
type JsonValue = JsonNull
               | JsonBool { value: bool }
               | JsonNum { value: float }
               | JsonStr { value: string }
               | JsonArray { items: array<JsonValue> }
               | JsonObject { entries: map<string, JsonValue> }
```

Note: `JsonArray` and `JsonObject` may require non-pointer-type array/map
handling. If `array<JsonValue>` doesn't work with a sum type, this is a
finding.

### Functions (parse side)

1. **`fn:pure skip_whitespace(input: string, pos: int): int`**
   - Advance pos past spaces, tabs, newlines

2. **`fn:pure parse_null(input: string, pos: int): (JsonValue, int)?`**
   - Match literal `"null"` at pos

3. **`fn:pure parse_bool(input: string, pos: int): (JsonValue, int)?`**
   - Match `"true"` or `"false"`

4. **`fn:pure parse_number(input: string, pos: int): (JsonValue, int)?`**
   - Parse optional `-`, digits, optional `.` + digits
   - Convert via `conv.string_to_float`

5. **`fn:pure parse_string_value(input: string, pos: int): (string, int)?`**
   - Parse `"..."` with basic escape handling (`\"`, `\\`, `\n`, `\t`)

6. **`fn:pure parse_string(input: string, pos: int): (JsonValue, int)?`**
   - Wraps `parse_string_value` in `JsonStr`

7. **`fn:pure parse_array(input: string, pos: int): (JsonValue, int)?`**
   - Parse `[`, then comma-separated values, then `]`
   - Calls `parse_value` recursively for each element

8. **`fn:pure parse_object(input: string, pos: int): (JsonValue, int)?`**
   - Parse `{`, then comma-separated `"key": value` pairs, then `}`
   - Calls `parse_value` recursively for each value

9. **`fn:pure parse_value(input: string, pos: int): (JsonValue, int)?`**
   - Dispatch to parse_null, parse_bool, parse_number, parse_string,
     parse_array, parse_object based on first character

10. **`fn:pure parse(input: string): JsonValue?`**
    - Entry point: parse_value at pos 0, verify all input consumed

### Functions (serialize side)

11. **`fn:pure json_to_string(val: JsonValue): string`**
    - Match on variant, recursively serialize
    - Objects: `{"key":"val",...}`, Arrays: `[1,2,3]`

### Functions (query side)

12. **`fn:pure json_get(val: JsonValue, key: string): JsonValue?`**
    - If `JsonObject`, look up key in map; else `none`

13. **`fn:pure json_index(val: JsonValue, idx: int): JsonValue?`**
    - If `JsonArray`, index into array; else `none`

## Test Program
`tests/programs/val_json_parser.flow`

Test cases:
- Parse `"null"` -> JsonNull
- Parse `"true"` -> JsonBool
- Parse `"42"` -> JsonNum
- Parse `"\"hello\""` -> JsonStr
- Parse `"[1, 2, 3]"` -> JsonArray with 3 elements
- Parse `"{\"name\": \"Flow\", \"version\": 1}"` -> JsonObject
- Parse nested: `"{\"data\": [1, {\"x\": true}]}"` -> nested structure
- Round-trip: parse then serialize, compare strings
- Query: json_get on object, json_index on array
- Invalid input: parse `"[1,]"` -> none (trailing comma)

## Expected Output (test)
```
null: null
bool: true
num: 42
str: hello
array len: 3
obj name: Flow
nested: true
round-trip: ok
get name: Flow
index 1: 2
invalid: none
done
```

## Estimated Size
~250 lines (app), ~80 lines (test)

## Flow Features Exercised

| Feature | Usage |
|---------|-------|
| Recursive sum type (6 variants) | `JsonValue` |
| `match` on sum type | every function |
| Mutual recursion | parse_value <-> parse_array/parse_object |
| `option<T>` + tuples | parse results as `(JsonValue, int)?` |
| `string.char_at` | character-level parsing |
| `string.substring` | extracting substrings |
| `map<string, JsonValue>` | object storage |
| `array<JsonValue>` | array storage (sum type elements) |
| `fn:pure` | all parse/serialize functions |
| `conv.string_to_float` | number parsing |

## Known Risks
- `array<JsonValue>` where JsonValue is a sum type: this tests the
  `array.push_sized` / `FL_OPT_DEREF_AS` path from Known Decision #9.
  If it fails, that's a critical finding.
- `map<string, JsonValue>` with sum type values: may need boxing. If
  `map.set/get` doesn't work with sum types, that's a finding.
- Tuple option `(JsonValue, int)?` may not be supported. If not, use
  a result struct instead.
- This is the most complex validation program. Expect to find gaps.
