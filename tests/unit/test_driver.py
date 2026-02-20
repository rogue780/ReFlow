# tests/unit/test_driver.py — Driver unit tests
#
# Covers RT-9-1-1 (compile_source), RT-9-1-2 (emit_only, already done),
# and RT-9-1-3 (check_only).
from __future__ import annotations

import io
import os
import shutil
import stat
import sys
import tempfile
import unittest

from compiler.driver import compile_source, emit_only, check_only
from compiler.errors import ResolveError, TypeError as ReFlowTypeError


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HELLO_REFLOW = os.path.join(
    os.path.dirname(__file__), os.pardir, "programs", "hello.reflow"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp_reflow(content: str) -> str:
    """Write *content* to a temp .reflow file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".reflow")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# RT-9-1-2: emit_only (already implemented, regression tests)
# ---------------------------------------------------------------------------

class TestEmitOnly(unittest.TestCase):
    """Tests for emit_only()."""

    def test_emit_only_returns_zero(self):
        """emit_only on a valid program returns 0."""
        with tempfile.NamedTemporaryFile(suffix=".c", delete=False) as f:
            out_path = f.name
        try:
            rc = emit_only(HELLO_REFLOW, output=out_path)
            self.assertEqual(rc, 0)
            c_source = open(out_path).read()
            self.assertIn("#include", c_source)
            self.assertIn("rf_tests_hello_add", c_source)
        finally:
            os.unlink(out_path)

    def test_emit_only_stdout(self):
        """emit_only with no output writes to stdout."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            rc = emit_only(HELLO_REFLOW)
        finally:
            sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        self.assertIn("#include", captured.getvalue())

    def test_emit_only_includes_entry_point(self):
        """emit_only on a module with main includes the C entry point."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            emit_only(HELLO_REFLOW)
        finally:
            sys.stdout = old_stdout
        c_source = captured.getvalue()
        self.assertIn("int main(void)", c_source)
        self.assertIn("rf_tests_hello_main();", c_source)

    def test_emit_only_no_entry_point_without_main(self):
        """emit_only on a module without main omits the C entry point."""
        source = 'module test.lib\n\npure fn add(x: int, y: int): int = x + y\n'
        path = _write_temp_reflow(source)
        try:
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                emit_only(path)
            finally:
                sys.stdout = old_stdout
            c_source = captured.getvalue()
            self.assertNotIn("int main(void)", c_source)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# RT-9-1-3: check_only
# ---------------------------------------------------------------------------

class TestCheckOnly(unittest.TestCase):
    """Tests for check_only()."""

    def test_check_only_success(self):
        """check_only on a valid program returns 0."""
        rc = check_only(HELLO_REFLOW)
        self.assertEqual(rc, 0)

    def test_check_only_type_error(self):
        """check_only raises TypeError on a program with a type error."""
        # let x: string = 5 is a type mismatch the type checker catches.
        source = 'module test.bad\n\nfn main(): none {\n    let x: string = 5\n}\n'
        path = _write_temp_reflow(source)
        try:
            with self.assertRaises(ReFlowTypeError):
                check_only(path)
        finally:
            os.unlink(path)

    def test_check_only_resolve_error(self):
        """check_only raises ResolveError on undefined name."""
        source = 'module test.bad\n\nfn main(): none {\n    let x = y\n}\n'
        path = _write_temp_reflow(source)
        try:
            with self.assertRaises(ResolveError):
                check_only(path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# RT-9-1-1: compile_source
# ---------------------------------------------------------------------------

@unittest.skipUnless(shutil.which("clang"), "clang not available")
class TestCompileSource(unittest.TestCase):
    """Tests for compile_source(). Requires clang."""

    def test_compile_source_produces_binary(self):
        """compile_source on hello.reflow returns 0 and creates an executable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "hello_test")
            rc = compile_source(HELLO_REFLOW, output=out_path)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(out_path))
            mode = os.stat(out_path).st_mode
            self.assertTrue(mode & stat.S_IXUSR)

    def test_compile_source_custom_output(self):
        """compile_source respects --output path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = os.path.join(tmpdir, "my_binary")
            rc = compile_source(HELLO_REFLOW, output=custom)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(custom))

    def test_compile_source_verbose(self):
        """compile_source with verbose=True writes C source to stderr."""
        captured = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, "hello_verbose")
                rc = compile_source(HELLO_REFLOW, output=out_path,
                                    verbose=True)
        finally:
            sys.stderr = old_stderr
        self.assertEqual(rc, 0)
        output = captured.getvalue()
        self.assertIn("#include", output)
        self.assertIn("rf_tests_hello_add", output)

    def test_compile_source_default_output_path(self):
        """compile_source with no output uses the source stem as binary name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "mytest.reflow")
            with open(HELLO_REFLOW) as f:
                content = f.read()
            with open(src, "w") as f:
                f.write(content)
            rc = compile_source(src)
            expected_bin = os.path.join(tmpdir, "mytest")
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(expected_bin))
            os.unlink(expected_bin)

    def test_compile_source_type_error(self):
        """compile_source raises TypeError before clang is ever invoked."""
        source = 'module test.bad\n\nfn main(): none {\n    let x: string = 5\n}\n'
        path = _write_temp_reflow(source)
        try:
            with self.assertRaises(ReFlowTypeError):
                compile_source(path)
        finally:
            os.unlink(path)

    def test_compile_source_link_failure_no_main(self):
        """compile_source returns 1 when the module has no main function."""
        source = 'module test.lib\n\npure fn add(x: int, y: int): int = x + y\n'
        path = _write_temp_reflow(source)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, "lib_test")
                rc = compile_source(path, output=out_path)
                self.assertEqual(rc, 1)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
