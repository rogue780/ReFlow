# compiler/resolver.py — Binds names to Symbol objects.
# No type inference.
#
# Implements RT-5-1-1 through RT-5-3-4.
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from compiler.errors import ResolveError
from compiler.ast_nodes import (
    # Base
    ASTNode, TypeExpr, Expr, Stmt, Decl, Pattern,
    # Type expressions
    NamedType, GenericType, OptionType, FnType, TupleType,
    MutType, ImutType, SizedType, SumTypeExpr, SumVariantExpr,
    # Expressions
    IntLit, FloatLit, BoolLit, StringLit, FStringExpr, CharLit, NoneLit,
    Ident, BinOp, UnaryOp, Call, MethodCall, FieldAccess, IndexAccess,
    Lambda, TupleExpr, ArrayLit, RecordLit, TypeLit, IfExpr, MatchExpr,
    CompositionChain, ChainElement, FanOut, TernaryExpr, CopyExpr,
    SomeExpr, OkExpr, ErrExpr, CoerceExpr, CastExpr, SnapshotExpr,
    PropagateExpr, NullCoalesce, TypeofExpr, CoroutineStart,
    PipelineStage, CoroutinePipeline,
    # Statements
    LetStmt, AssignStmt, UpdateStmt, ReturnStmt, YieldStmt, ThrowStmt,
    BreakStmt, ContinueStmt, ExprStmt, IfStmt, WhileStmt, ForStmt,
    MatchStmt, TryStmt, Block, MatchArm, RetryBlock, CatchBlock, FinallyBlock,
    # Patterns
    WildcardPattern, LiteralPattern, BindPattern, SomePattern, NonePattern,
    OkPattern, ErrPattern, VariantPattern, TuplePattern,
    # Declarations
    ModuleDecl, ImportDecl, FnDecl, TypeDecl, InterfaceDecl, AliasDecl,
    FieldDecl, ConstructorDecl, StaticMemberDecl, SumVariantDecl, Param,
    # Top-level
    Module,
)


# ---------------------------------------------------------------------------
# Symbol data structures (RT-5-1-1, RT-5-1-2)
# ---------------------------------------------------------------------------

class SymbolKind(Enum):
    LOCAL = auto()
    PARAM = auto()
    FN = auto()
    TYPE = auto()
    INTERFACE = auto()
    ALIAS = auto()
    STATIC = auto()
    IMPORT = auto()
    CONSTRUCTOR = auto()


@dataclass
class Symbol:
    name: str
    kind: SymbolKind
    decl: ASTNode
    type_ann: TypeExpr | None
    is_mut: bool


# ---------------------------------------------------------------------------
# Scope (RT-5-1-1)
# ---------------------------------------------------------------------------

class Scope:
    """A lexical scope that chains to an optional parent."""

    def __init__(self, parent: Scope | None = None,
                 is_function_boundary: bool = False) -> None:
        self._bindings: dict[str, Symbol] = {}
        self.parent: Scope | None = parent
        self.is_function_boundary: bool = is_function_boundary

    def define(self, name: str, symbol: Symbol) -> None:
        self._bindings[name] = symbol

    def lookup_local(self, name: str) -> Symbol | None:
        return self._bindings.get(name)

    def lookup(self, name: str) -> Symbol | None:
        sym = self._bindings.get(name)
        if sym is not None:
            return sym
        if self.parent is not None:
            return self.parent.lookup(name)
        return None


# ---------------------------------------------------------------------------
# ModuleScope and ResolvedModule (RT-5-1-3, RT-5-2-1)
# ---------------------------------------------------------------------------

@dataclass
class ModuleScope:
    module_path: list[str]
    exports: dict[str, Symbol] = field(default_factory=dict)


@dataclass
class ResolvedModule:
    module: Module
    symbols: dict[ASTNode, Symbol] = field(default_factory=dict)
    captures: dict[Lambda, list[Symbol]] = field(default_factory=dict)
    module_scope: ModuleScope = field(default_factory=lambda: ModuleScope([]))


# ---------------------------------------------------------------------------
# Lambda capture tracking context
# ---------------------------------------------------------------------------

@dataclass
class _CaptureContext:
    lambda_node: Lambda
    boundary_scope: Scope
    captured: list[Symbol] = field(default_factory=list)
    captured_names: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Resolver (RT-5-2-1 through RT-5-3-4)
# ---------------------------------------------------------------------------

class Resolver:
    """Resolve all names in a Module AST to Symbol objects."""

    def __init__(self, module: Module,
                 imported_modules: dict[str, ModuleScope] | None = None) -> None:
        self._module = module
        self._imported_modules = imported_modules or {}
        self._symbols: dict[ASTNode, Symbol] = {}
        self._captures: dict[Lambda, list[Symbol]] = {}
        self._scope = Scope()  # top-level module scope
        self._module_scope_obj = Scope()  # reference to the module-level scope
        self._in_method = False
        self._in_constructor = False
        self._in_stream_fn = False
        self._capture_stack: list[_CaptureContext] = []
        # Type member scopes: maps type name -> Scope with fields/methods/statics
        self._type_member_scopes: dict[str, Scope] = {}
        # Static member scopes: maps type name -> Scope with static members only
        self._static_member_scopes: dict[str, Scope] = {}
        self._file = module.filename

    def resolve(self) -> ResolvedModule:
        """Run the resolution pass and return a ResolvedModule."""
        self._pre_pass()
        self._resolve_imports()
        self._build_type_member_scopes()
        self._resolve_all_bodies()

        mod_scope = self._build_module_scope()
        return ResolvedModule(
            module=self._module,
            symbols=self._symbols,
            captures=self._captures,
            module_scope=mod_scope,
        )

    # ------------------------------------------------------------------
    # Phase 1: Pre-pass — collect top-level decls for forward refs (RT-5-2-2)
    # ------------------------------------------------------------------

    def _pre_pass(self) -> None:
        """Register all top-level declarations into the module scope."""
        self._module_scope_obj = self._scope
        for decl in self._module.decls:
            match decl:
                case FnDecl(name=name):
                    sym = Symbol(name, SymbolKind.FN, decl,
                                 decl.return_type, False)
                    self._define_or_error(self._scope, name, sym, decl)

                case TypeDecl(name=name):
                    sym = Symbol(name, SymbolKind.TYPE, decl, None, False)
                    self._define_or_error(self._scope, name, sym, decl)
                    # Register constructors at module level
                    for ctor in decl.constructors:
                        ctor_sym = Symbol(
                            ctor.name, SymbolKind.CONSTRUCTOR, ctor,
                            ctor.return_type, False)
                        self._define_or_error(
                            self._scope, ctor.name, ctor_sym, ctor)
                    # Register sum type variant constructors at module level
                    if decl.is_sum_type:
                        for variant in decl.variants:
                            v_sym = Symbol(
                                variant.name, SymbolKind.CONSTRUCTOR, variant,
                                None, False)
                            self._define_or_error(
                                self._scope, variant.name, v_sym, variant)

                case InterfaceDecl(name=name):
                    sym = Symbol(name, SymbolKind.INTERFACE, decl, None, False)
                    self._define_or_error(self._scope, name, sym, decl)

                case AliasDecl(name=name):
                    sym = Symbol(name, SymbolKind.ALIAS, decl,
                                 decl.target, False)
                    self._define_or_error(self._scope, name, sym, decl)

    # ------------------------------------------------------------------
    # Phase 2: Resolve import declarations (RT-5-2-3)
    # ------------------------------------------------------------------

    def _resolve_imports(self) -> None:
        """Resolve import declarations against loaded ModuleScopes."""
        for imp in self._module.imports:
            module_key = ".".join(imp.path)
            mod_scope = self._imported_modules.get(module_key)
            if mod_scope is None:
                raise self._error(
                    f"module '{module_key}' not found", imp)

            if imp.names is not None:
                # Named import: import math.vector (Vec3, dot)
                for name in imp.names:
                    exported = mod_scope.exports.get(name)
                    if exported is None:
                        raise self._error(
                            f"name '{name}' is not exported by "
                            f"module '{module_key}'", imp)
                    imp_sym = Symbol(
                        name, SymbolKind.IMPORT, exported.decl,
                        exported.type_ann, exported.is_mut)
                    self._define_or_error(self._scope, name, imp_sym, imp)
            elif imp.alias is not None:
                # Aliased import: import math.vector as vec
                ns_sym = Symbol(
                    imp.alias, SymbolKind.IMPORT, imp, None, False)
                # Store the module scope so we can resolve vec.X later
                self._define_or_error(
                    self._scope, imp.alias, ns_sym, imp)
                # Build a scope for namespace access
                ns_scope = Scope()
                for name, sym in mod_scope.exports.items():
                    ns_scope.define(name, sym)
                self._type_member_scopes[imp.alias] = ns_scope
            else:
                # Bare import: import math.vector -> namespace is "vector"
                ns_name = imp.path[-1]
                ns_sym = Symbol(
                    ns_name, SymbolKind.IMPORT, imp, None, False)
                self._define_or_error(
                    self._scope, ns_name, ns_sym, imp)
                ns_scope = Scope()
                for name, sym in mod_scope.exports.items():
                    ns_scope.define(name, sym)
                self._type_member_scopes[ns_name] = ns_scope

    # ------------------------------------------------------------------
    # Phase 3: Build type member scopes (RT-5-2-6)
    # ------------------------------------------------------------------

    def _build_type_member_scopes(self) -> None:
        """Index fields, methods, and statics for each TypeDecl."""
        for decl in self._module.decls:
            if not isinstance(decl, TypeDecl):
                continue

            member_scope = Scope()
            static_scope = Scope()

            for f in decl.fields:
                sym = Symbol(f.name, SymbolKind.LOCAL, f, f.type_ann, f.is_mut)
                member_scope.define(f.name, sym)

            for m in decl.methods:
                sym = Symbol(m.name, SymbolKind.FN, m, m.return_type, False)
                member_scope.define(m.name, sym)

            for s in decl.static_members:
                sym = Symbol(s.name, SymbolKind.STATIC, s, s.type_ann, s.is_mut)
                static_scope.define(s.name, sym)
                member_scope.define(s.name, sym)

            for ctor in decl.constructors:
                sym = Symbol(
                    ctor.name, SymbolKind.CONSTRUCTOR, ctor,
                    ctor.return_type, False)
                member_scope.define(ctor.name, sym)

            self._type_member_scopes[decl.name] = member_scope
            self._static_member_scopes[decl.name] = static_scope

    # ------------------------------------------------------------------
    # Phase 4: Resolve all bodies (RT-5-2-4, RT-5-2-6)
    # ------------------------------------------------------------------

    def _resolve_all_bodies(self) -> None:
        """Walk all declarations and resolve function/method/constructor bodies."""
        for decl in self._module.decls:
            match decl:
                case FnDecl():
                    self._resolve_fn_body(decl, self._module_scope_obj)

                case TypeDecl():
                    self._resolve_type_decl(decl)

                case InterfaceDecl():
                    # Interface methods have no bodies to resolve
                    pass

                case AliasDecl():
                    # Nothing to resolve in type alias bodies
                    pass

    def _resolve_type_decl(self, decl: TypeDecl) -> None:
        """Resolve methods, constructors, and static member initializers."""
        type_scope = Scope(parent=self._module_scope_obj,
                           is_function_boundary=True)

        # Resolve static member initializers
        for s in decl.static_members:
            if s.value is not None:
                self._resolve_expr(s.value, self._module_scope_obj)

        # Resolve methods
        for method in decl.methods:
            self._resolve_method_body(method, decl, type_scope)

        # Resolve constructors
        for ctor in decl.constructors:
            self._resolve_constructor_body(ctor, decl, type_scope)

    def _resolve_fn_body(self, fn: FnDecl, parent_scope: Scope) -> None:
        """Resolve a top-level function body."""
        if fn.body is None:
            return

        fn_scope = Scope(parent=parent_scope, is_function_boundary=True)

        # Bind parameters
        for param in fn.params:
            is_mut = self._is_mut_binding(param.type_ann)
            sym = Symbol(param.name, SymbolKind.PARAM, param,
                         param.type_ann, is_mut)
            self._define_or_error(fn_scope, param.name, sym, param)

        old_stream = self._in_stream_fn
        self._in_stream_fn = self._is_stream_return(fn.return_type)

        match fn.body:
            case Block():
                self._resolve_block(fn.body, fn_scope)
            case Expr():
                self._resolve_expr(fn.body, fn_scope)

        if fn.finally_block is not None:
            self._resolve_block(fn.finally_block, fn_scope)

        self._in_stream_fn = old_stream

    def _resolve_method_body(self, method: FnDecl, type_decl: TypeDecl,
                             type_scope: Scope) -> None:
        """Resolve a method body within a type."""
        if method.body is None:
            return

        method_scope = Scope(parent=self._module_scope_obj,
                             is_function_boundary=True)

        # Bind parameters — self is an explicit param per the spec
        for param in method.params:
            if param.name == "self":
                self_type = NamedType(line=param.line, col=param.col,
                                      name=type_decl.name, module_path=[])
                sym = Symbol("self", SymbolKind.PARAM, param,
                             self_type, False)
            else:
                is_mut = self._is_mut_binding(param.type_ann)
                sym = Symbol(param.name, SymbolKind.PARAM, param,
                             param.type_ann, is_mut)
            self._define_or_error(method_scope, param.name, sym, param)

        old_method = self._in_method
        old_stream = self._in_stream_fn
        self._in_method = True
        self._in_stream_fn = self._is_stream_return(method.return_type)

        match method.body:
            case Block():
                self._resolve_block(method.body, method_scope)
            case Expr():
                self._resolve_expr(method.body, method_scope)

        if method.finally_block is not None:
            self._resolve_block(method.finally_block, method_scope)

        self._in_method = old_method
        self._in_stream_fn = old_stream

    def _resolve_constructor_body(self, ctor: ConstructorDecl,
                                  type_decl: TypeDecl,
                                  type_scope: Scope) -> None:
        """Resolve a constructor body."""
        ctor_scope = Scope(parent=self._module_scope_obj,
                           is_function_boundary=True)

        # Bind parameters — self is an explicit param per the spec
        for param in ctor.params:
            if param.name == "self":
                self_type = NamedType(line=param.line, col=param.col,
                                      name=type_decl.name, module_path=[])
                sym = Symbol("self", SymbolKind.PARAM, param,
                             self_type, True)  # self is mutable in ctors
            else:
                is_mut = self._is_mut_binding(param.type_ann)
                sym = Symbol(param.name, SymbolKind.PARAM, param,
                             param.type_ann, is_mut)
            self._define_or_error(ctor_scope, param.name, sym, param)

        old_method = self._in_method
        old_ctor = self._in_constructor
        self._in_method = True
        self._in_constructor = True

        self._resolve_block(ctor.body, ctor_scope)

        self._in_method = old_method
        self._in_constructor = old_ctor

    # ------------------------------------------------------------------
    # Lambda resolution (RT-5-2-5)
    # ------------------------------------------------------------------

    def _resolve_lambda(self, lam: Lambda, scope: Scope) -> None:
        """Resolve a lambda expression, tracking captures."""
        lam_scope = Scope(parent=scope, is_function_boundary=False)

        # Bind parameters
        for param in lam.params:
            is_mut = self._is_mut_binding(param.type_ann)
            sym = Symbol(param.name, SymbolKind.PARAM, param,
                         param.type_ann, is_mut)
            self._define_or_error(lam_scope, param.name, sym, param)

        # Push capture context
        ctx = _CaptureContext(lambda_node=lam, boundary_scope=lam_scope)
        self._capture_stack.append(ctx)

        match lam.body:
            case Block():
                self._resolve_block(lam.body, lam_scope)
            case Expr():
                self._resolve_expr(lam.body, lam_scope)

        # Pop and store captures
        self._capture_stack.pop()
        self._captures[lam] = ctx.captured

    # ------------------------------------------------------------------
    # Expression resolution (RT-5-2-1)
    # ------------------------------------------------------------------

    def _resolve_expr(self, expr: Expr, scope: Scope) -> None:
        """Resolve names in an expression."""
        match expr:
            case IntLit() | FloatLit() | BoolLit() | StringLit() | CharLit() | NoneLit():
                pass  # Literals need no resolution

            case FStringExpr(parts=parts):
                for part in parts:
                    if isinstance(part, Expr):
                        self._resolve_expr(part, scope)

            case Ident(name=name, module_path=mp):
                if mp:
                    # Qualified name like math.vector.foo — resolve the
                    # first component and treat the rest as field access.
                    # For now, resolve just the namespace prefix.
                    ns_name = mp[0]
                    ns_sym = self._lookup_or_error(scope, ns_name, expr)
                    self._symbols[expr] = ns_sym
                else:
                    sym = self._lookup_or_error(scope, name, expr)
                    self._symbols[expr] = sym
                    self._track_capture(sym, scope)

            case BinOp(left=left, right=right):
                self._resolve_expr(left, scope)
                self._resolve_expr(right, scope)

            case UnaryOp(operand=operand):
                self._resolve_expr(operand, scope)

            case Call(callee=callee, args=args):
                self._resolve_expr(callee, scope)
                for arg in args:
                    self._resolve_expr(arg, scope)

            case MethodCall(receiver=receiver, method=method_name, args=args):
                self._resolve_expr(receiver, scope)
                # Check if receiver is a namespace import (RT-9 stdlib)
                if isinstance(receiver, Ident) and not receiver.module_path:
                    recv_sym = self._symbols.get(receiver)
                    if recv_sym is not None and recv_sym.kind == SymbolKind.IMPORT:
                        ns_scope = self._type_member_scopes.get(recv_sym.name)
                        if ns_scope is not None:
                            member_sym = ns_scope.lookup_local(method_name)
                            if member_sym is not None:
                                self._symbols[expr] = member_sym
                            else:
                                raise self._error(
                                    f"name '{method_name}' not found in "
                                    f"namespace '{recv_sym.name}'", expr)
                # Other method names resolved by type checker
                for arg in args:
                    self._resolve_expr(arg, scope)

            case FieldAccess(receiver=receiver, field=field_name):
                self._resolve_expr(receiver, scope)
                # Check for static member access (RT-5-2-7)
                if isinstance(receiver, Ident) and not receiver.module_path:
                    recv_sym = self._symbols.get(receiver)
                    if recv_sym is not None and recv_sym.kind == SymbolKind.TYPE:
                        # Static member access: Type.member
                        static_scope = self._static_member_scopes.get(
                            recv_sym.name)
                        if static_scope is not None:
                            member_sym = static_scope.lookup_local(field_name)
                            if member_sym is not None:
                                self._symbols[expr] = member_sym
                                return
                    # Namespace access (import namespace.name)
                    if recv_sym is not None and recv_sym.kind == SymbolKind.IMPORT:
                        ns_scope = self._type_member_scopes.get(recv_sym.name)
                        if ns_scope is not None:
                            member_sym = ns_scope.lookup_local(field_name)
                            if member_sym is not None:
                                self._symbols[expr] = member_sym
                                return
                            raise self._error(
                                f"name '{field_name}' not found in "
                                f"namespace '{recv_sym.name}'", expr)
                # Instance field access deferred to type checker

            case IndexAccess(receiver=receiver, index=index):
                self._resolve_expr(receiver, scope)
                self._resolve_expr(index, scope)

            case Lambda():
                self._resolve_lambda(expr, scope)

            case TupleExpr(elements=elements):
                for elem in elements:
                    self._resolve_expr(elem, scope)

            case ArrayLit(elements=elements):
                for elem in elements:
                    self._resolve_expr(elem, scope)

            case RecordLit(fields=fields):
                for _, val in fields:
                    self._resolve_expr(val, scope)

            case TypeLit(type_name=type_name, fields=fields, spread=spread):
                # Resolve type name
                sym = self._lookup_or_error(scope, type_name, expr)
                self._symbols[expr] = sym
                for _, val in fields:
                    self._resolve_expr(val, scope)
                if spread is not None:
                    self._resolve_expr(spread, scope)

            case IfExpr(condition=cond, then_branch=then_b,
                        else_branch=else_b):
                self._resolve_expr(cond, scope)
                self._resolve_block(then_b, scope)
                if else_b is not None:
                    if isinstance(else_b, Block):
                        self._resolve_block(else_b, scope)
                    else:
                        self._resolve_expr(else_b, scope)

            case MatchExpr(subject=subject, arms=arms):
                self._resolve_expr(subject, scope)
                self._resolve_match_arms(arms, scope)

            case CompositionChain(elements=elements):
                for elem in elements:
                    self._resolve_expr(elem.expr, scope)

            case FanOut(branches=branches):
                for branch in branches:
                    self._resolve_expr(branch.expr, scope)

            case TernaryExpr(condition=cond, then_expr=then_e,
                             else_expr=else_e):
                self._resolve_expr(cond, scope)
                self._resolve_expr(then_e, scope)
                self._resolve_expr(else_e, scope)

            case CopyExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case SomeExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case OkExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case ErrExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case CoerceExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case CastExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case SnapshotExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case PropagateExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case NullCoalesce(left=left, right=right):
                self._resolve_expr(left, scope)
                self._resolve_expr(right, scope)

            case TypeofExpr(inner=inner):
                self._resolve_expr(inner, scope)

            case CoroutineStart(call=call):
                self._resolve_expr(call, scope)

            case CoroutinePipeline(stages=stages):
                for stage in stages:
                    self._resolve_expr(stage.call, scope)
                    if stage.pool_size is not None:
                        self._resolve_expr(stage.pool_size, scope)

            case _:
                # SPEC GAP: unknown expression type — reject safely
                raise self._error(
                    f"unknown expression type: {type(expr).__name__}", expr)

    # ------------------------------------------------------------------
    # Statement resolution
    # ------------------------------------------------------------------

    def _resolve_stmt(self, stmt: Stmt, scope: Scope) -> None:
        """Resolve names in a statement."""
        match stmt:
            case LetStmt(name=name, type_ann=type_ann, value=value):
                self._resolve_expr(value, scope)
                is_mut = self._is_mut_binding(type_ann)
                sym = Symbol(name, SymbolKind.LOCAL, stmt, type_ann, is_mut)
                self._define_or_error(scope, name, sym, stmt)

            case AssignStmt(target=target, value=value):
                self._resolve_expr(value, scope)
                self._resolve_expr(target, scope)
                # Mutability check for simple Ident targets
                if isinstance(target, Ident) and not target.module_path:
                    sym = self._symbols.get(target)
                    if sym is not None and not sym.is_mut:
                        raise self._error(
                            f"cannot assign to immutable binding "
                            f"'{target.name}'", stmt)

            case UpdateStmt(target=target, value=value):
                self._resolve_expr(target, scope)
                if value is not None:
                    self._resolve_expr(value, scope)
                # Mutability check for simple Ident targets (RT-5-3-2)
                if isinstance(target, Ident) and not target.module_path:
                    sym = self._symbols.get(target)
                    if sym is not None and not sym.is_mut:
                        raise self._error(
                            f"cannot apply '{stmt.op}' to immutable "
                            f"binding '{target.name}'", stmt)
                # Compound targets deferred to type checker

            case ReturnStmt(value=value):
                if value is not None:
                    self._resolve_expr(value, scope)

            case YieldStmt(value=value):
                # RT-5-3-4: yield only valid in stream functions
                if not self._in_stream_fn:
                    raise self._error(
                        "yield is only valid inside a stream function",
                        stmt)
                self._resolve_expr(value, scope)

            case ThrowStmt(exception=exception):
                self._resolve_expr(exception, scope)

            case BreakStmt():
                pass

            case ContinueStmt():
                pass

            case ExprStmt(expr=expr):
                self._resolve_expr(expr, scope)

            case IfStmt(condition=cond, then_branch=then_b,
                        else_branch=else_b):
                self._resolve_expr(cond, scope)
                self._resolve_block(then_b, scope)
                if else_b is not None:
                    if isinstance(else_b, Block):
                        self._resolve_block(else_b, scope)
                    else:
                        self._resolve_stmt(else_b, scope)

            case WhileStmt(condition=cond, body=body,
                           finally_block=fin):
                self._resolve_expr(cond, scope)
                self._resolve_block(body, scope)
                if fin is not None:
                    self._resolve_block(fin, scope)

            case ForStmt(var=var, var_type=var_type,
                         iterable=iterable, body=body,
                         finally_block=fin):
                self._resolve_expr(iterable, scope)
                for_scope = Scope(parent=scope)
                is_mut = self._is_mut_binding(var_type)
                sym = Symbol(var, SymbolKind.LOCAL, stmt, var_type, is_mut)
                for_scope.define(var, sym)
                self._resolve_block(body, for_scope)
                if fin is not None:
                    self._resolve_block(fin, scope)

            case MatchStmt(subject=subject, arms=arms):
                self._resolve_expr(subject, scope)
                self._resolve_match_arms(arms, scope)

            case TryStmt(body=body, retry_blocks=retries,
                         catch_blocks=catches, finally_block=fin):
                self._resolve_block(body, scope)
                for retry in retries:
                    self._resolve_retry_block(retry, scope)
                for catch in catches:
                    self._resolve_catch_block(catch, scope)
                if fin is not None:
                    self._resolve_finally_block(fin, scope)

            case _:
                raise self._error(
                    f"unknown statement type: {type(stmt).__name__}", stmt)

    # ------------------------------------------------------------------
    # Block resolution
    # ------------------------------------------------------------------

    def _resolve_block(self, block: Block, parent_scope: Scope) -> None:
        """Resolve a block, creating a new inner scope."""
        block_scope = Scope(parent=parent_scope)
        for stmt in block.stmts:
            self._resolve_stmt(stmt, block_scope)
        if block.finally_block is not None:
            self._resolve_block(block.finally_block, parent_scope)

    # ------------------------------------------------------------------
    # Match arm resolution (RT-5-2-8)
    # ------------------------------------------------------------------

    def _resolve_match_arms(self, arms: list[MatchArm],
                            scope: Scope) -> None:
        """Resolve all match arms, creating pattern-binding scopes."""
        for arm in arms:
            arm_scope = Scope(parent=scope)
            self._resolve_pattern(arm.pattern, arm_scope)
            match arm.body:
                case Block():
                    self._resolve_block(arm.body, arm_scope)
                case Expr():
                    self._resolve_expr(arm.body, arm_scope)

    def _resolve_pattern(self, pat: Pattern, scope: Scope) -> None:
        """Resolve a pattern, binding names into scope."""
        match pat:
            case WildcardPattern():
                pass

            case LiteralPattern(value=val):
                self._resolve_expr(val, scope)

            case BindPattern(name=name):
                sym = Symbol(name, SymbolKind.LOCAL, pat, None, False)
                scope.define(name, sym)

            case SomePattern(inner_var=var):
                sym = Symbol(var, SymbolKind.LOCAL, pat, None, False)
                scope.define(var, sym)

            case NonePattern():
                pass

            case OkPattern(inner_var=var):
                sym = Symbol(var, SymbolKind.LOCAL, pat, None, False)
                scope.define(var, sym)

            case ErrPattern(inner_var=var):
                sym = Symbol(var, SymbolKind.LOCAL, pat, None, False)
                scope.define(var, sym)

            case VariantPattern(bindings=bindings):
                for binding in bindings:
                    sym = Symbol(binding, SymbolKind.LOCAL, pat, None, False)
                    scope.define(binding, sym)

            case TuplePattern(elements=elements):
                for elem in elements:
                    self._resolve_pattern(elem, scope)

            case _:
                raise self._error(
                    f"unknown pattern type: {type(pat).__name__}", pat)

    # ------------------------------------------------------------------
    # Try/catch/retry resolution
    # ------------------------------------------------------------------

    def _resolve_retry_block(self, retry: RetryBlock,
                             scope: Scope) -> None:
        retry_scope = Scope(parent=scope)
        sym = Symbol(retry.exception_var, SymbolKind.LOCAL, retry,
                     retry.exception_type, True)  # ex.data is mutable
        retry_scope.define(retry.exception_var, sym)
        self._resolve_block(retry.body, retry_scope)

    def _resolve_catch_block(self, catch: CatchBlock,
                             scope: Scope) -> None:
        catch_scope = Scope(parent=scope)
        sym = Symbol(catch.exception_var, SymbolKind.LOCAL, catch,
                     catch.exception_type, False)
        catch_scope.define(catch.exception_var, sym)
        self._resolve_block(catch.body, catch_scope)

    def _resolve_finally_block(self, fin: FinallyBlock,
                               scope: Scope) -> None:
        if fin.exception_var is not None:
            fin_scope = Scope(parent=scope)
            sym = Symbol(fin.exception_var, SymbolKind.LOCAL, fin,
                         fin.exception_type, False)
            fin_scope.define(fin.exception_var, sym)
            self._resolve_block(fin.body, fin_scope)
        else:
            self._resolve_block(fin.body, scope)

    # ------------------------------------------------------------------
    # Capture tracking
    # ------------------------------------------------------------------

    def _track_capture(self, sym: Symbol, scope: Scope) -> None:
        """If inside a lambda and sym is from an enclosing scope, record it."""
        if not self._capture_stack:
            return

        ctx = self._capture_stack[-1]
        # Check if the symbol is defined outside the lambda's own scope.
        # Walk from the lambda's scope to find where the symbol lives.
        if sym.name in ctx.captured_names:
            return  # Already captured

        # If the symbol is not found in the lambda's own local scope chain
        # (up to but not including the lambda boundary), it's a capture.
        check = ctx.boundary_scope
        while check is not None:
            local = check.lookup_local(sym.name)
            if local is sym:
                return  # Defined inside the lambda — not a capture
            check_parent = check.parent
            if check is ctx.boundary_scope and check_parent is not None:
                # Only check the lambda scope itself, not parents
                break
            check = check_parent

        # It's a capture
        ctx.captured.append(sym)
        ctx.captured_names.add(sym.name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _define_or_error(self, scope: Scope, name: str, symbol: Symbol,
                         node: ASTNode) -> None:
        """Define a name in scope, raising ResolveError on duplicate in same scope."""
        existing = scope.lookup_local(name)
        if existing is not None:
            raise self._error(
                f"duplicate definition of '{name}'", node)
        scope.define(name, symbol)

    def _lookup_or_error(self, scope: Scope, name: str,
                         node: ASTNode) -> Symbol:
        """Look up a name, raising ResolveError if not found."""
        # RT-5-3-3: self is only valid in methods/constructors
        if name == "self":
            if not self._in_method and not self._in_constructor:
                raise self._error(
                    "'self' is only valid inside a method or constructor",
                    node)

        sym = scope.lookup(name)
        if sym is None:
            raise self._error(f"undefined name '{name}'", node)
        return sym

    def _error(self, message: str, node: ASTNode) -> ResolveError:
        """Create a ResolveError from a message and AST node."""
        return ResolveError(
            message=message,
            file=self._file,
            line=node.line,
            col=node.col,
        )

    def _is_mut_binding(self, type_ann: TypeExpr | None) -> bool:
        """Check if a type annotation indicates a mutable binding."""
        if type_ann is None:
            return False
        return isinstance(type_ann, MutType)

    def _is_stream_return(self, type_ann: TypeExpr | None) -> bool:
        """Check if a return type is stream<T>."""
        if type_ann is None:
            return False
        # Unwrap SizedType (e.g., stream<int>[64] → stream<int>)
        if isinstance(type_ann, SizedType):
            return self._is_stream_return(type_ann.inner)
        match type_ann:
            case NamedType(name="stream"):
                return True
            case GenericType(base=NamedType(name="stream")):
                return True
            case _:
                return False

    def _build_module_scope(self) -> ModuleScope:
        """Build the ModuleScope with all exported symbols."""
        mod_scope = ModuleScope(module_path=self._module.path)
        for decl in self._module.decls:
            match decl:
                case FnDecl(name=name, is_export=True):
                    sym = self._scope.lookup_local(name)
                    if sym is not None:
                        mod_scope.exports[name] = sym

                case TypeDecl(name=name, is_export=True):
                    sym = self._scope.lookup_local(name)
                    if sym is not None:
                        mod_scope.exports[name] = sym
                    # Export constructors too
                    for ctor in decl.constructors:
                        ctor_sym = self._scope.lookup_local(ctor.name)
                        if ctor_sym is not None:
                            mod_scope.exports[ctor.name] = ctor_sym
                    if decl.is_sum_type:
                        for variant in decl.variants:
                            v_sym = self._scope.lookup_local(variant.name)
                            if v_sym is not None:
                                mod_scope.exports[variant.name] = v_sym

                case InterfaceDecl(name=name, is_export=True):
                    sym = self._scope.lookup_local(name)
                    if sym is not None:
                        mod_scope.exports[name] = sym

                case AliasDecl(name=name, is_export=True):
                    sym = self._scope.lookup_local(name)
                    if sym is not None:
                        mod_scope.exports[name] = sym

        return mod_scope
