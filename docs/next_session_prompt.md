# Prompt for Next Session: Complete Refcounting for Zero Memory Leaks

## Context

You are continuing work on the Flow compiler's memory management system. The goal is **zero memory leaks** — Flow must be memory-safe by design through automatic refcounting.

The branch is `story/RT-11-self-hosted-compiler`. The previous session implemented scope-exit cleanup for refcounted locals (strings, arrays, maps, closures), struct-construction retains, and string temp hoisting. RSS dropped from 873 MB to 846 MB, but ASAN still reports **1,035,247 bytes leaked in 2,989 allocations**.

## The Problem

The refcounting system is **incomplete**. It handles top-level locals (arrays, maps, strings) at scope exit, but does NOT handle refcounted **fields inside structs**. When a struct goes out of scope, its array/map/string fields leak.

Read `docs/memory_leak_analysis.md` for the full ASAN breakdown and implementation plan.

## What To Do

### Step 1: Understand the current refcounting machinery

Read these sections of `compiler/lowering.py`:
- `_container_locals` — list of 4-tuples `(name, c_type, release_fn, depth)` tracking locals for scope-exit release
- `_get_release_fn()` — maps type to release function name (`fl_string_release`, `fl_array_release`, `fl_map_release`)
- `_inject_scope_cleanup()` — generates block-scoped release calls
- The scope-exit cleanup code in `_lower_fn_decl` and `_lower_block` that emits release calls before returns

### Step 2: Implement struct field release at scope exit

When a struct-typed local goes out of scope, the lowering should generate release calls for each of its refcounted fields. This means:

1. When registering a local in `_container_locals`, if the local's type is a struct (TNamed pointing to a TypeDecl, or a type with known fields), also record its field types.

2. At scope exit, instead of just calling `fl_string_release(local)` etc., generate per-field release calls:
   ```c
   // For a local `rm` of type ResolvedModule with fields: symbols (map), scope_names (array), ...
   fl_map_release(rm.symbols);
   fl_array_release(rm.scope_names);
   // etc.
   ```

3. Handle complications:
   - Fields that were "moved" into a return value should NOT be released (the return value now owns them)
   - Recursive structs need cycle detection
   - Sum type variants have different fields per variant
   - Nested structs need recursive descent

### Step 3: Verify array.push reassignment release

Check that `arr = array.push(arr, val)` in `_lower_assign` properly releases the old array before reassignment. The lowering's release-on-reassign logic should handle this, but verify with ASAN.

### Step 4: In-place array.push / map.set for :mut (optimization)

Same pattern as `fl_string_append` — detect `arr = array.push(arr, val)` for `:mut` bindings and generate `fl_array_push_inplace(&arr, val)` that reuses the buffer when refcount == 1.

## Key Constraint

The user's stated goal: **"This language must be safe from memory leaks."** This is not an optimization — it's a correctness requirement. The refcounting must be complete and automatic. No `defer`, no manual cleanup, no `Releasable` interface. The compiler must generate all necessary retain/release calls.

## How To Verify

```bash
# Build with ASAN leak detection
python main.py emit-c self_hosted/driver.flow > /tmp/driver_leak.c
clang -g -fsanitize=address -O0 -I runtime /tmp/driver_leak.c runtime/flow_runtime.c -o /tmp/driver_leak -lm

# Run with leak detection on a simple program
ASAN_OPTIONS=detect_leaks=1 /tmp/driver_leak emit-c tests/programs/hello_world.flow 2>/tmp/leak_report.txt > /dev/null

# Check summary
grep "SUMMARY" /tmp/leak_report.txt
# Goal: 0 bytes leaked

# Also run make test to ensure no regressions
make test
```

## Files To Modify

- `compiler/lowering.py` — All refcounting logic (scope-exit, struct field release)
- `runtime/flow_runtime.c` — Possibly add `fl_array_push_inplace`, `fl_map_set_inplace`
- `runtime/flow_runtime.h` — Declarations for any new runtime functions
- `tests/expected/*.c` — Golden files will need regeneration after lowering changes
