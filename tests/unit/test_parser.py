# tests/unit/test_parser.py — Parser unit tests
#
# Covers RT-4-6-1 (declaration parse tests), RT-4-6-2 (expression parse tests),
# RT-4-6-3 (statement and pattern parse tests), RT-4-6-4 (error recovery tests).
#
# Each test provides a source string and asserts exact AST node types and field
# values. The parser under test is compiler/parser.py, which accepts a token
# list produced by compiler/lexer.py and returns a compiler/ast_nodes.Module.
from __future__ import annotations

import unittest

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.errors import ParseError
from compiler.ast_nodes import (
    # Base
    Module,
    # Declarations
    ModuleDecl, ImportDecl, FnDecl, TypeDecl, InterfaceDecl, AliasDecl,
    FieldDecl, ConstructorDecl, StaticMemberDecl, SumVariantDecl, Param,
    ExternLibDecl, ExternTypeDecl, ExternFnDecl,
    # Statements
    LetStmt, AssignStmt, UpdateStmt, ReturnStmt, YieldStmt, ThrowStmt,
    BreakStmt, ExprStmt, IfStmt, WhileStmt, ForStmt,
    MatchStmt, TryStmt, Block, MatchArm, RetryBlock, CatchBlock, FinallyBlock,
    # Expressions
    IntLit, FloatLit, BoolLit, StringLit, FStringExpr, CharLit, NoneLit,
    Ident, NamedArg, BinOp, UnaryOp, Call, MethodCall, FieldAccess, IndexAccess,
    Lambda, TupleExpr, ArrayLit, RecordLit, TypeLit, IfExpr, MatchExpr,
    CompositionChain, ChainElement, FanOut, TernaryExpr, CopyExpr, RefExpr,
    SomeExpr, OkExpr, ErrExpr, CoerceExpr, CastExpr,
    PropagateExpr, NullCoalesce, TypeofExpr, CoroutineStart,
    # Type expressions
    NamedType, GenericType, OptionType, FnType, TupleType, MutType,
    ImutType, SizedType, SumTypeExpr,
    # Patterns
    WildcardPattern, LiteralPattern, BindPattern, SomePattern, NonePattern,
    OkPattern, ErrPattern, VariantPattern, TuplePattern,
    # Type parameters
    TypeParam,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(source: str) -> Module:
    """Lex and parse *source* using the filename 'test.flow'."""
    tokens = Lexer(source, "test.flow").tokenize()
    parser = Parser(tokens, "test.flow")
    return parser.parse()


def parse_decls(source: str) -> list:
    """Return the top-level decls from a parsed module."""
    return parse(source).decls


def parse_first_decl(source: str):
    """Return the first top-level declaration from *source*."""
    decls = parse_decls(source)
    assert decls, "Expected at least one declaration"
    return decls[0]


def parse_fn_body_stmts(source: str) -> list:
    """Parse *source* (which must contain exactly one fn decl) and return its body statements."""
    decl = parse_first_decl(source)
    assert isinstance(decl, FnDecl), f"Expected FnDecl, got {type(decl)}"
    assert isinstance(decl.body, Block), f"Expected block body, got {type(decl.body)}"
    return decl.body.stmts


def wrap_in_fn(stmt_source: str) -> str:
    """Wrap a statement in a minimal function body for parsing."""
    return f"fn _test(): none {{\n{stmt_source}\n}}"


def wrap_expr_in_let(expr_source: str) -> str:
    """Wrap an expression in a let statement for parsing."""
    return f"fn _test(): none {{\nlet _x = {expr_source}\n}}"


def parse_stmt(stmt_source: str) -> "Stmt":
    """Parse a single statement wrapped in a function body."""
    stmts = parse_fn_body_stmts(wrap_in_fn(stmt_source))
    assert stmts, "Expected at least one statement"
    return stmts[0]


def parse_expr(expr_source: str) -> "Expr":
    """Parse a single expression wrapped in a let statement inside a function."""
    stmt = parse_stmt(f"let _x = {expr_source}")
    assert isinstance(stmt, LetStmt), f"Expected LetStmt, got {type(stmt)}"
    return stmt.value


# ===========================================================================
# RT-4-6-1: Declaration parse tests
# ===========================================================================

class TestModuleDecl(unittest.TestCase):
    """Module declaration parsing."""

    def test_simple_module_decl(self) -> None:
        mod = parse("module main")
        self.assertEqual(mod.path, ["main"])

    def test_dotted_module_decl(self) -> None:
        mod = parse("module math.vector")
        self.assertEqual(mod.path, ["math", "vector"])

    def test_three_part_module_decl(self) -> None:
        mod = parse("module a.b.c")
        self.assertEqual(mod.path, ["a", "b", "c"])

    def test_module_decl_filename_stored(self) -> None:
        mod = parse("module main")
        self.assertEqual(mod.filename, "test.flow")

    def test_module_decl_type(self) -> None:
        # The module path is directly on the Module node (not a separate decl)
        mod = parse("module math.vector")
        self.assertIsInstance(mod, Module)
        self.assertEqual(mod.path, ["math", "vector"])


class TestImportDecl(unittest.TestCase):
    """Import declaration parsing."""

    def test_simple_import(self) -> None:
        mod = parse("module main\nimport io")
        self.assertEqual(len(mod.imports), 1)
        imp = mod.imports[0]
        self.assertIsInstance(imp, ImportDecl)
        self.assertEqual(imp.path, ["io"])
        self.assertIsNone(imp.names)
        self.assertIsNone(imp.alias)

    def test_dotted_import(self) -> None:
        mod = parse("module main\nimport math.vector")
        imp = mod.imports[0]
        self.assertEqual(imp.path, ["math", "vector"])
        self.assertIsNone(imp.names)
        self.assertIsNone(imp.alias)

    def test_three_part_dotted_import(self) -> None:
        mod = parse("module main\nimport a.b.c")
        imp = mod.imports[0]
        self.assertEqual(imp.path, ["a", "b", "c"])

    def test_named_import(self) -> None:
        mod = parse("module main\nimport math.vector (Vec3, dot)")
        imp = mod.imports[0]
        self.assertEqual(imp.path, ["math", "vector"])
        self.assertEqual(imp.names, ["Vec3", "dot"])
        self.assertIsNone(imp.alias)

    def test_named_import_single(self) -> None:
        mod = parse("module main\nimport io (print)")
        imp = mod.imports[0]
        self.assertEqual(imp.names, ["print"])

    def test_aliased_import(self) -> None:
        mod = parse("module main\nimport math.vector as vec")
        imp = mod.imports[0]
        self.assertEqual(imp.path, ["math", "vector"])
        self.assertIsNone(imp.names)
        self.assertEqual(imp.alias, "vec")

    def test_multiple_imports(self) -> None:
        mod = parse("module main\nimport io\nimport math.vector")
        self.assertEqual(len(mod.imports), 2)
        self.assertEqual(mod.imports[0].path, ["io"])
        self.assertEqual(mod.imports[1].path, ["math", "vector"])


class TestFnDecl(unittest.TestCase):
    """Function declaration parsing."""

    def test_fn_with_block_body(self) -> None:
        decl = parse_first_decl("fn add(x: int, y: int): int { return x }")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(decl.name, "add")

    def test_fn_params(self) -> None:
        decl = parse_first_decl("fn add(x: int, y: int): int { return x }")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.params), 2)
        self.assertEqual(decl.params[0].name, "x")
        self.assertEqual(decl.params[1].name, "y")

    def test_fn_return_type(self) -> None:
        decl = parse_first_decl("fn add(x: int, y: int): int { return x }")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNotNone(decl.return_type)

    def test_fn_block_body_type(self) -> None:
        decl = parse_first_decl("fn add(x: int, y: int): int { return x }")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsInstance(decl.body, Block)

    def test_fn_with_expr_body(self) -> None:
        decl = parse_first_decl("fn add(x: int, y: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(decl.name, "add")
        # Expression body: body is an Expr, not a Block
        self.assertNotIsInstance(decl.body, Block)

    def test_pure_fn(self) -> None:
        decl = parse_first_decl("fn:pure square(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertTrue(decl.is_pure)
        self.assertEqual(decl.name, "square")

    def test_export_fn(self) -> None:
        decl = parse_first_decl("export fn visible(): int = 42")
        self.assertIsInstance(decl, FnDecl)
        self.assertTrue(decl.is_export)
        self.assertEqual(decl.name, "visible")

    def test_fn_not_pure_by_default(self) -> None:
        decl = parse_first_decl("fn regular(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertFalse(decl.is_pure)

    def test_fn_not_export_by_default(self) -> None:
        decl = parse_first_decl("fn regular(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertFalse(decl.is_export)

    def test_generic_fn_single_type_param(self) -> None:
        decl = parse_first_decl("fn identity<T>(x: T): T = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 1)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(decl.type_params[0].bounds, [])

    def test_generic_fn_multiple_type_params(self) -> None:
        decl = parse_first_decl("fn transform<T, U>(x: T): U { return x }")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 2)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(decl.type_params[1].name, "U")

    def test_fn_no_type_params_by_default(self) -> None:
        decl = parse_first_decl("fn foo(): int = 1")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(decl.type_params, [])

    def test_fn_no_params(self) -> None:
        decl = parse_first_decl("fn foo(): int = 42")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(decl.params, [])

    def test_fn_with_finally(self) -> None:
        decl = parse_first_decl(
            "fn foo(): int { return 1 } finally { return 0 }"
        )
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNotNone(decl.finally_block)

    def test_fn_without_finally_is_none(self) -> None:
        decl = parse_first_decl("fn foo(): int = 1")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNone(decl.finally_block)

    def test_param_type_annotation(self) -> None:
        decl = parse_first_decl("fn foo(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        param = decl.params[0]
        self.assertIsInstance(param, Param)
        self.assertEqual(param.name, "x")
        self.assertIsNotNone(param.type_ann)

    def test_export_pure_fn(self) -> None:
        decl = parse_first_decl("export fn:pure compute(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertTrue(decl.is_export)
        self.assertTrue(decl.is_pure)

    def test_fn_static(self) -> None:
        decl = parse_first_decl("type Foo { fn:static bar(): int = 42 }")
        self.assertIsInstance(decl, TypeDecl)
        method = decl.methods[0]
        self.assertIsInstance(method, FnDecl)
        self.assertTrue(method.is_static)
        self.assertFalse(method.is_pure)

    def test_fn_pure_static(self) -> None:
        decl = parse_first_decl("type Foo { fn:pure:static baz(): int = 42 }")
        self.assertIsInstance(decl, TypeDecl)
        method = decl.methods[0]
        self.assertIsInstance(method, FnDecl)
        self.assertTrue(method.is_pure)
        self.assertTrue(method.is_static)

    def test_fn_static_pure_error(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse_first_decl("type Foo { fn:static:pure baz(): int = 42 }")
        self.assertIn("fn:pure:static", ctx.exception.message)

    def test_old_pure_fn_error(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse_first_decl("pure fn foo(): int = 1")
        self.assertIn("fn:pure", ctx.exception.message)

    def test_old_static_fn_error(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse_first_decl("type Foo { static fn bar(): int = 42 }")
        self.assertIn("fn:static", ctx.exception.message)

    def test_duplicate_pure_error(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse_first_decl("fn:pure:pure foo(): int = 1")
        self.assertIn("duplicate", ctx.exception.message)

    def test_duplicate_static_error(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse_first_decl("type Foo { fn:static:static bar(): int = 42 }")
        self.assertIn("duplicate", ctx.exception.message)


class TestTypeDecl(unittest.TestCase):
    """Type (struct) declaration parsing."""

    def test_simple_struct(self) -> None:
        decl = parse_first_decl("type Point { x: float, y: float }")
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(decl.name, "Point")
        self.assertFalse(decl.is_sum_type)

    def test_struct_fields(self) -> None:
        decl = parse_first_decl("type Point { x: float, y: float }")
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.fields), 2)
        self.assertEqual(decl.fields[0].name, "x")
        self.assertEqual(decl.fields[1].name, "y")

    def test_struct_field_is_field_decl(self) -> None:
        decl = parse_first_decl("type Point { x: float, y: float }")
        self.assertIsInstance(decl.fields[0], FieldDecl)

    def test_struct_with_method(self) -> None:
        src = "type Point { x: float, y: float, fn magnitude(self): float { return x } }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.methods), 1)
        self.assertEqual(decl.methods[0].name, "magnitude")

    def test_struct_with_constructor(self) -> None:
        src = (
            "type LogEntry { msg: string, "
            "constructor from_raw(s: string): LogEntry { return LogEntry { msg: s } } }"
        )
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.constructors), 1)
        self.assertEqual(decl.constructors[0].name, "from_raw")

    def test_struct_with_static(self) -> None:
        src = 'type Config { static host: string:mut = "localhost" }'
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.static_members), 1)
        self.assertEqual(decl.static_members[0].name, "host")

    def test_type_fulfills_interface(self) -> None:
        src = "type MyType fulfills Serializable { x: int }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.interfaces), 1)
        self.assertIsInstance(decl.interfaces[0], NamedType)
        self.assertEqual(decl.interfaces[0].name, "Serializable")

    def test_type_fulfills_generic_interface(self) -> None:
        src = "type MyError fulfills Exception<string> { msg: string }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.interfaces), 1)
        self.assertIsInstance(decl.interfaces[0], GenericType)
        base = decl.interfaces[0].base
        self.assertIsInstance(base, NamedType)
        self.assertEqual(base.name, "Exception")
        self.assertEqual(len(decl.interfaces[0].args), 1)

    def test_export_type(self) -> None:
        decl = parse_first_decl("export type Point { x: float, y: float }")
        self.assertIsInstance(decl, TypeDecl)
        self.assertTrue(decl.is_export)

    def test_type_not_export_by_default(self) -> None:
        decl = parse_first_decl("type Point { x: float, y: float }")
        self.assertIsInstance(decl, TypeDecl)
        self.assertFalse(decl.is_export)

    def test_sum_type_basic(self) -> None:
        src = "type Shape = | Circle(radius: float) | Rectangle(width: float, height: float)"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertTrue(decl.is_sum_type)
        self.assertEqual(decl.name, "Shape")

    def test_sum_type_variants_count(self) -> None:
        src = "type Shape = | Circle(radius: float) | Rectangle(width: float, height: float)"
        decl = parse_first_decl(src)
        self.assertEqual(len(decl.variants), 2)

    def test_sum_type_variant_names(self) -> None:
        src = "type Shape = | Circle(radius: float) | Rectangle(width: float, height: float)"
        decl = parse_first_decl(src)
        names = [v.name for v in decl.variants]
        self.assertIn("Circle", names)
        self.assertIn("Rectangle", names)

    def test_enum_like_sum_type(self) -> None:
        src = "type Direction = | North | South | East | West"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertTrue(decl.is_sum_type)
        self.assertEqual(len(decl.variants), 4)

    def test_enum_variant_no_fields(self) -> None:
        src = "type Direction = | North | South | East | West"
        decl = parse_first_decl(src)
        for variant in decl.variants:
            self.assertIsInstance(variant, SumVariantDecl)
            # Variants without payload have None or empty fields
            self.assertTrue(variant.fields is None or len(variant.fields) == 0)

    def test_mut_field(self) -> None:
        src = "type Counter { count: int:mut }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, TypeDecl)
        self.assertTrue(decl.fields[0].is_mut)

    def test_immut_field(self) -> None:
        src = "type Point { x: float, y: float }"
        decl = parse_first_decl(src)
        self.assertFalse(decl.fields[0].is_mut)


class TestInterfaceDecl(unittest.TestCase):
    """Interface declaration parsing."""

    def test_simple_interface(self) -> None:
        src = "interface Serializable { fn serialize(self): string }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, InterfaceDecl)
        self.assertEqual(decl.name, "Serializable")

    def test_interface_method_signature(self) -> None:
        src = "interface Serializable { fn serialize(self): string }"
        decl = parse_first_decl(src)
        self.assertEqual(len(decl.methods), 1)
        self.assertEqual(decl.methods[0].name, "serialize")
        # Interface methods have no body
        self.assertIsNone(decl.methods[0].body)

    def test_interface_multiple_methods(self) -> None:
        src = "interface Runnable { fn run(self): none, fn stop(self): none }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, InterfaceDecl)
        self.assertEqual(len(decl.methods), 2)

    def test_export_interface(self) -> None:
        src = "export interface Serializable { fn serialize(self): string }"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, InterfaceDecl)
        self.assertTrue(decl.is_export)

    def test_interface_not_export_by_default(self) -> None:
        src = "interface Serializable { fn serialize(self): string }"
        decl = parse_first_decl(src)
        self.assertFalse(decl.is_export)


class TestAliasDecl(unittest.TestCase):
    """Alias declaration parsing."""

    def test_simple_alias(self) -> None:
        decl = parse_first_decl("alias Timestamp: int")
        self.assertIsInstance(decl, AliasDecl)
        self.assertEqual(decl.name, "Timestamp")

    def test_alias_target_type(self) -> None:
        decl = parse_first_decl("alias Timestamp: int")
        self.assertIsInstance(decl, AliasDecl)
        self.assertIsNotNone(decl.target)

    def test_generic_alias(self) -> None:
        src = "alias Transform<T, U>: fn(T): U"
        decl = parse_first_decl(src)
        self.assertIsInstance(decl, AliasDecl)
        self.assertEqual(decl.name, "Transform")
        self.assertEqual(len(decl.type_params), 2)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(decl.type_params[1].name, "U")

    def test_alias_no_type_params_by_default(self) -> None:
        decl = parse_first_decl("alias Timestamp: int")
        self.assertIsInstance(decl, AliasDecl)
        self.assertEqual(decl.type_params, [])

    def test_export_alias(self) -> None:
        decl = parse_first_decl("export alias Timestamp: int")
        self.assertIsInstance(decl, AliasDecl)
        self.assertTrue(decl.is_export)

    def test_alias_not_export_by_default(self) -> None:
        decl = parse_first_decl("alias Timestamp: int")
        self.assertFalse(decl.is_export)


# ===========================================================================
# RT-4-6-2: Expression parse tests
# ===========================================================================

class TestLiteralExpressions(unittest.TestCase):
    """Literal expression parsing."""

    def test_integer_literal(self) -> None:
        expr = parse_expr("42")
        self.assertIsInstance(expr, IntLit)
        self.assertEqual(expr.value, 42)

    def test_integer_zero(self) -> None:
        expr = parse_expr("0")
        self.assertIsInstance(expr, IntLit)
        self.assertEqual(expr.value, 0)

    def test_float_literal(self) -> None:
        expr = parse_expr("3.14")
        self.assertIsInstance(expr, FloatLit)
        self.assertAlmostEqual(expr.value, 3.14, places=5)

    def test_bool_true(self) -> None:
        expr = parse_expr("true")
        self.assertIsInstance(expr, BoolLit)
        self.assertTrue(expr.value)

    def test_bool_false(self) -> None:
        expr = parse_expr("false")
        self.assertIsInstance(expr, BoolLit)
        self.assertFalse(expr.value)

    def test_string_literal(self) -> None:
        expr = parse_expr('"hello"')
        self.assertIsInstance(expr, StringLit)
        self.assertEqual(expr.value, "hello")

    def test_none_literal(self) -> None:
        expr = parse_expr("none")
        self.assertIsInstance(expr, NoneLit)

    def test_char_literal(self) -> None:
        expr = parse_expr("'a'")
        self.assertIsInstance(expr, CharLit)


class TestBinaryOperators(unittest.TestCase):
    """Binary operator parsing and precedence."""

    def test_addition(self) -> None:
        expr = parse_expr("1 + 2")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "+")

    def test_subtraction(self) -> None:
        expr = parse_expr("5 - 3")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "-")

    def test_multiplication(self) -> None:
        expr = parse_expr("4 * 5")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "*")

    def test_division(self) -> None:
        expr = parse_expr("10 / 2")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "/")

    def test_modulo(self) -> None:
        expr = parse_expr("7 % 3")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "%")

    def test_floor_division(self) -> None:
        expr = parse_expr("7 </ 3")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "</")

    def test_exponentiation(self) -> None:
        expr = parse_expr("2 ** 10")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "**")

    def test_precedence_mul_over_add(self) -> None:
        # 1 + 2 * 3 must parse as 1 + (2 * 3)
        expr = parse_expr("1 + 2 * 3")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "+")
        self.assertIsInstance(expr.left, IntLit)
        self.assertEqual(expr.left.value, 1)
        self.assertIsInstance(expr.right, BinOp)
        self.assertEqual(expr.right.op, "*")

    def test_precedence_left_assoc_add(self) -> None:
        # 1 + 2 + 3 must parse as (1 + 2) + 3
        expr = parse_expr("1 + 2 + 3")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "+")
        self.assertIsInstance(expr.left, BinOp)
        self.assertEqual(expr.left.op, "+")
        self.assertIsInstance(expr.right, IntLit)

    def test_less_than(self) -> None:
        expr = parse_expr("a < b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "<")

    def test_greater_than(self) -> None:
        expr = parse_expr("a > b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, ">")

    def test_equality(self) -> None:
        expr = parse_expr("a == b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "==")

    def test_not_equal(self) -> None:
        expr = parse_expr("a != b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "!=")

    def test_congruence(self) -> None:
        expr = parse_expr("a === b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "===")

    def test_logical_and(self) -> None:
        expr = parse_expr("a && b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "&&")

    def test_logical_or(self) -> None:
        expr = parse_expr("a || b")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "||")

    def test_precedence_and_over_or(self) -> None:
        # a && b || c must parse as (a && b) || c
        expr = parse_expr("a && b || c")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "||")
        self.assertIsInstance(expr.left, BinOp)
        self.assertEqual(expr.left.op, "&&")


class TestUnaryOperators(unittest.TestCase):
    """Unary operator parsing."""

    def test_unary_minus(self) -> None:
        expr = parse_expr("-x")
        self.assertIsInstance(expr, UnaryOp)
        self.assertEqual(expr.op, "-")
        self.assertIsInstance(expr.operand, Ident)

    def test_logical_not(self) -> None:
        expr = parse_expr("!flag")
        self.assertIsInstance(expr, UnaryOp)
        self.assertEqual(expr.op, "!")
        self.assertIsInstance(expr.operand, Ident)

    def test_copy_operator(self) -> None:
        expr = parse_expr("@data")
        self.assertIsInstance(expr, CopyExpr)
        self.assertIsInstance(expr.inner, Ident)

    def test_ref_operator(self) -> None:
        expr = parse_expr("&data")
        self.assertIsInstance(expr, RefExpr)
        self.assertIsInstance(expr.inner, Ident)


class TestPostfixAndAccessExpressions(unittest.TestCase):
    """Postfix, field access, method call, index access."""

    def test_field_access(self) -> None:
        expr = parse_expr("obj.field")
        self.assertIsInstance(expr, FieldAccess)
        self.assertIsInstance(expr.receiver, Ident)
        self.assertEqual(expr.field, "field")

    def test_chained_field_access(self) -> None:
        expr = parse_expr("a.b.c")
        self.assertIsInstance(expr, FieldAccess)
        self.assertEqual(expr.field, "c")
        self.assertIsInstance(expr.receiver, FieldAccess)
        self.assertEqual(expr.receiver.field, "b")

    def test_method_call(self) -> None:
        expr = parse_expr("obj.method(arg)")
        self.assertIsInstance(expr, MethodCall)
        self.assertIsInstance(expr.receiver, Ident)
        self.assertEqual(expr.method, "method")
        self.assertEqual(len(expr.args), 1)

    def test_method_call_no_args(self) -> None:
        expr = parse_expr("obj.method()")
        self.assertIsInstance(expr, MethodCall)
        self.assertEqual(expr.args, [])

    def test_function_call(self) -> None:
        expr = parse_expr("func(a, b)")
        self.assertIsInstance(expr, Call)
        self.assertIsInstance(expr.callee, Ident)
        self.assertEqual(len(expr.args), 2)

    def test_function_call_no_args(self) -> None:
        expr = parse_expr("func()")
        self.assertIsInstance(expr, Call)
        self.assertEqual(expr.args, [])

    def test_index_access(self) -> None:
        expr = parse_expr("arr[0]")
        self.assertIsInstance(expr, IndexAccess)
        self.assertIsInstance(expr.receiver, Ident)
        self.assertIsInstance(expr.index, IntLit)
        self.assertEqual(expr.index.value, 0)

    def test_propagate_expr(self) -> None:
        expr = parse_expr("result?")
        self.assertIsInstance(expr, PropagateExpr)
        self.assertIsInstance(expr.inner, Ident)


class TestCompositeExpressions(unittest.TestCase):
    """Composite expression forms."""

    def test_null_coalesce(self) -> None:
        expr = parse_expr("x ?? default_val")
        self.assertIsInstance(expr, NullCoalesce)
        self.assertIsInstance(expr.left, Ident)
        self.assertIsInstance(expr.right, Ident)

    def test_ternary_expr(self) -> None:
        expr = parse_expr("a > b ? a : b")
        self.assertIsInstance(expr, TernaryExpr)
        self.assertIsInstance(expr.condition, BinOp)
        self.assertIsInstance(expr.then_expr, Ident)
        self.assertIsInstance(expr.else_expr, Ident)

    def test_array_literal(self) -> None:
        expr = parse_expr("[1, 2, 3]")
        self.assertIsInstance(expr, ArrayLit)
        self.assertEqual(len(expr.elements), 3)

    def test_empty_array_literal(self) -> None:
        expr = parse_expr("[]")
        self.assertIsInstance(expr, ArrayLit)
        self.assertEqual(len(expr.elements), 0)

    def test_tuple_expr(self) -> None:
        expr = parse_expr('(1, "hello")')
        self.assertIsInstance(expr, TupleExpr)
        self.assertEqual(len(expr.elements), 2)

    def test_some_expr(self) -> None:
        expr = parse_expr("some(42)")
        self.assertIsInstance(expr, SomeExpr)
        self.assertIsInstance(expr.inner, IntLit)

    def test_ok_expr(self) -> None:
        expr = parse_expr('ok(result)')
        self.assertIsInstance(expr, OkExpr)

    def test_err_expr(self) -> None:
        expr = parse_expr('err("bad")')
        self.assertIsInstance(expr, ErrExpr)

    def test_typeof_expr(self) -> None:
        expr = parse_expr("typeof(x)")
        self.assertIsInstance(expr, TypeofExpr)
        self.assertIsInstance(expr.inner, Ident)

    def test_coerce_expr(self) -> None:
        expr = parse_expr("coerce(val)")
        self.assertIsInstance(expr, CoerceExpr)

    def test_cast_expr(self) -> None:
        expr = parse_expr("cast<int>(val)")
        self.assertIsInstance(expr, CastExpr)
        self.assertIsNotNone(expr.target_type)

    def test_type_construction(self) -> None:
        expr = parse_expr("Point { x: 1.0, y: 2.0 }")
        self.assertIsInstance(expr, TypeLit)
        self.assertEqual(expr.type_name, "Point")
        self.assertEqual(len(expr.fields), 2)

    def test_type_construction_field_names(self) -> None:
        expr = parse_expr("Point { x: 1.0, y: 2.0 }")
        self.assertIsInstance(expr, TypeLit)
        field_names = [name for name, _ in expr.fields]
        self.assertIn("x", field_names)
        self.assertIn("y", field_names)

    def test_struct_spread(self) -> None:
        expr = parse_expr("Point { x: 9.9, ..p }")
        self.assertIsInstance(expr, TypeLit)
        self.assertIsNotNone(expr.spread)

    def test_struct_no_spread_by_default(self) -> None:
        expr = parse_expr("Point { x: 1.0, y: 2.0 }")
        self.assertIsInstance(expr, TypeLit)
        self.assertIsNone(expr.spread)

    def test_record_literal(self) -> None:
        expr = parse_expr('{ name: "Alice", age: 30 }')
        self.assertIsInstance(expr, RecordLit)
        self.assertEqual(len(expr.fields), 2)

    def test_record_literal_field_names(self) -> None:
        expr = parse_expr('{ name: "Alice", age: 30 }')
        self.assertIsInstance(expr, RecordLit)
        names = [name for name, _ in expr.fields]
        self.assertIn("name", names)
        self.assertIn("age", names)


class TestLambdaExpr(unittest.TestCase):
    """Lambda expression parsing."""

    def test_lambda_single_param(self) -> None:
        expr = parse_expr("\\(x: int => x)")
        self.assertIsInstance(expr, Lambda)
        self.assertEqual(len(expr.params), 1)
        self.assertEqual(expr.params[0].name, "x")

    def test_lambda_multiple_params(self) -> None:
        expr = parse_expr("\\(x: int, y: int => x)")
        self.assertIsInstance(expr, Lambda)
        self.assertEqual(len(expr.params), 2)
        self.assertEqual(expr.params[0].name, "x")
        self.assertEqual(expr.params[1].name, "y")

    def test_lambda_body_is_expr(self) -> None:
        expr = parse_expr("\\(x: int => x)")
        self.assertIsInstance(expr, Lambda)
        self.assertIsInstance(expr.body, Ident)


class TestFStringExpr(unittest.TestCase):
    """F-string expression parsing."""

    def test_fstring_simple(self) -> None:
        expr = parse_expr('f"hello {name}"')
        self.assertIsInstance(expr, FStringExpr)

    def test_fstring_has_parts(self) -> None:
        expr = parse_expr('f"hello {name}"')
        self.assertIsInstance(expr, FStringExpr)
        self.assertGreater(len(expr.parts), 0)

    def test_fstring_text_part(self) -> None:
        expr = parse_expr('f"hello {name}"')
        self.assertIsInstance(expr, FStringExpr)
        # First part should be the text "hello "
        text_parts = [p for p in expr.parts if isinstance(p, str)]
        self.assertTrue(any("hello" in p for p in text_parts))


class TestCompositionChain(unittest.TestCase):
    """Composition chain and fan-out parsing."""

    def test_simple_chain(self) -> None:
        expr = parse_expr("x -> double -> square")
        self.assertIsInstance(expr, CompositionChain)
        self.assertEqual(len(expr.elements), 3)

    def test_chain_elements_are_chain_elements(self) -> None:
        expr = parse_expr("x -> double")
        self.assertIsInstance(expr, CompositionChain)
        for elem in expr.elements:
            self.assertIsInstance(elem, ChainElement)

    def test_fan_out_in_chain(self) -> None:
        # x -> (dbl | sqr) -> mul
        expr = parse_expr("x -> (dbl | sqr) -> mul")
        self.assertIsInstance(expr, CompositionChain)
        # Find the FanOut element in the chain
        fan_out_elements = [
            e for e in expr.elements if isinstance(e.expr, FanOut)
        ]
        self.assertEqual(len(fan_out_elements), 1)

    def test_fan_out_sequential(self) -> None:
        expr = parse_expr("x -> (dbl | sqr) -> mul")
        self.assertIsInstance(expr, CompositionChain)
        fan_out_elements = [
            e for e in expr.elements if isinstance(e.expr, FanOut)
        ]
        fan_out = fan_out_elements[0].expr
        self.assertIsInstance(fan_out, FanOut)
        self.assertFalse(fan_out.parallel)

    def test_parallel_fan_out(self) -> None:
        # x -> <:(validate | compute) -> merge
        expr = parse_expr("x -> <:(validate | compute) -> merge")
        self.assertIsInstance(expr, CompositionChain)
        fan_out_elements = [
            e for e in expr.elements if isinstance(e.expr, FanOut)
        ]
        self.assertEqual(len(fan_out_elements), 1)
        fan_out = fan_out_elements[0].expr
        self.assertIsInstance(fan_out, FanOut)
        self.assertTrue(fan_out.parallel)

    def test_parallel_fan_out_branches(self) -> None:
        expr = parse_expr("x -> <:(validate | compute) -> merge")
        self.assertIsInstance(expr, CompositionChain)
        fan_out_elements = [
            e for e in expr.elements if isinstance(e.expr, FanOut)
        ]
        fan_out = fan_out_elements[0].expr
        self.assertEqual(len(fan_out.branches), 2)


class TestIfExpr(unittest.TestCase):
    """If expression parsing."""

    def test_if_else_expr(self) -> None:
        expr = parse_expr("if (a > b) { a } else { b }")
        self.assertIsInstance(expr, IfExpr)

    def test_if_expr_condition(self) -> None:
        expr = parse_expr("if (a > b) { a } else { b }")
        self.assertIsInstance(expr, IfExpr)
        self.assertIsInstance(expr.condition, BinOp)

    def test_if_expr_then_branch(self) -> None:
        expr = parse_expr("if (a > b) { a } else { b }")
        self.assertIsInstance(expr, IfExpr)
        self.assertIsInstance(expr.then_branch, Block)

    def test_if_expr_else_branch(self) -> None:
        expr = parse_expr("if (a > b) { a } else { b }")
        self.assertIsInstance(expr, IfExpr)
        self.assertIsNotNone(expr.else_branch)


class TestMatchExpr(unittest.TestCase):
    """Match expression parsing."""

    def test_match_expr_basic(self) -> None:
        src = "match x { some(v) : v, none : 0 }"
        expr = parse_expr(src)
        self.assertIsInstance(expr, MatchExpr)

    def test_match_expr_subject(self) -> None:
        src = "match x { some(v) : v, none : 0 }"
        expr = parse_expr(src)
        self.assertIsInstance(expr.subject, Ident)

    def test_match_expr_arm_count(self) -> None:
        src = "match x { some(v) : v, none : 0 }"
        expr = parse_expr(src)
        self.assertEqual(len(expr.arms), 2)

    def test_match_expr_arm_is_match_arm(self) -> None:
        src = "match x { some(v) : v, none : 0 }"
        expr = parse_expr(src)
        for arm in expr.arms:
            self.assertIsInstance(arm, MatchArm)


class TestIdentifierExpr(unittest.TestCase):
    """Identifier expression parsing."""

    def test_simple_ident(self) -> None:
        expr = parse_expr("foo")
        self.assertIsInstance(expr, Ident)
        self.assertEqual(expr.name, "foo")
        self.assertEqual(expr.module_path, [])

    def test_ident_no_module_path(self) -> None:
        expr = parse_expr("x")
        self.assertIsInstance(expr, Ident)
        self.assertEqual(expr.module_path, [])


# ===========================================================================
# RT-4-6-3: Statement parse tests
# ===========================================================================

class TestLetStmt(unittest.TestCase):
    """Let statement parsing."""

    def test_let_with_type_and_value(self) -> None:
        stmt = parse_stmt("let x: int = 42")
        self.assertIsInstance(stmt, LetStmt)
        self.assertEqual(stmt.name, "x")
        self.assertIsNotNone(stmt.type_ann)
        self.assertIsInstance(stmt.value, IntLit)

    def test_let_without_type(self) -> None:
        stmt = parse_stmt('let y = "hello"')
        self.assertIsInstance(stmt, LetStmt)
        self.assertEqual(stmt.name, "y")
        self.assertIsNone(stmt.type_ann)
        self.assertIsInstance(stmt.value, StringLit)

    def test_let_with_mut_type(self) -> None:
        stmt = parse_stmt("let z: int:mut = 0")
        self.assertIsInstance(stmt, LetStmt)
        self.assertEqual(stmt.name, "z")
        self.assertIsNotNone(stmt.type_ann)
        self.assertIsInstance(stmt.type_ann, MutType)

    def test_let_with_option_type(self) -> None:
        stmt = parse_stmt("let a: int? = none")
        self.assertIsInstance(stmt, LetStmt)
        self.assertEqual(stmt.name, "a")
        self.assertIsNotNone(stmt.type_ann)
        self.assertIsInstance(stmt.type_ann, OptionType)

    def test_let_value_integer(self) -> None:
        stmt = parse_stmt("let n: int = 100")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.value, IntLit)
        self.assertEqual(stmt.value.value, 100)

    def test_let_with_coroutine(self) -> None:
        stmt = parse_stmt("let b :< producer(1)")
        self.assertIsInstance(stmt, LetStmt)
        self.assertEqual(stmt.name, "b")
        self.assertIsInstance(stmt.value, CoroutineStart)


class TestAssignStmt(unittest.TestCase):
    """Assignment statement parsing."""

    def test_simple_assignment(self) -> None:
        stmt = parse_stmt("x = 42")
        self.assertIsInstance(stmt, AssignStmt)
        self.assertIsInstance(stmt.target, Ident)
        self.assertIsInstance(stmt.value, IntLit)

    def test_field_assignment(self) -> None:
        stmt = parse_stmt("obj.field = 10")
        self.assertIsInstance(stmt, AssignStmt)
        self.assertIsInstance(stmt.target, FieldAccess)


class TestUpdateStmt(unittest.TestCase):
    """Update statement parsing (+=, -=, *=, /=, ++, --)."""

    def test_plus_assign(self) -> None:
        stmt = parse_stmt("x += 1")
        self.assertIsInstance(stmt, UpdateStmt)
        self.assertEqual(stmt.op, "+=")
        self.assertIsInstance(stmt.value, IntLit)

    def test_minus_assign(self) -> None:
        stmt = parse_stmt("x -= 1")
        self.assertIsInstance(stmt, UpdateStmt)
        self.assertEqual(stmt.op, "-=")

    def test_star_assign(self) -> None:
        stmt = parse_stmt("x *= 2")
        self.assertIsInstance(stmt, UpdateStmt)
        self.assertEqual(stmt.op, "*=")

    def test_slash_assign(self) -> None:
        stmt = parse_stmt("x /= 2")
        self.assertIsInstance(stmt, UpdateStmt)
        self.assertEqual(stmt.op, "/=")

    def test_increment(self) -> None:
        stmt = parse_stmt("x++")
        self.assertIsInstance(stmt, UpdateStmt)
        self.assertEqual(stmt.op, "++")
        self.assertIsNone(stmt.value)

    def test_decrement(self) -> None:
        stmt = parse_stmt("x--")
        self.assertIsInstance(stmt, UpdateStmt)
        self.assertEqual(stmt.op, "--")
        self.assertIsNone(stmt.value)


class TestIfStmt(unittest.TestCase):
    """If statement parsing."""

    def test_simple_if(self) -> None:
        stmt = parse_stmt("if (cond) { return 1 }")
        self.assertIsInstance(stmt, IfStmt)
        self.assertIsInstance(stmt.condition, Ident)
        self.assertIsInstance(stmt.then_branch, Block)
        self.assertIsNone(stmt.else_branch)

    def test_if_else(self) -> None:
        stmt = parse_stmt("if (cond) { return 1 } else { return 2 }")
        self.assertIsInstance(stmt, IfStmt)
        self.assertIsNotNone(stmt.else_branch)
        self.assertIsInstance(stmt.else_branch, Block)

    def test_if_else_if(self) -> None:
        stmt = parse_stmt("if (cond) { return 1 } else if (cond2) { return 2 } else { return 3 }")
        self.assertIsInstance(stmt, IfStmt)
        self.assertIsNotNone(stmt.else_branch)
        self.assertIsInstance(stmt.else_branch, IfStmt)

    def test_if_condition_is_expr(self) -> None:
        stmt = parse_stmt("if (x > 0) { return x }")
        self.assertIsInstance(stmt, IfStmt)
        self.assertIsInstance(stmt.condition, BinOp)

    def test_if_missing_parens(self) -> None:
        with self.assertRaises(ParseError):
            parse_stmt("if cond { return 1 }")


class TestWhileStmt(unittest.TestCase):
    """While statement parsing."""

    def test_simple_while(self) -> None:
        stmt = parse_stmt("while (cond) { x++ }")
        self.assertIsInstance(stmt, WhileStmt)
        self.assertIsInstance(stmt.condition, Ident)
        self.assertIsInstance(stmt.body, Block)

    def test_while_no_finally_by_default(self) -> None:
        stmt = parse_stmt("while (cond) { x++ }")
        self.assertIsInstance(stmt, WhileStmt)
        self.assertIsNone(stmt.finally_block)

    def test_while_condition_is_expr(self) -> None:
        stmt = parse_stmt("while (i < n) { i++ }")
        self.assertIsInstance(stmt, WhileStmt)
        self.assertIsInstance(stmt.condition, BinOp)


class TestForStmt(unittest.TestCase):
    """For loop statement parsing (iteration and C-style forms)."""

    def test_for_iteration(self) -> None:
        stmt = parse_stmt("for(item: int in collection) { return item }")
        self.assertIsInstance(stmt, ForStmt)
        self.assertEqual(stmt.var, "item")
        self.assertIsNotNone(stmt.var_type)
        self.assertIsInstance(stmt.iterable, Ident)

    def test_for_iteration_body(self) -> None:
        stmt = parse_stmt("for(item: int in collection) { return item }")
        self.assertIsInstance(stmt, ForStmt)
        self.assertIsInstance(stmt.body, Block)


class TestReturnYieldThrowBreak(unittest.TestCase):
    """Return, yield, throw, and break statement parsing."""

    def test_return_with_value(self) -> None:
        stmt = parse_stmt("return 42")
        self.assertIsInstance(stmt, ReturnStmt)
        self.assertIsInstance(stmt.value, IntLit)

    def test_return_without_value(self) -> None:
        stmt = parse_stmt("return")
        self.assertIsInstance(stmt, ReturnStmt)
        self.assertIsNone(stmt.value)

    def test_yield_stmt(self) -> None:
        stmt = parse_stmt("yield x")
        self.assertIsInstance(stmt, YieldStmt)
        self.assertIsInstance(stmt.value, Ident)

    def test_throw_stmt(self) -> None:
        stmt = parse_stmt("throw ex")
        self.assertIsInstance(stmt, ThrowStmt)
        self.assertIsInstance(stmt.exception, Ident)

    def test_break_stmt(self) -> None:
        stmt = parse_stmt("break")
        self.assertIsInstance(stmt, BreakStmt)


class TestExprStmt(unittest.TestCase):
    """Expression statement parsing."""

    def test_function_call_as_stmt(self) -> None:
        stmt = parse_stmt("func(arg)")
        self.assertIsInstance(stmt, ExprStmt)
        self.assertIsInstance(stmt.expr, Call)

    def test_method_call_as_stmt(self) -> None:
        stmt = parse_stmt("obj.method()")
        self.assertIsInstance(stmt, ExprStmt)
        self.assertIsInstance(stmt.expr, MethodCall)


class TestMatchStmt(unittest.TestCase):
    """Match statement parsing."""

    def test_match_stmt_basic(self) -> None:
        src = "match x { some(v) : { return v }, none : { return 0 } }"
        stmt = parse_stmt(src)
        self.assertIsInstance(stmt, MatchStmt)

    def test_match_stmt_subject(self) -> None:
        src = "match x { some(v) : { return v }, none : { return 0 } }"
        stmt = parse_stmt(src)
        self.assertIsInstance(stmt.subject, Ident)

    def test_match_stmt_arms(self) -> None:
        src = "match x { some(v) : { return v }, none : { return 0 } }"
        stmt = parse_stmt(src)
        self.assertEqual(len(stmt.arms), 2)

    def test_match_stmt_arm_types(self) -> None:
        src = "match x { some(v) : { return v }, none : { return 0 } }"
        stmt = parse_stmt(src)
        for arm in stmt.arms:
            self.assertIsInstance(arm, MatchArm)


class TestTryStmt(unittest.TestCase):
    """Try/catch statement parsing."""

    def test_try_catch_basic(self) -> None:
        src = "try { return 1 } catch (ex: Error) { return 0 }"
        stmt = parse_stmt(src)
        self.assertIsInstance(stmt, TryStmt)

    def test_try_catch_body(self) -> None:
        src = "try { return 1 } catch (ex: Error) { return 0 }"
        stmt = parse_stmt(src)
        self.assertIsInstance(stmt.body, Block)

    def test_try_catch_blocks(self) -> None:
        src = "try { return 1 } catch (ex: Error) { return 0 }"
        stmt = parse_stmt(src)
        self.assertEqual(len(stmt.catch_blocks), 1)
        self.assertIsInstance(stmt.catch_blocks[0], CatchBlock)

    def test_try_catch_exception_var(self) -> None:
        src = "try { return 1 } catch (ex: Error) { return 0 }"
        stmt = parse_stmt(src)
        catch = stmt.catch_blocks[0]
        self.assertEqual(catch.exception_var, "ex")

    def test_try_retry_catch(self) -> None:
        src = (
            "try { return 1 } "
            "retry target_fn (ex: Error, attempts: 3) { return 0 } "
            "catch (ex: Error) { return 0 }"
        )
        stmt = parse_stmt(src)
        self.assertIsInstance(stmt, TryStmt)
        self.assertEqual(len(stmt.retry_blocks), 1)
        self.assertIsInstance(stmt.retry_blocks[0], RetryBlock)

    def test_try_retry_target_fn(self) -> None:
        src = (
            "try { return 1 } "
            "retry target_fn (ex: Error, attempts: 3) { return 0 } "
            "catch (ex: Error) { return 0 }"
        )
        stmt = parse_stmt(src)
        retry = stmt.retry_blocks[0]
        self.assertEqual(retry.target_fn, "target_fn")

    def test_try_retry_attempts(self) -> None:
        src = (
            "try { return 1 } "
            "retry target_fn (ex: Error, attempts: 3) { return 0 } "
            "catch (ex: Error) { return 0 }"
        )
        stmt = parse_stmt(src)
        retry = stmt.retry_blocks[0]
        self.assertIsInstance(retry.attempts, IntLit)
        self.assertEqual(retry.attempts.value, 3)

    def test_try_no_retry_blocks_by_default(self) -> None:
        src = "try { return 1 } catch (ex: Error) { return 0 }"
        stmt = parse_stmt(src)
        self.assertEqual(stmt.retry_blocks, [])


# ===========================================================================
# Pattern tests (part of RT-4-6-3)
# ===========================================================================

class TestPatterns(unittest.TestCase):
    """Pattern parsing in match arms."""

    def _get_patterns(self, match_src: str) -> list:
        """Parse a match expression and return the list of arm patterns."""
        stmt = parse_stmt(match_src)
        self.assertIsInstance(stmt, MatchStmt)
        return [arm.pattern for arm in stmt.arms]

    def test_wildcard_pattern(self) -> None:
        src = "match x { _ : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], WildcardPattern)

    def test_literal_int_pattern(self) -> None:
        src = "match x { 42 : 1, _ : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], LiteralPattern)
        self.assertIsInstance(patterns[0].value, IntLit)

    def test_literal_string_pattern(self) -> None:
        src = 'match x { "hello" : 1, _ : 0 }'
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], LiteralPattern)
        self.assertIsInstance(patterns[0].value, StringLit)

    def test_literal_bool_pattern(self) -> None:
        src = "match x { true : 1, false : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], LiteralPattern)

    def test_some_pattern(self) -> None:
        src = "match x { some(v) : v, none : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], SomePattern)
        self.assertEqual(patterns[0].inner_var, "v")

    def test_none_pattern(self) -> None:
        src = "match x { some(v) : v, none : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[1], NonePattern)

    def test_ok_pattern(self) -> None:
        src = "match x { ok(v) : v, err(e) : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], OkPattern)
        self.assertEqual(patterns[0].inner_var, "v")

    def test_err_pattern(self) -> None:
        src = "match x { ok(v) : v, err(e) : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[1], ErrPattern)
        self.assertEqual(patterns[1].inner_var, "e")

    def test_variant_pattern_single_binding(self) -> None:
        src = "match x { Circle(r) : r, _ : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], VariantPattern)
        self.assertEqual(patterns[0].variant_name, "Circle")
        self.assertEqual(patterns[0].bindings, ["r"])

    def test_variant_pattern_multiple_bindings(self) -> None:
        src = "match x { Rectangle(w, h) : w, _ : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], VariantPattern)
        self.assertEqual(patterns[0].variant_name, "Rectangle")
        self.assertEqual(patterns[0].bindings, ["w", "h"])

    def test_tuple_pattern(self) -> None:
        src = "match x { (a, b) : a, _ : 0 }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], TuplePattern)
        self.assertEqual(len(patterns[0].elements), 2)

    def test_bind_pattern(self) -> None:
        src = "match x { n : n }"
        patterns = self._get_patterns(src)
        self.assertIsInstance(patterns[0], BindPattern)
        self.assertEqual(patterns[0].name, "n")


# ===========================================================================
# RT-4-6-4: Error recovery tests
# ===========================================================================

class TestParseErrors(unittest.TestCase):
    """Parser error detection and error recovery tests."""

    def test_missing_closing_brace_raises_parse_error(self) -> None:
        with self.assertRaises(ParseError):
            parse("fn foo(): int { return 1")

    def test_unexpected_token_raises_parse_error(self) -> None:
        # 'fn' keyword where an expression is expected
        with self.assertRaises(ParseError):
            parse("fn foo(): int = fn")

    def test_parse_error_has_message(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse("fn foo(): int { return 1")
        self.assertIsInstance(ctx.exception.message, str)
        self.assertTrue(len(ctx.exception.message) > 0)

    def test_parse_error_has_file(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse("fn foo(): int { return 1")
        self.assertEqual(ctx.exception.file, "test.flow")

    def test_parse_error_has_line(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse("fn foo(): int { return 1")
        self.assertIsInstance(ctx.exception.line, int)
        self.assertGreater(ctx.exception.line, 0)

    def test_parse_error_has_col(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse("fn foo(): int { return 1")
        self.assertIsInstance(ctx.exception.col, int)
        self.assertGreater(ctx.exception.col, 0)

    def test_missing_colon_in_let_raises_parse_error(self) -> None:
        with self.assertRaises(ParseError):
            # let x int = 42 is missing the colon
            parse("fn foo(): none { let x int = 42 }")

    def test_malformed_fn_signature_raises_parse_error(self) -> None:
        with self.assertRaises(ParseError):
            # Missing closing paren
            parse("fn foo(x: int : int = x")

    def test_error_recovery_two_errors(self) -> None:
        # A source with two syntactic errors should produce ParseError(s).
        # The parser either collects multiple errors or raises on the first.
        # Either way, a ParseError must be raised.
        src = (
            "fn foo(): int { return 1\n"
            "fn bar(): int { return 2\n"
        )
        with self.assertRaises(ParseError):
            parse(src)

    def test_empty_source_parses_ok(self) -> None:
        # An empty source has no module declaration but should not crash.
        mod = parse("")
        self.assertIsInstance(mod, Module)

    def test_module_only_parses_ok(self) -> None:
        mod = parse("module main")
        self.assertIsInstance(mod, Module)
        self.assertEqual(mod.path, ["main"])
        self.assertEqual(mod.decls, [])
        self.assertEqual(mod.imports, [])


# ===========================================================================
# Additional coverage: type expressions
# ===========================================================================

class TestTypeExpressions(unittest.TestCase):
    """Type annotation parsing in declarations and let statements."""

    def test_named_type(self) -> None:
        stmt = parse_stmt("let x: int = 0")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, NamedType)
        self.assertEqual(stmt.type_ann.name, "int")

    def test_option_type(self) -> None:
        stmt = parse_stmt("let x: int? = none")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, OptionType)

    def test_mut_type(self) -> None:
        stmt = parse_stmt("let x: int:mut = 0")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, MutType)

    def test_generic_type(self) -> None:
        stmt = parse_stmt("let x: array<int> = []")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, GenericType)

    def test_generic_type_args(self) -> None:
        stmt = parse_stmt("let x: array<int> = []")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, GenericType)
        self.assertEqual(len(stmt.type_ann.args), 1)

    def test_fn_param_named_type(self) -> None:
        decl = parse_first_decl("fn foo(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsInstance(decl.params[0].type_ann, NamedType)

    def test_fn_return_named_type(self) -> None:
        decl = parse_first_decl("fn foo(x: int): int = x")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNotNone(decl.return_type)
        self.assertIsInstance(decl.return_type, NamedType)

    def test_sized_type_on_stream(self) -> None:
        """stream<int>[64] parses as SizedType wrapping GenericType."""
        stmt = parse_stmt("let x: stream<int>[64] = none")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, SizedType)
        self.assertIsInstance(stmt.type_ann.inner, GenericType)
        self.assertIsInstance(stmt.type_ann.capacity, IntLit)
        self.assertEqual(stmt.type_ann.capacity.value, 64)

    def test_sized_type_on_fn_return(self) -> None:
        """fn signature with [N] on return type."""
        decl = parse_first_decl(
            "fn producer(seed: int): stream<int>[128] { yield 1 }")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsInstance(decl.return_type, SizedType)
        self.assertIsInstance(decl.return_type.inner, GenericType)
        self.assertIsInstance(decl.return_type.capacity, IntLit)
        self.assertEqual(decl.return_type.capacity.value, 128)

    def test_sized_type_on_param(self) -> None:
        """fn param with [N] on stream type."""
        decl = parse_first_decl(
            "fn handler(inbox: stream<string>[32]): stream<int> { yield 1 }")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsInstance(decl.params[0].type_ann, SizedType)
        self.assertEqual(decl.params[0].type_ann.capacity.value, 32)

    def test_sized_type_with_option(self) -> None:
        """stream<int>[64]? — SizedType then option."""
        stmt = parse_stmt("let x: stream<int>[64]? = none")
        self.assertIsInstance(stmt, LetStmt)
        self.assertIsInstance(stmt.type_ann, OptionType)
        self.assertIsInstance(stmt.type_ann.inner, SizedType)


# ===========================================================================
# Additional coverage: module structure
# ===========================================================================

class TestModuleStructure(unittest.TestCase):
    """Module-level structure and top-level declaration ordering."""

    def test_module_with_multiple_decls(self) -> None:
        src = (
            "module main\n"
            "fn foo(): int = 1\n"
            "fn bar(): int = 2\n"
        )
        mod = parse(src)
        self.assertEqual(len(mod.decls), 2)

    def test_module_decls_are_fn_decls(self) -> None:
        src = (
            "module main\n"
            "fn foo(): int = 1\n"
            "fn bar(): int = 2\n"
        )
        mod = parse(src)
        for decl in mod.decls:
            self.assertIsInstance(decl, FnDecl)

    def test_module_with_import_and_fn(self) -> None:
        src = (
            "module main\n"
            "import io\n"
            "fn main(): none { return }\n"
        )
        mod = parse(src)
        self.assertEqual(len(mod.imports), 1)
        self.assertEqual(len(mod.decls), 1)
        self.assertIsInstance(mod.decls[0], FnDecl)

    def test_module_imports_come_before_decls(self) -> None:
        src = (
            "module main\n"
            "import io\n"
            "import math\n"
            "fn run(): none { return }\n"
        )
        mod = parse(src)
        self.assertEqual(len(mod.imports), 2)
        self.assertEqual(len(mod.decls), 1)

    def test_module_without_decl_has_empty_path(self) -> None:
        # A file with no module declaration has an empty path
        mod = parse("fn foo(): int = 1")
        self.assertIsInstance(mod, Module)
        self.assertIsInstance(mod.path, list)

    def test_module_decl_followed_by_type(self) -> None:
        src = "module shapes\ntype Circle { radius: float }"
        mod = parse(src)
        self.assertEqual(mod.path, ["shapes"])
        self.assertEqual(len(mod.decls), 1)
        self.assertIsInstance(mod.decls[0], TypeDecl)


# ===========================================================================
# Additional expression edge cases
# ===========================================================================

class TestExpressionEdgeCases(unittest.TestCase):
    """Edge cases in expression parsing."""

    def test_nested_calls(self) -> None:
        expr = parse_expr("outer(inner(x))")
        self.assertIsInstance(expr, Call)
        self.assertEqual(len(expr.args), 1)
        self.assertIsInstance(expr.args[0], Call)

    def test_nested_field_access_and_call(self) -> None:
        expr = parse_expr("obj.method().field")
        self.assertIsInstance(expr, FieldAccess)
        self.assertIsInstance(expr.receiver, MethodCall)

    def test_index_then_field(self) -> None:
        expr = parse_expr("arr[0].name")
        self.assertIsInstance(expr, FieldAccess)
        self.assertIsInstance(expr.receiver, IndexAccess)

    def test_binary_op_left_operand(self) -> None:
        expr = parse_expr("x + y")
        self.assertIsInstance(expr, BinOp)
        self.assertIsInstance(expr.left, Ident)
        self.assertEqual(expr.left.name, "x")

    def test_binary_op_right_operand(self) -> None:
        expr = parse_expr("x + y")
        self.assertIsInstance(expr, BinOp)
        self.assertIsInstance(expr.right, Ident)
        self.assertEqual(expr.right.name, "y")

    def test_int_literal_no_suffix(self) -> None:
        expr = parse_expr("42")
        self.assertIsInstance(expr, IntLit)
        self.assertIsNone(expr.suffix)

    def test_precedence_comparison_over_equality(self) -> None:
        # a < b == c < d should parse as (a < b) == (c < d)
        expr = parse_expr("a < b == c < d")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "==")
        self.assertIsInstance(expr.left, BinOp)
        self.assertEqual(expr.left.op, "<")

    def test_parenthesized_expr(self) -> None:
        # Parenthesized expression overrides precedence
        expr = parse_expr("(1 + 2) * 3")
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, "*")
        self.assertIsInstance(expr.left, BinOp)
        self.assertEqual(expr.left.op, "+")

    def test_negation_of_call(self) -> None:
        expr = parse_expr("-func()")
        self.assertIsInstance(expr, UnaryOp)
        self.assertEqual(expr.op, "-")
        self.assertIsInstance(expr.operand, Call)

    def test_propagate_on_call(self) -> None:
        expr = parse_expr("read_file(path)?")
        self.assertIsInstance(expr, PropagateExpr)
        self.assertIsInstance(expr.inner, Call)

    def test_null_coalesce_precedence_over_or(self) -> None:
        # a ?? b || c  — ?? is lowest precedence, so parses as (a ?? b) || c...
        # Actually per plan: ?? is precedence 1 (lowest), || is 2.
        # So a ?? b || c parses as a ?? (b || c).
        # But let's just verify the outer node is NullCoalesce.
        expr = parse_expr("a ?? b || c")
        # outer should be NullCoalesce since it's lowest precedence
        self.assertIsInstance(expr, NullCoalesce)


class TestBoundedGenerics(unittest.TestCase):
    """BG-1-3-2: Parser tests for bounded generic type parameters."""

    def test_single_bound(self) -> None:
        decl = parse_first_decl(
            "fn f<T fulfills Printable>(x: T): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 1)
        tp = decl.type_params[0]
        self.assertEqual(tp.name, "T")
        self.assertEqual(len(tp.bounds), 1)
        self.assertIsInstance(tp.bounds[0], NamedType)
        self.assertEqual(tp.bounds[0].name, "Printable")

    def test_no_bound_unchanged(self) -> None:
        decl = parse_first_decl("fn f<T>(x: T): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 1)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(decl.type_params[0].bounds, [])

    def test_multiple_params_each_bounded(self) -> None:
        decl = parse_first_decl(
            "fn f<T fulfills A, U fulfills B>(x: T, y: U): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 2)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(len(decl.type_params[0].bounds), 1)
        self.assertEqual(decl.type_params[0].bounds[0].name, "A")
        self.assertEqual(decl.type_params[1].name, "U")
        self.assertEqual(len(decl.type_params[1].bounds), 1)
        self.assertEqual(decl.type_params[1].bounds[0].name, "B")

    def test_multi_bound_parenthesized(self) -> None:
        decl = parse_first_decl(
            "fn f<T fulfills (A, B)>(x: T): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 1)
        tp = decl.type_params[0]
        self.assertEqual(tp.name, "T")
        self.assertEqual(len(tp.bounds), 2)
        self.assertEqual(tp.bounds[0].name, "A")
        self.assertEqual(tp.bounds[1].name, "B")

    def test_generic_interface_bound(self) -> None:
        decl = parse_first_decl(
            "fn f<T fulfills Mappable<int>>(x: T): void {}")
        self.assertIsInstance(decl, FnDecl)
        tp = decl.type_params[0]
        self.assertEqual(len(tp.bounds), 1)
        self.assertIsInstance(tp.bounds[0], GenericType)

    def test_bounded_type_decl(self) -> None:
        decl = parse_first_decl(
            "type Box<T fulfills P> { val: T }")
        self.assertIsInstance(decl, TypeDecl)
        self.assertEqual(len(decl.type_params), 1)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(len(decl.type_params[0].bounds), 1)
        self.assertEqual(decl.type_params[0].bounds[0].name, "P")

    def test_bounded_interface_decl(self) -> None:
        decl = parse_first_decl(
            "interface Container<T fulfills Comparable> {\n"
            "    fn min(self): T\n"
            "}")
        self.assertIsInstance(decl, InterfaceDecl)
        self.assertEqual(len(decl.type_params), 1)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(len(decl.type_params[0].bounds), 1)

    def test_bounded_alias_decl(self) -> None:
        decl = parse_first_decl(
            "alias Sorted<T fulfills Comparable>: array<T>")
        self.assertIsInstance(decl, AliasDecl)
        self.assertEqual(len(decl.type_params), 1)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(len(decl.type_params[0].bounds), 1)

    def test_mixed_bounded_unbounded(self) -> None:
        decl = parse_first_decl(
            "fn f<T fulfills A, U>(x: T, y: U): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 2)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(len(decl.type_params[0].bounds), 1)
        self.assertEqual(decl.type_params[1].name, "U")
        self.assertEqual(len(decl.type_params[1].bounds), 0)

    def test_disambiguation_comma(self) -> None:
        """<T fulfills A, B> = two params: T with bound A, unbounded B."""
        decl = parse_first_decl(
            "fn f<T fulfills A, B>(x: T, y: B): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.type_params), 2)
        self.assertEqual(decl.type_params[0].name, "T")
        self.assertEqual(len(decl.type_params[0].bounds), 1)
        self.assertEqual(decl.type_params[0].bounds[0].name, "A")
        self.assertEqual(decl.type_params[1].name, "B")
        self.assertEqual(len(decl.type_params[1].bounds), 0)


# ---------------------------------------------------------------------------
# Default parameter values
# ---------------------------------------------------------------------------

class TestDefaultParams(unittest.TestCase):
    """Tests for default parameter value parsing."""

    def test_single_default(self) -> None:
        decl = parse_first_decl(
            "fn connect(host: string, port: int = 80): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertEqual(len(decl.params), 2)
        self.assertIsNone(decl.params[0].default)
        self.assertIsNotNone(decl.params[1].default)
        self.assertIsInstance(decl.params[1].default, IntLit)
        self.assertEqual(decl.params[1].default.value, 80)

    def test_multiple_defaults(self) -> None:
        decl = parse_first_decl(
            "fn f(a: int, b: int = 1, c: int = 2): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNone(decl.params[0].default)
        self.assertIsInstance(decl.params[1].default, IntLit)
        self.assertIsInstance(decl.params[2].default, IntLit)

    def test_all_defaults(self) -> None:
        decl = parse_first_decl(
            "fn f(a: int = 0, b: string = \"hi\"): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsInstance(decl.params[0].default, IntLit)
        self.assertIsInstance(decl.params[1].default, StringLit)

    def test_none_default(self) -> None:
        decl = parse_first_decl(
            "fn f(x: int?, y: string? = none): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNone(decl.params[0].default)
        self.assertIsInstance(decl.params[1].default, NoneLit)

    def test_no_default_after_default_errors(self) -> None:
        with self.assertRaises(ParseError):
            parse("fn f(a: int = 1, b: int): void {}")

    def test_no_defaults(self) -> None:
        decl = parse_first_decl("fn f(x: int, y: string): void {}")
        self.assertIsInstance(decl, FnDecl)
        self.assertIsNone(decl.params[0].default)
        self.assertIsNone(decl.params[1].default)


# ---------------------------------------------------------------------------
# Named arguments
# ---------------------------------------------------------------------------

class TestNamedArgs(unittest.TestCase):
    """Tests for named argument parsing."""

    def test_single_named_arg(self) -> None:
        mod = parse("fn main(): none { f(x: 1) }")
        fn = mod.decls[0]
        call = fn.body.stmts[0].expr
        self.assertIsInstance(call, Call)
        self.assertEqual(len(call.args), 1)
        self.assertIsInstance(call.args[0], NamedArg)
        self.assertEqual(call.args[0].name, "x")
        self.assertIsInstance(call.args[0].value, IntLit)

    def test_mixed_positional_and_named(self) -> None:
        mod = parse("fn main(): none { f(1, y: 2) }")
        fn = mod.decls[0]
        call = fn.body.stmts[0].expr
        self.assertIsInstance(call, Call)
        self.assertEqual(len(call.args), 2)
        self.assertIsInstance(call.args[0], IntLit)
        self.assertIsInstance(call.args[1], NamedArg)
        self.assertEqual(call.args[1].name, "y")

    def test_all_named_args(self) -> None:
        mod = parse("fn main(): none { f(a: 1, b: 2) }")
        fn = mod.decls[0]
        call = fn.body.stmts[0].expr
        self.assertEqual(len(call.args), 2)
        self.assertIsInstance(call.args[0], NamedArg)
        self.assertIsInstance(call.args[1], NamedArg)

    def test_positional_after_named_errors(self) -> None:
        with self.assertRaises(ParseError):
            parse("fn main(): none { f(x: 1, 2) }")


class TestExternDecls(unittest.TestCase):
    """Tests for extern lib/type/fn declarations (FFI)."""

    def test_extern_lib(self) -> None:
        mod = parse('extern lib "z"')
        self.assertEqual(len(mod.decls), 1)
        d = mod.decls[0]
        self.assertIsInstance(d, ExternLibDecl)
        self.assertEqual(d.lib_name, "z")

    def test_extern_type(self) -> None:
        mod = parse("extern type SSL_CTX")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternTypeDecl)
        self.assertEqual(d.name, "SSL_CTX")
        self.assertFalse(d.is_export)

    def test_export_extern_type(self) -> None:
        mod = parse("export extern type SSL_CTX")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternTypeDecl)
        self.assertTrue(d.is_export)

    def test_extern_fn_no_return(self) -> None:
        mod = parse("extern fn free(p:ptr)")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "free")
        self.assertIsNone(d.c_name)
        self.assertEqual(len(d.params), 1)
        self.assertEqual(d.params[0].name, "p")
        self.assertIsNone(d.return_type)
        self.assertFalse(d.is_export)

    def test_extern_fn_with_return(self) -> None:
        mod = parse("extern fn strlen(s:ptr):int")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "strlen")
        self.assertIsNone(d.c_name)
        self.assertEqual(len(d.params), 1)
        self.assertIsInstance(d.return_type, NamedType)
        self.assertEqual(d.return_type.name, "int")

    def test_extern_fn_multiple_params(self) -> None:
        mod = parse("extern fn SSL_write(ssl:ptr, buf:ptr, n:int):int")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "SSL_write")
        self.assertEqual(len(d.params), 3)

    def test_export_extern_fn(self) -> None:
        mod = parse("export extern fn abs(x:int):int")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertTrue(d.is_export)

    def test_export_extern_lib_error(self) -> None:
        with self.assertRaises(ParseError):
            parse('export extern lib "x"')

    def test_extern_bad_keyword_error(self) -> None:
        with self.assertRaises(ParseError):
            parse("extern badword")

    def test_multiple_extern_decls(self) -> None:
        src = '''extern lib "ssl"
extern type SSL_CTX
extern fn SSL_CTX_new():ptr'''
        mod = parse(src)
        self.assertEqual(len(mod.decls), 3)
        self.assertIsInstance(mod.decls[0], ExternLibDecl)
        self.assertIsInstance(mod.decls[1], ExternTypeDecl)
        self.assertIsInstance(mod.decls[2], ExternFnDecl)

    def test_extern_fn_alias_syntax(self) -> None:
        mod = parse('extern fn "fl_math_floor" floor(f:float):float')
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "floor")
        self.assertEqual(d.c_name, "fl_math_floor")
        self.assertEqual(len(d.params), 1)
        self.assertEqual(d.params[0].name, "f")
        self.assertIsInstance(d.return_type, NamedType)
        self.assertEqual(d.return_type.name, "float")

    def test_extern_fn_alias_no_return(self) -> None:
        mod = parse('extern fn "c_free" free_ptr(p:ptr)')
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "free_ptr")
        self.assertEqual(d.c_name, "c_free")
        self.assertIsNone(d.return_type)

    def test_extern_fn_alias_export(self) -> None:
        mod = parse('export extern fn "SSL_connect" connect(ssl:ptr):int')
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "connect")
        self.assertEqual(d.c_name, "SSL_connect")
        self.assertTrue(d.is_export)

    def test_extern_fn_alias_multiple_params(self) -> None:
        mod = parse('extern fn "sqlite3_open" db_open(path:string, db:ptr):int')
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "db_open")
        self.assertEqual(d.c_name, "sqlite3_open")
        self.assertEqual(len(d.params), 2)

    def test_extern_fn_generic_single_type_param(self) -> None:
        mod = parse('extern fn "fl_push" push<T>(arr:array<T>, val:T):array<T>')
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "push")
        self.assertEqual(d.c_name, "fl_push")
        self.assertEqual(len(d.type_params), 1)
        self.assertEqual(d.type_params[0].name, "T")
        self.assertEqual(len(d.type_params[0].bounds), 0)
        self.assertEqual(len(d.params), 2)

    def test_extern_fn_generic_with_bounds(self) -> None:
        mod = parse(
            'extern fn "fl_sort" sort<T fulfills Comparable>'
            '(arr:array<T>):array<T>')
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.name, "sort")
        self.assertEqual(len(d.type_params), 1)
        self.assertEqual(d.type_params[0].name, "T")
        self.assertEqual(len(d.type_params[0].bounds), 1)

    def test_extern_fn_non_generic_has_empty_type_params(self) -> None:
        mod = parse("extern fn free(p:ptr)")
        d = mod.decls[0]
        self.assertIsInstance(d, ExternFnDecl)
        self.assertEqual(d.type_params, [])


if __name__ == "__main__":
    unittest.main()
