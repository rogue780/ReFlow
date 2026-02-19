# tests/conftest.py — pytest integration for golden file and negative tests.
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRAMS_DIR = PROJECT_ROOT / "tests" / "programs"
ERRORS_DIR = PROGRAMS_DIR / "errors"
EXPECTED_DIR = PROJECT_ROOT / "tests" / "expected"
EXPECTED_ERRORS_DIR = PROJECT_ROOT / "tests" / "expected_errors"
EXPECTED_STDOUT_DIR = PROJECT_ROOT / "tests" / "expected_stdout"

PYTHON = sys.executable


def _emit_c(source_path: Path) -> tuple[int, str, str]:
    result = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "main.py"), "emit-c", str(source_path)],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def _collect_golden() -> list[Path]:
    return sorted(PROGRAMS_DIR.glob("*.reflow"))


def _collect_negative() -> list[Path]:
    return sorted(ERRORS_DIR.glob("*.reflow"))


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> pytest.Collector | None:
    if file_path.suffix == ".reflow" and file_path.parent == PROGRAMS_DIR:
        return GoldenTestFile.from_parent(parent, path=file_path)
    if file_path.suffix == ".reflow" and file_path.parent == ERRORS_DIR:
        return NegativeTestFile.from_parent(parent, path=file_path)
    return None


class GoldenTestFile(pytest.File):
    def collect(self) -> list[pytest.Item]:
        return [GoldenTestItem.from_parent(self, name=self.path.stem)]


class GoldenTestItem(pytest.Item):
    def runtest(self) -> None:
        source = PROGRAMS_DIR / f"{self.name}.reflow"
        expected_path = EXPECTED_DIR / f"{self.name}.c"

        exit_code, stdout, stderr = _emit_c(source)
        if exit_code != 0:
            raise GoldenTestException(f"compiler error: {stderr.strip()}")

        if not expected_path.exists():
            expected_path.write_text(stdout)
            pytest.skip(f"new golden file written: {expected_path}")
            return

        expected = expected_path.read_text()
        if stdout != expected:
            raise GoldenTestException(
                f"output differs from {expected_path.name}")

    def repr_failure(self, excinfo: pytest.ExceptionInfo, style: str | None = None) -> str:
        return str(excinfo.value)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.path, None, f"golden:{self.name}"


class NegativeTestFile(pytest.File):
    def collect(self) -> list[pytest.Item]:
        return [NegativeTestItem.from_parent(self, name=self.path.stem)]


class NegativeTestItem(pytest.Item):
    def runtest(self) -> None:
        source = ERRORS_DIR / f"{self.name}.reflow"
        expected_path = EXPECTED_ERRORS_DIR / f"{self.name}.txt"

        if not expected_path.exists():
            pytest.skip(f"no expected error file: {expected_path}")
            return

        exit_code, stdout, stderr = _emit_c(source)
        if exit_code == 0:
            raise NegativeTestException(
                "expected compilation failure but succeeded")

        expected_lines = expected_path.read_text().strip().splitlines()
        expected_error_type = expected_lines[0].strip()
        expected_message_prefix = (expected_lines[1].strip()
                                   if len(expected_lines) > 1 else "")

        error_output = stderr.strip()
        if expected_error_type not in error_output:
            raise NegativeTestException(
                f"expected error type '{expected_error_type}' "
                f"not found in: {error_output}")
        if expected_message_prefix and expected_message_prefix not in error_output:
            raise NegativeTestException(
                f"expected message prefix '{expected_message_prefix}' "
                f"not found in: {error_output}")

    def repr_failure(self, excinfo: pytest.ExceptionInfo, style: str | None = None) -> str:
        return str(excinfo.value)

    def reportinfo(self) -> tuple[Path, int | None, str]:
        return self.path, None, f"negative:{self.name}"


class GoldenTestException(Exception):
    pass


class NegativeTestException(Exception):
    pass
