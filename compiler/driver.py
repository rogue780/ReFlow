# compiler/driver.py — Pipeline orchestration.
# No compiler logic. Calls other modules in order.
from __future__ import annotations


def compile_source(source_path: str, *, output: str | None = None,
                   verbose: bool = False) -> int:
    """Run the full pipeline: lex → parse → resolve → typecheck → lower → emit → clang."""
    # TODO: implement in RT-9-1-1
    raise NotImplementedError("compile_source not yet implemented")


def emit_only(source_path: str, *, output: str | None = None,
              verbose: bool = False) -> int:
    """Run pipeline through emit, output C source."""
    # TODO: implement in RT-9-1-2
    raise NotImplementedError("emit_only not yet implemented")


def check_only(source_path: str, *, verbose: bool = False) -> int:
    """Run pipeline through type checking only."""
    # TODO: implement in RT-9-1-3
    raise NotImplementedError("check_only not yet implemented")
