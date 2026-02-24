#!/usr/bin/env python3
"""Flow test runner for golden file, E2E, and negative tests.

Usage:
    python tests/run_tests.py              # run all test types
    python tests/run_tests.py --golden     # golden file tests only
    python tests/run_tests.py --e2e        # end-to-end execution tests only
    python tests/run_tests.py --negative   # negative compile tests only

Golden file tests:
    For each .flow in tests/programs/ (not in errors/), compile with emit-c
    and diff against tests/expected/<name>.c. If no expected file exists, write
    the generated output as the new golden file and mark as "new".

E2E tests:
    For each .flow in tests/programs/ that has a corresponding
    tests/expected_stdout/<name>.txt, compile, run, and diff stdout.

Negative tests:
    For each .flow in tests/programs/errors/, compile and verify the compiler
    exits with an error whose type and message prefix match
    tests/expected_errors/<name>.txt.
"""
from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRAMS_DIR = PROJECT_ROOT / "tests" / "programs"
ERRORS_DIR = PROGRAMS_DIR / "errors"
EXPECTED_DIR = PROJECT_ROOT / "tests" / "expected"
EXPECTED_STDOUT_DIR = PROJECT_ROOT / "tests" / "expected_stdout"
EXPECTED_ERRORS_DIR = PROJECT_ROOT / "tests" / "expected_errors"

PYTHON = sys.executable


class TestResult:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.new: list[str] = []
        self.skipped: list[str] = []

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.new)

    def report(self) -> int:
        """Print summary and return exit code."""
        if self.new:
            print(f"\n  NEW ({len(self.new)}):")
            for name in self.new:
                print(f"    {name}")

        if self.failed:
            print(f"\n  FAILED ({len(self.failed)}):")
            for name, reason in self.failed:
                print(f"    {name}: {reason}")

        passed = len(self.passed)
        failed = len(self.failed)
        new = len(self.new)
        print(f"\n  {passed} passed, {failed} failed, {new} new"
              f" ({self.total} total)")

        return 0 if failed == 0 else 1


def emit_c(source_path: Path) -> tuple[int, str, str]:
    """Run the compiler in emit-c mode. Returns (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "main.py"), "emit-c", str(source_path)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def build_and_run(source_path: Path) -> tuple[int, str, str]:
    """Compile and run a program. Returns (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "main.py"), "build", str(source_path),
         "-o", "/tmp/fl_test_binary"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        return result.returncode, result.stdout, result.stderr

    run_result = subprocess.run(
        ["/tmp/fl_test_binary"],
        capture_output=True,
        text=True,
    )
    return run_result.returncode, run_result.stdout, run_result.stderr


def run_golden_tests(result: TestResult) -> None:
    """Run golden file tests: emit-c and diff against expected C output."""
    print("Golden file tests:")
    sources = sorted(PROGRAMS_DIR.glob("*.flow"))
    if not sources:
        print("  (no test programs found)")
        return

    for source in sources:
        name = source.stem
        expected_path = EXPECTED_DIR / f"{name}.c"

        exit_code, stdout, stderr = emit_c(source)

        if exit_code != 0:
            result.failed.append((name, f"compiler error: {stderr.strip()}"))
            print(f"  FAIL  {name}")
            continue

        if not expected_path.exists():
            expected_path.write_text(stdout)
            result.new.append(name)
            print(f"  NEW   {name} (golden file written)")
            continue

        expected = expected_path.read_text()
        if stdout == expected:
            result.passed.append(name)
            print(f"  PASS  {name}")
        else:
            diff = "".join(difflib.unified_diff(
                expected.splitlines(keepends=True),
                stdout.splitlines(keepends=True),
                fromfile=f"expected/{name}.c",
                tofile=f"actual/{name}.c",
            ))
            result.failed.append((name, f"output differs:\n{diff}"))
            print(f"  FAIL  {name}")


def run_e2e_tests(result: TestResult) -> None:
    """Run end-to-end tests: compile, run, diff stdout."""
    print("End-to-end tests:")
    expected_files = sorted(EXPECTED_STDOUT_DIR.glob("*.txt"))
    if not expected_files:
        print("  (no E2E tests found)")
        return

    for expected_path in expected_files:
        name = expected_path.stem
        source = PROGRAMS_DIR / f"{name}.flow"

        if not source.exists():
            result.skipped.append(name)
            print(f"  SKIP  {name} (no source file)")
            continue

        exit_code, stdout, stderr = build_and_run(source)

        if exit_code != 0:
            result.failed.append((name, f"runtime error: {stderr.strip()}"))
            print(f"  FAIL  {name}")
            continue

        expected = expected_path.read_text()
        if stdout == expected:
            result.passed.append(name)
            print(f"  PASS  {name}")
        else:
            diff = "".join(difflib.unified_diff(
                expected.splitlines(keepends=True),
                stdout.splitlines(keepends=True),
                fromfile=f"expected_stdout/{name}.txt",
                tofile=f"actual stdout",
            ))
            result.failed.append((name, f"stdout differs:\n{diff}"))
            print(f"  FAIL  {name}")


def run_negative_tests(result: TestResult) -> None:
    """Run negative tests: programs that should fail to compile."""
    print("Negative tests:")
    sources = sorted(ERRORS_DIR.glob("*.flow"))
    if not sources:
        print("  (no negative tests found)")
        return

    for source in sources:
        name = source.stem
        expected_path = EXPECTED_ERRORS_DIR / f"{name}.txt"

        if not expected_path.exists():
            result.skipped.append(name)
            print(f"  SKIP  {name} (no expected error file)")
            continue

        exit_code, stdout, stderr = emit_c(source)

        if exit_code == 0:
            result.failed.append((name, "expected compilation failure but succeeded"))
            print(f"  FAIL  {name}")
            continue

        expected_lines = expected_path.read_text().strip().splitlines()
        if len(expected_lines) < 1:
            result.failed.append((name, "expected error file is empty"))
            print(f"  FAIL  {name}")
            continue

        expected_error_type = expected_lines[0].strip()
        expected_message_prefix = expected_lines[1].strip() if len(expected_lines) > 1 else ""

        error_output = stderr.strip()
        type_ok = expected_error_type in error_output
        msg_ok = (not expected_message_prefix
                  or expected_message_prefix in error_output)

        if type_ok and msg_ok:
            result.passed.append(name)
            print(f"  PASS  {name}")
        else:
            reason = f"expected [{expected_error_type}] "
            if expected_message_prefix:
                reason += f"with '{expected_message_prefix}' "
            reason += f"but got: {error_output}"
            result.failed.append((name, reason))
            print(f"  FAIL  {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Flow test runner")
    parser.add_argument("--golden", action="store_true", help="Run golden file tests only")
    parser.add_argument("--e2e", action="store_true", help="Run E2E tests only")
    parser.add_argument("--negative", action="store_true", help="Run negative tests only")
    args = parser.parse_args()

    run_all = not (args.golden or args.e2e or args.negative)

    result = TestResult()

    if run_all or args.golden:
        run_golden_tests(result)
    if run_all or args.e2e:
        run_e2e_tests(result)
    if run_all or args.negative:
        run_negative_tests(result)

    return result.report()


if __name__ == "__main__":
    sys.exit(main())
