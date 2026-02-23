# ReFlow Fixes Report

Improvements and additions identified while building the HTTP static file server
(`apps/http/server/server.reflow`). All 14 items have been implemented and tested.

---

## 1. Match-as-Expression Implicit Return

**Category:** Compiler bug fix
**Files changed:** `compiler/lowering.py`

**Problem:** When a `match` statement was the last expression in a function body,
the compiler did not implicitly return its value. Functions like
`fn classify(x: int): string { match x { 0: "zero" _: "other" } }` would not
return the matched string — the value was computed and discarded.

**Fix:** Added `_inject_tail_returns()` method to the lowering pass. This
recursively walks the last statement of a function body: if it's an `LExprStmt`,
it converts it to `LReturn`. If it's an `LIf` or `LSwitch` (which is what
`match` lowers to), it recurses into each branch's tail position. Applied to
both standalone functions and methods.

**Example:** `examples/match_expression_demo.reflow`

---

## 2. Opaque Types Cross-Module Parameter Passing

**Category:** Compiler bug fix
**Files changed:** `compiler/lowering.py`

**Problem:** When a stdlib function returns an opaque type (e.g., `Socket` from
`net.listen()`), passing the result to another function in the same module worked
fine. But passing it to a function in a different module (or back to another stdlib
function) caused a type mismatch because the lowering produced a mangled struct
name based on the importing module's path instead of the canonical runtime name.

**Fix:** Added `_OPAQUE_TYPE_MAP` dictionary in `lowering.py` that maps opaque
type names (`Socket`, `file`, `JsonValue`, `StringBuilder`, `DateTime`, `Instant`)
to their canonical C runtime struct names (`RF_Socket`, `RF_File`, etc.). The
`_lower_type` method checks this map before falling through to standard name
mangling.

---

## 3. Escape Sequences `\r` and `\0`

**Category:** Already implemented
**Status:** No changes needed. The lexer already handles `\r`, `\n`, `\t`, `\0`,
`\\`, and `\"` escape sequences.

---

## 4. Array Get/Len/Indexing

**Category:** New stdlib module
**Files changed:** `runtime/reflow_runtime.h`, `runtime/reflow_runtime.c`,
`stdlib/array.reflow`, `compiler/driver.py`

**Problem:** Arrays had no safe access or length functions. The only way to
interact with array elements was via `for` loops. This made it impossible to
extract specific elements by index (e.g., CLI args, HTTP request parts).

**Fix:** Added typed safe-access functions (`rf_array_get_int`, `rf_array_get_int64`,
`rf_array_get_float`, `rf_array_get_bool`) and a generic pointer-based one
(`rf_array_get_safe`) to the runtime. Added `rf_array_len_int` (returns `int`)
alongside the existing `rf_array_len` (returns `int64`). Created `stdlib/array.reflow`
exposing all functions. Added `"array"` to `_STDLIB_MODULES` in `driver.py`.

**Example:** `examples/array_demo.reflow`

---

## 5. String Builder

**Category:** New runtime type + stdlib module
**Files changed:** `runtime/reflow_runtime.h`, `runtime/reflow_runtime.c`,
`stdlib/string_builder.reflow`, `compiler/lowering.py`, `compiler/driver.py`

**Problem:** Building strings incrementally with `+` concatenation is O(n^2)
because each concatenation allocates a new string. The HTTP server needs to build
response headers, HTML pages, and log messages efficiently.

**Fix:** Added `RF_StringBuilder` struct to the runtime with a full API: `new`,
`with_capacity`, `append`, `append_cstr`, `append_char`, `append_int`,
`append_int64`, `append_float`, `build`, `len`, `clear`, `retain`, `release`.
Created `stdlib/string_builder.reflow`. Added `StringBuilder` to the opaque type
map in lowering.

**Example:** `examples/string_builder_demo.reflow`

---

## 6. Map Module (String-Key API)

**Category:** New stdlib module
**Files changed:** `runtime/reflow_runtime.h`, `runtime/reflow_runtime.c`,
`stdlib/map.reflow`, `compiler/driver.py`

**Problem:** The runtime had `RF_Map` with a low-level byte-key API, but there
was no way to use maps from ReFlow code with string keys (the most common case).

**Fix:** Added string-key convenience functions to the runtime: `rf_map_set_str`,
`rf_map_get_str`, `rf_map_has_str`, `rf_map_remove_str`, `rf_map_keys`,
`rf_map_values`. These handle the `s->data`/`s->len` extraction internally.
Created `stdlib/map.reflow` with all 8 functions. Added `"map"` to
`_STDLIB_MODULES`.

**Example:** `examples/map_demo.reflow`

---

## 7. Continue Keyword

**Category:** New language feature
**Files changed:** `compiler/lexer.py`, `compiler/ast_nodes.py`,
`compiler/parser.py`, `compiler/resolver.py`, `compiler/typechecker.py`,
`compiler/lowering.py`, `compiler/emitter.py`

**Problem:** ReFlow had `break` for loops but no `continue`. This forced awkward
control flow patterns (wrapping loop bodies in if/else to skip iterations).

**Fix:** Full pipeline implementation:
- Lexer: Added `CONTINUE` token type and `"continue"` keyword mapping
- Parser: Added `ContinueStmt` parsing in `parse_stmt`
- AST: Added `ContinueStmt(Stmt)` dataclass
- Resolver: Pass-through handling
- Type checker: Pass-through handling
- Lowering: Added `LContinue` LIR node
- Emitter: Emits `continue;`

**Spec update:** Added to `reflow_spec.md` keywords list and new "Loop Control:
break and continue" section.

**Example:** Updated `examples/control_flow.reflow` with continue demo

---

## 8. Else If

**Category:** Already working
**Status:** No changes needed. `else if` chains work correctly — the parser
handles them as nested if/else constructs.

---

## 9. Auto-Coerce Showable in String Concatenation

**Category:** Language feature enhancement
**Files changed:** `compiler/typechecker.py`, `compiler/lowering.py`

**Problem:** `"count: " + n` where `n: int` was a type error. Users had to use
f-strings (`f"count: {n}"`) for every mixed-type concatenation, which was verbose
and un-ergonomic.

**Fix:** Modified the type checker's BinOp handling: when the operator is `+`
and one operand is `string` while the other fulfills `Showable`, the result type
is `string`. Modified the lowering's `_lower_binop`: when the result type is
`TString` and an operand is not a string, it calls `_to_string_expr()` (the same
conversion used by f-strings) on the non-string operand, then emits
`rf_string_concat`.

**Spec update:** Added "Showable Auto-coercion in String Concatenation" section
to `reflow_spec.md`.

**Example:** `examples/string_extras_demo.reflow`

---

## 10. Int to Int64 Implicit Widening

**Category:** Language feature enhancement
**Files changed:** `compiler/typechecker.py`, `compiler/lowering.py`

**Problem:** `let small: int = 5; let big: int64 = 100; let sum = small + big`
was a type error. Users had no way to mix integer widths in arithmetic without
explicit casting (which ReFlow doesn't expose).

**Fix:** Modified the type checker to allow arithmetic between integers of the
same signedness but different widths, returning the wider type. Added widening
to `_is_assignable` so `int` can be assigned to `int64` parameters. Modified the
lowering to insert `LCast` on the narrower operand in checked arithmetic
operations.

**Spec update:** Added "Implicit Integer Widening" section to `reflow_spec.md`.

**Example:** `examples/int_widening_demo.reflow`

---

## 11. URL Percent-Encoding/Decoding

**Category:** New stdlib functions
**Files changed:** `runtime/reflow_runtime.h`, `runtime/reflow_runtime.c`,
`stdlib/string.reflow`

**Problem:** The HTTP server cannot correctly handle URLs with spaces, special
characters, or non-ASCII content. No way to decode `%20` to a space or encode
special characters for safe URLs.

**Fix:** Added `rf_string_url_decode` (handles `%XX` hex sequences and `+` as
space) and `rf_string_url_encode` (encodes everything except unreserved
characters per RFC 3986) to the runtime. Exposed as `url_decode` and
`url_encode` in `stdlib/string.reflow`.

**Spec update:** Added to `stdlib_spec.md` string module.

**Example:** `examples/string_extras_demo.reflow`

---

## 12. Date/Time Formatting

**Category:** Stdlib extension
**Files changed:** `stdlib/time.reflow`, `compiler/lowering.py`

**Problem:** The time module only exposed `now()` (Unix timestamp). The HTTP
server needs RFC 7231 formatted dates for `Date:` headers, and logging needs
human-readable timestamps.

**Fix:** Exposed existing runtime functions through `stdlib/time.reflow`:
`datetime_now`, `datetime_utc`, `format_iso8601`, `format_rfc2822`, `format_http`,
`year`, `month`, `day`, `hour`, `minute`, `second`. Added `DateTime` and
`Instant` to the opaque type map in lowering.

**Spec update:** Updated time module in `stdlib_spec.md` — changed 13 functions
from "Planned" to "Implemented".

---

## 13. Array Concatenation

**Category:** New runtime function + stdlib binding
**Files changed:** `runtime/reflow_runtime.h`, `runtime/reflow_runtime.c`,
`stdlib/array.reflow`

**Problem:** No way to combine two arrays. The HTTP server needs this for building
response byte arrays (header bytes + body bytes).

**Fix:** Added `rf_array_concat` to the runtime — allocates a new array and
copies elements from both inputs. Exposed as `concat_int`, `concat_string`, and
`concat_byte` in `stdlib/array.reflow` (typed wrappers over the generic function).

**Example:** `examples/array_demo.reflow`

---

## 14. String Repeat

**Category:** New runtime function + stdlib binding
**Files changed:** `runtime/reflow_runtime.h`, `runtime/reflow_runtime.c`,
`stdlib/string.reflow`

**Problem:** No efficient way to repeat a string N times. Useful for generating
padding, separators, and indentation.

**Fix:** Added `rf_string_repeat` to the runtime — pre-calculates total length,
allocates once, copies in a loop. Exposed as `repeat` in `stdlib/string.reflow`.

**Example:** `examples/string_extras_demo.reflow`

---

## Summary

| # | Item | Category | Status |
|---|------|----------|--------|
| 1 | Match-as-expression implicit return | Compiler fix | Done |
| 2 | Opaque types cross-module | Compiler fix | Done |
| 3 | `\r`/`\0` escape sequences | Already working | N/A |
| 4 | Array get/len | New stdlib | Done |
| 5 | String builder | New type + stdlib | Done |
| 6 | Map module | New stdlib | Done |
| 7 | Continue keyword | New language feature | Done |
| 8 | Else if | Already working | N/A |
| 9 | Auto-coerce Showable in `+` | Language enhancement | Done |
| 10 | Int→int64 widening | Language enhancement | Done |
| 11 | URL encode/decode | New stdlib | Done |
| 12 | Date/time formatting | Stdlib extension | Done |
| 13 | Array concatenation | New stdlib | Done |
| 14 | String repeat | New stdlib | Done |

**Files modified:** 14 compiler/runtime/stdlib files
**New files:** 7 (3 stdlib modules, 4 example programs)
**Spec updates:** `reflow_spec.md` (3 new sections), `stdlib_spec.md` (3 new modules, updated counts)
**Tests:** All 918 existing tests pass. 2 unit tests updated to reflect new semantics.
