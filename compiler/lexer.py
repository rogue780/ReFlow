# compiler/lexer.py — source string → list[Token]
# No semantics. Produces tokens only.
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from compiler.errors import LexError


class TokenType(Enum):
    """All token types for the Flow language."""

    # --- Keywords ---
    MODULE = auto()
    IMPORT = auto()
    EXPORT = auto()
    AS = auto()
    ALIAS = auto()
    TYPE = auto()
    TYPEOF = auto()
    MUT = auto()
    IMUT = auto()
    LET = auto()
    FN = auto()
    RETURN = auto()
    YIELD = auto()
    TRY = auto()
    RETRY = auto()
    CATCH = auto()
    FINALLY = auto()
    INTERFACE = auto()
    FULFILLS = auto()
    CONSTRUCTOR = auto()
    SELF = auto()
    FOR = auto()
    IN = auto()
    WHILE = auto()
    IF = auto()
    ELSE = auto()
    MATCH = auto()
    NONE = auto()
    BREAK = auto()
    CONTINUE = auto()
    STATIC = auto()
    PURE = auto()
    RECORD = auto()
    SOME = auto()
    OK = auto()
    ERR = auto()
    COERCE = auto()
    CAST = auto()
    # SNAPSHOT removed — replaced by @ on mutable static access
    THROW = auto()
    NATIVE = auto()
    EXTERN = auto()

    # --- Operators ---
    ARROW = auto()           # ->
    FAT_ARROW = auto()       # =>
    PARALLEL_FANOUT = auto() # <:(
    PIPE = auto()            # |
    QUESTION = auto()        # ?
    DOUBLE_QUESTION = auto() # ??
    TRIPLE_EQ = auto()       # ===
    DOUBLE_EQ = auto()       # ==
    NOT_EQ = auto()          # !=
    ASSIGN = auto()          # =
    PLUS_ASSIGN = auto()     # +=
    MINUS_ASSIGN = auto()    # -=
    STAR_ASSIGN = auto()     # *=
    SLASH_ASSIGN = auto()    # /=
    INCREMENT = auto()       # ++
    DECREMENT = auto()       # --
    DOUBLE_STAR = auto()     # **
    FLOOR_DIV = auto()       # </
    COROUTINE = auto()       # :<
    SPREAD = auto()          # ..
    AND = auto()             # &&
    OR = auto()              # ||
    BANG = auto()            # !
    AT = auto()              # @
    AMPERSAND = auto()       # &
    BACKSLASH = auto()       # \

    # --- Single-character tokens ---
    PLUS = auto()            # +
    MINUS = auto()           # -
    STAR = auto()            # *
    SLASH = auto()           # /
    PERCENT = auto()         # %
    LT = auto()              # <
    GT = auto()              # >
    LT_EQ = auto()           # <=
    GT_EQ = auto()           # >=
    LPAREN = auto()          # (
    RPAREN = auto()          # )
    LBRACE = auto()          # {
    RBRACE = auto()          # }
    LBRACKET = auto()        # [
    RBRACKET = auto()        # ]
    COLON = auto()           # :
    COMMA = auto()           # ,
    DOT = auto()             # .
    SEMICOLON = auto()       # ;

    # --- Literals ---
    INT_LIT = auto()
    FLOAT_LIT = auto()
    BOOL_LIT = auto()
    STRING_LIT = auto()
    FSTRING_START = auto()
    FSTRING_END = auto()
    FSTRING_TEXT = auto()
    FSTRING_EXPR_START = auto()
    FSTRING_EXPR_END = auto()
    CHAR_LIT = auto()

    # --- Other ---
    IDENT = auto()
    COMMENT = auto()
    NEWLINE = auto()
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int
    file: str


# Keyword string → TokenType mapping.
_KEYWORDS: dict[str, TokenType] = {
    "module": TokenType.MODULE,
    "import": TokenType.IMPORT,
    "export": TokenType.EXPORT,
    "as": TokenType.AS,
    "alias": TokenType.ALIAS,
    "type": TokenType.TYPE,
    "typeof": TokenType.TYPEOF,
    "mut": TokenType.MUT,
    "imut": TokenType.IMUT,
    "let": TokenType.LET,
    "fn": TokenType.FN,
    "return": TokenType.RETURN,
    "yield": TokenType.YIELD,
    "try": TokenType.TRY,
    "retry": TokenType.RETRY,
    "catch": TokenType.CATCH,
    "finally": TokenType.FINALLY,
    "interface": TokenType.INTERFACE,
    "fulfills": TokenType.FULFILLS,
    "constructor": TokenType.CONSTRUCTOR,
    "self": TokenType.SELF,
    "for": TokenType.FOR,
    "in": TokenType.IN,
    "while": TokenType.WHILE,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "match": TokenType.MATCH,
    "none": TokenType.NONE,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "static": TokenType.STATIC,
    "pure": TokenType.PURE,
    "record": TokenType.RECORD,
    "some": TokenType.SOME,
    "ok": TokenType.OK,
    "err": TokenType.ERR,
    "coerce": TokenType.COERCE,
    "cast": TokenType.CAST,
    "throw": TokenType.THROW,
    "native": TokenType.NATIVE,
    "extern": TokenType.EXTERN,
    "true": TokenType.BOOL_LIT,
    "false": TokenType.BOOL_LIT,
}


class Lexer:
    """Single-pass scanner that converts a Flow source string into tokens."""

    def __init__(self, source: str, filename: str) -> None:
        self._source = source
        self._filename = filename
        self._pos = 0
        self._line = 1
        self._col = 1
        self._tokens: list[Token] = []
        # Track whether we are currently inside an f-string (for nested handling).
        self._fstring_depth = 0
        # Stack of brace depths for nested f-string expressions.
        # Each entry is the current brace-depth counter for that f-string level.
        self._fstring_brace_depths: list[int] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _at_end(self) -> bool:
        return self._pos >= len(self._source)

    def _peek(self, offset: int = 0) -> str:
        idx = self._pos + offset
        if idx >= len(self._source):
            return "\0"
        return self._source[idx]

    def _advance(self) -> str:
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    def _match(self, expected: str) -> bool:
        """If the upcoming characters match *expected*, advance past them and return True."""
        end = self._pos + len(expected)
        if end > len(self._source):
            return False
        if self._source[self._pos:end] == expected:
            for _ in expected:
                self._advance()
            return True
        return False

    def _check(self, expected: str) -> bool:
        """Peek ahead to see if the upcoming chars match *expected* without consuming."""
        end = self._pos + len(expected)
        if end > len(self._source):
            return False
        return self._source[self._pos:end] == expected

    def _make_token(self, ttype: TokenType, value: str, line: int, col: int) -> Token:
        return Token(type=ttype, value=value, line=line, col=col, file=self._filename)

    def _error(self, message: str, line: int | None = None, col: int | None = None) -> LexError:
        return LexError(
            message=message,
            file=self._filename,
            line=line if line is not None else self._line,
            col=col if col is not None else self._col,
        )

    # ------------------------------------------------------------------
    # Escape sequences (shared by strings, f-strings, char literals)
    # ------------------------------------------------------------------

    def _scan_escape(self) -> str:
        """Consume and return the interpreted value of an escape sequence.

        Assumes the leading backslash has already been consumed.
        """
        if self._at_end():
            raise self._error("unterminated escape sequence")
        ch = self._advance()
        simple: dict[str, str] = {
            "n": "\n",
            "t": "\t",
            "\\": "\\",
            '"': '"',
            "'": "'",
            "0": "\0",
            "r": "\r",
            "{": "{",
        }
        if ch in simple:
            return simple[ch]
        if ch == "u":
            # \u{XXXX}
            if self._at_end() or self._peek() != "{":
                raise self._error("expected '{' after '\\u'")
            self._advance()  # consume '{'
            hex_digits: list[str] = []
            while not self._at_end() and self._peek() != "}":
                hex_digits.append(self._advance())
            if self._at_end():
                raise self._error("unterminated unicode escape")
            self._advance()  # consume '}'
            hex_str = "".join(hex_digits)
            if not hex_str:
                raise self._error("empty unicode escape")
            return chr(int(hex_str, 16))
        raise self._error(f"unknown escape sequence '\\{ch}'")

    # ------------------------------------------------------------------
    # Identifier / keyword
    # ------------------------------------------------------------------

    def _scan_identifier(self) -> Token:
        start_line = self._line
        start_col = self._col
        start_pos = self._pos
        self._advance()  # consume first char (letter or _)
        while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
            self._advance()
        text = self._source[start_pos:self._pos]
        ttype = _KEYWORDS.get(text, TokenType.IDENT)
        return self._make_token(ttype, text, start_line, start_col)

    # ------------------------------------------------------------------
    # Numeric literals
    # ------------------------------------------------------------------

    def _scan_number(self) -> Token:
        start_line = self._line
        start_col = self._col
        start_pos = self._pos
        is_float = False

        # Check for hex prefix.
        if self._peek() == "0" and self._peek(1) in ("x", "X"):
            self._advance()  # '0'
            self._advance()  # 'x'
            while not self._at_end() and (self._peek() in "0123456789abcdefABCDEF_"):
                self._advance()
            raw = self._source[start_pos:self._pos]
            value = raw.replace("_", "")
            return self._make_token(TokenType.INT_LIT, value, start_line, start_col)

        # Decimal digits (with underscores).
        while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
            self._advance()

        # Fractional part: only if '.' followed by a digit (not '..' spread).
        if not self._at_end() and self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._advance()  # '.'
            while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
                self._advance()

        # Exponent part.
        if not self._at_end() and self._peek() in ("e", "E"):
            is_float = True
            self._advance()  # 'e'/'E'
            if not self._at_end() and self._peek() in ("+", "-"):
                self._advance()
            while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
                self._advance()

        raw = self._source[start_pos:self._pos]
        value = raw.replace("_", "")
        ttype = TokenType.FLOAT_LIT if is_float else TokenType.INT_LIT
        return self._make_token(ttype, value, start_line, start_col)

    # ------------------------------------------------------------------
    # String literals
    # ------------------------------------------------------------------

    def _scan_string(self) -> Token:
        start_line = self._line
        start_col = self._col
        self._advance()  # consume opening '"'
        chars: list[str] = []
        while not self._at_end():
            ch = self._peek()
            if ch == '"':
                self._advance()  # consume closing '"'
                return self._make_token(
                    TokenType.STRING_LIT, "".join(chars), start_line, start_col
                )
            if ch == "\\":
                self._advance()  # consume backslash
                chars.append(self._scan_escape())
            elif ch == "\n":
                # Allow multi-line strings; track position.
                chars.append(self._advance())
            else:
                chars.append(self._advance())
        raise self._error("unterminated string literal", start_line, start_col)

    # ------------------------------------------------------------------
    # F-strings
    # ------------------------------------------------------------------

    def _scan_fstring(self) -> None:
        """Scan a complete f-string, emitting FSTRING_START, text/expr tokens, and FSTRING_END."""
        start_line = self._line
        start_col = self._col
        self._advance()  # consume 'f'
        self._advance()  # consume '"'
        self._tokens.append(
            self._make_token(TokenType.FSTRING_START, 'f"', start_line, start_col)
        )
        self._fstring_depth += 1
        self._fstring_brace_depths.append(0)

        self._scan_fstring_body()

        self._fstring_depth -= 1
        self._fstring_brace_depths.pop()

    def _scan_fstring_body(self) -> None:
        """Scan the body of an f-string (text segments and expressions) until closing quote."""
        while not self._at_end():
            ch = self._peek()
            if ch == '"':
                # End of f-string.
                end_line = self._line
                end_col = self._col
                self._advance()  # consume '"'
                self._tokens.append(
                    self._make_token(TokenType.FSTRING_END, '"', end_line, end_col)
                )
                return
            if ch == "{":
                self._scan_fstring_expr()
            elif ch == "\\":
                # Escape inside f-string text.
                text_line = self._line
                text_col = self._col
                self._advance()  # consume '\'
                escaped = self._scan_escape()
                self._tokens.append(
                    self._make_token(TokenType.FSTRING_TEXT, escaped, text_line, text_col)
                )
            else:
                # Accumulate plain text.
                self._scan_fstring_text()

        # If we reach here, the f-string was never closed.
        raise self._error("unterminated f-string")

    def _scan_fstring_text(self) -> None:
        """Accumulate plain text characters inside an f-string until '{', '"', or '\\'."""
        start_line = self._line
        start_col = self._col
        chars: list[str] = []
        while not self._at_end():
            ch = self._peek()
            if ch in ('"', "{"):
                break
            if ch == "\\":
                break
            chars.append(self._advance())
        if chars:
            self._tokens.append(
                self._make_token(TokenType.FSTRING_TEXT, "".join(chars), start_line, start_col)
            )

    def _scan_fstring_expr(self) -> None:
        """Scan an expression inside an f-string: '{' tokens... '}'."""
        expr_start_line = self._line
        expr_start_col = self._col
        self._advance()  # consume '{'
        self._tokens.append(
            self._make_token(TokenType.FSTRING_EXPR_START, "{", expr_start_line, expr_start_col)
        )

        brace_depth = 1
        while not self._at_end() and brace_depth > 0:
            ch = self._peek()
            if ch == "{":
                brace_depth += 1
                # Lex the '{' as a regular LBRACE token.
                t_line = self._line
                t_col = self._col
                self._advance()
                self._tokens.append(
                    self._make_token(TokenType.LBRACE, "{", t_line, t_col)
                )
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    # This closes the f-string expression.
                    end_line = self._line
                    end_col = self._col
                    self._advance()
                    self._tokens.append(
                        self._make_token(TokenType.FSTRING_EXPR_END, "}", end_line, end_col)
                    )
                else:
                    t_line = self._line
                    t_col = self._col
                    self._advance()
                    self._tokens.append(
                        self._make_token(TokenType.RBRACE, "}", t_line, t_col)
                    )
            else:
                # Lex one normal token inside the expression.
                self._scan_token()

        if brace_depth > 0:
            raise self._error("unterminated f-string")

    # ------------------------------------------------------------------
    # Character literals
    # ------------------------------------------------------------------

    def _scan_char(self) -> Token:
        start_line = self._line
        start_col = self._col
        self._advance()  # consume opening '\''
        if self._at_end():
            raise self._error("unterminated character literal", start_line, start_col)

        if self._peek() == "\\":
            self._advance()  # consume backslash
            ch = self._scan_escape()
        else:
            ch = self._advance()

        if self._at_end() or self._peek() != "'":
            raise self._error("unterminated character literal", start_line, start_col)
        self._advance()  # consume closing '\''
        return self._make_token(TokenType.CHAR_LIT, ch, start_line, start_col)

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def _scan_comment(self) -> Token:
        start_line = self._line
        start_col = self._col
        start_pos = self._pos
        self._advance()  # consume first '/'
        self._advance()  # consume second '/'
        while not self._at_end() and self._peek() != "\n":
            self._advance()
        text = self._source[start_pos:self._pos]
        return self._make_token(TokenType.COMMENT, text, start_line, start_col)

    # ------------------------------------------------------------------
    # Operators and punctuation
    # ------------------------------------------------------------------

    def _scan_operator_or_punctuation(self) -> Token:
        """Try multi-character operators (maximal munch), then single-character tokens."""
        start_line = self._line
        start_col = self._col
        ch = self._peek()

        # Three-character operators.
        if ch == "=" and self._check("==="):
            self._advance()
            self._advance()
            self._advance()
            return self._make_token(TokenType.TRIPLE_EQ, "===", start_line, start_col)

        # The <:( parallel fanout (3 chars).
        if ch == "<" and self._check("<:("):
            self._advance()
            self._advance()
            self._advance()
            return self._make_token(TokenType.PARALLEL_FANOUT, "<:(", start_line, start_col)

        # Two-character operators.
        two_char_ops: list[tuple[str, TokenType]] = [
            ("==", TokenType.DOUBLE_EQ),
            ("!=", TokenType.NOT_EQ),
            ("<=", TokenType.LT_EQ),
            (">=", TokenType.GT_EQ),
            ("->", TokenType.ARROW),
            ("=>", TokenType.FAT_ARROW),
            ("++", TokenType.INCREMENT),
            ("--", TokenType.DECREMENT),
            ("**", TokenType.DOUBLE_STAR),
            ("</", TokenType.FLOOR_DIV),
            ("??", TokenType.DOUBLE_QUESTION),
            ("&&", TokenType.AND),
            ("||", TokenType.OR),
            ("..", TokenType.SPREAD),
            (":<", TokenType.COROUTINE),
            ("+=", TokenType.PLUS_ASSIGN),
            ("-=", TokenType.MINUS_ASSIGN),
            ("*=", TokenType.STAR_ASSIGN),
            ("/=", TokenType.SLASH_ASSIGN),
        ]
        for op, ttype in two_char_ops:
            if ch == op[0] and self._check(op):
                self._advance()
                self._advance()
                return self._make_token(ttype, op, start_line, start_col)

        # Single-character tokens.
        single_char_ops: dict[str, TokenType] = {
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
            "/": TokenType.SLASH,
            "%": TokenType.PERCENT,
            "<": TokenType.LT,
            ">": TokenType.GT,
            "(": TokenType.LPAREN,
            ")": TokenType.RPAREN,
            "{": TokenType.LBRACE,
            "}": TokenType.RBRACE,
            "[": TokenType.LBRACKET,
            "]": TokenType.RBRACKET,
            ":": TokenType.COLON,
            ",": TokenType.COMMA,
            ".": TokenType.DOT,
            "|": TokenType.PIPE,
            "?": TokenType.QUESTION,
            "=": TokenType.ASSIGN,
            "!": TokenType.BANG,
            "@": TokenType.AT,
            "&": TokenType.AMPERSAND,
            "\\": TokenType.BACKSLASH,
        }
        if ch in single_char_ops:
            self._advance()
            return self._make_token(single_char_ops[ch], ch, start_line, start_col)

        raise self._error(f"unexpected character '{ch}'")

    # ------------------------------------------------------------------
    # Main scan loop
    # ------------------------------------------------------------------

    def _scan_token(self) -> None:
        """Scan a single token and append it to self._tokens."""
        ch = self._peek()

        # Whitespace (not newline).
        if ch in (" ", "\t", "\r"):
            self._advance()
            return

        # Newline.
        if ch == "\n":
            line = self._line
            col = self._col
            self._advance()
            self._tokens.append(self._make_token(TokenType.NEWLINE, "\n", line, col))
            return

        # Comment: '//' to end of line.
        if ch == "/" and self._peek(1) == "/":
            tok = self._scan_comment()
            self._tokens.append(tok)
            # Don't emit a separate NEWLINE for comment-only lines:
            # the comment runs to end-of-line, so if there's a newline
            # right after, consume it silently.
            if not self._at_end() and self._peek() == "\n":
                self._advance()
            return

        # F-string: 'f' followed by '"'.
        if ch == "f" and self._peek(1) == '"':
            self._scan_fstring()
            return

        # Identifier / keyword.
        if ch.isalpha() or ch == "_":
            self._tokens.append(self._scan_identifier())
            return

        # Numeric literal.
        if ch.isdigit():
            self._tokens.append(self._scan_number())
            return

        # String literal.
        if ch == '"':
            self._tokens.append(self._scan_string())
            return

        # Character literal.
        if ch == "'":
            self._tokens.append(self._scan_char())
            return

        # Operators and punctuation.
        self._tokens.append(self._scan_operator_or_punctuation())

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source and return the token list (ending with EOF)."""
        while not self._at_end():
            self._scan_token()

        self._tokens.append(
            self._make_token(TokenType.EOF, "", self._line, self._col)
        )
        return self._tokens
