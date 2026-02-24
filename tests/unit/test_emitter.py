# tests/unit/test_emitter.py — Emitter unit tests
#
# Covers RT-8-1-1 through RT-8-5-3.
from __future__ import annotations

import unittest

from compiler.emitter import Emitter
from compiler.lowering import (
    LModule, LTypeDef, LFnDef, LStaticDef,
    # Types
    LType, LInt, LFloat, LBool, LChar, LByte, LPtr, LStruct, LVoid, LFnPtr,
    # Expressions
    LExpr, LLit, LVar, LCall, LIndirectCall, LBinOp, LUnary,
    LFieldAccess, LArrow, LIndex, LCast, LAddrOf, LDeref,
    LCompound, LCheckedArith, LSizeOf, LTernary,
    # Statements
    LStmt, LVarDecl, LAssign, LReturn, LIf, LWhile, LBlock,
    LExprStmt, LGoto, LLabel, LSwitch, LBreak,
)
from compiler.errors import EmitError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_emitter(module: LModule | None = None,
                 source_file: str = "test.flow") -> Emitter:
    """Create an Emitter with a default or custom module."""
    if module is None:
        module = LModule(type_defs=[], fn_defs=[], static_defs=[])
    return Emitter(module, source_file)


def emit_ltype(t: LType) -> str:
    """Shorthand: emit a single LType."""
    return make_emitter()._emit_ltype(t)


def emit_expr(expr: LExpr) -> str:
    """Shorthand: emit a single LExpr."""
    e = make_emitter()
    return e._emit_expr(expr)


def emit_stmt(stmt: LStmt) -> str:
    """Shorthand: emit a single LStmt and return the output."""
    e = make_emitter()
    e._emit_stmt(stmt)
    return e._get_output()


# ---------------------------------------------------------------------------
# LType formatting tests (RT-8-2-3)
# ---------------------------------------------------------------------------

class TestEmitLType(unittest.TestCase):
    """Tests for _emit_ltype covering all LType variants."""

    def test_int32_signed(self) -> None:
        self.assertEqual(emit_ltype(LInt(32, True)), "fl_int")

    def test_int32_unsigned(self) -> None:
        self.assertEqual(emit_ltype(LInt(32, False)), "fl_uint")

    def test_int16_signed(self) -> None:
        self.assertEqual(emit_ltype(LInt(16, True)), "fl_int16")

    def test_int16_unsigned(self) -> None:
        self.assertEqual(emit_ltype(LInt(16, False)), "fl_uint16")

    def test_int64_signed(self) -> None:
        self.assertEqual(emit_ltype(LInt(64, True)), "fl_int64")

    def test_int64_unsigned(self) -> None:
        self.assertEqual(emit_ltype(LInt(64, False)), "fl_uint64")

    def test_float64(self) -> None:
        self.assertEqual(emit_ltype(LFloat(64)), "fl_float")

    def test_float32(self) -> None:
        self.assertEqual(emit_ltype(LFloat(32)), "fl_float32")

    def test_bool(self) -> None:
        self.assertEqual(emit_ltype(LBool()), "fl_bool")

    def test_char(self) -> None:
        self.assertEqual(emit_ltype(LChar()), "fl_char")

    def test_byte(self) -> None:
        self.assertEqual(emit_ltype(LByte()), "fl_byte")

    def test_void(self) -> None:
        self.assertEqual(emit_ltype(LVoid()), "void")

    def test_ptr_int(self) -> None:
        self.assertEqual(emit_ltype(LPtr(LInt(32, True))), "fl_int*")

    def test_ptr_struct(self) -> None:
        self.assertEqual(emit_ltype(LPtr(LStruct("FL_String"))), "FL_String*")

    def test_struct(self) -> None:
        self.assertEqual(emit_ltype(LStruct("fl_mod_MyType")), "fl_mod_MyType")

    def test_fn_ptr(self) -> None:
        result = emit_ltype(LFnPtr([LInt(32, True), LInt(32, True)], LBool()))
        self.assertEqual(result, "fl_bool (*)(fl_int, fl_int)")

    def test_fn_ptr_no_params(self) -> None:
        result = emit_ltype(LFnPtr([], LVoid()))
        self.assertEqual(result, "void (*)(void)")


# ---------------------------------------------------------------------------
# Expression emission tests (RT-8-3-4, RT-8-3-5, RT-8-3-7)
# ---------------------------------------------------------------------------

class TestEmitExpr(unittest.TestCase):
    """Tests for _emit_expr covering all LExpr variants."""

    def test_lit(self) -> None:
        self.assertEqual(emit_expr(LLit("42", LInt(32, True))), "42")

    def test_lit_string(self) -> None:
        self.assertEqual(
            emit_expr(LLit('"hello"', LPtr(LStruct("FL_String")))),
            '"hello"')

    def test_var(self) -> None:
        self.assertEqual(emit_expr(LVar("x", LInt(32, True))), "x")

    def test_call_no_args(self) -> None:
        self.assertEqual(
            emit_expr(LCall("fl_mod_foo", [], LVoid())),
            "fl_mod_foo()")

    def test_call_with_args(self) -> None:
        result = emit_expr(LCall("fl_mod_add",
                                 [LVar("x", LInt(32, True)),
                                  LVar("y", LInt(32, True))],
                                 LInt(32, True)))
        self.assertEqual(result, "fl_mod_add(x, y)")

    def test_indirect_call(self) -> None:
        fn_ptr = LVar("callback", LFnPtr([LInt(32, True)], LVoid()))
        result = emit_expr(LIndirectCall(fn_ptr,
                                         [LLit("5", LInt(32, True))],
                                         LVoid()))
        self.assertEqual(result, "callback(5)")

    def test_binop(self) -> None:
        result = emit_expr(LBinOp("+",
                                  LVar("a", LFloat(64)),
                                  LVar("b", LFloat(64)),
                                  LFloat(64)))
        self.assertEqual(result, "(a + b)")

    def test_binop_comparison(self) -> None:
        result = emit_expr(LBinOp("==",
                                  LVar("x", LInt(32, True)),
                                  LLit("0", LInt(32, True)),
                                  LBool()))
        self.assertEqual(result, "(x == 0)")

    def test_unary_negate(self) -> None:
        result = emit_expr(LUnary("-", LVar("x", LInt(32, True)),
                                  LInt(32, True)))
        self.assertEqual(result, "(-x)")

    def test_unary_not(self) -> None:
        result = emit_expr(LUnary("!", LVar("flag", LBool()), LBool()))
        self.assertEqual(result, "(!flag)")

    def test_field_access(self) -> None:
        obj = LVar("point", LStruct("fl_mod_Point"))
        result = emit_expr(LFieldAccess(obj, "x", LFloat(64)))
        self.assertEqual(result, "point.x")

    def test_arrow(self) -> None:
        ptr = LVar("self", LPtr(LStruct("fl_mod_Point")))
        result = emit_expr(LArrow(ptr, "x", LFloat(64)))
        self.assertEqual(result, "self->x")

    def test_index(self) -> None:
        arr = LVar("data", LPtr(LInt(32, True)))
        idx = LLit("3", LInt(64, True))
        result = emit_expr(LIndex(arr, idx, LInt(32, True)))
        self.assertEqual(result, "data[3]")

    def test_cast(self) -> None:
        inner = LVar("x", LInt(32, True))
        result = emit_expr(LCast(inner, LFloat(64)))
        self.assertEqual(result, "((fl_float)x)")

    def test_addr_of(self) -> None:
        result = emit_expr(LAddrOf(LVar("x", LInt(32, True)),
                                   LPtr(LInt(32, True))))
        self.assertEqual(result, "(&x)")

    def test_deref(self) -> None:
        result = emit_expr(LDeref(LVar("p", LPtr(LInt(32, True))),
                                  LInt(32, True)))
        self.assertEqual(result, "(*p)")

    def test_sizeof(self) -> None:
        result = emit_expr(LSizeOf(LStruct("fl_mod_Point")))
        self.assertEqual(result, "sizeof(fl_mod_Point)")

    def test_ternary(self) -> None:
        result = emit_expr(LTernary(
            LVar("cond", LBool()),
            LLit("1", LInt(32, True)),
            LLit("0", LInt(32, True)),
            LInt(32, True)))
        self.assertEqual(result, "(cond ? 1 : 0)")

    def test_compound(self) -> None:
        result = emit_expr(LCompound(
            [("x", LLit("1", LInt(32, True))),
             ("y", LLit("2", LInt(32, True)))],
            LStruct("fl_mod_Point")))
        self.assertEqual(result,
                         "(fl_mod_Point){.x = 1, .y = 2}")

    def test_checked_arith_add(self) -> None:
        """LCheckedArith emits hoisted temp + macro, returns temp name."""
        e = make_emitter()
        result = e._emit_expr(LCheckedArith(
            "+",
            LVar("a", LInt(32, True)),
            LVar("b", LInt(32, True)),
            LInt(32, True)))
        # The expression value is the temp name
        self.assertEqual(result, "_fl_e_1")
        # pre_stmts should contain declaration and macro call
        self.assertEqual(len(e._pre_stmts), 2)
        self.assertEqual(e._pre_stmts[0], "fl_int _fl_e_1;")
        self.assertEqual(e._pre_stmts[1], "FL_CHECKED_ADD(a, b, &_fl_e_1);")

    def test_checked_arith_sub(self) -> None:
        e = make_emitter()
        result = e._emit_expr(LCheckedArith(
            "-",
            LVar("x", LInt(64, True)),
            LVar("y", LInt(64, True)),
            LInt(64, True)))
        self.assertEqual(result, "_fl_e_1")
        self.assertIn("FL_CHECKED_SUB", e._pre_stmts[1])
        self.assertIn("fl_int64", e._pre_stmts[0])

    def test_checked_arith_mul(self) -> None:
        e = make_emitter()
        result = e._emit_expr(LCheckedArith(
            "*",
            LVar("a", LInt(32, True)),
            LLit("2", LInt(32, True)),
            LInt(32, True)))
        self.assertEqual(result, "_fl_e_1")
        self.assertIn("FL_CHECKED_MUL", e._pre_stmts[1])

    def test_checked_arith_invalid_op(self) -> None:
        e = make_emitter()
        with self.assertRaises(EmitError):
            e._emit_expr(LCheckedArith(
                "^",
                LVar("a", LInt(32, True)),
                LVar("b", LInt(32, True)),
                LInt(32, True)))

    def test_multiple_temps_increment(self) -> None:
        """Multiple LCheckedArith in the same function use different temps."""
        e = make_emitter()
        r1 = e._emit_expr(LCheckedArith("+",
                                         LVar("a", LInt(32, True)),
                                         LVar("b", LInt(32, True)),
                                         LInt(32, True)))
        r2 = e._emit_expr(LCheckedArith("+",
                                         LVar("c", LInt(32, True)),
                                         LVar("d", LInt(32, True)),
                                         LInt(32, True)))
        self.assertEqual(r1, "_fl_e_1")
        self.assertEqual(r2, "_fl_e_2")


# ---------------------------------------------------------------------------
# Statement emission tests (RT-8-3-3, RT-8-3-6)
# ---------------------------------------------------------------------------

class TestEmitStmt(unittest.TestCase):
    """Tests for _emit_stmt covering all LStmt variants."""

    def test_var_decl_with_init(self) -> None:
        result = emit_stmt(LVarDecl("x", LInt(32, True),
                                    LLit("42", LInt(32, True))))
        self.assertEqual(result, "fl_int x = 42;\n")

    def test_var_decl_no_init(self) -> None:
        result = emit_stmt(LVarDecl("x", LInt(32, True), None))
        self.assertEqual(result, "fl_int x;\n")

    def test_var_decl_ptr_type(self) -> None:
        result = emit_stmt(LVarDecl("p", LPtr(LStruct("FL_String")),
                                    LLit("NULL", LPtr(LStruct("FL_String")))))
        self.assertEqual(result, "FL_String* p = NULL;\n")

    def test_assign(self) -> None:
        result = emit_stmt(LAssign(
            LVar("x", LInt(32, True)),
            LLit("10", LInt(32, True))))
        self.assertEqual(result, "x = 10;\n")

    def test_assign_field(self) -> None:
        result = emit_stmt(LAssign(
            LFieldAccess(LVar("point", LStruct("fl_P")), "x", LFloat(64)),
            LLit("3.14", LFloat(64))))
        self.assertEqual(result, "point.x = 3.14;\n")

    def test_return_value(self) -> None:
        result = emit_stmt(LReturn(LVar("result", LInt(32, True))))
        self.assertEqual(result, "return result;\n")

    def test_return_void(self) -> None:
        result = emit_stmt(LReturn(None))
        self.assertEqual(result, "return;\n")

    def test_expr_stmt(self) -> None:
        result = emit_stmt(LExprStmt(
            LCall("fl_println", [LVar("s", LPtr(LStruct("FL_String")))],
                  LVoid())))
        self.assertEqual(result, "fl_println(s);\n")

    def test_if_no_else(self) -> None:
        result = emit_stmt(LIf(
            LVar("flag", LBool()),
            [LReturn(LLit("1", LInt(32, True)))],
            []))
        self.assertIn("if (flag) {", result)
        self.assertIn("return 1;", result)
        self.assertNotIn("} else {", result)

    def test_if_with_else(self) -> None:
        result = emit_stmt(LIf(
            LBinOp(">", LVar("x", LInt(32, True)),
                   LLit("0", LInt(32, True)), LBool()),
            [LReturn(LLit("1", LInt(32, True)))],
            [LReturn(LLit("0", LInt(32, True)))]))
        self.assertIn("if (x > 0) {", result)
        self.assertIn("} else {", result)
        self.assertIn("return 0;", result)

    def test_while(self) -> None:
        result = emit_stmt(LWhile(
            LBinOp("<", LVar("i", LInt(32, True)),
                   LVar("n", LInt(32, True)), LBool()),
            [LExprStmt(LCall("do_something", [], LVoid()))]))
        self.assertIn("while (i < n) {", result)
        self.assertIn("do_something();", result)

    def test_block(self) -> None:
        result = emit_stmt(LBlock([
            LVarDecl("tmp", LInt(32, True), LLit("0", LInt(32, True))),
        ]))
        self.assertIn("{", result)
        self.assertIn("fl_int tmp = 0;", result)
        self.assertIn("}", result)

    def test_switch(self) -> None:
        result = emit_stmt(LSwitch(
            LVar("tag", LByte()),
            [(0, [LReturn(LLit("0", LInt(32, True)))]),
             (1, [LReturn(LLit("1", LInt(32, True)))])],
            [LReturn(LLit("-1", LInt(32, True)))]))
        self.assertIn("switch (tag) {", result)
        self.assertIn("case 0:", result)
        self.assertIn("case 1:", result)
        self.assertIn("default:", result)

    def test_goto(self) -> None:
        result = emit_stmt(LGoto("_state_1"))
        self.assertEqual(result, "goto _state_1;\n")

    def test_label(self) -> None:
        result = emit_stmt(LLabel("_state_1"))
        self.assertEqual(result, "_state_1:;\n")

    def test_break(self) -> None:
        result = emit_stmt(LBreak())
        self.assertEqual(result, "break;\n")

    def test_var_decl_with_checked_arith(self) -> None:
        """VarDecl with LCheckedArith init flushes pre_stmts before the decl."""
        result = emit_stmt(LVarDecl(
            "sum", LInt(32, True),
            LCheckedArith("+",
                          LVar("a", LInt(32, True)),
                          LVar("b", LInt(32, True)),
                          LInt(32, True))))
        # Should contain the hoisted temp declaration, macro call, then assignment
        self.assertIn("fl_int _fl_e_1;", result)
        self.assertIn("FL_CHECKED_ADD(a, b, &_fl_e_1);", result)
        self.assertIn("fl_int sum = _fl_e_1;", result)

    def test_return_with_checked_arith(self) -> None:
        """Return with LCheckedArith flushes pre_stmts before the return."""
        result = emit_stmt(LReturn(
            LCheckedArith("+",
                          LVar("x", LInt(32, True)),
                          LVar("y", LInt(32, True)),
                          LInt(32, True))))
        self.assertIn("fl_int _fl_e_1;", result)
        self.assertIn("FL_CHECKED_ADD(x, y, &_fl_e_1);", result)
        self.assertIn("return _fl_e_1;", result)


# ---------------------------------------------------------------------------
# Type definition emission tests (RT-8-2-1)
# ---------------------------------------------------------------------------

class TestEmitTypeDef(unittest.TestCase):
    """Tests for _emit_type_def."""

    def test_simple_struct(self) -> None:
        td = LTypeDef("fl_mod_Point", [
            ("x", LFloat(64)),
            ("y", LFloat(64)),
        ])
        e = make_emitter()
        e._emit_type_def(td)
        result = e._get_output()
        self.assertIn("struct fl_mod_Point {", result)
        self.assertIn("fl_float x;", result)
        self.assertIn("fl_float y;", result)
        self.assertIn("};", result)

    def test_tagged_union_struct(self) -> None:
        """Sum types are lowered as structs with tag + payload fields."""
        td = LTypeDef("fl_mod_Shape", [
            ("tag", LByte()),
            ("circle_radius", LFloat(64)),
            ("rect_width", LFloat(64)),
            ("rect_height", LFloat(64)),
        ])
        e = make_emitter()
        e._emit_type_def(td)
        result = e._get_output()
        self.assertIn("struct fl_mod_Shape {", result)
        self.assertIn("fl_byte tag;", result)
        self.assertIn("fl_float circle_radius;", result)

    def test_struct_with_ptr_field(self) -> None:
        td = LTypeDef("fl_mod_Node", [
            ("value", LInt(32, True)),
            ("next", LPtr(LStruct("fl_mod_Node"))),
        ])
        e = make_emitter()
        e._emit_type_def(td)
        result = e._get_output()
        self.assertIn("fl_int value;", result)
        self.assertIn("fl_mod_Node* next;", result)


# ---------------------------------------------------------------------------
# Function definition emission tests (RT-8-3-1)
# ---------------------------------------------------------------------------

class TestEmitFnDef(unittest.TestCase):
    """Tests for _emit_fn_def."""

    def test_simple_function(self) -> None:
        fn = LFnDef(
            c_name="fl_test_identity",
            params=[("x", LInt(32, True))],
            ret=LInt(32, True),
            body=[LReturn(LVar("x", LInt(32, True)))],
            is_pure=True,
            source_name="test.identity",
        )
        e = make_emitter()
        e._emit_fn_def(fn)
        result = e._get_output()
        self.assertIn("/* Flow: test.identity */", result)
        self.assertIn("fl_int fl_test_identity(fl_int x) {", result)
        self.assertIn("return x;", result)
        self.assertIn("}", result)

    def test_void_no_params(self) -> None:
        fn = LFnDef(
            c_name="fl_test_noop",
            params=[],
            ret=LVoid(),
            body=[LReturn(None)],
            is_pure=True,
            source_name="test.noop",
        )
        e = make_emitter()
        e._emit_fn_def(fn)
        result = e._get_output()
        self.assertIn("void fl_test_noop(void) {", result)

    def test_no_source_name(self) -> None:
        """Function without source_name should not emit Flow comment."""
        fn = LFnDef(
            c_name="helper",
            params=[],
            ret=LVoid(),
            body=[LReturn(None)],
            is_pure=False,
        )
        e = make_emitter()
        e._emit_fn_def(fn)
        result = e._get_output()
        self.assertNotIn("/* Flow:", result)

    def test_temp_counter_resets_per_function(self) -> None:
        """Temp counter resets for each function."""
        fn1 = LFnDef(
            c_name="fl_test_fn1",
            params=[],
            ret=LInt(32, True),
            body=[LReturn(LCheckedArith("+",
                                        LVar("a", LInt(32, True)),
                                        LVar("b", LInt(32, True)),
                                        LInt(32, True)))],
            is_pure=True,
            source_name="test.fn1",
        )
        fn2 = LFnDef(
            c_name="fl_test_fn2",
            params=[],
            ret=LInt(32, True),
            body=[LReturn(LCheckedArith("+",
                                        LVar("c", LInt(32, True)),
                                        LVar("d", LInt(32, True)),
                                        LInt(32, True)))],
            is_pure=True,
            source_name="test.fn2",
        )
        mod = LModule(type_defs=[], fn_defs=[fn1, fn2], static_defs=[])
        e = Emitter(mod, "test.flow")
        result = e.emit()
        # Both functions should use _fl_e_1 (counter resets)
        self.assertEqual(result.count("_fl_e_1"), 6)  # 3 per function (decl, macro, return)


# ---------------------------------------------------------------------------
# Static/global definition emission tests (RT-8-4-1)
# ---------------------------------------------------------------------------

class TestEmitStaticDef(unittest.TestCase):
    """Tests for _emit_static_def."""

    def test_mutable_with_init(self) -> None:
        sd = LStaticDef("fl_test_counter", LInt(32, True),
                         LLit("0", LInt(32, True)), is_mut=True)
        e = make_emitter()
        e._emit_static_def(sd)
        result = e._get_output()
        self.assertEqual(result, "fl_int fl_test_counter = 0;\n")

    def test_mutable_no_init(self) -> None:
        sd = LStaticDef("fl_test_counter", LInt(32, True), None, is_mut=True)
        e = make_emitter()
        e._emit_static_def(sd)
        result = e._get_output()
        self.assertEqual(result, "fl_int fl_test_counter;\n")

    def test_immutable_with_init(self) -> None:
        sd = LStaticDef("fl_test_PI", LFloat(64),
                         LLit("3.14159", LFloat(64)), is_mut=False)
        e = make_emitter()
        e._emit_static_def(sd)
        result = e._get_output()
        self.assertEqual(result, "static const fl_float fl_test_PI = 3.14159;\n")

    def test_immutable_no_init(self) -> None:
        sd = LStaticDef("fl_test_DEFAULT", LInt(32, True), None, is_mut=False)
        e = make_emitter()
        e._emit_static_def(sd)
        result = e._get_output()
        self.assertEqual(result, "static const fl_int fl_test_DEFAULT;\n")


# ---------------------------------------------------------------------------
# Full emit() integration tests (RT-8-5-1)
# ---------------------------------------------------------------------------

class TestEmitFull(unittest.TestCase):
    """Tests for the full emit() entry point."""

    def test_empty_module(self) -> None:
        mod = LModule(type_defs=[], fn_defs=[], static_defs=[])
        result = Emitter(mod, "empty.flow").emit()
        self.assertIn("/* Generated by flowc - do not edit */", result)
        self.assertIn("/* Source: empty.flow */", result)
        self.assertIn('#include "flow_runtime.h"', result)

    def test_hello_world_structure(self) -> None:
        """A simple add function should produce the expected structure."""
        fn = LFnDef(
            c_name="fl_tests_hello_add",
            params=[("x", LInt(32, True)), ("y", LInt(32, True))],
            ret=LInt(32, True),
            body=[LReturn(LCheckedArith(
                "+",
                LVar("x", LInt(32, True)),
                LVar("y", LInt(32, True)),
                LInt(32, True)))],
            is_pure=True,
            source_name="tests.hello.add",
        )
        mod = LModule(type_defs=[], fn_defs=[fn], static_defs=[])
        result = Emitter(mod, "tests/programs/hello.flow").emit()

        expected = (
            "/* Generated by flowc - do not edit */\n"
            "/* Source: tests/programs/hello.flow */\n"
            '#include "flow_runtime.h"\n'
            "\n"
            "/* Flow: tests.hello.add */\n"
            "fl_int fl_tests_hello_add(fl_int x, fl_int y) {\n"
            "    fl_int _fl_e_1;\n"
            "    FL_CHECKED_ADD(x, y, &_fl_e_1);\n"
            "    return _fl_e_1;\n"
            "}\n"
        )
        self.assertEqual(result, expected)

    def test_module_with_types_has_forward_decls(self) -> None:
        """Module with type defs emits forward declarations."""
        td = LTypeDef("fl_mod_Point", [
            ("x", LFloat(64)),
            ("y", LFloat(64)),
        ])
        fn = LFnDef(
            c_name="fl_mod_origin",
            params=[],
            ret=LStruct("fl_mod_Point"),
            body=[LReturn(LCompound(
                [("x", LLit("0.0", LFloat(64))),
                 ("y", LLit("0.0", LFloat(64)))],
                LStruct("fl_mod_Point")))],
            is_pure=True,
            source_name="mod.origin",
        )
        mod = LModule(type_defs=[td], fn_defs=[fn], static_defs=[])
        result = Emitter(mod, "test.flow").emit()
        # Should have forward declarations
        self.assertIn("typedef struct fl_mod_Point fl_mod_Point;", result)
        # Function prototype forward declaration
        self.assertIn("fl_mod_Point fl_mod_origin(void);", result)
        # Then the actual struct and function definitions
        self.assertIn("struct fl_mod_Point {", result)
        self.assertIn("fl_mod_Point fl_mod_origin(void) {", result)

    def test_module_with_statics(self) -> None:
        """Module with static defs emits them between types and functions."""
        sd = LStaticDef("fl_mod_MAX", LInt(32, True),
                         LLit("100", LInt(32, True)), is_mut=False)
        fn = LFnDef(
            c_name="fl_mod_get_max",
            params=[],
            ret=LInt(32, True),
            body=[LReturn(LVar("fl_mod_MAX", LInt(32, True)))],
            is_pure=True,
            source_name="mod.get_max",
        )
        mod = LModule(type_defs=[], fn_defs=[fn], static_defs=[sd])
        result = Emitter(mod, "test.flow").emit()
        self.assertIn("static const fl_int fl_mod_MAX = 100;", result)
        # Static should come before function
        max_pos = result.index("fl_mod_MAX = 100")
        fn_pos = result.index("fl_mod_get_max(void) {")
        self.assertLess(max_pos, fn_pos)


# ---------------------------------------------------------------------------
# Format declaration tests
# ---------------------------------------------------------------------------

class TestFormatDecl(unittest.TestCase):
    """Tests for _format_decl handling special types like fn pointers."""

    def test_simple_decl(self) -> None:
        e = make_emitter()
        self.assertEqual(e._format_decl(LInt(32, True), "x"), "fl_int x")

    def test_ptr_decl(self) -> None:
        e = make_emitter()
        self.assertEqual(e._format_decl(LPtr(LVoid()), "data"), "void* data")

    def test_fn_ptr_decl(self) -> None:
        e = make_emitter()
        result = e._format_decl(
            LFnPtr([LInt(32, True)], LBool()), "callback")
        self.assertEqual(result, "fl_bool (*callback)(fl_int)")


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestEmitErrors(unittest.TestCase):
    """Tests for emitter error handling."""

    def test_unknown_ltype_raises_emit_error(self) -> None:
        """An unknown LType subclass should raise EmitError."""
        class LUnknownType(LType):
            pass
        e = make_emitter()
        with self.assertRaises(EmitError):
            e._emit_ltype(LUnknownType())

    def test_unknown_lexpr_raises_emit_error(self) -> None:
        """An unknown LExpr subclass should raise EmitError."""
        class LUnknownExpr(LExpr):
            pass
        e = make_emitter()
        with self.assertRaises(EmitError):
            e._emit_expr(LUnknownExpr())

    def test_unknown_lstmt_raises_emit_error(self) -> None:
        """An unknown LStmt subclass should raise EmitError."""
        class LUnknownStmt(LStmt):
            pass
        e = make_emitter()
        with self.assertRaises(EmitError):
            e._emit_stmt(LUnknownStmt())


if __name__ == "__main__":
    unittest.main()
