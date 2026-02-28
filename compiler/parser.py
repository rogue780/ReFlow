# compiler/parser.py — list[Token] → Module (AST). No type information.

from __future__ import annotations

from compiler.errors import ParseError
from compiler.lexer import Token, TokenType
from compiler.ast_nodes import (
    # Base
    ASTNode,
    TypeExpr,
    Expr,
    Stmt,
    Decl,
    Pattern,
    # Type expressions
    NamedType,
    GenericType,
    OptionType,
    FnType,
    TupleType,
    MutType,
    ImutType,
    SizedType,
    SumTypeExpr,
    SumVariantExpr,
    # Expressions
    IntLit,
    FloatLit,
    BoolLit,
    StringLit,
    FStringExpr,
    CharLit,
    NoneLit,
    Ident,
    NamedArg,
    SpreadExpr,
    BinOp,
    UnaryOp,
    Call,
    MethodCall,
    FieldAccess,
    IndexAccess,
    Lambda,
    TupleExpr,
    ArrayLit,
    RecordLit,
    TypeLit,
    IfExpr,
    MatchExpr,
    CompositionChain,
    ChainElement,
    FanOut,
    TernaryExpr,
    CopyExpr,
    RefExpr,
    SomeExpr,
    OkExpr,
    ErrExpr,
    CoerceExpr,
    CastExpr,
    PropagateExpr,
    NullCoalesce,
    TypeofExpr,
    CoroutineStart,
    PipelineStage,
    CoroutinePipeline,
    # Statements
    LetStmt,
    AssignStmt,
    UpdateStmt,
    ReturnStmt,
    YieldStmt,
    ThrowStmt,
    BreakStmt,
    ContinueStmt,
    ExprStmt,
    IfStmt,
    WhileStmt,
    ForStmt,
    MatchStmt,
    TryStmt,
    Block,
    MatchArm,
    RetryBlock,
    CatchBlock,
    FinallyBlock,
    # Patterns
    WildcardPattern,
    LiteralPattern,
    BindPattern,
    SomePattern,
    NonePattern,
    OkPattern,
    ErrPattern,
    VariantPattern,
    TuplePattern,
    # Declarations
    ModuleDecl,
    ImportDecl,
    FnDecl,
    Param,
    ExternLibDecl,
    ExternTypeDecl,
    ExternFnDecl,
    TypeDecl,
    FieldDecl,
    ConstructorDecl,
    StaticMemberDecl,
    InterfaceDecl,
    AliasDecl,
    SumVariantDecl,
    EnumVariantDecl,
    EnumDecl,
    TypeParam,
    # Top-level
    Module,
)


# ---------------------------------------------------------------------------
# Operator precedence levels for the Pratt parser (lowest to highest)
# ---------------------------------------------------------------------------

_PREC_NONE = 0
_PREC_COMPOSITION = 1   # ->
_PREC_TERNARY = 2       # ? :
_PREC_NULL_COALESCE = 3  # ??
_PREC_OR = 4             # ||
_PREC_AND = 5            # &&
_PREC_EQUALITY = 6       # == != ===
_PREC_COMPARISON = 7     # < > <= >=
_PREC_ADD = 8            # + -
_PREC_MUL = 9            # * / </ %
_PREC_POWER = 10         # **
_PREC_UNARY = 11         # - ! @
_PREC_POSTFIX = 12       # ? .field (args) [idx]
_PREC_PRIMARY = 13       # literals, idents, grouping

# Map token types to their infix (binary) precedence.
_INFIX_PRECEDENCE: dict[TokenType, int] = {
    TokenType.ARROW: _PREC_COMPOSITION,
    TokenType.DOUBLE_QUESTION: _PREC_NULL_COALESCE,
    TokenType.OR: _PREC_OR,
    TokenType.AND: _PREC_AND,
    TokenType.DOUBLE_EQ: _PREC_EQUALITY,
    TokenType.NOT_EQ: _PREC_EQUALITY,
    TokenType.TRIPLE_EQ: _PREC_EQUALITY,
    TokenType.LT: _PREC_COMPARISON,
    TokenType.GT: _PREC_COMPARISON,
    TokenType.LT_EQ: _PREC_COMPARISON,
    TokenType.GT_EQ: _PREC_COMPARISON,
    TokenType.PLUS: _PREC_ADD,
    TokenType.MINUS: _PREC_ADD,
    TokenType.STAR: _PREC_MUL,
    TokenType.SLASH: _PREC_MUL,
    TokenType.FLOOR_DIV: _PREC_MUL,
    TokenType.PERCENT: _PREC_MUL,
    TokenType.DOUBLE_STAR: _PREC_POWER,
    # Postfix operators handled separately
}

# Map binary operator token types to their string representation.
_BINOP_STRINGS: dict[TokenType, str] = {
    TokenType.DOUBLE_QUESTION: "??",
    TokenType.OR: "||",
    TokenType.AND: "&&",
    TokenType.DOUBLE_EQ: "==",
    TokenType.NOT_EQ: "!=",
    TokenType.TRIPLE_EQ: "===",
    TokenType.LT: "<",
    TokenType.GT: ">",
    TokenType.LT_EQ: "<=",
    TokenType.GT_EQ: ">=",
    TokenType.PLUS: "+",
    TokenType.MINUS: "-",
    TokenType.STAR: "*",
    TokenType.SLASH: "/",
    TokenType.FLOOR_DIV: "</",
    TokenType.PERCENT: "%",
    TokenType.DOUBLE_STAR: "**",
}

# Tokens that mark the start of a statement (used for error recovery).
_RECOVERY_TOKENS = frozenset({
    TokenType.LET,
    TokenType.FN,
    TokenType.IF,
    TokenType.WHILE,
    TokenType.FOR,
    TokenType.MATCH,
    TokenType.RETURN,
    TokenType.YIELD,
    TokenType.THROW,
    TokenType.BREAK,
    TokenType.TRY,
    TokenType.TYPE,
    TokenType.INTERFACE,
    TokenType.ALIAS,
    TokenType.IMPORT,
    TokenType.EXPORT,
    TokenType.RBRACE,
    TokenType.EOF,
})

# Tokens that are top-level declaration keywords and cannot appear as
# statements inside a block. Used by parse_block() to break out when
# error recovery synchronizes to one of these — prevents infinite loops
# when a block is missing its closing '}'.
_TOPLEVEL_ONLY_TOKENS = frozenset({
    TokenType.FN,
    TokenType.TYPE,
    TokenType.INTERFACE,
    TokenType.ALIAS,
    TokenType.IMPORT,
    TokenType.EXPORT,
    TokenType.MODULE,
})


class Parser:
    """Recursive-descent parser with Pratt expression parsing for Flow."""

    def __init__(self, tokens: list[Token], filename: str) -> None:
        self._tokens = tokens
        self._filename = filename
        self._pos = 0
        self._errors: list[ParseError] = []

    # ------------------------------------------------------------------
    # Helpers (RT-4-1-1)
    # ------------------------------------------------------------------

    def _error(self, message: str, token: Token | None = None) -> ParseError:
        """Create a ParseError at the given token (or current token)."""
        tok = token if token is not None else self.peek()
        return ParseError(
            message=message,
            file=self._filename,
            line=tok.line,
            col=tok.col,
        )

    def peek(self) -> Token:
        """Look at the current token without consuming it."""
        self.skip_comments()
        if self._pos >= len(self._tokens):
            return self._tokens[-1]  # EOF
        return self._tokens[self._pos]

    def peek2(self) -> Token:
        """Look two tokens ahead (skipping comments and newlines)."""
        saved = self._pos
        self.skip_comments()
        self._pos += 1
        self.skip_comments()
        tok = self._tokens[self._pos] if self._pos < len(self._tokens) else self._tokens[-1]
        self._pos = saved
        return tok

    def _peek_raw(self) -> Token:
        """Look at the current token without skipping comments/newlines."""
        if self._pos >= len(self._tokens):
            return self._tokens[-1]
        return self._tokens[self._pos]

    def advance(self) -> Token:
        """Consume and return the current token."""
        self.skip_comments()
        if self._pos >= len(self._tokens):
            return self._tokens[-1]
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def expect(self, ttype: TokenType) -> Token:
        """Consume the current token if it matches ttype, otherwise raise ParseError."""
        tok = self.peek()
        if tok.type != ttype:
            raise self._error(
                f"expected '{ttype.name}' but found '{tok.value}' ({tok.type.name})"
            )
        return self.advance()

    def check(self, ttype: TokenType) -> bool:
        """Return True if the current token is of the given type."""
        return self.peek().type == ttype

    def match_token(self, *types: TokenType) -> Token | None:
        """If the current token matches any of the given types, consume and return it."""
        tok = self.peek()
        if tok.type in types:
            return self.advance()
        return None

    def skip_comments(self) -> None:
        """Skip COMMENT and NEWLINE tokens."""
        while self._pos < len(self._tokens):
            t = self._tokens[self._pos]
            if t.type in (TokenType.COMMENT, TokenType.NEWLINE):
                self._pos += 1
            else:
                break

    def skip_newlines(self) -> None:
        """Skip only NEWLINE tokens (not comments — comments are skipped by skip_comments)."""
        while self._pos < len(self._tokens):
            t = self._tokens[self._pos]
            if t.type == TokenType.NEWLINE:
                self._pos += 1
            else:
                break

    def at_end(self) -> bool:
        """Return True if we have reached EOF."""
        return self.peek().type == TokenType.EOF

    def _synchronize(self) -> None:
        """Skip tokens until we reach a recovery point (for error recovery)."""
        while not self.at_end():
            tok = self.peek()
            if tok.type in _RECOVERY_TOKENS:
                return
            self.advance()

    # ------------------------------------------------------------------
    # Top-level entry point (RT-4-1-2)
    # ------------------------------------------------------------------

    def parse(self) -> Module:
        """Parse the entire token stream into a Module AST node."""
        start = self.peek()

        # Optional module declaration
        path: list[str] = []
        if self.check(TokenType.MODULE):
            mod_decl = self.parse_module_decl()
            path = mod_decl.path

        # Import declarations
        imports: list[ImportDecl] = []
        while self.check(TokenType.IMPORT):
            imports.append(self.parse_import_decl())

        # Top-level declarations
        decls: list[Decl] = []
        while not self.at_end():
            pos_before = self._pos
            try:
                decl = self._parse_top_level_decl()
                if decl is not None:
                    decls.append(decl)
            except ParseError as e:
                self._errors.append(e)
                self._synchronize()
                # Guarantee forward progress to prevent infinite loops
                if self._pos <= pos_before:
                    self.advance()

        if self._errors:
            raise self._errors[0]

        return Module(
            line=start.line,
            col=start.col,
            path=path,
            imports=imports,
            decls=decls,
            filename=self._filename,
        )

    def _parse_top_level_decl(self) -> Decl | None:
        """Parse a single top-level declaration."""
        tok = self.peek()

        is_export = False
        if tok.type == TokenType.EXPORT:
            is_export = True
            self.advance()
            tok = self.peek()

        match tok.type:
            case TokenType.FN:
                return self.parse_fn_decl(is_export=is_export)
            case TokenType.PURE:
                raise self._error(
                    "use 'fn:pure' instead of 'pure fn'"
                )
            case TokenType.TYPE:
                return self.parse_type_decl(is_export=is_export)
            case TokenType.INTERFACE:
                return self.parse_interface_decl(is_export=is_export)
            case TokenType.ALIAS:
                return self.parse_alias_decl(is_export=is_export)
            case TokenType.EXTERN:
                return self._parse_extern_decl(is_export=is_export)
            case TokenType.ENUM:
                return self.parse_enum_decl(is_export=is_export)
            case TokenType.IMPORT:
                # Late imports after exports — collect them
                imp = self.parse_import_decl()
                # We allow import declarations interspersed at top level
                # but they are still ImportDecl, which is a Decl
                return imp
            case _:
                raise self._error(
                    f"expected top-level declaration but found '{tok.value}' ({tok.type.name})"
                )

    # ------------------------------------------------------------------
    # Declarations (Story 4-2)
    # ------------------------------------------------------------------

    def parse_module_decl(self) -> ModuleDecl:
        """Parse: module a.b.c"""
        tok = self.expect(TokenType.MODULE)
        path = self._parse_dotted_name()
        return ModuleDecl(line=tok.line, col=tok.col, path=path)

    def _parse_dotted_name(self) -> list[str]:
        """Parse a dot-separated identifier path: a.b.c"""
        parts: list[str] = []
        name_tok = self.expect(TokenType.IDENT)
        parts.append(name_tok.value)
        while self.check(TokenType.DOT):
            self.advance()  # consume '.'
            name_tok = self.expect(TokenType.IDENT)
            parts.append(name_tok.value)
        return parts

    def parse_import_decl(self) -> ImportDecl:
        """Parse: import a.b.c, import a.b.c (X, Y), import a.b.c as alias"""
        tok = self.expect(TokenType.IMPORT)
        path = self._parse_dotted_name()

        names: list[str] | None = None
        alias: str | None = None

        if self.check(TokenType.LPAREN):
            # import a.b.c (Name1, Name2)
            self.advance()
            names = []
            if not self.check(TokenType.RPAREN):
                name_tok = self.expect(TokenType.IDENT)
                names.append(name_tok.value)
                while self.check(TokenType.COMMA):
                    self.advance()
                    name_tok = self.expect(TokenType.IDENT)
                    names.append(name_tok.value)
            self.expect(TokenType.RPAREN)
        elif self.check(TokenType.AS):
            # import a.b.c as alias
            self.advance()
            alias_tok = self.expect(TokenType.IDENT)
            alias = alias_tok.value

        return ImportDecl(
            line=tok.line,
            col=tok.col,
            path=path,
            names=names,
            alias=alias,
        )

    def _parse_fn_modifiers(self) -> tuple[bool, bool]:
        """Parse colon-chain modifiers after 'fn': fn:pure, fn:static, fn:pure:static.

        Returns (is_pure, is_static). Enforces order: :pure must come before :static.
        Raises ParseError for wrong order, duplicates, or unknown modifiers.
        """
        is_pure = False
        is_static = False

        while self.check(TokenType.COLON):
            # Peek ahead to see if next token is a modifier keyword
            next_tok = self.peek2()
            if next_tok.type not in (TokenType.PURE, TokenType.STATIC):
                # Not a modifier colon — stop (it's the return type colon, etc.)
                break

            self.advance()  # consume ':'
            mod_tok = self.advance()  # consume modifier keyword

            if mod_tok.type == TokenType.PURE:
                if is_pure:
                    raise self._error("duplicate modifier ':pure'", mod_tok)
                if is_static:
                    raise self._error(
                        "wrong modifier order: use 'fn:pure:static' not 'fn:static:pure'",
                        mod_tok,
                    )
                is_pure = True
            elif mod_tok.type == TokenType.STATIC:
                if is_static:
                    raise self._error("duplicate modifier ':static'", mod_tok)
                is_static = True

        return is_pure, is_static

    def _parse_extern_decl(self, is_export: bool = False) -> Decl:
        """Parse extern declarations: extern lib/type/fn."""
        tok = self.expect(TokenType.EXTERN)
        next_tok = self.peek()

        # extern lib "name"
        if next_tok.type == TokenType.IDENT and next_tok.value == "lib":
            if is_export:
                raise self._error("'export extern lib' is not allowed", tok)
            self.advance()  # consume 'lib'
            lib_tok = self.expect(TokenType.STRING_LIT)
            return ExternLibDecl(
                line=tok.line, col=tok.col,
                lib_name=lib_tok.value,
            )

        # extern type NAME
        if next_tok.type == TokenType.TYPE:
            self.advance()  # consume 'type'
            name_tok = self.expect(TokenType.IDENT)
            return ExternTypeDecl(
                line=tok.line, col=tok.col,
                name=name_tok.value,
                is_export=is_export,
            )

        # extern fn NAME(params):RetType
        if next_tok.type == TokenType.FN:
            return self._parse_extern_fn_decl(tok, is_export)

        raise self._error(
            f"expected 'lib', 'type', or 'fn' after 'extern' but found '{next_tok.value}'",
            next_tok,
        )

    def _parse_extern_fn_decl(self, extern_tok: Token, is_export: bool) -> ExternFnDecl:
        """Parse: extern fn name(params):RetType
                  extern fn "c_name" flow_name(params):RetType"""
        self.expect(TokenType.FN)

        # Optional alias: extern fn "c_name" flow_name(...)
        c_name: str | None = None
        if self.check(TokenType.STRING_LIT):
            c_name_tok = self.advance()
            c_name = c_name_tok.value

        name_tok = self.expect(TokenType.IDENT)

        # Optional generic type parameters
        type_params: list[TypeParam] = []
        if self.check(TokenType.LT):
            type_params = self._parse_type_params()

        self.expect(TokenType.LPAREN)
        params = self._parse_param_list()
        self.expect(TokenType.RPAREN)

        # Reject variadic params on extern fn
        for p in params:
            if p.is_variadic:
                raise self._error(
                    "variadic parameters are not allowed on extern fn declarations",
                    extern_tok)

        return_type: TypeExpr | None = None
        if self.check(TokenType.COLON):
            self.advance()
            return_type = self.parse_type_expr()

        return ExternFnDecl(
            line=extern_tok.line, col=extern_tok.col,
            name=name_tok.value,
            type_params=type_params,
            params=params,
            return_type=return_type,
            is_export=is_export,
            c_name=c_name,
        )

    def parse_enum_decl(self, is_export: bool = False) -> EnumDecl:
        """Parse: enum Name { Variant1 = value \\n Variant2 \\n ... }"""
        tok = self.expect(TokenType.ENUM)
        name_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.LBRACE)
        self.skip_newlines()

        variants: list[EnumVariantDecl] = []
        while not self.check(TokenType.RBRACE):
            v_tok = self.expect(TokenType.IDENT)
            value: int | None = None
            if self.check(TokenType.ASSIGN):
                self.advance()  # consume '='
                # Parse optional negative sign + integer literal
                negative = False
                if self.check(TokenType.MINUS):
                    negative = True
                    self.advance()
                val_tok = self.expect(TokenType.INT_LIT)
                value = int(val_tok.value)
                if negative:
                    value = -value
            variants.append(EnumVariantDecl(
                line=v_tok.line, col=v_tok.col,
                name=v_tok.value,
                value=value,
            ))
            self.skip_newlines()

        if not variants:
            raise self._error("enum must have at least one variant", tok)

        self.expect(TokenType.RBRACE)
        return EnumDecl(
            line=tok.line, col=tok.col,
            name=name_tok.value,
            variants=variants,
            is_export=is_export,
        )

    def parse_fn_decl(
        self,
        is_export: bool = False,
        allow_no_body: bool = False,
    ) -> FnDecl:
        """Parse a function declaration.

        Supports:
        - Full body: fn:pure name<T>(params): RetType { body }
        - Expression body: fn name(params): RetType = expr
        - Interface signature: fn name(params): RetType (no body, when allow_no_body=True)
        - Colon-chain modifiers: fn:pure, fn:static, fn:pure:static
        - Optional function-level finally block after body
        """
        tok = self.expect(TokenType.FN)
        is_pure, is_static = self._parse_fn_modifiers()
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value

        # Optional generic type parameters
        type_params: list[TypeParam] = []
        if self.check(TokenType.LT):
            type_params = self._parse_type_params()

        # Parameter list
        self.expect(TokenType.LPAREN)
        params = self._parse_param_list()
        self.expect(TokenType.RPAREN)

        # Optional return type
        return_type: TypeExpr | None = None
        if self.check(TokenType.COLON):
            self.advance()
            return_type = self.parse_type_expr()

        # Body: block, expression, or none (interface signature)
        body: Block | Expr | None = None
        finally_block: Block | None = None

        if self.check(TokenType.LBRACE):
            body = self.parse_block()
            # Optional function-level finally
            if self.check(TokenType.FINALLY):
                finally_block = self._parse_finally_block_simple()
        elif self.check(TokenType.ASSIGN):
            self.advance()
            body = self.parse_expr()
        elif allow_no_body:
            body = None
        else:
            # For top-level declarations, no body is an error
            # unless we're in an interface context
            body = None

        return FnDecl(
            line=tok.line,
            col=tok.col,
            name=name,
            type_params=type_params,
            params=params,
            return_type=return_type,
            body=body,
            is_pure=is_pure,
            is_export=is_export,
            is_static=is_static,
            finally_block=finally_block,
        )

    def _parse_type_param(self) -> TypeParam:
        """Parse a single type parameter: IDENT [ fulfills BOUND ]"""
        tok = self.expect(TokenType.IDENT)
        bounds: list[TypeExpr] = []
        if self.check(TokenType.FULFILLS):
            self.advance()
            if self.check(TokenType.LPAREN):
                # Multiple bounds: T fulfills (A, B, C)
                self.advance()
                bounds.append(self.parse_type_expr())
                while self.check(TokenType.COMMA):
                    self.advance()
                    bounds.append(self.parse_type_expr())
                self.expect(TokenType.RPAREN)
            else:
                # Single bound: T fulfills A
                bounds.append(self.parse_type_expr())
        return TypeParam(
            name=tok.value,
            bounds=bounds,
            line=tok.line,
            col=tok.col,
        )

    def _parse_type_params(self) -> list[TypeParam]:
        """Parse generic type parameter list: <T, U fulfills V, W>"""
        self.expect(TokenType.LT)
        params: list[TypeParam] = []
        if not self.check(TokenType.GT):
            params.append(self._parse_type_param())
            while self.check(TokenType.COMMA):
                self.advance()
                params.append(self._parse_type_param())
        self.expect(TokenType.GT)
        return params

    def _parse_param_list(self) -> list[Param]:
        """Parse a comma-separated parameter list (inside parens)."""
        params: list[Param] = []
        if self.check(TokenType.RPAREN):
            return params

        seen_default = False
        seen_variadic = False

        # Check for variadic prefix (..) on first param
        if self.check(TokenType.SPREAD):
            spread_tok = self.advance()
            p = self._parse_param()
            if p.default is not None:
                raise self._error(
                    "variadic parameter cannot have a default value",
                    spread_tok)
            p = Param(line=p.line, col=p.col, name=p.name,
                      type_ann=p.type_ann, default=None, is_variadic=True)
            seen_variadic = True
            params.append(p)
        else:
            params.append(self._parse_param())
            if params[-1].default is not None:
                seen_default = True

        while self.check(TokenType.COMMA):
            self.advance()
            if self.check(TokenType.RPAREN):
                break  # trailing comma
            if seen_variadic:
                raise self._error(
                    "variadic parameter must be the last parameter",
                    self._tokens[self._pos] if self._pos < len(self._tokens) else None)
            # Check for variadic prefix on subsequent param
            if self.check(TokenType.SPREAD):
                spread_tok = self.advance()
                p = self._parse_param()
                if p.default is not None:
                    raise self._error(
                        "variadic parameter cannot have a default value",
                        spread_tok)
                p = Param(line=p.line, col=p.col, name=p.name,
                          type_ann=p.type_ann, default=None, is_variadic=True)
                seen_variadic = True
                params.append(p)
            else:
                p = self._parse_param()
                if seen_default and p.default is None:
                    raise self._error(
                        f"parameter '{p.name}' must have a default value "
                        f"(all parameters after a defaulted parameter must also have defaults)",
                        self._tokens[self._pos - 1] if self._pos > 0 else None,
                    )
                if p.default is not None:
                    seen_default = True
                params.append(p)
        return params

    def _parse_param(self) -> Param:
        """Parse a single parameter: name: Type, name: Type = default, or self"""
        tok = self.peek()
        if tok.type == TokenType.SELF:
            self.advance()
            # 'self' is a special param — type is inferred by the resolver
            return Param(
                line=tok.line,
                col=tok.col,
                name="self",
                type_ann=NamedType(line=tok.line, col=tok.col, name="self", module_path=[]),
            )

        name_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.COLON)
        type_ann = self.parse_type_expr()

        # Optional default value: = expr
        default: Expr | None = None
        if self.check(TokenType.ASSIGN):
            self.advance()
            default = self.parse_expr()

        return Param(
            line=name_tok.line,
            col=name_tok.col,
            name=name_tok.value,
            type_ann=type_ann,
            default=default,
        )

    def parse_type_decl(self, is_export: bool = False) -> TypeDecl:
        """Parse a type declaration: struct or sum type."""
        tok = self.expect(TokenType.TYPE)
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value

        # Optional generic type params
        type_params: list[TypeParam] = []
        if self.check(TokenType.LT):
            type_params = self._parse_type_params()

        # Check for 'fulfills'
        interfaces: list[TypeExpr] = []
        if self.check(TokenType.FULFILLS):
            self.advance()
            interfaces.append(self.parse_type_expr())
            while self.check(TokenType.COMMA):
                self.advance()
                interfaces.append(self.parse_type_expr())

        # Sum type: type Name = | Variant1(...) | Variant2
        if self.check(TokenType.ASSIGN):
            return self._parse_sum_type(tok, name, type_params, interfaces, is_export)

        # Struct type: type Name { ... }
        return self._parse_struct_type(tok, name, type_params, interfaces, is_export)

    def _parse_sum_type(
        self,
        tok: Token,
        name: str,
        type_params: list[TypeParam],
        interfaces: list[TypeExpr],
        is_export: bool,
    ) -> TypeDecl:
        """Parse a sum type: type Name = | Variant1(fields) | Variant2"""
        self.expect(TokenType.ASSIGN)

        variants: list[SumVariantDecl] = []
        # Expect at least one | before the first variant
        self.expect(TokenType.PIPE)
        variants.append(self._parse_sum_variant())

        while self.check(TokenType.PIPE):
            self.advance()
            variants.append(self._parse_sum_variant())

        return TypeDecl(
            line=tok.line,
            col=tok.col,
            name=name,
            type_params=type_params,
            fields=[],
            methods=[],
            constructors=[],
            static_members=[],
            interfaces=interfaces,
            is_export=is_export,
            is_sum_type=True,
            variants=variants,
        )

    def _parse_sum_variant(self) -> SumVariantDecl:
        """Parse a single sum type variant: VariantName or VariantName(field: Type, ...)"""
        name_tok = self.expect(TokenType.IDENT)
        fields: list[tuple[str, TypeExpr]] | None = None

        if self.check(TokenType.LPAREN):
            self.advance()
            fields = []
            if not self.check(TokenType.RPAREN):
                field_name_tok = self.expect(TokenType.IDENT)
                self.expect(TokenType.COLON)
                field_type = self.parse_type_expr()
                fields.append((field_name_tok.value, field_type))

                while self.check(TokenType.COMMA):
                    self.advance()
                    if self.check(TokenType.RPAREN):
                        break
                    field_name_tok = self.expect(TokenType.IDENT)
                    self.expect(TokenType.COLON)
                    field_type = self.parse_type_expr()
                    fields.append((field_name_tok.value, field_type))
            self.expect(TokenType.RPAREN)

        return SumVariantDecl(
            line=name_tok.line,
            col=name_tok.col,
            name=name_tok.value,
            fields=fields,
        )

    def _parse_struct_type(
        self,
        tok: Token,
        name: str,
        type_params: list[TypeParam],
        interfaces: list[TypeExpr],
        is_export: bool,
    ) -> TypeDecl:
        """Parse a struct type: type Name { fields, methods, constructors, statics }"""
        self.expect(TokenType.LBRACE)

        fields: list[FieldDecl] = []
        methods: list[FnDecl] = []
        constructors: list[ConstructorDecl] = []
        static_members: list[StaticMemberDecl] = []

        while not self.check(TokenType.RBRACE) and not self.at_end():
            member_tok = self.peek()

            if member_tok.type == TokenType.STATIC:
                self.advance()
                # static data member or old-style 'static fn' (now an error)
                if self.check(TokenType.FN):
                    raise self._error(
                        "use 'fn:static' instead of 'static fn'"
                    )
                elif self.check(TokenType.PURE):
                    raise self._error(
                        "use 'fn:pure:static' instead of 'static pure fn'"
                    )
                else:
                    static_member = self._parse_static_member_body(member_tok)
                    static_members.append(static_member)
                # skip optional comma after static member
                self.match_token(TokenType.COMMA)
            elif member_tok.type == TokenType.FN:
                fn_decl = self.parse_fn_decl()
                methods.append(fn_decl)
                self.match_token(TokenType.COMMA)
            elif member_tok.type == TokenType.PURE:
                raise self._error(
                    "use 'fn:pure' instead of 'pure fn'"
                )
            elif member_tok.type == TokenType.CONSTRUCTOR:
                constructor = self.parse_constructor_decl()
                constructors.append(constructor)
                self.match_token(TokenType.COMMA)
            elif member_tok.type == TokenType.IDENT:
                # Field: name: Type
                field = self._parse_field_decl()
                fields.append(field)
                self.match_token(TokenType.COMMA)
            else:
                raise self._error(
                    f"expected field, method, constructor, or static member "
                    f"but found '{member_tok.value}' ({member_tok.type.name})"
                )

        self.expect(TokenType.RBRACE)

        return TypeDecl(
            line=tok.line,
            col=tok.col,
            name=name,
            type_params=type_params,
            fields=fields,
            methods=methods,
            constructors=constructors,
            static_members=static_members,
            interfaces=interfaces,
            is_export=is_export,
            is_sum_type=False,
            variants=[],
        )

    def _parse_field_decl(self) -> FieldDecl:
        """Parse a struct field: name: Type or name: Type:mut"""
        name_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.COLON)
        type_ann = self.parse_type_expr()

        # Determine mutability from type expression
        is_mut = isinstance(type_ann, MutType)

        return FieldDecl(
            line=name_tok.line,
            col=name_tok.col,
            name=name_tok.value,
            type_ann=type_ann,
            is_mut=is_mut,
        )

    def parse_constructor_decl(self) -> ConstructorDecl:
        """Parse: constructor name(params): RetType { body }"""
        tok = self.expect(TokenType.CONSTRUCTOR)
        name_tok = self.expect(TokenType.IDENT)

        self.expect(TokenType.LPAREN)
        params = self._parse_param_list()
        self.expect(TokenType.RPAREN)

        self.expect(TokenType.COLON)
        return_type = self.parse_type_expr()

        body = self.parse_block()

        return ConstructorDecl(
            line=tok.line,
            col=tok.col,
            name=name_tok.value,
            params=params,
            return_type=return_type,
            body=body,
        )

    def _parse_static_member_body(self, static_tok: Token) -> StaticMemberDecl:
        """Parse the body of a static member: name: Type = value or name: Type:mut = value"""
        name_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.COLON)
        type_ann = self.parse_type_expr()

        is_mut = isinstance(type_ann, MutType)

        value: Expr | None = None
        if self.check(TokenType.ASSIGN):
            self.advance()
            value = self.parse_expr()

        return StaticMemberDecl(
            line=static_tok.line,
            col=static_tok.col,
            name=name_tok.value,
            type_ann=type_ann,
            value=value,
            is_mut=is_mut,
        )

    def parse_interface_decl(self, is_export: bool = False) -> InterfaceDecl:
        """Parse: interface Name<T> { method sigs, optional constructor sig }"""
        tok = self.expect(TokenType.INTERFACE)
        name_tok = self.expect(TokenType.IDENT)

        type_params: list[TypeParam] = []
        if self.check(TokenType.LT):
            type_params = self._parse_type_params()

        self.expect(TokenType.LBRACE)

        methods: list[FnDecl] = []
        constructor_sig: ConstructorDecl | None = None

        while not self.check(TokenType.RBRACE) and not self.at_end():
            member_tok = self.peek()

            if member_tok.type == TokenType.FN:
                fn_decl = self.parse_fn_decl(allow_no_body=True)
                methods.append(fn_decl)
                self.match_token(TokenType.COMMA)
            elif member_tok.type == TokenType.PURE:
                raise self._error(
                    "use 'fn:pure' instead of 'pure fn'"
                )
            elif member_tok.type == TokenType.CONSTRUCTOR:
                constructor_sig = self._parse_constructor_sig()
                self.match_token(TokenType.COMMA)
            else:
                raise self._error(
                    f"expected method signature or constructor in interface "
                    f"but found '{member_tok.value}' ({member_tok.type.name})"
                )

        self.expect(TokenType.RBRACE)

        return InterfaceDecl(
            line=tok.line,
            col=tok.col,
            name=name_tok.value,
            type_params=type_params,
            methods=methods,
            constructor_sig=constructor_sig,
            is_export=is_export,
        )

    def _parse_constructor_sig(self) -> ConstructorDecl:
        """Parse a constructor signature (no body) for interfaces."""
        tok = self.expect(TokenType.CONSTRUCTOR)
        name_tok = self.expect(TokenType.IDENT)

        self.expect(TokenType.LPAREN)
        params = self._parse_param_list()
        self.expect(TokenType.RPAREN)

        self.expect(TokenType.COLON)
        return_type = self.parse_type_expr()

        return ConstructorDecl(
            line=tok.line,
            col=tok.col,
            name=name_tok.value,
            params=params,
            return_type=return_type,
            body=Block(line=tok.line, col=tok.col, stmts=[], finally_block=None),
        )

    def parse_alias_decl(self, is_export: bool = False) -> AliasDecl:
        """Parse: alias Name<T>: UnderlyingType"""
        tok = self.expect(TokenType.ALIAS)
        name_tok = self.expect(TokenType.IDENT)

        type_params: list[TypeParam] = []
        if self.check(TokenType.LT):
            type_params = self._parse_type_params()

        self.expect(TokenType.COLON)
        target = self.parse_type_expr()

        return AliasDecl(
            line=tok.line,
            col=tok.col,
            name=name_tok.value,
            type_params=type_params,
            target=target,
            is_export=is_export,
        )

    # ------------------------------------------------------------------
    # Type expressions
    # ------------------------------------------------------------------

    def parse_type_expr(self) -> TypeExpr:
        """Parse a type expression, handling ? and :mut/:imut modifiers.

        Grammar: base_type ('?' )? (':mut' | ':imut')?
        Also handles fn(...): T type syntax and tuple types (A, B, C).
        """
        base = self._parse_base_type()

        # Optional [N] capacity hint (e.g., stream<int>[64])
        if self.check(TokenType.LBRACKET):
            bracket_tok = self.advance()  # consume '['
            cap_expr = self.parse_expr()
            self.expect(TokenType.RBRACKET)
            base = SizedType(line=bracket_tok.line, col=bracket_tok.col,
                             inner=base, capacity=cap_expr)

        # Optional ? for option type
        if self.check(TokenType.QUESTION):
            q_tok = self.advance()
            base = OptionType(line=q_tok.line, col=q_tok.col, inner=base)

        # Optional :mut or :imut modifier
        if self.check(TokenType.COLON):
            # Peek ahead to see if it's :mut or :imut
            saved = self._pos
            self.skip_comments()
            colon_pos = self._pos
            self._pos += 1  # skip colon
            self.skip_comments()
            next_tok = self._tokens[self._pos] if self._pos < len(self._tokens) else self._tokens[-1]
            self._pos = saved

            if next_tok.type == TokenType.MUT:
                self.advance()  # consume ':'
                mut_tok = self.advance()  # consume 'mut'
                base = MutType(line=mut_tok.line, col=mut_tok.col, inner=base)
            elif next_tok.type == TokenType.IMUT:
                self.advance()  # consume ':'
                imut_tok = self.advance()  # consume 'imut'
                base = ImutType(line=imut_tok.line, col=imut_tok.col, inner=base)

        return base

    def _parse_base_type(self) -> TypeExpr:
        """Parse a base type expression (before ? and :mut/:imut)."""
        tok = self.peek()

        # fn type: fn(T, U): V
        if tok.type == TokenType.FN:
            return self._parse_fn_type()

        # Tuple type: (A, B, C)
        if tok.type == TokenType.LPAREN:
            return self._parse_tuple_type()

        # Keywords that double as type names
        if tok.type == TokenType.NONE:
            self.advance()
            return NamedType(line=tok.line, col=tok.col, name="none", module_path=[])

        if tok.type == TokenType.RECORD:
            self.advance()
            return NamedType(line=tok.line, col=tok.col, name="record", module_path=[])

        # Named type with optional module path and generics
        if tok.type == TokenType.IDENT or tok.type == TokenType.SELF:
            return self._parse_named_or_generic_type()

        raise self._error(f"expected type expression but found '{tok.value}' ({tok.type.name})")

    def _parse_fn_type(self) -> FnType:
        """Parse: fn(T, U): V"""
        tok = self.expect(TokenType.FN)
        self.expect(TokenType.LPAREN)

        params: list[TypeExpr] = []
        if not self.check(TokenType.RPAREN):
            params.append(self.parse_type_expr())
            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.RPAREN):
                    break
                params.append(self.parse_type_expr())
        self.expect(TokenType.RPAREN)

        self.expect(TokenType.COLON)
        ret = self.parse_type_expr()

        return FnType(line=tok.line, col=tok.col, params=params, ret=ret)

    def _parse_tuple_type(self) -> TupleType:
        """Parse: (A, B, C)"""
        tok = self.expect(TokenType.LPAREN)
        elements: list[TypeExpr] = []
        if not self.check(TokenType.RPAREN):
            elements.append(self.parse_type_expr())
            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.RPAREN):
                    break
                elements.append(self.parse_type_expr())
        self.expect(TokenType.RPAREN)
        return TupleType(line=tok.line, col=tok.col, elements=elements)

    def _parse_named_or_generic_type(self) -> TypeExpr:
        """Parse a named type with optional module path and generic args.

        Examples: int, string, math.vector.Vec3, array<int>, result<T, E>
        """
        first_tok = self.advance()  # IDENT or SELF
        module_path: list[str] = []
        name = first_tok.value

        # Collect dotted path: a.b.c.Name
        while self.check(TokenType.DOT):
            self.advance()
            next_tok = self.expect(TokenType.IDENT)
            module_path.append(name)
            name = next_tok.value

        base: TypeExpr = NamedType(
            line=first_tok.line,
            col=first_tok.col,
            name=name,
            module_path=module_path,
        )

        # Generic args: Name<T, U>
        if self.check(TokenType.LT):
            args = self._parse_type_args()
            base = GenericType(
                line=first_tok.line,
                col=first_tok.col,
                base=base,
                args=args,
            )

        return base

    def _parse_type_args(self) -> list[TypeExpr]:
        """Parse generic type arguments: <T, U, V>"""
        self.expect(TokenType.LT)
        args: list[TypeExpr] = []
        if not self.check(TokenType.GT):
            args.append(self.parse_type_expr())
            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.GT):
                    break
                args.append(self.parse_type_expr())
        self.expect(TokenType.GT)
        return args

    # ------------------------------------------------------------------
    # Statements (Story 4-3)
    # ------------------------------------------------------------------

    def parse_block(self) -> Block:
        """Parse a block: { stmt* }"""
        tok = self.expect(TokenType.LBRACE)
        stmts: list[Stmt] = []

        while not self.check(TokenType.RBRACE) and not self.at_end():
            # If we see a top-level declaration keyword, this block is
            # missing its closing '}'. Break out to let the caller handle it.
            if self.peek().type in _TOPLEVEL_ONLY_TOKENS:
                break
            pos_before = self._pos
            try:
                stmt = self.parse_stmt()
                if stmt is not None:
                    stmts.append(stmt)
            except ParseError as e:
                self._errors.append(e)
                self._synchronize()
                # Guarantee forward progress to prevent infinite loops
                if self._pos <= pos_before:
                    self.advance()

        self.expect(TokenType.RBRACE)

        return Block(
            line=tok.line,
            col=tok.col,
            stmts=stmts,
            finally_block=None,
        )

    def _parse_finally_block_simple(self) -> Block:
        """Parse a simple finally block: finally { ... }"""
        self.expect(TokenType.FINALLY)
        return self.parse_block()

    def parse_stmt(self) -> Stmt:
        """Dispatch to the appropriate statement parser."""
        tok = self.peek()

        match tok.type:
            case TokenType.LET:
                return self.parse_let_stmt()
            case TokenType.IF:
                return self.parse_if_stmt()
            case TokenType.WHILE:
                return self.parse_while_stmt()
            case TokenType.FOR:
                return self.parse_for_stmt()
            case TokenType.MATCH:
                return self.parse_match_stmt()
            case TokenType.TRY:
                return self.parse_try_stmt()
            case TokenType.RETURN:
                return self.parse_return_stmt()
            case TokenType.YIELD:
                return self.parse_yield_stmt()
            case TokenType.THROW:
                return self.parse_throw_stmt()
            case TokenType.BREAK:
                return self.parse_break_stmt()
            case TokenType.CONTINUE:
                return self.parse_continue_stmt()
            case _:
                return self._parse_expr_or_assign_stmt()

    def parse_let_stmt(self) -> LetStmt:
        """Parse: let name: Type:mut = expr or let name = expr

        Also handles coroutine start: let b :< a(x)
        """
        tok = self.expect(TokenType.LET)
        name_tok = self.expect(TokenType.IDENT)
        name = name_tok.value

        type_ann: TypeExpr | None = None

        # Check for coroutine start: let b :< expr [* N] [-> expr [* N]]*
        if self.check(TokenType.COROUTINE):
            coro_tok = self.advance()
            # Parse call at high precedence so -> and * are not consumed
            # as binary operators. Postfix precedence captures calls,
            # field access, and indexing but not infix operators.
            call_expr = self._parse_pratt(_PREC_UNARY)
            if not isinstance(call_expr, Call):
                raise self._error(
                    "coroutine start ':< ' requires a function call expression",
                    coro_tok,
                )
            # Check for * N pool size on first stage
            pool_size: Expr | None = None
            if self.check(TokenType.STAR):
                self.advance()
                pool_size = self._parse_pratt(_PREC_UNARY)
            # Check for pipeline: -> next_call [* N] -> ...
            if self.check(TokenType.ARROW) or pool_size is not None:
                stages = [PipelineStage(
                    line=call_expr.line, col=call_expr.col,
                    call=call_expr, pool_size=pool_size)]
                while self.check(TokenType.ARROW):
                    self.advance()  # consume ->
                    next_call = self._parse_pratt(_PREC_UNARY)
                    if not isinstance(next_call, Call):
                        raise self._error(
                            "pipeline stage requires a function call", coro_tok)
                    stage_pool: Expr | None = None
                    if self.check(TokenType.STAR):
                        self.advance()
                        stage_pool = self._parse_pratt(_PREC_UNARY)
                    stages.append(PipelineStage(
                        line=next_call.line, col=next_call.col,
                        call=next_call, pool_size=stage_pool))
                coro_expr = CoroutinePipeline(
                    line=coro_tok.line, col=coro_tok.col,
                    stages=stages)
            else:
                coro_expr = CoroutineStart(
                    line=coro_tok.line, col=coro_tok.col,
                    call=call_expr)
            return LetStmt(
                line=tok.line,
                col=tok.col,
                name=name,
                type_ann=type_ann,
                value=coro_expr,
            )

        # Optional type annotation
        if self.check(TokenType.COLON):
            self.advance()
            type_ann = self.parse_type_expr()

        self.expect(TokenType.ASSIGN)
        value = self.parse_expr()

        return LetStmt(
            line=tok.line,
            col=tok.col,
            name=name,
            type_ann=type_ann,
            value=value,
        )

    def parse_if_stmt(self) -> IfStmt | MatchStmt:
        """Parse: if (expr) { block } else if ... else { block }
        Also: if (let pattern = expr) { block } [else { block }]
        """
        tok = self.expect(TokenType.IF)
        self.expect(TokenType.LPAREN)

        # if (let ...) — desugar to MatchStmt
        if self.check(TokenType.LET):
            return self._parse_if_let(tok)

        condition = self.parse_expr()
        self.expect(TokenType.RPAREN)
        then_branch = self.parse_block()

        else_branch: Block | IfStmt | None = None
        if self.check(TokenType.ELSE):
            self.advance()
            if self.check(TokenType.IF):
                else_branch = self.parse_if_stmt()
            else:
                else_branch = self.parse_block()

        return IfStmt(
            line=tok.line,
            col=tok.col,
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch,
        )

    def _parse_if_let(self, if_tok: Token) -> MatchStmt:
        """Parse: if (let pattern = expr) { block } [else { block }]
        Desugars to MatchStmt with two arms.
        Note: LPAREN already consumed by parse_if_stmt()."""
        self.advance()  # consume LET
        pattern = self.parse_pattern()
        self.expect(TokenType.ASSIGN)
        subject = self.parse_expr()
        self.expect(TokenType.RPAREN)
        then_block = self.parse_block()

        else_block: Block | None = None
        if self.check(TokenType.ELSE):
            self.advance()
            else_block = self.parse_block()

        if else_block is None:
            else_block = Block(line=if_tok.line, col=if_tok.col, stmts=[],
                               finally_block=None)

        # Build complement pattern for the else arm
        complement = self._complement_pattern(pattern, if_tok)

        return MatchStmt(
            line=if_tok.line,
            col=if_tok.col,
            subject=subject,
            arms=[
                MatchArm(line=pattern.line, col=pattern.col,
                         pattern=pattern, body=then_block),
                MatchArm(line=complement.line, col=complement.col,
                         pattern=complement, body=else_block),
            ],
        )

    def _complement_pattern(self, pattern: Pattern, tok: Token) -> Pattern:
        """Return the complement pattern for an if-let arm."""
        match pattern:
            case SomePattern():
                return NonePattern(line=tok.line, col=tok.col)
            case NonePattern():
                return SomePattern(line=tok.line, col=tok.col, inner_var="_")
            case OkPattern():
                return ErrPattern(line=tok.line, col=tok.col, inner_var="_")
            case ErrPattern():
                return OkPattern(line=tok.line, col=tok.col, inner_var="_")
            case _:
                # For variant patterns or others, use wildcard as complement
                return WildcardPattern(line=tok.line, col=tok.col)

    def parse_while_stmt(self) -> WhileStmt:
        """Parse: while (expr) { block } [finally { block }]"""
        tok = self.expect(TokenType.WHILE)
        self.expect(TokenType.LPAREN)
        condition = self.parse_expr()
        self.expect(TokenType.RPAREN)
        body = self.parse_block()

        finally_block: Block | None = None
        if self.check(TokenType.FINALLY):
            finally_block = self._parse_finally_block_simple()

        return WhileStmt(
            line=tok.line,
            col=tok.col,
            condition=condition,
            body=body,
            finally_block=finally_block,
        )

    def parse_for_stmt(self) -> ForStmt:
        """Parse: for(item: Type in expr) { body } [finally { block }]"""
        tok = self.expect(TokenType.FOR)
        self.expect(TokenType.LPAREN)

        var_tok = self.expect(TokenType.IDENT)
        var = var_tok.value

        var_type: TypeExpr | None = None
        if self.check(TokenType.COLON):
            self.advance()
            var_type = self.parse_type_expr()

        self.expect(TokenType.IN)
        iterable = self.parse_expr()
        self.expect(TokenType.RPAREN)

        body = self.parse_block()

        finally_block: Block | None = None
        if self.check(TokenType.FINALLY):
            finally_block = self._parse_finally_block_simple()

        return ForStmt(
            line=tok.line,
            col=tok.col,
            var=var,
            var_type=var_type,
            iterable=iterable,
            body=body,
            finally_block=finally_block,
        )

    def parse_match_stmt(self) -> MatchStmt:
        """Parse: match expr { pattern : expr_or_block, ... }"""
        tok = self.expect(TokenType.MATCH)
        subject = self.parse_expr()
        self.expect(TokenType.LBRACE)

        arms: list[MatchArm] = []
        while not self.check(TokenType.RBRACE) and not self.at_end():
            arm = self._parse_match_arm()
            arms.append(arm)
            # Optional comma between arms
            self.match_token(TokenType.COMMA)

        self.expect(TokenType.RBRACE)

        return MatchStmt(
            line=tok.line,
            col=tok.col,
            subject=subject,
            arms=arms,
        )

    def parse_match_expr(self) -> MatchExpr:
        """Parse a match expression (same syntax as statement)."""
        tok = self.expect(TokenType.MATCH)
        subject = self.parse_expr()
        self.expect(TokenType.LBRACE)

        arms: list[MatchArm] = []
        while not self.check(TokenType.RBRACE) and not self.at_end():
            arm = self._parse_match_arm()
            arms.append(arm)
            self.match_token(TokenType.COMMA)

        self.expect(TokenType.RBRACE)

        return MatchExpr(
            line=tok.line,
            col=tok.col,
            subject=subject,
            arms=arms,
        )

    def _parse_match_arm(self) -> MatchArm:
        """Parse a single match arm: pattern : expr_or_block"""
        pattern = self.parse_pattern()
        self.expect(TokenType.COLON)

        # Body is either a block or an expression
        if self.check(TokenType.LBRACE):
            body: Expr | Block = self.parse_block()
        else:
            body = self.parse_expr()

        return MatchArm(
            line=pattern.line,
            col=pattern.col,
            pattern=pattern,
            body=body,
        )

    def parse_try_stmt(self) -> TryStmt:
        """Parse: try { } retry fn (ex: Type, attempts: n) { } catch (ex: Type) { } finally { }"""
        tok = self.expect(TokenType.TRY)
        body = self.parse_block()

        retry_blocks: list[RetryBlock] = []
        catch_blocks: list[CatchBlock] = []
        finally_block: FinallyBlock | None = None

        # Parse retry blocks
        while self.check(TokenType.RETRY):
            retry_blocks.append(self._parse_retry_block())

        # Parse catch blocks
        while self.check(TokenType.CATCH):
            catch_blocks.append(self._parse_catch_block())

        # Parse optional finally block
        if self.check(TokenType.FINALLY):
            finally_block = self._parse_finally_block()

        return TryStmt(
            line=tok.line,
            col=tok.col,
            body=body,
            retry_blocks=retry_blocks,
            catch_blocks=catch_blocks,
            finally_block=finally_block,
        )

    def _parse_retry_block(self) -> RetryBlock:
        """Parse: retry function_name (ex: Type, attempts: n) { body }"""
        tok = self.expect(TokenType.RETRY)
        target_fn_tok = self.expect(TokenType.IDENT)

        self.expect(TokenType.LPAREN)
        ex_var_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.COLON)
        ex_type = self.parse_type_expr()

        attempts: Expr | None = None
        if self.check(TokenType.COMMA):
            self.advance()
            # Parse "attempts: <expr>"
            self.expect(TokenType.IDENT)  # "attempts"
            self.expect(TokenType.COLON)
            attempts = self.parse_expr()

        self.expect(TokenType.RPAREN)
        body = self.parse_block()

        return RetryBlock(
            line=tok.line,
            col=tok.col,
            target_fn=target_fn_tok.value,
            exception_var=ex_var_tok.value,
            exception_type=ex_type,
            attempts=attempts,
            body=body,
        )

    def _parse_catch_block(self) -> CatchBlock:
        """Parse: catch (ex: Type) { body }"""
        tok = self.expect(TokenType.CATCH)
        self.expect(TokenType.LPAREN)
        ex_var_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.COLON)
        ex_type = self.parse_type_expr()
        self.expect(TokenType.RPAREN)

        body = self.parse_block()

        return CatchBlock(
            line=tok.line,
            col=tok.col,
            exception_var=ex_var_tok.value,
            exception_type=ex_type,
            body=body,
        )

    def _parse_finally_block(self) -> FinallyBlock:
        """Parse: finally (? ex: Exception) { body } or finally { body }"""
        tok = self.expect(TokenType.FINALLY)

        exception_var: str | None = None
        exception_type: TypeExpr | None = None

        if self.check(TokenType.LPAREN):
            self.advance()
            # Optional '?' before var name
            self.match_token(TokenType.QUESTION)
            ex_var_tok = self.expect(TokenType.IDENT)
            exception_var = ex_var_tok.value
            self.expect(TokenType.COLON)
            exception_type = self.parse_type_expr()
            self.expect(TokenType.RPAREN)

        body = self.parse_block()

        return FinallyBlock(
            line=tok.line,
            col=tok.col,
            exception_var=exception_var,
            exception_type=exception_type,
            body=body,
        )

    def parse_return_stmt(self) -> ReturnStmt:
        """Parse: return [expr]"""
        tok = self.expect(TokenType.RETURN)
        value: Expr | None = None
        # Return has an optional value — check if the next token could start an expr
        if not self._is_stmt_terminator():
            value = self.parse_expr()
        return ReturnStmt(line=tok.line, col=tok.col, value=value)

    def parse_yield_stmt(self) -> YieldStmt:
        """Parse: yield expr"""
        tok = self.expect(TokenType.YIELD)
        value = self.parse_expr()
        return YieldStmt(line=tok.line, col=tok.col, value=value)

    def parse_throw_stmt(self) -> ThrowStmt:
        """Parse: throw expr"""
        tok = self.expect(TokenType.THROW)
        exception = self.parse_expr()
        return ThrowStmt(line=tok.line, col=tok.col, exception=exception)

    def parse_break_stmt(self) -> BreakStmt:
        """Parse: break"""
        tok = self.expect(TokenType.BREAK)
        return BreakStmt(line=tok.line, col=tok.col)

    def parse_continue_stmt(self) -> ContinueStmt:
        """Parse: continue"""
        tok = self.expect(TokenType.CONTINUE)
        return ContinueStmt(line=tok.line, col=tok.col)

    def _is_stmt_terminator(self) -> bool:
        """Check if the current token would terminate a statement.

        Used to decide if 'return' has a value expression.
        """
        tok = self.peek()
        return tok.type in (
            TokenType.RBRACE,
            TokenType.EOF,
            TokenType.ELSE,
            TokenType.CATCH,
            TokenType.RETRY,
            TokenType.FINALLY,
        )

    def _parse_expr_or_assign_stmt(self) -> Stmt:
        """Parse an expression statement, assignment, or update statement."""
        expr = self.parse_expr()
        tok = self.peek()

        # Check for assignment: expr = value
        if tok.type == TokenType.ASSIGN:
            self.advance()
            value = self.parse_expr()
            return AssignStmt(
                line=expr.line,
                col=expr.col,
                target=expr,
                value=value,
            )

        # Check for update operators: +=, -=, *=, /=
        if tok.type in (TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN,
                        TokenType.STAR_ASSIGN, TokenType.SLASH_ASSIGN):
            op_tok = self.advance()
            value = self.parse_expr()
            op_map = {
                TokenType.PLUS_ASSIGN: "+=",
                TokenType.MINUS_ASSIGN: "-=",
                TokenType.STAR_ASSIGN: "*=",
                TokenType.SLASH_ASSIGN: "/=",
            }
            return UpdateStmt(
                line=expr.line,
                col=expr.col,
                target=expr,
                op=op_map[op_tok.type],
                value=value,
            )

        # Check for increment/decrement: ++, --
        if tok.type == TokenType.INCREMENT:
            self.advance()
            return UpdateStmt(
                line=expr.line, col=expr.col,
                target=expr, op="++", value=None,
            )
        if tok.type == TokenType.DECREMENT:
            self.advance()
            return UpdateStmt(
                line=expr.line, col=expr.col,
                target=expr, op="--", value=None,
            )

        # Plain expression statement
        return ExprStmt(line=expr.line, col=expr.col, expr=expr)

    # ------------------------------------------------------------------
    # Expressions — Pratt parser (Story 4-4)
    # ------------------------------------------------------------------

    def parse_expr(self) -> Expr:
        """Parse an expression at the lowest precedence level."""
        return self._parse_pratt(_PREC_NONE)

    def _parse_pratt(self, min_prec: int) -> Expr:
        """Pratt parser: parse expression with given minimum precedence."""
        left = self._parse_prefix()

        while True:
            tok = self.peek()

            # Composition chain: ->
            if tok.type == TokenType.ARROW and min_prec < _PREC_COMPOSITION:
                left = self._parse_composition_chain(left)
                continue

            # Ternary: expr ? then_expr : else_expr
            # This must be checked before the postfix ? (propagation).
            # Ternary binds at a very low precedence.
            if tok.type == TokenType.QUESTION and min_prec < _PREC_TERNARY:
                # Disambiguate ternary vs propagation:
                # If QUESTION is followed by a token that can start an expression,
                # and is not just ')' or ',' or '}' etc., try ternary.
                # We look ahead past QUESTION to see if there's an expression-like token.
                if self._is_ternary():
                    left = self._parse_ternary(left)
                    continue

            # Null coalesce: ??
            if tok.type == TokenType.DOUBLE_QUESTION and min_prec < _PREC_NULL_COALESCE:
                self.advance()
                right = self._parse_pratt(_PREC_NULL_COALESCE)
                left = NullCoalesce(
                    line=tok.line, col=tok.col,
                    left=left, right=right,
                )
                continue

            # Binary operators
            if tok.type in _INFIX_PRECEDENCE:
                prec = _INFIX_PRECEDENCE[tok.type]
                if prec > min_prec:
                    # Right-associative for **
                    if tok.type == TokenType.DOUBLE_STAR:
                        self.advance()
                        right = self._parse_pratt(prec - 1)
                    else:
                        self.advance()
                        right = self._parse_pratt(prec)
                    op_str = _BINOP_STRINGS[tok.type]
                    left = BinOp(
                        line=tok.line, col=tok.col,
                        op=op_str, left=left, right=right,
                    )
                    continue

            # Postfix operators (high precedence)
            if min_prec < _PREC_POSTFIX:
                # Propagation: expr?
                if tok.type == TokenType.QUESTION and not self._is_ternary():
                    self.advance()
                    left = PropagateExpr(
                        line=tok.line, col=tok.col,
                        inner=left,
                    )
                    continue

                # Field/method access: expr.name or expr.name(args)
                if tok.type == TokenType.DOT:
                    self.advance()
                    field_tok = self.peek()
                    if field_tok.type == TokenType.INT_LIT:
                        # Tuple index access: expr.0, expr.1
                        idx_tok = self.advance()
                        left = FieldAccess(
                            line=tok.line, col=tok.col,
                            receiver=left, field=idx_tok.value,
                        )
                    else:
                        field_tok = self.expect(TokenType.IDENT)
                        if self.check(TokenType.LPAREN):
                            # Method call: expr.name(args)
                            self.advance()
                            args = self._parse_arg_list()
                            self.expect(TokenType.RPAREN)
                            left = MethodCall(
                                line=tok.line, col=tok.col,
                                receiver=left,
                                method=field_tok.value,
                                args=args,
                            )
                        else:
                            left = FieldAccess(
                                line=tok.line, col=tok.col,
                                receiver=left, field=field_tok.value,
                            )
                    continue

                # Function call: expr(args)
                if tok.type == TokenType.LPAREN:
                    self.advance()
                    args = self._parse_arg_list()
                    self.expect(TokenType.RPAREN)
                    left = Call(
                        line=tok.line, col=tok.col,
                        callee=left, args=args,
                    )
                    continue

                # Index access: expr[index]
                if tok.type == TokenType.LBRACKET:
                    self.advance()
                    index = self.parse_expr()
                    self.expect(TokenType.RBRACKET)
                    left = IndexAccess(
                        line=tok.line, col=tok.col,
                        receiver=left, index=index,
                    )
                    continue

            break

        return left

    def _is_ternary(self) -> bool:
        """Determine whether the current QUESTION token is ternary (? expr : expr)
        or propagation (?).

        We speculatively parse past the ? to see if we find expr : expr.
        If the speculative parse fails or no COLON follows, it's propagation.
        """
        saved = self._pos
        saved_errors = list(self._errors)
        try:
            self.skip_comments()
            self._pos += 1  # skip ?
            self.skip_comments()

            next_tok = self._tokens[self._pos] if self._pos < len(self._tokens) else self._tokens[-1]

            # Quick reject: if the next token clearly can't start an expression,
            # it's definitely propagation.
            can_start_expr = next_tok.type in (
                TokenType.IDENT,
                TokenType.INT_LIT, TokenType.FLOAT_LIT, TokenType.BOOL_LIT,
                TokenType.STRING_LIT, TokenType.CHAR_LIT,
                TokenType.NONE,
                TokenType.LPAREN,
                TokenType.LBRACKET,
                TokenType.MINUS,
                TokenType.BANG,
                TokenType.AT,
                TokenType.BACKSLASH,
                TokenType.SOME,
                TokenType.OK,
                TokenType.ERR,
                TokenType.FSTRING_START,
                TokenType.MATCH,
                TokenType.IF,
                TokenType.TYPEOF,
                TokenType.COERCE,
                TokenType.CAST,
                TokenType.SELF,
            )
            if not can_start_expr:
                return False

            # Speculatively parse the then-expression and check for ':'
            try:
                self._parse_pratt(_PREC_TERNARY)
                self.skip_comments()
                if self._pos < len(self._tokens):
                    return self._tokens[self._pos].type == TokenType.COLON
                return False
            except Exception:
                return False
        finally:
            self._pos = saved
            self._errors = saved_errors

    def _parse_ternary(self, condition: Expr) -> TernaryExpr:
        """Parse: condition ? then_expr : else_expr"""
        q_tok = self.expect(TokenType.QUESTION)
        then_expr = self._parse_pratt(_PREC_TERNARY)
        self.expect(TokenType.COLON)
        else_expr = self._parse_pratt(_PREC_TERNARY)
        return TernaryExpr(
            line=q_tok.line, col=q_tok.col,
            condition=condition,
            then_expr=then_expr,
            else_expr=else_expr,
        )

    def _parse_composition_chain(self, first: Expr) -> CompositionChain:
        """Parse a composition chain: expr -> expr -> expr -> ...

        Handles fan-out groups: (a | b) and parallel fan-out: <:(a | b)
        """
        elements: list[ChainElement] = [
            ChainElement(line=first.line, col=first.col, expr=first)
        ]

        while self.check(TokenType.ARROW):
            self.advance()  # consume '->'

            # Check for parallel fan-out: <:( already consumed by arrow
            if self.check(TokenType.PARALLEL_FANOUT):
                pfan_tok = self.advance()
                fan = self._parse_fanout_body(parallel=True)
                fan.line = pfan_tok.line
                fan.col = pfan_tok.col
                elements.append(ChainElement(
                    line=pfan_tok.line, col=pfan_tok.col, expr=fan,
                ))
            elif self.check(TokenType.LPAREN):
                # Could be fan-out (a | b) or grouping (expr)
                # If it contains |, it's fan-out
                if self._is_fanout():
                    tok = self.advance()  # consume '('
                    fan = self._parse_fanout_body(parallel=False)
                    fan.line = tok.line
                    fan.col = tok.col
                    elements.append(ChainElement(
                        line=tok.line, col=tok.col, expr=fan,
                    ))
                else:
                    expr = self._parse_chain_element_expr()
                    elements.append(ChainElement(
                        line=expr.line, col=expr.col, expr=expr,
                    ))
            else:
                expr = self._parse_chain_element_expr()
                elements.append(ChainElement(
                    line=expr.line, col=expr.col, expr=expr,
                ))

        return CompositionChain(
            line=first.line, col=first.col,
            elements=elements,
        )

    def _parse_chain_element_expr(self) -> Expr:
        """Parse a single element in a composition chain (not a full expression,
        just at a high enough precedence that -> doesn't get consumed)."""
        return self._parse_pratt(_PREC_COMPOSITION)

    def _is_fanout(self) -> bool:
        """Look ahead to determine if the current LPAREN starts a fan-out (contains |)."""
        saved = self._pos
        depth = 0
        try:
            while self._pos < len(self._tokens):
                tok = self._tokens[self._pos]
                if tok.type in (TokenType.COMMENT, TokenType.NEWLINE):
                    self._pos += 1
                    continue
                if tok.type == TokenType.LPAREN:
                    depth += 1
                    self._pos += 1
                elif tok.type == TokenType.RPAREN:
                    depth -= 1
                    if depth == 0:
                        return False  # No | found before matching )
                    self._pos += 1
                elif tok.type == TokenType.PIPE and depth == 1:
                    return True
                elif tok.type == TokenType.EOF:
                    return False
                else:
                    self._pos += 1
            return False
        finally:
            self._pos = saved

    def _parse_fanout_body(self, parallel: bool) -> FanOut:
        """Parse the body of a fan-out: a | b | c).

        Assumes the opening '(' has already been consumed (for regular fan-out)
        or <:( has been consumed (for parallel).
        """
        branches: list[ChainElement] = []

        # Parse first branch
        expr = self._parse_fanout_branch()
        branches.append(ChainElement(line=expr.line, col=expr.col, expr=expr))

        while self.check(TokenType.PIPE):
            self.advance()
            expr = self._parse_fanout_branch()
            branches.append(ChainElement(line=expr.line, col=expr.col, expr=expr))

        self.expect(TokenType.RPAREN)

        return FanOut(
            line=0, col=0,  # will be set by caller
            branches=branches,
            parallel=parallel,
        )

    def _parse_fanout_branch(self) -> Expr:
        """Parse a single branch within a fan-out group.

        A branch can itself be a mini composition chain: x -> fn
        """
        expr = self._parse_pratt(_PREC_COMPOSITION)

        # If there's an arrow, parse a mini chain within this fan-out branch
        if self.check(TokenType.ARROW):
            elements: list[ChainElement] = [
                ChainElement(line=expr.line, col=expr.col, expr=expr)
            ]
            while self.check(TokenType.ARROW):
                self.advance()
                next_expr = self._parse_pratt(_PREC_COMPOSITION)
                elements.append(ChainElement(
                    line=next_expr.line, col=next_expr.col, expr=next_expr,
                ))
            return CompositionChain(
                line=expr.line, col=expr.col,
                elements=elements,
            )

        return expr

    def _parse_prefix(self) -> Expr:
        """Parse a prefix expression (unary or primary)."""
        tok = self.peek()

        # Unary minus: -expr
        if tok.type == TokenType.MINUS:
            self.advance()
            operand = self._parse_pratt(_PREC_UNARY)
            return UnaryOp(
                line=tok.line, col=tok.col,
                op="-", operand=operand,
            )

        # Unary not: !expr
        if tok.type == TokenType.BANG:
            self.advance()
            operand = self._parse_pratt(_PREC_UNARY)
            return UnaryOp(
                line=tok.line, col=tok.col,
                op="!", operand=operand,
            )

        # Copy: @expr
        if tok.type == TokenType.AT:
            self.advance()
            operand = self._parse_pratt(_PREC_UNARY)
            return CopyExpr(
                line=tok.line, col=tok.col,
                inner=operand,
            )

        # Immutable ref: &expr
        if tok.type == TokenType.AMPERSAND:
            self.advance()
            operand = self._parse_pratt(_PREC_UNARY)
            return RefExpr(
                line=tok.line, col=tok.col,
                inner=operand,
            )

        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        """Parse a primary expression."""
        tok = self.peek()

        match tok.type:
            # Literals
            case TokenType.INT_LIT:
                return self._parse_int_lit()
            case TokenType.FLOAT_LIT:
                return self._parse_float_lit()
            case TokenType.BOOL_LIT:
                return self._parse_bool_lit()
            case TokenType.STRING_LIT:
                return self._parse_string_lit()
            case TokenType.CHAR_LIT:
                return self._parse_char_lit()
            case TokenType.NONE:
                return self._parse_none_lit()
            case TokenType.FSTRING_START:
                return self._parse_fstring_expr()

            # Keywords that produce expressions
            case TokenType.SOME:
                return self._parse_some_expr()
            case TokenType.OK:
                return self._parse_ok_expr()
            case TokenType.ERR:
                return self._parse_err_expr()
            case TokenType.COERCE:
                return self._parse_coerce_expr()
            case TokenType.CAST:
                return self._parse_cast_expr()
            case TokenType.TYPEOF:
                return self._parse_typeof_expr()

            # Match expression
            case TokenType.MATCH:
                return self.parse_match_expr()

            # If expression
            case TokenType.IF:
                return self._parse_if_expr()

            # Lambda: \(params => body)
            case TokenType.BACKSLASH:
                return self._parse_lambda()

            # Array literal: [a, b, c]
            case TokenType.LBRACKET:
                return self._parse_array_lit()

            # Grouped expression, tuple, or record: (expr) or (a, b) or { k: v }
            case TokenType.LPAREN:
                return self._parse_paren_expr()

            # Record literal: { field: value }
            case TokenType.LBRACE:
                return self._parse_record_lit()

            # Self keyword
            case TokenType.SELF:
                self.advance()
                return Ident(
                    line=tok.line, col=tok.col,
                    name="self", module_path=[],
                )

            # Identifier (possibly with module path, possibly type construction)
            case TokenType.IDENT:
                return self._parse_ident_or_type_lit()

            case _:
                raise self._error(
                    f"expected expression but found '{tok.value}' ({tok.type.name})"
                )

    def _parse_int_lit(self) -> IntLit:
        tok = self.advance()
        value = int(tok.value, 0)  # handles hex with 0x prefix
        return IntLit(line=tok.line, col=tok.col, value=value, suffix=None)

    def _parse_float_lit(self) -> FloatLit:
        tok = self.advance()
        value = float(tok.value)
        return FloatLit(line=tok.line, col=tok.col, value=value, suffix=None)

    def _parse_bool_lit(self) -> BoolLit:
        tok = self.advance()
        return BoolLit(line=tok.line, col=tok.col, value=(tok.value == "true"))

    def _parse_string_lit(self) -> StringLit:
        tok = self.advance()
        return StringLit(line=tok.line, col=tok.col, value=tok.value)

    def _parse_char_lit(self) -> CharLit:
        tok = self.advance()
        return CharLit(line=tok.line, col=tok.col, value=ord(tok.value))

    def _parse_none_lit(self) -> NoneLit:
        tok = self.advance()
        return NoneLit(line=tok.line, col=tok.col)

    def _parse_fstring_expr(self) -> FStringExpr:
        """Parse an f-string: FSTRING_START (FSTRING_TEXT | FSTRING_EXPR_START expr FSTRING_EXPR_END)* FSTRING_END"""
        start_tok = self.advance()  # FSTRING_START
        parts: list[str | Expr] = []

        while not self.at_end():
            raw_tok = self._peek_raw()

            if raw_tok.type == TokenType.FSTRING_END:
                self._pos += 1  # consume FSTRING_END
                break
            elif raw_tok.type == TokenType.FSTRING_TEXT:
                self._pos += 1  # consume text
                parts.append(raw_tok.value)
            elif raw_tok.type == TokenType.FSTRING_EXPR_START:
                self._pos += 1  # consume FSTRING_EXPR_START
                expr = self.parse_expr()
                parts.append(expr)
                # Expect FSTRING_EXPR_END
                raw_end = self._peek_raw()
                if raw_end.type == TokenType.FSTRING_EXPR_END:
                    self._pos += 1
                else:
                    raise self._error(
                        f"expected FSTRING_EXPR_END but found '{raw_end.value}' ({raw_end.type.name})"
                    )
            elif raw_tok.type in (TokenType.COMMENT, TokenType.NEWLINE):
                self._pos += 1  # skip
            else:
                raise self._error(
                    f"unexpected token in f-string: '{raw_tok.value}' ({raw_tok.type.name})"
                )

        return FStringExpr(line=start_tok.line, col=start_tok.col, parts=parts)

    def _parse_some_expr(self) -> SomeExpr:
        """Parse: some(expr)"""
        tok = self.advance()  # 'some'
        self.expect(TokenType.LPAREN)
        inner = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return SomeExpr(line=tok.line, col=tok.col, inner=inner)

    def _parse_ok_expr(self) -> OkExpr:
        """Parse: ok(expr)"""
        tok = self.advance()  # 'ok'
        self.expect(TokenType.LPAREN)
        inner = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return OkExpr(line=tok.line, col=tok.col, inner=inner)

    def _parse_err_expr(self) -> ErrExpr:
        """Parse: err(expr)"""
        tok = self.advance()  # 'err'
        self.expect(TokenType.LPAREN)
        inner = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return ErrExpr(line=tok.line, col=tok.col, inner=inner)

    def _parse_coerce_expr(self) -> CoerceExpr:
        """Parse: coerce(expr)"""
        tok = self.advance()  # 'coerce'
        self.expect(TokenType.LPAREN)
        inner = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return CoerceExpr(line=tok.line, col=tok.col, inner=inner, target_type=None)

    def _parse_cast_expr(self) -> CastExpr:
        """Parse: cast<T>(expr)"""
        tok = self.advance()  # 'cast'
        self.expect(TokenType.LT)
        target_type = self.parse_type_expr()
        self.expect(TokenType.GT)
        self.expect(TokenType.LPAREN)
        inner = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return CastExpr(line=tok.line, col=tok.col, inner=inner, target_type=target_type)

    def _parse_typeof_expr(self) -> TypeofExpr:
        """Parse: typeof(expr)"""
        tok = self.advance()  # 'typeof'
        self.expect(TokenType.LPAREN)
        inner = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return TypeofExpr(line=tok.line, col=tok.col, inner=inner)

    def _parse_if_expr(self) -> IfExpr:
        """Parse an if expression: if (expr) { block } else { block }"""
        tok = self.expect(TokenType.IF)
        self.expect(TokenType.LPAREN)
        condition = self.parse_expr()
        self.expect(TokenType.RPAREN)
        then_branch = self.parse_block()

        else_branch: Block | IfExpr | None = None
        if self.check(TokenType.ELSE):
            self.advance()
            if self.check(TokenType.IF):
                else_branch = self._parse_if_expr()
            else:
                else_branch = self.parse_block()

        return IfExpr(
            line=tok.line, col=tok.col,
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch,
        )

    def _parse_lambda(self) -> Lambda:
        r"""Parse: \(params => body)"""
        tok = self.expect(TokenType.BACKSLASH)
        self.expect(TokenType.LPAREN)

        params: list[Param] = []

        # Parse params until we see '=>'
        # Params are: name: Type, name: Type, ... =>
        # Or just: => (for zero-param lambdas like \( => x + y))
        if not self.check(TokenType.FAT_ARROW):
            params.append(self._parse_param())
            while self.check(TokenType.COMMA):
                self.advance()
                # Check if we hit => after comma (trailing comma)
                if self.check(TokenType.FAT_ARROW):
                    break
                params.append(self._parse_param())

        self.expect(TokenType.FAT_ARROW)
        body = self.parse_expr()
        self.expect(TokenType.RPAREN)

        return Lambda(
            line=tok.line, col=tok.col,
            params=params,
            body=body,
        )

    def _parse_array_lit(self) -> ArrayLit:
        """Parse: [a, b, c]"""
        tok = self.expect(TokenType.LBRACKET)
        elements: list[Expr] = []
        if not self.check(TokenType.RBRACKET):
            elements.append(self.parse_expr())
            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.RBRACKET):
                    break  # trailing comma
                elements.append(self.parse_expr())
        self.expect(TokenType.RBRACKET)
        return ArrayLit(line=tok.line, col=tok.col, elements=elements)

    def _parse_paren_expr(self) -> Expr:
        """Parse: (expr) grouping or (a, b, c) tuple."""
        tok = self.expect(TokenType.LPAREN)

        # Empty tuple: ()
        if self.check(TokenType.RPAREN):
            self.advance()
            return TupleExpr(line=tok.line, col=tok.col, elements=[])

        first = self.parse_expr()

        # If comma follows, it's a tuple
        if self.check(TokenType.COMMA):
            elements: list[Expr] = [first]
            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.RPAREN):
                    break  # trailing comma
                elements.append(self.parse_expr())
            self.expect(TokenType.RPAREN)
            return TupleExpr(line=tok.line, col=tok.col, elements=elements)

        # Simple grouping
        self.expect(TokenType.RPAREN)
        return first

    def _parse_record_lit(self) -> RecordLit:
        """Parse: { field: value, field2: value2 }"""
        tok = self.expect(TokenType.LBRACE)
        fields: list[tuple[str, Expr]] = []

        if not self.check(TokenType.RBRACE):
            field_name_tok = self.expect(TokenType.IDENT)
            self.expect(TokenType.COLON)
            value = self.parse_expr()
            fields.append((field_name_tok.value, value))

            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.RBRACE):
                    break
                field_name_tok = self.expect(TokenType.IDENT)
                self.expect(TokenType.COLON)
                value = self.parse_expr()
                fields.append((field_name_tok.value, value))

        self.expect(TokenType.RBRACE)
        return RecordLit(line=tok.line, col=tok.col, fields=fields)

    def _parse_ident_or_type_lit(self) -> Expr:
        """Parse an identifier, possibly followed by type construction literal.

        Dots are NOT consumed here — they are handled by the Pratt postfix
        handler which produces FieldAccess / MethodCall nodes. The only
        exception: when we see a dotted path leading to an uppercase name
        followed by '{', we collect it as a type construction literal
        (e.g. math.vector.Vec3 { ... }).
        """
        first_tok = self.advance()  # IDENT
        name = first_tok.value

        # Check for dotted path leading to type construction: a.b.TypeName { ... }
        # We speculatively collect dots only if the final segment is uppercase + LBRACE.
        if self.check(TokenType.DOT):
            saved_pos = self._pos
            module_path: list[str] = []
            current_name = name

            while self.check(TokenType.DOT):
                next_after_dot = self.peek2()
                if next_after_dot.type != TokenType.IDENT:
                    break
                self.advance()  # consume '.'
                next_tok = self.advance()  # consume IDENT
                module_path.append(current_name)
                current_name = next_tok.value

            # If it leads to TypeName { ... }, consume as type construction
            if self.check(TokenType.LBRACE) and current_name[0:1].isupper():
                return self._parse_type_construction_lit(first_tok, current_name, module_path)

            # Otherwise, backtrack — let the Pratt postfix handler deal with dots
            self._pos = saved_pos

        # Simple uppercase name + brace: TypeName { ... }
        if self.check(TokenType.LBRACE) and name[0:1].isupper():
            return self._parse_type_construction_lit(first_tok, name, [])

        return Ident(
            line=first_tok.line, col=first_tok.col,
            name=name, module_path=[],
        )

    def _parse_type_construction_lit(
        self,
        start_tok: Token,
        type_name: str,
        module_path: list[str],
    ) -> TypeLit:
        """Parse: TypeName { field: value, field2: value2, ..spread }"""
        self.expect(TokenType.LBRACE)
        fields: list[tuple[str, Expr]] = []
        spread: Expr | None = None

        while not self.check(TokenType.RBRACE) and not self.at_end():
            # Check for spread: ..expr
            if self.check(TokenType.SPREAD):
                spread_tok = self.advance()
                spread = self._parse_pratt(_PREC_POSTFIX)
                # Spread must be last
                self.match_token(TokenType.COMMA)
                break

            field_name_tok = self.expect(TokenType.IDENT)
            self.expect(TokenType.COLON)
            value = self.parse_expr()
            fields.append((field_name_tok.value, value))

            if not self.check(TokenType.RBRACE):
                self.expect(TokenType.COMMA)

        self.expect(TokenType.RBRACE)

        # Construct the full type name with module path for display
        full_name = ".".join(module_path + [type_name]) if module_path else type_name

        return TypeLit(
            line=start_tok.line, col=start_tok.col,
            type_name=full_name,
            fields=fields,
            spread=spread,
        )

    def _parse_arg_list(self) -> list[Expr]:
        """Parse a comma-separated argument list (inside parens, brackets not consumed)."""
        args: list[Expr] = []
        seen_named = False
        if self.check(TokenType.RPAREN):
            return args
        args.append(self._parse_call_arg(seen_named))
        if isinstance(args[-1], NamedArg):
            seen_named = True
        while self.check(TokenType.COMMA):
            self.advance()
            if self.check(TokenType.RPAREN):
                break  # trailing comma
            arg = self._parse_call_arg(seen_named)
            if isinstance(arg, NamedArg):
                seen_named = True
            elif seen_named:
                raise self._error(
                    "positional arguments cannot follow named arguments")
            args.append(arg)
        return args

    def _parse_call_arg(self, seen_named: bool) -> Expr:
        """Parse a single call argument, detecting named args (name: expr) and spread args (..expr)."""
        # Spread argument: ..expr
        if self.check(TokenType.SPREAD):
            spread_tok = self.advance()
            inner = self.parse_expr()
            return SpreadExpr(line=spread_tok.line, col=spread_tok.col,
                              expr=inner)
        if (self.check(TokenType.IDENT)
                and self.peek2().type == TokenType.COLON):
            # Named argument: name: expr
            tok = self.advance()  # consume IDENT
            self.advance()  # consume COLON
            value = self.parse_expr()
            return NamedArg(line=tok.line, col=tok.col,
                            name=tok.value, value=value)
        if seen_named:
            raise self._error(
                "positional arguments cannot follow named arguments")
        return self.parse_expr()

    # ------------------------------------------------------------------
    # Pattern parsing (Story 4-4, RT-4-4-6)
    # ------------------------------------------------------------------

    def parse_pattern(self) -> Pattern:
        """Parse a match pattern.

        Patterns:
          _ -> WildcardPattern
          none -> NonePattern
          some(v) -> SomePattern
          ok(v) -> OkPattern
          err(e) -> ErrPattern
          VariantName(a, b) -> VariantPattern
          (a, b) -> TuplePattern
          literal -> LiteralPattern
          ident -> BindPattern
        """
        tok = self.peek()

        # Wildcard
        if tok.type == TokenType.IDENT and tok.value == "_":
            self.advance()
            return WildcardPattern(line=tok.line, col=tok.col)

        # none
        if tok.type == TokenType.NONE:
            self.advance()
            return NonePattern(line=tok.line, col=tok.col)

        # some(v)
        if tok.type == TokenType.SOME:
            self.advance()
            self.expect(TokenType.LPAREN)
            inner_tok = self.expect(TokenType.IDENT)
            self.expect(TokenType.RPAREN)
            return SomePattern(line=tok.line, col=tok.col, inner_var=inner_tok.value)

        # ok(v)
        if tok.type == TokenType.OK:
            self.advance()
            self.expect(TokenType.LPAREN)
            inner_tok = self.expect(TokenType.IDENT)
            self.expect(TokenType.RPAREN)
            return OkPattern(line=tok.line, col=tok.col, inner_var=inner_tok.value)

        # err(e)
        if tok.type == TokenType.ERR:
            self.advance()
            self.expect(TokenType.LPAREN)
            inner_tok = self.expect(TokenType.IDENT)
            self.expect(TokenType.RPAREN)
            return ErrPattern(line=tok.line, col=tok.col, inner_var=inner_tok.value)

        # Tuple pattern: (a, b)
        if tok.type == TokenType.LPAREN:
            return self._parse_tuple_pattern()

        # Literal patterns (numbers, strings, booleans, chars)
        if tok.type in (TokenType.INT_LIT, TokenType.FLOAT_LIT,
                        TokenType.STRING_LIT, TokenType.CHAR_LIT):
            expr = self._parse_primary()
            return LiteralPattern(line=tok.line, col=tok.col, value=expr)

        # Negative number literal pattern: -42
        if tok.type == TokenType.MINUS:
            self.advance()
            inner = self._parse_primary()
            neg = UnaryOp(line=tok.line, col=tok.col, op="-", operand=inner)
            return LiteralPattern(line=tok.line, col=tok.col, value=neg)

        if tok.type == TokenType.BOOL_LIT:
            expr = self._parse_bool_lit()
            return LiteralPattern(line=tok.line, col=tok.col, value=expr)

        # Identifier: could be a variant pattern like Circle(r) or a bind pattern
        if tok.type == TokenType.IDENT:
            name_tok = self.advance()

            # Variant pattern: Name(a, b, c)
            if self.check(TokenType.LPAREN):
                self.advance()
                bindings: list[str] = []
                if not self.check(TokenType.RPAREN):
                    b_tok = self.expect(TokenType.IDENT)
                    bindings.append(b_tok.value)
                    while self.check(TokenType.COMMA):
                        self.advance()
                        if self.check(TokenType.RPAREN):
                            break
                        b_tok = self.expect(TokenType.IDENT)
                        bindings.append(b_tok.value)
                self.expect(TokenType.RPAREN)
                return VariantPattern(
                    line=name_tok.line, col=name_tok.col,
                    variant_name=name_tok.value,
                    bindings=bindings,
                )

            # Bare identifier: bind pattern
            return BindPattern(line=name_tok.line, col=name_tok.col, name=name_tok.value)

        raise self._error(f"expected pattern but found '{tok.value}' ({tok.type.name})")

    def _parse_tuple_pattern(self) -> TuplePattern:
        """Parse: (pattern, pattern, ...)"""
        tok = self.expect(TokenType.LPAREN)
        elements: list[Pattern] = []
        if not self.check(TokenType.RPAREN):
            elements.append(self.parse_pattern())
            while self.check(TokenType.COMMA):
                self.advance()
                if self.check(TokenType.RPAREN):
                    break
                elements.append(self.parse_pattern())
        self.expect(TokenType.RPAREN)
        return TuplePattern(line=tok.line, col=tok.col, elements=elements)


# ---------------------------------------------------------------------------
# Public convenience function
# ---------------------------------------------------------------------------

def parse(tokens: list[Token], filename: str) -> Module:
    """Convenience function: parse a token list into a Module AST."""
    parser = Parser(tokens, filename)
    return parser.parse()
