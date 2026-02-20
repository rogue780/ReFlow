# compiler/ast_nodes.py — Dataclass definitions only. No logic, no imports from other compiler modules.

from __future__ import annotations
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------

@dataclass
class ASTNode:
    line: int
    col: int


@dataclass
class TypeExpr(ASTNode):
    pass


@dataclass
class Expr(ASTNode):
    pass


@dataclass
class Stmt(ASTNode):
    pass


@dataclass
class Decl(ASTNode):
    pass


@dataclass
class Pattern(ASTNode):
    pass


# ---------------------------------------------------------------------------
# Type Expression Nodes (RT-3-1-1)
# ---------------------------------------------------------------------------

@dataclass
class NamedType(TypeExpr):
    name: str
    module_path: list[str]       # e.g. ["math", "vector"]


@dataclass
class GenericType(TypeExpr):
    base: TypeExpr
    args: list[TypeExpr]


@dataclass
class OptionType(TypeExpr):      # T?
    inner: TypeExpr


@dataclass
class FnType(TypeExpr):
    params: list[TypeExpr]
    ret: TypeExpr


@dataclass
class TupleType(TypeExpr):
    elements: list[TypeExpr]


@dataclass
class MutType(TypeExpr):         # T:mut
    inner: TypeExpr


@dataclass
class ImutType(TypeExpr):        # T:imut
    inner: TypeExpr


@dataclass
class SumTypeExpr(TypeExpr):
    variants: list[SumVariantExpr]


@dataclass
class SumVariantExpr(ASTNode):
    name: str
    fields: list[tuple[str, TypeExpr]] | None  # None = no payload


# ---------------------------------------------------------------------------
# Expression Nodes (RT-3-2-1)
# ---------------------------------------------------------------------------

@dataclass
class IntLit(Expr):
    value: int
    suffix: str | None           # "i64", "u32", etc.


@dataclass
class FloatLit(Expr):
    value: float
    suffix: str | None


@dataclass
class BoolLit(Expr):
    value: bool


@dataclass
class StringLit(Expr):
    value: str


@dataclass
class FStringExpr(Expr):
    parts: list[str | Expr]      # alternating text and expressions


@dataclass
class CharLit(Expr):
    value: int                   # Unicode scalar


@dataclass
class NoneLit(Expr):
    pass


@dataclass
class Ident(Expr):
    name: str
    module_path: list[str]


@dataclass
class BinOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class UnaryOp(Expr):
    op: str
    operand: Expr


@dataclass
class Call(Expr):
    callee: Expr
    args: list[Expr]


@dataclass
class MethodCall(Expr):
    receiver: Expr
    method: str
    args: list[Expr]


@dataclass
class FieldAccess(Expr):
    receiver: Expr
    field: str


@dataclass
class IndexAccess(Expr):
    receiver: Expr
    index: Expr


@dataclass
class Lambda(Expr):
    params: list[Param]
    body: Expr


@dataclass
class TupleExpr(Expr):
    elements: list[Expr]


@dataclass
class ArrayLit(Expr):
    elements: list[Expr]


@dataclass
class RecordLit(Expr):
    fields: list[tuple[str, Expr]]


@dataclass
class TypeLit(Expr):
    type_name: str
    fields: list[tuple[str, Expr]]
    spread: Expr | None          # ..source


@dataclass
class IfExpr(Expr):
    condition: Expr
    then_branch: Block
    else_branch: Block | IfExpr | None


@dataclass
class MatchExpr(Expr):
    subject: Expr
    arms: list[MatchArm]


@dataclass
class CompositionChain(Expr):
    elements: list[ChainElement]


@dataclass
class ChainElement(ASTNode):
    """A single element in a composition chain — a value or function."""
    expr: Expr


@dataclass
class FanOut(Expr):
    branches: list[ChainElement]
    parallel: bool


@dataclass
class TernaryExpr(Expr):
    condition: Expr
    then_expr: Expr
    else_expr: Expr


@dataclass
class CopyExpr(Expr):            # @expr
    inner: Expr


@dataclass
class SomeExpr(Expr):
    inner: Expr


@dataclass
class OkExpr(Expr):
    inner: Expr


@dataclass
class ErrExpr(Expr):
    inner: Expr


@dataclass
class CoerceExpr(Expr):
    inner: Expr
    target_type: TypeExpr | None  # inferred from context if None


@dataclass
class CastExpr(Expr):
    inner: Expr
    target_type: TypeExpr


@dataclass
class SnapshotExpr(Expr):
    inner: Expr


@dataclass
class PropagateExpr(Expr):       # expr?
    inner: Expr


@dataclass
class NullCoalesce(Expr):        # expr ?? expr
    left: Expr
    right: Expr


@dataclass
class TypeofExpr(Expr):
    inner: Expr


@dataclass
class CoroutineStart(Expr):      # let b :< a(x)
    call: Call


# ---------------------------------------------------------------------------
# Statement Nodes (RT-3-3-1)
# ---------------------------------------------------------------------------

@dataclass
class LetStmt(Stmt):
    name: str
    type_ann: TypeExpr | None
    value: Expr


@dataclass
class AssignStmt(Stmt):
    target: Expr
    value: Expr


@dataclass
class UpdateStmt(Stmt):          # +=, -=, *=, /=, ++, --
    target: Expr
    op: str
    value: Expr | None           # None for ++ and --


@dataclass
class ReturnStmt(Stmt):
    value: Expr | None


@dataclass
class YieldStmt(Stmt):
    value: Expr


@dataclass
class ThrowStmt(Stmt):
    exception: Expr


@dataclass
class BreakStmt(Stmt):
    pass


@dataclass
class ExprStmt(Stmt):
    expr: Expr


@dataclass
class IfStmt(Stmt):
    condition: Expr
    then_branch: Block
    else_branch: Block | IfStmt | None


@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: Block
    finally_block: Block | None


@dataclass
class ForStmt(Stmt):
    var: str
    var_type: TypeExpr | None
    iterable: Expr
    body: Block
    finally_block: Block | None


@dataclass
class MatchStmt(Stmt):
    subject: Expr
    arms: list[MatchArm]


@dataclass
class TryStmt(Stmt):
    body: Block
    retry_blocks: list[RetryBlock]
    catch_blocks: list[CatchBlock]
    finally_block: FinallyBlock | None


@dataclass
class Block(ASTNode):
    stmts: list[Stmt]
    finally_block: Block | None


@dataclass
class MatchArm(ASTNode):
    pattern: Pattern
    body: Expr | Block


@dataclass
class RetryBlock(ASTNode):
    target_fn: str
    exception_var: str
    exception_type: TypeExpr
    attempts: int | None         # None means unlimited
    body: Block


@dataclass
class CatchBlock(ASTNode):
    exception_var: str
    exception_type: TypeExpr
    body: Block


@dataclass
class FinallyBlock(ASTNode):
    exception_var: str | None
    exception_type: TypeExpr | None
    body: Block


# ---------------------------------------------------------------------------
# Pattern Nodes (RT-3-4-1)
# ---------------------------------------------------------------------------

@dataclass
class WildcardPattern(Pattern):
    pass


@dataclass
class LiteralPattern(Pattern):
    value: Expr


@dataclass
class BindPattern(Pattern):
    name: str


@dataclass
class SomePattern(Pattern):
    inner_var: str


@dataclass
class NonePattern(Pattern):
    pass


@dataclass
class OkPattern(Pattern):
    inner_var: str


@dataclass
class ErrPattern(Pattern):
    inner_var: str


@dataclass
class VariantPattern(Pattern):
    variant_name: str
    bindings: list[str]


@dataclass
class TuplePattern(Pattern):
    elements: list[Pattern]


# ---------------------------------------------------------------------------
# Declaration Nodes (RT-3-5-1)
# ---------------------------------------------------------------------------

@dataclass
class ModuleDecl(Decl):
    path: list[str]


@dataclass
class ImportDecl(Decl):
    path: list[str]
    names: list[str] | None      # None = import all
    alias: str | None


@dataclass
class FnDecl(Decl):
    name: str
    type_params: list[str]
    params: list[Param]
    return_type: TypeExpr | None
    body: Block | Expr | None    # None for interface declarations
    is_pure: bool
    is_export: bool
    is_static: bool
    finally_block: Block | None


@dataclass
class Param(ASTNode):
    name: str
    type_ann: TypeExpr


@dataclass
class TypeDecl(Decl):
    name: str
    type_params: list[str]
    fields: list[FieldDecl]
    methods: list[FnDecl]
    constructors: list[ConstructorDecl]
    static_members: list[StaticMemberDecl]
    interfaces: list[str]
    is_export: bool
    is_sum_type: bool
    variants: list[SumVariantDecl]


@dataclass
class FieldDecl(ASTNode):
    name: str
    type_ann: TypeExpr
    is_mut: bool


@dataclass
class ConstructorDecl(ASTNode):
    name: str
    params: list[Param]
    return_type: TypeExpr
    body: Block


@dataclass
class StaticMemberDecl(ASTNode):
    name: str
    type_ann: TypeExpr
    value: Expr | None
    is_mut: bool


@dataclass
class InterfaceDecl(Decl):
    name: str
    type_params: list[str]
    methods: list[FnDecl]
    constructor_sig: ConstructorDecl | None
    is_export: bool


@dataclass
class AliasDecl(Decl):
    name: str
    type_params: list[str]
    target: TypeExpr
    is_export: bool


@dataclass
class SumVariantDecl(ASTNode):
    name: str
    fields: list[tuple[str, TypeExpr]] | None


# ---------------------------------------------------------------------------
# Top-level Module (RT-3-5-1)
# ---------------------------------------------------------------------------

@dataclass
class Module(ASTNode):
    path: list[str]
    imports: list[ImportDecl]
    decls: list[Decl]
    filename: str


# ---------------------------------------------------------------------------
# Identity-based hashing for all AST nodes
# ---------------------------------------------------------------------------
# @dataclass sets __hash__ = None when eq=True and frozen=False.
# The resolver's symbols side map (dict[ASTNode, Symbol]) requires AST nodes
# as dict keys. Restore identity-based hashing on all ASTNode subclasses.

def _restore_ast_hashing() -> None:
    import sys
    mod = sys.modules[__name__]
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and issubclass(obj, ASTNode):
            obj.__hash__ = object.__hash__  # type: ignore[assignment]

_restore_ast_hashing()
del _restore_ast_hashing
