# compiler/driver.py — Pipeline orchestration.
# No compiler logic. Calls other modules in order.
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.resolver import Resolver
from compiler.typechecker import TypeChecker
from compiler.lowering import Lowerer
from compiler.emitter import Emitter


def _run_pipeline(source_path: str) -> tuple[str, object]:
    """Run pipeline through type checking. Returns (display_path, typed_module).

    The return type for typed_module is TypedModule but typed as object
    to avoid exposing the type in the signature (driver owns no compiler logic).
    """
    path = Path(source_path)
    source = path.read_text()

    # Use a relative display path for the source comment in generated C.
    try:
        display_path = str(path.relative_to(Path.cwd()))
    except ValueError:
        display_path = source_path

    tokens = Lexer(source, display_path).tokenize()
    module = Parser(tokens, display_path).parse()
    resolved = Resolver(module).resolve()
    typed = TypeChecker(resolved).check()
    return display_path, typed


def compile_source(source_path: str, *, output: str | None = None,
                   verbose: bool = False) -> int:
    """Run the full pipeline: lex → parse → resolve → typecheck → lower → emit → clang."""
    display_path, typed = _run_pipeline(source_path)
    lmodule = Lowerer(typed).lower()
    c_source = Emitter(lmodule, display_path).emit()

    if verbose:
        sys.stderr.write(c_source)

    # Determine output binary path.
    if output is None:
        output_path = str(Path(source_path).with_suffix(""))
    else:
        output_path = output

    # Locate runtime files relative to this module.
    project_root = Path(__file__).resolve().parent.parent
    runtime_c = project_root / "runtime" / "reflow_runtime.c"
    runtime_include = project_root / "runtime"

    # Write C source to a temp file and invoke clang.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".c")
    try:
        os.write(tmp_fd, c_source.encode("utf-8"))
        os.close(tmp_fd)

        result = subprocess.run(
            [
                "clang", "-std=c11", "-Wall", "-Wextra",
                "-o", output_path,
                tmp_path,
                str(runtime_c),
                "-I", str(runtime_include),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            return 1

        return 0
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def emit_only(source_path: str, *, output: str | None = None,
              verbose: bool = False) -> int:
    """Run pipeline through emit, output C source."""
    display_path, typed = _run_pipeline(source_path)
    lmodule = Lowerer(typed).lower()
    c_source = Emitter(lmodule, display_path).emit()

    if output is not None:
        Path(output).write_text(c_source)
    else:
        sys.stdout.write(c_source)

    return 0


def check_only(source_path: str, *, verbose: bool = False) -> int:
    """Run pipeline through type checking only."""
    _run_pipeline(source_path)
    return 0
