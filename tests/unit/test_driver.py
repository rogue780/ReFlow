# tests/unit/test_driver.py — Driver unit tests
#
# Covers RT-9-1-1 (compile_source), RT-9-1-2 (emit_only, already done),
# and RT-9-1-3 (check_only).
from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from compiler.driver import compile_source, emit_only, check_only
from compiler.errors import ResolveError, TypeError as FlowTypeError


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HELLO_REFLOW = os.path.join(
    os.path.dirname(__file__), os.pardir, "programs", "hello.flow"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp_flow(content: str) -> str:
    """Write *content* to a temp .flow file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".flow")
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
            self.assertIn("fl_tests_hello_add", c_source)
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
        self.assertIn("int main(int argc, char** argv)", c_source)
        self.assertIn("_fl_runtime_init(argc, argv);", c_source)
        self.assertIn("fl_tests_hello_main();", c_source)

    def test_emit_only_no_entry_point_without_main(self):
        """emit_only on a module without main omits the C entry point."""
        source = 'module test.lib\n\nfn:pure add(x: int, y: int): int = x + y\n'
        path = _write_temp_flow(source)
        try:
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                emit_only(path)
            finally:
                sys.stdout = old_stdout
            c_source = captured.getvalue()
            self.assertNotIn("int main(", c_source)
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
        path = _write_temp_flow(source)
        try:
            with self.assertRaises(FlowTypeError):
                check_only(path)
        finally:
            os.unlink(path)

    def test_check_only_resolve_error(self):
        """check_only raises ResolveError on undefined name."""
        source = 'module test.bad\n\nfn main(): none {\n    let x = y\n}\n'
        path = _write_temp_flow(source)
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
        """compile_source on hello.flow returns 0 and creates an executable."""
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
        self.assertIn("fl_tests_hello_add", output)

    def test_compile_source_default_output_path(self):
        """compile_source with no output uses the source stem as binary name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, "mytest.flow")
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
        path = _write_temp_flow(source)
        try:
            with self.assertRaises(FlowTypeError):
                compile_source(path)
        finally:
            os.unlink(path)

    def test_compile_source_link_failure_no_main(self):
        """compile_source returns 1 when the module has no main function."""
        source = 'module test.lib\n\nfn:pure add(x: int, y: int): int = x + y\n'
        path = _write_temp_flow(source)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, "lib_test")
                rc = compile_source(path, output=out_path)
                self.assertEqual(rc, 1)
        finally:
            os.unlink(path)


HELLO_WORLD_REFLOW = os.path.join(
    os.path.dirname(__file__), os.pardir, "programs", "hello_world.flow"
)


# ---------------------------------------------------------------------------
# Stdlib integration tests
# ---------------------------------------------------------------------------

class TestStdlibIntegration(unittest.TestCase):
    """Tests for stdlib module discovery and native function support."""

    def test_check_only_with_io_import(self):
        """check_only succeeds on a program that imports io."""
        rc = check_only(HELLO_WORLD_REFLOW)
        self.assertEqual(rc, 0)

    def test_emit_hello_world_calls_fl_println(self):
        """emit_only on hello_world.flow emits a direct call to fl_println."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            rc = emit_only(HELLO_WORLD_REFLOW)
        finally:
            sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        c_source = captured.getvalue()
        self.assertIn("fl_println(", c_source)
        # Should NOT contain a mangled io.println wrapper
        self.assertNotIn("fl_io_println", c_source)

    @unittest.skipUnless(shutil.which("clang"), "clang not available")
    def test_compile_and_run_hello_world(self):
        """hello_world.flow compiles, runs, and produces correct output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "hello_world")
            rc = compile_source(HELLO_WORLD_REFLOW, output=out_path)
            self.assertEqual(rc, 0)
            result = subprocess.run(
                [out_path], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "Hello, World!\n")

    def test_extern_fn_parsing(self):
        """Parser correctly handles extern fn declarations."""
        from compiler.lexer import Lexer
        from compiler.parser import Parser
        from compiler.ast_nodes import ExternFnDecl
        source = 'module test.lib\n\nexport extern fn "fl_foo" foo(s:string):none\n'
        tokens = Lexer(source, "test.flow").tokenize()
        mod = Parser(tokens, "test.flow").parse()
        fn = mod.decls[0]
        self.assertIsInstance(fn, ExternFnDecl)
        self.assertEqual(fn.name, "foo")
        self.assertEqual(fn.c_name, "fl_foo")

    def test_unknown_import_raises_error(self):
        """Importing an unknown module raises ResolveError."""
        from compiler.errors import ResolveError as RE
        source = 'module test.bad\n\nimport nonexistent\n\nfn main(): none { }\n'
        path = _write_temp_flow(source)
        try:
            with self.assertRaises(RE):
                check_only(path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Multi-module compilation tests (RB-0-0-1)
# ---------------------------------------------------------------------------

MULTI_MAIN_REFLOW = os.path.join(
    os.path.dirname(__file__), os.pardir, "programs", "multi_main.flow"
)
MULTI_HELPER_REFLOW = os.path.join(
    os.path.dirname(__file__), os.pardir, "programs", "multi_helper.flow"
)


class TestMultiModuleCompilation(unittest.TestCase):
    """Tests for multi-file compilation."""

    def test_check_only_multi_module(self):
        """check_only succeeds on a program that imports a user module."""
        rc = check_only(MULTI_MAIN_REFLOW)
        self.assertEqual(rc, 0)

    def test_emit_multi_module_includes_dependency(self):
        """emit_only on multi_main includes the helper module's functions."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            rc = emit_only(MULTI_MAIN_REFLOW)
        finally:
            sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        c_source = captured.getvalue()
        # Root module header is present.
        self.assertIn('#include "flow_runtime.h"', c_source)
        # Helper module's function is included.
        self.assertIn("fl_tests_programs_multi_helper_double", c_source)
        # Root module's function is included.
        self.assertIn("fl_tests_programs_multi_main_main", c_source)
        # Only one #include (from root).
        self.assertEqual(c_source.count('#include "flow_runtime.h"'), 1)
        # Only one main() entry point.
        self.assertEqual(c_source.count("int main("), 1)
        # Helper is emitted before the root module code.
        helper_pos = c_source.index("fl_tests_programs_multi_helper_double")
        main_pos = c_source.index("fl_tests_programs_multi_main_main")
        self.assertLess(helper_pos, main_pos)

    def test_emit_multi_module_has_from_comment(self):
        """emit_only on multi_main includes a '/* From: ...' comment."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            emit_only(MULTI_MAIN_REFLOW)
        finally:
            sys.stdout = old_stdout
        c_source = captured.getvalue()
        self.assertIn("/* From: tests/programs/multi_helper.flow */", c_source)

    @unittest.skipUnless(shutil.which("clang"), "clang not available")
    def test_compile_and_run_multi_module(self):
        """multi_main.flow compiles, runs, and produces correct output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "multi_main")
            rc = compile_source(MULTI_MAIN_REFLOW, output=out_path)
            self.assertEqual(rc, 0)
            result = subprocess.run(
                [out_path], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "42\n")


class TestMultiModuleErrors(unittest.TestCase):
    """Tests for multi-module error detection."""

    def test_circular_import_detected(self):
        """Circular imports raise ResolveError."""
        circ_a = os.path.join(
            os.path.dirname(__file__), os.pardir, "programs", "errors",
            "circular_import_a.flow"
        )
        with self.assertRaises(ResolveError) as cm:
            check_only(circ_a)
        self.assertIn("circular import detected", cm.exception.message)

    def test_missing_import_file_error(self):
        """Importing a nonexistent user module raises ResolveError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            main_path = os.path.join(tmpdir, "main.flow")
            with open(main_path, "w") as f:
                f.write(
                    'module main\n\n'
                    'import helpers.missing\n\n'
                    'fn main(): none { }\n'
                )
            with self.assertRaises(ResolveError) as cm:
                check_only(main_path)
            self.assertIn("cannot find module", cm.exception.message)
            self.assertIn("helpers.missing", cm.exception.message)


class TestProjectRootInference(unittest.TestCase):
    """Tests for _infer_project_root."""

    def test_infer_root_no_module_path(self):
        """Empty module path returns file's parent directory."""
        from compiler.driver import _infer_project_root
        from pathlib import Path
        p = Path("/a/b/c/test.flow")
        self.assertEqual(_infer_project_root(p, []), Path("/a/b/c"))

    def test_infer_root_with_module_path(self):
        """Module path strips nesting from parent directory."""
        from compiler.driver import _infer_project_root
        from pathlib import Path
        # File at /proj/src/math/vector.flow with module math.vector
        p = Path("/proj/src/math/vector.flow")
        root = _infer_project_root(p, ["math", "vector"])
        self.assertEqual(root, Path("/proj/src/math").resolve().parent)

    def test_infer_root_deep_path(self):
        """Deep module path correctly strips multiple segments."""
        from compiler.driver import _infer_project_root
        from pathlib import Path
        # File at /proj/a/b/c.flow with module a.b.c
        p = Path("/proj/a/b/c.flow")
        root = _infer_project_root(p, ["a", "b", "c"])
        self.assertEqual(root, Path("/proj").resolve())


if __name__ == "__main__":
    unittest.main()
