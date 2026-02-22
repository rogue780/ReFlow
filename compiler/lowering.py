# compiler/lowering.py — Typed AST → LModule.
# No C syntax. No formatting.
#
# Implements RT-7-1-1 through RT-7-5-3.
from __future__ import annotations

from dataclasses import dataclass, field

from compiler.errors import EmitError
from compiler.mangler import (
    mangle, mangle_stream_frame, mangle_stream_next, mangle_stream_free,
    mangle_closure_frame, mangle_closure_fn, mangle_fn_wrapper,
    mangle_stream_wrapper, mangle_exception_frame,
)
from compiler.ast_nodes import (
    # Base
    ASTNode, TypeExpr, Expr, Stmt, Decl, Block, Pattern,
    # Type expressions
    NamedType, GenericType, OptionType, FnType, TupleType, MutType, ImutType,
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
    MatchStmt, TryStmt, MatchArm,
    CatchBlock, FinallyBlock, RetryBlock,
    # Patterns
    WildcardPattern, LiteralPattern, BindPattern, SomePattern, NonePattern,
    OkPattern, ErrPattern, VariantPattern, TuplePattern,
    # Declarations
    FnDecl, TypeDecl, Param, StaticMemberDecl, SumVariantDecl,
    # Top-level
    Module,
)
from compiler.typechecker import (
    TypedModule, Type,
    TInt, TFloat, TBool, TChar, TByte, TString, TNone,
    TOption, TResult, TTuple, TArray, TStream, TCoroutine, TBuffer, TMap, TSet,
    TFn, TRecord, TNamed, TAlias, TSum, TVariant, TTypeVar, TAny,
)
from compiler.resolver import ResolvedModule, Symbol, SymbolKind


# ---------------------------------------------------------------------------
# LType hierarchy (RT-7-1-1)
# ---------------------------------------------------------------------------

@dataclass
class LType:
    """Base class for lowered types."""
    pass


@dataclass
class LInt(LType):
    width: int
    signed: bool


@dataclass
class LFloat(LType):
    width: int


@dataclass
class LBool(LType):
    pass


@dataclass
class LChar(LType):
    pass


@dataclass
class LByte(LType):
    pass


@dataclass
class LPtr(LType):
    inner: LType


@dataclass
class LStruct(LType):
    c_name: str


@dataclass
class LVoid(LType):
    pass


@dataclass
class LFnPtr(LType):
    params: list[LType]
    ret: LType


# ---------------------------------------------------------------------------
# LExpr hierarchy (RT-7-1-1)
# ---------------------------------------------------------------------------

@dataclass
class LExpr:
    """Base class for lowered expressions."""
    pass


@dataclass
class LLit(LExpr):
    value: str
    c_type: LType


@dataclass
class LVar(LExpr):
    c_name: str
    c_type: LType


@dataclass
class LCall(LExpr):
    fn_name: str
    args: list[LExpr]
    c_type: LType


@dataclass
class LIndirectCall(LExpr):
    fn_ptr: LExpr
    args: list[LExpr]
    c_type: LType


@dataclass
class LBinOp(LExpr):
    op: str
    left: LExpr
    right: LExpr
    c_type: LType


@dataclass
class LUnary(LExpr):
    op: str
    operand: LExpr
    c_type: LType


@dataclass
class LFieldAccess(LExpr):
    obj: LExpr
    field: str
    c_type: LType


@dataclass
class LArrow(LExpr):
    ptr: LExpr
    field: str
    c_type: LType


@dataclass
class LIndex(LExpr):
    arr: LExpr
    idx: LExpr
    c_type: LType


@dataclass
class LCast(LExpr):
    inner: LExpr
    c_type: LType


@dataclass
class LAddrOf(LExpr):
    inner: LExpr
    c_type: LType


@dataclass
class LDeref(LExpr):
    inner: LExpr
    c_type: LType


@dataclass
class LCompound(LExpr):
    fields: list[tuple[str, LExpr]]
    c_type: LType


@dataclass
class LCheckedArith(LExpr):
    op: str
    left: LExpr
    right: LExpr
    c_type: LType


@dataclass
class LSizeOf(LExpr):
    c_type: LType


@dataclass
class LArrayData(LExpr):
    """A C compound literal array: (type[]){e1, e2, ...}."""
    elements: list[LExpr]
    elem_type: LType
    c_type: LType


@dataclass
class LTernary(LExpr):
    cond: LExpr
    then_expr: LExpr
    else_expr: LExpr
    c_type: LType


# ---------------------------------------------------------------------------
# LStmt hierarchy (RT-7-1-1)
# ---------------------------------------------------------------------------

@dataclass
class LStmt:
    """Base class for lowered statements."""
    pass


@dataclass
class LVarDecl(LStmt):
    c_name: str
    c_type: LType
    init: LExpr | None


@dataclass
class LAssign(LStmt):
    target: LExpr
    value: LExpr


@dataclass
class LReturn(LStmt):
    value: LExpr | None


@dataclass
class LIf(LStmt):
    cond: LExpr
    then: list[LStmt]
    else_: list[LStmt]


@dataclass
class LWhile(LStmt):
    cond: LExpr
    body: list[LStmt]


@dataclass
class LBlock(LStmt):
    stmts: list[LStmt]


@dataclass
class LExprStmt(LStmt):
    expr: LExpr


@dataclass
class LGoto(LStmt):
    label: str


@dataclass
class LLabel(LStmt):
    name: str


@dataclass
class LSwitch(LStmt):
    value: LExpr
    cases: list[tuple[int, list[LStmt]]]
    default: list[LStmt]


@dataclass
class LBreak(LStmt):
    pass


# ---------------------------------------------------------------------------
# Top-level LIR nodes (RT-7-1-1)
# ---------------------------------------------------------------------------

@dataclass
class LTypeDef:
    c_name: str
    fields: list[tuple[str, LType]]


@dataclass
class LFnDef:
    c_name: str
    params: list[tuple[str, LType]]
    ret: LType
    body: list[LStmt]
    is_pure: bool
    source_name: str = ""


@dataclass
class LStaticDef:
    c_name: str
    c_type: LType
    init: LExpr | None
    is_mut: bool


@dataclass
class LModule:
    type_defs: list[LTypeDef]
    fn_defs: list[LFnDef]
    static_defs: list[LStaticDef]
    entry_point: str | None = None  # mangled C name of the entry function


# ---------------------------------------------------------------------------
# C type name helpers for option/result/tuple registries
# ---------------------------------------------------------------------------

def _ltype_c_name(lt: LType) -> str:
    """Return a short C-friendly name fragment for an LType, used in registry keys."""
    match lt:
        case LInt(width=w, signed=s):
            prefix = "rf_int" if s else "rf_uint"
            return prefix if w == 32 else f"{prefix}{w}"
        case LFloat(width=w):
            return "rf_float" if w == 64 else f"rf_float{w}"
        case LBool():
            return "rf_bool"
        case LChar():
            return "rf_char"
        case LByte():
            return "rf_byte"
        case LVoid():
            return "void"
        case LPtr(inner=LStruct(c_name=name)):
            return f"{name}_ptr"
        case LPtr():
            return "ptr"
        case LStruct(c_name=name):
            return name
        case _:
            return "unknown"


# ---------------------------------------------------------------------------
# Option type name mapping — uses pre-defined runtime types where possible
# ---------------------------------------------------------------------------

_BUILTIN_OPTION_MAP: dict[str, str] = {
    "rf_int": "RF_Option_int",
    "rf_int16": "RF_Option_int16",
    "rf_int32": "RF_Option_int32",
    "rf_int64": "RF_Option_int64",
    "rf_uint": "RF_Option_uint",
    "rf_uint16": "RF_Option_uint16",
    "rf_uint32": "RF_Option_uint32",
    "rf_uint64": "RF_Option_uint64",
    "rf_float": "RF_Option_float",
    "rf_float32": "RF_Option_float32",
    "rf_float64": "RF_Option_float64",
    "rf_bool": "RF_Option_bool",
    "rf_byte": "RF_Option_byte",
    "rf_char": "RF_Option_char",
}


# ---------------------------------------------------------------------------
# Builtin type annotation resolution
# ---------------------------------------------------------------------------

_BUILTIN_TYPE_ANNS: dict[str, Type] = {
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


# ---------------------------------------------------------------------------
# Lowerer (RT-7-2-1 through RT-7-5-3)
# ---------------------------------------------------------------------------

class Lowerer:
    """Transform a TypedModule into an LModule."""

    def __init__(self, typed: TypedModule) -> None:
        self._typed = typed
        self._module: Module = typed.module
        self._resolved: ResolvedModule = typed.resolved
        self._types: dict[ASTNode, Type] = typed.types
        self._file = typed.module.filename
        self._module_path = ".".join(typed.module.path) if typed.module.path else "main"

        # LIR output accumulators
        self._type_defs: list[LTypeDef] = []
        self._fn_defs: list[LFnDef] = []
        self._static_defs: list[LStaticDef] = []

        # Type registries — avoid duplicate LTypeDefs
        self._option_registry: dict[str, str] = {}   # key → c_name
        self._result_registry: dict[str, str] = {}
        self._tuple_registry: dict[str, str] = {}
        self._sum_registry: dict[str, str] = {}

        # Temp variable counter
        self._tmp_counter: int = 0

        # Pending statements generated during expression lowering
        self._pending_stmts: list[LStmt] = []

        # Current function's return type — used by ok/err/none to pick correct struct
        self._current_fn_return_type: Type | None = None

        # Closure support
        self._lambda_counter: int = 0
        self._current_fn_name: str = ""
        self._fn_wrapper_registry: dict[str, str] = {}
        self._capture_remap: dict[str, tuple[str, LType]] = {}

        # Exception frame counter (per-function)
        self._exception_frame_counter: int = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def lower(self) -> LModule:
        """Run the lowering pass."""
        for decl in self._module.decls:
            match decl:
                case FnDecl():
                    self._lower_fn_decl(decl)
                case TypeDecl():
                    self._lower_type_decl(decl)

        # Detect entry point: a top-level function named "main".
        entry_point: str | None = None
        for fn_def in self._fn_defs:
            if fn_def.source_name.endswith(".main"):
                entry_point = fn_def.c_name
                break

        return LModule(
            type_defs=self._type_defs,
            fn_defs=self._fn_defs,
            static_defs=self._static_defs,
            entry_point=entry_point,
        )

    # ------------------------------------------------------------------
    # Type lowering (RT-7-2-1)
    # ------------------------------------------------------------------

    def _lower_type(self, t: Type) -> LType:
        match t:
            case TInt(width=w, signed=s):
                return LInt(w, s)
            case TFloat(width=w):
                return LFloat(w)
            case TBool():
                return LBool()
            case TChar():
                return LChar()
            case TByte():
                return LByte()
            case TString():
                return LPtr(LStruct("RF_String"))
            case TNone():
                return LVoid()
            case TArray():
                return LPtr(LStruct("RF_Array"))
            case TStream():
                return LPtr(LStruct("RF_Stream"))
            case TCoroutine():
                return LPtr(LStruct("RF_Coroutine"))
            case TBuffer():
                return LPtr(LStruct("RF_Buffer"))
            case TMap():
                return LPtr(LStruct("RF_Map"))
            case TSet():
                return LPtr(LStruct("RF_Set"))
            case TOption(inner=inner):
                return self._lower_option_type(inner)
            case TResult(ok_type=ok_t, err_type=err_t):
                return self._lower_result_type(ok_t, err_t)
            case TTuple(elements=elems):
                return self._lower_tuple_type(elems)
            case TNamed(module=mod, name=name):
                c_name = mangle(mod if mod else self._module_path, name,
                                file=self._file, line=0, col=0)
                return LStruct(c_name)
            case TFn():
                # Function types lower to closure struct pointers
                return LPtr(LStruct("RF_Closure"))
            case TSum(name=name):
                c_name = mangle(self._module_path, name,
                                file=self._file, line=0, col=0)
                return LStruct(c_name)
            case TRecord(fields=fields):
                # Anonymous records — generate a struct
                return LStruct("rf_record")
            case TAlias(underlying=underlying):
                return self._lower_type(underlying)
            case TTypeVar():
                # Generic type variable — lower to void* for bootstrap
                return LPtr(LVoid())
            case TAny():
                # Unresolved — lower to void* for bootstrap
                return LPtr(LVoid())
            case _:
                return LVoid()

    def _lower_option_type(self, inner: Type) -> LType:
        """Lower option<T> to the appropriate option struct type."""
        inner_lt = self._lower_type(inner)
        inner_key = _ltype_c_name(inner_lt)

        # Check for pre-defined runtime option types
        if inner_key in _BUILTIN_OPTION_MAP:
            return LStruct(_BUILTIN_OPTION_MAP[inner_key])

        # Heap types use RF_Option_ptr
        if isinstance(inner_lt, LPtr):
            return LStruct("RF_Option_ptr")

        # Check registry for already-emitted option types
        if inner_key in self._option_registry:
            return LStruct(self._option_registry[inner_key])

        # Generate a new option typedef
        c_name = f"RF_Option_{inner_key}"
        self._option_registry[inner_key] = c_name
        self._type_defs.append(LTypeDef(
            c_name=c_name,
            fields=[("tag", LByte()), ("value", inner_lt)],
        ))
        return LStruct(c_name)

    def _lower_result_type(self, ok_t: Type, err_t: Type) -> LType:
        """Lower result<T, E> to a result struct type. RT-7-2-3."""
        ok_lt = self._lower_type(ok_t)
        err_lt = self._lower_type(err_t)
        key = f"{_ltype_c_name(ok_lt)}_{_ltype_c_name(err_lt)}"

        if key in self._result_registry:
            return LStruct(self._result_registry[key])

        c_name = f"RF_Result_{key}"
        self._result_registry[key] = c_name
        self._type_defs.append(LTypeDef(
            c_name=c_name,
            fields=[("tag", LByte()), ("ok_val", ok_lt), ("err_val", err_lt)],
        ))
        return LStruct(c_name)

    def _lower_tuple_type(self, elems: tuple[Type, ...]) -> LType:
        """Lower tuple types to generated structs. RT-7-2-4."""
        lowered = [self._lower_type(e) for e in elems]
        key = "_".join(_ltype_c_name(lt) for lt in lowered)

        if key in self._tuple_registry:
            return LStruct(self._tuple_registry[key])

        c_name = f"RF_Tuple_{key}"
        self._tuple_registry[key] = c_name
        fields: list[tuple[str, LType]] = []
        for i, lt in enumerate(lowered):
            fields.append((f"_{i}", lt))
        self._type_defs.append(LTypeDef(c_name=c_name, fields=fields))
        return LStruct(c_name)

    # ------------------------------------------------------------------
    # Declaration lowering
    # ------------------------------------------------------------------

    def _lower_fn_decl(self, fn: FnDecl) -> None:
        """Lower a function declaration. RT-7-3-1, RT-7-4-1."""
        if fn.native_name is not None:
            # Native functions are implemented in C — no LIR generated.
            return
        if fn.body is None:
            return

        # Check if this is a stream function
        ret_type = self._type_of_return(fn)
        if isinstance(ret_type, TStream):
            self._lower_stream_fn(fn)
            return

        saved_return_type = self._current_fn_return_type
        self._current_fn_return_type = ret_type
        saved_fn_name = self._current_fn_name
        self._current_fn_name = fn.name

        c_name = mangle(self._module_path, None, fn.name,
                        file=self._file, line=fn.line, col=fn.col)

        params: list[tuple[str, LType]] = []
        for p in fn.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
            params.append((p.name, self._lower_type(p_type)))

        ret_lt = self._lower_type(ret_type)

        body: list[LStmt] = []
        match fn.body:
            case Block():
                body = self._lower_block(fn.body)
            case Expr():
                expr_result = self._lower_expr(fn.body)
                body = list(self._pending_stmts)
                self._pending_stmts = []
                body.append(LReturn(expr_result))

        self._fn_defs.append(LFnDef(
            c_name=c_name,
            params=params,
            ret=ret_lt,
            body=body,
            is_pure=fn.is_pure,
            source_name=f"{self._module_path}.{fn.name}",
        ))
        self._current_fn_return_type = saved_return_type
        self._current_fn_name = saved_fn_name

    def _lower_type_decl(self, td: TypeDecl) -> None:
        """Lower a type declaration. RT-7-2-2."""
        c_name = mangle(self._module_path, td.name,
                        file=self._file, line=td.line, col=td.col)

        if td.is_sum_type:
            self._lower_sum_type_decl(td, c_name)
        else:
            # Regular struct
            fields: list[tuple[str, LType]] = []
            for f in td.fields:
                f_type = self._type_of(f.type_ann) if f.type_ann else TNone()
                fields.append((f.name, self._lower_type(f_type)))
            self._type_defs.append(LTypeDef(c_name=c_name, fields=fields))

        # Lower methods
        for method in td.methods:
            if method.body is None:
                continue
            m_c_name = mangle(self._module_path, td.name, method.name,
                              file=self._file, line=method.line, col=method.col)
            params: list[tuple[str, LType]] = []
            for p in method.params:
                if p.name == "self":
                    params.append(("self", LPtr(LStruct(c_name))))
                else:
                    p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
                    params.append((p.name, self._lower_type(p_type)))

            ret_type = self._type_of_return_method(method)
            ret_lt = self._lower_type(ret_type)

            saved_return_type = self._current_fn_return_type
            self._current_fn_return_type = ret_type

            body: list[LStmt] = []
            match method.body:
                case Block():
                    body = self._lower_block(method.body)
                case Expr():
                    expr_result = self._lower_expr(method.body)
                    body = list(self._pending_stmts)
                    self._pending_stmts = []
                    body.append(LReturn(expr_result))

            self._fn_defs.append(LFnDef(
                c_name=m_c_name,
                params=params,
                ret=ret_lt,
                body=body,
                is_pure=method.is_pure,
                source_name=f"{self._module_path}.{td.name}.{method.name}",
            ))
            self._current_fn_return_type = saved_return_type

        # Lower constructors
        for ctor in td.constructors:
            ctor_c_name = mangle(self._module_path, td.name, ctor.name,
                                 file=self._file, line=ctor.line, col=ctor.col)
            params = []
            for p in ctor.params:
                if p.name == "self":
                    params.append(("self", LPtr(LStruct(c_name))))
                else:
                    p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
                    params.append((p.name, self._lower_type(p_type)))
            body = self._lower_block(ctor.body)
            self._fn_defs.append(LFnDef(
                c_name=ctor_c_name,
                params=params,
                ret=LStruct(c_name),
                body=body,
                is_pure=False,
                source_name=f"{self._module_path}.{td.name}.{ctor.name}",
            ))

        # Lower static members
        for s in td.static_members:
            self._lower_static_member(s, td.name)

    def _lower_sum_type_decl(self, td: TypeDecl, c_name: str) -> None:
        """Lower a sum type to a tagged union struct. RT-7-2-2."""
        # Fields: tag (uint8_t) + union payload
        fields: list[tuple[str, LType]] = [("tag", LByte())]

        # Each variant gets a field in the union
        for i, variant in enumerate(td.variants):
            if variant.fields is not None:
                # Variant with payload — create a nested struct for the payload
                variant_fields: list[tuple[str, LType]] = []
                for fname, ftype_expr in variant.fields:
                    f_type = self._type_of(ftype_expr) if ftype_expr else TNone()
                    field_lt = self._lower_type(f_type)
                    # Recursive sum field: use pointer to avoid incomplete type
                    if self._is_recursive_sum_field(f_type, td.name):
                        field_lt = LPtr(field_lt)
                    variant_fields.append((fname, field_lt))
                # Add as a sub-struct named after the variant
                variant_c_name = f"{c_name}_{variant.name}"
                self._type_defs.append(LTypeDef(
                    c_name=variant_c_name,
                    fields=variant_fields,
                ))
                fields.append((variant.name, LStruct(variant_c_name)))
            # Variants without payload have no extra fields

        self._type_defs.append(LTypeDef(c_name=c_name, fields=fields))

    def _lower_static_member(self, sm: StaticMemberDecl, type_name: str) -> None:
        """Lower a static member declaration."""
        c_name = mangle(self._module_path, type_name, sm.name,
                        file=self._file, line=sm.line, col=sm.col)
        s_type = self._type_of(sm.type_ann) if sm.type_ann else TNone()
        init_expr: LExpr | None = None
        if sm.value is not None:
            init_expr = self._lower_expr(sm.value)
            # Flush any pending stmts (shouldn't happen for static inits, but be safe)
            self._pending_stmts = []
        self._static_defs.append(LStaticDef(
            c_name=c_name,
            c_type=self._lower_type(s_type),
            init=init_expr,
            is_mut=sm.is_mut,
        ))

    # ------------------------------------------------------------------
    # Block / statement lowering (RT-7-4-1 through RT-7-4-5)
    # ------------------------------------------------------------------

    def _lower_block(self, block: Block) -> list[LStmt]:
        """Lower a block of statements."""
        result: list[LStmt] = []
        for stmt in block.stmts:
            saved = self._pending_stmts
            self._pending_stmts = []
            lowered = self._lower_stmt(stmt)
            result.extend(self._pending_stmts)
            result.extend(lowered)
            self._pending_stmts = saved
        return result

    def _lower_stmt(self, stmt: Stmt) -> list[LStmt]:
        match stmt:
            case LetStmt():
                return self._lower_let(stmt)
            case AssignStmt():
                return self._lower_assign(stmt)
            case UpdateStmt():
                return self._lower_update(stmt)
            case ReturnStmt():
                return self._lower_return(stmt)
            case IfStmt():
                return self._lower_if_stmt(stmt)
            case WhileStmt():
                return self._lower_while(stmt)
            case ForStmt():
                return self._lower_for(stmt)
            case MatchStmt():
                return self._lower_match_stmt(stmt)
            case ExprStmt():
                return self._lower_expr_stmt(stmt)
            case BreakStmt():
                return [LBreak()]
            case YieldStmt():
                # Yield outside stream fn — should not happen after type check,
                # but handle gracefully
                return self._lower_yield(stmt)
            case TryStmt():
                return self._lower_try(stmt)
            case ThrowStmt():
                return self._lower_throw(stmt)
            case _:
                raise EmitError(
                    message=f"unsupported statement type: {type(stmt).__name__}",
                    file=self._file, line=stmt.line, col=stmt.col,
                )

    def _lower_let(self, stmt: LetStmt) -> list[LStmt]:
        val_type = self._type_of(stmt.value)
        c_type = self._lower_type(val_type)
        init = self._lower_expr(stmt.value)
        # If there's a type annotation, prefer it for the declared type
        if stmt.type_ann is not None:
            ann_type = self._type_of(stmt.type_ann)
            c_type = self._lower_type(ann_type)
            # Auto-lift T → option<T>
            if isinstance(ann_type, TOption) and not isinstance(val_type, TOption):
                init = LCompound(
                    fields=[("tag", LLit("1", LByte())),
                            ("value", init)],
                    c_type=c_type,
                )
        return [LVarDecl(c_name=stmt.name, c_type=c_type, init=init)]

    def _lower_assign(self, stmt: AssignStmt) -> list[LStmt]:
        target = self._lower_expr(stmt.target)
        value = self._lower_expr(stmt.value)
        return [LAssign(target=target, value=value)]

    def _lower_update(self, stmt: UpdateStmt) -> list[LStmt]:
        target = self._lower_expr(stmt.target)
        target_type = self._type_of(stmt.target)
        c_type = self._lower_type(target_type)

        if stmt.op in ("++", "--"):
            # Increment/decrement
            one = LLit("1", c_type)
            if isinstance(target_type, (TInt,)):
                # Checked arithmetic for integers
                arith_op = "+" if stmt.op == "++" else "-"
                arith = LCheckedArith(op=arith_op, left=target, right=one, c_type=c_type)
                return [LAssign(target=target, value=arith)]
            else:
                # Float — plain binop
                op = "+" if stmt.op == "++" else "-"
                binop = LBinOp(op=op, left=target, right=one, c_type=c_type)
                return [LAssign(target=target, value=binop)]

        # Compound assignment: +=, -=, *=, /=, %=
        op = stmt.op.rstrip("=")
        if stmt.value is None:
            raise EmitError(
                message=f"compound assignment '{stmt.op}' requires a value",
                file=self._file, line=stmt.line, col=stmt.col,
            )
        value = self._lower_expr(stmt.value)

        if isinstance(target_type, (TInt,)) and op in ("+", "-", "*"):
            expr = LCheckedArith(op=op, left=target, right=value, c_type=c_type)
        elif isinstance(target_type, (TInt,)) and op in ("/", "%"):
            expr = LCheckedArith(op=op, left=target, right=value, c_type=c_type)
        else:
            expr = LBinOp(op=op, left=target, right=value, c_type=c_type)

        return [LAssign(target=target, value=expr)]

    def _lower_return(self, stmt: ReturnStmt) -> list[LStmt]:
        if stmt.value is None:
            return [LReturn(None)]
        value = self._lower_expr(stmt.value)
        return [LReturn(value)]

    def _lower_if_stmt(self, stmt: IfStmt) -> list[LStmt]:
        cond = self._lower_expr(stmt.condition)
        then_body = self._lower_block(stmt.then_branch)
        else_body: list[LStmt] = []
        if stmt.else_branch is not None:
            if isinstance(stmt.else_branch, Block):
                else_body = self._lower_block(stmt.else_branch)
            elif isinstance(stmt.else_branch, IfStmt):
                else_body = self._lower_if_stmt(stmt.else_branch)
        return [LIf(cond=cond, then=then_body, else_=else_body)]

    def _lower_while(self, stmt: WhileStmt) -> list[LStmt]:
        cond = self._lower_expr(stmt.condition)
        body = self._lower_block(stmt.body)
        result: list[LStmt] = [LWhile(cond=cond, body=body)]
        if stmt.finally_block is not None:
            result.extend(self._lower_block(stmt.finally_block))
        return result

    def _lower_for(self, stmt: ForStmt) -> list[LStmt]:
        """Lower for-loop to LWhile. RT-7-4-3, RT-7-4-4."""
        iter_type = self._type_of(stmt.iterable)

        match iter_type:
            case TArray(element=elem_t):
                return self._lower_for_array(stmt, elem_t)
            case TStream(element=elem_t):
                return self._lower_for_stream(stmt, elem_t)
            case _:
                # Fallback — treat as array
                return self._lower_for_array(stmt, TAny())

    def _lower_for_array(self, stmt: ForStmt, elem_t: Type) -> list[LStmt]:
        """Lower for-over-array to index-based while loop. RT-7-4-4."""
        arr_expr = self._lower_expr(stmt.iterable)
        idx_name = self._fresh_temp()
        elem_lt = self._lower_type(elem_t)

        # int64_t _rf_idx = 0;
        idx_decl = LVarDecl(
            c_name=idx_name,
            c_type=LInt(64, True),
            init=LLit("0", LInt(64, True)),
        )

        # _rf_idx < rf_array_len(arr)
        cond = LBinOp(
            op="<",
            left=LVar(idx_name, LInt(64, True)),
            right=LCall("rf_array_len", [arr_expr], LInt(64, True)),
            c_type=LBool(),
        )

        # ElementType item = *(ElementType*)rf_array_get_ptr(arr, _rf_idx);
        get_ptr = LCall("rf_array_get_ptr",
                         [arr_expr, LVar(idx_name, LInt(64, True))],
                         LPtr(LVoid()))
        cast_ptr = LCast(get_ptr, LPtr(elem_lt))
        deref = LDeref(cast_ptr, elem_lt)
        item_decl = LVarDecl(c_name=stmt.var, c_type=elem_lt, init=deref)

        # _rf_idx = _rf_idx + 1;
        increment = LAssign(
            target=LVar(idx_name, LInt(64, True)),
            value=LBinOp(
                op="+",
                left=LVar(idx_name, LInt(64, True)),
                right=LLit("1", LInt(64, True)),
                c_type=LInt(64, True),
            ),
        )

        body_stmts = [item_decl] + self._lower_block(stmt.body) + [increment]
        result: list[LStmt] = [idx_decl, LWhile(cond=cond, body=body_stmts)]

        if stmt.finally_block is not None:
            result.extend(self._lower_block(stmt.finally_block))

        return result

    def _lower_for_stream(self, stmt: ForStmt, elem_t: Type) -> list[LStmt]:
        """Lower for-over-stream to while loop with rf_stream_next. RT-7-4-3."""
        stream_expr = self._lower_expr(stmt.iterable)
        stream_lt = LPtr(LStruct("RF_Stream"))
        elem_lt = self._lower_type(elem_t)
        next_name = self._fresh_temp()

        # Store stream in a temp to avoid re-evaluating the iterable each iteration
        stream_tmp = self._fresh_temp()
        stream_decl = LVarDecl(c_name=stream_tmp, c_type=stream_lt, init=stream_expr)
        stream_var = LVar(stream_tmp, stream_lt)

        # while (1) { ... }
        cond = LLit("1", LBool())

        # RF_Option_ptr _rf_next = rf_stream_next(stream);
        next_decl = LVarDecl(
            c_name=next_name,
            c_type=LStruct("RF_Option_ptr"),
            init=LCall("rf_stream_next", [stream_var], LStruct("RF_Option_ptr")),
        )

        # if (_rf_next.tag == 0) break;
        tag_check = LIf(
            cond=LBinOp(
                op="==",
                left=LFieldAccess(
                    LVar(next_name, LStruct("RF_Option_ptr")),
                    "tag", LByte()),
                right=LLit("0", LByte()),
                c_type=LBool(),
            ),
            then=[LBreak()],
            else_=[],
        )

        # T item = (T)(uintptr_t)_rf_next.value;  (for value types)
        # T item = (T)_rf_next.value;              (for pointer types)
        value_access = LFieldAccess(
            LVar(next_name, LStruct("RF_Option_ptr")),
            "value", LPtr(LVoid()))
        item_init: LExpr
        if isinstance(elem_lt, LPtr):
            item_init = LCast(value_access, elem_lt)
        else:
            # Value types need intermediate cast through uintptr_t (uint64)
            item_init = LCast(LCast(value_access, LInt(64, False)), elem_lt)
        item_decl = LVarDecl(c_name=stmt.var, c_type=elem_lt, init=item_init)

        body_stmts = [next_decl, tag_check, item_decl] + self._lower_block(stmt.body)
        result: list[LStmt] = [stream_decl, LWhile(cond=cond, body=body_stmts)]

        if stmt.finally_block is not None:
            result.extend(self._lower_block(stmt.finally_block))

        return result

    def _lower_match_stmt(self, stmt: MatchStmt) -> list[LStmt]:
        """Lower match statement. RT-7-3-5, RT-7-3-6."""
        subj_type = self._type_of(stmt.subject)
        subj_expr = self._lower_expr(stmt.subject)

        # Store subject in a temp to avoid re-evaluation
        subj_tmp = self._fresh_temp()
        subj_lt = self._lower_type(subj_type)
        subj_decl = LVarDecl(c_name=subj_tmp, c_type=subj_lt, init=subj_expr)

        subj_var = LVar(subj_tmp, subj_lt)

        match subj_type:
            case TSum():
                stmts = self._lower_match_sum(subj_var, subj_type, stmt.arms)
                return [subj_decl] + stmts
            case TOption():
                stmts = self._lower_match_option(subj_var, subj_type, stmt.arms)
                return [subj_decl] + stmts
            case TResult():
                stmts = self._lower_match_result(subj_var, subj_type, stmt.arms)
                return [subj_decl] + stmts
            case TTuple():
                stmts = self._lower_match_tuple(subj_var, subj_type, stmt.arms)
                return [subj_decl] + stmts
            case _:
                # For primitives and other types, use if-else chains
                stmts = self._lower_match_generic(subj_var, subj_type, stmt.arms)
                return [subj_decl] + stmts

    def _lower_expr_stmt(self, stmt: ExprStmt) -> list[LStmt]:
        expr = self._lower_expr(stmt.expr)
        return [LExprStmt(expr)]

    def _lower_yield(self, stmt: YieldStmt) -> list[LStmt]:
        # Outside stream context — this is an error but we handle it for robustness
        value = self._lower_expr(stmt.value)
        return [LExprStmt(value)]

    def _lower_try(self, stmt: TryStmt) -> list[LStmt]:
        """Lower try/catch/retry/finally using setjmp/longjmp.

        When finally is present, unhandled exceptions must not rethrow until
        after the finally body runs. A _caught flag tracks whether the
        exception was handled by a catch/retry block.

        Generated pattern (with finally):
            RF_ExceptionFrame _rf_ef_N;
            rf_bool _rf_ef_N_caught = rf_true;  // assume success
            _rf_exception_push(&_rf_ef_N);
            if (setjmp(_rf_ef_N.jmp) == 0) {
                // try body
                _rf_exception_pop();
            } else {
                _rf_exception_pop();
                _rf_ef_N_caught = rf_false;  // exception occurred
                // catch dispatch (sets _caught back to rf_true if handled)
            }
            // finally body
            if (!_rf_ef_N_caught) {
                _rf_throw(_rf_ef_N.exception, _rf_ef_N.exception_tag);
            }
        """
        result: list[LStmt] = []
        frame_idx = self._exception_frame_counter
        self._exception_frame_counter += 1
        frame_name = mangle_exception_frame(frame_idx)
        frame_type = LStruct("RF_ExceptionFrame")
        has_finally = stmt.finally_block is not None
        caught_var = f"{frame_name}_caught"

        # Declare exception frame on stack
        result.append(LVarDecl(
            c_name=frame_name,
            c_type=frame_type,
            init=None,
        ))

        # If finally is present, track whether exception was handled
        if has_finally:
            result.append(LVarDecl(
                c_name=caught_var,
                c_type=LBool(),
                init=LLit("rf_true", LBool()),
            ))

        # Push frame
        result.append(LExprStmt(LCall(
            "_rf_exception_push",
            [LAddrOf(LVar(frame_name, frame_type), LPtr(frame_type))],
            LVoid(),
        )))

        # Build the try body (the "then" branch of setjmp == 0)
        try_stmts: list[LStmt] = []
        try_stmts.extend(self._lower_block(stmt.body))
        try_stmts.append(LExprStmt(LCall(
            "_rf_exception_pop", [], LVoid(),
        )))

        # Build the catch/retry branch (the "else" branch of setjmp != 0)
        catch_stmts: list[LStmt] = []
        catch_stmts.append(LExprStmt(LCall(
            "_rf_exception_pop", [], LVoid(),
        )))

        if has_finally:
            # Mark exception as not-yet-handled
            catch_stmts.append(LAssign(
                target=LVar(caught_var, LBool()),
                value=LLit("rf_false", LBool()),
            ))

        # Build catch/retry dispatch chain
        catch_stmts.extend(self._build_catch_dispatch(
            stmt, frame_name, frame_type, has_finally, caught_var))

        # setjmp condition: setjmp(_rf_ef_N.jmp) == 0
        setjmp_call = LCall(
            "setjmp",
            [LFieldAccess(
                LVar(frame_name, frame_type), "jmp",
                LStruct("jmp_buf"),
            )],
            LInt(32, True),
        )
        condition = LBinOp(
            "==", setjmp_call, LLit("0", LInt(32, True)), LBool(),
        )

        result.append(LIf(
            cond=condition,
            then=try_stmts,
            else_=catch_stmts,
        ))

        # Finally block — always runs
        if stmt.finally_block is not None:
            result.extend(self._lower_finally_block(
                stmt.finally_block, frame_name, frame_type))
            # Rethrow if exception was not handled
            result.append(LIf(
                cond=LUnary("!", LVar(caught_var, LBool()), LBool()),
                then=[LExprStmt(LCall(
                    "_rf_throw",
                    [LFieldAccess(LVar(frame_name, frame_type), "exception",
                                  LPtr(LVoid())),
                     LFieldAccess(LVar(frame_name, frame_type),
                                  "exception_tag", LInt(32, True))],
                    LVoid(),
                ))],
                else_=[],
            ))

        return result

    def _build_catch_dispatch(self, stmt: TryStmt,
                              frame_name: str,
                              frame_type: LType,
                              has_finally: bool = False,
                              caught_var: str = "") -> list[LStmt]:
        """Build the catch dispatch chain for a try statement.

        Handles retry blocks first (they wrap the function call in a loop),
        then catch blocks as an if-else chain by exception tag, with a
        default rethrow if no catch matches.

        Catch blocks whose exception type matches a retry block are skipped
        here — the retry handler already inlines the matching catch handler
        for the exhausted-retries case.

        When has_finally is True, catch/retry handlers set caught_var to
        rf_true instead of rethrowing, so finally can run before rethrow.
        """
        dispatch_entries: list[tuple[int, list[LStmt]]] = []

        # Track which tags are handled by retry blocks
        retry_tags: set[int] = set()

        for retry in stmt.retry_blocks:
            tag = self._exception_tag_for_type_expr(retry.exception_type)
            retry_tags.add(tag)
            retry_stmts = self._build_retry_handler(
                retry, frame_name, frame_type, stmt)
            if has_finally:
                retry_stmts.append(LAssign(
                    target=LVar(caught_var, LBool()),
                    value=LLit("rf_true", LBool()),
                ))
            dispatch_entries.append((tag, retry_stmts))

        for catch in stmt.catch_blocks:
            tag = self._exception_tag_for_type_expr(catch.exception_type)
            # Skip catch blocks already handled by a retry block
            if tag in retry_tags:
                continue
            catch_stmts = self._build_catch_handler(
                catch, frame_name, frame_type)
            if has_finally:
                catch_stmts.append(LAssign(
                    target=LVar(caught_var, LBool()),
                    value=LLit("rf_true", LBool()),
                ))
            dispatch_entries.append((tag, catch_stmts))

        if not dispatch_entries:
            if has_finally:
                # No catch/retry blocks — don't rethrow yet, let finally run
                # The _caught flag is already rf_false, so post-finally rethrow will fire
                return []
            else:
                # No catch or retry blocks, no finally — rethrow unconditionally
                return [LExprStmt(LCall(
                    "_rf_throw",
                    [LFieldAccess(LVar(frame_name, frame_type), "exception",
                                  LPtr(LVoid())),
                     LFieldAccess(LVar(frame_name, frame_type), "exception_tag",
                                  LInt(32, True))],
                    LVoid(),
                ))]

        # Build if-else chain from dispatch entries
        return self._build_tag_dispatch_chain(
            dispatch_entries, frame_name, frame_type, has_finally)

    def _build_tag_dispatch_chain(
        self,
        entries: list[tuple[int, list[LStmt]]],
        frame_name: str,
        frame_type: LType,
        has_finally: bool = False,
    ) -> list[LStmt]:
        """Build an if/else-if chain dispatching on exception_tag.

        When has_finally is True, the default else is empty (no rethrow) —
        the caller handles rethrow after finally runs.
        """
        if not entries:
            return []

        if has_finally:
            # Default: do nothing — _caught remains false, post-finally rethrow handles it
            default_else: list[LStmt] = []
        else:
            # Default: rethrow immediately
            default_else = [LExprStmt(LCall(
                "_rf_throw",
                [LFieldAccess(LVar(frame_name, frame_type), "exception",
                              LPtr(LVoid())),
                 LFieldAccess(LVar(frame_name, frame_type), "exception_tag",
                              LInt(32, True))],
                LVoid(),
            ))]

        # Build from last to first
        current_else = default_else
        for tag, stmts in reversed(entries):
            cond = LBinOp(
                "==",
                LFieldAccess(LVar(frame_name, frame_type), "exception_tag",
                             LInt(32, True)),
                LLit(str(tag), LInt(32, True)),
                LBool(),
            )
            current_else = [LIf(cond=cond, then=stmts, else_=current_else)]

        return current_else

    def _build_catch_handler(self, catch: CatchBlock,
                             frame_name: str,
                             frame_type: LType) -> list[LStmt]:
        """Build the statements for a single catch block.

        Binds the exception variable from the frame's exception pointer.
        For string exceptions (tag 0): bind as RF_String*.
        For typed exceptions: cast from void* to ExcType*.
        """
        stmts: list[LStmt] = []

        exc_type = self._resolve_type_ann(catch.exception_type)
        c_type = self._lower_type(exc_type)

        if isinstance(exc_type, TString):
            # String exception: cast void* to RF_String*
            stmts.append(LVarDecl(
                c_name=catch.exception_var,
                c_type=LPtr(LStruct("RF_String")),
                init=LCast(
                    LFieldAccess(LVar(frame_name, frame_type), "exception",
                                 LPtr(LVoid())),
                    LPtr(LStruct("RF_String")),
                ),
            ))
        else:
            # Typed exception: cast void* to ExcType* and dereference
            tmp = self._fresh_temp()
            stmts.append(LVarDecl(
                c_name=tmp,
                c_type=LPtr(c_type),
                init=LCast(
                    LFieldAccess(LVar(frame_name, frame_type), "exception",
                                 LPtr(LVoid())),
                    LPtr(c_type),
                ),
            ))
            stmts.append(LVarDecl(
                c_name=catch.exception_var,
                c_type=c_type,
                init=LDeref(LVar(tmp, LPtr(c_type)), c_type),
            ))

        # Lower the catch body
        stmts.extend(self._lower_block(catch.body))
        return stmts

    def _build_retry_handler(self, retry: RetryBlock,
                             frame_name: str,
                             frame_type: LType,
                             try_stmt: TryStmt) -> list[LStmt]:
        """Build the statements for a retry block.

        Retry re-invokes the named function. The exception variable's `data`
        field is mutable, allowing the retry body to correct it before re-invocation.

        Generated pattern:
            int _rf_attempts_N = 0;
            ExcType* ex_ptr = (ExcType*)_rf_ef_N.exception;
            ExcType ex = *ex_ptr;
            while (_rf_attempts_N < max_attempts) {
                _rf_attempts_N++;
                // retry body (can modify ex.data fields)
                // re-push frame, re-try the named function call
                *ex_ptr = ex;  // write back modifications
                _rf_exception_push(&_rf_ef_N);
                if (setjmp(_rf_ef_N.jmp) == 0) {
                    // call target_fn again with corrected data
                    _rf_exception_pop();
                    goto _rf_retry_success_N;
                } else {
                    _rf_exception_pop();
                    ex_ptr = (ExcType*)_rf_ef_N.exception;
                    ex = *ex_ptr;
                }
            }
            // retries exhausted — fall through to catch or rethrow
            _rf_retry_success_N: ;

        For bootstrap simplification: the retry re-executes the entire try body
        rather than just the named function, since isolating a single function
        from a composition chain requires deep chain analysis that isn't yet
        implemented. This matches the semantic intent for non-chain code.
        """
        stmts: list[LStmt] = []
        exc_type = self._resolve_type_ann(retry.exception_type)
        c_type = self._lower_type(exc_type)

        max_attempts = retry.attempts if retry.attempts is not None else 2147483647

        # Attempts counter
        attempts_var = self._fresh_temp()
        stmts.append(LVarDecl(
            c_name=attempts_var,
            c_type=LInt(32, True),
            init=LLit("0", LInt(32, True)),
        ))

        # Bind exception variable
        if isinstance(exc_type, TString):
            # String exception
            stmts.append(LVarDecl(
                c_name=retry.exception_var,
                c_type=LPtr(LStruct("RF_String")),
                init=LCast(
                    LFieldAccess(LVar(frame_name, LStruct("RF_ExceptionFrame")),
                                 "exception", LPtr(LVoid())),
                    LPtr(LStruct("RF_String")),
                ),
            ))
        else:
            # Typed exception: get pointer, dereference for local copy
            exc_ptr = self._fresh_temp()
            stmts.append(LVarDecl(
                c_name=exc_ptr,
                c_type=LPtr(c_type),
                init=LCast(
                    LFieldAccess(LVar(frame_name, LStruct("RF_ExceptionFrame")),
                                 "exception", LPtr(LVoid())),
                    LPtr(c_type),
                ),
            ))
            stmts.append(LVarDecl(
                c_name=retry.exception_var,
                c_type=c_type,
                init=LDeref(LVar(exc_ptr, LPtr(c_type)), c_type),
            ))

        # Success label for goto on successful retry
        success_label = self._fresh_temp()

        # Build loop body
        loop_body: list[LStmt] = []

        # Increment attempts
        loop_body.append(LAssign(
            target=LVar(attempts_var, LInt(32, True)),
            value=LBinOp("+",
                         LVar(attempts_var, LInt(32, True)),
                         LLit("1", LInt(32, True)),
                         LInt(32, True)),
        ))

        # Execute retry body (user code that modifies ex)
        loop_body.extend(self._lower_block(retry.body))

        # Write back modifications if typed exception
        if not isinstance(exc_type, TString):
            loop_body.append(LAssign(
                target=LDeref(LVar(exc_ptr, LPtr(c_type)), c_type),
                value=LVar(retry.exception_var, c_type),
            ))

        # Re-push exception frame for retry
        frame_type_s = LStruct("RF_ExceptionFrame")
        loop_body.append(LExprStmt(LCall(
            "_rf_exception_push",
            [LAddrOf(LVar(frame_name, frame_type_s), LPtr(frame_type_s))],
            LVoid(),
        )))

        # Inner setjmp for retry
        inner_setjmp = LCall(
            "setjmp",
            [LFieldAccess(LVar(frame_name, frame_type_s), "jmp",
                          LStruct("jmp_buf"))],
            LInt(32, True),
        )
        inner_cond = LBinOp("==", inner_setjmp, LLit("0", LInt(32, True)),
                            LBool())

        # Inner try body: re-run try body and goto success on completion
        inner_try: list[LStmt] = []
        inner_try.extend(self._lower_block(try_stmt.body))
        inner_try.append(LExprStmt(LCall("_rf_exception_pop", [], LVoid())))
        inner_try.append(LGoto(success_label))

        # Inner catch: pop, re-bind exception, continue loop
        inner_catch: list[LStmt] = []
        inner_catch.append(LExprStmt(LCall("_rf_exception_pop", [], LVoid())))
        if isinstance(exc_type, TString):
            inner_catch.append(LAssign(
                target=LVar(retry.exception_var, LPtr(LStruct("RF_String"))),
                value=LCast(
                    LFieldAccess(LVar(frame_name, frame_type_s),
                                 "exception", LPtr(LVoid())),
                    LPtr(LStruct("RF_String")),
                ),
            ))
        else:
            inner_catch.append(LAssign(
                target=LVar(exc_ptr, LPtr(c_type)),
                value=LCast(
                    LFieldAccess(LVar(frame_name, frame_type_s),
                                 "exception", LPtr(LVoid())),
                    LPtr(c_type),
                ),
            ))
            inner_catch.append(LAssign(
                target=LVar(retry.exception_var, c_type),
                value=LDeref(LVar(exc_ptr, LPtr(c_type)), c_type),
            ))

        loop_body.append(LIf(cond=inner_cond, then=inner_try, else_=inner_catch))

        # While loop: while (attempts < max_attempts)
        loop_cond = LBinOp(
            "<",
            LVar(attempts_var, LInt(32, True)),
            LLit(str(max_attempts), LInt(32, True)),
            LBool(),
        )
        stmts.append(LWhile(cond=loop_cond, body=loop_body))

        # After loop: retries exhausted — find matching catch or rethrow
        # Check if there's a catch block for this exception type
        matching_catch = None
        for catch in try_stmt.catch_blocks:
            catch_type = self._resolve_type_ann(catch.exception_type)
            catch_tag = self._exception_type_tag(catch_type)
            retry_tag = self._exception_type_tag(exc_type)
            if catch_tag == retry_tag:
                matching_catch = catch
                break

        if matching_catch is not None:
            # Execute the matching catch body directly — the exception variable
            # is already bound from the retry block, so we only lower the body
            # without re-declaring the variable.
            stmts.extend(self._lower_block(matching_catch.body))
        else:
            # No matching catch — rethrow
            stmts.append(LExprStmt(LCall(
                "_rf_throw",
                [LFieldAccess(LVar(frame_name, LStruct("RF_ExceptionFrame")),
                              "exception", LPtr(LVoid())),
                 LFieldAccess(LVar(frame_name, LStruct("RF_ExceptionFrame")),
                              "exception_tag", LInt(32, True))],
                LVoid(),
            )))

        # Success label
        stmts.append(LLabel(success_label))

        return stmts

    def _lower_finally_block(self, fin: FinallyBlock,
                             frame_name: str,
                             frame_type: LType) -> list[LStmt]:
        """Lower a finally block.

        If the finally block captures the exception (? ex), bind it from the
        frame's exception pointer (NULL if no exception occurred).
        """
        stmts: list[LStmt] = []

        if fin.exception_var is not None:
            # Bind exception as void* — NULL if no exception
            stmts.append(LVarDecl(
                c_name=fin.exception_var,
                c_type=LPtr(LVoid()),
                init=LFieldAccess(
                    LVar(frame_name, frame_type), "exception",
                    LPtr(LVoid()),
                ),
            ))

        stmts.extend(self._lower_block(fin.body))
        return stmts

    def _exception_tag_for_type_expr(self, te: TypeExpr) -> int:
        """Compute exception tag from a TypeExpr annotation."""
        exc_type = self._resolve_type_ann(te)
        if isinstance(exc_type, TString):
            return 0
        return self._exception_type_tag(exc_type)

    def _lower_throw(self, stmt: ThrowStmt) -> list[LStmt]:
        """Lower throw statement.

        For string exceptions: _rf_throw(rf_string_from_cstr("msg"), 0)
          where tag 0 means untyped/string exception.
        For typed exceptions: heap-allocate the exception struct and pass pointer.
        """
        exc_expr = self._lower_expr(stmt.exception)
        exc_type = self._type_of(stmt.exception)

        if isinstance(exc_type, TString):
            # String exceptions use tag 0
            return [LExprStmt(LCall(
                "_rf_throw",
                [LCast(exc_expr, LPtr(LVoid())),
                 LLit("0", LInt(32, True))],
                LVoid(),
            ))]

        # Typed exception: heap-allocate and pass pointer + tag
        tag = self._exception_type_tag(exc_type)
        c_type = self._lower_type(exc_type)
        tmp = self._fresh_temp()
        # Allocate: ExcType* tmp = malloc(sizeof(ExcType)); *tmp = exc_expr;
        alloc = LVarDecl(
            c_name=tmp,
            c_type=LPtr(c_type),
            init=LCast(
                LCall("malloc", [LSizeOf(c_type)], LPtr(LVoid())),
                LPtr(c_type),
            ),
        )
        store = LAssign(
            target=LDeref(LVar(tmp, LPtr(c_type)), c_type),
            value=exc_expr,
        )
        throw = LExprStmt(LCall(
            "_rf_throw",
            [LCast(LVar(tmp, LPtr(c_type)), LPtr(LVoid())),
             LLit(str(tag), LInt(32, True))],
            LVoid(),
        ))
        return [alloc, store, throw]

    def _exception_type_tag(self, t: Type) -> int:
        """Compute a deterministic integer tag for an exception type.

        Uses a simple string hash. Tag 0 is reserved for untyped/string exceptions.
        """
        name = self._type_name_str(t)
        h = 0
        for ch in name:
            h = (h * 31 + ord(ch)) & 0x7FFFFFFF
        return h if h != 0 else 1

    # ------------------------------------------------------------------
    # Expression lowering (RT-7-3-1 through RT-7-3-8)
    # ------------------------------------------------------------------

    def _lower_expr(self, expr: Expr) -> LExpr:
        match expr:
            # Literals
            case IntLit(value=v, suffix=suffix):
                t = self._type_of(expr)
                lt = self._lower_type(t)
                return LLit(str(v), lt)

            case FloatLit(value=v):
                t = self._type_of(expr)
                lt = self._lower_type(t)
                return LLit(repr(v), lt)

            case BoolLit(value=v):
                return LLit("rf_true" if v else "rf_false", LBool())

            case StringLit(value=v):
                escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
                return LCall(
                    "rf_string_from_cstr",
                    [LLit(f'"{escaped}"', LPtr(LVoid()))],
                    LPtr(LStruct("RF_String")),
                )

            case CharLit(value=v):
                return LLit(str(v), LChar())

            case NoneLit():
                # Lower to RF_NONE compound literal with concrete option type
                t = self._type_of(expr)
                # Prefer function return type for concrete option type
                if isinstance(t, TOption) and isinstance(t.inner, TAny):
                    if isinstance(self._current_fn_return_type, TOption):
                        t = self._current_fn_return_type
                lt = self._lower_type(t) if isinstance(t, TOption) else LStruct("RF_Option_ptr")
                return LCompound(
                    fields=[("tag", LLit("0", LByte()))],
                    c_type=lt,
                )

            case FStringExpr():
                return self._lower_fstring(expr)

            # Identifiers
            case Ident(name=name, module_path=mp):
                # Capture remap — inside lambda body, captured vars
                # become frame field accesses
                if name in self._capture_remap:
                    remap_expr, remap_lt = self._capture_remap[name]
                    return LVar(remap_expr, remap_lt)
                t = self._type_of(expr)
                lt = self._lower_type(t)
                sym = self._resolved.symbols.get(expr)
                if sym is not None and sym.kind == SymbolKind.FN:
                    # Function reference used as value — wrap in closure
                    return self._wrap_fn_as_closure(name, t, lt, expr)
                # Unit variant constructor — compound literal with just tag
                if (sym is not None and sym.kind == SymbolKind.CONSTRUCTOR
                        and isinstance(sym.decl, SumVariantDecl)
                        and sym.decl.fields is None
                        and isinstance(t, TSum)):
                    tag = next((i for i, v in enumerate(t.variants)
                                if v.name == name), 0)
                    return LCompound(
                        fields=[("tag", LLit(str(tag), LByte()))],
                        c_type=lt,
                    )
                # self is always a pointer in methods
                if name == "self" and isinstance(lt, LStruct):
                    return LVar(name, LPtr(lt))
                return LVar(name, lt)

            # Binary operators (RT-7-3-2)
            case BinOp(op=op, left=left, right=right):
                return self._lower_binop(expr, op, left, right)

            case UnaryOp(op=op, operand=operand):
                inner = self._lower_expr(operand)
                t = self._type_of(expr)
                lt = self._lower_type(t)
                return LUnary(op=op, operand=inner, c_type=lt)

            # Function calls
            case Call(callee=callee, args=args):
                return self._lower_call(expr)

            case MethodCall(receiver=receiver, method=method_name, args=args):
                return self._lower_method_call(expr)

            # Field/index access
            case FieldAccess(receiver=receiver, field=field_name):
                t = self._type_of(expr)
                lt = self._lower_type(t)
                # Static member access: Type.member → mangled global var
                sym = self._resolved.symbols.get(expr)
                if sym is not None and sym.kind == SymbolKind.STATIC:
                    recv_type = self._type_of(receiver)
                    type_name = recv_type.name if isinstance(recv_type, TNamed) else None
                    if type_name is None and isinstance(receiver, Ident):
                        type_name = receiver.name
                    c_name = mangle(self._module_path, type_name, field_name,
                                    file=self._file, line=expr.line, col=expr.col)
                    return LVar(c_name, lt)
                recv = self._lower_expr(receiver)
                # Tuple field names: .0, .1 → ._0, ._1 (numeric names are
                # invalid C identifiers, prefix with underscore)
                c_field = f"_{field_name}" if field_name.isdigit() else field_name
                # Use arrow for pointer-typed receivers (heap types, self param)
                recv_c_type = getattr(recv, 'c_type', None)
                if isinstance(recv_c_type, LPtr):
                    return LArrow(ptr=recv, field=c_field, c_type=lt)
                return LFieldAccess(obj=recv, field=c_field, c_type=lt)

            case IndexAccess(receiver=receiver, index=index):
                recv = self._lower_expr(receiver)
                idx = self._lower_expr(index)
                t = self._type_of(expr)
                lt = self._lower_type(t)
                recv_type = self._type_of(receiver)
                if isinstance(recv_type, TArray):
                    # Array index returns option — use rf_array_get_safe
                    return LCall("rf_array_get_safe",
                                 [recv, idx], lt)
                if isinstance(recv_type, TMap):
                    return LCall("rf_map_get", [recv, idx], lt)
                return LIndex(arr=recv, idx=idx, c_type=lt)

            # Lambda
            case Lambda():
                return self._lower_lambda(expr)

            # Tuple
            case TupleExpr(elements=elements):
                t = self._type_of(expr)
                lt = self._lower_type(t)
                fields: list[tuple[str, LExpr]] = []
                for i, elem in enumerate(elements):
                    fields.append((f"_{i}", self._lower_expr(elem)))
                return LCompound(fields=fields, c_type=lt)

            # Array literal
            case ArrayLit(elements=elements):
                return self._lower_array_lit(expr)

            # Record literal
            case RecordLit(fields=rfields):
                t = self._type_of(expr)
                lt = self._lower_type(t)
                lfields: list[tuple[str, LExpr]] = []
                for name, val in rfields:
                    lfields.append((name, self._lower_expr(val)))
                return LCompound(fields=lfields, c_type=lt)

            # Type literal (struct construction)
            case TypeLit(type_name=type_name, fields=tfields, spread=spread):
                return self._lower_type_lit(expr)

            # If expression
            case IfExpr(condition=cond, then_branch=then_b, else_branch=else_b):
                return self._lower_if_expr(expr)

            # Match expression
            case MatchExpr():
                return self._lower_match_expr(expr)

            # Composition chain (RT-7-3-3)
            case CompositionChain():
                return self._lower_chain(expr)

            # Fan-out
            case FanOut(branches=branches):
                # Lower each branch, collect into tuple
                results: list[LExpr] = []
                for branch in branches:
                    results.append(self._lower_expr(branch.expr))
                if len(results) == 1:
                    return results[0]
                t = self._type_of(expr)
                lt = self._lower_type(t)
                fields = [(f"_{i}", r) for i, r in enumerate(results)]
                return LCompound(fields=fields, c_type=lt)

            # Ternary
            case TernaryExpr(condition=cond, then_expr=then_e, else_expr=else_e):
                c = self._lower_expr(cond)
                th = self._lower_expr(then_e)
                el = self._lower_expr(else_e)
                t = self._type_of(expr)
                lt = self._lower_type(t)
                return LTernary(cond=c, then_expr=th, else_expr=el, c_type=lt)

            # Copy (RT-7-3-8)
            case CopyExpr(inner=inner):
                return self._lower_copy(expr)

            # Some/Ok/Err wrappers
            case SomeExpr(inner=inner):
                return self._lower_some(expr)

            case OkExpr(inner=inner):
                return self._lower_ok(expr)

            case ErrExpr(inner=inner):
                return self._lower_err(expr)

            # Coerce
            case CoerceExpr(inner=inner):
                return self._lower_expr(inner)

            # Cast
            case CastExpr(inner=inner, target_type=target):
                inner_expr = self._lower_expr(inner)
                t = self._type_of(expr)
                lt = self._lower_type(t)
                return LCast(inner=inner_expr, c_type=lt)

            # Snapshot
            case SnapshotExpr(inner=inner):
                # SPEC GAP: .refresh() not implemented. Without parallelism
                # (Gap #10), .refresh() has no observable effect since only
                # the current thread can mutate the source static. The
                # pass-through is correct for value types (C copy semantics)
                # and immutable heap types (strings/arrays are reference-counted
                # and their content cannot change).
                return self._lower_expr(inner)

            # Propagate (RT-7-3-7)
            case PropagateExpr(inner=inner):
                return self._lower_propagate(expr)

            # Null coalesce
            case NullCoalesce(left=left, right=right):
                return self._lower_null_coalesce(expr)

            # Typeof
            case TypeofExpr(inner=inner):
                # Lower to string representation of type
                t = self._type_of(inner)
                type_name = self._type_name_str(t)
                return LCall(
                    "rf_string_from_cstr",
                    [LLit(f'"{type_name}"', LPtr(LVoid()))],
                    LPtr(LStruct("RF_String")),
                )

            # Coroutine start — wrap stream in RF_Coroutine
            case CoroutineStart(call=call):
                stream_expr = self._lower_expr(call)
                return LCall("rf_coroutine_new", [stream_expr],
                             LPtr(LStruct("RF_Coroutine")))

            case _:
                raise EmitError(
                    message=f"unsupported expression type: {type(expr).__name__}",
                    file=self._file, line=expr.line, col=expr.col,
                )

    # ------------------------------------------------------------------
    # Expression lowering — specific cases
    # ------------------------------------------------------------------

    def _lower_binop(self, expr: BinOp, op: str, left: Expr, right: Expr) -> LExpr:
        """Lower binary operator. RT-7-3-2."""
        left_expr = self._lower_expr(left)
        right_expr = self._lower_expr(right)
        t = self._type_of(expr)
        lt = self._lower_type(t)
        left_type = self._type_of(left)

        # String concatenation
        if op == "+" and isinstance(left_type, TString):
            return LCall("rf_string_concat", [left_expr, right_expr],
                         LPtr(LStruct("RF_String")))

        # String equality
        if op == "==" and isinstance(left_type, TString):
            return LCall("rf_string_eq", [left_expr, right_expr], LBool())
        if op == "!=" and isinstance(left_type, TString):
            return LUnary("!", LCall("rf_string_eq", [left_expr, right_expr], LBool()),
                          LBool())

        # Congruence operator — compile-time structural type comparison
        if op == "===":
            right_type = self._type_of(right)
            if self._is_congruent(left_type, right_type):
                return LLit("rf_true", LBool())
            else:
                return LLit("rf_false", LBool())

        # Integer checked arithmetic (RT-7-3-2)
        if isinstance(left_type, TInt) and op in ("+", "-", "*", "/", "%"):
            return LCheckedArith(op=op, left=left_expr, right=right_expr, c_type=lt)

        # Logical operators
        if op == "&&":
            return LBinOp(op="&&", left=left_expr, right=right_expr, c_type=LBool())
        if op == "||":
            return LBinOp(op="||", left=left_expr, right=right_expr, c_type=LBool())

        return LBinOp(op=op, left=left_expr, right=right_expr, c_type=lt)

    def _lower_call(self, expr: Call) -> LExpr:
        """Lower function call."""
        t = self._type_of(expr)
        lt = self._lower_type(t)
        lowered_args = [self._lower_expr(a) for a in expr.args]

        if isinstance(expr.callee, Ident):
            # Direct function call
            name = expr.callee.name
            sym = self._resolved.symbols.get(expr.callee)
            # Sum type variant constructor — inline as compound literal
            if (sym is not None and sym.kind == SymbolKind.CONSTRUCTOR
                    and isinstance(sym.decl, SumVariantDecl)):
                return self._lower_variant_ctor(name, sym.decl, t, lt, lowered_args)
            if sym is not None and sym.kind in (SymbolKind.FN, SymbolKind.CONSTRUCTOR):
                c_name = mangle(self._module_path, None, name,
                                file=self._file, line=expr.line, col=expr.col)
                return LCall(c_name, lowered_args, lt)
            # Named import of a native function: import io (println)
            if sym is not None and sym.kind == SymbolKind.IMPORT:
                fn_decl = sym.decl
                if isinstance(fn_decl, FnDecl) and fn_decl.native_name is not None:
                    return LCall(fn_decl.native_name, lowered_args, lt)
            # Check if callee is a closure-typed variable (local var, param)
            callee_type = self._type_of(expr.callee)
            if isinstance(callee_type, TFn):
                callee_expr = self._lower_expr(expr.callee)
                return self._make_closure_call(callee_expr, callee_type, lowered_args, lt)
            # Builtin or unresolved — use name directly
            return LCall(name, lowered_args, lt)

        # Indirect call through expression — closure call
        callee_expr = self._lower_expr(expr.callee)
        callee_type = self._type_of(expr.callee)
        if isinstance(callee_type, TFn):
            return self._make_closure_call(callee_expr, callee_type, lowered_args, lt)
        return LIndirectCall(callee_expr, lowered_args, lt)

    def _lower_variant_ctor(self, name: str, decl: SumVariantDecl,
                            t: Type, lt: LType,
                            lowered_args: list[LExpr]) -> LExpr:
        """Lower a sum type variant constructor to a compound literal.

        Circle(5.0) → (Shape){.tag = 0, .Circle = {.radius = 5.0}}
        """
        if not isinstance(t, TSum):
            return LCall(name, lowered_args, lt)

        # Find the tag for this variant
        tag = next((i for i, v in enumerate(t.variants) if v.name == name), 0)
        variant = t.variants[tag]

        # Build the inner struct for the variant payload
        field_names = [fname for fname, _ in decl.fields] if decl.fields else []
        variant_c_name = f"{lt.c_name}_{name}" if isinstance(lt, LStruct) else name
        inner_fields: list[tuple[str, LExpr]] = []
        for i, arg in enumerate(lowered_args):
            fname = field_names[i] if i < len(field_names) else f"_{i}"
            # Recursive sum field: heap-allocate and store pointer
            if (variant.fields is not None
                    and i < len(variant.fields)
                    and self._is_recursive_sum_field(variant.fields[i], t.name)):
                tmp = self._fresh_temp()
                ptr_type = LPtr(lt)
                # Type* tmp = (Type*)malloc(sizeof(Type));
                self._pending_stmts.append(LVarDecl(
                    c_name=tmp,
                    c_type=ptr_type,
                    init=LCast(
                        LCall("malloc", [LSizeOf(lt)], LPtr(LVoid())),
                        ptr_type),
                ))
                # *tmp = arg;
                self._pending_stmts.append(LAssign(
                    LDeref(LVar(tmp, ptr_type), lt),
                    arg,
                ))
                inner_fields.append((fname, LVar(tmp, ptr_type)))
            else:
                inner_fields.append((fname, arg))

        fields: list[tuple[str, LExpr]] = [("tag", LLit(str(tag), LByte()))]
        if inner_fields:
            fields.append((name, LCompound(
                fields=inner_fields,
                c_type=LStruct(variant_c_name),
            )))
        return LCompound(fields=fields, c_type=lt)

    def _lower_method_call(self, expr: MethodCall) -> LExpr:
        """Lower method call."""
        t = self._type_of(expr)
        lt = self._lower_type(t)

        # Check if resolver bound this to a namespace function symbol
        resolved_sym = self._resolved.symbols.get(expr)
        if resolved_sym is not None and resolved_sym.kind in (
                SymbolKind.FN, SymbolKind.IMPORT):
            fn_decl = resolved_sym.decl
            lowered_args = [self._lower_expr(a) for a in expr.args]
            if isinstance(fn_decl, FnDecl) and fn_decl.native_name is not None:
                # Native function — call the C name directly
                return LCall(fn_decl.native_name, lowered_args, lt)
            # Non-native imported function — use mangled name from source module
            if isinstance(fn_decl, FnDecl):
                # Determine module path from the import's module scope
                src_module = self._resolve_import_module_path(expr.receiver)
                c_name = mangle(src_module, None, fn_decl.name,
                                file=self._file, line=expr.line, col=expr.col)
                return LCall(c_name, lowered_args, lt)

        recv = self._lower_expr(expr.receiver)
        lowered_args = [self._lower_expr(a) for a in expr.args]
        recv_type = self._type_of(expr.receiver)

        if isinstance(recv_type, TCoroutine):
            return self._lower_coroutine_method(expr, recv, recv_type,
                                                lowered_args, lt)

        if isinstance(recv_type, TStream):
            return self._lower_stream_method(expr, recv, recv_type,
                                             lowered_args)

        if isinstance(recv_type, TNamed):
            # User-defined type method
            c_name = mangle(self._module_path, recv_type.name, expr.method,
                            file=self._file, line=expr.line, col=expr.col)
            return LCall(c_name, [LAddrOf(recv, LPtr(self._lower_type(recv_type)))] + lowered_args, lt)

        # Built-in type methods
        method_c_name = f"rf_{self._type_name_str(recv_type)}_{expr.method}"
        return LCall(method_c_name, [recv] + lowered_args, lt)

    def _lower_coroutine_method(self, expr: MethodCall, recv: LExpr,
                                recv_type: TCoroutine,
                                args: list[LExpr], lt: LType) -> LExpr:
        """Lower coroutine method calls (.next, .done, .send)."""
        if expr.method == "next":
            return self._lower_coroutine_next(recv, recv_type)
        elif expr.method == "done":
            return LCall("rf_coroutine_done", [recv], LBool())
        elif expr.method == "send":
            raise EmitError(
                message="coroutine .send() not yet implemented",
                file=self._file, line=expr.line, col=expr.col)
        raise EmitError(
            message=f"unknown coroutine method: {expr.method}",
            file=self._file, line=expr.line, col=expr.col)

    def _lower_coroutine_next(self, recv: LExpr,
                              recv_type: TCoroutine) -> LExpr:
        """Lower coroutine .next() — returns option<yield_type>.

        rf_coroutine_next returns RF_Option_ptr. For pointer-type yields
        this is already correct. For value-type yields we convert to the
        typed option struct (e.g. RF_Option_int).
        """
        yield_t = recv_type.yield_type
        option_t = TOption(yield_t)
        c_option_t = self._lower_type(option_t)

        # Call rf_coroutine_next — returns RF_Option_ptr
        raw_call = LCall("rf_coroutine_next", [recv],
                         LStruct("RF_Option_ptr"))

        # For pointer types, RF_Option_ptr IS the option type
        if self._is_heap_type(yield_t):
            return raw_call

        # For value types, convert RF_Option_ptr → RF_Option_<type>
        raw_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=raw_tmp, c_type=LStruct("RF_Option_ptr"),
            init=raw_call))

        result_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=result_tmp, c_type=c_option_t, init=None))

        # result.tag = raw.tag
        self._pending_stmts.append(LAssign(
            target=LFieldAccess(LVar(result_tmp, c_option_t),
                                "tag", LByte()),
            value=LFieldAccess(LVar(raw_tmp, LStruct("RF_Option_ptr")),
                               "tag", LByte())))

        # if (raw.tag == 1) result.value = (YieldCType)(intptr_t)raw.value
        c_yield_t = self._lower_type(yield_t)
        cast_expr = LCast(
            LCast(
                LFieldAccess(LVar(raw_tmp, LStruct("RF_Option_ptr")),
                             "value", LPtr(LVoid())),
                LInt(64, True)),  # (intptr_t)raw.value
            c_yield_t)           # (rf_int)(intptr_t)raw.value

        self._pending_stmts.append(LIf(
            cond=LBinOp("==",
                LFieldAccess(LVar(raw_tmp, LStruct("RF_Option_ptr")),
                             "tag", LByte()),
                LLit("1", LByte()), LBool()),
            then=[LAssign(
                target=LFieldAccess(LVar(result_tmp, c_option_t),
                                    "value", c_yield_t),
                value=cast_expr)],
            else_=[]))

        return LVar(result_tmp, c_option_t)

    def _lower_stream_method(self, expr: MethodCall, recv: LExpr,
                             recv_type: TStream,
                             args: list[LExpr]) -> LExpr:
        """Lower stream method calls (.take, .skip, .map, .filter, .reduce)."""
        stream_lt = LPtr(LStruct("RF_Stream"))

        if expr.method == "take":
            return LCall("rf_stream_take", [recv, args[0]], stream_lt)

        if expr.method == "skip":
            return LCall("rf_stream_skip", [recv, args[0]], stream_lt)

        if expr.method == "map":
            wrapper = self._lower_stream_closure_wrapper(
                expr.args[0], recv_type.element, "map")
            return LCall("rf_stream_map", [recv, wrapper], stream_lt)

        if expr.method == "filter":
            wrapper = self._lower_stream_closure_wrapper(
                expr.args[0], recv_type.element, "filter")
            return LCall("rf_stream_filter", [recv, wrapper], stream_lt)

        if expr.method == "reduce":
            wrapper = self._lower_stream_closure_wrapper(
                expr.args[1], recv_type.element, "reduce")
            return LCall("rf_stream_reduce",
                         [recv, args[0], wrapper], LPtr(LVoid()))

        raise EmitError(
            message=f"unknown stream method: {expr.method}",
            file=self._file, line=expr.line, col=expr.col)

    def _lower_stream_closure_wrapper(self, closure_ast: Expr,
                                      elem_type: Type,
                                      kind: str) -> LExpr:
        """Generate a void*-based closure wrapper for stream helper methods.

        The stream runtime helpers call closures with (void* env, void* arg)
        signatures. User lambdas have typed signatures like (void* env, rf_int x).
        This method generates a thin wrapper that casts between the two calling
        conventions and wraps the original closure as the environment.
        """
        # Lower the original closure expression
        inner_closure = self._lower_expr(closure_ast)
        closure_lt = LPtr(LStruct("RF_Closure"))

        # Get the closure type from the typechecker
        fn_type = self._type_of(closure_ast)
        if not isinstance(fn_type, TFn):
            return inner_closure

        module = self._module_path
        fn_name = self._current_fn_name or "anon"
        wrapper_id = self._lambda_counter
        self._lambda_counter += 1

        wrapper_c_name = mangle_stream_wrapper(module, fn_name, wrapper_id)

        elem_lt = self._lower_type(elem_type)
        ret_lt = self._lower_type(fn_type.ret)

        if kind == "reduce":
            # Wrapper signature: void* wrapper(void* _env, void* _acc, void* _arg)
            acc_type = fn_type.params[0] if fn_type.params else elem_type
            acc_lt = self._lower_type(acc_type)
            wrapper_params: list[tuple[str, LType]] = [
                ("_env", LPtr(LVoid())),
                ("_acc", LPtr(LVoid())),
                ("_arg", LPtr(LVoid())),
            ]
            wrapper_body: list[LStmt] = []

            # RF_Closure* _inner = (RF_Closure*)_env;
            wrapper_body.append(LVarDecl(
                c_name="_inner", c_type=closure_lt,
                init=LCast(LVar("_env", LPtr(LVoid())), closure_lt)))

            # Cast _acc to typed accumulator
            if isinstance(acc_lt, LPtr):
                typed_acc: LExpr = LCast(
                    LVar("_acc", LPtr(LVoid())), acc_lt)
            else:
                typed_acc = LCast(
                    LCast(LVar("_acc", LPtr(LVoid())), LInt(64, True)),
                    acc_lt)

            # Cast _arg to typed element
            if isinstance(elem_lt, LPtr):
                typed_arg: LExpr = LCast(
                    LVar("_arg", LPtr(LVoid())), elem_lt)
            else:
                typed_arg = LCast(
                    LCast(LVar("_arg", LPtr(LVoid())), LInt(64, True)),
                    elem_lt)

            # Call inner: ((ret(*)(void*, acc_t, elem_t))_inner->fn)(_inner->env, typed_acc, typed_arg)
            fn_ptr_type = LFnPtr([LPtr(LVoid()), acc_lt, elem_lt], ret_lt)
            call_expr = LIndirectCall(
                LCast(LArrow(LVar("_inner", closure_lt), "fn", LPtr(LVoid())),
                      fn_ptr_type),
                [LArrow(LVar("_inner", closure_lt), "env", LPtr(LVoid())),
                 typed_acc, typed_arg],
                ret_lt)

            # Cast result back to void*
            if isinstance(ret_lt, LPtr):
                result_expr: LExpr = LCast(call_expr, LPtr(LVoid()))
            else:
                result_expr = LCast(
                    LCast(call_expr, LInt(64, True)), LPtr(LVoid()))

            wrapper_body.append(LReturn(result_expr))

        else:
            # map/filter: void* wrapper(void* _env, void* _arg)
            wrapper_params = [
                ("_env", LPtr(LVoid())),
                ("_arg", LPtr(LVoid())),
            ]
            wrapper_body = []

            # RF_Closure* _inner = (RF_Closure*)_env;
            wrapper_body.append(LVarDecl(
                c_name="_inner", c_type=closure_lt,
                init=LCast(LVar("_env", LPtr(LVoid())), closure_lt)))

            # Cast _arg to typed element
            if isinstance(elem_lt, LPtr):
                typed_arg = LCast(
                    LVar("_arg", LPtr(LVoid())), elem_lt)
            else:
                typed_arg = LCast(
                    LCast(LVar("_arg", LPtr(LVoid())), LInt(64, True)),
                    elem_lt)

            # Call inner: ((ret(*)(void*, elem_t))_inner->fn)(_inner->env, typed_arg)
            fn_ptr_type = LFnPtr([LPtr(LVoid()), elem_lt], ret_lt)
            call_expr = LIndirectCall(
                LCast(LArrow(LVar("_inner", closure_lt), "fn", LPtr(LVoid())),
                      fn_ptr_type),
                [LArrow(LVar("_inner", closure_lt), "env", LPtr(LVoid())),
                 typed_arg],
                ret_lt)

            # Cast result back to void*
            if isinstance(ret_lt, LPtr):
                result_expr = LCast(call_expr, LPtr(LVoid()))
            else:
                result_expr = LCast(
                    LCast(call_expr, LInt(64, True)), LPtr(LVoid()))

            wrapper_body.append(LReturn(result_expr))

        # Register the wrapper function
        self._fn_defs.append(LFnDef(
            c_name=wrapper_c_name,
            params=wrapper_params,
            ret=LPtr(LVoid()),
            body=wrapper_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}::stream_{kind}_wrapper",
        ))

        # Create a new closure: fn=wrapper, env=original_closure
        wrap_closure_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=wrap_closure_tmp,
            c_type=closure_lt,
            init=LCast(
                LCall("malloc", [LSizeOf(LStruct("RF_Closure"))],
                      LPtr(LVoid())),
                closure_lt),
        ))
        # Set fn = wrapper
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(wrap_closure_tmp, closure_lt),
                          "fn", LPtr(LVoid())),
            value=LCast(LVar(wrapper_c_name, LPtr(LVoid())),
                         LPtr(LVoid())),
        ))
        # Set env = original closure
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(wrap_closure_tmp, closure_lt),
                          "env", LPtr(LVoid())),
            value=LCast(inner_closure, LPtr(LVoid())),
        ))
        return LVar(wrap_closure_tmp, closure_lt)

    def _is_heap_type(self, t: Type) -> bool:
        """Check if a type is heap-allocated (pointer-based)."""
        return isinstance(t, (TString, TArray, TStream, TBuffer,
                              TMap, TSet, TNamed, TSum))

    def _get_direct_fn_c_name(self, expr: Expr) -> str | None:
        """If expr is an Ident bound to SymbolKind.FN, return its mangled C name."""
        if isinstance(expr, Ident):
            sym = self._resolved.symbols.get(expr)
            if sym is not None and sym.kind == SymbolKind.FN:
                return mangle(self._module_path, None, expr.name,
                              file=self._file, line=expr.line, col=expr.col)
            if sym is not None and sym.kind == SymbolKind.IMPORT:
                fn_decl = sym.decl
                if isinstance(fn_decl, FnDecl) and fn_decl.native_name is not None:
                    return fn_decl.native_name
        return None

    def _chain_call(self, elem_expr: Expr, elem_type: TFn,
                    args: list[LExpr], result_type: LType) -> LExpr:
        """Emit a call in a chain context — direct LCall for known functions,
        closure call otherwise."""
        direct_name = self._get_direct_fn_c_name(elem_expr)
        if direct_name is not None:
            return LCall(direct_name, args, result_type)
        fn_expr = self._lower_expr(elem_expr)
        return self._make_closure_call(fn_expr, elem_type, args, result_type)

    def _lower_chain(self, chain: CompositionChain) -> LExpr:
        """Lower composition chain using a value stack. RT-7-3-3."""
        if not chain.elements:
            return LLit("0", LVoid())

        stack: list[LExpr] = []

        for elem in chain.elements:
            elem_expr = elem.expr

            # Fan-out: apply each branch function to the stack top
            if isinstance(elem_expr, FanOut):
                if stack:
                    # Shorthand fan-out: distribute input to each branch
                    input_val = stack.pop()
                    input_type = getattr(input_val, 'c_type', LVoid())
                    tmp = self._fresh_temp()
                    self._pending_stmts.append(
                        LVarDecl(c_name=tmp, c_type=input_type,
                                 init=input_val))

                    for branch in elem_expr.branches:
                        bt = self._type_of(branch.expr)
                        if isinstance(bt, TFn) and len(bt.params) > 0:
                            result_type = self._lower_type(bt.ret)
                            call = self._chain_call(
                                branch.expr, bt,
                                [LVar(tmp, input_type)], result_type)
                            stack.append(call)
                        else:
                            stack.append(self._lower_expr(branch.expr))
                else:
                    # Long form: each branch produces its own value
                    for branch in elem_expr.branches:
                        stack.append(self._lower_expr(branch.expr))
                continue

            elem_type = self._type_of(elem_expr)

            if isinstance(elem_type, TFn):
                arity = len(elem_type.params)
                if arity > 0 and len(stack) >= arity:
                    # Store each arg in a temp, pop from stack
                    args: list[LExpr] = []
                    arg_vals = stack[-arity:]
                    stack = stack[:-arity]
                    for arg_val in arg_vals:
                        arg_type = getattr(arg_val, 'c_type', LVoid())
                        tmp = self._fresh_temp()
                        self._pending_stmts.append(
                            LVarDecl(c_name=tmp, c_type=arg_type,
                                     init=arg_val))
                        args.append(LVar(tmp, arg_type))

                    result_type = self._lower_type(elem_type.ret)
                    stack.append(self._chain_call(
                        elem_expr, elem_type, args, result_type))
                elif arity == 0:
                    result_type = self._lower_type(elem_type.ret)
                    stack.append(self._chain_call(
                        elem_expr, elem_type, [], result_type))
                else:
                    # Not enough values on stack — push as value
                    stack.append(self._lower_expr(elem_expr))
            else:
                stack.append(self._lower_expr(elem_expr))

        return stack[-1] if stack else LLit("0", LVoid())

    # ------------------------------------------------------------------
    # Lambda / closure lowering
    # ------------------------------------------------------------------

    def _lower_lambda(self, expr: Lambda) -> LExpr:
        """Lower a lambda expression to a closure allocation.

        Generates:
        1. Frame struct typedef (if captures exist)
        2. Implementation function with void* _env first param
        3. At expression site: allocate frame, populate captures, create closure
        """
        t = self._type_of(expr)
        if not isinstance(t, TFn):
            return LLit("NULL", LPtr(LStruct("RF_Closure")))

        closure_lt = LPtr(LStruct("RF_Closure"))
        module = self._module_path
        fn_name = self._current_fn_name or "anon"
        lambda_id = self._lambda_counter
        self._lambda_counter += 1

        # Get captures from resolver
        captures = self._resolved.captures.get(expr, [])

        frame_c_name = mangle_closure_frame(module, fn_name, lambda_id)
        impl_c_name = mangle_closure_fn(module, fn_name, lambda_id)

        # 1. Generate frame struct if captures exist
        frame_fields: list[tuple[str, LType]] = []
        if captures:
            for sym in captures:
                cap_type = self._type_of_capture(sym)
                cap_lt = self._lower_type(cap_type)
                frame_fields.append((sym.name, cap_lt))
            self._type_defs.append(LTypeDef(
                c_name=frame_c_name, fields=frame_fields))

        # 2. Generate implementation function
        impl_params: list[tuple[str, LType]] = [("_env", LPtr(LVoid()))]
        for p in expr.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TAny()
            impl_params.append((p.name, self._lower_type(p_type)))

        ret_lt = self._lower_type(t.ret)

        # Save and set up capture remap for lambda body lowering
        saved_remap = self._capture_remap
        self._capture_remap = dict(saved_remap)  # copy parent remap
        saved_fn_name = self._current_fn_name
        self._current_fn_name = f"{fn_name}_lambda{lambda_id}"
        saved_return_type = self._current_fn_return_type
        self._current_fn_return_type = t.ret

        if captures:
            frame_ptr_type = LPtr(LStruct(frame_c_name))
            for sym in captures:
                cap_type = self._type_of_capture(sym)
                cap_lt = self._lower_type(cap_type)
                self._capture_remap[sym.name] = (
                    f"_frame->{sym.name}", cap_lt)

        # Lower body
        impl_body: list[LStmt] = []

        # Cast _env to frame pointer
        if captures:
            frame_ptr_type = LPtr(LStruct(frame_c_name))
            impl_body.append(LVarDecl(
                c_name="_frame",
                c_type=frame_ptr_type,
                init=LCast(LVar("_env", LPtr(LVoid())), frame_ptr_type),
            ))

        # Lower the lambda body expression
        saved_pending = self._pending_stmts
        self._pending_stmts = []
        body_result = self._lower_expr(expr.body)
        impl_body.extend(self._pending_stmts)
        self._pending_stmts = saved_pending
        impl_body.append(LReturn(body_result))

        self._capture_remap = saved_remap
        self._current_fn_name = saved_fn_name
        self._current_fn_return_type = saved_return_type

        self._fn_defs.append(LFnDef(
            c_name=impl_c_name,
            params=impl_params,
            ret=ret_lt,
            body=impl_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}::lambda{lambda_id}",
        ))

        # 3. At expression site: allocate frame and closure
        if captures:
            # Allocate frame
            frame_ptr_type = LPtr(LStruct(frame_c_name))
            frame_tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=frame_tmp,
                c_type=frame_ptr_type,
                init=LCast(
                    LCall("malloc", [LSizeOf(LStruct(frame_c_name))],
                          LPtr(LVoid())),
                    frame_ptr_type),
            ))
            # Populate captures
            for sym in captures:
                cap_type = self._type_of_capture(sym)
                cap_lt = self._lower_type(cap_type)
                # Use the original variable name — may be remapped if nested
                if sym.name in saved_remap:
                    src_expr_str, src_lt = saved_remap[sym.name]
                    src_expr = LVar(src_expr_str, src_lt)
                else:
                    src_expr = LVar(sym.name, cap_lt)
                self._pending_stmts.append(LAssign(
                    target=LArrow(LVar(frame_tmp, frame_ptr_type),
                                  sym.name, cap_lt),
                    value=src_expr,
                ))
            env_expr: LExpr = LCast(
                LVar(frame_tmp, frame_ptr_type), LPtr(LVoid()))
        else:
            env_expr = LLit("NULL", LPtr(LVoid()))

        # Allocate closure
        closure_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=closure_tmp,
            c_type=closure_lt,
            init=LCast(
                LCall("malloc", [LSizeOf(LStruct("RF_Closure"))],
                      LPtr(LVoid())),
                closure_lt),
        ))
        # Set fn pointer
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(closure_tmp, closure_lt),
                          "fn", LPtr(LVoid())),
            value=LCast(LVar(impl_c_name, LPtr(LVoid())), LPtr(LVoid())),
        ))
        # Set env pointer
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(closure_tmp, closure_lt),
                          "env", LPtr(LVoid())),
            value=env_expr,
        ))

        return LVar(closure_tmp, closure_lt)

    def _make_closure_call(self, callee_expr: LExpr, callee_type: TFn,
                           args: list[LExpr], result_lt: LType) -> LExpr:
        """Generate a closure call: extract fn/env from closure, cast fn,
        call with env as first arg."""
        # Store callee in temp to avoid multiple evaluation
        cl_tmp = self._fresh_temp()
        closure_lt = LPtr(LStruct("RF_Closure"))
        self._pending_stmts.append(LVarDecl(
            c_name=cl_tmp, c_type=closure_lt, init=callee_expr))
        cl_var = LVar(cl_tmp, closure_lt)

        # Extract fn and env
        fn_void = LArrow(cl_var, "fn", LPtr(LVoid()))
        env_void = LArrow(cl_var, "env", LPtr(LVoid()))

        # Build function pointer type: ret (*)(void*, param_types...)
        param_ltypes = [self._lower_type(p) for p in callee_type.params]
        fn_ptr_type = LFnPtr([LPtr(LVoid())] + param_ltypes, result_lt)

        # Cast void* fn to correct function pointer type
        casted_fn = LCast(fn_void, fn_ptr_type)

        # Call: fn(env, args...)
        return LIndirectCall(casted_fn, [env_void] + args, result_lt)

    def _wrap_fn_as_closure(self, fn_name: str, fn_type: Type,
                            lt: LType, expr: Ident) -> LExpr:
        """Wrap a named function reference as a closure.

        Generates a thin wrapper function with void* _env (ignored) that
        forwards to the real function, then creates a closure struct.
        """
        if not isinstance(fn_type, TFn):
            fn_c_name = mangle(self._module_path, None, fn_name,
                               file=self._file, line=expr.line, col=expr.col)
            return LVar(fn_c_name, lt)

        fn_c_name = mangle(self._module_path, None, fn_name,
                           file=self._file, line=expr.line, col=expr.col)

        # Check if wrapper already exists
        wrapper_c_name = self._fn_wrapper_registry.get(fn_c_name)
        if wrapper_c_name is None:
            wrapper_c_name = mangle_fn_wrapper(self._module_path, fn_name)
            self._fn_wrapper_registry[fn_c_name] = wrapper_c_name

            # Generate wrapper function: ret wrapper(void* _env, params...) { return real(params...); }
            wrapper_params: list[tuple[str, LType]] = [("_env", LPtr(LVoid()))]
            forward_args: list[LExpr] = []
            for i, pt in enumerate(fn_type.params):
                p_lt = self._lower_type(pt)
                p_name = f"_p{i}"
                wrapper_params.append((p_name, p_lt))
                forward_args.append(LVar(p_name, p_lt))

            ret_lt = self._lower_type(fn_type.ret)
            wrapper_body: list[LStmt] = [
                LReturn(LCall(fn_c_name, forward_args, ret_lt))
            ]

            self._fn_defs.append(LFnDef(
                c_name=wrapper_c_name,
                params=wrapper_params,
                ret=ret_lt,
                body=wrapper_body,
                is_pure=False,
                source_name=f"{self._module_path}.{fn_name}::wrapper",
            ))

        # Create closure with wrapper fn and NULL env
        closure_lt = LPtr(LStruct("RF_Closure"))
        closure_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=closure_tmp,
            c_type=closure_lt,
            init=LCast(
                LCall("malloc", [LSizeOf(LStruct("RF_Closure"))],
                      LPtr(LVoid())),
                closure_lt),
        ))
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(closure_tmp, closure_lt),
                          "fn", LPtr(LVoid())),
            value=LCast(LVar(wrapper_c_name, LPtr(LVoid())), LPtr(LVoid())),
        ))
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(closure_tmp, closure_lt),
                          "env", LPtr(LVoid())),
            value=LLit("NULL", LPtr(LVoid())),
        ))
        return LVar(closure_tmp, closure_lt)

    def _lower_fstring(self, expr: FStringExpr) -> LExpr:
        """Lower f-string to chain of rf_string_concat calls. RT-7-3-4."""
        string_type = LPtr(LStruct("RF_String"))

        parts: list[LExpr] = []
        for part in expr.parts:
            if isinstance(part, str):
                if part:
                    escaped = part.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
                    parts.append(LCall(
                        "rf_string_from_cstr",
                        [LLit(f'"{escaped}"', LPtr(LVoid()))],
                        string_type,
                    ))
            else:
                # Expression part — convert to string
                inner = self._lower_expr(part)
                inner_type = self._type_of(part)
                parts.append(self._to_string_expr(inner, inner_type))

        if not parts:
            return LCall("rf_string_from_cstr",
                         [LLit('""', LPtr(LVoid()))], string_type)

        # Chain concat calls
        result = parts[0]
        for p in parts[1:]:
            tmp = self._fresh_temp()
            self._pending_stmts.append(
                LVarDecl(c_name=tmp, c_type=string_type, init=result))
            result = LCall("rf_string_concat",
                           [LVar(tmp, string_type), p], string_type)

        return result

    def _to_string_expr(self, expr: LExpr, t: Type) -> LExpr:
        """Convert an expression to a string expression for f-string interpolation."""
        string_type = LPtr(LStruct("RF_String"))
        match t:
            case TString():
                return expr
            case TInt(width=32, signed=True):
                return LCall("rf_int_to_string", [expr], string_type)
            case TInt(width=64, signed=True):
                return LCall("rf_int64_to_string", [expr], string_type)
            case TFloat():
                return LCall("rf_float_to_string", [expr], string_type)
            case TBool():
                return LCall("rf_bool_to_string", [expr], string_type)
            case TChar():
                return LCall("rf_char_to_string", [expr], string_type)
            case TInt():
                # Other int widths — cast to int32 first
                return LCall("rf_int_to_string",
                             [LCast(expr, LInt(32, True))], string_type)
            case _:
                # Fallback — cast to int and convert
                return LCall("rf_int_to_string",
                             [LCast(expr, LInt(32, True))], string_type)

    def _lower_match_expr(self, expr: MatchExpr) -> LExpr:
        """Lower match expression to temp var + match statement. RT-7-3-5, RT-7-3-6."""
        result_type = self._type_of(expr)
        result_lt = self._lower_type(result_type)
        result_tmp = self._fresh_temp()

        # Declare result var
        self._pending_stmts.append(
            LVarDecl(c_name=result_tmp, c_type=result_lt, init=None))

        subj_type = self._type_of(expr.subject)
        subj_expr = self._lower_expr(expr.subject)
        subj_tmp = self._fresh_temp()
        subj_lt = self._lower_type(subj_type)
        self._pending_stmts.append(
            LVarDecl(c_name=subj_tmp, c_type=subj_lt, init=subj_expr))
        subj_var = LVar(subj_tmp, subj_lt)

        result_var = LVar(result_tmp, result_lt)

        # Generate match body that assigns to result var
        match subj_type:
            case TSum():
                match_stmts = self._lower_match_sum_expr(
                    subj_var, subj_type, expr.arms, result_var)
            case TOption():
                match_stmts = self._lower_match_option_expr(
                    subj_var, subj_type, expr.arms, result_var)
            case TResult():
                match_stmts = self._lower_match_result_expr(
                    subj_var, subj_type, expr.arms, result_var)
            case TTuple():
                match_stmts = self._lower_match_tuple_expr(
                    subj_var, subj_type, expr.arms, result_var)
            case _:
                match_stmts = self._lower_match_generic_expr(
                    subj_var, subj_type, expr.arms, result_var)

        self._pending_stmts.extend(match_stmts)
        return result_var

    def _lower_propagate(self, expr: PropagateExpr) -> LExpr:
        """Lower propagate (?) operator. RT-7-3-7."""
        inner = self._lower_expr(expr.inner)
        inner_type = self._type_of(expr.inner)

        if not isinstance(inner_type, TResult):
            raise EmitError(
                message="propagate (?) requires a result type",
                file=self._file, line=expr.line, col=expr.col,
            )

        result_lt = self._lower_type(inner_type)
        ok_lt = self._lower_type(inner_type.ok_type)

        # Store result in temp
        tmp = self._fresh_temp()
        self._pending_stmts.append(
            LVarDecl(c_name=tmp, c_type=result_lt, init=inner))

        # if (rf_result_is_err(tmp)) { return tmp; }
        tmp_var = LVar(tmp, result_lt)
        err_check = LIf(
            cond=LBinOp(
                op="==",
                left=LFieldAccess(tmp_var, "tag", LByte()),
                right=LLit("1", LByte()),
                c_type=LBool(),
            ),
            then=[LReturn(tmp_var)],
            else_=[],
        )
        self._pending_stmts.append(err_check)

        # Extract ok value
        ok_tmp = self._fresh_temp()
        ok_value = LFieldAccess(tmp_var, "ok_val", ok_lt)
        self._pending_stmts.append(
            LVarDecl(c_name=ok_tmp, c_type=ok_lt, init=ok_value))

        return LVar(ok_tmp, ok_lt)

    def _lower_copy(self, expr: CopyExpr) -> LExpr:
        """Lower copy expression. RT-7-3-8."""
        inner = self._lower_expr(expr.inner)
        inner_type = self._type_of(expr.inner)

        # Value types — copy is no-op
        if isinstance(inner_type, (TInt, TFloat, TBool, TChar, TByte)):
            return inner

        # Heap types — retain for immutable, deep copy for mutable
        match inner_type:
            case TString():
                self._pending_stmts.append(
                    LExprStmt(LCall("rf_string_retain", [inner], LVoid())))
                return inner
            case TArray():
                self._pending_stmts.append(
                    LExprStmt(LCall("rf_array_retain", [inner], LVoid())))
                return inner
            case TStream():
                self._pending_stmts.append(
                    LExprStmt(LCall("rf_stream_retain", [inner], LVoid())))
                return inner
            case _:
                return inner

    def _lower_null_coalesce(self, expr: NullCoalesce) -> LExpr:
        """Lower ?? operator."""
        left = self._lower_expr(expr.left)
        right = self._lower_expr(expr.right)
        left_type = self._type_of(expr.left)

        if isinstance(left_type, TOption):
            # opt.tag == 1 ? opt.value : default
            inner_lt = self._lower_type(left_type.inner)

            # Store left in temp
            tmp = self._fresh_temp()
            left_lt = self._lower_type(left_type)
            self._pending_stmts.append(
                LVarDecl(c_name=tmp, c_type=left_lt, init=left))
            tmp_var = LVar(tmp, left_lt)

            return LTernary(
                cond=LBinOp(
                    op="==",
                    left=LFieldAccess(tmp_var, "tag", LByte()),
                    right=LLit("1", LByte()),
                    c_type=LBool(),
                ),
                then_expr=LFieldAccess(tmp_var, "value", inner_lt),
                else_expr=right,
                c_type=inner_lt,
            )

        # Non-option — just return left
        return left

    def _lower_some(self, expr: SomeExpr) -> LExpr:
        """Lower some(value)."""
        inner = self._lower_expr(expr.inner)
        t = self._type_of(expr)
        lt = self._lower_type(t)
        return LCompound(
            fields=[("tag", LLit("1", LByte())), ("value", inner)],
            c_type=lt,
        )

    def _lower_ok(self, expr: OkExpr) -> LExpr:
        """Lower ok(value)."""
        inner = self._lower_expr(expr.inner)
        # Use function return type to get concrete result struct
        t = self._current_fn_return_type if isinstance(
            self._current_fn_return_type, TResult) else self._type_of(expr)
        lt = self._lower_type(t)
        return LCompound(
            fields=[("tag", LLit("0", LByte())),
                    ("ok_val", inner)],
            c_type=lt,
        )

    def _lower_err(self, expr: ErrExpr) -> LExpr:
        """Lower err(value)."""
        inner = self._lower_expr(expr.inner)
        # Use function return type to get concrete result struct
        t = self._current_fn_return_type if isinstance(
            self._current_fn_return_type, TResult) else self._type_of(expr)
        lt = self._lower_type(t)
        return LCompound(
            fields=[("tag", LLit("1", LByte())),
                    ("err_val", inner)],
            c_type=lt,
        )

    def _lower_if_expr(self, expr: IfExpr) -> LExpr:
        """Lower if expression to temp var + if statement."""
        result_type = self._type_of(expr)
        result_lt = self._lower_type(result_type)
        result_tmp = self._fresh_temp()

        self._pending_stmts.append(
            LVarDecl(c_name=result_tmp, c_type=result_lt, init=None))

        result_var = LVar(result_tmp, result_lt)
        cond = self._lower_expr(expr.condition)

        # Then branch
        then_stmts = self._lower_block(expr.then_branch)
        # The last expression in the block is the value
        then_assign = self._extract_block_result(then_stmts, result_var)

        # Else branch
        else_stmts: list[LStmt] = []
        if expr.else_branch is not None:
            if isinstance(expr.else_branch, Block):
                else_stmts = self._lower_block(expr.else_branch)
                else_assign = self._extract_block_result(else_stmts, result_var)
            else:
                # Else is another IfExpr
                else_result = self._lower_expr(expr.else_branch)
                else_stmts = list(self._pending_stmts)
                self._pending_stmts = []
                else_stmts.append(LAssign(result_var, else_result))

        self._pending_stmts.append(
            LIf(cond=cond, then=then_assign, else_=else_stmts))

        return result_var

    def _extract_block_result(self, stmts: list[LStmt],
                               result_var: LVar) -> list[LStmt]:
        """Replace the last expression statement with an assignment to result_var."""
        if not stmts:
            return stmts
        last = stmts[-1]
        if isinstance(last, LExprStmt):
            return stmts[:-1] + [LAssign(result_var, last.expr)]
        if isinstance(last, LReturn) and last.value is not None:
            return stmts[:-1] + [LAssign(result_var, last.value)]
        return stmts

    def _lower_array_lit(self, expr: ArrayLit) -> LExpr:
        """Lower array literal."""
        t = self._type_of(expr)
        lt = self._lower_type(t)
        if not expr.elements:
            return LCall("rf_array_new",
                         [LLit("0", LInt(64, True)),
                          LLit("0", LInt(64, True)),
                          LLit("NULL", LPtr(LVoid()))],
                         lt)

        elem_type = TAny()
        if isinstance(t, TArray):
            elem_type = t.element
        elem_lt = self._lower_type(elem_type)

        lowered_elems = [self._lower_expr(e) for e in expr.elements]
        count = len(lowered_elems)

        # Create a compound literal array and pass its address to rf_array_new
        data_expr = LArrayData(
            elements=lowered_elems,
            elem_type=elem_lt,
            c_type=LPtr(elem_lt),
        )
        return LCall("rf_array_new",
                     [LLit(str(count), LInt(64, True)),
                      LSizeOf(elem_lt),
                      data_expr],
                     lt)

    def _lower_type_lit(self, expr: TypeLit) -> LExpr:
        """Lower type literal (struct construction)."""
        t = self._type_of(expr)
        lt = self._lower_type(t)
        lfields: list[tuple[str, LExpr]] = []
        for name, val in expr.fields:
            lfields.append((name, self._lower_expr(val)))
        return LCompound(fields=lfields, c_type=lt)

    # ------------------------------------------------------------------
    # Match lowering helpers
    # ------------------------------------------------------------------

    def _lower_match_sum(self, subj: LVar, sum_t: TSum,
                         arms: list[MatchArm]) -> list[LStmt]:
        """Lower match on sum type to LSwitch. RT-7-3-5."""
        cases: list[tuple[int, list[LStmt]]] = []
        default: list[LStmt] = []

        variant_map = {v.name: i for i, v in enumerate(sum_t.variants)}

        for arm in arms:
            match arm.pattern:
                case VariantPattern(variant_name=vname, bindings=bindings):
                    tag = variant_map.get(vname, -1)
                    if tag < 0:
                        continue
                    body: list[LStmt] = []
                    variant = sum_t.variants[tag]
                    # Bind variant fields using actual field names from TypeDecl
                    if variant.fields is not None:
                        field_names = self._get_variant_field_names(
                            sum_t.name, vname)
                        for i, binding in enumerate(bindings):
                            if i < len(variant.fields):
                                field_lt = self._lower_type(variant.fields[i])
                                fname = field_names[i] if i < len(field_names) else f"_{i}"
                                is_recursive = self._is_recursive_sum_field(
                                    variant.fields[i], sum_t.name)
                                if is_recursive:
                                    # Field is a pointer — dereference to get value
                                    ptr_lt = LPtr(field_lt)
                                    field_access = LFieldAccess(
                                        LFieldAccess(subj, vname, subj.c_type),
                                        fname, ptr_lt)
                                    body.append(LVarDecl(
                                        c_name=binding,
                                        c_type=field_lt,
                                        init=LDeref(field_access, field_lt),
                                    ))
                                else:
                                    body.append(LVarDecl(
                                        c_name=binding,
                                        c_type=field_lt,
                                        init=LFieldAccess(
                                            LFieldAccess(subj, vname, subj.c_type),
                                            fname, field_lt),
                                    ))
                    body.extend(self._lower_arm_body_stmts(arm))
                    cases.append((tag, body))

                case BindPattern(name=bname) if bname in variant_map:
                    # Unit variant pattern: bare name matches a variant
                    tag = variant_map[bname]
                    body = self._lower_arm_body_stmts(arm)
                    cases.append((tag, body))

                case WildcardPattern() | BindPattern():
                    default = self._lower_arm_body_stmts(arm)

        tag_access = LFieldAccess(subj, "tag", LByte())
        return [LSwitch(value=tag_access, cases=cases, default=default)]

    def _lower_arm_body_stmts(self, arm: MatchArm) -> list[LStmt]:
        """Lower a match arm's body to a list of statements."""
        match arm.body:
            case Block():
                return self._lower_block(arm.body)
            case Expr():
                saved = self._pending_stmts
                self._pending_stmts = []
                val = self._lower_expr(arm.body)
                stmts = list(self._pending_stmts)
                self._pending_stmts = saved
                stmts.append(LExprStmt(val))
                return stmts
        return []

    def _get_variant_field_names(self, sum_name: str, vname: str) -> list[str]:
        """Get field names for a variant by looking up the SumVariantDecl in the AST."""
        for decl in self._module.decls:
            if isinstance(decl, TypeDecl) and decl.name == sum_name and decl.is_sum_type:
                for variant in decl.variants:
                    if variant.name == vname and variant.fields is not None:
                        return [fname for fname, _ in variant.fields]
        return []

    def _lower_match_option(self, subj: LVar, opt_t: TOption,
                            arms: list[MatchArm]) -> list[LStmt]:
        """Lower match on option to LIf. RT-7-3-6."""
        some_body: list[LStmt] = []
        none_body: list[LStmt] = []
        some_var: str | None = None

        for arm in arms:
            match arm.pattern:
                case SomePattern(inner_var=var):
                    some_var = var
                    inner_lt = self._lower_type(opt_t.inner)
                    some_body.append(LVarDecl(
                        c_name=var, c_type=inner_lt,
                        init=LFieldAccess(subj, "value", inner_lt)))
                    match arm.body:
                        case Block():
                            some_body.extend(self._lower_block(arm.body))
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            val = self._lower_expr(arm.body)
                            some_body.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            some_body.append(LExprStmt(val))

                case NonePattern():
                    match arm.body:
                        case Block():
                            none_body = self._lower_block(arm.body)
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            val = self._lower_expr(arm.body)
                            none_body.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            none_body.append(LExprStmt(val))

                case WildcardPattern() | BindPattern():
                    match arm.body:
                        case Block():
                            none_body = self._lower_block(arm.body)
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            val = self._lower_expr(arm.body)
                            none_body.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            none_body.append(LExprStmt(val))

        # if (subj.tag == 1) { some_body } else { none_body }
        tag_check = LBinOp(
            op="==",
            left=LFieldAccess(subj, "tag", LByte()),
            right=LLit("1", LByte()),
            c_type=LBool(),
        )
        return [LIf(cond=tag_check, then=some_body, else_=none_body)]

    def _lower_match_result(self, subj: LVar, res_t: TResult,
                            arms: list[MatchArm]) -> list[LStmt]:
        """Lower match on result to LIf."""
        ok_body: list[LStmt] = []
        err_body: list[LStmt] = []

        for arm in arms:
            match arm.pattern:
                case OkPattern(inner_var=var):
                    ok_lt = self._lower_type(res_t.ok_type)
                    ok_body.append(LVarDecl(
                        c_name=var, c_type=ok_lt,
                        init=LFieldAccess(subj, "ok_val", ok_lt)))
                    match arm.body:
                        case Block():
                            ok_body.extend(self._lower_block(arm.body))
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            val = self._lower_expr(arm.body)
                            ok_body.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            ok_body.append(LExprStmt(val))

                case ErrPattern(inner_var=var):
                    err_lt = self._lower_type(res_t.err_type)
                    err_body.append(LVarDecl(
                        c_name=var, c_type=err_lt,
                        init=LFieldAccess(subj, "err_val", err_lt)))
                    match arm.body:
                        case Block():
                            err_body.extend(self._lower_block(arm.body))
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            val = self._lower_expr(arm.body)
                            err_body.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            err_body.append(LExprStmt(val))

                case WildcardPattern() | BindPattern():
                    match arm.body:
                        case Block():
                            err_body = self._lower_block(arm.body)
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            val = self._lower_expr(arm.body)
                            err_body.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            err_body.append(LExprStmt(val))

        # if (subj.tag == 0) { ok_body } else { err_body }
        tag_check = LBinOp(
            op="==",
            left=LFieldAccess(subj, "tag", LByte()),
            right=LLit("0", LByte()),
            c_type=LBool(),
        )
        return [LIf(cond=tag_check, then=ok_body, else_=err_body)]

    def _lower_match_tuple(self, subj: LVar, tup_t: TTuple,
                           arms: list[MatchArm]) -> list[LStmt]:
        """Lower match on tuple type to pattern bindings."""
        for arm in arms:
            match arm.pattern:
                case TuplePattern(elements=elements):
                    body: list[LStmt] = []
                    for i, elem_pat in enumerate(elements):
                        if i < len(tup_t.elements):
                            elem_lt = self._lower_type(tup_t.elements[i])
                            field_access = LFieldAccess(subj, f"_{i}", elem_lt)
                            match elem_pat:
                                case BindPattern(name=bname):
                                    body.append(LVarDecl(
                                        c_name=bname, c_type=elem_lt,
                                        init=field_access))
                                case WildcardPattern():
                                    pass  # No binding needed
                    body.extend(self._lower_arm_body_stmts(arm))
                    return body

                case WildcardPattern() | BindPattern():
                    body = []
                    if isinstance(arm.pattern, BindPattern):
                        body.append(LVarDecl(
                            c_name=arm.pattern.name,
                            c_type=subj.c_type, init=subj))
                    body.extend(self._lower_arm_body_stmts(arm))
                    return body

        return []

    def _lower_match_generic(self, subj: LVar, subj_type: Type,
                             arms: list[MatchArm]) -> list[LStmt]:
        """Lower match on primitive/other types to if-else chain."""
        if not arms:
            return []

        # Build if-else chain from arms
        stmts: list[LStmt] = []
        remaining = list(arms)

        while remaining:
            arm = remaining.pop(0)
            match arm.pattern:
                case LiteralPattern(value=val):
                    cond = self._make_equality_check(subj, val, subj_type)
                    match arm.body:
                        case Block():
                            body = self._lower_block(arm.body)
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            expr = self._lower_expr(arm.body)
                            body = list(self._pending_stmts)
                            self._pending_stmts = saved
                            body.append(LExprStmt(expr))

                    if remaining:
                        else_stmts = self._lower_match_generic(subj, subj_type, remaining)
                        stmts.append(LIf(cond=cond, then=body, else_=else_stmts))
                    else:
                        stmts.append(LIf(cond=cond, then=body, else_=[]))
                    return stmts

                case WildcardPattern() | BindPattern():
                    if isinstance(arm.pattern, BindPattern):
                        body_stmts: list[LStmt] = [
                            LVarDecl(c_name=arm.pattern.name,
                                     c_type=subj.c_type, init=subj)]
                    else:
                        body_stmts = []
                    match arm.body:
                        case Block():
                            body_stmts.extend(self._lower_block(arm.body))
                        case Expr():
                            saved = self._pending_stmts
                            self._pending_stmts = []
                            expr = self._lower_expr(arm.body)
                            body_stmts.extend(self._pending_stmts)
                            self._pending_stmts = saved
                            body_stmts.append(LExprStmt(expr))
                    stmts.extend(body_stmts)
                    return stmts

                case _:
                    # Unsupported pattern — skip
                    continue

        return stmts

    # Match expression variants (assign to result_var)
    def _lower_match_sum_expr(self, subj: LVar, sum_t: TSum,
                               arms: list[MatchArm], result: LVar) -> list[LStmt]:
        cases: list[tuple[int, list[LStmt]]] = []
        default: list[LStmt] = []
        variant_map = {v.name: i for i, v in enumerate(sum_t.variants)}

        for arm in arms:
            match arm.pattern:
                case VariantPattern(variant_name=vname, bindings=bindings):
                    tag = variant_map.get(vname, -1)
                    if tag < 0:
                        continue
                    body: list[LStmt] = []
                    variant = sum_t.variants[tag]
                    if variant.fields is not None:
                        field_names = self._get_variant_field_names(
                            sum_t.name, vname)
                        for i, binding in enumerate(bindings):
                            if i < len(variant.fields):
                                field_lt = self._lower_type(variant.fields[i])
                                fname = field_names[i] if i < len(field_names) else f"_{i}"
                                is_recursive = self._is_recursive_sum_field(
                                    variant.fields[i], sum_t.name)
                                if is_recursive:
                                    ptr_lt = LPtr(field_lt)
                                    field_access = LFieldAccess(
                                        LFieldAccess(subj, vname, subj.c_type),
                                        fname, ptr_lt)
                                    body.append(LVarDecl(
                                        c_name=binding, c_type=field_lt,
                                        init=LDeref(field_access, field_lt)))
                                else:
                                    body.append(LVarDecl(
                                        c_name=binding, c_type=field_lt,
                                        init=LFieldAccess(
                                            LFieldAccess(subj, vname, subj.c_type),
                                            fname, field_lt)))
                    val = self._lower_arm_body(arm)
                    body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    body.append(LAssign(result, val))
                    cases.append((tag, body))

                case BindPattern(name=bname) if bname in variant_map:
                    # Unit variant pattern in expression context
                    tag = variant_map[bname]
                    val = self._lower_arm_body(arm)
                    body = list(self._pending_stmts)
                    self._pending_stmts = []
                    body.append(LAssign(result, val))
                    cases.append((tag, body))

                case WildcardPattern() | BindPattern():
                    val = self._lower_arm_body(arm)
                    default.extend(self._pending_stmts)
                    self._pending_stmts = []
                    default.append(LAssign(result, val))

        tag_access = LFieldAccess(subj, "tag", LByte())
        return [LSwitch(value=tag_access, cases=cases, default=default)]

    def _lower_match_option_expr(self, subj: LVar, opt_t: TOption,
                                  arms: list[MatchArm], result: LVar) -> list[LStmt]:
        some_body: list[LStmt] = []
        none_body: list[LStmt] = []

        for arm in arms:
            match arm.pattern:
                case SomePattern(inner_var=var):
                    inner_lt = self._lower_type(opt_t.inner)
                    some_body.append(LVarDecl(
                        c_name=var, c_type=inner_lt,
                        init=LFieldAccess(subj, "value", inner_lt)))
                    val = self._lower_arm_body(arm)
                    some_body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    some_body.append(LAssign(result, val))

                case NonePattern():
                    val = self._lower_arm_body(arm)
                    none_body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    none_body.append(LAssign(result, val))

                case WildcardPattern() | BindPattern():
                    val = self._lower_arm_body(arm)
                    none_body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    none_body.append(LAssign(result, val))

        tag_check = LBinOp(
            op="==",
            left=LFieldAccess(subj, "tag", LByte()),
            right=LLit("1", LByte()),
            c_type=LBool(),
        )
        return [LIf(cond=tag_check, then=some_body, else_=none_body)]

    def _lower_match_result_expr(self, subj: LVar, res_t: TResult,
                                  arms: list[MatchArm], result: LVar) -> list[LStmt]:
        ok_body: list[LStmt] = []
        err_body: list[LStmt] = []

        for arm in arms:
            match arm.pattern:
                case OkPattern(inner_var=var):
                    ok_lt = self._lower_type(res_t.ok_type)
                    ok_body.append(LVarDecl(
                        c_name=var, c_type=ok_lt,
                        init=LFieldAccess(subj, "ok_val", ok_lt)))
                    val = self._lower_arm_body(arm)
                    ok_body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    ok_body.append(LAssign(result, val))

                case ErrPattern(inner_var=var):
                    err_lt = self._lower_type(res_t.err_type)
                    err_body.append(LVarDecl(
                        c_name=var, c_type=err_lt,
                        init=LFieldAccess(subj, "err_val", err_lt)))
                    val = self._lower_arm_body(arm)
                    err_body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    err_body.append(LAssign(result, val))

                case WildcardPattern() | BindPattern():
                    val = self._lower_arm_body(arm)
                    err_body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    err_body.append(LAssign(result, val))

        tag_check = LBinOp(
            op="==",
            left=LFieldAccess(subj, "tag", LByte()),
            right=LLit("0", LByte()),
            c_type=LBool(),
        )
        return [LIf(cond=tag_check, then=ok_body, else_=err_body)]

    def _lower_match_tuple_expr(self, subj: LVar, tup_t: TTuple,
                                arms: list[MatchArm], result: LVar) -> list[LStmt]:
        """Lower match expression on tuple type to pattern bindings."""
        for arm in arms:
            match arm.pattern:
                case TuplePattern(elements=elements):
                    body: list[LStmt] = []
                    for i, elem_pat in enumerate(elements):
                        if i < len(tup_t.elements):
                            elem_lt = self._lower_type(tup_t.elements[i])
                            field_access = LFieldAccess(subj, f"_{i}", elem_lt)
                            match elem_pat:
                                case BindPattern(name=bname):
                                    body.append(LVarDecl(
                                        c_name=bname, c_type=elem_lt,
                                        init=field_access))
                                case WildcardPattern():
                                    pass
                    saved = self._pending_stmts
                    self._pending_stmts = []
                    val = self._lower_arm_body(arm)
                    body.extend(self._pending_stmts)
                    self._pending_stmts = saved
                    body.append(LAssign(result, val))
                    return body

                case WildcardPattern() | BindPattern():
                    body: list[LStmt] = []
                    if isinstance(arm.pattern, BindPattern):
                        body.append(LVarDecl(
                            c_name=arm.pattern.name,
                            c_type=subj.c_type, init=subj))
                    saved = self._pending_stmts
                    self._pending_stmts = []
                    val = self._lower_arm_body(arm)
                    body.extend(self._pending_stmts)
                    self._pending_stmts = saved
                    body.append(LAssign(result, val))
                    return body

        return []

    def _lower_match_generic_expr(self, subj: LVar, subj_type: Type,
                                   arms: list[MatchArm], result: LVar) -> list[LStmt]:
        if not arms:
            return []

        remaining = list(arms)
        stmts: list[LStmt] = []

        while remaining:
            arm = remaining.pop(0)
            match arm.pattern:
                case LiteralPattern(value=val):
                    cond = self._make_equality_check(subj, val, subj_type)
                    body: list[LStmt] = []
                    arm_val = self._lower_arm_body(arm)
                    body.extend(self._pending_stmts)
                    self._pending_stmts = []
                    body.append(LAssign(result, arm_val))

                    if remaining:
                        else_stmts = self._lower_match_generic_expr(
                            subj, subj_type, remaining, result)
                        stmts.append(LIf(cond=cond, then=body, else_=else_stmts))
                    else:
                        stmts.append(LIf(cond=cond, then=body, else_=[]))
                    return stmts

                case WildcardPattern() | BindPattern():
                    if isinstance(arm.pattern, BindPattern):
                        stmts.append(LVarDecl(
                            c_name=arm.pattern.name, c_type=subj.c_type, init=subj))
                    arm_val = self._lower_arm_body(arm)
                    stmts.extend(self._pending_stmts)
                    self._pending_stmts = []
                    stmts.append(LAssign(result, arm_val))
                    return stmts

                case _:
                    continue

        return stmts

    def _lower_arm_body(self, arm: MatchArm) -> LExpr:
        """Lower match arm body and return the result expression."""
        match arm.body:
            case Block():
                block_stmts = self._lower_block(arm.body)
                # Find the last expression
                if block_stmts and isinstance(block_stmts[-1], LExprStmt):
                    self._pending_stmts.extend(block_stmts[:-1])
                    return block_stmts[-1].expr
                if block_stmts and isinstance(block_stmts[-1], LReturn) and block_stmts[-1].value is not None:
                    self._pending_stmts.extend(block_stmts[:-1])
                    return block_stmts[-1].value
                self._pending_stmts.extend(block_stmts)
                return LLit("0", LVoid())
            case Expr():
                return self._lower_expr(arm.body)

    def _make_equality_check(self, subj: LVar, val: Expr, subj_type: Type) -> LExpr:
        """Create an equality comparison for pattern matching."""
        val_expr = self._lower_expr(val)
        if isinstance(subj_type, TString):
            return LCall("rf_string_eq", [subj, val_expr], LBool())
        return LBinOp(op="==", left=subj, right=val_expr, c_type=LBool())

    # ------------------------------------------------------------------
    # Stream function lowering (RT-7-5-1 through RT-7-5-3)
    # ------------------------------------------------------------------

    def _lower_stream_fn(self, fn: FnDecl) -> None:
        """Lower a stream function to frame struct + next + free + factory.
        RT-7-5-1."""
        if fn.body is None:
            return

        module = self._module_path
        fn_name = fn.name

        frame_c_name = mangle_stream_frame(module, fn_name)
        next_c_name = mangle_stream_next(module, fn_name)
        free_c_name = mangle_stream_free(module, fn_name)
        factory_c_name = mangle(module, None, fn_name,
                                 file=self._file, line=fn.line, col=fn.col)

        # Determine element type from stream<T> return type
        ret_type = self._type_of_return(fn)
        elem_type = TAny()
        if isinstance(ret_type, TStream):
            elem_type = ret_type.element

        # 1. Collect yield points and locals
        yield_stmts = self._collect_yields(fn.body)
        num_states = len(yield_stmts) + 1  # +1 for initial state

        # 2. Build frame struct with all params and locals
        frame_fields: list[tuple[str, LType]] = [
            ("_state", LInt(32, True)),
        ]
        # Add parameters to frame
        for p in fn.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
            frame_fields.append((p.name, self._lower_type(p_type)))
        # Add locals from body
        local_names = self._collect_locals(fn.body)
        for name, local_type in local_names:
            frame_fields.append((name, self._lower_type(local_type)))

        self._type_defs.append(LTypeDef(c_name=frame_c_name, fields=frame_fields))

        # 3. Build next function
        frame_ptr_type = LPtr(LStruct(frame_c_name))
        option_ptr_type = LStruct("RF_Option_ptr")

        # next function body: cast self->state to frame, switch on _state
        next_body: list[LStmt] = []

        # frame_type* frame = (frame_type*)self->state;
        frame_var_name = "frame"
        next_body.append(LVarDecl(
            c_name=frame_var_name,
            c_type=frame_ptr_type,
            init=LCast(
                LArrow(LVar("self", LPtr(LStruct("RF_Stream"))),
                       "state", LPtr(LVoid())),
                frame_ptr_type),
        ))

        # Collect frame variable names for rewriting
        frame_var_names: set[str] = set()
        for p in fn.params:
            frame_var_names.add(p.name)
        for name, _ in local_names:
            frame_var_names.add(name)

        # Build state machine body (goto-based dispatch)
        state_machine_stmts = self._build_stream_states(
            fn.body, frame_var_name, frame_c_name,
            elem_type, yield_stmts, frame_var_names)
        next_body.extend(state_machine_stmts)

        self._fn_defs.append(LFnDef(
            c_name=next_c_name,
            params=[("self", LPtr(LStruct("RF_Stream")))],
            ret=option_ptr_type,
            body=next_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}::next",
        ))

        # 4. Build free function
        free_body: list[LStmt] = []
        free_body.append(LVarDecl(
            c_name=frame_var_name,
            c_type=frame_ptr_type,
            init=LCast(
                LArrow(LVar("self", LPtr(LStruct("RF_Stream"))),
                       "state", LPtr(LVoid())),
                frame_ptr_type),
        ))
        # free(frame)
        free_body.append(LExprStmt(LCall("free",
                                          [LVar(frame_var_name, frame_ptr_type)],
                                          LVoid())))

        self._fn_defs.append(LFnDef(
            c_name=free_c_name,
            params=[("self", LPtr(LStruct("RF_Stream")))],
            ret=LVoid(),
            body=free_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}::free",
        ))

        # 5. Build factory function
        factory_body: list[LStmt] = []

        # frame_type* frame = malloc(sizeof(frame_type))
        factory_body.append(LVarDecl(
            c_name=frame_var_name,
            c_type=frame_ptr_type,
            init=LCast(
                LCall("malloc", [LSizeOf(LStruct(frame_c_name))],
                      LPtr(LVoid())),
                frame_ptr_type),
        ))

        # frame->_state = 0
        factory_body.append(LAssign(
            target=LArrow(LVar(frame_var_name, frame_ptr_type),
                          "_state", LInt(32, True)),
            value=LLit("0", LInt(32, True)),
        ))

        # Copy params to frame
        for p in fn.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
            factory_body.append(LAssign(
                target=LArrow(LVar(frame_var_name, frame_ptr_type),
                              p.name, self._lower_type(p_type)),
                value=LVar(p.name, self._lower_type(p_type)),
            ))

        # return rf_stream_new(next, free, frame)
        factory_body.append(LReturn(
            LCall("rf_stream_new",
                  [LVar(next_c_name, LPtr(LVoid())),
                   LVar(free_c_name, LPtr(LVoid())),
                   LCast(LVar(frame_var_name, frame_ptr_type), LPtr(LVoid()))],
                  LPtr(LStruct("RF_Stream"))),
        ))

        factory_params: list[tuple[str, LType]] = []
        for p in fn.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
            factory_params.append((p.name, self._lower_type(p_type)))

        self._fn_defs.append(LFnDef(
            c_name=factory_c_name,
            params=factory_params,
            ret=LPtr(LStruct("RF_Stream")),
            body=factory_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}",
        ))

    def _resolve_import_module_path(self, receiver: Expr) -> str:
        """Get the module path for a namespace import receiver."""
        if isinstance(receiver, Ident):
            # Look up the import to find the original module path
            for imp in self._module.imports:
                ns_name = imp.alias if imp.alias else imp.path[-1]
                if ns_name == receiver.name:
                    return ".".join(imp.path)
        return self._module_path

    def _collect_yields(self, body: Block | Expr | None) -> list[YieldStmt]:
        """Collect all yield statements in a function body."""
        yields: list[YieldStmt] = []
        if body is None:
            return yields
        if isinstance(body, Block):
            for stmt in body.stmts:
                yields.extend(self._collect_yields_stmt(stmt))
        return yields

    def _collect_yields_stmt(self, stmt: Stmt) -> list[YieldStmt]:
        yields: list[YieldStmt] = []
        match stmt:
            case YieldStmt():
                yields.append(stmt)
            case IfStmt(then_branch=tb, else_branch=eb):
                for s in tb.stmts:
                    yields.extend(self._collect_yields_stmt(s))
                if eb is not None:
                    if isinstance(eb, Block):
                        for s in eb.stmts:
                            yields.extend(self._collect_yields_stmt(s))
                    elif isinstance(eb, IfStmt):
                        yields.extend(self._collect_yields_stmt(eb))
            case WhileStmt(body=b):
                for s in b.stmts:
                    yields.extend(self._collect_yields_stmt(s))
            case ForStmt(body=b):
                for s in b.stmts:
                    yields.extend(self._collect_yields_stmt(s))
            case _:
                pass
        return yields

    def _collect_locals(self, body: Block | Expr | None) -> list[tuple[str, Type]]:
        """Collect all let-bound locals in a function body (conservative)."""
        locals_: list[tuple[str, Type]] = []
        if body is None:
            return locals_
        if isinstance(body, Block):
            for stmt in body.stmts:
                self._collect_locals_stmt(stmt, locals_)
        return locals_

    def _collect_locals_stmt(self, stmt: Stmt,
                             locals_: list[tuple[str, Type]]) -> None:
        existing_names = {n for n, _ in locals_}
        match stmt:
            case LetStmt(name=name, value=value):
                if name not in existing_names:
                    t = self._type_of(value)
                    locals_.append((name, t))
            case IfStmt(then_branch=tb, else_branch=eb):
                for s in tb.stmts:
                    self._collect_locals_stmt(s, locals_)
                if eb is not None:
                    if isinstance(eb, Block):
                        for s in eb.stmts:
                            self._collect_locals_stmt(s, locals_)
                    elif isinstance(eb, IfStmt):
                        self._collect_locals_stmt(eb, locals_)
            case WhileStmt(body=b):
                for s in b.stmts:
                    self._collect_locals_stmt(s, locals_)
            case ForStmt(var=var, body=b):
                if var not in existing_names:
                    iter_type = self._type_of(stmt.iterable)
                    elem_type = TAny()
                    if isinstance(iter_type, TArray):
                        elem_type = iter_type.element
                    elif isinstance(iter_type, TStream):
                        elem_type = iter_type.element
                    locals_.append((var, elem_type))
                for s in b.stmts:
                    self._collect_locals_stmt(s, locals_)
            case _:
                pass

    def _build_stream_states(self, body: Block | Expr | None,
                              frame_var: str,
                              frame_c_name: str,
                              elem_type: Type,
                              yield_stmts: list[YieldStmt],
                              frame_names: set[str]) -> list[LStmt]:
        """Build goto-based state machine for stream function.

        Returns a flat list of statements (not switch cases) that form the
        state machine: a switch dispatch at the top, then the lowered body
        with yields replaced by state transitions and goto labels.
        """
        if body is None or not isinstance(body, Block):
            return []

        option_ptr_type = LStruct("RF_Option_ptr")
        num_yields = len(yield_stmts)

        # Lower body with yields converted to state transitions + gotos
        yield_counter = [0]  # mutable counter shared across recursion
        body_stmts = self._lower_stream_stmts(
            body.stmts, frame_var, elem_type, yield_counter)

        # Rewrite all frame variable references to use frame-> access
        body_stmts = self._rewrite_frame_access(
            body_stmts, frame_var, frame_c_name, frame_names)

        # Terminal: return RF_NONE
        done_label = "_rf_stream_done"
        body_stmts.append(LLabel(done_label))
        frame_ptr_type = LPtr(LStruct(frame_c_name))
        body_stmts.append(LAssign(
            target=LArrow(LVar(frame_var, frame_ptr_type),
                          "_state", LInt(32, True)),
            value=LLit("-1", LInt(32, True))))
        body_stmts.append(LReturn(LCompound(
            fields=[("tag", LLit("0", LByte())),
                    ("value", LLit("NULL", LPtr(LVoid())))],
            c_type=option_ptr_type)))

        # Build switch dispatch: case 0 → _state_0, case 1 → _state_1, ...
        switch_cases: list[tuple[int, list[LStmt]]] = []
        for i in range(num_yields + 1):
            switch_cases.append((i, [LGoto(f"_rf_state_{i}")]))
        switch_default = [LGoto(done_label)]

        frame_state = LArrow(
            LVar(frame_var, LPtr(LStruct(frame_c_name))),
            "_state", LInt(32, True))

        result: list[LStmt] = []
        result.append(LSwitch(value=frame_state, cases=switch_cases,
                               default=switch_default))
        # State 0 label — initial entry
        result.append(LLabel("_rf_state_0"))
        result.extend(body_stmts)

        return result

    def _lower_stream_stmts(self, stmts: list[Stmt], frame_var: str,
                              elem_type: Type,
                              yield_counter: list[int]) -> list[LStmt]:
        """Lower a list of statements for stream body, handling yields
        at any nesting level."""
        result: list[LStmt] = []
        option_ptr_type = LStruct("RF_Option_ptr")

        for stmt in stmts:
            if isinstance(stmt, YieldStmt):
                # Lower the yield value
                saved = self._pending_stmts
                self._pending_stmts = []
                value = self._lower_expr(stmt.value)
                result.extend(self._pending_stmts)
                self._pending_stmts = saved

                yield_counter[0] += 1
                state_num = yield_counter[0]

                # Set next state
                frame_ptr_type = LPtr(LStruct(frame_var))
                result.append(LAssign(
                    target=LArrow(LVar(frame_var, frame_ptr_type),
                                  "_state", LInt(32, True)),
                    value=LLit(str(state_num), LInt(32, True)),
                ))

                # Return RF_SOME(value) — cast through uintptr_t for value types
                void_value = LCast(LCast(value, LInt(64, False)), LPtr(LVoid()))
                result.append(LReturn(LCompound(
                    fields=[("tag", LLit("1", LByte())),
                            ("value", void_value)],
                    c_type=option_ptr_type)))

                # Resume label for this yield point
                result.append(LLabel(f"_rf_state_{state_num}"))

            elif isinstance(stmt, ReturnStmt):
                result.append(LGoto("_rf_stream_done"))

            elif isinstance(stmt, WhileStmt):
                # Lower while loop, recursing into body for yields
                cond = self._lower_expr(stmt.condition)
                loop_body = self._lower_stream_stmts(
                    stmt.body.stmts, frame_var, elem_type, yield_counter)
                result.append(LWhile(cond=cond, body=loop_body))

            elif isinstance(stmt, IfStmt):
                cond = self._lower_expr(stmt.condition)
                then_body = self._lower_stream_stmts(
                    stmt.then_branch.stmts, frame_var, elem_type, yield_counter)
                else_body: list[LStmt] = []
                if stmt.else_branch is not None:
                    if isinstance(stmt.else_branch, Block):
                        else_body = self._lower_stream_stmts(
                            stmt.else_branch.stmts, frame_var,
                            elem_type, yield_counter)
                    elif isinstance(stmt.else_branch, IfStmt):
                        else_body = self._lower_stream_stmts(
                            [stmt.else_branch], frame_var,
                            elem_type, yield_counter)
                result.append(LIf(cond=cond, then=then_body, else_=else_body))

            elif isinstance(stmt, ForStmt):
                # Lower for loop normally, recurse into body
                for_stmts = self._lower_for(stmt)
                # The for lowering returns a list with LWhile; we need to
                # handle yields inside. For simplicity, just include as-is.
                result.extend(for_stmts)

            else:
                saved = self._pending_stmts
                self._pending_stmts = []
                lowered = self._lower_stmt(stmt)
                result.extend(self._pending_stmts)
                result.extend(lowered)
                self._pending_stmts = saved

        return result

    # ------------------------------------------------------------------
    # Stream frame variable rewriting
    # ------------------------------------------------------------------

    def _rewrite_frame_access(self, stmts: list[LStmt],
                                frame_var: str,
                                frame_c_name: str,
                                frame_names: set[str]) -> list[LStmt]:
        """Rewrite variable references in stream body to use frame-> access."""
        return [self._rewrite_stmt(s, frame_var, frame_c_name, frame_names)
                for s in stmts]

    def _rewrite_stmt(self, stmt: LStmt, fv: str, fc: str,
                       names: set[str]) -> LStmt:
        fpt = LPtr(LStruct(fc))
        match stmt:
            case LVarDecl(c_name=name, c_type=ct, init=init):
                if name in names:
                    # Convert to frame->name = init
                    if init is not None:
                        return LAssign(
                            target=LArrow(LVar(fv, fpt), name, ct),
                            value=self._rewrite_expr(init, fv, fc, names))
                    # No init — skip (frame field is already allocated)
                    return LBlock(stmts=[])
                new_init = self._rewrite_expr(init, fv, fc, names) if init else None
                return LVarDecl(c_name=name, c_type=ct, init=new_init)
            case LAssign(target=target, value=value):
                return LAssign(
                    target=self._rewrite_expr(target, fv, fc, names),
                    value=self._rewrite_expr(value, fv, fc, names))
            case LReturn(value=value):
                new_val = self._rewrite_expr(value, fv, fc, names) if value else None
                return LReturn(new_val)
            case LExprStmt(expr=expr):
                return LExprStmt(self._rewrite_expr(expr, fv, fc, names))
            case LIf(cond=cond, then=then, else_=else_):
                return LIf(
                    cond=self._rewrite_expr(cond, fv, fc, names),
                    then=self._rewrite_frame_access(then, fv, fc, names),
                    else_=self._rewrite_frame_access(else_, fv, fc, names))
            case LWhile(cond=cond, body=body):
                return LWhile(
                    cond=self._rewrite_expr(cond, fv, fc, names),
                    body=self._rewrite_frame_access(body, fv, fc, names))
            case LBlock(stmts=stmts):
                return LBlock(self._rewrite_frame_access(stmts, fv, fc, names))
            case LSwitch(value=value, cases=cases, default=default):
                new_cases = [(tag, self._rewrite_frame_access(body, fv, fc, names))
                             for tag, body in cases]
                new_default = self._rewrite_frame_access(default, fv, fc, names)
                return LSwitch(
                    value=self._rewrite_expr(value, fv, fc, names),
                    cases=new_cases, default=new_default)
            case _:
                return stmt

    def _rewrite_expr(self, expr: LExpr, fv: str, fc: str,
                       names: set[str]) -> LExpr:
        fpt = LPtr(LStruct(fc))
        match expr:
            case LVar(c_name=name, c_type=ct):
                if name in names:
                    return LArrow(LVar(fv, fpt), name, ct)
                return expr
            case LCall(fn_name=fn, args=args, c_type=ct):
                return LCall(fn, [self._rewrite_expr(a, fv, fc, names) for a in args], ct)
            case LIndirectCall(fn_ptr=fp, args=args, c_type=ct):
                return LIndirectCall(
                    self._rewrite_expr(fp, fv, fc, names),
                    [self._rewrite_expr(a, fv, fc, names) for a in args], ct)
            case LBinOp(op=op, left=left, right=right, c_type=ct):
                return LBinOp(op, self._rewrite_expr(left, fv, fc, names),
                              self._rewrite_expr(right, fv, fc, names), ct)
            case LUnary(op=op, operand=operand, c_type=ct):
                return LUnary(op, self._rewrite_expr(operand, fv, fc, names), ct)
            case LFieldAccess(obj=obj, field=field, c_type=ct):
                return LFieldAccess(self._rewrite_expr(obj, fv, fc, names), field, ct)
            case LArrow(ptr=ptr, field=field, c_type=ct):
                return LArrow(self._rewrite_expr(ptr, fv, fc, names), field, ct)
            case LCast(inner=inner, c_type=ct):
                return LCast(self._rewrite_expr(inner, fv, fc, names), ct)
            case LAddrOf(inner=inner, c_type=ct):
                return LAddrOf(self._rewrite_expr(inner, fv, fc, names), ct)
            case LDeref(inner=inner, c_type=ct):
                return LDeref(self._rewrite_expr(inner, fv, fc, names), ct)
            case LTernary(cond=c, then_expr=t, else_expr=e, c_type=ct):
                return LTernary(
                    self._rewrite_expr(c, fv, fc, names),
                    self._rewrite_expr(t, fv, fc, names),
                    self._rewrite_expr(e, fv, fc, names), ct)
            case LCompound(fields=fields, c_type=ct):
                return LCompound(
                    [(n, self._rewrite_expr(v, fv, fc, names)) for n, v in fields], ct)
            case LCheckedArith(op=op, left=left, right=right, c_type=ct):
                return LCheckedArith(
                    op, self._rewrite_expr(left, fv, fc, names),
                    self._rewrite_expr(right, fv, fc, names), ct)
            case _:
                return expr

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fresh_temp(self) -> str:
        """Generate a fresh temporary variable name."""
        name = f"_rf_tmp_{self._tmp_counter}"
        self._tmp_counter += 1
        return name

    def _is_congruent(self, a: Type, b: Type) -> bool:
        """Check structural congruence: same field names and types."""
        a_fields = self._get_struct_fields(a)
        b_fields = self._get_struct_fields(b)
        if a_fields is None or b_fields is None:
            return False
        return a_fields == b_fields

    def _get_struct_fields(self, t: Type) -> dict[str, Type] | None:
        """Get the field name→type mapping for a structural type."""
        if isinstance(t, TNamed):
            for decl in self._module.decls:
                if isinstance(decl, TypeDecl) and decl.name == t.name:
                    fields: dict[str, Type] = {}
                    for f in decl.fields:
                        ft = self._types.get(f.type_ann)
                        if ft is None:
                            ft = self._resolve_type_ann(f.type_ann) if f.type_ann else TAny()
                        fields[f.name] = ft
                    return fields
        if isinstance(t, TRecord):
            return dict(t.fields)
        return None

    def _type_of(self, node: ASTNode) -> Type:
        """Look up the type of an AST node in the TypedModule."""
        t = self._types.get(node)
        if t is not None:
            return t
        # If it's a TypeExpr, resolve it via _resolve_type_ann
        if isinstance(node, TypeExpr):
            return self._resolve_type_ann(node)
        return TAny()

    def _type_of_capture(self, sym: Symbol) -> Type:
        """Get the inferred type of a captured symbol."""
        # Try the type annotation first
        if sym.type_ann is not None:
            t = self._types.get(sym.type_ann)
            if t is not None:
                return t
            return self._resolve_type_ann(sym.type_ann)
        # For let bindings without type annotation, look up the value's type
        if isinstance(sym.decl, LetStmt) and sym.decl.value is not None:
            t = self._types.get(sym.decl.value)
            if t is not None:
                return t
        # For param decls, check the Param node's type_ann
        if isinstance(sym.decl, Param) and sym.decl.type_ann is not None:
            t = self._types.get(sym.decl.type_ann)
            if t is not None:
                return t
            return self._resolve_type_ann(sym.decl.type_ann)
        return TAny()

    def _type_of_return(self, fn: FnDecl) -> Type:
        """Get the return type of a function declaration."""
        if fn.return_type is not None:
            t = self._types.get(fn.return_type)
            if t is not None:
                return t
            return self._resolve_type_ann(fn.return_type)
        return TNone()

    def _type_of_return_method(self, method: FnDecl) -> Type:
        """Get the return type of a method."""
        return self._type_of_return(method)

    def _resolve_type_ann(self, te: TypeExpr) -> Type:
        """Resolve a TypeExpr AST node to a Type.

        TypeExpr nodes are not stored in the typechecker's types dict.
        This method mirrors the typechecker's _resolve_type_expr logic.
        """
        match te:
            case NamedType(name=name, module_path=mp):
                if mp:
                    return TNamed(".".join(mp), name, ())
                builtin = _BUILTIN_TYPE_ANNS.get(name)
                if builtin is not None:
                    return builtin
                return TNamed("", name, ())

            case GenericType(base=base, args=args):
                resolved_args = tuple(self._resolve_type_ann(a) for a in args)
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
                        return TAny()

            case OptionType(inner=inner):
                return TOption(self._resolve_type_ann(inner))

            case FnType(params=params, ret=ret):
                return TFn(
                    tuple(self._resolve_type_ann(p) for p in params),
                    self._resolve_type_ann(ret), False)

            case TupleType(elements=elems):
                return TTuple(tuple(self._resolve_type_ann(e) for e in elems))

            case MutType(inner=inner):
                return self._resolve_type_ann(inner)

            case ImutType(inner=inner):
                return self._resolve_type_ann(inner)

            case _:
                return TAny()

    def _type_name_str(self, t: Type) -> str:
        """Return a human-readable name for a type."""
        match t:
            case TInt(width=32, signed=True):
                return "int"
            case TInt(width=w, signed=s):
                return f"{'int' if s else 'uint'}{w}"
            case TFloat(width=64):
                return "float"
            case TFloat(width=w):
                return f"float{w}"
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
                return f"option_{self._type_name_str(inner)}"
            case TResult(ok_type=ok_t, err_type=err_t):
                return f"result_{self._type_name_str(ok_t)}_{self._type_name_str(err_t)}"
            case TTuple(elements=elems):
                return "_".join(self._type_name_str(e) for e in elems)
            case TArray(element=elem):
                return f"array_{self._type_name_str(elem)}"
            case TStream(element=elem):
                return f"stream_{self._type_name_str(elem)}"
            case TCoroutine(yield_type=yt):
                return f"coroutine_{self._type_name_str(yt)}"
            case TNamed(name=name):
                return name
            case TSum(name=name):
                return name
            case _:
                return "unknown"

    def _is_recursive_sum_field(self, field_type: Type,
                                enclosing_name: str) -> bool:
        """Check if a variant field type refers to its enclosing sum type."""
        match field_type:
            case TSum(name=name) if name == enclosing_name:
                return True
            case TNamed(name=name) if name == enclosing_name:
                return True
            case _:
                return False
