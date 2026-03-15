# Self-Hosted Flow Compiler — Bootstrap Status

## Progress: 5500 → 516 errors (91% reduction)

The self-hosted compiler pipeline works end-to-end. Stage 1 compiles
15K lines of Flow into 26K lines of C. With fix_stage2.py post-processing,
516 hard clang errors remain.

## How to reproduce
```bash
source .venv/bin/activate
python main.py build self_hosted/driver.flow -o flowc_bs1
./flowc_bs1 emit-c self_hosted/driver.flow --stdlib stdlib -o stage2.c
python fix_stage2.py stage2.c
clang -w -I runtime stage2.c runtime/flow_runtime.c -o flowc_bs2 -lm -lpthread
```

## Remaining 516 errors

| Category | Count | Root cause |
|----------|-------|-----------|
| FL_Box* ↔ Expr (match destr) | ~90 | FL_BOX_DEREF needed but post-processor over-matches non-recursive fields |
| void* ← struct assignment | ~45 | void* compound literal fix creates mismatches where FL_Box* expected |
| TCTypeBox → void* | 43 | map.get/array.push for typechecker box types |
| void member reference | 52 | Cascade from FL_Box errors |
| EmitState :mut | 22 | Local EmitState passed to pointer-expecting functions |
| FL_Option_ptr mismatch | 18 | map.get/scope_lookup returns FL_Option_ptr for struct types |
| Symbol/SumVariantDecl → void* | ~29 | Push patterns for resolver structs |
| Other cascading | ~217 | From above root causes |

## Key files
- `self_hosted/lowering.flow` — main lowering with all codegen fixes
- `fix_stage2.py` — post-processing script for FL_BOX_DEREF, field names, push_sized
- `history.md` — detailed log of all approaches and findings

## What would fix the most remaining errors

### 1. FL_BOX_DEREF precision (90 errors)
The post-processor applies FL_BOX_DEREF to Expr fields like `value`, `inner` etc.
but some of these are NOT recursive (e.g., SLet.value is an Expr by VALUE, not FL_Box*).
Need containing-type awareness: only apply FL_BOX_DEREF when the SUBJECT is the same
type as the FIELD (self-recursive).

### 2. TCTypeBox push patterns (43 errors)
Similar to LExprBox/LStmtBox push_ptr→push_sized, but for map operations and ternary
operator contexts.

### 3. EmitState :mut (22 errors)
The emit() function creates `st` as a local value but passes to :mut functions.
Need to convert `st` to a pointer in emit() and emit_with_deferred() bodies only.
