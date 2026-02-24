#!/usr/bin/env python3
"""ReFlow compiler CLI entry point.

Usage:
    reflow build <file.reflow>          compile to binary via clang
    reflow emit-c <file.reflow>         emit C only, do not compile
    reflow check <file.reflow>          type check only, no output
    --output <path>                     output binary path
    --verbose                           print generated C before compiling
"""
from __future__ import annotations

import argparse
import sys

from compiler.driver import compile_source, emit_only, check_only, run_source
from compiler.errors import ReFlowError


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="reflow",
        description="ReFlow compiler",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # reflow run <file>
    run_parser = subparsers.add_parser("run", help="Compile and run immediately")
    run_parser.add_argument("file", help="Path to .reflow source file")
    run_parser.add_argument("--verbose", "-v", action="store_true",
                            help="Print generated C before compiling")
    run_parser.add_argument("args", nargs="*", help="Arguments passed to the program")

    # reflow build <file>
    build_parser = subparsers.add_parser("build", help="Compile to binary via clang")
    build_parser.add_argument("file", help="Path to .reflow source file")
    build_parser.add_argument("--output", "-o", default=None,
                              help="Output binary path")
    build_parser.add_argument("--verbose", "-v", action="store_true",
                              help="Print generated C before compiling")

    # reflow emit-c <file>
    emit_parser = subparsers.add_parser("emit-c", help="Emit C only, do not compile")
    emit_parser.add_argument("file", help="Path to .reflow source file")
    emit_parser.add_argument("--output", "-o", default=None,
                             help="Output file path (default: stdout)")
    emit_parser.add_argument("--verbose", "-v", action="store_true",
                             help="Verbose output")

    # reflow check <file>
    check_parser = subparsers.add_parser("check", help="Type check only, no output")
    check_parser.add_argument("file", help="Path to .reflow source file")
    check_parser.add_argument("--verbose", "-v", action="store_true",
                              help="Verbose output")

    args = parser.parse_args()

    try:
        match args.command:
            case "run":
                return run_source(args.file, verbose=args.verbose,
                                  args=args.args)
            case "build":
                return compile_source(args.file, output=args.output,
                                      verbose=args.verbose)
            case "emit-c":
                return emit_only(args.file, output=args.output,
                                 verbose=args.verbose)
            case "check":
                return check_only(args.file, verbose=args.verbose)
            case _:
                parser.print_help()
                return 1
    except ReFlowError as e:
        _print_error(e)
        return 1


def _print_error(error: ReFlowError) -> None:
    """Print a formatted compiler error to stderr."""
    kind = type(error).__name__
    print(f"error[{kind}]: {error.message}", file=sys.stderr)
    print(f"  --> {error.file}:{error.line}:{error.col}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
