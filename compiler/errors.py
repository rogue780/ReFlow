# compiler/errors.py — Error type definitions only.
# No logic.
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReFlowError(Exception):
    """Base class for all compiler errors."""
    message: str
    file: str
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}: {self.message}"


@dataclass
class LexError(ReFlowError):
    """Bad character, unterminated literal."""
    pass


@dataclass
class ParseError(ReFlowError):
    """Syntax error."""
    pass


@dataclass
class ResolveError(ReFlowError):
    """Undefined name, scope violation."""
    pass


@dataclass
class TypeError(ReFlowError):
    """Type mismatch, exhaustiveness, purity."""
    pass


@dataclass
class EmitError(ReFlowError):
    """Malformed LIR."""
    pass
