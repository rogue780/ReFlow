# compiler/typechecker.py — Infers and verifies types.
# No C-level concerns.
#
# Implements RT-6-1-1 through RT-6-7-3.
from __future__ import annotations

import warnings as _warnings
from dataclasses import dataclass, field
from enum import Enum, auto

from compiler.errors import TypeError as ReFlowTypeError
from compiler.ast_nodes import (
    # Base
    ASTNode, TypeExpr, Expr, Stmt, Decl, Pattern,
    # Type expressions
    NamedType, GenericType, OptionType, FnType, TupleType,
    MutType, ImutType, SumTypeExpr, SumVariantExpr,
    # Expressions
    IntLit, FloatLit, BoolLit, StringLit, FStringExpr, CharLit, NoneLit,
    Ident, BinOp, UnaryOp, Call, MethodCall, FieldAccess, IndexAccess,
    Lambda, TupleExpr, ArrayLit, RecordLit, TypeLit, IfExpr, MatchExpr,
    CompositionChain, ChainElement, FanOut, TernaryExpr, CopyExpr,
    SomeExpr, OkExpr, ErrExpr, CoerceExpr, CastExpr, SnapshotExpr,
    PropagateExpr, NullCoalesce, TypeofExpr, CoroutineStart,
    # Statements
    LetStmt, AssignStmt, UpdateStmt, ReturnStmt, YieldStmt, ThrowStmt,
    BreakStmt, ExprStmt, IfStmt, WhileStmt, ForStmt,
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
from compiler.resolver import (
    ResolvedModule, Symbol, SymbolKind, ModuleScope,
)


# ---------------------------------------------------------------------------
# Type representation (RT-6-1-1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Type:
    """Base class for all resolved types."""
    pass


@dataclass(frozen=True)
class TInt(Type):
    width: int
    signed: bool


@dataclass(frozen=True)
class TFloat(Type):
    width: int


@dataclass(frozen=True)
class TBool(Type):
    pass


@dataclass(frozen=True)
class TChar(Type):
    pass


@dataclass(frozen=True)
class TByte(Type):
    pass


@dataclass(frozen=True)
class TString(Type):
    pass


@dataclass(frozen=True)
class TNone(Type):
    pass


@dataclass(frozen=True)
class TOption(Type):
    inner: Type


@dataclass(frozen=True)
class TResult(Type):
    ok_type: Type
    err_type: Type


@dataclass(frozen=True)
class TTuple(Type):
    elements: tuple[Type, ...]


@dataclass(frozen=True)
class TArray(Type):
    element: Type


@dataclass(frozen=True)
class TStream(Type):
    element: Type


@dataclass(frozen=True)
class TBuffer(Type):
    element: Type


@dataclass(frozen=True)
class TMap(Type):
    key: Type
    value: Type


@dataclass(frozen=True)
class TSet(Type):
    element: Type


@dataclass(frozen=True)
class TFn(Type):
    params: tuple[Type, ...]
    ret: Type
    is_pure: bool


@dataclass(frozen=True)
class TRecord(Type):
    fields: tuple[tuple[str, Type], ...]


@dataclass(frozen=True)
class TNamed(Type):
    module: str
    name: str
    type_args: tuple[Type, ...]


@dataclass(frozen=True)
class TAlias(Type):
    name: str
    underlying: Type


@dataclass(frozen=True)
class TSum(Type):
    name: str
    variants: tuple[TVariant, ...]


@dataclass(frozen=True)
class TVariant:
    name: str
    fields: tuple[Type, ...] | None


@dataclass(frozen=True)
class TTypeVar(Type):
    name: str


@dataclass(frozen=True)
class TAny(Type):
    """Placeholder during inference before resolution."""
    pass


# ---------------------------------------------------------------------------
# TypeEnv — generic type variable bindings (RT-6-1-2)
# ---------------------------------------------------------------------------

TypeEnv = dict[str, Type]


def apply_env(t: Type, env: TypeEnv) -> Type:
    """Substitute all type variables in *t* with their bindings in *env*."""
    if not env:
        return t

    match t:
        case TTypeVar(name=name):
            return env.get(name, t)

        case TOption(inner=inner):
            return TOption(apply_env(inner, env))

        case TResult(ok_type=ok_t, err_type=err_t):
            return TResult(apply_env(ok_t, env), apply_env(err_t, env))

        case TTuple(elements=elems):
            return TTuple(tuple(apply_env(e, env) for e in elems))

        case TArray(element=elem):
            return TArray(apply_env(elem, env))

        case TStream(element=elem):
            return TStream(apply_env(elem, env))

        case TBuffer(element=elem):
            return TBuffer(apply_env(elem, env))

        case TMap(key=k, value=v):
            return TMap(apply_env(k, env), apply_env(v, env))

        case TSet(element=elem):
            return TSet(apply_env(elem, env))

        case TFn(params=params, ret=ret, is_pure=pure):
            return TFn(
                tuple(apply_env(p, env) for p in params),
                apply_env(ret, env), pure)

        case TRecord(fields=fields):
            return TRecord(
                tuple((n, apply_env(ft, env)) for n, ft in fields))

        case TNamed(module=mod, name=name, type_args=args):
            return TNamed(mod, name,
                          tuple(apply_env(a, env) for a in args))

        case TSum(name=name, variants=variants):
            new_variants = []
            for v in variants:
                if v.fields is not None:
                    new_fields = tuple(apply_env(f, env) for f in v.fields)
                    new_variants.append(TVariant(v.name, new_fields))
                else:
                    new_variants.append(v)
            return TSum(name, tuple(new_variants))

        case _:
            return t


# ---------------------------------------------------------------------------
# TypedModule (RT-6-2-1)
# ---------------------------------------------------------------------------

@dataclass
class TypedModule:
    module: Module
    resolved: ResolvedModule
    types: dict[ASTNode, Type] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Type scope — tracks name → Type during checking
# ---------------------------------------------------------------------------

class TypeScope:
    def __init__(self, parent: TypeScope | None = None) -> None:
        self._types: dict[str, Type] = {}
        self.parent = parent

    def define(self, name: str, ty: Type) -> None:
        self._types[name] = ty

    def lookup(self, name: str) -> Type | None:
        t = self._types.get(name)
        if t is not None:
            return t
        if self.parent is not None:
            return self.parent.lookup(name)
        return None


# ---------------------------------------------------------------------------
# Type info — metadata about user-defined types
# ---------------------------------------------------------------------------

@dataclass
class TypeInfo:
    name: str
    type_params: list[str]
    fields: dict[str, Type]
    field_mutability: dict[str, bool]
    methods: dict[str, TFn]
    statics: dict[str, Type]
    static_mutability: dict[str, bool]
    constructors: dict[str, TFn]
    is_sum_type: bool
    sum_type: TSum | None
    interfaces: list[str]


# ---------------------------------------------------------------------------
# Builtin type name mapping
# ---------------------------------------------------------------------------

_BUILTIN_TYPES: dict[str, Type] = {
    "int": TInt(32, True),
    "int16": TInt(16, True),
    "int32": TInt(32, True),
    "int64": TInt(64, True),
    "uint": TInt(32, False),
    "uint16": TInt(16, False),
    "uint32": TInt(32, False),
    "uint64": TInt(64, False),
    "float": TFloat(64),
    "float32": TFloat(32),
    "float64": TFloat(64),
    "bool": TBool(),
    "char": TChar(),
    "byte": TByte(),
    "string": TString(),
    "none": TNone(),
}

_INT_SUFFIXES: dict[str, Type] = {
    "i16": TInt(16, True),
    "i32": TInt(32, True),
    "i64": TInt(64, True),
    "u16": TInt(16, False),
    "u32": TInt(32, False),
    "u64": TInt(64, False),
}

_FLOAT_SUFFIXES: dict[str, Type] = {
    "f32": TFloat(32),
    "f64": TFloat(64),
}

_NUMERIC_TYPES = (TInt, TFloat)

_ARITHMETIC_OPS = {"+", "-", "*", "/", "//", "%", "**"}
_COMPARISON_OPS = {"<", ">", "<=", ">=", "==", "!="}
_LOGICAL_OPS = {"&&", "||"}


# ---------------------------------------------------------------------------
# TypeChecker (RT-6-2-1 through RT-6-7-3)
# ---------------------------------------------------------------------------

class TypeChecker:
    """Infer and verify types for a resolved module."""

    def __init__(self, resolved: ResolvedModule) -> None:
        self._resolved = resolved
        self._module = resolved.module
        self._file = resolved.module.filename
        self._types: dict[ASTNode, Type] = {}
        self._warnings: list[str] = []
        self._scope = TypeScope()
        self._module_scope = TypeScope()
        self._type_registry: dict[str, TypeInfo] = {}
        self._current_return_type: Type | None = None
        self._consumed_streams: set[str] = set()
        self._in_pure_fn = False
        self._purity_map: dict[str, bool] = {}

    def check(self) -> TypedModule:
        """Run the type checking pass."""
        self._build_type_registry()
        self._register_top_level_types()
        self._check_all_bodies()
        return TypedModule(
            module=self._module,
            resolved=self._resolved,
            types=self._types,
            warnings=self._warnings,
        )

    # ------------------------------------------------------------------
    # Pre-pass: build type registry from TypeDecls
    # ------------------------------------------------------------------

    def _build_type_registry(self) -> None:
        for decl in self._module.decls:
            if not isinstance(decl, TypeDecl):
                continue

            fields: dict[str, Type] = {}
            field_mut: dict[str, bool] = {}
            for f in decl.fields:
                fields[f.name] = self._resolve_type_expr(f.type_ann)
                field_mut[f.name] = f.is_mut

            methods: dict[str, TFn] = {}
            for m in decl.methods:
                params = []
                for p in m.params:
                    if p.name == "self":
                        continue
                    params.append(self._resolve_type_expr(p.type_ann))
                ret = self._resolve_type_expr(m.return_type) if m.return_type else TNone()
                methods[m.name] = TFn(tuple(params), ret, m.is_pure)

            statics: dict[str, Type] = {}
            static_mut: dict[str, bool] = {}
            for s in decl.static_members:
                statics[s.name] = self._resolve_type_expr(s.type_ann)
                static_mut[s.name] = s.is_mut

            constructors: dict[str, TFn] = {}
            for c in decl.constructors:
                c_params = []
                for p in c.params:
                    if p.name == "self":
                        continue
                    c_params.append(self._resolve_type_expr(p.type_ann))
                c_ret = self._resolve_type_expr(c.return_type)
                constructors[c.name] = TFn(tuple(c_params), c_ret, False)

            sum_type: TSum | None = None
            if decl.is_sum_type:
                variants = []
                for v in decl.variants:
                    if v.fields is not None:
                        v_fields = tuple(
                            self._resolve_type_expr(ft)
                            for _, ft in v.fields)
                        variants.append(TVariant(v.name, v_fields))
                    else:
                        variants.append(TVariant(v.name, None))
                sum_type = TSum(decl.name, tuple(variants))

            self._type_registry[decl.name] = TypeInfo(
                name=decl.name,
                type_params=decl.type_params,
                fields=fields,
                field_mutability=field_mut,
                methods=methods,
                statics=statics,
                static_mutability=static_mut,
                constructors=constructors,
                is_sum_type=decl.is_sum_type,
                sum_type=sum_type,
                interfaces=decl.interfaces,
            )

    # ------------------------------------------------------------------
    # Pre-pass: register top-level names in the type scope
    # ------------------------------------------------------------------

    def _register_top_level_types(self) -> None:
        for decl in self._module.decls:
            match decl:
                case FnDecl(name=name):
                    fn_type = self._fn_decl_type(decl)
                    self._scope.define(name, fn_type)
                    self._purity_map[name] = decl.is_pure

                case TypeDecl(name=name):
                    info = self._type_registry.get(name)
                    if info and info.is_sum_type and info.sum_type:
                        self._scope.define(name, info.sum_type)
                    else:
                        self._scope.define(
                            name, TNamed("", name, ()))
                    # Register constructors
                    for c_name, c_type in (info.constructors if info else {}).items():
                        self._scope.define(c_name, c_type)
                    # Register variant constructors for sum types
                    if info and info.is_sum_type and info.sum_type:
                        for v in info.sum_type.variants:
                            if v.fields is not None:
                                v_type = TFn(v.fields, info.sum_type, False)
                                self._scope.define(v.name, v_type)
                            else:
                                self._scope.define(v.name, info.sum_type)

                case InterfaceDecl(name=name):
                    self._scope.define(name, TNamed("", name, ()))

                case AliasDecl(name=name):
                    target = self._resolve_type_expr(decl.target)
                    self._scope.define(name, TAlias(name, target))

        self._module_scope = TypeScope()
        self._module_scope._types = dict(self._scope._types)

    # ------------------------------------------------------------------
    # Check all bodies
    # ------------------------------------------------------------------

    def _check_all_bodies(self) -> None:
        for decl in self._module.decls:
            match decl:
                case FnDecl():
                    self._check_fn_body(decl)
                case TypeDecl():
                    self._check_type_decl(decl)

    def _check_fn_body(self, fn: FnDecl) -> None:
        if fn.body is None:
            return

        fn_scope = TypeScope(parent=self._module_scope)

        for param in fn.params:
            p_type = self._resolve_type_expr(param.type_ann)
            fn_scope.define(param.name, p_type)

        ret_type = self._resolve_type_expr(fn.return_type) if fn.return_type else TNone()
        old_ret = self._current_return_type
        old_consumed = self._consumed_streams
        old_pure = self._in_pure_fn
        self._current_return_type = ret_type
        self._consumed_streams = set()
        self._in_pure_fn = fn.is_pure

        match fn.body:
            case Block():
                self._check_block(fn.body, fn_scope)
            case Expr():
                self._infer_expr(fn.body, fn_scope)

        if fn.finally_block is not None:
            self._check_block(fn.finally_block, fn_scope)

        # RT-6-6-1: purity checking
        if fn.is_pure:
            self._check_purity(fn, fn_scope)

        self._current_return_type = old_ret
        self._consumed_streams = old_consumed
        self._in_pure_fn = old_pure

    def _check_type_decl(self, decl: TypeDecl) -> None:
        for s in decl.static_members:
            if s.value is not None:
                self._infer_expr(s.value, self._module_scope)

        for method in decl.methods:
            self._check_method_body(method, decl)

        for ctor in decl.constructors:
            self._check_constructor_body(ctor, decl)

    def _check_method_body(self, method: FnDecl, type_decl: TypeDecl) -> None:
        if method.body is None:
            return

        method_scope = TypeScope(parent=self._module_scope)
        self_type = TNamed("", type_decl.name, ())
        method_scope.define("self", self_type)

        for param in method.params:
            if param.name == "self":
                continue
            p_type = self._resolve_type_expr(param.type_ann)
            method_scope.define(param.name, p_type)

        ret_type = self._resolve_type_expr(method.return_type) if method.return_type else TNone()
        old_ret = self._current_return_type
        old_pure = self._in_pure_fn
        self._current_return_type = ret_type
        self._in_pure_fn = method.is_pure

        match method.body:
            case Block():
                self._check_block(method.body, method_scope)
            case Expr():
                self._infer_expr(method.body, method_scope)

        if method.finally_block is not None:
            self._check_block(method.finally_block, method_scope)

        if method.is_pure:
            self._check_purity(method, method_scope)

        self._current_return_type = old_ret
        self._in_pure_fn = old_pure

    def _check_constructor_body(self, ctor: ConstructorDecl,
                                type_decl: TypeDecl) -> None:
        ctor_scope = TypeScope(parent=self._module_scope)
        self_type = TNamed("", type_decl.name, ())
        ctor_scope.define("self", self_type)

        for param in ctor.params:
            if param.name == "self":
                continue
            p_type = self._resolve_type_expr(param.type_ann)
            ctor_scope.define(param.name, p_type)

        old_ret = self._current_return_type
        self._current_return_type = self_type
        self._check_block(ctor.body, ctor_scope)
        self._current_return_type = old_ret

    # ------------------------------------------------------------------
    # resolve_type_expr: TypeExpr AST → Type
    # ------------------------------------------------------------------

    def _resolve_type_expr(self, te: TypeExpr | None) -> Type:
        if te is None:
            return TNone()

        match te:
            case NamedType(name=name, module_path=mp):
                if mp:
                    return TNamed(".".join(mp), name, ())
                builtin = _BUILTIN_TYPES.get(name)
                if builtin is not None:
                    return builtin
                # User-defined type or type parameter
                info = self._type_registry.get(name)
                if info is not None:
                    if info.is_sum_type and info.sum_type:
                        return info.sum_type
                    return TNamed("", name, ())
                # Could be a type variable
                return TTypeVar(name)

            case GenericType(base=base, args=args):
                resolved_args = tuple(self._resolve_type_expr(a) for a in args)
                match base:
                    case NamedType(name="option"):
                        return TOption(resolved_args[0]) if resolved_args else TOption(TAny())
                    case NamedType(name="result"):
                        ok = resolved_args[0] if len(resolved_args) > 0 else TAny()
                        err = resolved_args[1] if len(resolved_args) > 1 else TAny()
                        return TResult(ok, err)
                    case NamedType(name="array"):
                        return TArray(resolved_args[0]) if resolved_args else TArray(TAny())
                    case NamedType(name="stream"):
                        return TStream(resolved_args[0]) if resolved_args else TStream(TAny())
                    case NamedType(name="buffer"):
                        return TBuffer(resolved_args[0]) if resolved_args else TBuffer(TAny())
                    case NamedType(name="map"):
                        k = resolved_args[0] if len(resolved_args) > 0 else TAny()
                        v = resolved_args[1] if len(resolved_args) > 1 else TAny()
                        return TMap(k, v)
                    case NamedType(name="set"):
                        return TSet(resolved_args[0]) if resolved_args else TSet(TAny())
                    case NamedType(name=name):
                        return TNamed("", name, resolved_args)
                    case _:
                        base_t = self._resolve_type_expr(base)
                        if isinstance(base_t, TNamed):
                            return TNamed(base_t.module, base_t.name, resolved_args)
                        return base_t

            case OptionType(inner=inner):
                return TOption(self._resolve_type_expr(inner))

            case FnType(params=params, ret=ret):
                return TFn(
                    tuple(self._resolve_type_expr(p) for p in params),
                    self._resolve_type_expr(ret), False)

            case TupleType(elements=elems):
                return TTuple(tuple(self._resolve_type_expr(e) for e in elems))

            case MutType(inner=inner):
                return self._resolve_type_expr(inner)

            case ImutType(inner=inner):
                return self._resolve_type_expr(inner)

            case _:
                return TAny()

    # ------------------------------------------------------------------
    # Expression inference (RT-6-2-2 through RT-6-2-8)
    # ------------------------------------------------------------------

    def _infer_expr(self, expr: Expr, scope: TypeScope) -> Type:
        t = self._infer_expr_inner(expr, scope)
        self._types[expr] = t
        return t

    def _infer_expr_inner(self, expr: Expr, scope: TypeScope) -> Type:
        match expr:
            # RT-6-2-3: Literals
            case IntLit(suffix=suffix):
                if suffix and suffix in _INT_SUFFIXES:
                    return _INT_SUFFIXES[suffix]
                return TInt(32, True)

            case FloatLit(suffix=suffix):
                if suffix and suffix in _FLOAT_SUFFIXES:
                    return _FLOAT_SUFFIXES[suffix]
                return TFloat(64)

            case BoolLit():
                return TBool()

            case StringLit():
                return TString()

            case FStringExpr(parts=parts):
                for part in parts:
                    if isinstance(part, Expr):
                        self._infer_expr(part, scope)
                return TString()

            case CharLit():
                return TChar()

            case NoneLit():
                return TOption(TAny())

            # Identifiers
            case Ident(name=name, module_path=mp):
                if mp:
                    ns = mp[0]
                    t = scope.lookup(ns)
                    return t if t is not None else TAny()
                t = scope.lookup(name)
                if t is not None:
                    # RT-6-5-3: track stream consumption
                    if isinstance(t, TStream):
                        self._check_stream_consumption(name, expr)
                    return t
                return TAny()

            # RT-6-2-4: Binary operators
            case BinOp(op=op, left=left, right=right):
                lt = self._infer_expr(left, scope)
                rt = self._infer_expr(right, scope)

                if op in _ARITHMETIC_OPS:
                    if op == "+" and isinstance(lt, TString) and isinstance(rt, TString):
                        return TString()
                    if not isinstance(lt, _NUMERIC_TYPES) or not isinstance(rt, _NUMERIC_TYPES):
                        raise self._error(
                            f"arithmetic operator '{op}' requires numeric "
                            f"operands, got {self._type_name(lt)} and "
                            f"{self._type_name(rt)}", expr)
                    if not self._types_equal(lt, rt):
                        raise self._error(
                            f"mixed-type arithmetic: {self._type_name(lt)} "
                            f"and {self._type_name(rt)} (use cast<T>)", expr)
                    return lt

                if op in _COMPARISON_OPS:
                    return TBool()

                if op in _LOGICAL_OPS:
                    return TBool()

                if op == "===":
                    # RT-6-7-3: === requires structural types
                    if isinstance(lt, (TInt, TFloat, TBool, TChar, TByte, TString)):
                        raise self._error(
                            f"'===' requires structural types, not "
                            f"{self._type_name(lt)}", expr)
                    return TBool()

                return TAny()

            case UnaryOp(op=op, operand=operand):
                ot = self._infer_expr(operand, scope)
                if op == "!" and not isinstance(ot, TBool):
                    raise self._error(
                        f"'!' requires bool operand, got "
                        f"{self._type_name(ot)}", expr)
                if op == "-" and not isinstance(ot, _NUMERIC_TYPES):
                    raise self._error(
                        f"unary '-' requires numeric operand, got "
                        f"{self._type_name(ot)}", expr)
                return ot

            # RT-6-2-5: Function calls
            case Call(callee=callee, args=args):
                callee_t = self._infer_expr(callee, scope)
                arg_types = [self._infer_expr(a, scope) for a in args]

                if isinstance(callee_t, TFn):
                    self._check_call_args(callee_t, arg_types, args, expr)
                    return callee_t.ret
                # Calling a non-function — might be a constructor or TAny
                if isinstance(callee_t, TAny):
                    return TAny()
                return TAny()

            case MethodCall(receiver=receiver, method=method_name,
                            args=args):
                # Check if the resolver bound this to a namespace symbol
                resolved_sym = self._resolved.symbols.get(expr)
                if resolved_sym is not None and resolved_sym.kind in (
                        SymbolKind.FN, SymbolKind.IMPORT):
                    # Namespace function call (e.g. io.println)
                    self._infer_expr(receiver, scope)
                    arg_types = [self._infer_expr(a, scope) for a in args]
                    fn_decl = resolved_sym.decl
                    if isinstance(fn_decl, FnDecl):
                        fn_type = self._fn_decl_type(fn_decl)
                        self._check_call_args(fn_type, arg_types, args, expr)
                        return fn_type.ret
                    return TAny()

                recv_t = self._infer_expr(receiver, scope)
                arg_types = [self._infer_expr(a, scope) for a in args]

                # Look up method on the receiver type
                method_type = self._lookup_method(recv_t, method_name, expr)
                if method_type is not None:
                    self._check_call_args(method_type, arg_types, args, expr)
                    return method_type.ret
                return TAny()

            case FieldAccess(receiver=receiver, field=field_name):
                recv_t = self._infer_expr(receiver, scope)

                # Static member access (resolver already validated)
                resolved_sym = self._resolved.symbols.get(expr)
                if resolved_sym is not None:
                    if resolved_sym.kind == SymbolKind.STATIC:
                        if resolved_sym.type_ann:
                            return self._resolve_type_expr(resolved_sym.type_ann)
                    # Import namespace access
                    if resolved_sym.kind in (SymbolKind.FN, SymbolKind.TYPE,
                                             SymbolKind.CONSTRUCTOR):
                        if resolved_sym.type_ann:
                            return self._resolve_type_expr(resolved_sym.type_ann)

                # Instance field access
                ft = self._lookup_field(recv_t, field_name, expr)
                return ft if ft is not None else TAny()

            case IndexAccess(receiver=receiver, index=index):
                recv_t = self._infer_expr(receiver, scope)
                self._infer_expr(index, scope)

                match recv_t:
                    case TArray(element=elem):
                        return TOption(elem)
                    case TMap(value=val):
                        return TOption(val)
                    case TTuple(elements=elems):
                        if isinstance(index, IntLit):
                            idx = index.value
                            if 0 <= idx < len(elems):
                                return elems[idx]
                        return TAny()
                    case _:
                        return TAny()

            # RT-6-2-8: Lambda
            case Lambda(params=params, body=body):
                lam_scope = TypeScope(parent=scope)
                p_types = []
                for p in params:
                    pt = self._resolve_type_expr(p.type_ann)
                    lam_scope.define(p.name, pt)
                    p_types.append(pt)

                match body:
                    case Block():
                        body_t = self._infer_block_type(body, lam_scope)
                    case Expr():
                        body_t = self._infer_expr(body, lam_scope)

                return TFn(tuple(p_types), body_t, False)

            case TupleExpr(elements=elements):
                elem_types = tuple(self._infer_expr(e, scope) for e in elements)
                return TTuple(elem_types)

            case ArrayLit(elements=elements):
                if not elements:
                    return TArray(TAny())
                first = self._infer_expr(elements[0], scope)
                for elem in elements[1:]:
                    et = self._infer_expr(elem, scope)
                    if not self._is_assignable(et, first):
                        raise self._error(
                            f"array element type mismatch: expected "
                            f"{self._type_name(first)}, got "
                            f"{self._type_name(et)}", elem)
                return TArray(first)

            case RecordLit(fields=fields):
                f_types = []
                for name, val in fields:
                    vt = self._infer_expr(val, scope)
                    f_types.append((name, vt))
                return TRecord(tuple(f_types))

            case TypeLit(type_name=type_name, fields=fields, spread=spread):
                info = self._type_registry.get(type_name)
                named_t = TNamed("", type_name, ())

                for _, val in fields:
                    self._infer_expr(val, scope)

                if spread is not None:
                    self._infer_expr(spread, scope)

                if info is not None:
                    # Verify field types match
                    for fname, val in fields:
                        val_t = self._types.get(val)
                        expected_t = info.fields.get(fname)
                        if expected_t is not None and val_t is not None:
                            if not self._is_assignable(val_t, expected_t):
                                raise self._error(
                                    f"field '{fname}' expects "
                                    f"{self._type_name(expected_t)}, got "
                                    f"{self._type_name(val_t)}", val)

                return named_t

            # RT-6-2-7: If expression
            case IfExpr(condition=cond, then_branch=then_b,
                        else_branch=else_b):
                cond_t = self._infer_expr(cond, scope)
                if not isinstance(cond_t, (TBool, TAny)):
                    raise self._error(
                        f"if condition must be bool, got "
                        f"{self._type_name(cond_t)}", cond)

                then_t = self._infer_block_type(then_b, scope)

                if else_b is None:
                    return TNone()
                elif isinstance(else_b, Block):
                    else_t = self._infer_block_type(else_b, scope)
                else:
                    else_t = self._infer_expr(else_b, scope)

                if self._is_assignable(then_t, else_t):
                    return else_t
                if self._is_assignable(else_t, then_t):
                    return then_t
                return then_t  # Allow mismatched branches for now

            case MatchExpr(subject=subject, arms=arms):
                subj_t = self._infer_expr(subject, scope)
                self._check_exhaustiveness(subj_t, arms, expr)
                arm_types = []
                for arm in arms:
                    arm_scope = TypeScope(parent=scope)
                    self._bind_pattern_types(arm.pattern, subj_t, arm_scope)
                    match arm.body:
                        case Block():
                            at = self._infer_block_type(arm.body, arm_scope)
                        case Expr():
                            at = self._infer_expr(arm.body, arm_scope)
                    arm_types.append(at)
                return arm_types[0] if arm_types else TNone()

            # Composition chain (RT-6-3-1)
            case CompositionChain(elements=elements):
                return self._infer_chain(elements, scope, expr)

            case FanOut(branches=branches):
                results = []
                for branch in branches:
                    bt = self._infer_expr(branch.expr, scope)
                    results.append(bt)
                if len(results) == 1:
                    return results[0]
                return TTuple(tuple(results))

            case TernaryExpr(condition=cond, then_expr=then_e,
                             else_expr=else_e):
                cond_t = self._infer_expr(cond, scope)
                if not isinstance(cond_t, (TBool, TAny)):
                    raise self._error(
                        f"ternary condition must be bool, got "
                        f"{self._type_name(cond_t)}", cond)
                then_t = self._infer_expr(then_e, scope)
                else_t = self._infer_expr(else_e, scope)
                return then_t

            case CopyExpr(inner=inner):
                return self._infer_expr(inner, scope)

            case SomeExpr(inner=inner):
                inner_t = self._infer_expr(inner, scope)
                return TOption(inner_t)

            case OkExpr(inner=inner):
                inner_t = self._infer_expr(inner, scope)
                return TResult(inner_t, TAny())

            case ErrExpr(inner=inner):
                inner_t = self._infer_expr(inner, scope)
                return TResult(TAny(), inner_t)

            case CoerceExpr(inner=inner, target_type=target):
                inner_t = self._infer_expr(inner, scope)
                if target is not None:
                    target_t = self._resolve_type_expr(target)
                elif self._current_return_type is not None:
                    target_t = self._current_return_type
                else:
                    return inner_t
                # RT-6-7-2: coerce requires congruence
                if not self._is_congruent(inner_t, target_t):
                    raise self._error(
                        f"coerce requires structurally congruent types; "
                        f"source is {self._type_name(inner_t)} but "
                        f"target is {self._type_name(target_t)}", expr)
                return target_t

            case CastExpr(inner=inner, target_type=target):
                self._infer_expr(inner, scope)
                return self._resolve_type_expr(target)

            case SnapshotExpr(inner=inner):
                return self._infer_expr(inner, scope)

            case PropagateExpr(inner=inner):
                inner_t = self._infer_expr(inner, scope)
                if isinstance(inner_t, TResult):
                    return inner_t.ok_type
                raise self._error(
                    f"'?' propagation requires result type, got "
                    f"{self._type_name(inner_t)}", expr)

            case NullCoalesce(left=left, right=right):
                lt = self._infer_expr(left, scope)
                rt = self._infer_expr(right, scope)
                if isinstance(lt, TOption):
                    return lt.inner if not isinstance(lt.inner, TAny) else rt
                return lt

            case TypeofExpr(inner=inner):
                self._infer_expr(inner, scope)
                return TString()

            case CoroutineStart(call=call):
                return self._infer_expr(call, scope)

            case _:
                return TAny()

    # ------------------------------------------------------------------
    # Statement checking
    # ------------------------------------------------------------------

    def _check_stmt(self, stmt: Stmt, scope: TypeScope) -> None:
        match stmt:
            # RT-6-2-6: Let statement
            case LetStmt(name=name, type_ann=type_ann, value=value):
                val_t = self._infer_expr(value, scope)

                if type_ann is not None:
                    expected = self._resolve_type_expr(type_ann)
                    # RT-6-4-5: auto-lift T to option<T>
                    if (isinstance(expected, TOption)
                            and not isinstance(val_t, (TOption, TAny))
                            and self._is_assignable(val_t, expected.inner)):
                        val_t = TOption(val_t)
                    elif not self._is_assignable(val_t, expected):
                        raise self._error(
                            f"type mismatch in let binding '{name}': "
                            f"expected {self._type_name(expected)}, got "
                            f"{self._type_name(val_t)}", stmt)
                    scope.define(name, expected)
                else:
                    scope.define(name, val_t)

            case AssignStmt(target=target, value=value):
                val_t = self._infer_expr(value, scope)
                target_t = self._infer_expr(target, scope)

                # Check field mutability for field access targets
                if isinstance(target, FieldAccess):
                    self._check_field_mutability(target, scope)

                if not self._is_assignable(val_t, target_t):
                    raise self._error(
                        f"type mismatch in assignment: expected "
                        f"{self._type_name(target_t)}, got "
                        f"{self._type_name(val_t)}", stmt)

            case UpdateStmt(target=target, value=value):
                target_t = self._infer_expr(target, scope)
                if value is not None:
                    val_t = self._infer_expr(value, scope)
                if not isinstance(target_t, (_NUMERIC_TYPES[0], _NUMERIC_TYPES[1], TAny)):
                    raise self._error(
                        f"update operator requires numeric type, got "
                        f"{self._type_name(target_t)}", stmt)

            case ReturnStmt(value=value):
                if value is not None:
                    val_t = self._infer_expr(value, scope)
                    if self._current_return_type is not None:
                        expected = self._current_return_type
                        # Auto-lift for option return
                        if (isinstance(expected, TOption)
                                and not isinstance(val_t, (TOption, TAny))
                                and self._is_assignable(val_t, expected.inner)):
                            pass  # auto-lifted
                        elif not self._is_assignable(val_t, expected):
                            raise self._error(
                                f"return type mismatch: expected "
                                f"{self._type_name(expected)}, got "
                                f"{self._type_name(val_t)}", stmt)

            case YieldStmt(value=value):
                val_t = self._infer_expr(value, scope)

            case ThrowStmt(exception=exception):
                self._infer_expr(exception, scope)

            case BreakStmt():
                pass

            case ExprStmt(expr=ex):
                self._infer_expr(ex, scope)

            case IfStmt(condition=cond, then_branch=then_b,
                        else_branch=else_b):
                cond_t = self._infer_expr(cond, scope)
                if not isinstance(cond_t, (TBool, TAny)):
                    raise self._error(
                        f"if condition must be bool, got "
                        f"{self._type_name(cond_t)}", cond)
                self._check_block(then_b, scope)
                if else_b is not None:
                    if isinstance(else_b, Block):
                        self._check_block(else_b, scope)
                    else:
                        self._check_stmt(else_b, scope)

            case WhileStmt(condition=cond, body=body,
                           finally_block=fin):
                cond_t = self._infer_expr(cond, scope)
                if not isinstance(cond_t, (TBool, TAny)):
                    raise self._error(
                        f"while condition must be bool, got "
                        f"{self._type_name(cond_t)}", cond)
                self._check_block(body, scope)
                if fin is not None:
                    self._check_block(fin, scope)

            case ForStmt(var=var, var_type=var_type,
                         iterable=iterable, body=body,
                         finally_block=fin):
                iter_t = self._infer_expr(iterable, scope)
                elem_t: Type
                match iter_t:
                    case TStream(element=elem):
                        elem_t = elem
                    case TArray(element=elem):
                        elem_t = elem
                    case _:
                        elem_t = TAny()
                for_scope = TypeScope(parent=scope)
                if var_type is not None:
                    elem_t = self._resolve_type_expr(var_type)
                for_scope.define(var, elem_t)
                self._check_block(body, for_scope)
                if fin is not None:
                    self._check_block(fin, scope)

            case MatchStmt(subject=subject, arms=arms):
                subj_t = self._infer_expr(subject, scope)
                self._check_exhaustiveness(subj_t, arms, stmt)
                for arm in arms:
                    arm_scope = TypeScope(parent=scope)
                    self._bind_pattern_types(arm.pattern, subj_t, arm_scope)
                    match arm.body:
                        case Block():
                            self._check_block(arm.body, arm_scope)
                        case Expr():
                            self._infer_expr(arm.body, arm_scope)

            case TryStmt(body=body, retry_blocks=retries,
                         catch_blocks=catches, finally_block=fin):
                self._check_block(body, scope)
                for retry in retries:
                    r_scope = TypeScope(parent=scope)
                    r_scope.define(retry.exception_var,
                                   self._resolve_type_expr(retry.exception_type))
                    self._check_block(retry.body, r_scope)
                for catch in catches:
                    c_scope = TypeScope(parent=scope)
                    c_scope.define(catch.exception_var,
                                   self._resolve_type_expr(catch.exception_type))
                    self._check_block(catch.body, c_scope)
                if fin is not None:
                    f_scope = TypeScope(parent=scope)
                    if fin.exception_var:
                        f_scope.define(
                            fin.exception_var,
                            self._resolve_type_expr(fin.exception_type))
                    self._check_block(fin.body, f_scope)

    # ------------------------------------------------------------------
    # Block checking and type inference
    # ------------------------------------------------------------------

    def _check_block(self, block: Block, parent_scope: TypeScope) -> None:
        block_scope = TypeScope(parent=parent_scope)
        for stmt in block.stmts:
            self._check_stmt(stmt, block_scope)
        if block.finally_block is not None:
            self._check_block(block.finally_block, parent_scope)

    def _infer_block_type(self, block: Block,
                          parent_scope: TypeScope) -> Type:
        block_scope = TypeScope(parent=parent_scope)
        last_type: Type = TNone()
        for stmt in block.stmts:
            self._check_stmt(stmt, block_scope)
            if isinstance(stmt, ExprStmt):
                t = self._types.get(stmt.expr)
                if t is not None:
                    last_type = t
            elif isinstance(stmt, ReturnStmt):
                if stmt.value is not None:
                    t = self._types.get(stmt.value)
                    if t is not None:
                        last_type = t
        if block.finally_block is not None:
            self._check_block(block.finally_block, parent_scope)
        return last_type

    # ------------------------------------------------------------------
    # Composition chain type checking (RT-6-3-1 through RT-6-3-3)
    # ------------------------------------------------------------------

    def _infer_chain(self, elements: list[ChainElement],
                     scope: TypeScope, node: ASTNode) -> Type:
        if not elements:
            return TNone()

        stack: list[Type] = []
        for elem in elements:
            et = self._infer_expr(elem.expr, scope)

            if isinstance(et, TFn):
                arity = len(et.params)
                if arity == 0:
                    stack.append(et.ret)
                elif len(stack) >= arity:
                    # Pop arity values, check types, push result
                    arg_types = stack[-arity:]
                    stack = stack[:-arity]

                    for i, (arg_t, param_t) in enumerate(
                            zip(arg_types, et.params)):
                        # RT-6-3-2: auto-mapping
                        if (isinstance(arg_t, TStream)
                                and not isinstance(param_t, TStream)):
                            if self._is_assignable(arg_t.element, param_t):
                                # Auto-map: stream<T> -> fn(T):U
                                # becomes stream<U>
                                stack.append(TStream(et.ret))
                                break
                            else:
                                raise self._error(
                                    f"stream element type "
                                    f"{self._type_name(arg_t.element)} is not "
                                    f"assignable to parameter type "
                                    f"{self._type_name(param_t)}", node)
                        elif not self._is_assignable(arg_t, param_t):
                            raise self._error(
                                f"chain type mismatch: expected "
                                f"{self._type_name(param_t)}, got "
                                f"{self._type_name(arg_t)}", node)
                    else:
                        # Normal (non-auto-mapped) case
                        stack.append(et.ret)
                elif len(stack) > 0 and len(stack) < arity:
                    # RT-6-3-3: fan-out arity mismatch
                    raise self._error(
                        f"fan-out produces {len(stack)} values but "
                        f"'{self._expr_name(elem.expr)}' accepts "
                        f"{arity} parameters", node)
                else:
                    stack.append(et.ret)

            elif isinstance(et, TTuple):
                # Fan-out result: expand tuple onto stack
                for t in et.elements:
                    stack.append(t)
            else:
                stack.append(et)

        return stack[-1] if stack else TNone()

    # ------------------------------------------------------------------
    # Exhaustiveness checking (RT-6-4-1 through RT-6-4-4)
    # ------------------------------------------------------------------

    def _check_exhaustiveness(self, subject_type: Type,
                              arms: list[MatchArm],
                              node: ASTNode) -> None:
        has_wildcard = any(
            isinstance(arm.pattern, (WildcardPattern, BindPattern))
            for arm in arms)

        if has_wildcard:
            return  # Wildcard covers all cases

        # RT-6-4-1: sum type exhaustiveness
        if isinstance(subject_type, TSum):
            variant_names = {v.name for v in subject_type.variants}
            covered = set()
            for arm in arms:
                if isinstance(arm.pattern, VariantPattern):
                    covered.add(arm.pattern.variant_name)
            missing = variant_names - covered
            if missing:
                raise self._error(
                    f"match on {subject_type.name} is not exhaustive: "
                    f"missing variant(s) {', '.join(sorted(missing))}",
                    node)
            return

        # RT-6-4-2: option exhaustiveness
        if isinstance(subject_type, TOption):
            has_some = any(isinstance(a.pattern, SomePattern) for a in arms)
            has_none = any(isinstance(a.pattern, NonePattern) for a in arms)
            if not has_some or not has_none:
                missing = []
                if not has_some:
                    missing.append("some")
                if not has_none:
                    missing.append("none")
                raise self._error(
                    f"match on option is not exhaustive: missing "
                    f"{', '.join(missing)}", node)
            return

        # RT-6-4-3: result exhaustiveness
        if isinstance(subject_type, TResult):
            has_ok = any(isinstance(a.pattern, OkPattern) for a in arms)
            has_err = any(isinstance(a.pattern, ErrPattern) for a in arms)
            if not has_ok or not has_err:
                missing = []
                if not has_ok:
                    missing.append("ok")
                if not has_err:
                    missing.append("err")
                raise self._error(
                    f"match on result is not exhaustive: missing "
                    f"{', '.join(missing)}", node)
            return

        # RT-6-4-4: primitive match — warn, don't error
        if isinstance(subject_type, (TInt, TFloat, TString, TBool,
                                      TChar, TByte)):
            self._warnings.append(
                f"{self._file}:{node.line}:{node.col}: warning: "
                f"match on {self._type_name(subject_type)} may not be "
                f"exhaustive; consider adding a '_' arm")
            return

    # ------------------------------------------------------------------
    # Pattern type binding
    # ------------------------------------------------------------------

    def _bind_pattern_types(self, pat: Pattern, subject_type: Type,
                            scope: TypeScope) -> None:
        match pat:
            case WildcardPattern():
                pass

            case LiteralPattern():
                pass

            case BindPattern(name=name):
                scope.define(name, subject_type)

            case SomePattern(inner_var=var):
                inner = subject_type
                if isinstance(subject_type, TOption):
                    inner = subject_type.inner
                scope.define(var, inner)

            case NonePattern():
                pass

            case OkPattern(inner_var=var):
                inner = TAny()
                if isinstance(subject_type, TResult):
                    inner = subject_type.ok_type
                scope.define(var, inner)

            case ErrPattern(inner_var=var):
                inner = TAny()
                if isinstance(subject_type, TResult):
                    inner = subject_type.err_type
                scope.define(var, inner)

            case VariantPattern(variant_name=vname, bindings=bindings):
                if isinstance(subject_type, TSum):
                    for v in subject_type.variants:
                        if v.name == vname and v.fields is not None:
                            for i, binding in enumerate(bindings):
                                if i < len(v.fields):
                                    scope.define(binding, v.fields[i])
                                else:
                                    scope.define(binding, TAny())
                            break
                    else:
                        for binding in bindings:
                            scope.define(binding, TAny())
                else:
                    for binding in bindings:
                        scope.define(binding, TAny())

            case TuplePattern(elements=elements):
                if isinstance(subject_type, TTuple):
                    for i, elem in enumerate(elements):
                        elem_t = (subject_type.elements[i]
                                  if i < len(subject_type.elements)
                                  else TAny())
                        self._bind_pattern_types(elem, elem_t, scope)
                else:
                    for elem in elements:
                        self._bind_pattern_types(elem, TAny(), scope)

    # ------------------------------------------------------------------
    # Purity checking (RT-6-6-1, RT-6-6-2)
    # ------------------------------------------------------------------

    def _check_purity(self, fn: FnDecl, scope: TypeScope) -> None:
        # Check no :mut parameters
        for param in fn.params:
            if isinstance(param.type_ann, MutType):
                raise self._error(
                    f"pure function '{fn.name}' cannot accept :mut "
                    f"parameter '{param.name}'", fn)

        # Check body for impure calls
        if fn.body is not None:
            self._check_purity_body(fn.body, fn.name)

    def _check_purity_body(self, node: ASTNode, fn_name: str) -> None:
        match node:
            case Block(stmts=stmts):
                for stmt in stmts:
                    self._check_purity_body(stmt, fn_name)

            case ExprStmt(expr=expr):
                self._check_purity_body(expr, fn_name)

            case LetStmt(value=value):
                self._check_purity_body(value, fn_name)

            case ReturnStmt(value=value):
                if value is not None:
                    self._check_purity_body(value, fn_name)

            case Call(callee=callee, args=args):
                # Check if callee is a known non-pure function
                if isinstance(callee, Ident):
                    is_pure = self._purity_map.get(callee.name)
                    if is_pure is not None and not is_pure:
                        raise self._error(
                            f"pure function '{fn_name}' cannot call "
                            f"non-pure function '{callee.name}'", node)
                for arg in args:
                    self._check_purity_body(arg, fn_name)

            case BinOp(left=left, right=right):
                self._check_purity_body(left, fn_name)
                self._check_purity_body(right, fn_name)

            case UnaryOp(operand=operand):
                self._check_purity_body(operand, fn_name)

            case IfExpr(condition=cond, then_branch=then_b,
                        else_branch=else_b):
                self._check_purity_body(cond, fn_name)
                self._check_purity_body(then_b, fn_name)
                if else_b is not None:
                    self._check_purity_body(else_b, fn_name)

            case IfStmt(condition=cond, then_branch=then_b,
                        else_branch=else_b):
                self._check_purity_body(cond, fn_name)
                self._check_purity_body(then_b, fn_name)
                if else_b is not None:
                    self._check_purity_body(else_b, fn_name)

            case _:
                pass  # Other nodes don't affect purity

    # ------------------------------------------------------------------
    # Congruence checking (RT-6-7-1)
    # ------------------------------------------------------------------

    def _is_congruent(self, a: Type, b: Type) -> bool:
        """Two types are congruent if they have the same field names/types."""
        a_fields = self._get_struct_fields(a)
        b_fields = self._get_struct_fields(b)

        if a_fields is None or b_fields is None:
            return False

        return a_fields == b_fields

    def _get_struct_fields(self, t: Type) -> dict[str, Type] | None:
        if isinstance(t, TNamed):
            info = self._type_registry.get(t.name)
            if info is not None:
                return dict(info.fields)
        if isinstance(t, TRecord):
            return dict(t.fields)
        return None

    # ------------------------------------------------------------------
    # Call argument checking (RT-6-5-1, RT-6-5-2)
    # ------------------------------------------------------------------

    def _check_call_args(self, fn_type: TFn, arg_types: list[Type],
                         arg_nodes: list[Expr],
                         call_node: ASTNode) -> None:
        if len(arg_types) != len(fn_type.params):
            raise self._error(
                f"expected {len(fn_type.params)} arguments, got "
                f"{len(arg_types)}", call_node)

        for i, (arg_t, param_t) in enumerate(
                zip(arg_types, fn_type.params)):
            # RT-6-4-5: auto-lift T to option<T>
            if (isinstance(param_t, TOption)
                    and not isinstance(arg_t, (TOption, TAny))
                    and self._is_assignable(arg_t, param_t.inner)):
                continue

            if not self._is_assignable(arg_t, param_t):
                raise self._error(
                    f"argument {i + 1} type mismatch: expected "
                    f"{self._type_name(param_t)}, got "
                    f"{self._type_name(arg_t)}", call_node)

    def _check_mut_param_args(self, fn_decl: FnDecl,
                              arg_nodes: list[Expr],
                              call_node: ASTNode) -> None:
        """RT-6-5-2: check :mut parameter passing rules."""
        for i, param in enumerate(fn_decl.params):
            if i >= len(arg_nodes):
                break
            if isinstance(param.type_ann, MutType):
                arg = arg_nodes[i]
                if isinstance(arg, Ident):
                    sym = self._resolved.symbols.get(arg)
                    if sym is not None and not sym.is_mut:
                        raise self._error(
                            f"cannot pass immutable binding "
                            f"'{arg.name}' to :mut parameter "
                            f"'{param.name}'; use @ to pass a copy",
                            call_node)
                elif not isinstance(arg, CopyExpr):
                    raise self._error(
                        f"cannot pass immutable binding to :mut "
                        f"parameter '{param.name}'; use @ to pass a copy",
                        call_node)

    # ------------------------------------------------------------------
    # Stream single-consumer (RT-6-5-3)
    # ------------------------------------------------------------------

    def _check_stream_consumption(self, name: str,
                                  node: ASTNode) -> None:
        if name in self._consumed_streams:
            raise self._error(
                f"stream '{name}' has already been consumed; "
                f"streams can only have one consumer", node)
        self._consumed_streams.add(name)

    # ------------------------------------------------------------------
    # Field mutability checking
    # ------------------------------------------------------------------

    def _check_field_mutability(self, fa: FieldAccess,
                                scope: TypeScope) -> None:
        recv_t = self._types.get(fa.receiver)
        if recv_t is None:
            return
        if isinstance(recv_t, TNamed):
            info = self._type_registry.get(recv_t.name)
            if info is not None:
                is_mut = info.field_mutability.get(fa.field)
                if is_mut is not None and not is_mut:
                    raise self._error(
                        f"cannot assign to immutable field "
                        f"'{fa.field}'", fa)

    # ------------------------------------------------------------------
    # Type compatibility
    # ------------------------------------------------------------------

    def _is_assignable(self, source: Type, target: Type) -> bool:
        if isinstance(source, TAny) or isinstance(target, TAny):
            return True

        if self._types_equal(source, target):
            return True

        # T assignable to option<T>
        if isinstance(target, TOption):
            if isinstance(source, TOption):
                return self._is_assignable(source.inner, target.inner)
            return self._is_assignable(source, target.inner)

        # TNone assignable to any option
        if isinstance(source, TNone) and isinstance(target, TOption):
            return True

        # TResult assignability: check ok_type and err_type
        if isinstance(source, TResult) and isinstance(target, TResult):
            return (self._is_assignable(source.ok_type, target.ok_type) and
                    self._is_assignable(source.err_type, target.err_type))

        # TTypeVar matches if names match
        if (isinstance(source, TTypeVar) and isinstance(target, TTypeVar)
                and source.name == target.name):
            return True

        # TAlias: unwrap
        if isinstance(source, TAlias):
            return self._is_assignable(source.underlying, target)
        if isinstance(target, TAlias):
            return self._is_assignable(source, target.underlying)

        return False

    def _types_equal(self, a: Type, b: Type) -> bool:
        if type(a) != type(b):
            return False
        return a == b

    # ------------------------------------------------------------------
    # Method and field lookup
    # ------------------------------------------------------------------

    def _lookup_method(self, recv_type: Type, method_name: str,
                       node: ASTNode) -> TFn | None:
        if isinstance(recv_type, TNamed):
            info = self._type_registry.get(recv_type.name)
            if info is not None:
                m = info.methods.get(method_name)
                if m is not None:
                    return m
        return None

    def _lookup_field(self, recv_type: Type, field_name: str,
                      node: ASTNode) -> Type | None:
        if isinstance(recv_type, TNamed):
            info = self._type_registry.get(recv_type.name)
            if info is not None:
                f = info.fields.get(field_name)
                if f is not None:
                    return f
                s = info.statics.get(field_name)
                if s is not None:
                    return s

        if isinstance(recv_type, TTuple):
            if field_name.isdigit():
                idx = int(field_name)
                if 0 <= idx < len(recv_type.elements):
                    return recv_type.elements[idx]

        if isinstance(recv_type, TRecord):
            for name, ft in recv_type.fields:
                if name == field_name:
                    return ft

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fn_decl_type(self, fn: FnDecl) -> TFn:
        params = []
        for p in fn.params:
            params.append(self._resolve_type_expr(p.type_ann))
        ret = self._resolve_type_expr(fn.return_type) if fn.return_type else TNone()
        return TFn(tuple(params), ret, fn.is_pure)

    def _type_name(self, t: Type) -> str:
        match t:
            case TInt(width=w, signed=s):
                if s:
                    return "int" if w == 32 else f"int{w}"
                return "uint" if w == 32 else f"uint{w}"
            case TFloat(width=w):
                return "float" if w == 64 else f"float{w}"
            case TBool():
                return "bool"
            case TChar():
                return "char"
            case TByte():
                return "byte"
            case TString():
                return "string"
            case TNone():
                return "none"
            case TOption(inner=inner):
                return f"option<{self._type_name(inner)}>"
            case TResult(ok_type=ok_t, err_type=err_t):
                return f"result<{self._type_name(ok_t)}, {self._type_name(err_t)}>"
            case TTuple(elements=elems):
                return f"({', '.join(self._type_name(e) for e in elems)})"
            case TArray(element=elem):
                return f"array<{self._type_name(elem)}>"
            case TStream(element=elem):
                return f"stream<{self._type_name(elem)}>"
            case TFn(params=params, ret=ret):
                p = ", ".join(self._type_name(p) for p in params)
                return f"fn({p}): {self._type_name(ret)}"
            case TNamed(name=name):
                return name
            case TSum(name=name):
                return name
            case TAlias(name=name):
                return name
            case TTypeVar(name=name):
                return name
            case TAny():
                return "any"
            case TRecord():
                return "record"
            case _:
                return str(t)

    def _expr_name(self, expr: Expr) -> str:
        if isinstance(expr, Ident):
            return expr.name
        return type(expr).__name__

    def _error(self, message: str, node: ASTNode) -> ReFlowTypeError:
        return ReFlowTypeError(
            message=message,
            file=self._file,
            line=node.line,
            col=node.col,
        )
