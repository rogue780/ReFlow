# tests/unit/test_resolver.py — Resolver unit tests
#
# Covers RT-5-4-1 (undefined variable), RT-5-4-2 (lambda capture vs nested fn),
# RT-5-4-3 (forward references), RT-5-4-4 (self outside method).
# Also covers RT-5-3-1 through RT-5-3-4 (scope violation checks).
from __future__ import annotations

import unittest

from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.errors import ResolveError
from compiler.resolver import (
    Resolver, ResolvedModule, Symbol, SymbolKind, Scope,
    ModuleScope,
)
from compiler.ast_nodes import (
    Ident, Lambda, FnDecl, TypeDecl, LetStmt, FieldAccess,
    NamedType, MutType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve(source: str,
            imported: dict[str, ModuleScope] | None = None) -> ResolvedModule:
    """Lex, parse, and resolve *source*."""
    tokens = Lexer(source, "test.reflow").tokenize()
    mod = Parser(tokens, "test.reflow").parse()
    return Resolver(mod, imported).resolve()


def resolve_symbols(source: str) -> dict:
    """Return the symbols dict from resolving *source*."""
    return resolve(source).symbols


def find_idents(result: ResolvedModule) -> list[tuple[str, Symbol]]:
    """Return (name, symbol) pairs for all resolved Ident nodes."""
    return [
        (node.name, sym)
        for node, sym in result.symbols.items()
        if isinstance(node, Ident)
    ]


# ---------------------------------------------------------------------------
# Story 5-4: Resolver Tests
# ---------------------------------------------------------------------------


class TestBasicResolution(unittest.TestCase):
    """Basic name resolution: locals, params, literals."""

    def test_resolve_param_reference(self):
        src = """fn add(x: int, y: int): int {
    return x
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        name, sym = idents[0]
        self.assertEqual(name, "x")
        self.assertEqual(sym.kind, SymbolKind.PARAM)

    def test_resolve_local_variable(self):
        src = """fn main(): none {
    let x = 5
    let y = x
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        name, sym = idents[0]
        self.assertEqual(name, "x")
        self.assertEqual(sym.kind, SymbolKind.LOCAL)

    def test_resolve_function_call(self):
        src = """fn greet(): none { }
fn main(): none {
    greet()
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        name, sym = idents[0]
        self.assertEqual(name, "greet")
        self.assertEqual(sym.kind, SymbolKind.FN)

    def test_literals_need_no_resolution(self):
        src = """fn main(): none {
    let a = 42
    let b = 3.14
    let c = true
    let d = "hello"
    let e = none
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 0)

    def test_multiple_params(self):
        src = """fn add(a: int, b: int, c: int): int {
    let x = a
    let y = b
    let z = c
    return x
}"""
        result = resolve(src)
        idents = find_idents(result)
        # a, b, c referenced from let stmts, x referenced from return
        self.assertEqual(len(idents), 4)
        names = [name for name, _ in idents]
        self.assertIn("a", names)
        self.assertIn("b", names)
        self.assertIn("c", names)
        self.assertIn("x", names)


class TestForwardReferences(unittest.TestCase):
    """RT-5-4-3: forward reference tests."""

    def test_forward_ref_function_call(self):
        """Function a calls function b defined later."""
        src = """fn a(): none {
    b()
}
fn b(): none { }"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        name, sym = idents[0]
        self.assertEqual(name, "b")
        self.assertEqual(sym.kind, SymbolKind.FN)

    def test_forward_ref_type(self):
        """Function references a type declared later."""
        src = """fn make(): none {
    let p = Point { x: 1, y: 2 }
}
type Point {
    x: int
    y: int
}"""
        result = resolve(src)
        # TypeLit resolves the type name
        found_point = False
        for node, sym in result.symbols.items():
            if sym.name == "Point":
                found_point = True
                self.assertEqual(sym.kind, SymbolKind.TYPE)
        self.assertTrue(found_point)

    def test_mutual_forward_ref(self):
        """Two functions reference each other."""
        src = """fn a(): none {
    b()
}
fn b(): none {
    a()
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("a", names)
        self.assertIn("b", names)


class TestScopeAndShadowing(unittest.TestCase):
    """Scope chaining and shadowing rules."""

    def test_inner_scope_shadows_outer(self):
        """Inner scope silently shadows outer name (per spec)."""
        src = """fn main(): none {
    let x = 5
    if true {
        let x = 10
        let y = x
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        # The x referenced in inner scope should resolve to inner x (LOCAL)
        self.assertEqual(len(idents), 1)
        _, sym = idents[0]
        self.assertEqual(sym.kind, SymbolKind.LOCAL)

    def test_nested_block_accesses_outer(self):
        """Inner block can access names from enclosing scope."""
        src = """fn main(): none {
    let x = 5
    if true {
        let y = x
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        _, sym = idents[0]
        self.assertEqual(sym.name, "x")
        self.assertEqual(sym.kind, SymbolKind.LOCAL)

    def test_for_loop_var_in_scope(self):
        """For loop variable is in scope within the loop body."""
        src = """fn main(): none {
    let items = [1, 2, 3]
    for (item in items) {
        let x = item
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("items", names)
        self.assertIn("item", names)


class TestUndefinedNames(unittest.TestCase):
    """RT-5-4-1: undefined variable raises ResolveError."""

    def test_undefined_variable(self):
        src = """fn main(): none {
    let x = y
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("undefined name 'y'", ctx.exception.message)
        self.assertEqual(ctx.exception.file, "test.reflow")
        self.assertGreater(ctx.exception.line, 0)
        self.assertGreater(ctx.exception.col, 0)

    def test_undefined_function(self):
        src = """fn main(): none {
    foo()
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("undefined name 'foo'", ctx.exception.message)

    def test_undefined_type_in_type_lit(self):
        src = """fn main(): none {
    let p = Unknown { x: 1 }
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("undefined name 'Unknown'", ctx.exception.message)


class TestDuplicateDefinitions(unittest.TestCase):
    """Duplicate definitions in the same scope raise errors."""

    def test_duplicate_local_same_scope(self):
        src = """fn main(): none {
    let x = 5
    let x = 10
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("duplicate definition of 'x'", ctx.exception.message)

    def test_duplicate_top_level_fn(self):
        src = """fn foo(): none { }
fn foo(): none { }"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("duplicate definition of 'foo'", ctx.exception.message)

    def test_duplicate_param_names(self):
        src = """fn add(x: int, x: int): int {
    return x
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("duplicate definition of 'x'", ctx.exception.message)


class TestLambdaCapture(unittest.TestCase):
    """RT-5-4-2: lambda capture tests."""

    def test_lambda_captures_outer_local(self):
        src = """fn outer(): none {
    let x = 5
    let f = \\(y: int => x)
}"""
        result = resolve(src)
        self.assertEqual(len(result.captures), 1)
        for lam, caps in result.captures.items():
            self.assertIsInstance(lam, Lambda)
            self.assertEqual(len(caps), 1)
            self.assertEqual(caps[0].name, "x")

    def test_lambda_captures_param(self):
        src = """fn outer(z: int): none {
    let f = \\(y: int => z)
}"""
        result = resolve(src)
        self.assertEqual(len(result.captures), 1)
        for _, caps in result.captures.items():
            self.assertEqual(len(caps), 1)
            self.assertEqual(caps[0].name, "z")
            self.assertEqual(caps[0].kind, SymbolKind.PARAM)

    def test_lambda_no_capture_for_own_params(self):
        src = """fn outer(): none {
    let f = \\(x: int => x)
}"""
        result = resolve(src)
        for _, caps in result.captures.items():
            self.assertEqual(len(caps), 0)

    def test_lambda_captures_multiple(self):
        src = """fn outer(): none {
    let a = 1
    let b = 2
    let f = \\(x: int => a)
}"""
        result = resolve(src)
        for _, caps in result.captures.items():
            # Only 'a' is captured (b is not referenced)
            self.assertEqual(len(caps), 1)
            self.assertEqual(caps[0].name, "a")


class TestSelfResolution(unittest.TestCase):
    """RT-5-4-4 and RT-5-3-3: self validity checks."""

    def test_self_valid_in_method(self):
        src = """type Point {
    x: int
    fn get_x(self): int {
        return self.x
    }
}"""
        result = resolve(src)
        # self should be resolved
        found_self = False
        for node, sym in result.symbols.items():
            if isinstance(node, Ident) and node.name == "self":
                found_self = True
                self.assertEqual(sym.kind, SymbolKind.PARAM)
        self.assertTrue(found_self)

    def test_self_outside_method_raises(self):
        src = """fn main(): none {
    let x = self
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("'self' is only valid inside a method", ctx.exception.message)

    def test_self_in_constructor(self):
        src = """type Point {
    x: int
    y: int
    constructor new(self, x: int, y: int): Point {
        self.x = x
        self.y = y
    }
}"""
        # Should not raise
        result = resolve(src)
        found_self = False
        for node, sym in result.symbols.items():
            if isinstance(node, Ident) and node.name == "self":
                found_self = True
        self.assertTrue(found_self)


class TestYieldCheck(unittest.TestCase):
    """RT-5-3-4: yield only valid in stream functions."""

    def test_yield_in_stream_fn(self):
        src = """fn gen(): stream<int> {
    yield 1
    yield 2
}"""
        # Should not raise
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_yield_outside_stream_raises(self):
        src = """fn main(): none {
    yield 5
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("yield is only valid inside a stream function",
                       ctx.exception.message)

    def test_yield_in_int_return_raises(self):
        src = """fn compute(): int {
    yield 42
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("yield is only valid inside a stream function",
                       ctx.exception.message)


class TestMutabilityChecks(unittest.TestCase):
    """RT-5-3-2: update and assign on immutable bindings."""

    def test_update_immutable_raises(self):
        src = """fn main(): none {
    let x = 5
    x += 1
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("cannot apply '+='", ctx.exception.message)
        self.assertIn("immutable", ctx.exception.message)

    def test_update_mutable_ok(self):
        src = """fn main(): none {
    let x: int:mut = 5
    x += 1
}"""
        # Should not raise
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_increment_immutable_raises(self):
        src = """fn main(): none {
    let x = 0
    x++
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("immutable", ctx.exception.message)

    def test_increment_mutable_ok(self):
        src = """fn main(): none {
    let x: int:mut = 0
    x++
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_assign_immutable_raises(self):
        src = """fn main(): none {
    let x = 5
    x = 10
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("cannot assign to immutable binding",
                       ctx.exception.message)

    def test_assign_mutable_ok(self):
        src = """fn main(): none {
    let x: int:mut = 5
    x = 10
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_mut_param_update_ok(self):
        src = """fn inc(x: int:mut): none {
    x += 1
}"""
        result = resolve(src)
        self.assertIsNotNone(result)


class TestMatchPatterns(unittest.TestCase):
    """RT-5-2-8: match pattern resolution."""

    def test_some_pattern_binds_var(self):
        src = """fn test(x: int?): int {
    return match x {
        some(v) : v,
        none : 0
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        # x (param ref in match subject) and v (pattern binding in arm body)
        names = [name for name, _ in idents]
        self.assertIn("x", names)
        self.assertIn("v", names)

    def test_variant_pattern_binds(self):
        src = """type Shape = | Circle(radius: float) | Rect(w: float, h: float)
fn area(s: Shape): float {
    return match s {
        Circle(r) : r,
        Rect(w, h) : w
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("s", names)
        self.assertIn("r", names)
        self.assertIn("w", names)

    def test_ok_err_patterns(self):
        src = """fn handle(r: result<int, string>): int {
    return match r {
        ok(v) : v,
        err(e) : 0
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("r", names)
        self.assertIn("v", names)

    def test_wildcard_pattern(self):
        src = """fn test(x: int): int {
    return match x {
        _ : 0
    }
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_pattern_binding_scoped_to_arm(self):
        """Variable bound in one arm is not visible in another."""
        src = """fn test(x: int?): int {
    return match x {
        some(v) : v,
        none : v
    }
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("undefined name 'v'", ctx.exception.message)


class TestTypeDeclaration(unittest.TestCase):
    """Type resolution: methods, constructors, statics."""

    def test_type_method_resolves(self):
        src = """type Counter {
    value: int
    fn get(self): int {
        return self.value
    }
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_static_member_access(self):
        src = """type Config {
    static host: string = "localhost"
}
fn main(): none {
    let h = Config.host
}"""
        result = resolve(src)
        # FieldAccess Config.host should resolve
        found_static = False
        for node, sym in result.symbols.items():
            if isinstance(node, FieldAccess):
                found_static = True
                self.assertEqual(sym.name, "host")
                self.assertEqual(sym.kind, SymbolKind.STATIC)
        self.assertTrue(found_static)

    def test_constructor_resolves(self):
        src = """type Point {
    x: int
    y: int
    constructor new(self, x: int, y: int): Point {
        self.x = x
        self.y = y
    }
}
fn main(): none {
    let p = new(1, 2)
}"""
        result = resolve(src)
        idents = find_idents(result)
        found_new = any(name == "new" for name, _ in idents)
        self.assertTrue(found_new)


class TestImports(unittest.TestCase):
    """RT-5-2-3: import resolution."""

    def _make_math_scope(self) -> ModuleScope:
        """Create a mock ModuleScope for 'math.vector'."""
        from compiler.ast_nodes import ASTNode
        dummy = ASTNode(line=0, col=0)
        scope = ModuleScope(module_path=["math", "vector"])
        scope.exports["Vec3"] = Symbol(
            "Vec3", SymbolKind.TYPE, dummy, None, False)
        scope.exports["dot"] = Symbol(
            "dot", SymbolKind.FN, dummy, None, False)
        return scope

    def test_bare_import(self):
        src = """import math.vector
fn main(): none {
    let v = vector.Vec3
}"""
        imported = {"math.vector": self._make_math_scope()}
        result = resolve(src, imported)
        idents = find_idents(result)
        # 'vector' is the namespace
        found_vector = any(name == "vector" for name, _ in idents)
        self.assertTrue(found_vector)

    def test_named_import(self):
        src = """import math.vector (Vec3)
fn main(): none {
    let v = Vec3
}"""
        imported = {"math.vector": self._make_math_scope()}
        result = resolve(src, imported)
        idents = find_idents(result)
        found_vec3 = any(
            name == "Vec3" and sym.kind == SymbolKind.IMPORT
            for name, sym in idents
        )
        self.assertTrue(found_vec3)

    def test_aliased_import(self):
        src = """import math.vector as vec
fn main(): none {
    let v = vec.Vec3
}"""
        imported = {"math.vector": self._make_math_scope()}
        result = resolve(src, imported)
        idents = find_idents(result)
        found_vec = any(name == "vec" for name, _ in idents)
        self.assertTrue(found_vec)

    def test_import_module_not_found(self):
        src = """import nonexistent.lib"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("not found", ctx.exception.message)

    def test_import_name_not_exported(self):
        src = """import math.vector (Missing)"""
        imported = {"math.vector": self._make_math_scope()}
        with self.assertRaises(ResolveError) as ctx:
            resolve(src, imported)
        self.assertIn("not exported", ctx.exception.message)


class TestModuleScope(unittest.TestCase):
    """ModuleScope and export building."""

    def test_exported_fn(self):
        src = """export fn greet(): none { }
fn private(): none { }"""
        result = resolve(src)
        exports = result.module_scope.exports
        self.assertIn("greet", exports)
        self.assertNotIn("private", exports)

    def test_exported_type(self):
        src = """export type Point {
    x: int
    y: int
}"""
        result = resolve(src)
        exports = result.module_scope.exports
        self.assertIn("Point", exports)

    def test_non_exported_not_in_module_scope(self):
        src = """fn helper(): none { }"""
        result = resolve(src)
        exports = result.module_scope.exports
        self.assertNotIn("helper", exports)


class TestExpressions(unittest.TestCase):
    """Expression resolution: binary ops, calls, etc."""

    def test_binary_op_resolves_both_sides(self):
        src = """fn add(x: int, y: int): int {
    return x + y
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = sorted([name for name, _ in idents])
        self.assertEqual(names, ["x", "y"])

    def test_if_expr_resolves_all_branches(self):
        src = """fn test(x: int): int {
    return if x > 0 { x } else { x }
}"""
        result = resolve(src)
        idents = find_idents(result)
        # x appears in condition and both branches
        self.assertTrue(all(name == "x" for name, _ in idents))
        self.assertGreaterEqual(len(idents), 3)

    def test_fstring_resolves_exprs(self):
        src = """fn greet(name: string): string {
    return f"hello {name}"
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        self.assertEqual(idents[0][0], "name")

    def test_composition_chain_resolves(self):
        src = """fn double(x: int): int {
    return x
}
fn main(): none {
    let r = 5 -> double
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("double", names)

    def test_ternary_resolves(self):
        src = """fn abs(x: int): int {
    return x > 0 ? x : x
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertTrue(all(name == "x" for name, _ in idents))

    def test_array_lit_resolves(self):
        src = """fn main(): none {
    let x = 1
    let arr = [x, x]
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 2)

    def test_copy_expr_resolves(self):
        src = """fn main(): none {
    let x = 5
    let y = @x
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        self.assertEqual(idents[0][0], "x")

    def test_null_coalesce_resolves(self):
        src = """fn test(x: int?, y: int): int {
    return x ?? y
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = sorted([name for name, _ in idents])
        self.assertEqual(names, ["x", "y"])


class TestStatements(unittest.TestCase):
    """Statement-level resolution."""

    def test_while_stmt(self):
        src = """fn main(): none {
    let x: bool:mut = true
    while x {
        x = false
    }
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_for_stmt_iterable_resolved(self):
        src = """fn main(): none {
    let items = [1, 2, 3]
    for (item in items) {
        let x = item
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("items", names)
        self.assertIn("item", names)

    def test_try_catch_binds_exception_var(self):
        src = """fn main(): none {
    try {
        let x = 5
    } catch (e: Exception) {
        let y = e
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        found_e = any(name == "e" for name, _ in idents)
        self.assertTrue(found_e)

    def test_throw_resolves_expr(self):
        src = """fn fail(e: Exception): none {
    throw e
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        self.assertEqual(idents[0][0], "e")

    def test_return_resolves_value(self):
        src = """fn identity(x: int): int {
    return x
}"""
        result = resolve(src)
        idents = find_idents(result)
        self.assertEqual(len(idents), 1)
        self.assertEqual(idents[0][0], "x")


class TestScopeClass(unittest.TestCase):
    """Unit tests for the Scope class itself."""

    def test_define_and_lookup(self):
        from compiler.ast_nodes import ASTNode
        s = Scope()
        dummy = ASTNode(line=1, col=1)
        sym = Symbol("x", SymbolKind.LOCAL, dummy, None, False)
        s.define("x", sym)
        self.assertIs(s.lookup("x"), sym)

    def test_lookup_local_only(self):
        from compiler.ast_nodes import ASTNode
        parent = Scope()
        child = Scope(parent=parent)
        dummy = ASTNode(line=1, col=1)
        sym = Symbol("x", SymbolKind.LOCAL, dummy, None, False)
        parent.define("x", sym)
        self.assertIsNone(child.lookup_local("x"))
        self.assertIs(child.lookup("x"), sym)

    def test_parent_chain(self):
        from compiler.ast_nodes import ASTNode
        grandparent = Scope()
        parent = Scope(parent=grandparent)
        child = Scope(parent=parent)
        dummy = ASTNode(line=1, col=1)
        sym = Symbol("x", SymbolKind.LOCAL, dummy, None, False)
        grandparent.define("x", sym)
        self.assertIs(child.lookup("x"), sym)

    def test_lookup_returns_none_for_missing(self):
        s = Scope()
        self.assertIsNone(s.lookup("nonexistent"))

    def test_function_boundary_flag(self):
        s = Scope(is_function_boundary=True)
        self.assertTrue(s.is_function_boundary)


class TestFunctionIsolation(unittest.TestCase):
    """RT-5-3-1: functions cannot access outer function locals."""

    def test_nested_fn_cannot_access_outer_local(self):
        """A named function cannot access locals from another function."""
        src = """fn outer(): none {
    let x = 5
}
fn inner(): none {
    let y = x
}"""
        with self.assertRaises(ResolveError) as ctx:
            resolve(src)
        self.assertIn("undefined name 'x'", ctx.exception.message)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and misc resolution scenarios."""

    def test_match_stmt_resolves(self):
        src = """fn test(x: int): none {
    match x {
        1 : 1,
        _ : 0
    }
}"""
        result = resolve(src)
        idents = find_idents(result)
        found_x = any(name == "x" for name, _ in idents)
        self.assertTrue(found_x)

    def test_index_access_resolves(self):
        src = """fn test(arr: array<int>, i: int): int {
    return arr[i]
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("arr", names)
        self.assertIn("i", names)

    def test_method_call_resolves_receiver_and_args(self):
        src = """fn test(obj: Foo, x: int): none {
    obj.bar(x)
}"""
        result = resolve(src)
        idents = find_idents(result)
        names = [name for name, _ in idents]
        self.assertIn("obj", names)
        self.assertIn("x", names)

    def test_nested_if_stmt(self):
        src = """fn test(x: int): none {
    if x > 0 {
        if x > 10 {
            let y = x
        }
    }
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_else_if_chain(self):
        src = """fn test(x: int): none {
    if x > 0 {
        let a = 1
    } else if x < 0 {
        let b = 2
    } else {
        let c = 3
    }
}"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_empty_function_body(self):
        src = """fn noop(): none { }"""
        result = resolve(src)
        self.assertIsNotNone(result)

    def test_resolved_module_has_module(self):
        src = """fn main(): none { }"""
        result = resolve(src)
        self.assertIsNotNone(result.module)
        self.assertEqual(result.module.filename, "test.reflow")


if __name__ == "__main__":
    unittest.main()
