# compiler/driver.py — Pipeline orchestration.
# No compiler logic. Calls other modules in order.
from __future__ import annotations

import sys
from pathlib import Path

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.resolver import Resolver
from compiler.typechecker import TypeChecker
from compiler.lowering import Lowerer
from compiler.emitter import Emitter


def compile_source(source_path: str, *, output: str | None = None,
                   verbose: bool = False) -> int:
    """Run the full pipeline: lex → parse → resolve → typecheck → lower → emit → clang."""
    # TODO: implement in RT-9-1-1
    raise NotImplementedError("compile_source not yet implemented")


def emit_only(source_path: str, *, output: str | None = None,
              verbose: bool = False) -> int:
    """Run pipeline through emit, output C source."""
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
    lmodule = Lowerer(typed).lower()
    c_source = Emitter(lmodule, display_path).emit()

    if output is not None:
        Path(output).write_text(c_source)
    else:
        sys.stdout.write(c_source)

    return 0


def check_only(source_path: str, *, verbose: bool = False) -> int:
    """Run pipeline through type checking only."""
    # TODO: implement in RT-9-1-3
    raise NotImplementedError("check_only not yet implemented")
