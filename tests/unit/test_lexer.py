"""Unit tests for compiler/lexer.py — RT-2-4-1, RT-2-4-2.

Covers:
  - All keyword token types
  - All multi-character and single-character operator token types
  - Integer, float, string, f-string, and char literals
  - Comments
  - Line/column tracking
  - Multiline source token sequences
  - Error cases: unterminated string, unrecognized character, unterminated char
"""
from __future__ import annotations

import unittest

from compiler.lexer import Lexer, Token, TokenType
from compiler.errors import LexError


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def lex(source: str) -> list[Token]:
    """Lex *source* using the filename 'test.flow'."""
    return Lexer(source, "test.flow").tokenize()


def types(source: str) -> list[TokenType]:
    """Return only the TokenType values for *source*, excluding EOF."""
    return [t.type for t in lex(source) if t.type != TokenType.EOF]


def non_eof(source: str) -> list[Token]:
    """Return all tokens except the trailing EOF."""
    return [t for t in lex(source) if t.type != TokenType.EOF]


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

class TestKeywords(unittest.TestCase):
    """Every reserved keyword produces its dedicated TokenType, not IDENT."""

    KEYWORD_MAP: list[tuple[str, TokenType]] = [
        ("module",      TokenType.MODULE),
        ("import",      TokenType.IMPORT),
        ("export",      TokenType.EXPORT),
        ("as",          TokenType.AS),
        ("alias",       TokenType.ALIAS),
        ("type",        TokenType.TYPE),
        ("typeof",      TokenType.TYPEOF),
        ("mut",         TokenType.MUT),
        ("imut",        TokenType.IMUT),
        ("let",         TokenType.LET),
        ("fn",          TokenType.FN),
        ("return",      TokenType.RETURN),
        ("yield",       TokenType.YIELD),
        ("try",         TokenType.TRY),
        ("retry",       TokenType.RETRY),
        ("catch",       TokenType.CATCH),
        ("finally",     TokenType.FINALLY),
        ("interface",   TokenType.INTERFACE),
        ("fulfills",    TokenType.FULFILLS),
        ("constructor", TokenType.CONSTRUCTOR),
        ("self",        TokenType.SELF),
        ("for",         TokenType.FOR),
        ("in",          TokenType.IN),
        ("while",       TokenType.WHILE),
        ("if",          TokenType.IF),
        ("else",        TokenType.ELSE),
        ("match",       TokenType.MATCH),
        ("none",        TokenType.NONE),
        ("break",       TokenType.BREAK),
        ("static",      TokenType.STATIC),
        ("pure",        TokenType.PURE),
        ("record",      TokenType.RECORD),
        ("some",        TokenType.SOME),
        ("ok",          TokenType.OK),
        ("err",         TokenType.ERR),
        ("coerce",      TokenType.COERCE),
        ("cast",        TokenType.CAST),
        ("throw",       TokenType.THROW),
        ("extern",      TokenType.EXTERN),
        ("true",        TokenType.BOOL_LIT),
        ("false",       TokenType.BOOL_LIT),
    ]

    def _check(self, source: str, expected_type: TokenType) -> None:
        toks = non_eof(source)
        self.assertEqual(len(toks), 1, f"Expected 1 token for {source!r}, got {toks}")
        self.assertEqual(toks[0].type, expected_type)
        self.assertEqual(toks[0].value, source)

    def test_all_keywords(self) -> None:
        for kw, tt in self.KEYWORD_MAP:
            with self.subTest(keyword=kw):
                self._check(kw, tt)

    # Individual keyword tests for clear failure messages
    def test_module(self) -> None:
        self.assertEqual(types("module"), [TokenType.MODULE])

    def test_import(self) -> None:
        self.assertEqual(types("import"), [TokenType.IMPORT])

    def test_export(self) -> None:
        self.assertEqual(types("export"), [TokenType.EXPORT])

    def test_as(self) -> None:
        self.assertEqual(types("as"), [TokenType.AS])

    def test_alias(self) -> None:
        self.assertEqual(types("alias"), [TokenType.ALIAS])

    def test_type(self) -> None:
        self.assertEqual(types("type"), [TokenType.TYPE])

    def test_typeof(self) -> None:
        self.assertEqual(types("typeof"), [TokenType.TYPEOF])

    def test_mut(self) -> None:
        self.assertEqual(types("mut"), [TokenType.MUT])

    def test_imut(self) -> None:
        self.assertEqual(types("imut"), [TokenType.IMUT])

    def test_let(self) -> None:
        self.assertEqual(types("let"), [TokenType.LET])

    def test_fn(self) -> None:
        self.assertEqual(types("fn"), [TokenType.FN])

    def test_return(self) -> None:
        self.assertEqual(types("return"), [TokenType.RETURN])

    def test_yield(self) -> None:
        self.assertEqual(types("yield"), [TokenType.YIELD])

    def test_try(self) -> None:
        self.assertEqual(types("try"), [TokenType.TRY])

    def test_retry(self) -> None:
        self.assertEqual(types("retry"), [TokenType.RETRY])

    def test_catch(self) -> None:
        self.assertEqual(types("catch"), [TokenType.CATCH])

    def test_finally(self) -> None:
        self.assertEqual(types("finally"), [TokenType.FINALLY])

    def test_interface(self) -> None:
        self.assertEqual(types("interface"), [TokenType.INTERFACE])

    def test_fulfills(self) -> None:
        self.assertEqual(types("fulfills"), [TokenType.FULFILLS])

    def test_constructor(self) -> None:
        self.assertEqual(types("constructor"), [TokenType.CONSTRUCTOR])

    def test_self(self) -> None:
        self.assertEqual(types("self"), [TokenType.SELF])

    def test_for(self) -> None:
        self.assertEqual(types("for"), [TokenType.FOR])

    def test_in(self) -> None:
        self.assertEqual(types("in"), [TokenType.IN])

    def test_while(self) -> None:
        self.assertEqual(types("while"), [TokenType.WHILE])

    def test_if(self) -> None:
        self.assertEqual(types("if"), [TokenType.IF])

    def test_else(self) -> None:
        self.assertEqual(types("else"), [TokenType.ELSE])

    def test_match(self) -> None:
        self.assertEqual(types("match"), [TokenType.MATCH])

    def test_none(self) -> None:
        self.assertEqual(types("none"), [TokenType.NONE])

    def test_break(self) -> None:
        self.assertEqual(types("break"), [TokenType.BREAK])

    def test_static(self) -> None:
        self.assertEqual(types("static"), [TokenType.STATIC])

    def test_pure(self) -> None:
        self.assertEqual(types("pure"), [TokenType.PURE])

    def test_record(self) -> None:
        self.assertEqual(types("record"), [TokenType.RECORD])

    def test_some(self) -> None:
        self.assertEqual(types("some"), [TokenType.SOME])

    def test_ok(self) -> None:
        self.assertEqual(types("ok"), [TokenType.OK])

    def test_err(self) -> None:
        self.assertEqual(types("err"), [TokenType.ERR])

    def test_coerce(self) -> None:
        self.assertEqual(types("coerce"), [TokenType.COERCE])

    def test_cast(self) -> None:
        self.assertEqual(types("cast"), [TokenType.CAST])

    def test_snapshot_is_now_ident(self) -> None:
        self.assertEqual(types("snapshot"), [TokenType.IDENT])

    def test_throw(self) -> None:
        self.assertEqual(types("throw"), [TokenType.THROW])

    def test_true_is_bool_lit(self) -> None:
        toks = non_eof("true")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.BOOL_LIT)
        self.assertEqual(toks[0].value, "true")

    def test_false_is_bool_lit(self) -> None:
        toks = non_eof("false")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.BOOL_LIT)
        self.assertEqual(toks[0].value, "false")


class TestKeywordPrefixIsIdent(unittest.TestCase):
    """An identifier that starts with a keyword must be lexed as IDENT, not keyword."""

    def test_module_name_is_ident(self) -> None:
        toks = non_eof("module_name")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[0].value, "module_name")

    def test_let_value_is_ident(self) -> None:
        toks = non_eof("let_value")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_return_code_is_ident(self) -> None:
        toks = non_eof("return_code")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_if_condition_is_ident(self) -> None:
        toks = non_eof("if_condition")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_for_each_is_ident(self) -> None:
        toks = non_eof("for_each")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_true_ish_is_ident(self) -> None:
        toks = non_eof("trueish")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_some_value_is_ident(self) -> None:
        toks = non_eof("some_value")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_keyword_followed_by_digit_is_ident(self) -> None:
        toks = non_eof("let2")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)


# ---------------------------------------------------------------------------
# Multi-character operators
# ---------------------------------------------------------------------------

class TestMultiCharOperators(unittest.TestCase):
    """Each multi-character operator lexes to exactly one token with the right type."""

    def _single(self, source: str, expected: TokenType) -> None:
        toks = non_eof(source)
        self.assertEqual(
            len(toks), 1,
            f"Expected exactly 1 token for {source!r}, got {[str(t) for t in toks]}"
        )
        self.assertEqual(toks[0].type, expected, f"source={source!r}")

    def test_arrow(self) -> None:
        self._single("->", TokenType.ARROW)

    def test_fat_arrow(self) -> None:
        self._single("=>", TokenType.FAT_ARROW)

    def test_parallel_fanout(self) -> None:
        self._single("<:(", TokenType.PARALLEL_FANOUT)

    def test_coroutine(self) -> None:
        self._single(":<", TokenType.COROUTINE)

    def test_pipe(self) -> None:
        self._single("|", TokenType.PIPE)

    def test_question(self) -> None:
        self._single("?", TokenType.QUESTION)

    def test_double_question(self) -> None:
        self._single("??", TokenType.DOUBLE_QUESTION)

    def test_triple_eq(self) -> None:
        self._single("===", TokenType.TRIPLE_EQ)

    def test_double_eq(self) -> None:
        self._single("==", TokenType.DOUBLE_EQ)

    def test_not_eq(self) -> None:
        self._single("!=", TokenType.NOT_EQ)

    def test_assign(self) -> None:
        self._single("=", TokenType.ASSIGN)

    def test_plus_assign(self) -> None:
        self._single("+=", TokenType.PLUS_ASSIGN)

    def test_minus_assign(self) -> None:
        self._single("-=", TokenType.MINUS_ASSIGN)

    def test_star_assign(self) -> None:
        self._single("*=", TokenType.STAR_ASSIGN)

    def test_slash_assign(self) -> None:
        self._single("/=", TokenType.SLASH_ASSIGN)

    def test_increment(self) -> None:
        self._single("++", TokenType.INCREMENT)

    def test_decrement(self) -> None:
        self._single("--", TokenType.DECREMENT)

    def test_double_star(self) -> None:
        self._single("**", TokenType.DOUBLE_STAR)

    def test_floor_div(self) -> None:
        self._single("</", TokenType.FLOOR_DIV)

    def test_spread(self) -> None:
        self._single("..", TokenType.SPREAD)

    def test_and(self) -> None:
        self._single("&&", TokenType.AND)

    def test_or(self) -> None:
        self._single("||", TokenType.OR)

    def test_bang(self) -> None:
        self._single("!", TokenType.BANG)

    def test_at(self) -> None:
        self._single("@", TokenType.AT)

    def test_ampersand(self) -> None:
        self._single("&", TokenType.AMPERSAND)

    def test_backslash(self) -> None:
        self._single("\\", TokenType.BACKSLASH)

    def test_lt_eq(self) -> None:
        self._single("<=", TokenType.LT_EQ)

    def test_gt_eq(self) -> None:
        self._single(">=", TokenType.GT_EQ)


class TestSingleCharOperators(unittest.TestCase):
    """Single-character operators each produce their dedicated token type."""

    def _single(self, ch: str, expected: TokenType) -> None:
        toks = non_eof(ch)
        self.assertEqual(len(toks), 1, f"Expected 1 token for {ch!r}")
        self.assertEqual(toks[0].type, expected, f"source={ch!r}")

    def test_plus(self) -> None:
        self._single("+", TokenType.PLUS)

    def test_minus(self) -> None:
        self._single("-", TokenType.MINUS)

    def test_star(self) -> None:
        self._single("*", TokenType.STAR)

    def test_slash(self) -> None:
        self._single("/", TokenType.SLASH)

    def test_percent(self) -> None:
        self._single("%", TokenType.PERCENT)

    def test_lt(self) -> None:
        self._single("<", TokenType.LT)

    def test_gt(self) -> None:
        self._single(">", TokenType.GT)

    def test_lparen(self) -> None:
        self._single("(", TokenType.LPAREN)

    def test_rparen(self) -> None:
        self._single(")", TokenType.RPAREN)

    def test_lbrace(self) -> None:
        self._single("{", TokenType.LBRACE)

    def test_rbrace(self) -> None:
        self._single("}", TokenType.RBRACE)

    def test_lbracket(self) -> None:
        self._single("[", TokenType.LBRACKET)

    def test_rbracket(self) -> None:
        self._single("]", TokenType.RBRACKET)

    def test_colon(self) -> None:
        self._single(":", TokenType.COLON)

    def test_comma(self) -> None:
        self._single(",", TokenType.COMMA)

    def test_dot(self) -> None:
        self._single(".", TokenType.DOT)


class TestOperatorMaximalMunch(unittest.TestCase):
    """Maximal munch: longer operators win over shorter prefixes."""

    def test_triple_eq_not_double_then_assign(self) -> None:
        # === must be a single TRIPLE_EQ token, not == followed by =
        toks = non_eof("===")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.TRIPLE_EQ)

    def test_double_eq_not_two_assigns(self) -> None:
        toks = non_eof("==")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.DOUBLE_EQ)

    def test_arrow_not_minus_gt(self) -> None:
        toks = non_eof("->")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.ARROW)

    def test_double_question_not_two_questions(self) -> None:
        toks = non_eof("??")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.DOUBLE_QUESTION)

    def test_increment_not_two_plus(self) -> None:
        toks = non_eof("++")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INCREMENT)

    def test_decrement_not_two_minus(self) -> None:
        toks = non_eof("--")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.DECREMENT)

    def test_double_star_not_two_stars(self) -> None:
        toks = non_eof("**")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.DOUBLE_STAR)

    def test_double_slash_is_comment(self) -> None:
        # // is now a comment, not an operator
        toks = non_eof("//")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.COMMENT)

    def test_floor_div_not_lt_then_slash(self) -> None:
        # </ is floor division, a single token
        toks = non_eof("</")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOOR_DIV)

    def test_spread_not_two_dots(self) -> None:
        toks = non_eof("..")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.SPREAD)

    def test_and_not_two_ampersands(self) -> None:
        toks = non_eof("&&")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.AND)

    def test_or_not_two_pipes(self) -> None:
        toks = non_eof("||")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.OR)

    def test_parallel_fanout_not_lt_colon_lparen(self) -> None:
        # <:( is a single token
        toks = non_eof("<:(")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.PARALLEL_FANOUT)

    def test_coroutine_not_colon_lt(self) -> None:
        # :< is COROUTINE
        toks = non_eof(":<")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.COROUTINE)

    def test_minus_gt_separate(self) -> None:
        # "- >" with space: MINUS then GT
        toks = non_eof("- >")
        self.assertEqual(len(toks), 2)
        self.assertEqual(toks[0].type, TokenType.MINUS)
        self.assertEqual(toks[1].type, TokenType.GT)

    def test_arrow_in_expression(self) -> None:
        # a->b without spaces
        toks = non_eof("a->b")
        self.assertEqual(len(toks), 3)
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[1].type, TokenType.ARROW)
        self.assertEqual(toks[2].type, TokenType.IDENT)

    def test_plus_eq_not_plus_assign(self) -> None:
        # Make sure += is a single token, not PLUS then ASSIGN
        toks = non_eof("+=")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.PLUS_ASSIGN)


# ---------------------------------------------------------------------------
# Integer literals
# ---------------------------------------------------------------------------

class TestIntegerLiterals(unittest.TestCase):
    """INT_LIT tokens."""

    def test_simple_integer(self) -> None:
        toks = non_eof("42")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[0].value, "42")

    def test_zero(self) -> None:
        toks = non_eof("0")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[0].value, "0")

    def test_large_integer(self) -> None:
        toks = non_eof("2147483647")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)

    def test_integer_with_underscores(self) -> None:
        # Underscores are stripped from the value per spec: 1_000_000 → "1000000"
        toks = non_eof("1_000_000")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[0].value, "1000000")

    def test_integer_with_single_underscore(self) -> None:
        toks = non_eof("1_000")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[0].value, "1000")

    def test_integer_with_multiple_underscores(self) -> None:
        toks = non_eof("1_000_000_000")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[0].value, "1000000000")

    def test_hex_integer(self) -> None:
        toks = non_eof("0xFF")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[0].value, "0xFF")

    def test_hex_lowercase(self) -> None:
        toks = non_eof("0xff")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)

    def test_hex_zero(self) -> None:
        toks = non_eof("0x0")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)

    def test_hex_all_digits(self) -> None:
        toks = non_eof("0xDEADBEEF")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)


# ---------------------------------------------------------------------------
# Float literals
# ---------------------------------------------------------------------------

class TestFloatLiterals(unittest.TestCase):
    """FLOAT_LIT tokens."""

    def test_simple_float(self) -> None:
        toks = non_eof("3.14")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOAT_LIT)

    def test_float_value(self) -> None:
        toks = non_eof("3.14")
        self.assertEqual(toks[0].value, "3.14")

    def test_float_with_exponent(self) -> None:
        toks = non_eof("1.5e10")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOAT_LIT)

    def test_float_with_negative_exponent(self) -> None:
        toks = non_eof("1.5e-3")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOAT_LIT)

    def test_float_with_positive_exponent_explicit(self) -> None:
        toks = non_eof("2.0e+5")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOAT_LIT)

    def test_float_zero(self) -> None:
        toks = non_eof("0.0")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOAT_LIT)

    def test_float_no_leading_digit_is_dot_then_int(self) -> None:
        # ".5" should NOT be a FLOAT_LIT; it's a DOT followed by INT_LIT
        toks = non_eof(".5")
        self.assertEqual(len(toks), 2)
        self.assertEqual(toks[0].type, TokenType.DOT)
        self.assertEqual(toks[1].type, TokenType.INT_LIT)

    def test_float_vs_int_dot_ident(self) -> None:
        # "3.x" should be INT_LIT, DOT, IDENT — not a float
        toks = non_eof("3.x")
        self.assertEqual(len(toks), 3)
        self.assertEqual(toks[0].type, TokenType.INT_LIT)
        self.assertEqual(toks[1].type, TokenType.DOT)
        self.assertEqual(toks[2].type, TokenType.IDENT)

    def test_float_uppercase_e_exponent(self) -> None:
        toks = non_eof("1.0E5")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.FLOAT_LIT)


# ---------------------------------------------------------------------------
# String literals
# ---------------------------------------------------------------------------

class TestStringLiterals(unittest.TestCase):
    """STRING_LIT tokens with escape handling."""

    def test_simple_string(self) -> None:
        toks = non_eof('"hello"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "hello")

    def test_empty_string(self) -> None:
        toks = non_eof('""')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "")

    def test_string_with_newline_escape(self) -> None:
        toks = non_eof(r'"hello\nworld"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "hello\nworld")

    def test_string_with_tab_escape(self) -> None:
        toks = non_eof(r'"col1\tcol2"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "col1\tcol2")

    def test_string_with_backslash_escape(self) -> None:
        toks = non_eof(r'"path\\to"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "path\\to")

    def test_string_with_quote_escape(self) -> None:
        toks = non_eof(r'"say \"hi\""')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, 'say "hi"')

    def test_string_with_unicode_escape(self) -> None:
        # \u{41} is 'A'
        toks = non_eof(r'"\u{41}"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "A")

    def test_string_with_unicode_escape_multibyte(self) -> None:
        # \u{1F600} is the emoji 😀 (U+1F600)
        toks = non_eof(r'"\u{1F600}"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "\U0001F600")

    def test_string_with_multiple_escapes(self) -> None:
        toks = non_eof(r'"line1\nline2\ttabbed"')
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.STRING_LIT)
        self.assertEqual(toks[0].value, "line1\nline2\ttabbed")

    def test_string_position(self) -> None:
        toks = non_eof('"hello"')
        self.assertEqual(toks[0].line, 1)
        self.assertEqual(toks[0].col, 1)


# ---------------------------------------------------------------------------
# F-string literals
# ---------------------------------------------------------------------------

class TestFStringLiterals(unittest.TestCase):
    """F-string token sequences: FSTRING_START ... FSTRING_END."""

    def test_simple_fstring_no_expressions(self) -> None:
        # f"hello" → FSTRING_START, FSTRING_TEXT("hello"), FSTRING_END
        toks = non_eof('f"hello"')
        self.assertEqual(len(toks), 3)
        self.assertEqual(toks[0].type, TokenType.FSTRING_START)
        self.assertEqual(toks[1].type, TokenType.FSTRING_TEXT)
        self.assertEqual(toks[1].value, "hello")
        self.assertEqual(toks[2].type, TokenType.FSTRING_END)

    def test_fstring_single_expression(self) -> None:
        # f"hello {name}" → START, TEXT("hello "), EXPR_START, IDENT(name), EXPR_END, END
        toks = non_eof('f"hello {name}"')
        self.assertEqual(toks[0].type, TokenType.FSTRING_START)
        self.assertEqual(toks[1].type, TokenType.FSTRING_TEXT)
        self.assertEqual(toks[1].value, "hello ")
        self.assertEqual(toks[2].type, TokenType.FSTRING_EXPR_START)
        self.assertEqual(toks[3].type, TokenType.IDENT)
        self.assertEqual(toks[3].value, "name")
        self.assertEqual(toks[4].type, TokenType.FSTRING_EXPR_END)
        self.assertEqual(toks[5].type, TokenType.FSTRING_END)

    def test_fstring_expression_only(self) -> None:
        # f"{x}" → START, EXPR_START, IDENT(x), EXPR_END, END
        toks = non_eof('f"{x}"')
        self.assertEqual(toks[0].type, TokenType.FSTRING_START)
        self.assertEqual(toks[1].type, TokenType.FSTRING_EXPR_START)
        self.assertEqual(toks[2].type, TokenType.IDENT)
        self.assertEqual(toks[2].value, "x")
        self.assertEqual(toks[3].type, TokenType.FSTRING_EXPR_END)
        self.assertEqual(toks[4].type, TokenType.FSTRING_END)

    def test_fstring_trailing_text(self) -> None:
        # f"{x} end" → START, EXPR_START, IDENT, EXPR_END, TEXT(" end"), END
        toks = non_eof('f"{x} end"')
        self.assertEqual(toks[0].type, TokenType.FSTRING_START)
        self.assertEqual(toks[1].type, TokenType.FSTRING_EXPR_START)
        self.assertEqual(toks[2].type, TokenType.IDENT)
        self.assertEqual(toks[3].type, TokenType.FSTRING_EXPR_END)
        self.assertEqual(toks[4].type, TokenType.FSTRING_TEXT)
        self.assertEqual(toks[4].value, " end")
        self.assertEqual(toks[5].type, TokenType.FSTRING_END)

    def test_fstring_multiple_expressions(self) -> None:
        # f"{a} and {b}"
        toks = non_eof('f"{a} and {b}"')
        ttypes = [t.type for t in toks]
        self.assertEqual(ttypes[0], TokenType.FSTRING_START)
        self.assertEqual(ttypes[1], TokenType.FSTRING_EXPR_START)
        self.assertEqual(ttypes[2], TokenType.IDENT)    # a
        self.assertEqual(ttypes[3], TokenType.FSTRING_EXPR_END)
        self.assertEqual(ttypes[4], TokenType.FSTRING_TEXT)    # " and "
        self.assertEqual(toks[4].value, " and ")
        self.assertEqual(ttypes[5], TokenType.FSTRING_EXPR_START)
        self.assertEqual(ttypes[6], TokenType.IDENT)    # b
        self.assertEqual(ttypes[7], TokenType.FSTRING_EXPR_END)
        self.assertEqual(ttypes[8], TokenType.FSTRING_END)

    def test_fstring_nested_braces_in_expression(self) -> None:
        # f"{func({x})}" — inner {} in the expression should not end the f-string expr
        # Expected: START, EXPR_START, IDENT(func), LPAREN, LBRACE, IDENT(x), RBRACE, RPAREN, EXPR_END, END
        toks = non_eof('f"{func({x})}"')
        self.assertEqual(toks[0].type, TokenType.FSTRING_START)
        self.assertEqual(toks[1].type, TokenType.FSTRING_EXPR_START)
        # The expression tokens: func, (, {, x, }, )
        ident_tok = toks[2]
        self.assertEqual(ident_tok.type, TokenType.IDENT)
        self.assertEqual(ident_tok.value, "func")
        self.assertEqual(toks[3].type, TokenType.LPAREN)
        self.assertEqual(toks[4].type, TokenType.LBRACE)
        self.assertEqual(toks[5].type, TokenType.IDENT)
        self.assertEqual(toks[5].value, "x")
        self.assertEqual(toks[6].type, TokenType.RBRACE)
        self.assertEqual(toks[7].type, TokenType.RPAREN)
        # After the depth drops back to 0, FSTRING_EXPR_END
        self.assertEqual(toks[8].type, TokenType.FSTRING_EXPR_END)
        self.assertEqual(toks[9].type, TokenType.FSTRING_END)

    def test_fstring_expression_with_arithmetic(self) -> None:
        # f"{a + b}"
        toks = non_eof('f"{a + b}"')
        self.assertEqual(toks[0].type, TokenType.FSTRING_START)
        self.assertEqual(toks[1].type, TokenType.FSTRING_EXPR_START)
        self.assertEqual(toks[2].type, TokenType.IDENT)   # a
        self.assertEqual(toks[3].type, TokenType.PLUS)
        self.assertEqual(toks[4].type, TokenType.IDENT)   # b
        self.assertEqual(toks[5].type, TokenType.FSTRING_EXPR_END)
        self.assertEqual(toks[6].type, TokenType.FSTRING_END)

    def test_fstring_empty_text_between_expressions(self) -> None:
        # f"{a}{b}" — no text between expressions
        toks = non_eof('f"{a}{b}"')
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.FSTRING_START, ttypes)
        self.assertIn(TokenType.FSTRING_END, ttypes)
        # Both expressions should be present
        expr_starts = [t for t in toks if t.type == TokenType.FSTRING_EXPR_START]
        expr_ends = [t for t in toks if t.type == TokenType.FSTRING_EXPR_END]
        self.assertEqual(len(expr_starts), 2)
        self.assertEqual(len(expr_ends), 2)

    def test_fstring_empty_string(self) -> None:
        # f"" → START, END  (no text token since there's nothing)
        toks = non_eof('f""')
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.FSTRING_START, ttypes)
        self.assertIn(TokenType.FSTRING_END, ttypes)


# ---------------------------------------------------------------------------
# Character literals
# ---------------------------------------------------------------------------

class TestCharLiterals(unittest.TestCase):
    """CHAR_LIT tokens."""

    def test_simple_char(self) -> None:
        toks = non_eof("'a'")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)

    def test_char_value(self) -> None:
        toks = non_eof("'z'")
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)
        self.assertEqual(toks[0].value, "z")

    def test_char_digit(self) -> None:
        toks = non_eof("'9'")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)

    def test_char_newline_escape(self) -> None:
        toks = non_eof(r"'\n'")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)
        self.assertEqual(toks[0].value, "\n")

    def test_char_tab_escape(self) -> None:
        toks = non_eof(r"'\t'")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)
        self.assertEqual(toks[0].value, "\t")

    def test_char_backslash_escape(self) -> None:
        toks = non_eof(r"'\\'")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)
        self.assertEqual(toks[0].value, "\\")

    def test_char_unicode_escape(self) -> None:
        # '\u{41}' → 'A'
        toks = non_eof(r"'\u{41}'")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)
        self.assertEqual(toks[0].value, "A")

    def test_char_space(self) -> None:
        toks = non_eof("' '")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.CHAR_LIT)
        self.assertEqual(toks[0].value, " ")


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class TestComments(unittest.TestCase):
    """Double-slash starts a comment running to end of line."""

    def test_standalone_comment(self) -> None:
        toks = non_eof("// this is a comment")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.COMMENT)

    def test_comment_value_contains_text(self) -> None:
        toks = non_eof("// hello world")
        self.assertEqual(toks[0].type, TokenType.COMMENT)
        # Value should include everything after the //
        self.assertIn("hello world", toks[0].value)

    def test_comment_after_code(self) -> None:
        toks = non_eof("let x // this is a comment")
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.LET, ttypes)
        self.assertIn(TokenType.IDENT, ttypes)
        self.assertIn(TokenType.COMMENT, ttypes)
        # LET then IDENT then COMMENT
        non_eof_toks = toks
        self.assertEqual(non_eof_toks[0].type, TokenType.LET)
        self.assertEqual(non_eof_toks[1].type, TokenType.IDENT)
        self.assertEqual(non_eof_toks[1].value, "x")
        self.assertEqual(non_eof_toks[2].type, TokenType.COMMENT)

    def test_comment_then_next_line_code(self) -> None:
        src = "// first line comment\nlet y"
        toks = non_eof(src)
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.COMMENT, ttypes)
        self.assertIn(TokenType.LET, ttypes)
        self.assertIn(TokenType.IDENT, ttypes)

    def test_empty_comment(self) -> None:
        toks = non_eof("//")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.COMMENT)

    def test_decorative_comment(self) -> None:
        # //===================
        toks = non_eof("//===================")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.COMMENT)


# ---------------------------------------------------------------------------
# Line and column tracking
# ---------------------------------------------------------------------------

class TestLineColumnTracking(unittest.TestCase):
    """Token positions are accurate."""

    def test_first_token_line_and_col(self) -> None:
        toks = non_eof("let")
        self.assertEqual(toks[0].line, 1)
        self.assertEqual(toks[0].col, 1)

    def test_second_token_col(self) -> None:
        toks = non_eof("let x")
        # "let" is at col 1; "x" follows a space, so col 5
        self.assertEqual(toks[0].col, 1)
        self.assertEqual(toks[1].col, 5)

    def test_second_line_token(self) -> None:
        toks = non_eof("let\nx")
        # x is on line 2
        x_tok = next(t for t in toks if t.type == TokenType.IDENT)
        self.assertEqual(x_tok.line, 2)
        self.assertEqual(x_tok.col, 1)

    def test_col_resets_on_newline(self) -> None:
        toks = non_eof("abc\ndef")
        abc_tok = toks[0]
        def_tok = toks[-1]
        self.assertEqual(abc_tok.col, 1)
        self.assertEqual(def_tok.col, 1)

    def test_operator_position(self) -> None:
        toks = non_eof("a + b")
        plus_tok = next(t for t in toks if t.type == TokenType.PLUS)
        self.assertEqual(plus_tok.line, 1)
        self.assertEqual(plus_tok.col, 3)

    def test_string_position(self) -> None:
        toks = non_eof('  "hi"')
        str_tok = next(t for t in toks if t.type == TokenType.STRING_LIT)
        self.assertEqual(str_tok.col, 3)

    def test_multiline_col_and_line(self) -> None:
        src = "let a = 1\nlet b = 2"
        toks = non_eof(src)
        # Find the second LET token
        let_toks = [t for t in toks if t.type == TokenType.LET]
        self.assertEqual(len(let_toks), 2)
        self.assertEqual(let_toks[0].line, 1)
        self.assertEqual(let_toks[1].line, 2)
        self.assertEqual(let_toks[1].col, 1)


# ---------------------------------------------------------------------------
# EOF token
# ---------------------------------------------------------------------------

class TestEOFToken(unittest.TestCase):
    """The tokenize result always ends with EOF."""

    def test_empty_source_gives_eof(self) -> None:
        toks = lex("")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.EOF)

    def test_non_empty_source_ends_with_eof(self) -> None:
        toks = lex("let x = 42")
        self.assertEqual(toks[-1].type, TokenType.EOF)

    def test_eof_value(self) -> None:
        toks = lex("")
        # Value of EOF token should be empty string or ""
        self.assertEqual(toks[0].value, "")


# ---------------------------------------------------------------------------
# Identifier tokens
# ---------------------------------------------------------------------------

class TestIdentifiers(unittest.TestCase):
    """IDENT tokens."""

    def test_simple_ident(self) -> None:
        toks = non_eof("foo")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[0].value, "foo")

    def test_underscore_leading_ident(self) -> None:
        toks = non_eof("_internal")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_underscore_only_ident(self) -> None:
        toks = non_eof("_")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_ident_with_digits(self) -> None:
        toks = non_eof("x1")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[0].value, "x1")

    def test_camel_case_ident(self) -> None:
        toks = non_eof("MyType")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)

    def test_ident_filename_field(self) -> None:
        toks = non_eof("foo")
        self.assertEqual(toks[0].file, "test.flow")


# ---------------------------------------------------------------------------
# Multiline source programs
# ---------------------------------------------------------------------------

class TestMultilineSource(unittest.TestCase):
    """Multi-line programs produce the expected token sequence."""

    def test_simple_function_declaration(self) -> None:
        src = "fn add(x: int, y: int): int"
        toks = non_eof(src)
        ttypes = [t.type for t in toks]
        self.assertEqual(ttypes[0], TokenType.FN)
        self.assertEqual(ttypes[1], TokenType.IDENT)  # add
        self.assertEqual(ttypes[2], TokenType.LPAREN)
        self.assertEqual(ttypes[3], TokenType.IDENT)  # x
        self.assertEqual(ttypes[4], TokenType.COLON)
        self.assertEqual(ttypes[5], TokenType.IDENT)  # int (IDENT not keyword per plan)

    def test_let_binding(self) -> None:
        src = "let x = 42"
        toks = non_eof(src)
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.LET, ttypes)
        self.assertIn(TokenType.IDENT, ttypes)
        self.assertIn(TokenType.ASSIGN, ttypes)
        self.assertIn(TokenType.INT_LIT, ttypes)

    def test_module_declaration(self) -> None:
        src = "module math.vector"
        toks = non_eof(src)
        self.assertEqual(toks[0].type, TokenType.MODULE)
        self.assertEqual(toks[1].type, TokenType.IDENT)  # math
        self.assertEqual(toks[2].type, TokenType.DOT)
        self.assertEqual(toks[3].type, TokenType.IDENT)  # vector

    def test_import_declaration(self) -> None:
        src = "import math.vector as vec"
        toks = non_eof(src)
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.IMPORT, ttypes)
        self.assertIn(TokenType.AS, ttypes)

    def test_multiline_program_token_count(self) -> None:
        src = (
            "module main\n"
            "import io\n"
            "fn greet(name: string): string {\n"
            '    return f"hello {name}"\n'
            "}"
        )
        toks = lex(src)
        # Just verify it lexes without error and has a reasonable number of tokens
        self.assertGreater(len(toks), 10)
        self.assertEqual(toks[-1].type, TokenType.EOF)

    def test_multiline_assigns_correct_lines(self) -> None:
        src = "let a = 1\nlet b = 2\nlet c = 3"
        toks = non_eof(src)
        let_toks = [t for t in toks if t.type == TokenType.LET]
        self.assertEqual(let_toks[0].line, 1)
        self.assertEqual(let_toks[1].line, 2)
        self.assertEqual(let_toks[2].line, 3)

    def test_operator_sequence_without_spaces(self) -> None:
        # x+y → IDENT, PLUS, IDENT (no spaces required)
        toks = non_eof("x+y")
        self.assertEqual(len(toks), 3)
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[0].value, "x")
        self.assertEqual(toks[1].type, TokenType.PLUS)
        self.assertEqual(toks[2].type, TokenType.IDENT)
        self.assertEqual(toks[2].value, "y")

    def test_complex_expression_tokens(self) -> None:
        # a + b * c - d
        toks = non_eof("a + b * c - d")
        ttypes = [t.type for t in toks]
        self.assertEqual(ttypes, [
            TokenType.IDENT,
            TokenType.PLUS,
            TokenType.IDENT,
            TokenType.STAR,
            TokenType.IDENT,
            TokenType.MINUS,
            TokenType.IDENT,
        ])

    def test_comparison_expression(self) -> None:
        toks = non_eof("x <= y && y >= z")
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.LT_EQ, ttypes)
        self.assertIn(TokenType.AND, ttypes)
        self.assertIn(TokenType.GT_EQ, ttypes)

    def test_composition_chain(self) -> None:
        toks = non_eof("data -> filter -> map")
        ttypes = [t.type for t in toks]
        self.assertEqual(ttypes, [
            TokenType.IDENT,
            TokenType.ARROW,
            TokenType.IDENT,
            TokenType.ARROW,
            TokenType.IDENT,
        ])

    def test_option_type_expression(self) -> None:
        toks = non_eof("x ?? default")
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.DOUBLE_QUESTION, ttypes)


# ---------------------------------------------------------------------------
# Whitespace handling
# ---------------------------------------------------------------------------

class TestWhitespace(unittest.TestCase):
    """Whitespace is skipped (unless it's a newline that counts as NEWLINE)."""

    def test_spaces_between_tokens(self) -> None:
        toks = non_eof("  let   x  ")
        non_newline = [t for t in toks if t.type not in (TokenType.NEWLINE,)]
        ttypes = [t.type for t in non_newline]
        self.assertIn(TokenType.LET, ttypes)
        self.assertIn(TokenType.IDENT, ttypes)

    def test_tabs_between_tokens(self) -> None:
        toks = non_eof("let\tx")
        ttypes = [t.type for t in toks]
        self.assertIn(TokenType.LET, ttypes)
        self.assertIn(TokenType.IDENT, ttypes)


# ---------------------------------------------------------------------------
# Error cases (RT-2-4-2)
# ---------------------------------------------------------------------------

class TestLexErrors(unittest.TestCase):
    """Error conditions must raise LexError with populated fields."""

    def test_unterminated_string_raises_lex_error(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex('"hello')
        err = ctx.exception
        self.assertIsInstance(err, LexError)

    def test_unterminated_string_message_contains_unterminated(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex('"hello')
        self.assertIn("unterminated", ctx.exception.message.lower())

    def test_unterminated_string_has_file(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex('"hello')
        self.assertEqual(ctx.exception.file, "test.flow")

    def test_unterminated_string_has_line(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex('"hello')
        self.assertIsInstance(ctx.exception.line, int)
        self.assertGreater(ctx.exception.line, 0)

    def test_unterminated_string_has_col(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex('"hello')
        self.assertIsInstance(ctx.exception.col, int)
        self.assertGreater(ctx.exception.col, 0)

    def test_unrecognized_character_backtick(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex("`")
        self.assertIsInstance(ctx.exception, LexError)

    def test_unrecognized_character_message(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex("`")
        msg = ctx.exception.message.lower()
        # Message should mention "unexpected" or "unrecognized" and the character
        self.assertTrue(
            "unexpected" in msg or "unrecognized" in msg or "unknown" in msg,
            f"Expected error message to mention unexpected character, got: {msg!r}"
        )

    def test_unrecognized_character_has_file(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex("`")
        self.assertEqual(ctx.exception.file, "test.flow")

    def test_unrecognized_character_has_position(self) -> None:
        with self.assertRaises(LexError) as ctx:
            lex("`")
        self.assertGreater(ctx.exception.line, 0)
        self.assertGreater(ctx.exception.col, 0)

    def test_unrecognized_character_dollar_sign(self) -> None:
        with self.assertRaises(LexError):
            lex("$x")

    def test_unrecognized_character_hash(self) -> None:
        # '#' is not a valid Flow token start
        with self.assertRaises(LexError):
            lex("#define")

    def test_unterminated_char_literal_multichar(self) -> None:
        # 'ab' is malformed — char literal is exactly one character
        with self.assertRaises(LexError):
            lex("'ab")

    def test_unterminated_char_literal_eof(self) -> None:
        # Char literal that never closes
        with self.assertRaises(LexError):
            lex("'a")

    def test_unterminated_string_on_second_line(self) -> None:
        # Error occurs on line 2
        with self.assertRaises(LexError) as ctx:
            lex('let x = 1\n"unterminated')
        self.assertEqual(ctx.exception.line, 2)

    def test_fstring_unmatched_brace_raises_lex_error(self) -> None:
        # f"{" with no closing brace or quote
        with self.assertRaises(LexError):
            lex('f"hello {name"')

    def test_unrecognized_char_col_is_accurate(self) -> None:
        # Backtick at column 5 (after "let ")
        with self.assertRaises(LexError) as ctx:
            lex("let `x")
        # col should be 5 (1-indexed)
        self.assertEqual(ctx.exception.col, 5)

    def test_unrecognized_char_line_is_accurate(self) -> None:
        # Backtick on line 3
        with self.assertRaises(LexError) as ctx:
            lex("let a = 1\nlet b = 2\n`")
        self.assertEqual(ctx.exception.line, 3)


# ---------------------------------------------------------------------------
# Token dataclass fields
# ---------------------------------------------------------------------------

class TestTokenDataclass(unittest.TestCase):
    """Token dataclass must have type, value, line, col, file fields."""

    def test_token_has_type_field(self) -> None:
        tok = non_eof("let")[0]
        self.assertIsInstance(tok.type, TokenType)

    def test_token_has_value_field(self) -> None:
        tok = non_eof("let")[0]
        self.assertIsInstance(tok.value, str)

    def test_token_has_line_field(self) -> None:
        tok = non_eof("let")[0]
        self.assertIsInstance(tok.line, int)

    def test_token_has_col_field(self) -> None:
        tok = non_eof("let")[0]
        self.assertIsInstance(tok.col, int)

    def test_token_has_file_field(self) -> None:
        tok = non_eof("let")[0]
        self.assertIsInstance(tok.file, str)
        self.assertEqual(tok.file, "test.flow")

    def test_keyword_value_matches_source(self) -> None:
        tok = non_eof("module")[0]
        self.assertEqual(tok.value, "module")

    def test_ident_value_matches_source(self) -> None:
        tok = non_eof("fooBar")[0]
        self.assertEqual(tok.value, "fooBar")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_empty_source_single_eof(self) -> None:
        toks = lex("")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.EOF)

    def test_only_whitespace_gives_eof(self) -> None:
        toks = lex("   \t  ")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.EOF)

    def test_only_comment_gives_comment_and_eof(self) -> None:
        toks = lex("// just a comment")
        non_eof_toks = [t for t in toks if t.type != TokenType.EOF]
        self.assertEqual(len(non_eof_toks), 1)
        self.assertEqual(non_eof_toks[0].type, TokenType.COMMENT)

    def test_tokens_without_spaces(self) -> None:
        # let+42 — LET, PLUS, INT_LIT
        toks = non_eof("let+42")
        self.assertEqual(toks[0].type, TokenType.LET)
        self.assertEqual(toks[1].type, TokenType.PLUS)
        self.assertEqual(toks[2].type, TokenType.INT_LIT)

    def test_arrow_distinguished_from_minus_and_gt(self) -> None:
        # "a->b" is IDENT ARROW IDENT
        toks = non_eof("a->b")
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[1].type, TokenType.ARROW)
        self.assertEqual(toks[2].type, TokenType.IDENT)

    def test_minus_space_gt_is_not_arrow(self) -> None:
        # "a - >b" is IDENT MINUS GT IDENT
        toks = non_eof("a - >b")
        self.assertEqual(toks[1].type, TokenType.MINUS)
        self.assertEqual(toks[2].type, TokenType.GT)

    def test_spread_not_two_field_accesses(self) -> None:
        toks = non_eof("..src")
        self.assertEqual(toks[0].type, TokenType.SPREAD)
        self.assertEqual(toks[1].type, TokenType.IDENT)

    def test_dot_then_ident(self) -> None:
        toks = non_eof(".field")
        self.assertEqual(toks[0].type, TokenType.DOT)
        self.assertEqual(toks[1].type, TokenType.IDENT)

    def test_two_dots_then_ident(self) -> None:
        # ..x is SPREAD then IDENT
        toks = non_eof("..x")
        self.assertEqual(toks[0].type, TokenType.SPREAD)
        self.assertEqual(toks[1].type, TokenType.IDENT)

    def test_three_dots_is_spread_then_dot(self) -> None:
        # ...x is SPREAD DOT IDENT (maximal munch takes two dots as SPREAD)
        toks = non_eof("...x")
        self.assertEqual(toks[0].type, TokenType.SPREAD)
        self.assertEqual(toks[1].type, TokenType.DOT)
        self.assertEqual(toks[2].type, TokenType.IDENT)

    def test_lexer_filename_stored_on_tokens(self) -> None:
        toks = Lexer("let x", "myfile.flow").tokenize()
        for t in toks:
            self.assertEqual(t.file, "myfile.flow")

    def test_integer_immediately_after_keyword(self) -> None:
        # fn42 is an IDENT, not FN followed by INT_LIT
        toks = non_eof("fn42")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[0].value, "fn42")

    def test_consecutive_int_literals(self) -> None:
        toks = non_eof("1 2 3")
        ttypes = [t.type for t in toks]
        self.assertEqual(ttypes, [TokenType.INT_LIT, TokenType.INT_LIT, TokenType.INT_LIT])

    def test_mixed_operators_no_spaces(self) -> None:
        # a+=b -= c — should be: IDENT PLUS_ASSIGN IDENT MINUS_ASSIGN IDENT
        toks = non_eof("a+=b-=c")
        self.assertEqual(toks[0].type, TokenType.IDENT)
        self.assertEqual(toks[1].type, TokenType.PLUS_ASSIGN)
        self.assertEqual(toks[2].type, TokenType.IDENT)
        self.assertEqual(toks[3].type, TokenType.MINUS_ASSIGN)
        self.assertEqual(toks[4].type, TokenType.IDENT)

    def test_bool_lit_followed_by_operator(self) -> None:
        toks = non_eof("true && false")
        self.assertEqual(toks[0].type, TokenType.BOOL_LIT)
        self.assertEqual(toks[0].value, "true")
        self.assertEqual(toks[1].type, TokenType.AND)
        self.assertEqual(toks[2].type, TokenType.BOOL_LIT)
        self.assertEqual(toks[2].value, "false")

    def test_question_mark_vs_double_question(self) -> None:
        # Maximal munch: ?? wins over ?
        toks = non_eof("??")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.DOUBLE_QUESTION)

    def test_single_question_mark(self) -> None:
        toks = non_eof("?")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.QUESTION)

    def test_not_eq_vs_bang_then_assign(self) -> None:
        # != is NOT_EQ, not BANG then ASSIGN
        toks = non_eof("!=")
        self.assertEqual(len(toks), 1)
        self.assertEqual(toks[0].type, TokenType.NOT_EQ)

    def test_bang_then_ident(self) -> None:
        # !x is BANG then IDENT
        toks = non_eof("!x")
        self.assertEqual(toks[0].type, TokenType.BANG)
        self.assertEqual(toks[1].type, TokenType.IDENT)


if __name__ == "__main__":
    unittest.main()
