"""Unit tests for compiler/linter.py — Flow linter rules and fix engine."""
from __future__ import annotations

import unittest

from compiler.lexer import Lexer, Token, TokenType
from compiler.parser import Parser
from compiler.linter import (
    LintContext, LintDiagnostic, LintSeverity,
    build_context, lint, apply_fixes, get_rules, format_diagnostic,
    TypePascalCase, VariantPascalCase, FnSnakeCase, VarSnakeCase,
    ModuleSnakeCase, AliasPascalCase, CommentSpace, NoCComments,
    BraceSameLine, IndentFourSpaces, NoTrailingWhitespace, FileEndsNewline,
    ALL_RULES,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_ctx(source: str, filename: str = "test.flow") -> LintContext:
    """Lex+parse source and build a LintContext."""
    tokens = Lexer(source, filename).tokenize()
    try:
        module = Parser(tokens, filename).parse()
    except Exception:
        module = None
    return build_context(source, filename, tokens, module)


def _diag_ids(diags: list[LintDiagnostic]) -> list[str]:
    """Extract just the rule IDs from diagnostics."""
    return [d.rule_id for d in diags]


# ---------------------------------------------------------------------------
# FL-N001: type-pascal-case
# ---------------------------------------------------------------------------

class TestTypePascalCase(unittest.TestCase):
    def test_pascal_case_passes(self):
        ctx = _make_ctx("type Vec3 {}\n")
        diags = TypePascalCase().check(ctx)
        self.assertEqual(diags, [])

    def test_lowercase_type_warns(self):
        ctx = _make_ctx("type my_type {}\n")
        diags = TypePascalCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-N001")
        self.assertIn("my_type", diags[0].message)

    def test_single_letter_upper_passes(self):
        ctx = _make_ctx("type T {}\n")
        diags = TypePascalCase().check(ctx)
        self.assertEqual(diags, [])


# ---------------------------------------------------------------------------
# FL-N002: variant-pascal-case
# ---------------------------------------------------------------------------

class TestVariantPascalCase(unittest.TestCase):
    def test_pascal_variants_pass(self):
        src = "type Color =\n    | Red\n    | Blue\n"
        ctx = _make_ctx(src)
        diags = VariantPascalCase().check(ctx)
        self.assertEqual(diags, [])

    def test_lowercase_variant_warns(self):
        src = "type Color =\n    | red\n"
        ctx = _make_ctx(src)
        diags = VariantPascalCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-N002")
        self.assertIn("red", diags[0].message)


# ---------------------------------------------------------------------------
# FL-N003: fn-snake-case
# ---------------------------------------------------------------------------

class TestFnSnakeCase(unittest.TestCase):
    def test_snake_case_passes(self):
        ctx = _make_ctx("fn my_func(): int {\n    return 1\n}\n")
        diags = FnSnakeCase().check(ctx)
        self.assertEqual(diags, [])

    def test_camel_case_warns(self):
        ctx = _make_ctx("fn myFunc(): int {\n    return 1\n}\n")
        diags = FnSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-N003")
        self.assertIn("myFunc", diags[0].message)

    def test_method_camel_case_warns(self):
        src = "type Foo {\n    fn doThing(self): int {\n        return 1\n    }\n}\n"
        ctx = _make_ctx(src)
        diags = FnSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("doThing", diags[0].message)


# ---------------------------------------------------------------------------
# FL-N004: var-snake-case
# ---------------------------------------------------------------------------

class TestVarSnakeCase(unittest.TestCase):
    def test_snake_case_var_passes(self):
        ctx = _make_ctx("fn main(): int {\n    let my_var = 1\n    return my_var\n}\n")
        diags = VarSnakeCase().check(ctx)
        self.assertEqual(diags, [])

    def test_camel_case_var_warns(self):
        ctx = _make_ctx("fn main(): int {\n    let myVar = 1\n    return myVar\n}\n")
        diags = VarSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-N004")
        self.assertIn("myVar", diags[0].message)

    def test_self_param_exempt(self):
        src = "type Foo {\n    fn bar(self): int {\n        return 1\n    }\n}\n"
        ctx = _make_ctx(src)
        diags = VarSnakeCase().check(ctx)
        self.assertEqual(diags, [])

    def test_camel_case_param_warns(self):
        ctx = _make_ctx("fn foo(myParam: int): int {\n    return myParam\n}\n")
        diags = VarSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("myParam", diags[0].message)

    def test_for_var_camel_warns(self):
        ctx = _make_ctx("fn main(): int {\n    for (myItem in [1, 2, 3]) {\n    }\n    return 0\n}\n")
        diags = VarSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("myItem", diags[0].message)


# ---------------------------------------------------------------------------
# FL-N005: module-snake-case
# ---------------------------------------------------------------------------

class TestModuleSnakeCase(unittest.TestCase):
    def test_snake_case_module_passes(self):
        ctx = _make_ctx("module my_app\nfn main(): int {\n    return 0\n}\n")
        diags = ModuleSnakeCase().check(ctx)
        self.assertEqual(diags, [])

    def test_camel_case_module_warns(self):
        ctx = _make_ctx("module myApp\nfn main(): int {\n    return 0\n}\n")
        diags = ModuleSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("myApp", diags[0].message)

    def test_dotted_module_checks_each_segment(self):
        ctx = _make_ctx("module my_app.badPart\nfn main(): int {\n    return 0\n}\n")
        diags = ModuleSnakeCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("badPart", diags[0].message)


# ---------------------------------------------------------------------------
# FL-N006: alias-pascal-case
# ---------------------------------------------------------------------------

class TestAliasPascalCase(unittest.TestCase):
    def test_pascal_alias_passes(self):
        ctx = _make_ctx("alias MyType: int\n")
        diags = AliasPascalCase().check(ctx)
        self.assertEqual(diags, [])

    def test_snake_alias_warns(self):
        ctx = _make_ctx("alias my_type: int\n")
        diags = AliasPascalCase().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("my_type", diags[0].message)


# ---------------------------------------------------------------------------
# FL-C001: comment-space
# ---------------------------------------------------------------------------

class TestCommentSpace(unittest.TestCase):
    def test_proper_comment_passes(self):
        ctx = _make_ctx("; this is a comment\n")
        diags = CommentSpace().check(ctx)
        self.assertEqual(diags, [])

    def test_no_space_warns(self):
        ctx = _make_ctx(";this is a comment\n")
        diags = CommentSpace().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-C001")
        self.assertTrue(diags[0].fixable)

    def test_decorator_exempt(self):
        # ;=== and ;--- are decorator comments, exempt from FL-C001
        ctx = _make_ctx(";=== section\n;--- divider\n;;; triple\n")
        diags = CommentSpace().check(ctx)
        self.assertEqual(diags, [])

    def test_bare_semicolon_passes(self):
        ctx = _make_ctx(";\n")
        diags = CommentSpace().check(ctx)
        self.assertEqual(diags, [])

    def test_fix_inserts_space(self):
        source = ";comment\n"
        ctx = _make_ctx(source)
        diags = CommentSpace().check(ctx)
        self.assertEqual(len(diags), 1)
        fixed = apply_fixes(source, diags)
        self.assertEqual(fixed, "; comment\n")


# ---------------------------------------------------------------------------
# FL-C002: no-c-comments
# ---------------------------------------------------------------------------

class TestNoCComments(unittest.TestCase):
    def test_no_c_comment_passes(self):
        ctx = _make_ctx("; normal comment\n")
        diags = NoCComments().check(ctx)
        self.assertEqual(diags, [])

    def test_c_comment_warns(self):
        ctx = _make_ctx("// c-style comment\n")
        diags = NoCComments().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-C002")
        self.assertTrue(diags[0].fixable)

    def test_double_slash_in_code_not_flagged(self):
        # // at the start of a line is flagged, but not inside expressions
        # (the check only flags line-leading //)
        ctx = _make_ctx("fn main(): int {\n    return 0\n}\n")
        diags = NoCComments().check(ctx)
        self.assertEqual(diags, [])

    def test_indented_c_comment_warns(self):
        ctx = _make_ctx("    // indented c-style\n")
        diags = NoCComments().check(ctx)
        self.assertEqual(len(diags), 1)

    def test_fix_replaces_with_semicolon(self):
        source = "// c-style comment\n"
        ctx = _make_ctx(source)
        diags = NoCComments().check(ctx)
        fixed = apply_fixes(source, diags)
        self.assertEqual(fixed, "; c-style comment\n")


# ---------------------------------------------------------------------------
# FL-S001: brace-same-line
# ---------------------------------------------------------------------------

class TestBraceSameLine(unittest.TestCase):
    def test_same_line_passes(self):
        ctx = _make_ctx("fn main(): int {\n    return 0\n}\n")
        diags = BraceSameLine().check(ctx)
        self.assertEqual(diags, [])

    def test_next_line_warns(self):
        ctx = _make_ctx("fn main(): int\n{\n    return 0\n}\n")
        diags = BraceSameLine().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-S001")
        self.assertFalse(diags[0].fixable)

    def test_expression_fn_no_brace_ok(self):
        ctx = _make_ctx("fn double(x: int): int = x * 2\n")
        diags = BraceSameLine().check(ctx)
        self.assertEqual(diags, [])


# ---------------------------------------------------------------------------
# FL-S002: indent-four-spaces
# ---------------------------------------------------------------------------

class TestIndentFourSpaces(unittest.TestCase):
    def test_four_spaces_passes(self):
        ctx = _make_ctx("fn main(): int {\n    return 0\n}\n")
        diags = IndentFourSpaces().check(ctx)
        self.assertEqual(diags, [])

    def test_two_spaces_warns(self):
        ctx = _make_ctx("fn main(): int {\n  return 0\n}\n")
        diags = IndentFourSpaces().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-S002")
        self.assertIn("2 spaces", diags[0].message)

    def test_tab_warns(self):
        ctx = _make_ctx("fn main(): int {\n\treturn 0\n}\n")
        diags = IndentFourSpaces().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("tabs", diags[0].message)

    def test_eight_spaces_passes(self):
        ctx = _make_ctx("fn main(): int {\n        return 0\n}\n")
        diags = IndentFourSpaces().check(ctx)
        self.assertEqual(diags, [])

    def test_blank_lines_ignored(self):
        ctx = _make_ctx("fn main(): int {\n\n    return 0\n}\n")
        diags = IndentFourSpaces().check(ctx)
        self.assertEqual(diags, [])


# ---------------------------------------------------------------------------
# FL-S003: no-trailing-whitespace
# ---------------------------------------------------------------------------

class TestNoTrailingWhitespace(unittest.TestCase):
    def test_clean_passes(self):
        ctx = _make_ctx("fn main(): int {\n    return 0\n}\n")
        diags = NoTrailingWhitespace().check(ctx)
        self.assertEqual(diags, [])

    def test_trailing_spaces_warns(self):
        ctx = _make_ctx("fn main(): int {  \n    return 0\n}\n")
        diags = NoTrailingWhitespace().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-S003")
        self.assertTrue(diags[0].fixable)

    def test_fix_removes_trailing_whitespace(self):
        source = "hello   \nworld\n"
        ctx = _make_ctx(source)
        diags = NoTrailingWhitespace().check(ctx)
        fixed = apply_fixes(source, diags)
        self.assertEqual(fixed, "hello\nworld\n")


# ---------------------------------------------------------------------------
# FL-S004: file-ends-newline
# ---------------------------------------------------------------------------

class TestFileEndsNewline(unittest.TestCase):
    def test_single_newline_passes(self):
        ctx = _make_ctx("fn main(): int {\n    return 0\n}\n")
        diags = FileEndsNewline().check(ctx)
        self.assertEqual(diags, [])

    def test_no_newline_warns(self):
        source = "fn main(): int {\n    return 0\n}"
        ctx = _make_ctx(source)
        diags = FileEndsNewline().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].rule_id, "FL-S004")
        self.assertTrue(diags[0].fixable)

    def test_fix_adds_newline(self):
        source = "hello"
        ctx = _make_ctx(source)
        diags = FileEndsNewline().check(ctx)
        fixed = apply_fixes(source, diags)
        self.assertEqual(fixed, "hello\n")

    def test_double_newline_warns(self):
        source = "hello\n\n"
        ctx = _make_ctx(source)
        diags = FileEndsNewline().check(ctx)
        self.assertEqual(len(diags), 1)
        self.assertIn("multiple", diags[0].message)

    def test_fix_removes_extra_newlines(self):
        source = "hello\n\n\n"
        ctx = _make_ctx(source)
        diags = FileEndsNewline().check(ctx)
        fixed = apply_fixes(source, diags)
        self.assertEqual(fixed, "hello\n")

    def test_empty_source_passes(self):
        source = ""
        ctx = build_context(source, "test.flow", [], None)
        diags = FileEndsNewline().check(ctx)
        self.assertEqual(diags, [])


# ---------------------------------------------------------------------------
# Fix engine
# ---------------------------------------------------------------------------

class TestFixEngine(unittest.TestCase):
    def test_multiple_fixes_applied_correctly(self):
        source = ";comment1\n;comment2\n"
        ctx = _make_ctx(source)
        diags = CommentSpace().check(ctx)
        self.assertEqual(len(diags), 2)
        fixed = apply_fixes(source, diags)
        self.assertEqual(fixed, "; comment1\n; comment2\n")

    def test_no_fixable_diags_returns_same(self):
        source = "hello\n"
        diags = [LintDiagnostic(
            rule_id="FL-TEST", message="not fixable", file="t.flow",
            line=1, col=1, severity=LintSeverity.WARNING, fixable=False,
        )]
        self.assertEqual(apply_fixes(source, diags), source)

    def test_mixed_fixable_and_non_fixable(self):
        source = ";comment  \n"
        ctx = _make_ctx(source)
        comment_diags = CommentSpace().check(ctx)
        trailing_diags = NoTrailingWhitespace().check(ctx)
        all_diags = comment_diags + trailing_diags
        fixed = apply_fixes(source, all_diags)
        self.assertEqual(fixed, "; comment\n")


# ---------------------------------------------------------------------------
# Rule filtering
# ---------------------------------------------------------------------------

class TestGetRules(unittest.TestCase):
    def test_default_returns_all(self):
        rules = get_rules()
        self.assertEqual(len(rules), len(ALL_RULES))

    def test_include_by_id(self):
        rules = get_rules(include=["FL-N001"])
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "FL-N001")

    def test_include_by_name(self):
        rules = get_rules(include=["comment-space"])
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_id, "FL-C001")

    def test_exclude_by_id(self):
        rules = get_rules(exclude=["FL-N001"])
        ids = [r.rule_id for r in rules]
        self.assertNotIn("FL-N001", ids)
        self.assertGreater(len(rules), 0)

    def test_exclude_by_name(self):
        rules = get_rules(exclude=["type-pascal-case"])
        ids = [r.rule_id for r in rules]
        self.assertNotIn("FL-N001", ids)

    def test_include_unknown_returns_empty(self):
        rules = get_rules(include=["FL-ZZZZ"])
        self.assertEqual(rules, [])


# ---------------------------------------------------------------------------
# Format diagnostic
# ---------------------------------------------------------------------------

class TestFormatDiagnostic(unittest.TestCase):
    def test_basic_format(self):
        d = LintDiagnostic(
            rule_id="FL-N001",
            message="type name 'foo' should be PascalCase",
            file="test.flow",
            line=1,
            col=6,
            severity=LintSeverity.WARNING,
            fixable=False,
        )
        result = format_diagnostic(d)
        self.assertEqual(
            result,
            "test.flow:1:6: warning[FL-N001] type name 'foo' should be PascalCase"
        )

    def test_fixable_tag(self):
        d = LintDiagnostic(
            rule_id="FL-C001",
            message="comment should have space after ';'",
            file="test.flow",
            line=1,
            col=2,
            severity=LintSeverity.WARNING,
            fixable=True,
        )
        result = format_diagnostic(d)
        self.assertIn("[fixable]", result)


# ---------------------------------------------------------------------------
# Lint orchestrator
# ---------------------------------------------------------------------------

class TestLintOrchestrator(unittest.TestCase):
    def test_clean_file_returns_no_diags(self):
        source = "fn main(): int {\n    return 0\n}\n"
        ctx = _make_ctx(source)
        diags = lint(ctx)
        self.assertEqual(diags, [])

    def test_multiple_issues_sorted_by_location(self):
        source = ";comment\nfn myFunc(): int {\n    return 0\n}\n"
        ctx = _make_ctx(source)
        diags = lint(ctx)
        # Should have at least FL-C001 and FL-N003
        ids = _diag_ids(diags)
        self.assertIn("FL-C001", ids)
        self.assertIn("FL-N003", ids)
        # Sorted by line
        lines = [d.line for d in diags]
        self.assertEqual(lines, sorted(lines))

    def test_lint_with_specific_rules(self):
        source = ";comment\nfn myFunc(): int {\n    return 0\n}\n"
        ctx = _make_ctx(source)
        rules = get_rules(include=["FL-C001"])
        diags = lint(ctx, rules=rules)
        ids = _diag_ids(diags)
        self.assertEqual(ids, ["FL-C001"])


if __name__ == "__main__":
    unittest.main()
