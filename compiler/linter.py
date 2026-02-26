# compiler/linter.py — Lint engine, all rules, fix logic.
# Runs only lex + parse (no resolver/typechecker) for speed.
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from compiler.ast_nodes import (
    ASTNode, Module, FnDecl, TypeDecl, InterfaceDecl, AliasDecl,
    LetStmt, Param, ForStmt, SumVariantDecl, StaticMemberDecl,
    FieldDecl, ConstructorDecl, Block, IfStmt, WhileStmt, MatchStmt,
    TryStmt, MatchArm, IfExpr, MatchExpr, RetryBlock, CatchBlock,
    FinallyBlock, Expr, Stmt, Decl, ExprStmt,
    BindPattern, SomePattern, OkPattern, ErrPattern, VariantPattern,
)
from compiler.lexer import Token, TokenType


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class LintSeverity(Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass
class LintDiagnostic:
    rule_id: str
    message: str
    file: str
    line: int
    col: int
    severity: LintSeverity
    fixable: bool
    fix_start: int | None = None
    fix_end: int | None = None
    fix_replacement: str | None = None


@dataclass
class LintContext:
    source: str
    filename: str
    tokens: list[Token]
    module: Module | None
    source_lines: list[str]
    line_offsets: list[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASCAL_RE = re.compile(r'^[A-Z][a-zA-Z0-9]*$')
_SNAKE_RE = re.compile(r'^_?[a-z][a-z0-9_]*$')


def _is_pascal_case(name: str) -> bool:
    return bool(_PASCAL_RE.match(name))


def _is_snake_case(name: str) -> bool:
    return bool(_SNAKE_RE.match(name))


def _build_line_offsets(source: str) -> list[int]:
    """Build an array mapping line number (1-based) to byte offset of line start."""
    offsets = [0, 0]  # index 0 unused; index 1 = offset of line 1
    for i, ch in enumerate(source):
        if ch == '\n':
            offsets.append(i + 1)
    return offsets


def _offset_of(ctx: LintContext, line: int, col: int) -> int:
    """Convert 1-based line/col to source byte offset."""
    if line < len(ctx.line_offsets):
        return ctx.line_offsets[line] + (col - 1)
    return len(ctx.source)


# ---------------------------------------------------------------------------
# Rule base class
# ---------------------------------------------------------------------------

class LintRule:
    rule_id: str = ""
    name: str = ""

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Naming rules (AST-level)
# ---------------------------------------------------------------------------

class TypePascalCase(LintRule):
    rule_id = "FL-N001"
    name = "type-pascal-case"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if ctx.module is None:
            return []
        diags: list[LintDiagnostic] = []
        for decl in ctx.module.decls:
            if isinstance(decl, TypeDecl) and not _is_pascal_case(decl.name):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"type name '{decl.name}' should be PascalCase",
                    file=ctx.filename,
                    line=decl.line,
                    col=decl.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        return diags


class VariantPascalCase(LintRule):
    rule_id = "FL-N002"
    name = "variant-pascal-case"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if ctx.module is None:
            return []
        diags: list[LintDiagnostic] = []
        for decl in ctx.module.decls:
            if isinstance(decl, TypeDecl) and decl.is_sum_type:
                for variant in decl.variants:
                    if not _is_pascal_case(variant.name):
                        diags.append(LintDiagnostic(
                            rule_id=self.rule_id,
                            message=f"variant name '{variant.name}' should be PascalCase",
                            file=ctx.filename,
                            line=variant.line,
                            col=variant.col,
                            severity=LintSeverity.WARNING,
                            fixable=False,
                        ))
        return diags


class FnSnakeCase(LintRule):
    rule_id = "FL-N003"
    name = "fn-snake-case"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if ctx.module is None:
            return []
        diags: list[LintDiagnostic] = []
        self._check_decls(ctx.module.decls, ctx, diags)
        return diags

    def _check_decls(self, decls: list[Decl], ctx: LintContext,
                     diags: list[LintDiagnostic]) -> None:
        for decl in decls:
            if isinstance(decl, FnDecl):
                if not _is_snake_case(decl.name):
                    diags.append(LintDiagnostic(
                        rule_id=self.rule_id,
                        message=f"function name '{decl.name}' should be snake_case",
                        file=ctx.filename,
                        line=decl.line,
                        col=decl.col,
                        severity=LintSeverity.WARNING,
                        fixable=False,
                    ))
            if isinstance(decl, TypeDecl):
                for method in decl.methods:
                    if not _is_snake_case(method.name):
                        diags.append(LintDiagnostic(
                            rule_id=self.rule_id,
                            message=f"function name '{method.name}' should be snake_case",
                            file=ctx.filename,
                            line=method.line,
                            col=method.col,
                            severity=LintSeverity.WARNING,
                            fixable=False,
                        ))


class VarSnakeCase(LintRule):
    rule_id = "FL-N004"
    name = "var-snake-case"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if ctx.module is None:
            return []
        diags: list[LintDiagnostic] = []
        self._check_decls(ctx.module.decls, ctx, diags)
        return diags

    def _check_decls(self, decls: list, ctx: LintContext,
                     diags: list[LintDiagnostic]) -> None:
        for decl in decls:
            if isinstance(decl, FnDecl):
                self._check_params(decl.params, ctx, diags)
                if isinstance(decl.body, Block):
                    self._check_block(decl.body, ctx, diags)
            elif isinstance(decl, TypeDecl):
                for method in decl.methods:
                    self._check_params(method.params, ctx, diags)
                    if isinstance(method.body, Block):
                        self._check_block(method.body, ctx, diags)
                for ctor in decl.constructors:
                    self._check_params(ctor.params, ctx, diags)
                    self._check_block(ctor.body, ctx, diags)

    def _check_params(self, params: list[Param], ctx: LintContext,
                      diags: list[LintDiagnostic]) -> None:
        for param in params:
            if param.name == "self":
                continue
            if not _is_snake_case(param.name):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"parameter name '{param.name}' should be snake_case",
                    file=ctx.filename,
                    line=param.line,
                    col=param.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))

    def _check_block(self, block: Block, ctx: LintContext,
                     diags: list[LintDiagnostic]) -> None:
        for stmt in block.stmts:
            self._check_stmt(stmt, ctx, diags)

    def _check_stmt(self, stmt: Stmt, ctx: LintContext,
                    diags: list[LintDiagnostic]) -> None:
        if isinstance(stmt, LetStmt):
            if not _is_snake_case(stmt.name):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"variable name '{stmt.name}' should be snake_case",
                    file=ctx.filename,
                    line=stmt.line,
                    col=stmt.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        elif isinstance(stmt, ForStmt):
            if not _is_snake_case(stmt.var):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"variable name '{stmt.var}' should be snake_case",
                    file=ctx.filename,
                    line=stmt.line,
                    col=stmt.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
            self._check_block(stmt.body, ctx, diags)
        elif isinstance(stmt, IfStmt):
            self._check_block(stmt.then_branch, ctx, diags)
            if isinstance(stmt.else_branch, Block):
                self._check_block(stmt.else_branch, ctx, diags)
            elif isinstance(stmt.else_branch, IfStmt):
                self._check_stmt(stmt.else_branch, ctx, diags)
        elif isinstance(stmt, WhileStmt):
            self._check_block(stmt.body, ctx, diags)
        elif isinstance(stmt, MatchStmt):
            for arm in stmt.arms:
                self._check_match_arm(arm, ctx, diags)
        elif isinstance(stmt, TryStmt):
            self._check_block(stmt.body, ctx, diags)
            for retry in stmt.retry_blocks:
                self._check_block(retry.body, ctx, diags)
            for catch in stmt.catch_blocks:
                self._check_block(catch.body, ctx, diags)
        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr, ctx, diags)

    def _check_expr(self, expr: Expr, ctx: LintContext,
                    diags: list[LintDiagnostic]) -> None:
        if isinstance(expr, IfExpr):
            self._check_block(expr.then_branch, ctx, diags)
            if isinstance(expr.else_branch, Block):
                self._check_block(expr.else_branch, ctx, diags)
            elif isinstance(expr.else_branch, IfExpr):
                self._check_expr(expr.else_branch, ctx, diags)
        elif isinstance(expr, MatchExpr):
            for arm in expr.arms:
                self._check_match_arm(arm, ctx, diags)

    def _check_match_arm(self, arm: MatchArm, ctx: LintContext,
                         diags: list[LintDiagnostic]) -> None:
        self._check_pattern(arm.pattern, ctx, diags)
        if isinstance(arm.body, Block):
            self._check_block(arm.body, ctx, diags)

    def _check_pattern(self, pattern, ctx: LintContext,
                       diags: list[LintDiagnostic]) -> None:
        name: str | None = None
        names: list[tuple[str, int, int]] = []

        if isinstance(pattern, BindPattern):
            names.append((pattern.name, pattern.line, pattern.col))
        elif isinstance(pattern, SomePattern):
            names.append((pattern.inner_var, pattern.line, pattern.col))
        elif isinstance(pattern, OkPattern):
            names.append((pattern.inner_var, pattern.line, pattern.col))
        elif isinstance(pattern, ErrPattern):
            names.append((pattern.inner_var, pattern.line, pattern.col))
        elif isinstance(pattern, VariantPattern):
            for binding in pattern.bindings:
                names.append((binding, pattern.line, pattern.col))

        for name, line, col in names:
            if name == "_":
                continue
            if not _is_snake_case(name):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"variable name '{name}' should be snake_case",
                    file=ctx.filename,
                    line=line,
                    col=col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))


class ModuleSnakeCase(LintRule):
    rule_id = "FL-N005"
    name = "module-snake-case"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if ctx.module is None or not ctx.module.path:
            return []
        diags: list[LintDiagnostic] = []
        for segment in ctx.module.path:
            if not _is_snake_case(segment):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"module segment '{segment}' should be snake_case",
                    file=ctx.filename,
                    line=ctx.module.line,
                    col=ctx.module.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        return diags


class AliasPascalCase(LintRule):
    rule_id = "FL-N006"
    name = "alias-pascal-case"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if ctx.module is None:
            return []
        diags: list[LintDiagnostic] = []
        for decl in ctx.module.decls:
            if isinstance(decl, AliasDecl) and not _is_pascal_case(decl.name):
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"alias name '{decl.name}' should be PascalCase",
                    file=ctx.filename,
                    line=decl.line,
                    col=decl.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        return diags


# ---------------------------------------------------------------------------
# Comment style rules (token-level)
# ---------------------------------------------------------------------------

class CommentSpace(LintRule):
    rule_id = "FL-C001"
    name = "comment-space"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        diags: list[LintDiagnostic] = []
        for tok in ctx.tokens:
            if tok.type != TokenType.COMMENT:
                continue
            # Token value starts with '//'
            text = tok.value
            if len(text) <= 2:
                # Just '//' alone — no content, no check needed
                continue
            third = text[2]
            # Exempt decorator comments: //=== //--- ///
            if third in ('=', '-', '/'):
                continue
            if third != ' ':
                offset = _offset_of(ctx, tok.line, tok.col + 2)
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message="comment should have space after '//'",
                    file=ctx.filename,
                    line=tok.line,
                    col=tok.col + 2,
                    severity=LintSeverity.WARNING,
                    fixable=True,
                    fix_start=offset,
                    fix_end=offset,
                    fix_replacement=" ",
                ))
        return diags


class NoSemicolonComments(LintRule):
    rule_id = "FL-C002"
    name = "no-semicolon-comments"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        diags: list[LintDiagnostic] = []
        for i, raw_line in enumerate(ctx.source_lines):
            stripped = raw_line.lstrip()
            if stripped.startswith(";"):
                line_num = i + 1
                col = len(raw_line) - len(stripped) + 1
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message="semicolon comment ';' — use '//' for Flow comments",
                    file=ctx.filename,
                    line=line_num,
                    col=col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        return diags


# ---------------------------------------------------------------------------
# Structural rules (source-text + AST)
# ---------------------------------------------------------------------------

class IndentFourSpaces(LintRule):
    rule_id = "FL-S002"
    name = "indent-four-spaces"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        diags: list[LintDiagnostic] = []
        for i, raw_line in enumerate(ctx.source_lines):
            if not raw_line or raw_line.isspace():
                continue
            # Count leading whitespace
            leading = raw_line[:len(raw_line) - len(raw_line.lstrip())]
            if '\t' in leading:
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message="indentation uses tabs; use 4 spaces instead",
                    file=ctx.filename,
                    line=i + 1,
                    col=1,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
            elif len(leading) % 4 != 0:
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"indentation is {len(leading)} spaces; should be a multiple of 4",
                    file=ctx.filename,
                    line=i + 1,
                    col=1,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        return diags


class NoTrailingWhitespace(LintRule):
    rule_id = "FL-S003"
    name = "no-trailing-whitespace"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        diags: list[LintDiagnostic] = []
        for i, raw_line in enumerate(ctx.source_lines):
            stripped = raw_line.rstrip()
            if len(stripped) < len(raw_line):
                line_num = i + 1
                col = len(stripped) + 1
                offset = ctx.line_offsets[line_num] + len(stripped)
                end_offset = ctx.line_offsets[line_num] + len(raw_line)
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message="trailing whitespace",
                    file=ctx.filename,
                    line=line_num,
                    col=col,
                    severity=LintSeverity.WARNING,
                    fixable=True,
                    fix_start=offset,
                    fix_end=end_offset,
                    fix_replacement="",
                ))
        return diags


class FileEndsNewline(LintRule):
    rule_id = "FL-S004"
    name = "file-ends-newline"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        if not ctx.source:
            return []
        diags: list[LintDiagnostic] = []
        if not ctx.source.endswith('\n'):
            diags.append(LintDiagnostic(
                rule_id=self.rule_id,
                message="file should end with a newline",
                file=ctx.filename,
                line=len(ctx.source_lines),
                col=len(ctx.source_lines[-1]) + 1 if ctx.source_lines else 1,
                severity=LintSeverity.WARNING,
                fixable=True,
                fix_start=len(ctx.source),
                fix_end=len(ctx.source),
                fix_replacement="\n",
            ))
        elif ctx.source.endswith('\n\n'):
            # Find where the extra newlines start
            end = len(ctx.source)
            start = end - 1
            while start > 0 and ctx.source[start - 1] == '\n':
                start -= 1
            # Keep one newline, remove the rest
            diags.append(LintDiagnostic(
                rule_id=self.rule_id,
                message="file has multiple trailing newlines; should have exactly one",
                file=ctx.filename,
                line=len(ctx.source_lines),
                col=1,
                severity=LintSeverity.WARNING,
                fixable=True,
                fix_start=start + 1,
                fix_end=end,
                fix_replacement="",
            ))
        return diags


class NoSpaceAroundColon(LintRule):
    rule_id = "FL-S005"
    name = "no-space-around-colon"

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        diags: list[LintDiagnostic] = []
        for tok in ctx.tokens:
            if tok.type != TokenType.COLON:
                continue
            colon_offset = _offset_of(ctx, tok.line, tok.col)

            # Check for space before colon
            if colon_offset > 0 and ctx.source[colon_offset - 1] in (' ', '\t'):
                ws_start = colon_offset - 1
                while ws_start > 0 and ctx.source[ws_start - 1] in (' ', '\t'):
                    ws_start -= 1
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message="no space before ':'",
                    file=ctx.filename,
                    line=tok.line,
                    col=tok.col - (colon_offset - ws_start),
                    severity=LintSeverity.WARNING,
                    fixable=True,
                    fix_start=ws_start,
                    fix_end=colon_offset,
                    fix_replacement="",
                ))

            # Check for space after colon
            after = colon_offset + 1
            if after < len(ctx.source) and ctx.source[after] in (' ', '\t'):
                ws_end = after + 1
                while ws_end < len(ctx.source) and ctx.source[ws_end] in (' ', '\t'):
                    ws_end += 1
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message="no space after ':'",
                    file=ctx.filename,
                    line=tok.line,
                    col=tok.col + 1,
                    severity=LintSeverity.WARNING,
                    fixable=True,
                    fix_start=after,
                    fix_end=ws_end,
                    fix_replacement="",
                ))
        return diags


class BraceSameLine(LintRule):
    rule_id = "FL-S001"
    name = "brace-same-line"

    # Keywords whose opening brace should be on the same line.
    _KEYWORDS = frozenset({
        TokenType.FN, TokenType.IF, TokenType.WHILE, TokenType.FOR,
        TokenType.TYPE, TokenType.MATCH,
    })

    def check(self, ctx: LintContext) -> list[LintDiagnostic]:
        diags: list[LintDiagnostic] = []
        # Scan tokens for keyword ... { patterns where { is on a different line.
        tokens = [t for t in ctx.tokens
                  if t.type not in (TokenType.COMMENT, TokenType.NEWLINE, TokenType.EOF)]

        for i, tok in enumerate(tokens):
            if tok.type not in self._KEYWORDS:
                continue
            # For FN: check if it's an expression-form fn (has = before { or no { at all)
            # Find the next LBRACE at the same or deeper nesting
            brace = self._find_opening_brace(tokens, i)
            if brace is None:
                continue
            # Check for expression-form functions: fn f(): int = expr
            if tok.type == TokenType.FN and self._is_expression_fn(tokens, i, brace):
                continue
            if brace.line != tok.line:
                diags.append(LintDiagnostic(
                    rule_id=self.rule_id,
                    message=f"opening '{{' should be on the same line as '{tok.value}'",
                    file=ctx.filename,
                    line=brace.line,
                    col=brace.col,
                    severity=LintSeverity.WARNING,
                    fixable=False,
                ))
        return diags

    def _find_opening_brace(self, tokens: list[Token], start: int) -> Token | None:
        """Find the next LBRACE that belongs to this construct."""
        depth = 0
        for j in range(start + 1, len(tokens)):
            tok = tokens[j]
            if tok.type == TokenType.LBRACE and depth == 0:
                return tok
            if tok.type == TokenType.LPAREN:
                depth += 1
            elif tok.type == TokenType.RPAREN:
                depth -= 1
            # Stop at another keyword or construct boundary
            if tok.type in self._KEYWORDS and depth == 0 and j > start + 1:
                return None
            # Stop at RBRACE (end of enclosing block)
            if tok.type == TokenType.RBRACE and depth <= 0:
                return None
        return None

    def _is_expression_fn(self, tokens: list[Token], fn_idx: int,
                          brace: Token) -> bool:
        """Check if there's an ASSIGN token between fn and the brace."""
        for j in range(fn_idx + 1, len(tokens)):
            if tokens[j] is brace:
                break
            if tokens[j].type == TokenType.ASSIGN:
                return True
        return False


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

ALL_RULES: list[LintRule] = [
    TypePascalCase(),
    VariantPascalCase(),
    FnSnakeCase(),
    VarSnakeCase(),
    ModuleSnakeCase(),
    AliasPascalCase(),
    CommentSpace(),
    NoSemicolonComments(),
    NoSpaceAroundColon(),
    BraceSameLine(),
    IndentFourSpaces(),
    NoTrailingWhitespace(),
    FileEndsNewline(),
]

_RULE_BY_ID: dict[str, LintRule] = {r.rule_id: r for r in ALL_RULES}
_RULE_BY_NAME: dict[str, LintRule] = {r.name: r for r in ALL_RULES}


def get_rules(
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[LintRule]:
    """Return the list of rules to run, filtered by include/exclude.

    Rules can be specified by ID (FL-N001) or name (type-pascal-case).
    """
    if include is not None:
        rules = []
        for spec in include:
            rule = _RULE_BY_ID.get(spec) or _RULE_BY_NAME.get(spec)
            if rule is not None:
                rules.append(rule)
        return rules

    rules = list(ALL_RULES)
    if exclude is not None:
        excluded_ids = set()
        for spec in exclude:
            rule = _RULE_BY_ID.get(spec) or _RULE_BY_NAME.get(spec)
            if rule is not None:
                excluded_ids.add(rule.rule_id)
        rules = [r for r in rules if r.rule_id not in excluded_ids]
    return rules


# ---------------------------------------------------------------------------
# Lint orchestrator
# ---------------------------------------------------------------------------

def build_context(source: str, filename: str, tokens: list[Token],
                  module: Module | None) -> LintContext:
    """Build a LintContext from the given inputs."""
    # Split source into lines without the line ending
    source_lines = source.split('\n')
    # Remove the trailing empty string from split if source ends with \n
    if source_lines and source_lines[-1] == '' and source.endswith('\n'):
        source_lines = source_lines[:-1]
    line_offsets = _build_line_offsets(source)
    return LintContext(
        source=source,
        filename=filename,
        tokens=tokens,
        module=module,
        source_lines=source_lines,
        line_offsets=line_offsets,
    )


def lint(ctx: LintContext,
         rules: list[LintRule] | None = None) -> list[LintDiagnostic]:
    """Run all (or specified) lint rules and return diagnostics sorted by location."""
    if rules is None:
        rules = ALL_RULES
    diags: list[LintDiagnostic] = []
    for rule in rules:
        diags.extend(rule.check(ctx))
    diags.sort(key=lambda d: (d.line, d.col))
    return diags


# ---------------------------------------------------------------------------
# Fix engine
# ---------------------------------------------------------------------------

def apply_fixes(source: str, diags: list[LintDiagnostic]) -> str:
    """Apply fixable diagnostics to source and return the new source.

    Only diagnostics with fixable=True and valid fix_start/fix_end/fix_replacement
    are applied. Fixes are applied end-to-start to preserve earlier offsets.
    """
    fixable = [
        d for d in diags
        if d.fixable and d.fix_start is not None
        and d.fix_end is not None and d.fix_replacement is not None
    ]
    # Sort by fix_start descending so we apply from end to start.
    fixable.sort(key=lambda d: d.fix_start, reverse=True)  # type: ignore[arg-type]

    result = source
    for d in fixable:
        result = result[:d.fix_start] + d.fix_replacement + result[d.fix_end:]  # type: ignore[index]
    return result


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_diagnostic(d: LintDiagnostic) -> str:
    """Format a diagnostic for terminal output."""
    fixable_tag = " [fixable]" if d.fixable else ""
    return (
        f"{d.file}:{d.line}:{d.col}: "
        f"{d.severity.value}[{d.rule_id}] "
        f"{d.message}{fixable_tag}"
    )
