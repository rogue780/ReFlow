# Flow Engineer Memory

## Key Runtime Facts
- `:<` operator creates **non-threaded** (lazy, same-thread) coroutines by default
- Only **receivable coroutines** (first param `inbox: stream<T>`) get real threads via `fl_coroutine_new_threaded`
- For concurrent server+client patterns, the server MUST be a receivable coroutine to run on a separate thread
- `with capacity(N)` is in the spec but NOT implemented in the compiler — omit it

## Codegen Workarounds
- `throw` as the last statement in a non-void function generates `return _fl_throw(...)` which won't compile (void return in non-void function). Fix: add an unreachable `return` after the throw
- Sum type match arms that bind the same variable name across arms (e.g., `Pass(code)` and `Warn(code, r)`) cause C `redefinition` errors. Fix: use unique names per arm (`pass_code`, `warn_code`)
- `throw` inside match arm tail positions also generates invalid `return _fl_throw(...)`. Fix: restructure with `if-let` instead of match

## Net Module
- All net functions return `Socket?` (option), not result types
- `net.listen` returns `Socket?`, `net.accept` returns `Socket?`, `net.connect` returns `Socket?`
- `net.read` returns `array<byte>?`, `net.write_string` returns `bool`
- `time.sleep_ms(ms: int)` exists (not `time.sleep`)
- `SO_RCVTIMEO` on listener socket controls accept timeout

## Style Conventions
- Type annotations have NO space after the colon: `name:type` not `name: type`
- Applies to params (`x:int`), return types (`:int`), let bindings (`let x:int = 1`), struct fields (`x:float`)
- Prefer `??` and `?` over nested `match` for option unwrapping — avoids deeply nested `match`/`none: {}` patterns
- `??` for default values: `array.get(items, i) ?? ""`
- `?` for propagation in functions returning option/result

## Match Patterns with Imported Modules
- Match patterns on imported sum types use BARE variant names (no module prefix)
- e.g., `import self_hosted.lir as lir` → match patterns use `LInt(w, s):` NOT `lir.LInt(w, s):`
- But CONSTRUCTOR CALLS use the module prefix: `lir.LInt(width:32, is_signed:true)`
- This applies even when the type is from a module imported with `as` alias

## Array Stdlib Functions
- `array.set` does NOT exist — use `array.put(arr, idx, val)` to replace an element
- `array.size(arr)` for length (generic, works for any type)
- `array.push(arr, val)` returns NEW array — must reassign (generic, for pointer/heap types)
- `array.push_int(arr, val)` for `array<int>` — use explicitly for int arrays
- `array.get(arr, i)` returns `string?` for string arrays
- `array.get_any(arr, i)` returns `T?` for any type — use for records/sum types
- `array.get_int(arr, i)` returns `int?` for int arrays — use explicitly
- `array.put(arr, idx, val)` returns NEW array with element replaced (uses generic push internally — safe for pointer types but rebuild manually for int arrays)
- `array.slice` exists for slicing

## Multi-Module Compilation
- Empty map literal `{}` is parsed as empty record, NOT empty map — use `map.new()` instead
- Cross-module user-defined types require `imported_typed` dict passed to TypeChecker
- `TypeInfo.module_path` carries the origin module path for correct mangling
- Root module type_defs are deduplicated against dependency module type_defs in driver
- Positional struct construction `Type(a, b)` resolves as `SymbolKind.TYPE` (not CONSTRUCTOR)
- Struct brace syntax `Type { field: val }` is the supported/tested construction form
- `_build_dependency_graph` has stdlib/ fallback for non-stdlib user-written modules (like http)
- Stdlib-to-stdlib imports: `_get_stdlib_typed` now passes `imported_modules` and `imported_typed` to Resolver/TypeChecker
- `_inject_compilable_stdlib` discovers transitive stdlib deps and topologically sorts them
- Extern fn protos: lowering skips forward declarations for `fl_*` names (already in flow_runtime.h)
- Migrated to pure Flow: csv.flow, conv.flow (parsing), path.flow (string ops), char.flow, testing.flow, math.flow (libm)

## Architecture Priority: Minimize Runtime
**The implementation priority order for ALL stdlib/language features is:**
1. **Native Flow** — write it in pure Flow. If the language can't express it, improve the compiler to enable it.
2. **Extern library FFI** — bind to existing C libraries (libc, OpenSSL, etc.) via `extern fn`. If the FFI can't express it, improve the FFI system.
3. **Runtime `fl_*` functions** — LAST RESORT only. Every `fl_*` function is tech debt toward self-hosting.

## HTTP Module (stdlib/http.flow)
- Pure Flow implementation using net sockets — no C native functions
- Returns `HttpResponse?` (option) for all request methods
- Supports GET, POST, PUT, DELETE with custom headers
- HTTPS support via ssl.flow module (TLS via direct OpenSSL FFI)

## FFI System (implemented)
- Three `extern` forms: `extern lib "name"`, `extern type Name`, `extern fn c_name(params):RetType`
- `ptr` builtin type = opaque `void*`, no dereference/arithmetic, `none` assignable to `ptr` (NULL)
- Extern fn calls use literal C name (no mangling) — bypass `mangler.py`
- Extern types lower to `LPtr(LVoid())`
- `_lower_extern_type()` handles TFn→LFnPtr (not FL_Closure) for extern fn proto params
- `_rewrite_extern_fn_args()` converts named FnDecl args to raw function pointers for callbacks
- Driver collects `-l` flags from ExternLibDecl across all modules
- System header conflicts: `extern fn strlen` etc. will conflict with `<string.h>` — avoid binding standard C functions directly
- `none` literal types as `TOption(TAny())`, NOT `TNone` — can't pass `none` where `ptr` is expected. Use `mem.null()` instead
- `mem.flow` provides: `alloc`, `free`, `read_byte`, `write_byte`, `read_int`, `is_null`, `null`, `to_option`
- Negative error test format: line 1 = error class name (e.g., `TypeError`), line 2 = message substring
- `string.to_cptr(s)` / `string.from_cptr(p, len)` for string↔ptr marshaling

## Self-Hosted Compiler (Epic 11)
- Branch: `story/RT-11-self-hosted-compiler`
- Completed: `errors.flow`, `ast.flow`, `mangler.flow`, `lexer.flow`, `parser.flow`, `resolver.flow`, `typechecker.flow`, `emitter.flow`, `lowering.flow`, `driver.flow`
- Remaining: bootstrap main (main.flow or integrating driver into executable)
- Cross-module sum type variant constructors: parsed as MethodCall (not FieldAccess+Call). Required lowering fix to handle CONSTRUCTOR symbols from MethodCall.
- Typechecker returns TAny for cross-module variant constructors. Lowering uses `_find_variant_sum_type()` to locate parent TSum type.
- Circular by-value sum type dependencies broken with int IDs: `TSizedType.capacity_id:int`, `ECast.target_id:int`, `PLiteral.value_id:int`
- Array literals with sum type elements don't work (void* cast fails). Use `array.push()` instead.
- Emitter has topo sort (Kahn's algorithm) for type definition ordering.
- `_is_recursive_sum_field()` now accepts optional AST TypeExpr for cross-module recursive field detection.

### Compiler Bugs Fixed During Typechecker Port
- **Resolver BindPattern shadowing**: Fieldless variant patterns like `TCString:` in match arms created LOCAL symbols that shadowed CONSTRUCTOR symbols. Fix: check if BindPattern name is a known CONSTRUCTOR before defining LOCAL.
- **Lowering _find_sum_type_module during monomorphization**: Used `self._module_path` (changes during mono) instead of `self._module.path` (actual module). Caused wrong mangling (e.g., `fl_array_TCTypeBox` instead of `fl_self_hosted_typechecker_TCTypeBox`).
- **Lowering TTypeVar match subjects**: Cross-module sum type fields (e.g., `arm.pattern` where Pattern is from `self_hosted.ast`) typed as TTypeVar, lowered as `void*`. Fix: `_resolve_tvar_to_sum()` builds TSum from AST TypeDecl.
- **Lowering _type_name_str missing module**: TNamed/TSum in mono function suffixes used bare type name. Fix: include module path for fully-qualified C names.

### Flow Language Gotchas (for writing large .flow files)
- `module`, `err`, `signed`, `alias` are reserved keywords — don't use as field/variable names
- `array.new()` doesn't exist — use `[]` for empty arrays
- `map.contains()` doesn't exist — use `map.has()`
- `array.length()` doesn't exist — use `array.size()`
- `conv.int_to_string()` doesn't exist — use `conv.to_string()`
- `array.push()`/`map.set()` return NEW values — must reassign: `arr = array.push(arr, val)`
- No `ast.` prefix in match patterns (auto-imported), but need `ast.` for constructor CALLS
- `type Foo:mut` needed when fields are mutated (e.g., TypeInfo, InterfaceInfo)
- `array.set` does NOT exist — use `array.put(arr, idx, val)`
- Match patterns for imported sum types: use BARE variant name (no module prefix)

## Testing Patterns
- E2E app tests go in `tests/programs/app_*.flow` with expected stdout in `tests/expected_stdout/app_*.txt`
- Golden C files go in `tests/expected/app_*.c`
- Port 39876 used for healthcheck test mock server

# currentDate
Today's date is 2026-03-02.
