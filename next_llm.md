# Self-Hosted Flow Compiler — Bootstrap Status

## Progress: 5500 → 2145 errors (61% reduction)

The self-hosted compiler pipeline works end-to-end. Stage 1 (Python → binary)
compiles 15K lines of Flow into ~26K lines of C. The remaining errors are
systematic and well-understood.

## Remaining Error Categories (~2145 raw)

| Category | Count | Fix approach |
|----------|-------|-------------|
| int ↔ LExpr/LType return | 423 | Change fallback LELit("0", LVoid) to zero-init struct |
| FL_Box* ↔ struct | 432 | FL_BOX_DEREF in post-processor (can't do in lowering) |
| Cross-module module ref | 211 | More prefix fixes in post-processor |
| void* compound literal | 135 | Fix compound literal type in lowering |
| LExprBox/StmtBox → void* | 138 | array.push_sized for non-pointer structs |
| Other cascading | ~800 | From above root causes |

## Key files
- `self_hosted/lowering.flow` — most fixes go here
- `fix_stage2.py` — post-processing for FL_BOX_DEREF and field names
- `history.md` — detailed log of all approaches tried

## How to reproduce
```bash
source .venv/bin/activate
python main.py build self_hosted/driver.flow -o flowc_bs1
./flowc_bs1 emit-c self_hosted/driver.flow --stdlib stdlib -o stage2.c
python fix_stage2.py stage2.c  # optional post-processing
clang -w -Wno-implicit-function-declaration -I runtime stage2.c runtime/flow_runtime.c -o flowc_bs2 -lm -lpthread
```
