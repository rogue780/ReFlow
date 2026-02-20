"""Unit tests for compiler/mangler.py."""
from __future__ import annotations

import unittest

from compiler.mangler import (
    mangle,
    mangle_builtin_type,
    mangle_stream_frame,
    mangle_stream_next,
    mangle_stream_free,
    mangle_closure_frame,
    BUILTIN_TYPE_MAP,
)
from compiler.errors import EmitError


class TestMangleModuleOnly(unittest.TestCase):
    """Module-only mangling: dots become underscores, rf_ prefix."""

    def test_single_component(self) -> None:
        self.assertEqual(mangle("main"), "rf_main")

    def test_two_components(self) -> None:
        self.assertEqual(mangle("math.vector"), "rf_math_vector")

    def test_three_components(self) -> None:
        self.assertEqual(mangle("pipeline.orders.csv"), "rf_pipeline_orders_csv")


class TestMangleModuleAndType(unittest.TestCase):
    """Module + type name mangling."""

    def test_simple_type(self) -> None:
        self.assertEqual(mangle("math.vector", "Vec3"), "rf_math_vector_Vec3")

    def test_single_module_type(self) -> None:
        self.assertEqual(mangle("config", "DB"), "rf_config_DB")


class TestMangleModuleTypeAndMethod(unittest.TestCase):
    """Module + type + method mangling."""

    def test_method(self) -> None:
        self.assertEqual(
            mangle("math.vector", "Vec3", "dot"),
            "rf_math_vector_Vec3_dot",
        )

    def test_constructor(self) -> None:
        self.assertEqual(
            mangle("domain.order", "Order", "from_raw"),
            "rf_domain_order_Order_from_raw",
        )


class TestMangleTopLevelFunction(unittest.TestCase):
    """Top-level function mangling (no type name)."""

    def test_function(self) -> None:
        self.assertEqual(
            mangle("pipeline.orders", fn_name="run"),
            "rf_pipeline_orders_run",
        )

    def test_single_module_function(self) -> None:
        self.assertEqual(mangle("main", fn_name="entry"), "rf_main_entry")


class TestMangleMultiplePathComponents(unittest.TestCase):
    """Deep module paths."""

    def test_deep_path(self) -> None:
        self.assertEqual(
            mangle("a.b.c.d", "T", "m"),
            "rf_a_b_c_d_T_m",
        )

    def test_deep_path_function(self) -> None:
        self.assertEqual(
            mangle("a.b.c.d.e", fn_name="f"),
            "rf_a_b_c_d_e_f",
        )


class TestMangleReservedCIdentifiers(unittest.TestCase):
    """C reserved words are safe after rf_ prefix mangling."""

    def test_return_as_function_name(self) -> None:
        result = mangle("test", fn_name="return", file="t.reflow", line=1, col=1)
        self.assertEqual(result, "rf_test_return")

    def test_int_as_function_name(self) -> None:
        result = mangle("test", fn_name="int", file="t.reflow", line=1, col=1)
        self.assertEqual(result, "rf_test_int")

    def test_static_as_type_name(self) -> None:
        result = mangle("test", "static", file="t.reflow", line=1, col=1)
        self.assertEqual(result, "rf_test_static")

    def test_while_as_function_name(self) -> None:
        result = mangle("test", fn_name="while", file="t.reflow", line=1, col=1)
        self.assertEqual(result, "rf_test_while")

    def test_non_reserved_passes(self) -> None:
        result = mangle("test", fn_name="process")
        self.assertEqual(result, "rf_test_process")


class TestMangleBuiltinType(unittest.TestCase):
    """Built-in type to C typedef mapping."""

    def test_int(self) -> None:
        self.assertEqual(mangle_builtin_type("int"), "rf_int")

    def test_int64(self) -> None:
        self.assertEqual(mangle_builtin_type("int64"), "rf_int64")

    def test_float(self) -> None:
        self.assertEqual(mangle_builtin_type("float"), "rf_float")

    def test_float32(self) -> None:
        self.assertEqual(mangle_builtin_type("float32"), "rf_float32")

    def test_bool(self) -> None:
        self.assertEqual(mangle_builtin_type("bool"), "rf_bool")

    def test_byte(self) -> None:
        self.assertEqual(mangle_builtin_type("byte"), "rf_byte")

    def test_char(self) -> None:
        self.assertEqual(mangle_builtin_type("char"), "rf_char")

    def test_string(self) -> None:
        self.assertEqual(mangle_builtin_type("string"), "RF_String*")

    def test_none(self) -> None:
        self.assertEqual(mangle_builtin_type("none"), "void")

    def test_unknown_raises(self) -> None:
        with self.assertRaises(KeyError):
            mangle_builtin_type("foobar")

    def test_all_builtins_covered(self) -> None:
        """Every entry in the map should be tested above."""
        for name in BUILTIN_TYPE_MAP:
            result = mangle_builtin_type(name)
            self.assertIsInstance(result, str)
            self.assertTrue(len(result) > 0)


class TestMangleStreamArtifacts(unittest.TestCase):
    """Stream frame, next, and free function mangling."""

    def test_stream_frame(self) -> None:
        self.assertEqual(
            mangle_stream_frame("math.vector", "generate"),
            "_rf_frame_math_vector_generate",
        )

    def test_stream_next(self) -> None:
        self.assertEqual(
            mangle_stream_next("math.vector", "generate"),
            "_rf_next_math_vector_generate",
        )

    def test_stream_free(self) -> None:
        self.assertEqual(
            mangle_stream_free("math.vector", "generate"),
            "_rf_free_math_vector_generate",
        )


class TestMangleClosureFrame(unittest.TestCase):
    """Closure frame struct mangling."""

    def test_closure_frame(self) -> None:
        self.assertEqual(
            mangle_closure_frame("pipeline.orders", "run", 0),
            "_rf_closure_pipeline_orders_run_0",
        )

    def test_closure_frame_id(self) -> None:
        self.assertEqual(
            mangle_closure_frame("main", "entry", 3),
            "_rf_closure_main_entry_3",
        )


if __name__ == "__main__":
    unittest.main()
