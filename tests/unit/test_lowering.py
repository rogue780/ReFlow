# tests/unit/test_lowering.py — Lowering pass unit tests
#
# Covers RT-7-1-1 through RT-7-5-3.
from __future__ import annotations

import unittest

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.resolver import Resolver
from compiler.typechecker import (
    TypeChecker,
    TInt, TFloat, TBool, TChar, TByte, TString, TArray, TMap,
    TNamed, TOption, TResult, TSet, TStream, TBuffer, TFn, TSum,
)
from compiler.errors import EmitError
from compiler.lowering import (
    Lowerer, LModule, LTypeDef, LFnDef, LStaticDef,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def lower(source: str) -> LModule:
    """Lex, parse, resolve, type-check, and lower *source*."""
    tokens = Lexer(source, "test.flow").tokenize()
    mod = Parser(tokens, "test.flow").parse()
    resolved = Resolver(mod).resolve()
    typed = TypeChecker(resolved).check()
    return Lowerer(typed).lower()


def find_fn(module: LModule, c_name_suffix: str) -> LFnDef | None:
    """Find a function definition by suffix of c_name (after last _)."""
    for fn in module.fn_defs:
        # Match exact suffix after the last underscore, or exact c_name
        if fn.c_name.endswith("_" + c_name_suffix) or fn.c_name == c_name_suffix:
            return fn
    return None


def find_fn_containing(module: LModule, substr: str) -> LFnDef | None:
    """Find a function definition containing substr in c_name."""
    for fn in module.fn_defs:
        if substr in fn.c_name:
            return fn
    return None


def _get_lowerer_for_test(source: str) -> "Lowerer":
    """Create a Lowerer instance with pipeline state initialized.

    Runs lex→parse→resolve→typecheck→lower so that classification methods
    like _is_affine_type can be called (they need internal state populated).
    """
    tokens = Lexer(source, "test.flow").tokenize()
    mod = Parser(tokens, "test.flow").parse()
    resolved = Resolver(mod).resolve()
    typed = TypeChecker(resolved).check()
    lowerer = Lowerer(typed)
    lowerer.lower()
    return lowerer


def find_type(module: LModule, c_name_suffix: str) -> LTypeDef | None:
    """Find a type definition by exact suffix of c_name."""
    for td in module.type_defs:
        if td.c_name.endswith("_" + c_name_suffix) or td.c_name == c_name_suffix:
            return td
    return None


def find_type_containing(module: LModule, substr: str) -> LTypeDef | None:
    """Find a type definition containing substr in c_name."""
    for td in module.type_defs:
        if substr in td.c_name:
            return td
    return None


def find_static(module: LModule, c_name_substr: str) -> LStaticDef | None:
    """Find a static definition by substring of c_name."""
    for sd in module.static_defs:
        if c_name_substr in sd.c_name:
            return sd
    return None


def count_stmts_of_type(stmts: list[LStmt], cls: type) -> int:
    """Count statements of a given type in a list."""
    return sum(1 for s in stmts if isinstance(s, cls))


def find_stmt_of_type(stmts: list[LStmt], cls: type) -> LStmt | None:
    """Find first statement of a given type."""
    for s in stmts:
        if isinstance(s, cls):
            return s
    return None


# ---------------------------------------------------------------------------
# Story 7-1: LIR Node Definitions (RT-7-1-1)
# ---------------------------------------------------------------------------

class TestLIRNodeDefinitions(unittest.TestCase):
    """RT-7-1-1: All LIR dataclasses are correctly defined."""

    def test_lmodule_fields(self):
        m = LModule(type_defs=[], fn_defs=[], static_defs=[])
        self.assertEqual(m.type_defs, [])
        self.assertEqual(m.fn_defs, [])
        self.assertEqual(m.static_defs, [])

    def test_ltypedef_fields(self):
        td = LTypeDef(c_name="fl_main_Foo", fields=[("x", LInt(32, True))])
        self.assertEqual(td.c_name, "fl_main_Foo")
        self.assertEqual(len(td.fields), 1)
        self.assertEqual(td.fields[0], ("x", LInt(32, True)))

    def test_lfndef_fields(self):
        fn = LFnDef(
            c_name="fl_main_add",
            params=[("a", LInt(32, True)), ("b", LInt(32, True))],
            ret=LInt(32, True),
            body=[LReturn(LLit("0", LInt(32, True)))],
            is_pure=True,
        )
        self.assertEqual(fn.c_name, "fl_main_add")
        self.assertEqual(len(fn.params), 2)
        self.assertTrue(fn.is_pure)

    def test_lstaticdef_fields(self):
        sd = LStaticDef(
            c_name="fl_main_Foo_count",
            c_type=LInt(32, True),
            init=LLit("0", LInt(32, True)),
            is_mut=True,
        )
        self.assertEqual(sd.c_name, "fl_main_Foo_count")
        self.assertTrue(sd.is_mut)

    def test_ltype_hierarchy(self):
        self.assertIsInstance(LInt(32, True), LType)
        self.assertIsInstance(LFloat(64), LType)
        self.assertIsInstance(LBool(), LType)
        self.assertIsInstance(LChar(), LType)
        self.assertIsInstance(LByte(), LType)
        self.assertIsInstance(LPtr(LVoid()), LType)
        self.assertIsInstance(LStruct("FL_String"), LType)
        self.assertIsInstance(LVoid(), LType)
        self.assertIsInstance(LFnPtr([LInt(32, True)], LBool()), LType)

    def test_lexpr_hierarchy(self):
        self.assertIsInstance(LLit("42", LInt(32, True)), LExpr)
        self.assertIsInstance(LVar("x", LInt(32, True)), LExpr)
        self.assertIsInstance(LCall("fn", [], LVoid()), LExpr)
        self.assertIsInstance(LBinOp("+", LLit("1", LInt(32, True)),
                                     LLit("2", LInt(32, True)),
                                     LInt(32, True)), LExpr)

    def test_lstmt_hierarchy(self):
        self.assertIsInstance(LVarDecl("x", LInt(32, True), None), LStmt)
        self.assertIsInstance(LReturn(None), LStmt)
        self.assertIsInstance(LIf(LLit("1", LBool()), [], []), LStmt)
        self.assertIsInstance(LWhile(LLit("1", LBool()), []), LStmt)
        self.assertIsInstance(LBreak(), LStmt)
        self.assertIsInstance(LSwitch(LLit("0", LByte()), [], []), LStmt)


# ---------------------------------------------------------------------------
# Story 7-2: Type Lowering (RT-7-2-1 through RT-7-2-4)
# ---------------------------------------------------------------------------

class TestTypeLowering(unittest.TestCase):
    """RT-7-2-1: _lower_type maps Flow types to LTypes."""

    def test_int_lowers_to_lint(self):
        m = lower("fn do_stuff(): int { return 0 }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.ret, LInt)
        self.assertEqual(fn.ret.width, 32)
        self.assertTrue(fn.ret.signed)

    def test_float_lowers_to_lfloat(self):
        m = lower("fn do_stuff(): float { return 0.0 }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.ret, LFloat)
        self.assertEqual(fn.ret.width, 64)

    def test_bool_lowers_to_lbool(self):
        m = lower("fn do_stuff(): bool { return true }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.ret, LBool)

    def test_string_lowers_to_lptr_fl_string(self):
        m = lower('fn do_stuff(): string { return "hi" }')
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.ret, LPtr)
        self.assertIsInstance(fn.ret.inner, LStruct)
        self.assertEqual(fn.ret.inner.c_name, "FL_String")

    def test_none_lowers_to_lvoid(self):
        m = lower("fn do_stuff(): none { }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.ret, LVoid)

    def test_params_lowered_correctly(self):
        m = lower("fn add(a: int, b: int): int { return a }")
        fn = find_fn(m, "add")
        self.assertIsNotNone(fn)
        self.assertEqual(len(fn.params), 2)
        self.assertEqual(fn.params[0][0], "a")
        self.assertIsInstance(fn.params[0][1], LInt)
        self.assertEqual(fn.params[1][0], "b")
        self.assertIsInstance(fn.params[1][1], LInt)


class TestTypeDeclLowering(unittest.TestCase):
    """RT-7-2-2: Type declarations produce LTypeDefs."""

    def test_struct_type_produces_typedef(self):
        m = lower("""
            type Point {
                x: int
                y: int
            }
            fn do_stuff(): none { }
        """)
        td = find_type(m, "Point")
        self.assertIsNotNone(td)
        self.assertEqual(len(td.fields), 2)
        names = [f[0] for f in td.fields]
        self.assertIn("x", names)
        self.assertIn("y", names)

    def test_sum_type_produces_tagged_typedef(self):
        m = lower("""
            type Shape = | Circle(radius: float) | Square(side: float) | Empty
            fn do_stuff(): none { }
        """)
        td = find_type(m, "Shape")
        self.assertIsNotNone(td)
        # Should have a tag field
        field_names = [f[0] for f in td.fields]
        self.assertIn("tag", field_names)

    def test_static_member_produces_staticdef(self):
        m = lower("""
            type Counter {
                value: int
                static count: int:mut = 0
            }
            fn do_stuff(): none { }
        """)
        sd = find_static(m, "count")
        self.assertIsNotNone(sd)
        self.assertTrue(sd.is_mut)
        self.assertIsInstance(sd.c_type, LInt)


class TestOptionResultTupleLowering(unittest.TestCase):
    """RT-7-2-3, RT-7-2-4: Option/result/tuple type registries."""

    def test_option_int_uses_builtin(self):
        m = lower("""
            fn maybe(): int? { return some(5) }
        """)
        fn = find_fn(m, "maybe")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.ret, LStruct)
        self.assertEqual(fn.ret.c_name, "FL_Option_int")


# ---------------------------------------------------------------------------
# Story 7-3: Expression Lowering (RT-7-3-1 through RT-7-3-8)
# ---------------------------------------------------------------------------

class TestLiteralLowering(unittest.TestCase):
    """RT-7-3-1: Literal expressions lower correctly."""

    def test_int_literal(self):
        m = lower("fn do_stuff(): int { return 42 }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)
        self.assertEqual(ret.value.value, "42")

    def test_float_literal(self):
        m = lower("fn do_stuff(): float { return 3.14 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)

    def test_bool_literal_true(self):
        m = lower("fn do_stuff(): bool { return true }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)
        self.assertEqual(ret.value.value, "fl_true")

    def test_bool_literal_false(self):
        m = lower("fn do_stuff(): bool { return false }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)
        self.assertEqual(ret.value.value, "fl_false")

    def test_string_literal(self):
        m = lower('fn do_stuff(): string { return "hello" }')
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        # String literals are interned as static globals (_fl_str_N)
        self.assertIsInstance(ret.value, LVar)
        self.assertTrue(ret.value.c_name.startswith("_fl_str_"))


class TestArithmeticLowering(unittest.TestCase):
    """RT-7-3-2: Integer arithmetic uses LCheckedArith."""

    def test_int_addition_checked(self):
        m = lower("fn do_stuff(): int { return 1 + 2 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LCheckedArith)
        self.assertEqual(ret.value.op, "+")

    def test_int_subtraction_checked(self):
        m = lower("fn do_stuff(): int { return 5 - 3 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LCheckedArith)
        self.assertEqual(ret.value.op, "-")

    def test_int_multiplication_checked(self):
        m = lower("fn do_stuff(): int { return 2 * 3 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LCheckedArith)
        self.assertEqual(ret.value.op, "*")

    def test_int_division_checked(self):
        m = lower("fn do_stuff(): int { return 10 / 3 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LCheckedArith)
        self.assertEqual(ret.value.op, "/")

    def test_float_arithmetic_plain_binop(self):
        m = lower("fn do_stuff(): float { return 1.0 + 2.0 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LBinOp)
        self.assertEqual(ret.value.op, "+")

    def test_comparison_produces_binop(self):
        m = lower("fn do_stuff(): bool { return 1 < 2 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LBinOp)
        self.assertEqual(ret.value.op, "<")

    def test_string_concat_uses_runtime_call(self):
        m = lower('fn do_stuff(): string { return "a" + "b" }')
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LCall)
        self.assertEqual(ret.value.fn_name, "fl_string_concat")


class TestChainLowering(unittest.TestCase):
    """RT-7-3-3: Composition chains flatten to sequential temp vars."""

    def test_simple_chain(self):
        m = lower("""
            fn inc(x: int): int { return x }
            fn do_stuff(): int {
                return 5 -> inc
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        # The chain should produce temp vars and a call
        has_var_decl = any(isinstance(s, LVarDecl) for s in fn.body)
        self.assertTrue(has_var_decl)


class TestFStringLowering(unittest.TestCase):
    """RT-7-3-4: F-strings lower to fl_string_concat chains."""

    def test_fstring_with_int_interpolation(self):
        m = lower("""
            fn do_stuff(): string {
                let x: int = 42
                return f"value is {x}"
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)

    def test_fstring_string_only(self):
        m = lower("""
            fn do_stuff(): string {
                return f"hello"
            }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        # f-string with only a string literal part is interned
        self.assertIsInstance(ret.value, LVar)
        self.assertTrue(ret.value.c_name.startswith("_fl_str_"))


class TestMatchLowering(unittest.TestCase):
    """RT-7-3-5, RT-7-3-6: Match on sum types and options."""

    def test_match_option_produces_lif(self):
        m = lower("""
            fn check(x: int?): int {
                match x {
                    some(v): { return v }
                    none: { return 0 }
                }
            }
        """)
        fn = find_fn(m, "check")
        self.assertIsNotNone(fn)
        # Should contain an LIf for option matching
        has_if = any(isinstance(s, LIf) for s in fn.body)
        self.assertTrue(has_if)

    def test_match_sum_produces_switch(self):
        m = lower("""
            type Color = | Red | Green | Blue
            fn name(c: Color): int {
                match c {
                    Red: { return 0 }
                    Green: { return 1 }
                    Blue: { return 2 }
                }
            }
        """)
        fn = find_fn(m, "name")
        self.assertIsNotNone(fn)
        # Should contain an LSwitch for sum type matching
        has_switch = any(isinstance(s, LSwitch) for s in fn.body)
        self.assertTrue(has_switch)


class TestPropagateLowering(unittest.TestCase):
    """RT-7-3-7: Propagate operator lowers to early return."""

    def test_propagate_produces_if_and_return(self):
        m = lower("""
            fn parse(s: string): result<int, string> {
                return ok(42)
            }
            fn do_stuff(): result<int, string> {
                let n: int = parse("42")?
                return ok(n)
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        # Should contain an LIf with early return
        has_if = any(isinstance(s, LIf) for s in fn.body)
        self.assertTrue(has_if)


class TestCopyLowering(unittest.TestCase):
    """RT-7-3-8: Copy expression handling."""

    def test_copy_value_type_noop(self):
        m = lower("""
            fn do_stuff(): int {
                let x: int = 42
                return @x
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LVar)

    def test_copy_string_calls_string_copy(self):
        m = lower("""
            fn do_stuff(): string {
                let s: string = "hello"
                return @s
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        has_copy = False
        for s in fn.body:
            if isinstance(s, LVarDecl) and isinstance(s.init, LCall):
                if s.init.fn_name == "fl_string_copy":
                    has_copy = True
        self.assertTrue(has_copy)

    def test_copy_array_calls_array_copy(self):
        m = lower("""
            fn do_stuff(): array<int> {
                let a: array<int> = []
                return @a
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        has_copy = False
        for s in fn.body:
            if isinstance(s, LVarDecl) and isinstance(s.init, LCall):
                if s.init.fn_name == "fl_array_copy":
                    has_copy = True
        self.assertTrue(has_copy)

    def test_ref_string_calls_string_retain(self):
        m = lower("""
            fn do_stuff(): string {
                let s: string = "hello"
                return &s
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        has_retain = False
        for s in fn.body:
            if isinstance(s, LExprStmt) and isinstance(s.expr, LCall):
                if s.expr.fn_name == "fl_string_retain":
                    has_retain = True
        self.assertTrue(has_retain)

    def test_ref_array_calls_array_retain(self):
        m = lower("""
            fn do_stuff(): array<int> {
                let a: array<int> = []
                return &a
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        has_retain = False
        for s in fn.body:
            if isinstance(s, LExprStmt) and isinstance(s.expr, LCall):
                if s.expr.fn_name == "fl_array_retain":
                    has_retain = True
        self.assertTrue(has_retain)


class TestUnaryOpLowering(unittest.TestCase):
    """Unary operators lower correctly."""

    def test_unary_negation(self):
        m = lower("fn do_stuff(): int { return -5 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LUnary)
        self.assertEqual(ret.value.op, "-")

    def test_logical_not(self):
        m = lower("fn do_stuff(): bool { return !true }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LUnary)
        self.assertEqual(ret.value.op, "!")


class TestSomeOkErrLowering(unittest.TestCase):
    """Some/Ok/Err wrapper lowering."""

    def test_some_produces_compound(self):
        m = lower("""
            fn do_stuff(): int? { return some(5) }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LCompound)

    def test_ok_produces_compound(self):
        m = lower("""
            fn do_stuff(): result<int, string> { return ok(5) }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LCompound)

    def test_err_produces_compound(self):
        m = lower("""
            fn do_stuff(): result<int, string> { return err("oops") }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LCompound)


class TestTernaryLowering(unittest.TestCase):
    """Ternary expression lowering."""

    def test_ternary_produces_lternary(self):
        m = lower("fn do_stuff(): int { return true ? 1 : 0 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LTernary)


# ---------------------------------------------------------------------------
# Story 7-4: Statement Lowering (RT-7-4-1 through RT-7-4-5)
# ---------------------------------------------------------------------------

class TestLetStmtLowering(unittest.TestCase):
    """RT-7-4-1: Let statement lowering."""

    def test_let_produces_var_decl(self):
        m = lower("fn do_stuff(): none { let x: int = 42 }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        decl = find_stmt_of_type(fn.body, LVarDecl)
        self.assertIsNotNone(decl)
        self.assertEqual(decl.c_name, "x")
        self.assertIsInstance(decl.c_type, LInt)


class TestAssignStmtLowering(unittest.TestCase):
    """Assignment statement lowering."""

    def test_assign_produces_lassign(self):
        m = lower("""
            fn do_stuff(): none {
                let x: int:mut = 0
                x = 42
            }
        """)
        fn = find_fn(m, "do_stuff")
        has_assign = any(isinstance(s, LAssign) for s in fn.body)
        self.assertTrue(has_assign)


class TestUpdateStmtLowering(unittest.TestCase):
    """Update statement lowering (+=, ++, etc.)."""

    def test_increment_uses_checked_arith(self):
        m = lower("""
            fn do_stuff(): none {
                let x: int:mut = 0
                x++
            }
        """)
        fn = find_fn(m, "do_stuff")
        has_assign = any(isinstance(s, LAssign) for s in fn.body)
        self.assertTrue(has_assign)
        for s in fn.body:
            if isinstance(s, LAssign):
                self.assertIsInstance(s.value, LCheckedArith)
                break

    def test_compound_assign_uses_checked_arith(self):
        m = lower("""
            fn do_stuff(): none {
                let x: int:mut = 0
                x += 5
            }
        """)
        fn = find_fn(m, "do_stuff")
        for s in fn.body:
            if isinstance(s, LAssign):
                self.assertIsInstance(s.value, LCheckedArith)
                self.assertEqual(s.value.op, "+")
                break


class TestIfStmtLowering(unittest.TestCase):
    """If statement lowering."""

    def test_if_produces_lif(self):
        m = lower("""
            fn do_stuff(): none {
                if (true) {
                    let x: int = 1
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        has_if = any(isinstance(s, LIf) for s in fn.body)
        self.assertTrue(has_if)

    def test_if_else_produces_lif_with_else(self):
        m = lower("""
            fn do_stuff(): none {
                if (true) {
                    let x: int = 1
                } else {
                    let x: int = 2
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        for s in fn.body:
            if isinstance(s, LIf):
                self.assertTrue(len(s.else_) > 0)
                break


class TestWhileStmtLowering(unittest.TestCase):
    """While statement lowering."""

    def test_while_produces_lwhile(self):
        m = lower("""
            fn do_stuff(): none {
                while (true) {
                    let x: int = 1
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        has_while = any(isinstance(s, LWhile) for s in fn.body)
        self.assertTrue(has_while)


class TestForStmtLowering(unittest.TestCase):
    """RT-7-4-3, RT-7-4-4: For loop lowers to LWhile."""

    def test_for_array_produces_while_with_index(self):
        m = lower("""
            fn do_stuff(): none {
                let arr: array<int> = [1, 2, 3]
                for(item in arr) {
                    let x: int = item
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        has_while = any(isinstance(s, LWhile) for s in fn.body)
        self.assertTrue(has_while)
        has_idx_decl = any(
            isinstance(s, LVarDecl) and s.c_name.startswith("_fl_tmp")
            for s in fn.body)
        self.assertTrue(has_idx_decl)


class TestReturnStmtLowering(unittest.TestCase):
    """Return statement lowering."""

    def test_return_with_value(self):
        m = lower("fn do_stuff(): int { return 42 }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsNotNone(ret.value)

    def test_return_without_value(self):
        m = lower("fn do_stuff(): none { return }")
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsNone(ret.value)


class TestBreakStmtLowering(unittest.TestCase):
    """Break statement lowering."""

    def test_break_in_while(self):
        m = lower("""
            fn do_stuff(): none {
                while (true) {
                    break
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        while_stmt = find_stmt_of_type(fn.body, LWhile)
        self.assertIsNotNone(while_stmt)
        has_break = any(isinstance(s, LBreak) for s in while_stmt.body)
        self.assertTrue(has_break)


# ---------------------------------------------------------------------------
# Story 7-5: Streaming Function Lowering (RT-7-5-1 through RT-7-5-3)
# ---------------------------------------------------------------------------

class TestStreamFunctionLowering(unittest.TestCase):
    """RT-7-5-1: Stream functions produce frame + next + free + factory."""

    def test_stream_fn_produces_four_artifacts(self):
        m = lower("""
            fn count(n: int): stream<int> {
                let i: int:mut = 0
                while (i < n) {
                    yield i
                    i++
                }
            }
        """)
        frame = find_type_containing(m, "_fl_frame")
        self.assertIsNotNone(frame, "Stream frame struct should be generated")

        next_fn = find_fn_containing(m, "_fl_next")
        self.assertIsNotNone(next_fn, "Stream next function should be generated")

        free_fn = find_fn_containing(m, "_fl_free")
        self.assertIsNotNone(free_fn, "Stream free function should be generated")

        # Factory starts with fl_ (not _fl_next_ or _fl_free_)
        factory = None
        for fn in m.fn_defs:
            if fn.c_name.endswith("_count") and not fn.c_name.startswith("_fl_"):
                factory = fn
                break
        self.assertIsNotNone(factory, "Stream factory function should be generated")

    def test_stream_frame_has_state_and_params(self):
        m = lower("""
            fn count(n: int): stream<int> {
                let i: int:mut = 0
                while (i < n) {
                    yield i
                    i++
                }
            }
        """)
        frame = find_type_containing(m, "_fl_frame")
        self.assertIsNotNone(frame)
        field_names = [f[0] for f in frame.fields]
        self.assertIn("_state", field_names)
        self.assertIn("n", field_names)

    def test_stream_factory_returns_fl_stream(self):
        m = lower("""
            fn count(n: int): stream<int> {
                yield 1
            }
        """)
        # Factory is the one starting with fl_ (not _fl_next_ or _fl_free_)
        factory = None
        for fn in m.fn_defs:
            if fn.c_name.endswith("_count") and not fn.c_name.startswith("_fl_"):
                factory = fn
                break
        self.assertIsNotNone(factory)
        self.assertIsInstance(factory.ret, LPtr)
        self.assertIsInstance(factory.ret.inner, LStruct)
        self.assertEqual(factory.ret.inner.c_name, "FL_Stream")

    def test_stream_next_returns_option_ptr(self):
        m = lower("""
            fn count(n: int): stream<int> {
                yield 1
            }
        """)
        next_fn = find_fn_containing(m, "_fl_next")
        self.assertIsNotNone(next_fn)
        self.assertIsInstance(next_fn.ret, LStruct)
        self.assertEqual(next_fn.ret.c_name, "FL_Option_ptr")


# ---------------------------------------------------------------------------
# Name mangling integration
# ---------------------------------------------------------------------------

class TestNameMangling(unittest.TestCase):
    """Verify C names are produced by the mangler."""

    def test_fn_name_mangled(self):
        m = lower("fn greet(): none { }")
        fn = find_fn(m, "greet")
        self.assertIsNotNone(fn)
        self.assertTrue(fn.c_name.startswith("fl_"))
        self.assertIn("greet", fn.c_name)

    def test_type_name_mangled(self):
        m = lower("""
            type Point {
                x: int
                y: int
            }
            fn do_stuff(): none { }
        """)
        td = find_type(m, "Point")
        self.assertIsNotNone(td)
        self.assertTrue(td.c_name.startswith("fl_"))
        self.assertIn("Point", td.c_name)

    def test_method_name_mangled(self):
        m = lower("""
            type Point {
                x: int
                y: int
                fn get_x(self): int { return self.x }
            }
            fn do_stuff(): none { }
        """)
        method = find_fn(m, "get_x")
        self.assertIsNotNone(method)
        self.assertIn("Point", method.c_name)
        self.assertIn("get_x", method.c_name)


# ---------------------------------------------------------------------------
# Function call lowering
# ---------------------------------------------------------------------------

class TestCallLowering(unittest.TestCase):
    """Function call lowering."""

    def test_direct_call_uses_mangled_name(self):
        m = lower("""
            fn add(a: int, b: int): int { return a }
            fn do_stuff(): int { return add(1, 2) }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LCall)
        self.assertIn("add", ret.value.fn_name)
        self.assertTrue(ret.value.fn_name.startswith("fl_"))

    def test_call_args_lowered(self):
        m = lower("""
            fn add(a: int, b: int): int { return a }
            fn do_stuff(): int { return add(1, 2) }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsInstance(ret.value, LCall)
        self.assertEqual(len(ret.value.args), 2)


# ---------------------------------------------------------------------------
# Purity flag preservation
# ---------------------------------------------------------------------------

class TestPurityPreservation(unittest.TestCase):
    """Purity flags are preserved in lowered functions."""

    def test_pure_fn_flag(self):
        m = lower("fn:pure add(a: int, b: int): int { return a }")
        fn = find_fn(m, "add")
        self.assertIsNotNone(fn)
        self.assertTrue(fn.is_pure)

    def test_impure_fn_flag(self):
        m = lower("fn add(a: int, b: int): int { return a }")
        fn = find_fn(m, "add")
        self.assertIsNotNone(fn)
        self.assertFalse(fn.is_pure)


# ---------------------------------------------------------------------------
# Multiple functions in module
# ---------------------------------------------------------------------------

class TestMultipleFunctions(unittest.TestCase):
    """Multiple functions all get lowered."""

    def test_multiple_fns(self):
        m = lower("""
            fn foo(): int { return 1 }
            fn bar(): int { return 2 }
            fn baz(): int { return 3 }
        """)
        self.assertEqual(len(m.fn_defs), 3)

    def test_fn_with_multiple_stmts(self):
        m = lower("""
            fn compute(): int {
                let a: int = 1
                let b: int = 2
                return a
            }
        """)
        fn = find_fn(m, "compute")
        self.assertIsNotNone(fn)
        var_decls = [s for s in fn.body if isinstance(s, LVarDecl)]
        self.assertEqual(len(var_decls), 2)


# ---------------------------------------------------------------------------
# Null coalesce lowering
# ---------------------------------------------------------------------------

class TestNullCoalesceLowering(unittest.TestCase):
    """Null coalesce ?? lowering."""

    def test_null_coalesce_produces_ternary(self):
        m = lower("""
            fn do_stuff(): int {
                let x: int? = some(5)
                return x ?? 0
            }
        """)
        fn = find_fn(m, "do_stuff")
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LTernary)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases for the lowering pass."""

    def test_empty_fn_body(self):
        m = lower("fn do_stuff(): none { }")
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn.body, list)

    def test_nested_if(self):
        m = lower("""
            fn do_stuff(): none {
                if (true) {
                    if (false) {
                        let x: int = 1
                    }
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        outer_if = find_stmt_of_type(fn.body, LIf)
        self.assertIsNotNone(outer_if)
        inner_if = find_stmt_of_type(outer_if.then, LIf)
        self.assertIsNotNone(inner_if)


class TestStreamMethodLowering(unittest.TestCase):
    """Stream helper method lowering."""

    def test_stream_take_lowers_to_runtime_call(self):
        """take on stream lowers to fl_stream_take call."""
        m = lower("""
            fn range(n: int): stream<int> {
                let i: int:mut = 0
                while (i < n) { yield i
                    i++ }
            }
            fn do_stuff(): none {
                for (x: int in range(10).take(3)) {
                    let y = x
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        # Should have a call to fl_stream_take somewhere in the lowered body
        found_take = False
        for s in fn.body:
            if isinstance(s, LVarDecl) and isinstance(s.init, LCall):
                if s.init.fn_name == "fl_stream_take":
                    found_take = True
        self.assertTrue(found_take,
                        "Expected fl_stream_take call in lowered body")

    def test_stream_skip_lowers_to_runtime_call(self):
        """skip on stream lowers to fl_stream_skip call."""
        m = lower("""
            fn range(n: int): stream<int> {
                let i: int:mut = 0
                while (i < n) { yield i
                    i++ }
            }
            fn do_stuff(): none {
                for (x: int in range(5).skip(2)) {
                    let y = x
                }
            }
        """)
        fn = find_fn(m, "do_stuff")
        self.assertIsNotNone(fn)
        found_skip = False
        for s in fn.body:
            if isinstance(s, LVarDecl) and isinstance(s.init, LCall):
                if s.init.fn_name == "fl_stream_skip":
                    found_skip = True
        self.assertTrue(found_skip,
                        "Expected fl_stream_skip call in lowered body")

    def test_stream_map_lowers_with_wrapper(self):
        """map on stream generates a wrapper function."""
        m = lower("""
            fn range(n: int): stream<int> {
                let i: int:mut = 0
                while (i < n) { yield i
                    i++ }
            }
            fn do_stuff(): none {
                for (x: int in range(5).map(\\(x: int => x * 10))) {
                    let y = x
                }
            }
        """)
        # Should have generated a stream wrapper function
        wrapper = find_fn_containing(m, "_fl_swrap")
        self.assertIsNotNone(wrapper,
                             "Expected stream map wrapper function")


class TestCongruenceLowering(unittest.TestCase):
    """Tests for === congruence operator lowering."""

    def test_congruence_same_type_lowers_to_true(self):
        """=== on two values of the same struct type lowers to fl_true."""
        m = lower("""
            type Point {
                x: int
                y: int
            }
            fn test(a: Point, b: Point): bool {
                return a === b
            }
        """)
        fn = find_fn(m, "test")
        self.assertIsNotNone(fn)
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)
        self.assertEqual(ret.value.value, "fl_true")

    def test_congruence_different_fields_lowers_to_false(self):
        """=== on two non-congruent types lowers to fl_false."""
        m = lower("""
            type A {
                x: int
                y: int
            }
            type B {
                x: int
                z: string
            }
            fn test(a: A, b: B): bool {
                return a === b
            }
        """)
        fn = find_fn(m, "test")
        self.assertIsNotNone(fn)
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)
        self.assertEqual(ret.value.value, "fl_false")

    def test_congruence_congruent_different_names_lowers_to_true(self):
        """=== on congruent types with different names lowers to fl_true."""
        m = lower("""
            type LogEntry {
                timestamp: int
                source: string
            }
            type EventRecord {
                timestamp: int
                source: string
            }
            fn test(a: LogEntry, b: EventRecord): bool {
                return a === b
            }
        """)
        fn = find_fn(m, "test")
        self.assertIsNotNone(fn)
        ret = find_stmt_of_type(fn.body, LReturn)
        self.assertIsNotNone(ret)
        self.assertIsInstance(ret.value, LLit)
        self.assertEqual(ret.value.value, "fl_true")


class TestParallelFanout(unittest.TestCase):
    """Gap #10: parallel fan-out lowering."""

    def test_parallel_fanout_generates_fanout_run(self):
        """Parallel fan-out in chain generates fl_fanout_run call."""
        m = lower("""fn:pure dbl(x: int): int = x * 2
fn:pure sqr(x: int): int = x * x
fn:pure add(a: int, b: int): int = a + b
fn main() {
    let r = 5 -> <:(dbl | sqr) -> add
}""")
        fn = find_fn(m, "main")
        self.assertIsNotNone(fn)
        # Look for fl_fanout_run call in statements
        found_fanout_run = False
        for stmt in fn.body:
            if isinstance(stmt, LExprStmt) and isinstance(stmt.expr, LCall):
                if stmt.expr.fn_name == "fl_fanout_run":
                    found_fanout_run = True
        self.assertTrue(found_fanout_run,
                        "expected fl_fanout_run call in parallel fan-out")

    def test_sequential_fanout_no_fanout_run(self):
        """Sequential fan-out does not generate fl_fanout_run."""
        m = lower("""fn:pure dbl(x: int): int = x * 2
fn:pure sqr(x: int): int = x * x
fn:pure add(a: int, b: int): int = a + b
fn main() {
    let r = 5 -> (dbl | sqr) -> add
}""")
        fn = find_fn(m, "main")
        self.assertIsNotNone(fn)
        for stmt in fn.body:
            if isinstance(stmt, LExprStmt) and isinstance(stmt.expr, LCall):
                self.assertNotEqual(stmt.expr.fn_name, "fl_fanout_run",
                                    "sequential fan-out should not use fl_fanout_run")

    def test_parallel_fanout_generates_wrapper_functions(self):
        """Parallel fan-out generates wrapper functions."""
        m = lower("""fn:pure dbl(x: int): int = x * 2
fn:pure sqr(x: int): int = x * x
fn:pure add(a: int, b: int): int = a + b
fn main() {
    let r = 5 -> <:(dbl | sqr) -> add
}""")
        wrapper_fns = [fn for fn in m.fn_defs
                       if "_fl_fanout_" in fn.c_name]
        self.assertEqual(len(wrapper_fns), 2,
                         "expected 2 wrapper functions for 2 branches")


class TestAffineClassification(unittest.TestCase):
    """Test _is_affine_type classification logic."""

    def test_value_types_not_affine(self):
        """int, float, bool, byte, char are NOT affine."""
        low = _get_lowerer_for_test("fn do_stuff():int { return 0 }")
        self.assertFalse(low._is_affine_type(TInt(32, True)))
        self.assertFalse(low._is_affine_type(TFloat(64)))
        self.assertFalse(low._is_affine_type(TBool()))
        self.assertFalse(low._is_affine_type(TChar()))
        self.assertFalse(low._is_affine_type(TByte()))

    def test_refcounted_types_not_affine(self):
        """string, array, map are refcounted, not affine."""
        low = _get_lowerer_for_test("fn do_stuff():int { return 0 }")
        self.assertFalse(low._is_affine_type(TString()))
        self.assertFalse(low._is_affine_type(TArray(TInt(32, True))))
        self.assertFalse(low._is_affine_type(TMap(TString(), TInt(32, True))))

    def test_trivial_struct_not_affine(self):
        """Struct with only value fields is trivial, not affine."""
        low = _get_lowerer_for_test("""
            type Point { x:int, y:int }
            fn do_stuff():int { return 0 }
        """)
        point_type = TNamed("test", "Point", ())
        self.assertFalse(low._is_affine_type(point_type))

    def test_struct_with_string_is_affine(self):
        """Struct with a string field is affine."""
        low = _get_lowerer_for_test("""
            type Token { value:string, line:int }
            fn do_stuff():int { return 0 }
        """)
        token_type = TNamed("test", "Token", ())
        self.assertTrue(low._is_affine_type(token_type))

    def test_struct_with_array_is_affine(self):
        """Struct with an array field is affine."""
        low = _get_lowerer_for_test("""
            type Container { items:array<int> }
            fn do_stuff():int { return 0 }
        """)
        container_type = TNamed("test", "Container", ())
        self.assertTrue(low._is_affine_type(container_type))


class TestConsumedBindings(unittest.TestCase):
    """Test that consumed (moved) bindings skip scope-exit cleanup."""

    def test_returned_affine_struct_consumed(self):
        """Returning an affine struct should consume it (no field releases)."""
        m = lower("""
            type Token { value:string, line:int }
            fn make():Token {
                let tok = Token{value:"hello", line:1}
                return tok
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "make")
        self.assertIsNotNone(fn)
        # The function should NOT have fl_string_release for tok.value
        # because tok is returned (consumed/moved to caller)
        body_str = repr(fn.body)
        self.assertNotIn("fl_string_release", body_str)

    def test_assignment_move_consumes_source(self):
        """let b = a where a is affine should consume a (move semantics)."""
        m = lower("""
            type Token { value:string, line:int }
            fn process():Token {
                let a = Token{value:"hello", line:1}
                let b = a
                return b
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "process")
        self.assertIsNotNone(fn)
        body_str = repr(fn.body)
        # Under move semantics, 'a' is consumed by 'let b = a'.
        # There should be no fl_string_release for a.value (a is consumed).
        # There should be no fl_string_retain for b.value (move, not copy).
        # Count: retain should appear once (for the string literal at
        # construction of a), and release should not appear at all
        # (b is returned, a is consumed).
        release_count = body_str.count("fl_string_release")
        self.assertEqual(release_count, 0,
                         f"Expected 0 fl_string_release calls but found {release_count}")


class TestSumTypeDestructors(unittest.TestCase):
    """Test that sum types with refcounted variants get destructors."""

    def test_sum_with_string_variant_gets_destructor(self):
        """A sum type with a string-bearing variant should generate a destructor."""
        m = lower("""
            type Item =
                | Text(value:string)
                | Number(n:int)

            type Container { item:Item, count:int }

            fn do_stuff():int {
                let c = Container{item:Item.Text("hello"), count:1}
                return 0
            }
        """)
        # Check that a _fl_destroy_* function exists for Item
        destroy_fns = [fn for fn in m.fn_defs if "_fl_destroy_" in fn.c_name and "Item" in fn.c_name]
        self.assertTrue(len(destroy_fns) > 0, "Expected destructor for sum type Item")

    def test_no_excluded_sum_types(self):
        """All sum types should now have destructors (no exclusion mechanism)."""
        # _EXCLUDED_SUM_TYPES was removed — all sum types with refcounted
        # fields now unconditionally get destructors.
        from compiler.lowering import Lowerer
        self.assertFalse(hasattr(Lowerer, '_EXCLUDED_SUM_TYPES'))


class TestForLoopBorrow(unittest.TestCase):
    """For-loop vars over containers should borrow, not own."""

    def test_for_loop_no_field_cleanup(self):
        """For-loop variable should NOT have field cleanup at iteration end."""
        m = lower("""
            type Token { value:string, line:int }
            fn process(tokens:array<Token>):none {
                for(tok:Token in tokens) {
                    // tok borrows — no cleanup
                }
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "process")
        self.assertIsNotNone(fn)
        # The for loop body should NOT contain fl_string_release for tok.value
        # because tok is a borrowed iteration variable
        body_str = repr(fn.body)
        self.assertNotIn("fl_string_release", body_str)


class TestParamBorrow(unittest.TestCase):
    """Function params on affine types should borrow (no field cleanup)."""

    def test_affine_param_no_field_cleanup(self):
        """Affine struct param should NOT get field releases at callee scope exit."""
        m = lower("""
            type Token { value:string, line:int }
            fn process(tok:Token):int {
                return tok.line
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "process")
        self.assertIsNotNone(fn)
        # The function should NOT have fl_string_release for tok.value
        # because tok is a borrowed parameter
        body_str = repr(fn.body)
        self.assertNotIn("fl_string_release", body_str)


class TestSpreadMove(unittest.TestCase):
    """Struct spread should consume the source."""

    def test_spread_source_consumed(self):
        """Spreading an affine struct should consume the source (no retain on spread fields)."""
        m = lower("""
            type Token { value:string, line:int }
            fn make():Token {
                let tok = Token{value:"hello", line:1}
                let tok2 = Token{line:2, ..tok}
                return tok2
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "make")
        self.assertIsNotNone(fn)
        body_str = repr(fn.body)
        # tok is consumed by spread — its fields should NOT be retained
        # (move, not copy) and should NOT be released (ownership transferred).
        # The only retain should be for the string literal "hello" at
        # initial construction of tok; the spread should not add another.
        retain_count = body_str.count("fl_string_retain")
        self.assertLessEqual(retain_count, 1,
                             f"Expected at most 1 fl_string_retain but found {retain_count}")

    def test_spread_source_no_field_cleanup(self):
        """Spread source should not have field releases (ownership transferred)."""
        m = lower("""
            type Token { value:string, line:int }
            fn make():Token {
                let tok = Token{value:"hello", line:1}
                let tok2 = Token{line:2, ..tok}
                return tok2
            }
            fn do_stuff():int { return 0 }
        """)
        fn = find_fn(m, "make")
        self.assertIsNotNone(fn)
        body_str = repr(fn.body)
        # tok is consumed by spread, tok2 is consumed by return.
        # There should be no fl_string_release calls — all ownership transferred.
        release_count = body_str.count("fl_string_release")
        self.assertEqual(release_count, 0,
                         f"Expected 0 fl_string_release calls but found {release_count}")

    def test_spread_non_affine_not_consumed(self):
        """Spreading a trivial (non-affine) struct should NOT consume the source."""
        low = _get_lowerer_for_test("""
            type Point { x:int, y:int }
            fn make():Point {
                let p = Point{x:1, y:2}
                let p2 = Point{y:3, ..p}
                return p2
            }
            fn do_stuff():int { return 0 }
        """)
        # p has no refcounted fields, so it's not affine — no consumption
        self.assertNotIn("p", low._consumed_bindings)


if __name__ == "__main__":
    unittest.main()
