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
    mangle_stream_wrapper, mangle_sort_wrapper, mangle_fanout_wrapper,
    mangle_exception_frame, mangle_monomorphized,
)
from compiler.ast_nodes import (
    # Base
    ASTNode, TypeExpr, Expr, Stmt, Decl, Block, Pattern,
    # Type expressions
    NamedType, GenericType, OptionType, FnType, TupleType, MutType, ImutType, SizedType,
    # Expressions
    IntLit, FloatLit, BoolLit, StringLit, FStringExpr, CharLit, NoneLit,
    Ident, NamedArg, SpreadExpr, BinOp, UnaryOp, Call, MethodCall, FieldAccess, IndexAccess,
    Lambda, TupleExpr, ArrayLit, RecordLit, TypeLit, IfExpr, MatchExpr,
    CompositionChain, ChainElement, FanOut, TernaryExpr, CopyExpr, RefExpr,
    SomeExpr, OkExpr, ErrExpr, CoerceExpr, CastExpr,
    PropagateExpr, NullCoalesce, TypeofExpr, CoroutineStart,
    PipelineStage, CoroutinePipeline,
    # Statements
    LetStmt, AssignStmt, UpdateStmt, ReturnStmt, YieldStmt, ThrowStmt,
    BreakStmt, ContinueStmt, ExprStmt, IfStmt, WhileStmt, ForStmt,
    MatchStmt, TryStmt, MatchArm,
    CatchBlock, FinallyBlock, RetryBlock,
    # Patterns
    WildcardPattern, LiteralPattern, BindPattern, SomePattern, NonePattern,
    OkPattern, ErrPattern, VariantPattern, TuplePattern,
    # Declarations
    FnDecl, TypeDecl, Param, StaticMemberDecl, SumVariantDecl, ConstructorDecl,
    ExternLibDecl, ExternTypeDecl, ExternFnDecl, EnumDecl,
    # Top-level
    Module,
)
from compiler.typechecker import (
    TypedModule, Type,
    TInt, TFloat, TBool, TChar, TByte, TPtr, TString, TNone,
    TOption, TResult, TTuple, TArray, TStream, TCoroutine, TBuffer, TMap, TSet,
    TFn, TRecord, TNamed, TAlias, TSum, TVariant, TTypeVar, TAny, TSelf,
    TEnum,
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


@dataclass
class LOptDerefAs(LExpr):
    """Repack FL_Option_ptr to FL_Option_<ValueType> by dereferencing void*.

    Emits: FL_OPT_DEREF_AS(inner, val_type, opt_type)
    Used when fl_array_get_safe returns FL_Option_ptr but the element is
    a non-pointer type (struct, sum type, etc.).
    """
    inner: LExpr        # The FL_Option_ptr expression
    val_type: LType     # The value type to dereference as
    c_type: LType       # The target FL_Option_<T> type


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
    source_line: int | None = None


@dataclass
class LArrayDecl(LStmt):
    c_name: str
    elem_type: LType
    count: int
    source_line: int | None = None


@dataclass
class LAssign(LStmt):
    target: LExpr
    value: LExpr
    source_line: int | None = None


@dataclass
class LReturn(LStmt):
    value: LExpr | None
    source_line: int | None = None


@dataclass
class LIf(LStmt):
    cond: LExpr
    then: list[LStmt]
    else_: list[LStmt]
    source_line: int | None = None


@dataclass
class LWhile(LStmt):
    cond: LExpr
    body: list[LStmt]
    source_line: int | None = None


@dataclass
class LBlock(LStmt):
    stmts: list[LStmt]
    source_line: int | None = None


@dataclass
class LExprStmt(LStmt):
    expr: LExpr
    source_line: int | None = None


@dataclass
class LGoto(LStmt):
    label: str
    source_line: int | None = None


@dataclass
class LLabel(LStmt):
    name: str
    source_line: int | None = None


@dataclass
class LSwitch(LStmt):
    value: LExpr
    cases: list[tuple[int, list[LStmt]]]
    default: list[LStmt]
    source_line: int | None = None


@dataclass
class LBreak(LStmt):
    source_line: int | None = None


@dataclass
class LContinue(LStmt):
    source_line: int | None = None


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
    source_line: int | None = None


@dataclass
class LStaticDef:
    c_name: str
    c_type: LType
    init: LExpr | None
    is_mut: bool
    is_interned: bool = False  # interned string literal — set refcount high


@dataclass
class LEnumDef:
    c_name: str
    variants: list[tuple[str, int]]  # (mangled_variant_c_name, int_value)


@dataclass
class LModule:
    type_defs: list[LTypeDef]
    fn_defs: list[LFnDef]
    static_defs: list[LStaticDef]
    entry_point: str | None = None  # mangled C name of the entry function
    extern_fn_protos: list[tuple[str, list[LType], LType]] = field(default_factory=list)
    enum_defs: list[LEnumDef] = field(default_factory=list)


# ---------------------------------------------------------------------------
# C type name helpers for option/result/tuple registries
# ---------------------------------------------------------------------------

def _ltype_c_name(lt: LType) -> str:
    """Return a short C-friendly name fragment for an LType, used in registry keys."""
    match lt:
        case LInt(width=w, signed=s):
            prefix = "fl_int" if s else "fl_uint"
            return prefix if w == 32 else f"{prefix}{w}"
        case LFloat(width=w):
            return "fl_float" if w == 64 else f"fl_float{w}"
        case LBool():
            return "fl_bool"
        case LChar():
            return "fl_char"
        case LByte():
            return "fl_byte"
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
# Opaque runtime types — TNamed with empty module resolves to these C types
# ---------------------------------------------------------------------------

_OPAQUE_TYPE_MAP: dict[str, str] = {
    "Socket": "FL_Socket",
    "file": "FL_File",
    "DateTime": "FL_DateTime",
    "Instant": "FL_Instant",
}

# ---------------------------------------------------------------------------
# Option type name mapping — uses pre-defined runtime types where possible
# ---------------------------------------------------------------------------

_BUILTIN_OPTION_MAP: dict[str, str] = {
    "fl_int": "FL_Option_int",
    "fl_int16": "FL_Option_int16",
    "fl_int32": "FL_Option_int32",
    "fl_int64": "FL_Option_int64",
    "fl_uint": "FL_Option_uint",
    "fl_uint16": "FL_Option_uint16",
    "fl_uint32": "FL_Option_uint32",
    "fl_uint64": "FL_Option_uint64",
    "fl_float": "FL_Option_float",
    "fl_float32": "FL_Option_float32",
    "fl_float64": "FL_Option_float64",
    "fl_bool": "FL_Option_bool",
    "fl_byte": "FL_Option_byte",
    "fl_char": "FL_Option_char",
}


# ---------------------------------------------------------------------------
# Value-type box/unbox mapping for generic containers (Gap-2)
#
# When a generic native function (e.g. map.set<V>) is instantiated with a
# value type (int, float, bool, etc.), arguments of that type must be boxed
# to void* before passing, and return values of FL_Option_ptr must be
# repacked into the concrete option struct (e.g. FL_Option_float).
# ---------------------------------------------------------------------------

_VALUE_TYPE_BOX_FN: dict[str, str] = {
    "fl_int": "fl_box_int",
    "fl_int64": "fl_box_int64",
    "fl_float": "fl_box_float",
    "fl_bool": "fl_box_bool",
    "fl_byte": "fl_box_byte",
}

_VALUE_TYPE_UNBOX_FN: dict[str, str] = {
    "fl_int": "fl_unbox_int",
    "fl_int64": "fl_unbox_int64",
    "fl_float": "fl_unbox_float",
    "fl_bool": "fl_unbox_bool",
    "fl_byte": "fl_unbox_byte",
}

_VALUE_TYPE_OPT_UNBOX_FN: dict[str, str] = {
    "fl_int": "fl_opt_unbox_int",
    "fl_int64": "fl_opt_unbox_int64",
    "fl_float": "fl_opt_unbox_float",
    "fl_bool": "fl_opt_unbox_bool",
    "fl_byte": "fl_opt_unbox_byte",
}


def _get_c_fn_name(decl) -> str | None:
    """Extract the C function name from an ExternFnDecl."""
    if isinstance(decl, ExternFnDecl):
        return decl.c_name or decl.name
    return None


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
    "ptr": TPtr(),
    "string": TString(),
    "none": TNone(),
    "void": TNone(),  # alias: some users write ': void' though ': none' is canonical
}


# ---------------------------------------------------------------------------
# Monomorphization support (SG-3-3-1, SG-3-5-1)
#
# Algorithm overview (SG-5-2-2):
#
# Bounded generic functions (`fn f<T fulfills Interface>(...)`) cannot be
# compiled to a single C function because the concrete representation of T
# is unknown until call time. The lowering pass resolves this via compile-time
# specialization (monomorphization):
#
# 1. COLLECTION PHASE — whenever a bounded generic call is encountered in
#    `_lower_call` or `_lower_method_call`, `_record_mono_site` is called with
#    the concrete type environment ({"T": TInt(32,True), ...}) inferred from
#    the actual argument types at that call site.  Each unique
#    (src_module, fn_name, type_args) triple is recorded exactly once in
#    `_mono_sites` and assigned a mangled C name via `mangle_monomorphized`
#    (e.g. `fl_math_min__int`).  The call site emits a direct call to that
#    mangled name.
#
# 2. EMISSION PHASE — after all declarations have been lowered, `lower()`
#    iterates `_mono_sites` and calls `_lower_monomorphized_fn` for each one.
#    That method temporarily swaps the type map, resolver, and module path so
#    that the function body is lowered as if it were in its source module, with
#    every TTypeVar("T") substituted for the concrete type.  The resulting
#    `LFnDef` nodes are prepended to `_fn_defs` so they appear before any
#    callers in the generated C translation unit.
#
# 3. TYPE SUBSTITUTION — `_build_substituted_types` walks the source module's
#    type map (from `all_typed`) and replaces each TTypeVar whose name appears
#    in the type environment with its concrete type.  This is a shallow
#    substitution: only top-level TTypeVar occurrences are replaced (nested
#    generics such as option<T> are handled by the same mechanism recursively
#    in `_substitute_type`).
#
# 4. INTERFACE METHOD DISPATCH — inside a monomorphized body, calls to bounded
#    interface methods (e.g. `a.compare(b)`) are handled by `_lower_method_call`
#    consulting `BUILTIN_METHOD_OPS`.  Each (concrete_type_name, method_name)
#    pair maps to a `BuiltinMethodOp` describing the C operator or macro to
#    emit (e.g. `_fl_compare` for numeric `compare`, `FL_CHECKED_ADD` for
#    `Numeric.add`).  This avoids virtual dispatch for all built-in types.
#
# 5. CROSS-MODULE GENERICS — when a generic function lives in an imported
#    module (e.g. `stdlib/math.flow`), its `FnDecl` is retrieved via the
#    resolver and its body is lowered with the source module's TypedModule
#    (looked up in `all_typed`).  If the source module's TypedModule is absent
#    (e.g. stdlib modules compiled without debug info), `_ltype_to_type_name`
#    provides a fallback for resolving method names from LType alone.
# ---------------------------------------------------------------------------

@dataclass
class MonoSite:
    """A single monomorphization request: one generic function + concrete types."""
    fn_decl: FnDecl
    type_env: dict[str, Type]   # e.g. {"T": TInt(32, True)}
    mangled_name: str            # e.g. "fl_math_min__int"
    src_module: str              # e.g. "math"


@dataclass
class BuiltinMethodOp:
    """Lowering strategy for a built-in interface method on a concrete type."""
    kind: str   # "compare", "binop", "checked_binop", "unary", "call"
    op: str     # C operator, macro name, or C function name


# Dispatch table: (type_name, method_name) → BuiltinMethodOp
# Used when lowering interface method calls on built-in types (SG-3-5-1).
BUILTIN_METHOD_OPS: dict[tuple[str, str], BuiltinMethodOp] = {
    # --- Comparable.compare ---
    # Numeric/char/byte: _fl_compare macro (ternary, no overflow concern)
    ("int",    "compare"):    BuiltinMethodOp("compare", ""),
    ("int64",  "compare"):    BuiltinMethodOp("compare", ""),
    ("float",  "compare"):    BuiltinMethodOp("compare", ""),
    ("char",   "compare"):    BuiltinMethodOp("compare", ""),
    ("byte",   "compare"):    BuiltinMethodOp("compare", ""),
    # String: runtime function
    ("string", "compare"):    BuiltinMethodOp("call", "fl_string_cmp"),

    # --- Numeric.add ---  CHECKED for integers (overflow → panic), plain for float
    ("int",   "add"):         BuiltinMethodOp("checked_binop", "+"),
    ("int64", "add"):         BuiltinMethodOp("checked_binop", "+"),
    ("float", "add"):         BuiltinMethodOp("binop", "+"),

    # --- Numeric.sub ---
    ("int",   "sub"):         BuiltinMethodOp("checked_binop", "-"),
    ("int64", "sub"):         BuiltinMethodOp("checked_binop", "-"),
    ("float", "sub"):         BuiltinMethodOp("binop", "-"),

    # --- Numeric.mul ---
    ("int",   "mul"):         BuiltinMethodOp("checked_binop", "*"),
    ("int64", "mul"):         BuiltinMethodOp("checked_binop", "*"),
    ("float", "mul"):         BuiltinMethodOp("binop", "*"),

    # --- Numeric.negate ---
    ("int",   "negate"):      BuiltinMethodOp("unary", "-"),
    ("int64", "negate"):      BuiltinMethodOp("unary", "-"),
    ("float", "negate"):      BuiltinMethodOp("unary", "-"),

    # --- Equatable.equals ---
    ("int",    "equals"):     BuiltinMethodOp("binop", "=="),
    ("int64",  "equals"):     BuiltinMethodOp("binop", "=="),
    ("float",  "equals"):     BuiltinMethodOp("binop", "=="),
    ("bool",   "equals"):     BuiltinMethodOp("binop", "=="),
    ("char",   "equals"):     BuiltinMethodOp("binop", "=="),
    ("byte",   "equals"):     BuiltinMethodOp("binop", "=="),
    ("string", "equals"):     BuiltinMethodOp("call", "fl_string_eq"),

    # --- Showable.to_string ---
    ("int",    "to_string"):  BuiltinMethodOp("call", "fl_int_to_string"),
    ("int64",  "to_string"):  BuiltinMethodOp("call", "fl_int64_to_string"),
    ("float",  "to_string"):  BuiltinMethodOp("call", "fl_float_to_string"),
    ("bool",   "to_string"):  BuiltinMethodOp("call", "fl_bool_to_string"),
    ("string", "to_string"):  BuiltinMethodOp("call", "_fl_identity_string"),
    ("char",   "to_string"):  BuiltinMethodOp("call", "fl_char_to_string"),
    ("byte",   "to_string"):  BuiltinMethodOp("call", "fl_byte_to_string"),
}


# ---------------------------------------------------------------------------
# Lowerer (RT-7-2-1 through RT-7-5-3)
# ---------------------------------------------------------------------------

class Lowerer:
    """Transform a TypedModule into an LModule."""

    def __init__(self, typed: TypedModule,
                 all_typed: dict[str, TypedModule] | None = None) -> None:
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
        self._enum_defs: list[LEnumDef] = []

        # Type registries — avoid duplicate LTypeDefs
        self._option_registry: dict[str, str] = {}   # key → c_name
        self._result_registry: dict[str, str] = {}
        self._tuple_registry: dict[str, str] = {}
        self._sum_registry: dict[str, str] = {}

        # Temp variable counter
        self._tmp_counter: int = 0

        # Pending statements generated during expression lowering
        self._pending_stmts: list[LStmt] = []
        # Post-statements: emitted AFTER the enclosing statement completes.
        # Used to release temporary string expressions that were hoisted
        # to temps for use as function arguments.
        self._post_stmts: list[LStmt] = []

        # Current function's return type — used by ok/err/none to pick correct struct
        self._current_fn_return_type: Type | None = None

        # Closure support
        self._lambda_counter: int = 0
        self._current_fn_name: str = ""
        self._fn_wrapper_registry: dict[str, str] = {}
        self._capture_remap: dict[str, tuple[str, LType]] = {}

        # Parallel fan-out support
        self._fanout_counter: int = 0

        # Exception frame counter (per-function)
        self._exception_frame_counter: int = 0

        # Monomorphization support (SG-3-3-1, SG-3-4-1)
        # all_typed: all compiled TypedModules by module path — used to access
        # imported modules' type maps when monomorphizing cross-module generics.
        self._all_typed: dict[str, TypedModule] | None = all_typed
        # mono_sites: collected monomorphization requests keyed by
        # (src_module, fn_name, (type_arg_names...))
        self._mono_sites: dict[tuple[str, str, tuple[str, ...]], MonoSite] = {}

        # Per-function map: let-binding name → concrete LType.
        # The typechecker propagates TTypeVar through generic-call return types,
        # so _lower_type(_type_of(ident)) may give LPtr(LVoid) for vars that
        # actually hold a concrete int/float/etc.  We track the concrete type
        # from _lower_let so _lower_ident can use it as a fallback.
        self._let_var_ltypes: dict[str, LType] = {}

        # Stream body context: when set, match/block lowering recurses via
        # _lower_stream_stmts so yields inside match arms get proper state
        # machine resume labels. Set to (frame_var, elem_type, yield_counter)
        # while inside _lower_stream_stmts, None otherwise.
        self._stream_body_ctx: tuple[str, Type, list[int]] | None = None

        # Active monomorphization type env (set during _lower_monomorphized_fn)
        self._mono_type_env: dict[str, Type] | None = None
        # Caller module path saved during cross-module monomorphization
        self._mono_caller_module_path: str | None = None

        # :mut parameter tracking — names of params with :mut annotation
        # that need pass-by-pointer treatment. Cleared per function.
        self._mut_params: set[str] = set()

        # Scope-exit cleanup: track container-typed locals at function level
        # so we can release them before each return statement.
        # Each entry: (var_name, c_type, release_fn_name)
        self._container_locals: list[tuple[str, LType, str, int]] = []
        self._scope_depth: int = 0

        # String literal interning: deduplicate string constants as static
        # globals, initialized once in _fl_init_statics with high refcount
        # so retain/release never frees them.  Eliminates millions of
        # temporary fl_string_from_cstr allocations.
        self._interned_strings: dict[str, str] = {}  # raw C literal → global name
        self._intern_counter: int = 0

        # FFI: extern type names for lowering TNamed to void*
        self._extern_type_names: set[str] = set()
        for decl in self._module.decls:
            if isinstance(decl, ExternTypeDecl):
                self._extern_type_names.add(decl.name)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def lower(self) -> LModule:
        """Run the lowering pass."""
        extern_fn_protos: list[tuple[str, list[LType], LType]] = []
        for decl in self._module.decls:
            match decl:
                case FnDecl():
                    self._lower_fn_decl(decl)
                case TypeDecl():
                    self._lower_type_decl(decl)
                case ExternFnDecl():
                    # Skip proto generation for generic extern fns — their
                    # C signatures use void* and are declared in runtime headers.
                    # Also skip for fl_* names — those are runtime functions
                    # already declared via #include "flow_runtime.h".
                    c_name = decl.c_name or decl.name
                    if not decl.type_params and not c_name.startswith("fl_"):
                        param_ltypes = [self._lower_extern_type(
                            self._resolve_type_ann(p.type_ann))
                            for p in decl.params]
                        ret_ltype = (self._lower_extern_type(
                            self._resolve_type_ann(decl.return_type))
                            if decl.return_type else LVoid())
                        extern_fn_protos.append(
                            (c_name, param_ltypes, ret_ltype))
                case EnumDecl():
                    self._lower_enum_decl(decl)
                case ExternTypeDecl() | ExternLibDecl():
                    pass  # handled elsewhere

        # Lower all collected monomorphization sites (SG-3-4-1).
        # Emit them BEFORE the regular functions so callers can always find
        # the definition above them in the same translation unit.
        mono_fn_defs: list[LFnDef] = []
        for site in self._mono_sites.values():
            fn_def = self._lower_monomorphized_fn(site)
            mono_fn_defs.append(fn_def)
        self._fn_defs = mono_fn_defs + self._fn_defs

        # Detect entry point: a top-level function named "main".
        entry_point: str | None = None
        for fn_def in self._fn_defs:
            if fn_def.source_name.endswith(".main"):
                entry_point = fn_def.c_name
                break

        # Add interned string globals to static_defs
        for c_literal, global_name in self._interned_strings.items():
            self._static_defs.append(LStaticDef(
                c_name=global_name,
                c_type=LPtr(LStruct("FL_String")),
                init=LCall("fl_string_from_cstr",
                           [LLit(c_literal, LPtr(LVoid()))],
                           LPtr(LStruct("FL_String"))),
                is_mut=False,
                is_interned=True,
            ))

        return LModule(
            type_defs=self._type_defs,
            fn_defs=self._fn_defs,
            static_defs=self._static_defs,
            entry_point=entry_point,
            extern_fn_protos=extern_fn_protos,
            enum_defs=self._enum_defs,
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
            case TPtr():
                return LPtr(LVoid())
            case TString():
                return LPtr(LStruct("FL_String"))
            case TNone():
                return LVoid()
            case TArray():
                return LPtr(LStruct("FL_Array"))
            case TStream():
                return LPtr(LStruct("FL_Stream"))
            case TCoroutine():
                return LPtr(LStruct("FL_Coroutine"))
            case TBuffer():
                return LPtr(LStruct("FL_Buffer"))
            case TMap():
                return LPtr(LStruct("FL_Map"))
            case TSet():
                return LPtr(LStruct("FL_Set"))
            case TOption(inner=inner):
                return self._lower_option_type(inner)
            case TResult(ok_type=ok_t, err_type=err_t):
                return self._lower_result_type(ok_t, err_t)
            case TTuple(elements=elems):
                return self._lower_tuple_type(elems)
            case TNamed(module=mod, name=name):
                # Opaque runtime types get their C type directly
                if not mod and name in _OPAQUE_TYPE_MAP:
                    return LPtr(LStruct(_OPAQUE_TYPE_MAP[name]))
                # FFI extern types → opaque void*
                if not mod and name in self._extern_type_names:
                    return LPtr(LVoid())
                # Cross-module type: find the declaring module
                resolved_mod = mod if mod else self._find_sum_type_module(name)
                # Resolve namespace alias (e.g., "ast" -> "self_hosted.ast")
                if resolved_mod and '.' not in resolved_mod:
                    resolved_mod = self._resolve_ns_to_module_path(resolved_mod)
                c_name = mangle(resolved_mod, name,
                                file=self._file, line=0, col=0)
                return LStruct(c_name)
            case TFn():
                # Function types lower to closure struct pointers
                return LPtr(LStruct("FL_Closure"))
            case TSum(name=name):
                mod_path = self._find_sum_type_module(name)
                c_name = mangle(mod_path, name,
                                file=self._file, line=0, col=0)
                return LStruct(c_name)
            case TEnum():
                return LInt(32, True)
            case TRecord(fields=fields):
                # Anonymous records — generate a struct
                return LStruct("fl_record")
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

    def _lower_type_resolving_tvars(self, t: Type) -> LType:
        """Lower a type, resolving TTypeVar to concrete struct if possible.

        This is used specifically for variant field types in match patterns,
        where the typechecker may leave cross-module struct types as TTypeVar
        instead of TNamed.  For genuine generic type params (T, V, etc.),
        _find_sum_type_module returns '' and we fall back to void*.
        """
        if isinstance(t, TTypeVar):
            resolved_mod = self._find_sum_type_module(t.name)
            if resolved_mod:
                c_name = mangle(resolved_mod, t.name,
                                file=self._file, line=0, col=0)
                return LStruct(c_name)
        return self._lower_type(t)

    def _find_sum_type_module(self, name: str) -> str:
        """Find the module path that declares a sum type.

        For locally-defined sum types, returns the module's own path.
        For cross-module sum types (imported from other modules),
        searches _all_typed to find the originating module.
        """
        # Check local module first — use the module's own path, not
        # self._module_path which may differ during monomorphization.
        for decl in self._module.decls:
            if isinstance(decl, TypeDecl) and decl.name == name:
                return ".".join(self._module.path) if self._module.path else self._module_path
        # Search all compiled modules
        if self._all_typed:
            for mod_path, typed_mod in self._all_typed.items():
                for decl in typed_mod.module.decls:
                    if isinstance(decl, TypeDecl) and decl.name == name:
                        return mod_path
        # During cross-module monomorphization, the caller module has the type
        if self._mono_caller_module_path is not None:
            return self._mono_caller_module_path
        return self._module_path

    def _get_struct_field_types(self, type_name: str) -> dict[str, "Type"]:
        """Look up declared field types for a struct from its TypeDecl.

        Returns {field_name: Type} for each field. Used by _lower_type_lit
        to set elem_type on empty array fields whose inferred type is
        TArray(TAny) — the declared field type provides the concrete
        element type needed for container element refcounting.
        """
        bare = type_name.rsplit('.', 1)[-1] if '.' in type_name else type_name
        # Search local module
        for decl in self._module.decls:
            if isinstance(decl, TypeDecl) and decl.name == bare and not decl.is_sum_type:
                return {f.name: self._type_of(f.type_ann)
                        for f in decl.fields if f.type_ann}
        # Search imported modules
        if self._all_typed:
            for _, typed_mod in self._all_typed.items():
                for decl in typed_mod.module.decls:
                    if isinstance(decl, TypeDecl) and decl.name == bare and not decl.is_sum_type:
                        return {f.name: self._type_of(f.type_ann)
                                for f in decl.fields if f.type_ann}
        return {}

    def _resolve_tvar_to_sum(self, name: str) -> TSum | None:
        """Try to resolve a TTypeVar name to a concrete TSum type.

        Searches all compiled modules for a sum TypeDecl with matching name
        and builds the TSum from the AST declaration.
        """
        def _build_tsum_from_decl(decl: TypeDecl) -> TSum:
            """Build a TSum from an AST TypeDecl."""
            variants = []
            for v in decl.variants:
                field_types = []
                if v.fields:
                    for field_name, field_type_expr in v.fields:
                        ft = self._type_of(field_type_expr) if field_type_expr else TAny()
                        field_types.append(ft)
                variants.append(TVariant(v.name, tuple(field_types)))
            return TSum(name, tuple(variants))

        # Search local module
        for decl in self._module.decls:
            if isinstance(decl, TypeDecl) and decl.name == name and decl.is_sum_type:
                return _build_tsum_from_decl(decl)
        # Search all compiled modules
        if self._all_typed:
            for mod_path, typed_mod in self._all_typed.items():
                for decl in typed_mod.module.decls:
                    if isinstance(decl, TypeDecl) and decl.name == name and decl.is_sum_type:
                        # Use the source module's types for field resolution
                        saved_types = self._types
                        self._types = typed_mod.types
                        try:
                            result = _build_tsum_from_decl(decl)
                        finally:
                            self._types = saved_types
                        return result
        return None

    def _lower_option_type(self, inner: Type) -> LType:
        """Lower option<T> to the appropriate option struct type."""
        inner_lt = self._lower_type(inner)
        inner_key = _ltype_c_name(inner_lt)

        # Check for pre-defined runtime option types
        if inner_key in _BUILTIN_OPTION_MAP:
            return LStruct(_BUILTIN_OPTION_MAP[inner_key])

        # Heap types use FL_Option_ptr
        if isinstance(inner_lt, LPtr):
            return LStruct("FL_Option_ptr")

        # Check registry for already-emitted option types
        if inner_key in self._option_registry:
            return LStruct(self._option_registry[inner_key])

        # Generate a new option typedef
        c_name = f"FL_Option_{inner_key}"
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

        c_name = f"FL_Result_{key}"
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

        c_name = f"FL_Tuple_{key}"
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
        if fn.body is None:
            return
        # Bounded generic functions are emitted only via monomorphization (SG-3-4-3).
        # Their unspecialized form contains unresolved TTypeVar and cannot be
        # lowered to valid C. Specializations are collected during lowering of
        # call sites and emitted at the end of lower().
        if self._is_bounded_generic(fn):
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
        saved_let_var_ltypes = self._let_var_ltypes
        self._let_var_ltypes = {}
        saved_mut_params = self._mut_params
        self._mut_params = set()
        saved_container_locals = self._container_locals
        self._container_locals = []
        saved_scope_depth = self._scope_depth
        self._scope_depth = 0

        c_name = mangle(self._module_path, None, fn.name,
                        file=self._file, line=fn.line, col=fn.col)

        params: list[tuple[str, LType]] = []
        for p in fn.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
            if p.is_variadic:
                p_type = TArray(p_type)
            p_lt = self._lower_type(p_type)
            if isinstance(p.type_ann, MutType):
                p_lt = LPtr(p_lt)
                self._mut_params.add(p.name)
            params.append((p.name, p_lt))
            self._let_var_ltypes[p.name] = p_lt

        ret_lt = self._lower_type(ret_type)

        body: list[LStmt] = []
        match fn.body:
            case Block():
                body = self._lower_block(fn.body)
                # Implicit return: if the function has a non-void return type
                # and the last statement doesn't already contain a return,
                # inject returns into the tail position (handles match, if/else).
                if body and not isinstance(ret_lt, LVoid):
                    self._inject_tail_returns(body)
            case Expr():
                expr_result = self._lower_expr(fn.body)
                body = list(self._pending_stmts)
                self._pending_stmts = []
                # Owned-return: retain non-allocating expression body
                if not self._is_allocating_expr(fn.body):
                    retain_fn = self._RETAIN_FN.get(
                        type(self._current_fn_return_type)
                    ) if self._current_fn_return_type else None
                    if retain_fn:
                        body.append(LExprStmt(LCall(
                            retain_fn, [expr_result], c_type=LVoid())))
                body.append(LReturn(expr_result))

        # Scope-exit cleanup: release container locals before returns
        if self._container_locals:
            self._inject_scope_cleanup(body)
            # For void functions without explicit return, append cleanup
            # Only depth-0 locals (inner-scope vars out of C scope here)
            if isinstance(ret_lt, LVoid):
                body.extend([LExprStmt(LCall(fn_name, [LVar(n, ct)], LVoid()))
                             for n, ct, fn_name, depth in self._container_locals
                             if depth == 0])

        self._fn_defs.append(LFnDef(
            c_name=c_name,
            params=params,
            ret=ret_lt,
            body=body,
            is_pure=fn.is_pure,
            source_name=f"{self._module_path}.{fn.name}",
            source_line=fn.line,
        ))
        self._current_fn_return_type = saved_return_type
        self._current_fn_name = saved_fn_name
        self._let_var_ltypes = saved_let_var_ltypes
        self._mut_params = saved_mut_params
        self._container_locals = saved_container_locals
        self._scope_depth = saved_scope_depth

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
            saved_mut_params = self._mut_params
            self._mut_params = set()
            saved_let_var_ltypes = self._let_var_ltypes
            self._let_var_ltypes = {}
            saved_container_locals = self._container_locals
            self._container_locals = []
            saved_scope_depth = self._scope_depth
            self._scope_depth = 0
            params: list[tuple[str, LType]] = []
            for p in method.params:
                if p.name == "self":
                    params.append(("self", LPtr(LStruct(c_name))))
                else:
                    p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
                    p_lt = self._lower_type(p_type)
                    if isinstance(p.type_ann, MutType):
                        p_lt = LPtr(p_lt)
                        self._mut_params.add(p.name)
                    params.append((p.name, p_lt))
                    self._let_var_ltypes[p.name] = p_lt

            ret_type = self._type_of_return_method(method)
            ret_lt = self._lower_type(ret_type)

            saved_return_type = self._current_fn_return_type
            self._current_fn_return_type = ret_type

            body: list[LStmt] = []
            match method.body:
                case Block():
                    body = self._lower_block(method.body)
                    if body and not isinstance(ret_lt, LVoid):
                        self._inject_tail_returns(body)
                case Expr():
                    expr_result = self._lower_expr(method.body)
                    body = list(self._pending_stmts)
                    self._pending_stmts = []
                    # Owned-return: retain non-allocating expression body
                    if not self._is_allocating_expr(method.body):
                        retain_fn = self._RETAIN_FN.get(
                            type(self._current_fn_return_type)
                        ) if self._current_fn_return_type else None
                        if retain_fn:
                            body.append(LExprStmt(LCall(
                                retain_fn, [expr_result], c_type=LVoid())))
                    body.append(LReturn(expr_result))

            # Scope-exit cleanup: release container locals before returns
            if self._container_locals:
                self._inject_scope_cleanup(body)
                if isinstance(ret_lt, LVoid):
                    body.extend([LExprStmt(LCall(fn_name, [LVar(n, ct)], LVoid()))
                                 for n, ct, fn_name, depth in self._container_locals
                                 if depth == 0])

            self._fn_defs.append(LFnDef(
                c_name=m_c_name,
                params=params,
                ret=ret_lt,
                body=body,
                is_pure=method.is_pure,
                source_name=f"{self._module_path}.{td.name}.{method.name}",
                source_line=method.line,
            ))
            self._current_fn_return_type = saved_return_type
            self._mut_params = saved_mut_params
            self._let_var_ltypes = saved_let_var_ltypes
            self._container_locals = saved_container_locals
            self._scope_depth = saved_scope_depth

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
                source_line=ctor.line,
            ))

        # Lower static members
        for s in td.static_members:
            self._lower_static_member(s, td.name)

    def _lower_enum_decl(self, decl: EnumDecl) -> None:
        """Lower an enum declaration to a C enum typedef."""
        c_name = mangle(self._module_path, decl.name,
                        file=self._file, line=decl.line, col=decl.col)
        variants: list[tuple[str, int]] = []
        next_val = 0
        for v in decl.variants:
            val = v.value if v.value is not None else next_val
            v_c_name = mangle(self._module_path, decl.name, v.name,
                              file=self._file, line=v.line, col=v.col)
            variants.append((v_c_name, val))
            next_val = val + 1
        self._enum_defs.append(LEnumDef(c_name=c_name, variants=variants))

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
                    if self._is_recursive_sum_field(f_type, td.name, ftype_expr):
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
        """Lower a block of statements.

        When inside a stream body context (_stream_body_ctx is set),
        delegates to _lower_stream_stmts so yields inside match arms
        and other nested constructs get proper state machine handling.
        """
        if self._stream_body_ctx is not None:
            frame_var, elem_type, yield_counter = self._stream_body_ctx
            return self._lower_stream_stmts(
                block.stmts, frame_var, elem_type, yield_counter)
        result: list[LStmt] = []
        for stmt in block.stmts:
            saved = self._pending_stmts
            saved_post = self._post_stmts
            self._pending_stmts = []
            self._post_stmts = []
            lowered = self._lower_stmt(stmt)
            result.extend(self._pending_stmts)
            # Handle post_stmts around terminal control flow.
            # - return: insert releases BEFORE the return (the return
            #   value is a fresh allocation, not the hoisted temp).
            #   Skip temps referenced in the return expression.
            # - throw: never returns, cleanup is unreachable — drop.
            if self._post_stmts and lowered:
                last = lowered[-1]
                is_throw = (isinstance(last, LExprStmt)
                            and isinstance(last.expr, LCall)
                            and last.expr.fn_name == "_fl_throw")
                if isinstance(last, LReturn):
                    # Insert releases before the return, but skip any
                    # temps referenced in the return expression
                    returned_names = self._collect_referenced_vars(last.value)
                    safe_posts = []
                    for ps in self._post_stmts:
                        if (isinstance(ps, LExprStmt)
                                and isinstance(ps.expr, LCall)
                                and ps.expr.args
                                and isinstance(ps.expr.args[0], LVar)
                                and ps.expr.args[0].c_name in returned_names):
                            continue  # skip — temp is the returned value
                        safe_posts.append(ps)
                    result.extend(lowered[:-1])  # all stmts before return
                    result.extend(safe_posts)
                    result.append(last)  # the return
                elif is_throw:
                    result.extend(lowered)
                    # Drop post_stmts — throw never returns
                else:
                    result.extend(lowered)
                    result.extend(self._post_stmts)
            else:
                result.extend(lowered)
                result.extend(self._post_stmts)
            self._pending_stmts = saved
            self._post_stmts = saved_post
        return result

    def _inject_tail_returns(self, stmts: list[LStmt]) -> None:
        """Inject LReturn into the tail position of a statement list.

        Handles match-as-expression in tail position: if the last statement
        is an LExprStmt, convert it to LReturn. If it's an LIf or LSwitch,
        recurse into the arms/cases to inject returns into their tails.
        Already-present LReturn statements are left alone.
        """
        if not stmts:
            return
        last = stmts[-1]
        if isinstance(last, LReturn):
            return  # already has a return
        if isinstance(last, LExprStmt):
            # Don't wrap _Noreturn calls (like _fl_throw) in LReturn —
            # they never return and `return _fl_throw(...)` is invalid C.
            if (isinstance(last.expr, LCall)
                    and last.expr.fn_name == "_fl_throw"):
                return
            expr = last.expr
            # Owned-return: retain non-allocating tail expressions
            if not self._is_allocating_lir_expr(expr):
                ret_type = self._current_fn_return_type
                if ret_type is not None:
                    retain_fn = self._RETAIN_FN.get(type(ret_type))
                    if retain_fn:
                        stmts[-1] = LExprStmt(LCall(
                            retain_fn, [expr], c_type=LVoid()))
                        stmts.append(LReturn(expr))
                        return
            stmts[-1] = LReturn(expr)
        elif isinstance(last, LIf):
            self._inject_tail_returns(last.then)
            self._inject_tail_returns(last.else_)
        elif isinstance(last, LSwitch):
            for _, case_stmts in last.cases:
                self._inject_tail_returns(case_stmts)
            self._inject_tail_returns(last.default)
        elif isinstance(last, LBlock):
            self._inject_tail_returns(last.stmts)

    @staticmethod
    def _collect_referenced_vars(expr: LExpr | None) -> set[str]:
        """Collect all LVar names referenced in an expression tree."""
        refs: set[str] = set()
        if expr is None:
            return refs
        stack: list[LExpr] = [expr]
        while stack:
            e = stack.pop()
            if isinstance(e, LVar):
                refs.add(e.c_name)
            # Walk into sub-expressions
            for attr in ('left', 'right', 'cond', 'then_expr', 'else_expr',
                         'value', 'inner', 'operand', 'expr', 'base'):
                child = getattr(e, attr, None)
                if isinstance(child, LExpr):
                    stack.append(child)
            # Walk into lists (e.g. LCall args, LArrayData elements)
            for attr in ('args', 'elements'):
                child_list = getattr(e, attr, None)
                if isinstance(child_list, list):
                    for item in child_list:
                        if isinstance(item, LExpr):
                            stack.append(item)
            # LCompound fields: list of (name, expr) tuples
            if hasattr(e, 'fields') and isinstance(getattr(e, 'fields'), list):
                for item in e.fields:
                    if isinstance(item, tuple) and len(item) == 2:
                        _, field_val = item
                        if isinstance(field_val, LExpr):
                            stack.append(field_val)
        return refs

    def _inject_scope_cleanup(self, stmts: list[LStmt],
                              declared: set[str] | None = None) -> None:
        """Insert release calls for container locals before each LReturn.

        Walks the statement tree recursively. Before each LReturn, inserts
        release calls for container locals that have already been declared,
        skipping variables referenced in the return expression (to avoid
        use-after-free on returned compound literals).
        """
        if declared is None:
            declared = set()
        container_names = {name for name, _, _, _ in self._container_locals}
        i = 0
        while i < len(stmts):
            s = stmts[i]
            # Track declarations of container locals
            if isinstance(s, LVarDecl) and s.c_name in container_names:
                declared.add(s.c_name)
            elif isinstance(s, LReturn):
                # Collect ALL variable names referenced in the return expr
                returned_names = self._collect_referenced_vars(s.value)
                # Build release calls for declared locals, skip referenced vars
                cleanup: list[LStmt] = []
                for name, ct, fn_name, _depth in self._container_locals:
                    if name not in declared or name in returned_names:
                        continue
                    cleanup.append(LExprStmt(
                        LCall(fn_name, [LVar(name, ct)], LVoid())))
                # Insert cleanup before the return
                for j, c_stmt in enumerate(cleanup):
                    stmts.insert(i + j, c_stmt)
                i += len(cleanup) + 1
                continue
            # Recurse into compound statements, passing a copy of declared
            # so both branches see what's been declared before the branch
            if isinstance(s, LIf):
                self._inject_scope_cleanup(s.then, set(declared))
                self._inject_scope_cleanup(s.else_, set(declared))
            elif isinstance(s, LSwitch):
                for _, case_stmts in s.cases:
                    self._inject_scope_cleanup(case_stmts, set(declared))
                self._inject_scope_cleanup(s.default, set(declared))
            elif isinstance(s, LBlock):
                self._inject_scope_cleanup(s.stmts, set(declared))
            # Do NOT recurse into LWhile — returns inside loops are rare
            # and the loop may re-enter, so cleanup before loop-internal
            # returns would be incorrect.
            i += 1

    @staticmethod
    def _tag_source(stmts: list[LStmt], line: int | None) -> list[LStmt]:
        """Set source_line on each LStmt that doesn't already have one."""
        if line is None:
            return stmts
        for s in stmts:
            if getattr(s, 'source_line', None) is None:
                s.source_line = line
        return stmts

    def _lower_stmt(self, stmt: Stmt) -> list[LStmt]:
        match stmt:
            case LetStmt():
                result = self._lower_let(stmt)
            case AssignStmt():
                result = self._lower_assign(stmt)
            case UpdateStmt():
                result = self._lower_update(stmt)
            case ReturnStmt():
                result = self._lower_return(stmt)
            case IfStmt():
                result = self._lower_if_stmt(stmt)
            case WhileStmt():
                result = self._lower_while(stmt)
            case ForStmt():
                result = self._lower_for(stmt)
            case MatchStmt():
                result = self._lower_match_stmt(stmt)
            case ExprStmt():
                result = self._lower_expr_stmt(stmt)
            case BreakStmt():
                result = [LBreak()]
            case ContinueStmt():
                result = [LContinue()]
            case YieldStmt():
                # Yield outside stream fn — should not happen after type check,
                # but handle gracefully
                result = self._lower_yield(stmt)
            case TryStmt():
                result = self._lower_try(stmt)
            case ThrowStmt():
                result = self._lower_throw(stmt)
            case _:
                raise EmitError(
                    message=f"unsupported statement type: {type(stmt).__name__}",
                    file=self._file, line=stmt.line, col=stmt.col,
                )
        return self._tag_source(result, getattr(stmt, 'line', None))

    def _lower_let(self, stmt: LetStmt) -> list[LStmt]:
        val_type = self._type_of(stmt.value)
        c_type = self._lower_type(val_type)
        init = self._lower_expr(stmt.value)
        # If the static type resolved to void* (TTypeVar/TAny — e.g. from a
        # monomorphized call), use the concrete LType from the lowered expression.
        if isinstance(c_type, LPtr) and isinstance(c_type.inner, LVoid):
            expr_ct = getattr(init, 'c_type', None)
            if expr_ct is not None and not (
                    isinstance(expr_ct, LPtr) and isinstance(expr_ct.inner, LVoid)):
                c_type = expr_ct
        # If there's a type annotation, prefer it for the declared type
        auto_lifted = False
        if stmt.type_ann is not None:
            ann_type = self._type_of(stmt.type_ann)
            c_type = self._lower_type(ann_type)
            # Auto-lift T → option<T>
            if isinstance(ann_type, TOption) and not isinstance(val_type, TOption):
                auto_lifted = True
                init = LCompound(
                    fields=[("tag", LLit("1", LByte())),
                            ("value", init)],
                    c_type=c_type,
                )
        # Track concrete LType so _lower_ident can use it when the type map
        # contains TTypeVar/TAny (typechecker doesn't substitute generic call
        # return types, so let-bound vars may appear typed as TTypeVar).
        self._let_var_ltypes[stmt.name] = c_type
        stmts: list[LStmt] = [LVarDecl(c_name=stmt.name, c_type=c_type, init=init)]

        # Phase 4 (element refcounting): empty array literals `[]` get type
        # TArray(TAny()) from the typechecker (no elements to infer from).
        # When the let binding has an annotation like array<string>, we know
        # the concrete element type and must call fl_array_set_elem_type so
        # subsequent push calls retain/release elements correctly.
        if (isinstance(stmt.value, ArrayLit)
                and not stmt.value.elements
                and stmt.type_ann is not None):
            ann_type = self._type_of(stmt.type_ann)
            if isinstance(ann_type, TArray):
                elem_tag = self._ELEM_TYPE_TAG.get(type(ann_type.element))
                if elem_tag is not None:
                    stmts.append(LExprStmt(LCall(
                        "fl_array_set_elem_type",
                        [LVar(stmt.name, c_type),
                         LLit(str(elem_tag), LInt(64, True))],
                        LVoid())))

        # Retain-on-store: retain ALL let bindings from non-allocating sources.
        # Skip when option auto-lifting changed the type: val_type is T but
        # the variable is option<T>, so calling fl_T_retain(option_var) would
        # be a type mismatch.
        if not auto_lifted and not self._is_allocating_expr(stmt.value):
            retain_fn = self._RETAIN_FN.get(type(val_type))
            if retain_fn is not None:
                stmts.append(LExprStmt(LCall(
                    retain_fn,
                    [LVar(stmt.name, c_type)],
                    c_type=LVoid(),
                )))

        # Register refcounted locals for scope-exit cleanup.
        # Only top-level function scope (depth 0) — inner block vars
        # are not tracked to avoid releasing already-dead variables.
        # Skip auto-lifted bindings: the variable is option<T>, not T.
        #
        # All refcounted locals are registered for scope-exit cleanup:
        # - Non-allocating: retained at bind (+1), scope-exit release (-1).
        # - Allocating (including :mut): owned-return convention gives
        #   refcount=1. If embedded in a struct, struct-construction
        #   retain (_retain_struct_fields) bumps to 2. Scope-exit
        #   release brings to 1 — struct ref survives.
        # Both depth-0 and inner-scope locals are registered.
        # _inject_scope_cleanup handles block scoping via the `declared`
        # set. Void-function trailing cleanup only uses depth-0 locals
        # (inner-scope vars are out of C scope at function end).
        if not auto_lifted:
            release_fn = self._get_release_fn(val_type)
            if release_fn:
                # Avoid duplicates when same name appears at different depths
                # (e.g. `raw` in both hex and decimal paths of scan_number).
                # Keep the shallowest depth entry for void-function cleanup.
                dup_idx = None
                for idx, (n, _, _, d) in enumerate(self._container_locals):
                    if n == stmt.name:
                        dup_idx = idx
                        break
                if dup_idx is not None:
                    if self._scope_depth < self._container_locals[dup_idx][3]:
                        self._container_locals[dup_idx] = (
                            stmt.name, c_type, release_fn, self._scope_depth)
                else:
                    self._container_locals.append(
                        (stmt.name, c_type, release_fn, self._scope_depth))

        return stmts

    # Type → release/retain function mappings.
    # All refcounted heap types: string, array, map, stream, buffer, closure.
    # Retain-on-store ensures every "owner" (let binding, struct field,
    # option/result wrapper) bumps the refcount, so release-on-reassignment
    # and scope-exit cleanup are safe.
    _RELEASE_FN: dict[type, str] = {
        TString: "fl_string_release",
        TArray:  "fl_array_release",
        TMap:    "fl_map_release",
        TStream: "fl_stream_release",
        TBuffer: "fl_buffer_release",
        TFn:     "fl_closure_release",
    }

    _RETAIN_FN: dict[type, str] = {
        TString: "fl_string_retain",
        TArray:  "fl_array_retain",
        TMap:    "fl_map_retain",
        TStream: "fl_stream_retain",
        TBuffer: "fl_buffer_retain",
        TFn:     "fl_closure_retain",
    }

    # Maps Flow element/value types to FL_ElemType integer constants.
    # These mirror the FL_ElemType enum in flow_runtime.h.
    # Used by _lower_array_lit and map.new() interception to call
    # fl_array_set_elem_type / fl_map_set_val_type so the runtime
    # can retain/release elements automatically on push/copy/free.
    _ELEM_TYPE_TAG: dict[type, int] = {
        TString: 1,  # FL_ELEM_STRING
        TArray:  2,  # FL_ELEM_ARRAY
        TMap:    3,  # FL_ELEM_MAP
        TFn:     4,  # FL_ELEM_CLOSURE
        TStream: 5,  # FL_ELEM_STREAM
        TBuffer: 6,  # FL_ELEM_BUFFER
    }

    def _get_release_fn(self, t: Type) -> str | None:
        """Return the release function name for a container type, or None."""
        return self._RELEASE_FN.get(type(t))

    def _retain_struct_fields(self, fields: list[tuple[str, LExpr]],
                              ast_args: list[Expr]) -> None:
        """Retain borrowed refcounted field values in struct/variant construction.

        For each field whose AST expression is non-allocating and whose type
        is refcounted, emit a retain call via _pending_stmts.  This ensures
        the struct owns its own references, enabling safe scope-exit cleanup
        of the local variables that were embedded.
        """
        for (fname, lowered_val), ast_val in zip(fields, ast_args):
            if not self._is_allocating_expr(ast_val):
                val_type = self._type_of(ast_val)
                retain_fn = self._RETAIN_FN.get(type(val_type))
                if retain_fn:
                    self._pending_stmts.append(
                        LExprStmt(LCall(retain_fn, [lowered_val], LVoid())))

    def _intern_string(self, c_literal: str) -> LVar:
        """Return an LVar referencing an interned static string global.

        All identical C string literals share the same global FL_String*
        variable, initialized once in _fl_init_statics with a high refcount
        so it is never freed by retain/release.
        """
        if c_literal in self._interned_strings:
            name = self._interned_strings[c_literal]
        else:
            mod_prefix = self._module_path.replace(".", "_")
            name = f"_fl_str_{mod_prefix}_{self._intern_counter}"
            self._intern_counter += 1
            self._interned_strings[c_literal] = name
        return LVar(name, LPtr(LStruct("FL_String")))

    _STRING_LTYPE = LPtr(LStruct("FL_String"))

    # Functions that never return owned strings — do not hoist.
    _NON_OWNED_STRING_FNS = frozenset({
        "fl_string_retain",
        "fl_string_release",
    })

    def _hoist_string_temp(self, expr: LExpr) -> LExpr:
        """If expr is a string-returning call, hoist to temp and schedule release.

        With the owned-return convention, all function calls return owned
        values. String-returning calls (both runtime and user-defined) are
        safe to hoist and release as intermediates in concat chains.

        Returns the temp LVar if hoisted, or the original expr if not eligible.
        """
        if not isinstance(expr, LCall):
            return expr
        if expr.fn_name in self._NON_OWNED_STRING_FNS:
            return expr
        # Only hoist string-returning calls
        if expr.c_type != self._STRING_LTYPE:
            return expr
        tmp = self._fresh_temp()
        self._pending_stmts.append(
            LVarDecl(c_name=tmp, c_type=self._STRING_LTYPE, init=expr))
        self._post_stmts.append(
            LExprStmt(LCall("fl_string_release",
                            [LVar(tmp, self._STRING_LTYPE)], LVoid())))
        return LVar(tmp, self._STRING_LTYPE)

    def _hoist_string_args(self, fn_name: str, args: list[LExpr]) -> list[LExpr]:
        """Hoist string-returning call arguments for non-storing functions.

        Only hoists (and schedules release) for functions known NOT to store
        their arguments.  Functions like array.push, map.set, etc. store the
        pointer so releasing the temp would cause use-after-free.
        """
        # Functions that store string arguments — never hoist for these
        if fn_name in ("fl_array_push_ptr", "fl_array_push_sized",
                        "fl_map_set_str", "fl_map_set",
                        "fl_array_put__string", "_fl_throw",
                        "fl_string_retain", "fl_string_release"):
            return args
        return [self._hoist_string_temp(a) for a in args]

    @staticmethod
    def _is_allocating_expr(expr: Expr) -> bool:
        """Check if an expression is guaranteed to produce a fresh allocation.

        StringLit is NOT allocating — interned as a static global with a
        pinned refcount, so retain/release is a no-op on it.
        """
        return isinstance(expr, (Call, MethodCall, BinOp, SomeExpr, OkExpr,
                                 ErrExpr, ArrayLit, RecordLit, FStringExpr,
                                 CopyExpr, IfExpr, MatchExpr))

    @staticmethod
    def _is_allocating_lir_expr(expr: LExpr) -> bool:
        """Check if an LIR expression produces a freshly-allocated value."""
        return isinstance(expr, (LCall, LIndirectCall, LCompound))

    def _call_passes_var_by_mut_ref(self, call_expr: Expr, var_name: str) -> bool:
        """Check if a Call passes `var_name` as a :mut (by-reference) argument.

        When a variable is passed by &reference, the callee handles
        release-on-reassignment internally through the pointer.  The caller
        must NOT also emit release-on-reassignment to avoid double-free.
        """
        if not isinstance(call_expr, Call):
            return False
        # Find the FnDecl to check param annotations
        sym = self._resolved.symbols.get(call_expr.callee)
        if sym is None or not isinstance(sym.decl, FnDecl):
            return False
        fn_decl: FnDecl = sym.decl
        for i, param in enumerate(fn_decl.params):
            if i >= len(call_expr.args):
                break
            if isinstance(param.type_ann, MutType):
                arg = call_expr.args[i]
                if isinstance(arg, Ident) and arg.name == var_name:
                    return True
        return False

    def _lower_assign(self, stmt: AssignStmt) -> list[LStmt]:
        target = self._lower_expr(stmt.target)
        value = self._lower_expr(stmt.value)

        # Release-on-reassignment for container-typed :mut variables.
        # Only for allocating RHS (call, literal) so the old value is
        # guaranteed to be from a previous allocation, not a borrow.
        # Guard: old != new handles functions like map.remove that return self.
        # Skip when the target variable is passed by &ref to the same call —
        # the callee already handles release through the pointer.
        if (isinstance(stmt.target, Ident)
                and self._is_allocating_expr(stmt.value)
                and not self._call_passes_var_by_mut_ref(stmt.value, stmt.target.name)):
            target_type = self._type_of(stmt.target)
            release_fn = self._get_release_fn(target_type)
            if release_fn is not None:
                old_tmp = f"_fl_old_{self._tmp_counter}"
                self._tmp_counter += 1
                old_c_type = target.c_type
                old_var = LVar(old_tmp, old_c_type)
                result = [
                    LVarDecl(c_name=old_tmp, c_type=old_c_type, init=target),
                    LAssign(target=target, value=value),
                    LIf(
                        cond=LBinOp("!=", old_var, target,
                                    c_type=LBool()),
                        then=[LExprStmt(LCall(release_fn, [old_var],
                                              c_type=LVoid()))],
                        else_=[],
                    ),
                ]
                # Set elem_type on empty array reassignment so pushed
                # elements are retained by the runtime.
                if isinstance(stmt.value, ArrayLit) and not stmt.value.elements:
                    if isinstance(target_type, TArray):
                        tag = self._ELEM_TYPE_TAG.get(type(target_type.element))
                        if tag is not None:
                            result.append(LExprStmt(LCall(
                                "fl_array_set_elem_type",
                                [target, LLit(str(tag), LInt(64, True))],
                                LVoid())))
                return result

        # Non-allocating RHS (borrowed value): retain new, release old.
        # This handles `x = param` where x is :mut and param is borrowed.
        # Skip when the target variable is passed by &ref to the same call —
        # the callee already handles release through the pointer.
        if (isinstance(stmt.target, Ident)
                and not self._call_passes_var_by_mut_ref(stmt.value, stmt.target.name)):
            target_type = self._type_of(stmt.target)
            retain_fn = self._RETAIN_FN.get(type(target_type))
            release_fn = self._get_release_fn(target_type)
            if retain_fn and release_fn:
                old_tmp = f"_fl_old_{self._tmp_counter}"
                self._tmp_counter += 1
                old_c_type = target.c_type
                old_var = LVar(old_tmp, old_c_type)
                return [
                    LVarDecl(c_name=old_tmp, c_type=old_c_type, init=target),
                    LAssign(target=target, value=value),
                    LIf(
                        cond=LBinOp("!=", old_var, target,
                                    c_type=LBool()),
                        then=[
                            LExprStmt(LCall(retain_fn, [target],
                                            c_type=LVoid())),
                            LExprStmt(LCall(release_fn, [old_var],
                                            c_type=LVoid())),
                        ],
                        else_=[],
                    ),
                ]

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
        # Owned-return convention: retain non-allocating return values of
        # refcounted types so every function return transfers ownership.
        if not self._is_allocating_expr(stmt.value):
            ret_type = self._type_of(stmt.value)
            retain_fn = self._RETAIN_FN.get(type(ret_type))
            if retain_fn is not None:
                # Skip simple variable returns that are tracked for scope-exit
                # cleanup — already owned by the binding, and
                # _inject_scope_cleanup skips releasing them (returned_names).
                tracked_names = {n for n, _, _, _ in self._container_locals}
                is_tracked_local = (isinstance(stmt.value, Ident)
                                    and stmt.value.name in tracked_names)
                if not is_tracked_local:
                    stmts = list(self._pending_stmts)
                    self._pending_stmts = []
                    stmts.append(LExprStmt(LCall(
                        retain_fn, [value], c_type=LVoid())))
                    stmts.append(LReturn(value))
                    return stmts
        stmts = list(self._pending_stmts)
        self._pending_stmts = []
        stmts.append(LReturn(value))
        return stmts

    def _lower_inner_block(self, block: Block) -> list[LStmt]:
        """Lower an inner block with scope depth tracking."""
        self._scope_depth += 1
        result = self._lower_block(block)
        self._scope_depth -= 1
        return result

    def _lower_if_stmt(self, stmt: IfStmt) -> list[LStmt]:
        cond = self._lower_expr(stmt.condition)
        then_body = self._lower_inner_block(stmt.then_branch)
        else_body: list[LStmt] = []
        if stmt.else_branch is not None:
            if isinstance(stmt.else_branch, Block):
                else_body = self._lower_inner_block(stmt.else_branch)
            elif isinstance(stmt.else_branch, IfStmt):
                else_body = self._lower_if_stmt(stmt.else_branch)
        return [LIf(cond=cond, then=then_body, else_=else_body)]

    def _lower_while(self, stmt: WhileStmt) -> list[LStmt]:
        cond = self._lower_expr(stmt.condition)
        self._scope_depth += 1
        body = self._lower_block(stmt.body)
        self._scope_depth -= 1
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

        # Release allocating iterables after the loop finishes
        iter_type = self._type_of(stmt.iterable)
        release_fn = self._get_release_fn(iter_type)
        cleanup_needed = release_fn and self._is_allocating_expr(stmt.iterable)

        if cleanup_needed:
            arr_tmp = self._fresh_temp()
            arr_lt = self._lower_type(iter_type)
            arr_var = LVar(arr_tmp, arr_lt)
        else:
            arr_var = arr_expr

        # int64_t _fl_idx = 0;
        idx_decl = LVarDecl(
            c_name=idx_name,
            c_type=LInt(64, True),
            init=LLit("0", LInt(64, True)),
        )

        # _fl_idx < fl_array_len(arr)
        cond = LBinOp(
            op="<",
            left=LVar(idx_name, LInt(64, True)),
            right=LCall("fl_array_len", [arr_var], LInt(64, True)),
            c_type=LBool(),
        )

        # ElementType item = *(ElementType*)fl_array_get_ptr(arr, _fl_idx);
        get_ptr = LCall("fl_array_get_ptr",
                         [arr_var, LVar(idx_name, LInt(64, True))],
                         LPtr(LVoid()))
        cast_ptr = LCast(get_ptr, LPtr(elem_lt))
        deref = LDeref(cast_ptr, elem_lt)
        item_decl = LVarDecl(c_name=stmt.var, c_type=elem_lt, init=deref)

        # _fl_idx = _fl_idx + 1;
        increment = LAssign(
            target=LVar(idx_name, LInt(64, True)),
            value=LBinOp(
                op="+",
                left=LVar(idx_name, LInt(64, True)),
                right=LLit("1", LInt(64, True)),
                c_type=LInt(64, True),
            ),
        )

        self._scope_depth += 1
        inner_body = self._lower_block(stmt.body)
        self._scope_depth -= 1
        body_stmts = [item_decl] + inner_body + [increment]
        result: list[LStmt] = []

        if cleanup_needed:
            arr_lt = self._lower_type(iter_type)
            result.append(LVarDecl(c_name=arr_tmp, c_type=arr_lt, init=arr_expr))

        result.extend([idx_decl, LWhile(cond=cond, body=body_stmts)])

        if stmt.finally_block is not None:
            result.extend(self._lower_block(stmt.finally_block))

        if cleanup_needed:
            result.append(LExprStmt(LCall(release_fn, [arr_var], LVoid())))

        return result

    def _lower_for_stream(self, stmt: ForStmt, elem_t: Type) -> list[LStmt]:
        """Lower for-over-stream to while loop with fl_stream_next. RT-7-4-3."""
        stream_expr = self._lower_expr(stmt.iterable)
        stream_lt = LPtr(LStruct("FL_Stream"))
        elem_lt = self._lower_type(elem_t)
        next_name = self._fresh_temp()

        # Release allocating stream iterables after the loop finishes
        cleanup_needed = self._is_allocating_expr(stmt.iterable)

        # Store stream in a temp to avoid re-evaluating the iterable each iteration
        stream_tmp = self._fresh_temp()
        stream_decl = LVarDecl(c_name=stream_tmp, c_type=stream_lt, init=stream_expr)
        stream_var = LVar(stream_tmp, stream_lt)

        # while (1) { ... }
        cond = LLit("1", LBool())

        # FL_Option_ptr _fl_next = fl_stream_next(stream);
        next_decl = LVarDecl(
            c_name=next_name,
            c_type=LStruct("FL_Option_ptr"),
            init=LCall("fl_stream_next", [stream_var], LStruct("FL_Option_ptr")),
        )

        # if (_fl_next.tag == 0) break;
        tag_check = LIf(
            cond=LBinOp(
                op="==",
                left=LFieldAccess(
                    LVar(next_name, LStruct("FL_Option_ptr")),
                    "tag", LByte()),
                right=LLit("0", LByte()),
                c_type=LBool(),
            ),
            then=[LBreak()],
            else_=[],
        )

        # T item = (T)(uintptr_t)_fl_next.value;  (for value types)
        # T item = (T)_fl_next.value;              (for pointer types)
        value_access = LFieldAccess(
            LVar(next_name, LStruct("FL_Option_ptr")),
            "value", LPtr(LVoid()))
        item_init: LExpr
        if isinstance(elem_lt, LPtr):
            item_init = LCast(value_access, elem_lt)
        else:
            # Value types need intermediate cast through uintptr_t (uint64)
            item_init = LCast(LCast(value_access, LInt(64, False)), elem_lt)
        item_decl = LVarDecl(c_name=stmt.var, c_type=elem_lt, init=item_init)

        self._scope_depth += 1
        inner_body = self._lower_block(stmt.body)
        self._scope_depth -= 1
        body_stmts = [next_decl, tag_check, item_decl] + inner_body
        result: list[LStmt] = [stream_decl, LWhile(cond=cond, body=body_stmts)]

        if stmt.finally_block is not None:
            result.extend(self._lower_block(stmt.finally_block))

        if cleanup_needed:
            result.append(LExprStmt(LCall("fl_stream_release", [stream_var], LVoid())))

        return result

    def _lower_match_stmt(self, stmt: MatchStmt) -> list[LStmt]:
        """Lower match statement. RT-7-3-5, RT-7-3-6."""
        subj_type = self._type_of(stmt.subject)
        # Resolve TTypeVar to concrete sum type for match lowering.
        # The typechecker may leave cross-module struct field types as
        # TTypeVar when the field type is a sum type defined in another
        # module (e.g., arm.pattern where Pattern is from self_hosted.ast).
        resolved_sum = None
        if isinstance(subj_type, TTypeVar):
            resolved_sum = self._resolve_tvar_to_sum(subj_type.name)
            if resolved_sum is not None:
                subj_type = resolved_sum
        # Resolve TSum with empty variants (recursive cycle sentinel).
        # The typechecker uses TSum(name, ()) to break recursive cycles
        # in sum type definitions. Resolve to the full TSum from the
        # module declarations so match arms can find their variant tags.
        if isinstance(subj_type, TSum) and len(subj_type.variants) == 0:
            resolved_sum = self._resolve_tvar_to_sum(subj_type.name)
            if resolved_sum is not None:
                subj_type = resolved_sum
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
        # Release discarded return values from allocating calls
        expr_type = self._type_of(stmt.expr) if stmt.expr in self._types else None
        release_fn = self._get_release_fn(expr_type) if expr_type else None
        if release_fn and self._is_allocating_expr(stmt.expr):
            tmp = self._fresh_temp()
            c_type = self._lower_type(expr_type)
            return [
                LVarDecl(c_name=tmp, c_type=c_type, init=expr),
                LExprStmt(LCall(release_fn, [LVar(tmp, c_type)], LVoid())),
            ]
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
            FL_ExceptionFrame _fl_ef_N;
            fl_bool _fl_ef_N_caught = fl_true;  // assume success
            _fl_exception_push(&_fl_ef_N);
            if (setjmp(_fl_ef_N.jmp) == 0) {
                // try body
                _fl_exception_pop();
            } else {
                _fl_exception_pop();
                _fl_ef_N_caught = fl_false;  // exception occurred
                // catch dispatch (sets _caught back to fl_true if handled)
            }
            // finally body
            if (!_fl_ef_N_caught) {
                _fl_throw(_fl_ef_N.exception, _fl_ef_N.exception_tag);
            }
        """
        result: list[LStmt] = []
        frame_idx = self._exception_frame_counter
        self._exception_frame_counter += 1
        frame_name = mangle_exception_frame(frame_idx)
        frame_type = LStruct("FL_ExceptionFrame")
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
                init=LLit("fl_true", LBool()),
            ))

        # Push frame
        result.append(LExprStmt(LCall(
            "_fl_exception_push",
            [LAddrOf(LVar(frame_name, frame_type), LPtr(frame_type))],
            LVoid(),
        )))

        # Build the try body (the "then" branch of setjmp == 0)
        try_stmts: list[LStmt] = []
        try_stmts.extend(self._lower_inner_block(stmt.body))
        try_stmts.append(LExprStmt(LCall(
            "_fl_exception_pop", [], LVoid(),
        )))

        # Build the catch/retry branch (the "else" branch of setjmp != 0)
        catch_stmts: list[LStmt] = []
        catch_stmts.append(LExprStmt(LCall(
            "_fl_exception_pop", [], LVoid(),
        )))

        if has_finally:
            # Mark exception as not-yet-handled
            catch_stmts.append(LAssign(
                target=LVar(caught_var, LBool()),
                value=LLit("fl_false", LBool()),
            ))

        # Build catch/retry dispatch chain
        catch_stmts.extend(self._build_catch_dispatch(
            stmt, frame_name, frame_type, has_finally, caught_var))

        # setjmp condition: setjmp(_fl_ef_N.jmp) == 0
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
                    "_fl_throw",
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
        fl_true instead of rethrowing, so finally can run before rethrow.
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
                    value=LLit("fl_true", LBool()),
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
                    value=LLit("fl_true", LBool()),
                ))
            dispatch_entries.append((tag, catch_stmts))

        if not dispatch_entries:
            if has_finally:
                # No catch/retry blocks — don't rethrow yet, let finally run
                # The _caught flag is already fl_false, so post-finally rethrow will fire
                return []
            else:
                # No catch or retry blocks, no finally — rethrow unconditionally
                return [LExprStmt(LCall(
                    "_fl_throw",
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
                "_fl_throw",
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
        For string exceptions (tag 0): bind as FL_String*.
        For typed exceptions: cast from void* to ExcType*.
        """
        stmts: list[LStmt] = []

        exc_type = self._resolve_type_ann(catch.exception_type)
        c_type = self._lower_type(exc_type)

        if isinstance(exc_type, TString):
            # String exception: cast void* to FL_String*
            stmts.append(LVarDecl(
                c_name=catch.exception_var,
                c_type=LPtr(LStruct("FL_String")),
                init=LCast(
                    LFieldAccess(LVar(frame_name, frame_type), "exception",
                                 LPtr(LVoid())),
                    LPtr(LStruct("FL_String")),
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
        self._scope_depth += 1
        stmts.extend(self._lower_block(catch.body))
        self._scope_depth -= 1
        return stmts

    def _build_retry_handler(self, retry: RetryBlock,
                             frame_name: str,
                             frame_type: LType,
                             try_stmt: TryStmt) -> list[LStmt]:
        """Build the statements for a retry block.

        Retry re-invokes the named function. The exception variable's `data`
        field is mutable, allowing the retry body to correct it before re-invocation.

        Generated pattern:
            int _fl_attempts_N = 0;
            ExcType* ex_ptr = (ExcType*)_fl_ef_N.exception;
            ExcType ex = *ex_ptr;
            while (_fl_attempts_N < max_attempts) {
                _fl_attempts_N++;
                // retry body (can modify ex.data fields)
                // re-push frame, re-try the named function call
                *ex_ptr = ex;  // write back modifications
                _fl_exception_push(&_fl_ef_N);
                if (setjmp(_fl_ef_N.jmp) == 0) {
                    // call target_fn again with corrected data
                    _fl_exception_pop();
                    goto _fl_retry_success_N;
                } else {
                    _fl_exception_pop();
                    ex_ptr = (ExcType*)_fl_ef_N.exception;
                    ex = *ex_ptr;
                }
            }
            // retries exhausted — fall through to catch or rethrow
            _fl_retry_success_N: ;

        For bootstrap simplification: the retry re-executes the entire try body
        rather than just the named function, since isolating a single function
        from a composition chain requires deep chain analysis that isn't yet
        implemented. This matches the semantic intent for non-chain code.
        """
        stmts: list[LStmt] = []
        exc_type = self._resolve_type_ann(retry.exception_type)
        c_type = self._lower_type(exc_type)

        # Lower the attempts expression (or use INT_MAX for unlimited)
        if retry.attempts is not None:
            max_attempts_expr = self._lower_expr(retry.attempts)
        else:
            max_attempts_expr = LLit("2147483647", LInt(32, True))

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
                c_type=LPtr(LStruct("FL_String")),
                init=LCast(
                    LFieldAccess(LVar(frame_name, LStruct("FL_ExceptionFrame")),
                                 "exception", LPtr(LVoid())),
                    LPtr(LStruct("FL_String")),
                ),
            ))
        else:
            # Typed exception: get pointer, dereference for local copy
            exc_ptr = self._fresh_temp()
            stmts.append(LVarDecl(
                c_name=exc_ptr,
                c_type=LPtr(c_type),
                init=LCast(
                    LFieldAccess(LVar(frame_name, LStruct("FL_ExceptionFrame")),
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
        self._scope_depth += 1
        loop_body.extend(self._lower_block(retry.body))
        self._scope_depth -= 1

        # Write back modifications if typed exception
        if not isinstance(exc_type, TString):
            loop_body.append(LAssign(
                target=LDeref(LVar(exc_ptr, LPtr(c_type)), c_type),
                value=LVar(retry.exception_var, c_type),
            ))

        # Re-push exception frame for retry
        frame_type_s = LStruct("FL_ExceptionFrame")
        loop_body.append(LExprStmt(LCall(
            "_fl_exception_push",
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
        inner_try.append(LExprStmt(LCall("_fl_exception_pop", [], LVoid())))
        inner_try.append(LGoto(success_label))

        # Inner catch: pop, re-bind exception, continue loop
        inner_catch: list[LStmt] = []
        inner_catch.append(LExprStmt(LCall("_fl_exception_pop", [], LVoid())))
        if isinstance(exc_type, TString):
            inner_catch.append(LAssign(
                target=LVar(retry.exception_var, LPtr(LStruct("FL_String"))),
                value=LCast(
                    LFieldAccess(LVar(frame_name, frame_type_s),
                                 "exception", LPtr(LVoid())),
                    LPtr(LStruct("FL_String")),
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
            max_attempts_expr,
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
                "_fl_throw",
                [LFieldAccess(LVar(frame_name, LStruct("FL_ExceptionFrame")),
                              "exception", LPtr(LVoid())),
                 LFieldAccess(LVar(frame_name, LStruct("FL_ExceptionFrame")),
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

        For string exceptions: _fl_throw(fl_string_from_cstr("msg"), 0)
          where tag 0 means untyped/string exception.
        For typed exceptions: heap-allocate the exception struct and pass pointer.
        """
        exc_expr = self._lower_expr(stmt.exception)
        exc_type = self._type_of(stmt.exception)

        if isinstance(exc_type, TString):
            # String exceptions use tag 0
            return [LExprStmt(LCall(
                "_fl_throw",
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
            "_fl_throw",
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
            case NamedArg(value=value):
                return self._lower_expr(value)

            case SpreadExpr(expr=inner):
                return self._lower_expr(inner)

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
                return LLit("fl_true" if v else "fl_false", LBool())

            case StringLit(value=v):
                escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t").replace("\0", "\\0")
                c_literal = f'"{escaped}"'
                return self._intern_string(c_literal)

            case CharLit(value=v):
                return LLit(str(v), LChar())

            case NoneLit():
                # Lower to FL_NONE compound literal with concrete option type
                t = self._type_of(expr)
                # none in ptr context → NULL
                if isinstance(t, TPtr):
                    return LLit("NULL", LPtr(LVoid()))
                # Prefer function return type for concrete option type
                if isinstance(t, TOption) and isinstance(t.inner, TAny):
                    if isinstance(self._current_fn_return_type, TOption):
                        t = self._current_fn_return_type
                lt = self._lower_type(t) if isinstance(t, TOption) else LStruct("FL_Option_ptr")
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
                # Fallback: if the semantic type resolved to void* (TTypeVar or TAny
                # from bounded-generic call return), use the concrete LType tracked
                # during let-binding or parameter lowering.
                if isinstance(lt, LPtr) and isinstance(lt.inner, LVoid):
                    concrete_lt = self._let_var_ltypes.get(name)
                    if concrete_lt is not None:
                        lt = concrete_lt
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
                # :mut param — pass-by-pointer. For value types (non-struct),
                # auto-deref so `x` becomes `(*x)`. For struct types, return
                # LVar with LPtr(LStruct) c_type so field access uses LArrow.
                if name in self._mut_params:
                    p_lt = self._let_var_ltypes.get(name)
                    if isinstance(p_lt, LPtr) and not isinstance(p_lt.inner, LStruct):
                        return LDeref(LVar(name, p_lt), p_lt.inner)
                    if isinstance(p_lt, LPtr):
                        return LVar(name, p_lt)
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
                    # Enum variant access: use the enum's own type for mangling
                    if isinstance(t, TEnum):
                        mod_path = t.module if t.module else self._module_path
                        c_name = mangle(mod_path, t.name, field_name,
                                        file=self._file, line=expr.line, col=expr.col)
                        return LVar(c_name, lt)
                    recv_type = self._type_of(receiver)
                    type_name = recv_type.name if isinstance(recv_type, TNamed) else None
                    if type_name is None and isinstance(receiver, Ident):
                        type_name = receiver.name
                    c_name = mangle(self._module_path, type_name, field_name,
                                    file=self._file, line=expr.line, col=expr.col)
                    return LVar(c_name, lt)
                # Cross-module fieldless variant constructor: mod.Variant
                if sym is not None and sym.kind == SymbolKind.CONSTRUCTOR:
                    if (isinstance(sym.decl, SumVariantDecl)
                            and sym.decl.fields is None):
                        sum_t = t
                        if not isinstance(sum_t, TSum):
                            sum_t = self._type_of(expr)
                        if isinstance(sum_t, TSum):
                            tag = next((i for i, v in enumerate(sum_t.variants)
                                        if v.name == field_name), 0)
                            return LCompound(
                                fields=[("tag", LLit(str(tag), LByte()))],
                                c_type=lt,
                            )
                        # Fallback: typechecker returned TAny — look up TSum from decl
                        found_t, found_lt = self._find_variant_sum_type(
                            field_name, sym.decl, t, lt)
                        if isinstance(found_t, TSum):
                            tag = next((i for i, v in enumerate(found_t.variants)
                                        if v.name == field_name), 0)
                            return LCompound(
                                fields=[("tag", LLit(str(tag), LByte()))],
                                c_type=found_lt,
                            )
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
                    # Array index returns option — use fl_array_get_safe
                    return LCall("fl_array_get_safe",
                                 [recv, idx], lt)
                if isinstance(recv_type, TMap):
                    return LCall("fl_map_get", [recv, idx], lt)
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
                    lowered_val = self._lower_expr(val)
                    # Retain-on-store: retain borrowed refcounted field values
                    if not self._is_allocating_expr(val):
                        val_type = self._type_of(val)
                        retain_fn = self._RETAIN_FN.get(type(val_type))
                        if retain_fn:
                            self._pending_stmts.append(
                                LExprStmt(LCall(retain_fn, [lowered_val], LVoid())))
                    lfields.append((name, lowered_val))
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
                # Standalone fan-out: evaluate each branch, collect into tuple.
                # Parallel flag ignored here — standalone fan-out does not
                # distribute a shared input, so parallelism has no benefit.
                # Parallel fan-out is meaningful in chain context only.
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

            # Immutable ref
            case RefExpr(inner=inner):
                return self._lower_ref(expr)

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
                return self._intern_string(f'"{type_name}"')

            # Coroutine start — wrap stream in FL_Coroutine (always threaded)
            case CoroutineStart(call=call):
                coro_type = self._type_of(expr)
                is_receivable = (isinstance(coro_type, TCoroutine)
                                 and not isinstance(coro_type.send_type, TAny))
                if is_receivable:
                    return self._lower_receivable_coroutine_start(call, expr)
                # Non-receivable: still threaded — spawn on a real thread
                # with a channel, just without an input channel for .send().
                coro_ptr = LPtr(LStruct("FL_Coroutine"))
                stream_ptr = LPtr(LStruct("FL_Stream"))
                stream_expr = self._lower_expr(call)
                stream_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=stream_tmp, c_type=stream_ptr,
                    init=stream_expr))
                # Get capacity from callee function's return type annotation
                callee_fn = self._get_callee_fn_decl(call)
                ret_ann = callee_fn.return_type if callee_fn else None
                capacity = self._get_capacity_expr(ret_ann)
                return LCall("fl_coroutine_new_threaded",
                             [LVar(stream_tmp, stream_ptr),
                              capacity],
                             coro_ptr)

            # Coroutine pipeline: a() -> b() * 5 -> c()
            case CoroutinePipeline(stages=stages):
                return self._lower_coroutine_pipeline(stages, expr)

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
        right_type = self._type_of(right)

        # String concatenation (including Showable auto-coercion)
        if op == "+" and isinstance(t, TString):
            l_str = left_expr if isinstance(left_type, TString) else self._to_string_expr(left_expr, left_type)
            r_str = right_expr if isinstance(right_type, TString) else self._to_string_expr(right_expr, right_type)
            args = self._hoist_string_args("fl_string_concat", [l_str, r_str])
            return LCall("fl_string_concat", args,
                         LPtr(LStruct("FL_String")))

        # String equality
        if op == "==" and isinstance(left_type, TString):
            return LCall("fl_string_eq", [left_expr, right_expr], LBool())
        if op == "!=" and isinstance(left_type, TString):
            return LUnary("!", LCall("fl_string_eq", [left_expr, right_expr], LBool()),
                          LBool())

        # Congruence operator — compile-time structural type comparison
        if op == "===":
            right_type = self._type_of(right)
            if self._is_congruent(left_type, right_type):
                return LLit("fl_true", LBool())
            else:
                return LLit("fl_false", LBool())

        # Integer checked arithmetic (RT-7-3-2)
        if isinstance(left_type, TInt) and isinstance(right_type, TInt) and op in ("+", "-", "*", "/", "%", "</"):
            # Implicit widening: cast narrower operand to wider type
            l = left_expr
            r = right_expr
            if left_type.width != right_type.width:
                if left_type.width < right_type.width:
                    l = LCast(left_expr, self._lower_type(right_type))
                else:
                    r = LCast(right_expr, self._lower_type(left_type))
            return LCheckedArith(op=op, left=l, right=r, c_type=lt)

        # Float modulo — needs fmod(), use checked arith for div-by-zero guard
        if isinstance(left_type, TFloat) and isinstance(right_type, TFloat) and op == "%":
            return LCheckedArith(op=op, left=left_expr, right=right_expr, c_type=lt)

        # Logical operators
        if op == "&&":
            return LBinOp(op="&&", left=left_expr, right=right_expr, c_type=LBool())
        if op == "||":
            return LBinOp(op="||", left=left_expr, right=right_expr, c_type=LBool())

        return LBinOp(op=op, left=left_expr, right=right_expr, c_type=lt)

    def _reorder_args_for_decl(self, args: list[Expr],
                               decl: Decl) -> list[Expr]:
        """Reorder named args to match param order for any FnDecl."""
        if not any(isinstance(a, NamedArg) for a in args):
            return args
        if not isinstance(decl, FnDecl):
            return args
        positional: list[Expr] = []
        named: dict[str, Expr] = {}
        for a in args:
            if isinstance(a, NamedArg):
                named[a.name] = a.value
            else:
                positional.append(a)
        result = list(positional)
        n_pos = len(positional)
        for i in range(n_pos, len(decl.params)):
            pname = decl.params[i].name
            if pname in named:
                result.append(named[pname])
        return result

    def _reorder_call_named_args(self, expr: Call) -> list[Expr]:
        """Reorder named args in a Call to match param order."""
        args = expr.args
        if not any(isinstance(a, NamedArg) for a in args):
            return args
        if not isinstance(expr.callee, Ident):
            return args
        sym = self._resolved.symbols.get(expr.callee)
        if sym is None:
            return args
        decl = sym.decl
        if not isinstance(decl, FnDecl):
            return args
        # Split positional and named
        positional: list[Expr] = []
        named: dict[str, Expr] = {}
        for a in args:
            if isinstance(a, NamedArg):
                named[a.name] = a.value
            else:
                positional.append(a)
        # Build reordered list
        result = list(positional)
        n_pos = len(positional)
        for i in range(n_pos, len(decl.params)):
            pname = decl.params[i].name
            if pname in named:
                result.append(named[pname])
        return result

    def _fill_default_args(self, expr: Call,
                           lowered_args: list[LExpr]) -> list[LExpr]:
        """If fewer args than params, append lowered default expressions."""
        if not isinstance(expr.callee, Ident):
            return lowered_args
        sym = self._resolved.symbols.get(expr.callee)
        if sym is None or sym.kind not in (
                SymbolKind.FN, SymbolKind.IMPORT, SymbolKind.CONSTRUCTOR):
            return lowered_args
        decl = sym.decl
        if not isinstance(decl, FnDecl):
            return lowered_args
        n_args = len(lowered_args)
        n_params = len(decl.params)
        if n_args >= n_params:
            return lowered_args
        # Append lowered defaults for trailing missing params
        result = list(lowered_args)
        for i in range(n_args, n_params):
            param = decl.params[i]
            if param.default is not None:
                result.append(self._lower_expr(param.default))
            else:
                # Typechecker should have caught this; defensive fallback
                break
        return result

    def _pack_variadic_call_args(self, expr: Call, call_args: list[Expr],
                                  lowered_args: list[LExpr]) -> list[LExpr]:
        """If calling a variadic function, pack trailing args into an array."""
        fn_decl = self._get_variadic_fn_decl(expr)
        if fn_decl is None:
            return lowered_args

        n_fixed = len(fn_decl.params) - 1
        variadic_param = fn_decl.params[-1]
        elem_type = self._type_of(variadic_param.type_ann) if variadic_param.type_ann else TAny()
        elem_lt = self._lower_type(elem_type)
        arr_lt = self._lower_type(TArray(elem_type))

        fixed_args = lowered_args[:n_fixed]
        variadic_lowered = lowered_args[n_fixed:]
        variadic_raw_args = call_args[n_fixed:]

        # Single spread arg — pass it directly (it's already an FL_Array*)
        if (len(variadic_raw_args) == 1
                and isinstance(variadic_raw_args[0], SpreadExpr)):
            return fixed_args + [variadic_lowered[0]]

        # No variadic args — empty array
        if not variadic_lowered:
            empty_arr = LCall("fl_array_new",
                              [LLit("0", LInt(64, True)),
                               LLit("0", LInt(64, True)),
                               LLit("NULL", LPtr(LVoid()))],
                              arr_lt)
            return fixed_args + [empty_arr]

        # Multiple literal args — pack into compound literal array
        count = len(variadic_lowered)
        data_expr = LArrayData(
            elements=variadic_lowered,
            elem_type=elem_lt,
            c_type=LPtr(elem_lt),
        )
        packed_arr = LCall("fl_array_new",
                           [LLit(str(count), LInt(64, True)),
                            LSizeOf(elem_lt),
                            data_expr],
                           arr_lt)
        return fixed_args + [packed_arr]

    def _pack_variadic_method_args(self, fn_decl: FnDecl,
                                     call_args: list[Expr],
                                     lowered_args: list[LExpr],
                                     type_env: dict | None = None) -> list[LExpr]:
        """Pack trailing variadic args into an array for method calls."""
        n_fixed = len(fn_decl.params) - 1
        variadic_param = fn_decl.params[-1]
        elem_type = self._type_of(variadic_param.type_ann) if variadic_param.type_ann else TAny()
        if type_env:
            elem_type = self._deep_substitute(elem_type, type_env)
        elem_lt = self._lower_type(elem_type)
        arr_lt = self._lower_type(TArray(elem_type))

        fixed_args = lowered_args[:n_fixed]
        variadic_lowered = lowered_args[n_fixed:]
        variadic_raw_args = call_args[n_fixed:]

        # Single spread arg — pass it directly (it's already an FL_Array*)
        if (len(variadic_raw_args) == 1
                and isinstance(variadic_raw_args[0], SpreadExpr)):
            return fixed_args + [variadic_lowered[0]]

        # No variadic args — empty array
        if not variadic_lowered:
            empty_arr = LCall("fl_array_new",
                              [LLit("0", LInt(64, True)),
                               LLit("0", LInt(64, True)),
                               LLit("NULL", LPtr(LVoid()))],
                              arr_lt)
            return fixed_args + [empty_arr]

        # Multiple literal args — pack into compound literal array
        count = len(variadic_lowered)
        data_expr = LArrayData(
            elements=variadic_lowered,
            elem_type=elem_lt,
            c_type=LPtr(elem_lt),
        )
        packed_arr = LCall("fl_array_new",
                           [LLit(str(count), LInt(64, True)),
                            LSizeOf(elem_lt),
                            data_expr],
                           arr_lt)
        return fixed_args + [packed_arr]

    def _wrap_mut_args(self, fn_decl: FnDecl | ExternFnDecl,
                       lowered_args: list[LExpr]) -> list[LExpr]:
        """Adjust arguments for :mut parameter passing.

        - :mut param + value arg → wrap in LAddrOf (&arg)
        - :mut param + correct-pointer arg → pass directly (forwarding)
        - :mut param + under-pointed arg → wrap in LAddrOf to reach correct level
        - non-:mut param + pointer arg from :mut local → unwrap with LDeref (*arg)
        """
        if not isinstance(fn_decl, FnDecl):
            return lowered_args
        result = list(lowered_args)
        for i, param in enumerate(fn_decl.params):
            if i >= len(result):
                break
            arg = result[i]
            arg_ct = getattr(arg, 'c_type', None)
            if isinstance(param.type_ann, MutType):
                # :mut param — compute the expected C pointer type for this param.
                # For a :mut map<K,V> param, the inner type is FL_Map* and the
                # expected C type is FL_Map** (LPtr(LPtr(LStruct("FL_Map")))).
                # A plain "is it already an LPtr?" check is not enough because
                # a :mut map param auto-derefs in _lower_expr to FL_Map* (LPtr),
                # which would be incorrectly passed directly when FL_Map** is needed.
                p_type = self._type_of(param.type_ann.inner) if param.type_ann.inner else TNone()
                p_lt = self._lower_type(p_type)
                expected_ct = LPtr(p_lt)
                if arg_ct == expected_ct:
                    # Already the correct pointer type — forward directly.
                    continue
                if isinstance(arg_ct, LPtr):
                    # Pointer, but wrong level (e.g. FL_Map* when FL_Map** needed).
                    # Take the address to reach the expected pointer level.
                    result[i] = LAddrOf(arg, expected_ct)
                elif arg_ct is not None:
                    result[i] = LAddrOf(arg, expected_ct)
                else:
                    result[i] = LAddrOf(arg, LPtr(LVoid()))
            else:
                # Non-:mut param — if arg is a pointer from a :mut local,
                # dereference it so the callee gets a value copy.
                # This handles both LPtr(LStruct) (struct :mut params) and
                # LPtr(LPtr(...)) (map/array :mut params that weren't auto-deref'd).
                if (isinstance(arg_ct, LPtr)
                        and isinstance(arg_ct.inner, (LStruct, LPtr))
                        and isinstance(arg, LVar) and arg.c_name in self._mut_params):
                    result[i] = LDeref(arg, arg_ct.inner)
        return result

    def _get_variadic_fn_decl(self, expr: Call) -> FnDecl | None:
        """Return the FnDecl if the callee is a variadic function, else None."""
        if not isinstance(expr.callee, Ident):
            return None
        sym = self._resolved.symbols.get(expr.callee)
        if sym is None:
            return None
        decl = sym.decl
        if isinstance(decl, FnDecl) and decl.params and decl.params[-1].is_variadic:
            return decl
        return None

    def _lower_call(self, expr: Call) -> LExpr:
        """Lower function call."""
        t = self._type_of(expr)
        lt = self._lower_type(t)

        # Special case: fl_sort_array_by wraps the comparator closure so that
        # it bridges qsort's element-pointer convention with Flow's typed closures.
        # Must be intercepted before lowering all args to avoid double-lowering.
        if isinstance(expr.callee, Ident) and len(expr.args) >= 2:
            sym = self._resolved.symbols.get(expr.callee)
            if sym is not None and sym.kind in (SymbolKind.FN, SymbolKind.IMPORT):
                decl = sym.decl
                if _get_c_fn_name(decl) == "fl_sort_array_by":
                    arr_arg = self._lower_expr(expr.args[0])
                    arr_type = self._type_of(expr.args[0])
                    elem_type = (arr_type.element if isinstance(arr_type, TArray)
                                 else TAny())
                    wrapped_cmp = self._lower_sort_closure_wrapper(
                        expr.args[1], elem_type)
                    return LCall("fl_sort_array_by", [arr_arg, wrapped_cmp], lt)

        # Reorder named args to param order before lowering
        call_args = self._reorder_call_named_args(expr)
        lowered_args = [self._lower_expr(a) for a in call_args]

        # Fill in default argument values for missing trailing params
        lowered_args = self._fill_default_args(expr, lowered_args)

        # Pack variadic args into an array if calling a variadic function
        lowered_args = self._pack_variadic_call_args(expr, call_args, lowered_args)

        if isinstance(expr.callee, Ident):
            # Direct function call
            name = expr.callee.name
            sym = self._resolved.symbols.get(expr.callee)
            # FFI extern fn — use literal C name, no mangling
            if sym is not None and isinstance(sym.decl, ExternFnDecl):
                extern_decl: ExternFnDecl = sym.decl
                c_name = extern_decl.c_name or extern_decl.name
                if extern_decl.type_params:
                    # Generic extern fn — apply same dispatch chain as native generics
                    redirected = self._maybe_redirect_array_push(
                        extern_decl, lowered_args, lt)
                    if redirected is not None:
                        return redirected
                    repacked = self._maybe_repack_array_get(
                        extern_decl, lowered_args, list(call_args), t, lt)
                    if repacked is not None:
                        return repacked
                    wrapped = self._lower_native_generic_call(
                        extern_decl, list(call_args), lowered_args, t, lt)
                    if wrapped is not None:
                        return wrapped
                    return LCall(c_name, lowered_args, lt)
                # Non-generic extern fn — rewrite function-typed args
                final_args = self._rewrite_extern_fn_args(
                    extern_decl, call_args, lowered_args)
                return LCall(c_name, final_args, lt)
            # Sum type variant constructor — inline as compound literal
            if (sym is not None and sym.kind == SymbolKind.CONSTRUCTOR
                    and isinstance(sym.decl, SumVariantDecl)):
                return self._lower_variant_ctor(name, sym.decl, t, lt, lowered_args,
                                                list(expr.args))
            # Struct constructor — inline as compound literal
            if (sym is not None and sym.kind == SymbolKind.CONSTRUCTOR
                    and isinstance(sym.decl, ConstructorDecl)):
                ctor_decl: ConstructorDecl = sym.decl
                fields = [(p.name, arg)
                          for p, arg in zip(ctor_decl.params, lowered_args)]
                self._retain_struct_fields(fields, list(expr.args))
                return LCompound(fields=fields, c_type=lt)
            # Positional struct construction via type name: MyStruct(a, b, c)
            if (sym is not None and sym.kind == SymbolKind.TYPE
                    and isinstance(sym.decl, TypeDecl)
                    and not sym.decl.is_sum_type):
                type_decl: TypeDecl = sym.decl
                fields = [(f.name, arg)
                          for f, arg in zip(type_decl.fields, lowered_args)]
                # Compute concrete struct type from the TypeDecl (typechecker
                # may return TAny for constructor-like calls, so lt may be wrong)
                struct_mod = getattr(sym, 'module_path', None) or self._module_path
                struct_lt = LStruct(mangle(struct_mod, type_decl.name,
                                          file=self._file, line=expr.line, col=expr.col))
                self._retain_struct_fields(fields, list(expr.args))
                return LCompound(fields=fields, c_type=struct_lt)
            if sym is not None and sym.kind in (SymbolKind.FN, SymbolKind.CONSTRUCTOR):
                # Check if this is a bounded generic — monomorphize it (SG-3-4-2)
                fn_decl_maybe = sym.decl if isinstance(sym.decl, FnDecl) else None
                if fn_decl_maybe and fn_decl_maybe.type_params:
                    env = self._infer_type_env_from_call(
                        fn_decl_maybe, list(expr.args), lowered_args)
                    if env:
                        mono_name = self._record_mono_site(
                            self._module_path, fn_decl_maybe, env)
                        # Substitute type env into return type for concrete LType
                        concrete_lt = self._lower_type(self._deep_substitute(t, env))
                        final = self._wrap_mut_args(fn_decl_maybe, lowered_args)
                        return LCall(mono_name, final, concrete_lt)
                # Wrap :mut args before emitting the call
                if fn_decl_maybe is not None:
                    lowered_args = self._wrap_mut_args(fn_decl_maybe, lowered_args)
                c_name = mangle(self._module_path, None, name,
                                file=self._file, line=expr.line, col=expr.col)
                return LCall(c_name, lowered_args, lt)
            # Named import of an extern fn from another module
            if (sym is not None and sym.kind == SymbolKind.IMPORT
                    and isinstance(sym.decl, ExternFnDecl)):
                ext_decl: ExternFnDecl = sym.decl
                ext_c_name = ext_decl.c_name or ext_decl.name
                if ext_decl.type_params:
                    redirected = self._maybe_redirect_array_push(
                        ext_decl, lowered_args, lt)
                    if redirected is not None:
                        return redirected
                    repacked = self._maybe_repack_array_get(
                        ext_decl, lowered_args, list(expr.args), t, lt)
                    if repacked is not None:
                        return repacked
                    wrapped = self._lower_native_generic_call(
                        ext_decl, list(expr.args), lowered_args, t, lt)
                    if wrapped is not None:
                        return wrapped
                return LCall(ext_c_name, self._hoist_string_args(ext_c_name, lowered_args), lt)
            # Check if callee is a closure-typed variable (local var, param)
            callee_type = self._type_of(expr.callee)
            if isinstance(callee_type, TFn):
                callee_expr = self._lower_expr(expr.callee)
                return self._make_closure_call(callee_expr, callee_type, lowered_args, lt)
            # Builtin or unresolved — use name directly
            return LCall(name, self._hoist_string_args(name, lowered_args), lt)

        # FieldAccess callee — check if resolved to constructor/type symbol
        if isinstance(expr.callee, FieldAccess):
            fa_sym = self._resolved.symbols.get(expr.callee)
            if fa_sym is not None:
                fa_name = expr.callee.field
                # Sum type variant constructor via namespace: mod.Variant(...)
                if (fa_sym.kind == SymbolKind.CONSTRUCTOR
                        and isinstance(fa_sym.decl, SumVariantDecl)):
                    return self._lower_variant_ctor(
                        fa_name, fa_sym.decl, t, lt, lowered_args,
                        list(expr.args))
                # Struct constructor via namespace: mod.MyStruct(...)
                if (fa_sym.kind == SymbolKind.CONSTRUCTOR
                        and isinstance(fa_sym.decl, ConstructorDecl)):
                    ctor_decl: ConstructorDecl = fa_sym.decl
                    fields = [(p.name, arg)
                              for p, arg in zip(ctor_decl.params, lowered_args)]
                    self._retain_struct_fields(fields, list(expr.args))
                    return LCompound(fields=fields, c_type=lt)
                # Positional struct construction via namespace: mod.Type(a, b)
                if (fa_sym.kind == SymbolKind.TYPE
                        and isinstance(fa_sym.decl, TypeDecl)
                        and not fa_sym.decl.is_sum_type):
                    type_decl: TypeDecl = fa_sym.decl
                    fields = [(f.name, arg)
                              for f, arg in zip(type_decl.fields, lowered_args)]
                    struct_mod = getattr(fa_sym, 'module_path', None) or self._module_path
                    struct_lt = LStruct(mangle(struct_mod, type_decl.name,
                                              file=self._file, line=expr.line, col=expr.col))
                    self._retain_struct_fields(fields, list(expr.args))
                    return LCompound(fields=fields, c_type=struct_lt)
                # Regular function via namespace: mod.func(...)
                if fa_sym.kind in (SymbolKind.FN, SymbolKind.CONSTRUCTOR):
                    mod_path = fa_sym.module_path or self._module_path
                    c_name = mangle(mod_path, None, fa_name,
                                    file=self._file, line=expr.line,
                                    col=expr.col)
                    return LCall(c_name, self._hoist_string_args(c_name, lowered_args), lt)

        # Indirect call through expression — closure call
        callee_expr = self._lower_expr(expr.callee)
        callee_type = self._type_of(expr.callee)
        if isinstance(callee_type, TFn):
            return self._make_closure_call(callee_expr, callee_type, lowered_args, lt)
        return LIndirectCall(callee_expr, lowered_args, lt)

    def _lower_extern_type(self, t: Type) -> LType:
        """Lower a type for extern FFI context.

        Like _lower_type but TFn becomes LFnPtr (raw C function pointer)
        instead of LPtr(LStruct("FL_Closure")).
        """
        if isinstance(t, TFn):
            param_ltypes = [self._lower_extern_type(p) for p in t.params]
            ret_ltype = self._lower_extern_type(t.ret)
            return LFnPtr(param_ltypes, ret_ltype)
        return self._lower_type(t)

    def _rewrite_extern_fn_args(
            self, extern_decl: ExternFnDecl,
            call_args: list[Expr],
            lowered_args: list[LExpr]) -> list[LExpr]:
        """Rewrite args for extern fn calls: replace closure-typed args with
        raw C function pointers when the arg is a direct function reference."""
        result = list(lowered_args)
        for i, param in enumerate(extern_decl.params):
            if i >= len(call_args):
                break
            param_type = self._resolve_type_ann(param.type_ann)
            if not isinstance(param_type, TFn):
                continue
            arg_expr = call_args[i]
            if isinstance(arg_expr, Ident):
                arg_sym = self._resolved.symbols.get(arg_expr)
                if arg_sym is not None and isinstance(arg_sym.decl, FnDecl):
                    # Non-capturing named function → raw C function pointer
                    fn_decl = arg_sym.decl
                    c_name = mangle(self._module_path, None, fn_decl.name,
                                    file=self._file, line=arg_expr.line,
                                    col=arg_expr.col)
                    fn_ptr_type = self._lower_type(param_type)
                    # Build LFnPtr type for correct C emission
                    param_ltypes = [self._lower_type(pt)
                                    for pt in param_type.params]
                    ret_ltype = self._lower_type(param_type.ret)
                    result[i] = LVar(c_name, LFnPtr(param_ltypes, ret_ltype))
                elif arg_sym is not None and isinstance(arg_sym.decl, Lambda):
                    raise EmitError(
                        message="cannot pass a capturing closure to an extern function; "
                                "use a named function instead",
                        file=self._file, line=arg_expr.line, col=arg_expr.col)
            elif isinstance(arg_expr, Lambda):
                raise EmitError(
                    message="cannot pass a lambda to an extern function; "
                            "use a named function instead",
                    file=self._file, line=arg_expr.line, col=arg_expr.col)
        return result

    def _lower_variant_ctor(self, name: str, decl: SumVariantDecl,
                            t: Type, lt: LType,
                            lowered_args: list[LExpr],
                            ast_args: list[Expr] | None = None) -> LExpr:
        """Lower a sum type variant constructor to a compound literal.

        Circle(5.0) → (Shape){.tag = 0, .Circle = {.radius = 5.0}}
        """
        if not isinstance(t, TSum):
            # Cross-module variant ctor: typechecker returns TAny.
            # Find the parent TypeDecl and derive TSum + LType.
            t, lt = self._find_variant_sum_type(name, decl, t, lt)
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
            ast_field_type = (decl.fields[i][1]
                              if decl.fields and i < len(decl.fields)
                              else None)
            if (variant.fields is not None
                    and i < len(variant.fields)
                    and self._is_recursive_sum_field(
                        variant.fields[i], t.name, ast_field_type)):
                tmp = self._fresh_temp()
                # For indirect recursion (e.g. LExprBox wrapping LExpr),
                # use the wrapper struct type. For direct recursion, use
                # the parent sum type.
                field_lt = self._lower_type_resolving_tvars(variant.fields[i])
                if (isinstance(field_lt, LStruct) and isinstance(lt, LStruct)
                        and field_lt.c_name != lt.c_name):
                    # Indirect: wrapper struct like LExprBox (different name)
                    alloc_lt = field_lt
                elif (isinstance(field_lt, LPtr)
                      and isinstance(field_lt.inner, LVoid)):
                    # TAny — use AST field type to determine allocation type
                    if (ast_field_type is not None
                            and isinstance(ast_field_type, NamedType)
                            and ast_field_type.name != t.name
                            and isinstance(lt, LStruct)):
                        # Indirect recursion through wrapper struct
                        # Derive module prefix from parent sum type's c_name
                        prefix = lt.c_name[:len(lt.c_name) - len(t.name)]
                        alloc_lt = LStruct(prefix + ast_field_type.name)
                    else:
                        # Direct recursion — use parent sum type
                        alloc_lt = lt
                else:
                    alloc_lt = lt
                ptr_type = LPtr(alloc_lt)
                # Type* tmp = (Type*)malloc(sizeof(Type));
                self._pending_stmts.append(LVarDecl(
                    c_name=tmp,
                    c_type=ptr_type,
                    init=LCast(
                        LCall("malloc", [LSizeOf(alloc_lt)], LPtr(LVoid())),
                        ptr_type),
                ))
                # *tmp = arg;
                self._pending_stmts.append(LAssign(
                    LDeref(LVar(tmp, ptr_type), alloc_lt),
                    arg,
                ))
                inner_fields.append((fname, LVar(tmp, ptr_type)))
            else:
                inner_fields.append((fname, arg))

        # Retain borrowed refcounted fields in non-recursive variant payload
        if ast_args is not None:
            non_recursive: list[tuple[tuple[str, LExpr], Expr]] = []
            for i, ((fname, lval), ast_val) in enumerate(
                    zip(inner_fields, ast_args)):
                is_recursive = (
                    variant.fields is not None
                    and i < len(variant.fields)
                    and self._is_recursive_sum_field(
                        variant.fields[i], t.name,
                        (decl.fields[i][1]
                         if decl.fields and i < len(decl.fields)
                         else None)))
                if not is_recursive:
                    non_recursive.append(((fname, lval), ast_val))
            if non_recursive:
                nr_fields = [f for f, _ in non_recursive]
                nr_ast = [a for _, a in non_recursive]
                self._retain_struct_fields(nr_fields, nr_ast)

        fields: list[tuple[str, LExpr]] = [("tag", LLit(str(tag), LByte()))]
        if inner_fields:
            fields.append((name, LCompound(
                fields=inner_fields,
                c_type=LStruct(variant_c_name),
            )))
        return LCompound(fields=fields, c_type=lt)

    def _find_variant_sum_type(
            self, variant_name: str, variant_decl: SumVariantDecl,
            fallback_t: Type, fallback_lt: LType
    ) -> tuple[Type, LType]:
        """Find the parent TSum type for a cross-module variant constructor.

        Scans all typed modules to find the TypeDecl containing this variant,
        then looks up the TSum type from the typed module's type map.
        """
        # Search current module first, then all_typed
        modules_to_search: list[tuple[str, TypedModule]] = [
            (self._module_path, self._typed)]
        if self._all_typed:
            modules_to_search.extend(self._all_typed.items())
        for mod_path_str, typed_mod in modules_to_search:
            for decl in typed_mod.module.decls:
                if (isinstance(decl, TypeDecl) and decl.is_sum_type
                        and any(v is variant_decl for v in decl.variants)):
                    # Found the parent TypeDecl — get its type from the typed module
                    tsum = typed_mod.types.get(decl)
                    if isinstance(tsum, TSum):
                        lt = self._lower_type(tsum)
                        return tsum, lt
                    # Construct TSum from the decl if not in type map
                    c_name = mangle(mod_path_str, decl.name, None,
                                    file=self._file, line=0, col=0)
                    lt = LStruct(c_name)
                    # Build TSum from variants
                    variants = []
                    for v in decl.variants:
                        fields = tuple(TAny() for _ in v.fields) if v.fields else None
                        variants.append(TVariant(v.name, fields))
                    tsum = TSum(decl.name, variants)
                    return tsum, lt
        return fallback_t, fallback_lt

    def _lower_method_call(self, expr: MethodCall) -> LExpr:
        """Lower method call."""
        t = self._type_of(expr)
        lt = self._lower_type(t)

        # Check if resolver bound this to a namespace function/constructor symbol
        resolved_sym = self._resolved.symbols.get(expr)

        # Sum type variant constructor via namespace: mod.Variant(...)
        if (resolved_sym is not None
                and resolved_sym.kind == SymbolKind.CONSTRUCTOR
                and isinstance(resolved_sym.decl, SumVariantDecl)):
            lowered_args = [self._lower_expr(a) for a in expr.args]
            return self._lower_variant_ctor(
                expr.method, resolved_sym.decl, t, lt, lowered_args,
                list(expr.args))

        # Struct constructor via namespace: mod.MyStruct(a, b) (ConstructorDecl)
        if (resolved_sym is not None
                and resolved_sym.kind == SymbolKind.CONSTRUCTOR
                and isinstance(resolved_sym.decl, ConstructorDecl)):
            ctor_decl: ConstructorDecl = resolved_sym.decl
            lowered_args = [self._lower_expr(a) for a in expr.args]
            fields = [(p.name, arg)
                      for p, arg in zip(ctor_decl.params, lowered_args)]
            self._retain_struct_fields(fields, list(expr.args))
            return LCompound(fields=fields, c_type=lt)

        # Positional struct construction via namespace: mod.Type(a, b) (TypeDecl)
        if (resolved_sym is not None
                and resolved_sym.kind == SymbolKind.TYPE
                and isinstance(resolved_sym.decl, TypeDecl)
                and not resolved_sym.decl.is_sum_type):
            type_decl: TypeDecl = resolved_sym.decl
            lowered_args = [self._lower_expr(a) for a in expr.args]
            fields = [(f.name, arg)
                      for f, arg in zip(type_decl.fields, lowered_args)]
            struct_mod = getattr(resolved_sym, 'module_path', None) or self._module_path
            struct_lt = LStruct(mangle(struct_mod, type_decl.name,
                                      file=self._file, line=expr.line, col=expr.col))
            self._retain_struct_fields(fields, list(expr.args))
            return LCompound(fields=fields, c_type=struct_lt)

        if resolved_sym is not None and resolved_sym.kind in (
                SymbolKind.FN, SymbolKind.IMPORT):
            fn_decl = resolved_sym.decl
            # Reorder named args to param order
            mc_args = self._reorder_args_for_decl(expr.args, fn_decl)
            lowered_args = [self._lower_expr(a) for a in mc_args]
            # Fill defaults for missing trailing params
            if isinstance(fn_decl, FnDecl):
                n_args = len(lowered_args)
                n_params = len(fn_decl.params)
                if n_args < n_params:
                    for i in range(n_args, n_params):
                        param = fn_decl.params[i]
                        if param.default is not None:
                            lowered_args.append(self._lower_expr(param.default))
            # Pack variadic args for method calls (same as _lower_call)
            if isinstance(fn_decl, FnDecl) and fn_decl.params and fn_decl.params[-1].is_variadic:
                # For generics, infer type env for concrete element type
                type_env = None
                if isinstance(fn_decl, FnDecl) and fn_decl.type_params:
                    type_env = self._infer_type_env_from_call(
                        fn_decl, list(expr.args), lowered_args)
                lowered_args = self._pack_variadic_method_args(
                    fn_decl, mc_args, lowered_args, type_env)
            # Extern fn — use literal C name, no mangling
            if isinstance(fn_decl, ExternFnDecl):
                mc_c_name = fn_decl.c_name or fn_decl.name
                # Sort closure wrapper interception
                if mc_c_name == "fl_sort_array_by" and len(mc_args) >= 2:
                    arr_arg = lowered_args[0]
                    arr_type = self._type_of(mc_args[0])
                    elem_type = (arr_type.element if isinstance(arr_type, TArray)
                                 else TAny())
                    wrapped_cmp = self._lower_sort_closure_wrapper(
                        mc_args[1], elem_type)
                    return LCall("fl_sort_array_by", [arr_arg, wrapped_cmp], lt)
                if fn_decl.type_params:
                    redirected = self._maybe_redirect_array_push(
                        fn_decl, lowered_args, lt)
                    if redirected is not None:
                        return redirected
                    repacked = self._maybe_repack_array_get(
                        fn_decl, lowered_args, list(expr.args), t, lt)
                    if repacked is not None:
                        return repacked
                    wrapped = self._lower_native_generic_call(
                        fn_decl, list(expr.args), lowered_args, t, lt)
                    if wrapped is not None:
                        return wrapped
                # Phase 4: set val_type on freshly created maps so the runtime
                # retains/releases values automatically on set/copy/free.
                call_result = LCall(mc_c_name, self._hoist_string_args(mc_c_name, lowered_args), lt)
                if mc_c_name == "fl_map_new" and isinstance(t, TMap):
                    val_tag = self._ELEM_TYPE_TAG.get(type(t.value))
                    if val_tag is not None:
                        tmp = self._fresh_temp()
                        self._pending_stmts.append(
                            LVarDecl(c_name=tmp, c_type=lt, init=call_result))
                        self._pending_stmts.append(LExprStmt(LCall(
                            "fl_map_set_val_type",
                            [LVar(tmp, lt), LLit(str(val_tag), LInt(64, True))],
                            LVoid())))
                        return LVar(tmp, lt)
                return call_result
            # Non-native imported function — use mangled name from source module
            if isinstance(fn_decl, FnDecl):
                src_module = self._resolve_import_module_path(expr.receiver)
                # Generic FnDecl — monomorphize at call site (SG-3-4-2)
                if fn_decl.type_params:
                    env = self._infer_type_env_from_call(
                        fn_decl, list(expr.args), lowered_args)
                    if env:
                        mono_name = self._record_mono_site(src_module, fn_decl, env)
                        concrete_lt = self._lower_type(self._deep_substitute(t, env))
                        final = self._wrap_mut_args(fn_decl, lowered_args)
                        return LCall(mono_name, self._hoist_string_args(mono_name, final), concrete_lt)
                # Wrap :mut args before emitting the call
                lowered_args = self._wrap_mut_args(fn_decl, lowered_args)
                c_name = mangle(src_module, None, fn_decl.name,
                                file=self._file, line=expr.line, col=expr.col)
                return LCall(c_name, self._hoist_string_args(c_name, lowered_args), lt)

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
            all_args = [LAddrOf(recv, LPtr(self._lower_type(recv_type)))] + lowered_args
            return LCall(c_name, self._hoist_string_args(c_name, all_args), lt)

        # Built-in type methods — check interface method dispatch table first (SG-3-5-1)
        type_name = self._type_name_str(recv_type)
        if type_name == "unknown":
            # Fall back to deriving type name from the LType of the lowered receiver.
            # This handles cross-module monomorphized contexts where the source module's
            # type map isn't available in all_typed (e.g. stdlib modules).
            ltype_name = self._ltype_to_type_name(getattr(recv, 'c_type', None))
            if ltype_name is not None:
                type_name = ltype_name
        builtin_op = BUILTIN_METHOD_OPS.get((type_name, expr.method))
        if builtin_op is not None:
            return self._emit_builtin_method_op(builtin_op, recv, lowered_args, lt)

        # Fallthrough: plain built-in type method (fl_<type>_<method>)
        method_c_name = f"fl_{type_name}_{expr.method}"
        all_args = [recv] + lowered_args
        return LCall(method_c_name, self._hoist_string_args(method_c_name, all_args), lt)

    def _get_callee_fn_decl(self, call: Call) -> FnDecl | None:
        """Look up the FnDecl for a call's callee from the resolver symbols."""
        sym = self._resolved.symbols.get(call.callee)
        if sym is not None and isinstance(sym.decl, FnDecl):
            return sym.decl
        return None

    def _get_capacity_expr(self, type_ann: TypeExpr | None) -> LExpr:
        """Extract a capacity expression from a type annotation.

        If the annotation uses SizedType (e.g., stream<int>[64]), lower the
        capacity expression. Otherwise return the default capacity of 64.
        """
        default = LLit("64", LInt(32, True))
        if type_ann is None:
            return default
        if isinstance(type_ann, SizedType):
            return self._lower_expr(type_ann.capacity)
        return default

    def _lower_receivable_coroutine_start(
            self, call: Call, expr: CoroutineStart) -> LExpr:
        """Lower a receivable coroutine start (first param is stream<T>).

        Creates an input channel, wraps it as a stream for the inbox param,
        prepends it to the function call args, creates a threaded coroutine,
        and wires up the input channel.

        If the first argument is a coroutine handle (direct wiring), uses
        the source coroutine's output channel as the input channel instead
        of creating a new one.
        """
        coro_ptr = LPtr(LStruct("FL_Coroutine"))
        ch_ptr = LPtr(LStruct("FL_Channel"))
        stream_ptr = LPtr(LStruct("FL_Stream"))

        # Look up callee FnDecl for capacity annotations
        callee_fn = self._get_callee_fn_decl(call)
        inbox_ann = (callee_fn.params[0].type_ann
                     if callee_fn and callee_fn.params else None)
        ret_ann = callee_fn.return_type if callee_fn else None

        # Check if first arg is a coroutine handle (direct wiring)
        is_wired = (call.args
                    and isinstance(self._type_of(call.args[0]), TCoroutine))

        if is_wired:
            # Direct wiring: use source coroutine's output channel
            source_coro = self._lower_expr(call.args[0])
            input_ch_tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=input_ch_tmp, c_type=ch_ptr,
                init=LCall("fl_coroutine_get_channel",
                            [source_coro], ch_ptr)))

            # Create inbox stream from the source's output channel (blocking)
            inbox_tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=inbox_tmp, c_type=stream_ptr,
                init=LCall("fl_stream_from_channel",
                            [LVar(input_ch_tmp, ch_ptr)], stream_ptr)))

            # Lower remaining args (skip first which is the source coroutine)
            lowered_args = [LVar(inbox_tmp, stream_ptr)]
            lowered_args.extend(self._lower_expr(a) for a in call.args[1:])
        else:
            # Standard receivable: create a new input channel
            input_ch_tmp = self._fresh_temp()
            inbox_capacity = self._get_capacity_expr(inbox_ann)
            self._pending_stmts.append(LVarDecl(
                c_name=input_ch_tmp, c_type=ch_ptr,
                init=LCall("fl_channel_new",
                            [inbox_capacity], ch_ptr)))

            # Create inbox stream (non-blocking for polling)
            inbox_tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=inbox_tmp, c_type=stream_ptr,
                init=LCall("fl_stream_from_channel_nonblocking",
                            [LVar(input_ch_tmp, ch_ptr)], stream_ptr)))

            # Lower the call args, prepending the inbox stream
            lowered_args = [LVar(inbox_tmp, stream_ptr)]
            lowered_args.extend(self._lower_expr(a) for a in call.args)

        # 4. Build the function call to get the stream (with inbox as first arg)
        call_t = self._type_of(call)
        call_lt = self._lower_type(call_t)
        # Resolve the function name using the same logic as _lower_call
        fn_c_name: str | None = None
        if isinstance(call.callee, Ident):
            sym = self._resolved.symbols.get(call.callee)
            if sym is not None and sym.kind in (SymbolKind.FN,
                                                 SymbolKind.CONSTRUCTOR):
                if isinstance(sym.decl, ExternFnDecl):
                    fn_c_name = sym.decl.c_name or sym.decl.name
                else:
                    fn_c_name = mangle(self._module_path, None,
                                       call.callee.name,
                                       file=self._file,
                                       line=call.line, col=call.col)
            elif sym is not None and sym.kind == SymbolKind.IMPORT:
                if isinstance(sym.decl, ExternFnDecl):
                    fn_c_name = sym.decl.c_name or sym.decl.name
                else:
                    fn_c_name = mangle(
                        getattr(sym, 'module_path', self._module_path),
                        None, call.callee.name,
                        file=self._file, line=call.line, col=call.col)
        elif isinstance(call.callee, MethodCall):
            # Namespace function call: mod.fn_name(args)
            callee_sym = self._resolved.symbols.get(call.callee)
            if callee_sym is not None and isinstance(callee_sym.decl, ExternFnDecl):
                fn_c_name = callee_sym.decl.c_name or callee_sym.decl.name

        if fn_c_name is None:
            # Fallback: lower the callee expr normally
            callee_expr = self._lower_expr(call.callee)
            fn_c_name = getattr(callee_expr, 'c_name',
                                getattr(callee_expr, 'fn', 'unknown'))

        stream_call = LCall(fn_c_name, lowered_args, call_lt)

        # 5. Store stream result: FL_Stream* _fl_tmp_P = fn(inbox, args...)
        stream_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=stream_tmp, c_type=stream_ptr, init=stream_call))

        # 6. Create threaded coroutine with outbox capacity
        outbox_capacity = self._get_capacity_expr(ret_ann)
        coro_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=coro_tmp, c_type=coro_ptr,
            init=LCall("fl_coroutine_new_threaded",
                        [LVar(stream_tmp, stream_ptr),
                         outbox_capacity],
                        coro_ptr)))

        # 7. Wire up input channel (only for non-wired case — wired uses source's channel)
        if not is_wired:
            self._pending_stmts.append(LExprStmt(
                LCall("fl_coroutine_set_input",
                      [LVar(coro_tmp, coro_ptr),
                       LVar(input_ch_tmp, ch_ptr)],
                      LVoid())))

        return LVar(coro_tmp, coro_ptr)

    def _lower_coroutine_pipeline(
            self, stages: list[PipelineStage], expr: CoroutinePipeline
    ) -> LExpr:
        """Lower a coroutine pipeline: a() -> b() * 5 -> c().

        Stage 0 is launched as a normal coroutine. Each subsequent stage
        reads from the previous stage's output channel:
          - With pool_size and no extra args: fl_pool_new(fn, N, channel, cap)
          - With pool_size and extra args: N individual wired coroutines,
            last one returned as the pipeline handle
          - Without pool_size: single wired coroutine
        """
        coro_ptr = LPtr(LStruct("FL_Coroutine"))
        ch_ptr = LPtr(LStruct("FL_Channel"))
        stream_ptr = LPtr(LStruct("FL_Stream"))
        pool_ptr = LPtr(LStruct("FL_Pool"))

        # --- Stage 0: launch as a regular coroutine ---
        stage0 = stages[0]
        stage0_call = stage0.call

        # Determine if stage 0 is receivable
        callee_fn_0 = self._get_callee_fn_decl(stage0_call)
        is_stage0_receivable = False
        if callee_fn_0 and callee_fn_0.params:
            first_param = callee_fn_0.params[0]
            first_type = self._resolve_type_ann(first_param.type_ann)
            if isinstance(first_type, TStream):
                is_stage0_receivable = True

        if is_stage0_receivable:
            # Use the receivable path (creates input channel, etc.)
            prev_coro_expr = self._lower_receivable_coroutine_start(
                stage0_call, CoroutineStart(
                    line=expr.line, col=expr.col, call=stage0_call))
        else:
            # Non-receivable: lower the call to get a stream, wrap in coroutine
            stream_expr = self._lower_expr(stage0_call)
            stream_tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=stream_tmp, c_type=stream_ptr, init=stream_expr))
            ret_ann = callee_fn_0.return_type if callee_fn_0 else None
            capacity = self._get_capacity_expr(ret_ann)
            prev_coro_expr = LCall("fl_coroutine_new_threaded",
                                   [LVar(stream_tmp, stream_ptr), capacity],
                                   coro_ptr)

        # Handle pool_size on stage 0 (uncommon but valid syntax)
        if stage0.pool_size is not None:
            # Pool on first stage doesn't make sense for non-receivable,
            # but if present, just ignore — typechecker allows it
            pass

        # Store stage 0 coroutine in a temp
        prev_coro_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=prev_coro_tmp, c_type=coro_ptr, init=prev_coro_expr))

        # --- Subsequent stages ---
        for i in range(1, len(stages)):
            stage = stages[i]
            callee_fn = self._get_callee_fn_decl(stage.call)
            ret_ann = callee_fn.return_type if callee_fn else None
            outbox_capacity = self._get_capacity_expr(ret_ann)
            has_extra_args = len(stage.call.args) > 0

            # Get the previous stage's output channel
            prev_ch_tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=prev_ch_tmp, c_type=ch_ptr,
                init=LCall("fl_coroutine_get_channel",
                           [LVar(prev_coro_tmp, coro_ptr)], ch_ptr)))

            if stage.pool_size is not None and not has_extra_args:
                # --- Pool path: fl_pool_new(fn_ptr, N, channel, cap) ---
                fn_c_name = self._resolve_stage_fn_name(stage.call)
                pool_size_expr = self._lower_expr(stage.pool_size)

                pool_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=pool_tmp, c_type=pool_ptr,
                    init=LCall("fl_pool_new",
                               [LCast(LVar(fn_c_name, LPtr(LVoid())),
                                      LPtr(LVoid())),
                                pool_size_expr,
                                LVar(prev_ch_tmp, ch_ptr),
                                outbox_capacity],
                               pool_ptr)))

                stage_coro_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=stage_coro_tmp, c_type=coro_ptr,
                    init=LCall("fl_pool_as_coroutine",
                               [LVar(pool_tmp, pool_ptr)], coro_ptr)))

            elif stage.pool_size is not None and has_extra_args:
                # --- Pool with extra args: N individual wired coroutines ---
                pool_size_expr = self._lower_expr(stage.pool_size)
                # We need a compile-time constant for the loop count.
                # For now, lower N individual coroutines inline if N is a literal.
                # Otherwise, fall back to a single coroutine (runtime will handle).
                # The typechecker already validated pool_size is int.
                lowered_args = [self._lower_expr(a) for a in stage.call.args]
                fn_c_name = self._resolve_stage_fn_name(stage.call)

                # Create a single wired coroutine (pool with extra args
                # needs closure support — for now, single worker)
                inbox_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=inbox_tmp, c_type=stream_ptr,
                    init=LCall("fl_stream_from_channel",
                               [LVar(prev_ch_tmp, ch_ptr)], stream_ptr)))

                call_args = [LVar(inbox_tmp, stream_ptr)] + lowered_args
                call_lt = self._lower_type(self._type_of(stage.call))
                stream_call = LCall(fn_c_name, call_args, call_lt)

                stream_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=stream_tmp, c_type=stream_ptr, init=stream_call))

                stage_coro_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=stage_coro_tmp, c_type=coro_ptr,
                    init=LCall("fl_coroutine_new_threaded",
                               [LVar(stream_tmp, stream_ptr),
                                outbox_capacity], coro_ptr)))

            else:
                # --- Single wired coroutine (no pool) ---
                inbox_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=inbox_tmp, c_type=stream_ptr,
                    init=LCall("fl_stream_from_channel",
                               [LVar(prev_ch_tmp, ch_ptr)], stream_ptr)))

                lowered_args = [LVar(inbox_tmp, stream_ptr)]
                lowered_args.extend(self._lower_expr(a) for a in stage.call.args)
                fn_c_name = self._resolve_stage_fn_name(stage.call)
                call_lt = self._lower_type(self._type_of(stage.call))
                stream_call = LCall(fn_c_name, lowered_args, call_lt)

                stream_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=stream_tmp, c_type=stream_ptr, init=stream_call))

                stage_coro_tmp = self._fresh_temp()
                self._pending_stmts.append(LVarDecl(
                    c_name=stage_coro_tmp, c_type=coro_ptr,
                    init=LCall("fl_coroutine_new_threaded",
                               [LVar(stream_tmp, stream_ptr),
                                outbox_capacity], coro_ptr)))

            prev_coro_tmp = stage_coro_tmp

        return LVar(prev_coro_tmp, coro_ptr)

    def _resolve_stage_fn_name(self, call: Call) -> str:
        """Resolve the C function name for a pipeline stage's callee."""
        if isinstance(call.callee, Ident):
            sym = self._resolved.symbols.get(call.callee)
            if sym is not None and sym.kind in (SymbolKind.FN,
                                                 SymbolKind.CONSTRUCTOR):
                if isinstance(sym.decl, ExternFnDecl):
                    return sym.decl.c_name or sym.decl.name
                return mangle(self._module_path, None, call.callee.name,
                              file=self._file, line=call.line, col=call.col)
            if sym is not None and sym.kind == SymbolKind.IMPORT:
                if isinstance(sym.decl, ExternFnDecl):
                    return sym.decl.c_name or sym.decl.name
                return mangle(
                    getattr(sym, 'module_path', self._module_path),
                    None, call.callee.name,
                    file=self._file, line=call.line, col=call.col)
        elif isinstance(call.callee, MethodCall):
            callee_sym = self._resolved.symbols.get(call.callee)
            if callee_sym is not None and isinstance(callee_sym.decl, ExternFnDecl):
                return callee_sym.decl.c_name or callee_sym.decl.name
        # Fallback
        callee_expr = self._lower_expr(call.callee)
        return getattr(callee_expr, 'c_name',
                       getattr(callee_expr, 'fn', 'unknown'))

    def _lower_coroutine_method(self, expr: MethodCall, recv: LExpr,
                                recv_type: TCoroutine,
                                args: list[LExpr], lt: LType) -> LExpr:
        """Lower coroutine method calls (.next, .done, .poll, .send)."""
        if expr.method == "next":
            return self._lower_coroutine_next(recv, recv_type)
        elif expr.method == "poll":
            return self._lower_coroutine_next(recv, recv_type, blocking=False)
        elif expr.method == "done":
            return LCall("fl_coroutine_done", [recv], LBool())
        elif expr.method == "send":
            if not args:
                raise EmitError(
                    message="coroutine .send() requires one argument",
                    file=self._file, line=expr.line, col=expr.col)
            # Cast value to void* for fl_coroutine_send
            send_val = args[0]
            send_type = recv_type.send_type
            cast_val = self._box_for_channel(send_val, send_type)
            return LCall("fl_coroutine_send",
                         [recv, cast_val], LVoid())
        elif expr.method == "stop":
            return LCall("fl_coroutine_stop", [recv], LVoid())
        elif expr.method == "kill":
            return LCall("fl_coroutine_kill", [recv], LVoid())
        raise EmitError(
            message=f"unknown coroutine method: {expr.method}",
            file=self._file, line=expr.line, col=expr.col)

    def _lower_coroutine_next(self, recv: LExpr,
                              recv_type: TCoroutine,
                              blocking: bool = True) -> LExpr:
        """Lower coroutine .next()/.poll() — returns option<yield_type>.

        fl_coroutine_next (blocking) and fl_coroutine_try_next (non-blocking)
        both return FL_Option_ptr. For pointer-type yields this is already
        correct. For value-type yields we convert to the typed option struct
        (e.g. FL_Option_int).
        """
        yield_t = recv_type.yield_type
        option_t = TOption(yield_t)
        c_option_t = self._lower_type(option_t)

        c_fn = "fl_coroutine_next" if blocking else "fl_coroutine_try_next"
        # Call runtime function — returns FL_Option_ptr
        raw_call = LCall(c_fn, [recv],
                         LStruct("FL_Option_ptr"))

        # For pointer types, FL_Option_ptr IS the option type
        if self._is_heap_type(yield_t):
            return raw_call

        # For value types, convert FL_Option_ptr → FL_Option_<type>
        raw_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=raw_tmp, c_type=LStruct("FL_Option_ptr"),
            init=raw_call))

        result_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=result_tmp, c_type=c_option_t, init=None))

        # result.tag = raw.tag
        self._pending_stmts.append(LAssign(
            target=LFieldAccess(LVar(result_tmp, c_option_t),
                                "tag", LByte()),
            value=LFieldAccess(LVar(raw_tmp, LStruct("FL_Option_ptr")),
                               "tag", LByte())))

        # if (raw.tag == 1) result.value = (YieldCType)(intptr_t)raw.value
        c_yield_t = self._lower_type(yield_t)
        cast_expr = LCast(
            LCast(
                LFieldAccess(LVar(raw_tmp, LStruct("FL_Option_ptr")),
                             "value", LPtr(LVoid())),
                LInt(64, True)),  # (intptr_t)raw.value
            c_yield_t)           # (fl_int)(intptr_t)raw.value

        self._pending_stmts.append(LIf(
            cond=LBinOp("==",
                LFieldAccess(LVar(raw_tmp, LStruct("FL_Option_ptr")),
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
        stream_lt = LPtr(LStruct("FL_Stream"))

        if expr.method == "take":
            return LCall("fl_stream_take", [recv, args[0]], stream_lt)

        if expr.method == "skip":
            return LCall("fl_stream_skip", [recv, args[0]], stream_lt)

        if expr.method == "map":
            wrapper = self._lower_stream_closure_wrapper(
                expr.args[0], recv_type.element, "map")
            return LCall("fl_stream_map", [recv, wrapper], stream_lt)

        if expr.method == "filter":
            wrapper = self._lower_stream_closure_wrapper(
                expr.args[0], recv_type.element, "filter")
            return LCall("fl_stream_filter", [recv, wrapper], stream_lt)

        if expr.method == "reduce":
            wrapper = self._lower_stream_closure_wrapper(
                expr.args[1], recv_type.element, "reduce")
            return LCall("fl_stream_reduce",
                         [recv, args[0], wrapper], LPtr(LVoid()))

        raise EmitError(
            message=f"unknown stream method: {expr.method}",
            file=self._file, line=expr.line, col=expr.col)

    def _lower_stream_closure_wrapper(self, closure_ast: Expr,
                                      elem_type: Type,
                                      kind: str) -> LExpr:
        """Generate a void*-based closure wrapper for stream helper methods.

        The stream runtime helpers call closures with (void* env, void* arg)
        signatures. User lambdas have typed signatures like (void* env, fl_int x).
        This method generates a thin wrapper that casts between the two calling
        conventions and wraps the original closure as the environment.
        """
        # Lower the original closure expression
        inner_closure = self._lower_expr(closure_ast)
        closure_lt = LPtr(LStruct("FL_Closure"))

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

            # FL_Closure* _inner = (FL_Closure*)_env;
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

            # FL_Closure* _inner = (FL_Closure*)_env;
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
                LCall("malloc", [LSizeOf(LStruct("FL_Closure"))],
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

    def _lower_sort_closure_wrapper(self, closure_ast: Expr,
                                    elem_type: Type) -> LExpr:
        """Generate a sort comparator closure wrapper for fl_sort_array_by.

        fl_sort_array_by expects a closure whose fn pointer has signature:
            fl_int (*)(void* env, const void* a_ptr, const void* b_ptr)
        where a_ptr and b_ptr are pointers into the array's element buffer.

        Flow lambdas have typed signatures like:
            fl_int (*)(void* env, fl_int a, fl_int b)

        This generates a thin wrapper that:
          1. Receives (env=outer_env, a_ptr, b_ptr)
          2. Unpacks inner closure from outer_env
          3. Dereferences a_ptr and b_ptr to typed element values
          4. Calls the inner closure with (inner->env, a_val, b_val)
        """
        inner_closure = self._lower_expr(closure_ast)
        closure_lt = LPtr(LStruct("FL_Closure"))

        fn_type = self._type_of(closure_ast)
        if not isinstance(fn_type, TFn):
            return inner_closure

        module = self._module_path
        fn_name = self._current_fn_name or "anon"
        wrapper_id = self._lambda_counter
        self._lambda_counter += 1

        wrapper_c_name = mangle_sort_wrapper(module, fn_name, wrapper_id)
        elem_lt = self._lower_type(elem_type)

        wrapper_params: list[tuple[str, LType]] = [
            ("_env", LPtr(LVoid())),
            ("_a", LPtr(LVoid())),
            ("_b", LPtr(LVoid())),
        ]
        wrapper_body: list[LStmt] = []

        # FL_Closure* _inner = (FL_Closure*)_env;
        wrapper_body.append(LVarDecl(
            c_name="_inner", c_type=closure_lt,
            init=LCast(LVar("_env", LPtr(LVoid())), closure_lt)))

        # T a_val = *(T*)_a;
        wrapper_body.append(LVarDecl(
            c_name="a_val", c_type=elem_lt,
            init=LDeref(LCast(LVar("_a", LPtr(LVoid())), LPtr(elem_lt)), elem_lt)))

        # T b_val = *(T*)_b;
        wrapper_body.append(LVarDecl(
            c_name="b_val", c_type=elem_lt,
            init=LDeref(LCast(LVar("_b", LPtr(LVoid())), LPtr(elem_lt)), elem_lt)))

        # Call inner: ((fl_int(*)(void*, T, T))_inner->fn)(_inner->env, a_val, b_val)
        ret_lt = LInt(32, True)  # fl_int — comparator return type
        fn_ptr_type = LFnPtr([LPtr(LVoid()), elem_lt, elem_lt], ret_lt)
        call_expr = LIndirectCall(
            LCast(LArrow(LVar("_inner", closure_lt), "fn", LPtr(LVoid())),
                  fn_ptr_type),
            [LArrow(LVar("_inner", closure_lt), "env", LPtr(LVoid())),
             LVar("a_val", elem_lt),
             LVar("b_val", elem_lt)],
            ret_lt)
        wrapper_body.append(LReturn(call_expr))

        # Register wrapper function
        self._fn_defs.append(LFnDef(
            c_name=wrapper_c_name,
            params=wrapper_params,
            ret=ret_lt,
            body=wrapper_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}::sort_cmp_wrapper",
        ))

        # Create outer closure: fn=wrapper, env=inner_closure
        wrap_closure_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=wrap_closure_tmp,
            c_type=closure_lt,
            init=LCast(
                LCall("malloc", [LSizeOf(LStruct("FL_Closure"))],
                      LPtr(LVoid())),
                closure_lt),
        ))
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(wrap_closure_tmp, closure_lt),
                          "fn", LPtr(LVoid())),
            value=LCast(LVar(wrapper_c_name, LPtr(LVoid())), LPtr(LVoid())),
        ))
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

    def _box_for_channel(self, val: LExpr, val_type: Type) -> LExpr:
        """Cast a value to void* for channel send.

        Heap types are already pointers. Value types (int, bool, float, byte)
        are cast through uintptr_t: (void*)(uintptr_t)val.
        """
        if self._is_heap_type(val_type):
            return LCast(val, LPtr(LVoid()))
        # Value type — cast through uint64 to void*
        return LCast(LCast(val, LInt(64, False)), LPtr(LVoid()))

    def _get_direct_fn_c_name(self, expr: Expr) -> str | None:
        """If expr is an Ident bound to SymbolKind.FN, return its mangled C name."""
        if isinstance(expr, Ident):
            sym = self._resolved.symbols.get(expr)
            if sym is not None and sym.kind == SymbolKind.FN:
                return mangle(self._module_path, None, expr.name,
                              file=self._file, line=expr.line, col=expr.col)
            if sym is not None and sym.kind == SymbolKind.IMPORT:
                if isinstance(sym.decl, ExternFnDecl):
                    return sym.decl.c_name or sym.decl.name
        return None

    # ------------------------------------------------------------------
    # Parallel fan-out lowering (Gap #10)
    # ------------------------------------------------------------------

    def _build_fanout_wrapper(self, branch_expr: Expr, branch_type: TFn,
                              fanout_id: int, branch_idx: int,
                              input_lt: LType) -> str:
        """Generate a void*(void*) wrapper for a fan-out branch.

        Returns the C name of the generated wrapper function.
        """
        module = self._module_path
        fn_name = self._current_fn_name or "anon"
        wrapper_c_name = mangle_fanout_wrapper(
            module, fn_name, fanout_id, branch_idx)

        result_lt = self._lower_type(branch_type.ret)

        wrapper_params: list[tuple[str, LType]] = [
            ("_arg", LPtr(LVoid())),
        ]
        wrapper_body: list[LStmt] = []

        # Cast void* _arg to the typed input
        if isinstance(input_lt, LPtr):
            typed_input: LExpr = LCast(
                LVar("_arg", LPtr(LVoid())), input_lt)
        else:
            typed_input = LCast(
                LCast(LVar("_arg", LPtr(LVoid())), LInt(64, True)),
                input_lt)

        # Call the branch function
        direct_name = self._get_direct_fn_c_name(branch_expr)
        if direct_name is not None:
            call_expr = LCall(direct_name, [typed_input], result_lt)
        else:
            # Closure: _arg carries a struct {void* input, FL_Closure* fn}
            # For simplicity, only support direct function names in fan-out
            call_expr = LCall(direct_name or "NULL", [typed_input], result_lt)

        # Cast result back to void*
        if isinstance(result_lt, LPtr):
            result_expr: LExpr = LCast(call_expr, LPtr(LVoid()))
        elif isinstance(result_lt, LVoid):
            # void-returning branch: return NULL
            wrapper_body.append(LExprStmt(call_expr))
            wrapper_body.append(LReturn(
                LCast(LLit("0", LInt(64, True)), LPtr(LVoid()))))
            self._fn_defs.append(LFnDef(
                c_name=wrapper_c_name,
                params=wrapper_params,
                ret=LPtr(LVoid()),
                body=wrapper_body,
                is_pure=False,
                source_name=f"{module}.{fn_name}::fanout_{fanout_id}_{branch_idx}",
            ))
            return wrapper_c_name
        else:
            result_expr = LCast(
                LCast(call_expr, LInt(64, True)), LPtr(LVoid()))

        wrapper_body.append(LReturn(result_expr))

        self._fn_defs.append(LFnDef(
            c_name=wrapper_c_name,
            params=wrapper_params,
            ret=LPtr(LVoid()),
            body=wrapper_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}::fanout_{fanout_id}_{branch_idx}",
        ))
        return wrapper_c_name

    def _lower_parallel_fanout_in_chain(self, fanout: FanOut,
                                        input_var: str,
                                        input_lt: LType) -> list[LExpr]:
        """Lower a parallel fan-out in a chain context.

        Generates wrapper functions, FL_FanoutBranch array, fl_fanout_run call,
        and result extraction. Returns list of result LExprs to push on stack.
        """
        branches = fanout.branches
        n = len(branches)
        fanout_id = self._fanout_counter
        self._fanout_counter += 1

        branch_type = LStruct("FL_FanoutBranch")
        tasks_name = self._fresh_temp()

        # Declare FL_FanoutBranch array
        self._pending_stmts.append(
            LArrayDecl(c_name=tasks_name, elem_type=branch_type, count=n))

        # Cast input to void*
        if isinstance(input_lt, LPtr):
            input_as_void: LExpr = LCast(
                LVar(input_var, input_lt), LPtr(LVoid()))
        else:
            input_as_void = LCast(
                LCast(LVar(input_var, input_lt), LInt(64, True)),
                LPtr(LVoid()))

        results: list[LExpr] = []

        for i, branch in enumerate(branches):
            bt = self._type_of(branch.expr)
            if not isinstance(bt, TFn) or len(bt.params) == 0:
                # Not a function branch — fall back to sequential
                results.append(self._lower_expr(branch.expr))
                continue

            result_lt = self._lower_type(bt.ret)

            # Generate wrapper function
            wrapper_name = self._build_fanout_wrapper(
                branch.expr, bt, fanout_id, i, input_lt)

            # tasks[i].fn = wrapper
            fn_ptr_type = LFnPtr([LPtr(LVoid())], LPtr(LVoid()))
            self._pending_stmts.append(LAssign(
                target=LFieldAccess(
                    LIndex(LVar(tasks_name, branch_type),
                           LLit(str(i), LInt(32, True)),
                           branch_type),
                    "fn", fn_ptr_type),
                value=LVar(wrapper_name, fn_ptr_type),
            ))

            # tasks[i].arg = (void*)input
            self._pending_stmts.append(LAssign(
                target=LFieldAccess(
                    LIndex(LVar(tasks_name, branch_type),
                           LLit(str(i), LInt(32, True)),
                           branch_type),
                    "arg", LPtr(LVoid())),
                value=input_as_void,
            ))

        # Call fl_fanout_run(tasks, n)
        self._pending_stmts.append(LExprStmt(
            LCall("fl_fanout_run",
                  [LVar(tasks_name, branch_type),
                   LLit(str(n), LInt(32, True))],
                  LVoid())))

        # Extract results from tasks[i].result
        for i, branch in enumerate(branches):
            bt = self._type_of(branch.expr)
            if not isinstance(bt, TFn) or len(bt.params) == 0:
                continue  # already added to results above

            result_lt = self._lower_type(bt.ret)
            raw_result = LFieldAccess(
                LIndex(LVar(tasks_name, branch_type),
                       LLit(str(i), LInt(32, True)),
                       branch_type),
                "result", LPtr(LVoid()))

            if isinstance(result_lt, LPtr):
                typed_result: LExpr = LCast(raw_result, result_lt)
            elif isinstance(result_lt, LVoid):
                continue
            else:
                typed_result = LCast(
                    LCast(raw_result, LInt(64, True)), result_lt)

            tmp = self._fresh_temp()
            self._pending_stmts.append(
                LVarDecl(c_name=tmp, c_type=result_lt, init=typed_result))
            results.append(LVar(tmp, result_lt))

        return results

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

                    # Parallel fan-out: use fl_fanout_run
                    if (elem_expr.parallel
                            and len(elem_expr.branches) > 1):
                        par_results = self._lower_parallel_fanout_in_chain(
                            elem_expr, tmp, input_type)
                        for r in par_results:
                            stack.append(r)
                    else:
                        # Sequential fan-out
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
            return LLit("NULL", LPtr(LStruct("FL_Closure")))

        closure_lt = LPtr(LStruct("FL_Closure"))
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
        # Use t.params[i] instead of self._type_of(p.type_ann): the TFn type
        # is already substituted in monomorphized context, so this correctly
        # resolves TTypeVar("T") to the concrete type.
        for i, p in enumerate(expr.params):
            p_type = t.params[i] if i < len(t.params) else TAny()
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
        # Owned-return: retain non-allocating lambda body
        if not self._is_allocating_expr(expr.body):
            retain_fn = self._RETAIN_FN.get(type(t.ret)) if t.ret else None
            if retain_fn:
                impl_body.append(LExprStmt(LCall(
                    retain_fn, [body_result], c_type=LVoid())))
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
                LCall("malloc", [LSizeOf(LStruct("FL_Closure"))],
                      LPtr(LVoid())),
                closure_lt),
        ))
        # Initialize refcount
        self._pending_stmts.append(LAssign(
            target=LArrow(LVar(closure_tmp, closure_lt),
                          "refcount", LInt(64, True)),
            value=LLit("1", LInt(64, True)),
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
        closure_lt = LPtr(LStruct("FL_Closure"))
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
        closure_lt = LPtr(LStruct("FL_Closure"))
        closure_tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(
            c_name=closure_tmp,
            c_type=closure_lt,
            init=LCast(
                LCall("malloc", [LSizeOf(LStruct("FL_Closure"))],
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
        """Lower f-string to chain of fl_string_concat calls. RT-7-3-4."""
        string_type = LPtr(LStruct("FL_String"))

        parts: list[LExpr] = []
        for part in expr.parts:
            if isinstance(part, str):
                if part:
                    escaped = part.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t").replace("\0", "\\0")
                    parts.append(self._intern_string(f'"{escaped}"'))
            else:
                # Expression part — convert to string
                inner = self._lower_expr(part)
                inner_type = self._type_of(part)
                parts.append(self._to_string_expr(inner, inner_type))

        if not parts:
            return self._intern_string('""')

        # Chain concat calls, releasing intermediate results
        result = parts[0]
        intermediates: list[str] = []
        for p in parts[1:]:
            tmp = self._fresh_temp()
            self._pending_stmts.append(
                LVarDecl(c_name=tmp, c_type=string_type, init=result))
            intermediates.append(tmp)
            result = LCall("fl_string_concat",
                           [LVar(tmp, string_type), p], string_type)

        # Release intermediate concat results (not the final one)
        if intermediates:
            final_tmp = self._fresh_temp()
            self._pending_stmts.append(
                LVarDecl(c_name=final_tmp, c_type=string_type, init=result))
            for itmp in intermediates:
                self._pending_stmts.append(
                    LExprStmt(LCall("fl_string_release",
                                    [LVar(itmp, string_type)], LVoid())))
            result = LVar(final_tmp, string_type)

        return result

    def _to_string_expr(self, expr: LExpr, t: Type) -> LExpr:
        """Convert an expression to a string expression for f-string interpolation."""
        string_type = LPtr(LStruct("FL_String"))
        match t:
            case TString():
                return expr
            case TInt(width=32, signed=True):
                return LCall("fl_int_to_string", [expr], string_type)
            case TInt(width=64, signed=True):
                return LCall("fl_int64_to_string", [expr], string_type)
            case TFloat():
                return LCall("fl_float_to_string", [expr], string_type)
            case TBool():
                return LCall("fl_bool_to_string", [expr], string_type)
            case TChar():
                return LCall("fl_char_to_string", [expr], string_type)
            case TInt():
                # Other int widths — cast to int32 first
                return LCall("fl_int_to_string",
                             [LCast(expr, LInt(32, True))], string_type)
            case _:
                # Fallback — cast to int and convert
                return LCall("fl_int_to_string",
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
        # Resolve TTypeVar or empty-variant TSum to full sum type
        if isinstance(subj_type, TTypeVar):
            resolved = self._resolve_tvar_to_sum(subj_type.name)
            if resolved is not None:
                subj_type = resolved
        if isinstance(subj_type, TSum) and len(subj_type.variants) == 0:
            resolved = self._resolve_tvar_to_sum(subj_type.name)
            if resolved is not None:
                subj_type = resolved
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

        if isinstance(inner_type, TResult):
            return self._lower_propagate_result(expr, inner, inner_type)

        if isinstance(inner_type, TOption):
            return self._lower_propagate_option(expr, inner, inner_type)

        raise EmitError(
            message="propagate (?) requires a result or option type",
            file=self._file, line=expr.line, col=expr.col,
        )

    def _lower_propagate_result(self, expr: PropagateExpr,
                                inner: LExpr, inner_type: TResult) -> LExpr:
        """Lower ? on result type."""
        result_lt = self._lower_type(inner_type)
        ok_lt = self._lower_type(inner_type.ok_type)

        # Store result in temp
        tmp = self._fresh_temp()
        self._pending_stmts.append(
            LVarDecl(c_name=tmp, c_type=result_lt, init=inner))

        # if (fl_result_is_err(tmp)) { return tmp; }
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

    def _lower_propagate_option(self, expr: PropagateExpr,
                                inner: LExpr, inner_type: TOption) -> LExpr:
        """Lower ? on option type."""
        option_lt = self._lower_type(inner_type)
        inner_lt = self._lower_type(inner_type.inner)

        # Store option in temp
        tmp = self._fresh_temp()
        self._pending_stmts.append(
            LVarDecl(c_name=tmp, c_type=option_lt, init=inner))
        tmp_var = LVar(tmp, option_lt)

        # Build none return value using the enclosing function's return type
        ret_type = self._current_fn_return_type
        if isinstance(ret_type, TOption):
            none_lt = self._lower_type(ret_type)
        else:
            none_lt = option_lt
        none_val = LCompound(
            fields=[("tag", LLit("0", LByte()))], c_type=none_lt)

        # if (tmp.tag == 0) { return none; }
        none_check = LIf(
            cond=LBinOp(
                op="==",
                left=LFieldAccess(tmp_var, "tag", LByte()),
                right=LLit("0", LByte()),
                c_type=LBool(),
            ),
            then=[LReturn(none_val)],
            else_=[],
        )
        self._pending_stmts.append(none_check)

        # Extract some value
        val_tmp = self._fresh_temp()
        self._pending_stmts.append(
            LVarDecl(c_name=val_tmp, c_type=inner_lt,
                     init=LFieldAccess(tmp_var, "value", inner_lt)))
        return LVar(val_tmp, inner_lt)

    def _lower_copy(self, expr: CopyExpr) -> LExpr:
        """Lower @expr: always an independent mutable deep copy. RT-7-3-8."""
        inner = self._lower_expr(expr.inner)
        inner_type = self._type_of(expr.inner)

        # Value types — stack copy is trivially independent, no-op
        if isinstance(inner_type, (TInt, TFloat, TBool, TChar, TByte)):
            return inner

        # Heap types — deep copy for independence
        match inner_type:
            case TString():
                tmp = self._fresh_temp()
                lt = self._lower_type(inner_type)
                self._pending_stmts.append(
                    LVarDecl(c_name=tmp, c_type=lt,
                             init=LCall("fl_string_copy", [inner], lt)))
                return LVar(tmp, lt)
            case TArray():
                tmp = self._fresh_temp()
                lt = self._lower_type(inner_type)
                self._pending_stmts.append(
                    LVarDecl(c_name=tmp, c_type=lt,
                             init=LCall("fl_array_copy", [inner], lt)))
                return LVar(tmp, lt)
            case TStream():
                # SPEC GAP: stream deep copy not implemented; streams are
                # stateful and single-consumer; retain is used as a fallback
                self._pending_stmts.append(
                    LExprStmt(LCall("fl_stream_retain", [inner], LVoid())))
                return inner
            case _:
                # SPEC GAP: deep copy for user-defined struct/sum types not
                # yet implemented; retain used as fallback
                return inner

    def _lower_ref(self, expr: RefExpr) -> LExpr:
        """Lower &expr: cheap refcount increment for immutable heap data."""
        inner = self._lower_expr(expr.inner)
        inner_type = self._type_of(expr.inner)

        # Value types — trivially copied, no refcount needed
        if isinstance(inner_type, (TInt, TFloat, TBool, TChar, TByte)):
            return inner

        match inner_type:
            case TString():
                self._pending_stmts.append(
                    LExprStmt(LCall("fl_string_retain", [inner], LVoid())))
                return inner
            case TArray():
                self._pending_stmts.append(
                    LExprStmt(LCall("fl_array_retain", [inner], LVoid())))
                return inner
            case TStream():
                self._pending_stmts.append(
                    LExprStmt(LCall("fl_stream_retain", [inner], LVoid())))
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
            left_lt = self._lower_type(left_type)

            # When the left expr was repacked by FL_OPT_DEREF_AS (e.g., from
            # array.get_any<StructType>), the semantic type may still be
            # TOption(TTypeVar) → void*, but the actual C expression returns a
            # properly-typed option struct.  Use the deref types instead.
            if isinstance(left, LOptDerefAs):
                inner_lt = left.val_type
                left_lt = left.c_type

            # Store left in temp
            tmp = self._fresh_temp()
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
        # Retain-on-store: retain borrowed inner value
        if not self._is_allocating_expr(expr.inner):
            inner_type = self._type_of(expr.inner)
            retain_fn = self._RETAIN_FN.get(type(inner_type))
            if retain_fn:
                self._pending_stmts.append(
                    LExprStmt(LCall(retain_fn, [inner], LVoid())))
        t = self._type_of(expr)
        lt = self._lower_type(t)
        return LCompound(
            fields=[("tag", LLit("1", LByte())), ("value", inner)],
            c_type=lt,
        )

    def _lower_ok(self, expr: OkExpr) -> LExpr:
        """Lower ok(value)."""
        inner = self._lower_expr(expr.inner)
        # Retain-on-store: retain borrowed inner value
        if not self._is_allocating_expr(expr.inner):
            inner_type = self._type_of(expr.inner)
            retain_fn = self._RETAIN_FN.get(type(inner_type))
            if retain_fn:
                self._pending_stmts.append(
                    LExprStmt(LCall(retain_fn, [inner], LVoid())))
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
        # Retain-on-store: retain borrowed inner value
        if not self._is_allocating_expr(expr.inner):
            inner_type = self._type_of(expr.inner)
            retain_fn = self._RETAIN_FN.get(type(inner_type))
            if retain_fn:
                self._pending_stmts.append(
                    LExprStmt(LCall(retain_fn, [inner], LVoid())))
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
        else_final: list[LStmt] = []
        if expr.else_branch is not None:
            if isinstance(expr.else_branch, Block):
                else_stmts = self._lower_block(expr.else_branch)
                else_final = self._extract_block_result(else_stmts, result_var)
            else:
                # Else is another IfExpr
                else_result = self._lower_expr(expr.else_branch)
                else_pending = list(self._pending_stmts)
                self._pending_stmts = []
                else_pending.append(LAssign(result_var, else_result))
                else_final = else_pending

        self._pending_stmts.append(
            LIf(cond=cond, then=then_assign, else_=else_final))

        return result_var

    def _extract_block_result(self, stmts: list[LStmt],
                               result_var: LVar) -> list[LStmt]:
        """Replace the last expression statement with an assignment to result_var."""
        if not stmts:
            return stmts
        last = stmts[-1]
        # Detect discarded-value-release pattern from _lower_expr_stmt:
        #   VarDecl(tmp, init=allocating_call)
        #   ExprStmt(release(tmp))
        # The value is NOT discarded — it's the block result. Undo the
        # release and use the VarDecl init as the value.
        if (len(stmts) >= 2
                and isinstance(last, LExprStmt)
                and isinstance(last.expr, LCall)
                and last.expr.fn_name in self._RELEASE_FN.values()
                and isinstance(stmts[-2], LVarDecl)
                and stmts[-2].init is not None):
            decl = stmts[-2]
            return stmts[:-2] + [LAssign(result_var, decl.init)]
        if isinstance(last, LExprStmt):
            return stmts[:-1] + [LAssign(result_var, last.expr)]
        if isinstance(last, LReturn) and last.value is not None:
            return stmts[:-1] + [LAssign(result_var, last.value)]
        return stmts

    def _lower_array_lit(self, expr: ArrayLit) -> LExpr:
        """Lower array literal.

        Phase 4 (element refcounting): after creating the array, if the
        element type is a refcounted heap type (string, array, map, etc.),
        emit fl_array_set_elem_type so the runtime knows to retain/release
        elements on push/copy/free.

        For non-empty literals fl_array_new copies the data via memcpy but
        does NOT retain elements.  The runtime's release path WILL release
        them.  So we emit explicit retain calls for every element to give the
        array ownership without stealing the caller's reference.
        """
        t = self._type_of(expr)
        lt = self._lower_type(t)
        elem_type = TAny()
        if isinstance(t, TArray):
            elem_type = t.element
        elem_lt = self._lower_type(elem_type)

        tag = self._ELEM_TYPE_TAG.get(type(elem_type))

        if not expr.elements:
            arr_call = LCall("fl_array_new",
                             [LLit("0", LInt(64, True)),
                              LLit("0", LInt(64, True)),
                              LLit("NULL", LPtr(LVoid()))],
                             lt)
            if tag is None:
                return arr_call
            # Emit: Type* _fl_tmp_N = fl_array_new(...);
            #        fl_array_set_elem_type(_fl_tmp_N, TAG);
            tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(c_name=tmp, c_type=lt, init=arr_call))
            self._pending_stmts.append(LExprStmt(LCall(
                "fl_array_set_elem_type",
                [LVar(tmp, lt), LLit(str(tag), LInt(64, True))],
                LVoid())))
            return LVar(tmp, lt)

        lowered_elems = [self._lower_expr(e) for e in expr.elements]
        count = len(lowered_elems)

        # Create a compound literal array and pass its address to fl_array_new
        data_expr = LArrayData(
            elements=lowered_elems,
            elem_type=elem_lt,
            c_type=LPtr(elem_lt),
        )
        arr_call = LCall("fl_array_new",
                         [LLit(str(count), LInt(64, True)),
                          LSizeOf(elem_lt),
                          data_expr],
                         lt)

        if tag is None:
            return arr_call

        # Refcounted element type: store array in temp, set elem_type, retain
        # each element so the array holds an owned reference without stealing
        # the caller's reference.
        tmp = self._fresh_temp()
        self._pending_stmts.append(LVarDecl(c_name=tmp, c_type=lt, init=arr_call))
        self._pending_stmts.append(LExprStmt(LCall(
            "fl_array_set_elem_type",
            [LVar(tmp, lt), LLit(str(tag), LInt(64, True))],
            LVoid())))
        retain_fn = self._RETAIN_FN.get(type(elem_type))
        if retain_fn:
            for lowered_elem in lowered_elems:
                self._pending_stmts.append(LExprStmt(LCall(
                    retain_fn, [lowered_elem], LVoid())))
        return LVar(tmp, lt)

    def _lower_type_lit(self, expr: TypeLit) -> LExpr:
        """Lower type literal (struct construction)."""
        t = self._type_of(expr)
        lt = self._lower_type(t)

        # Look up declared field types from the struct's TypeDecl so we can
        # set elem_type on empty array fields (whose inferred type is
        # TArray(TAny) — no concrete element type without the declaration).
        decl_field_types = self._get_struct_field_types(expr.type_name)

        lfields: list[tuple[str, LExpr]] = []
        for name, val in expr.fields:
            lowered_val = self._lower_expr(val)

            # Set elem_type on empty arrays from declared field type,
            # since the typechecker infers TArray(TAny) for empty
            # literals without context.  Must store the array in a
            # temp first — lowered_val is an LCall that would create
            # a new array each time it's evaluated.
            if isinstance(val, ArrayLit) and not val.elements:
                decl_t = decl_field_types.get(name)
                if isinstance(decl_t, TArray):
                    tag = self._ELEM_TYPE_TAG.get(type(decl_t.element))
                    if tag is not None:
                        arr_lt = self._lower_type(TArray(decl_t.element))
                        tmp = self._fresh_temp()
                        self._pending_stmts.append(
                            LVarDecl(c_name=tmp, c_type=arr_lt,
                                     init=lowered_val))
                        self._pending_stmts.append(LExprStmt(LCall(
                            "fl_array_set_elem_type",
                            [LVar(tmp, arr_lt),
                             LLit(str(tag), LInt(64, True))],
                            LVoid())))
                        lowered_val = LVar(tmp, arr_lt)

            # Retain-on-store: retain borrowed refcounted field values
            if not self._is_allocating_expr(val):
                val_type = self._type_of(val)
                retain_fn = self._RETAIN_FN.get(type(val_type))
                if retain_fn:
                    self._pending_stmts.append(
                        LExprStmt(LCall(retain_fn, [lowered_val], LVoid())))
            lfields.append((name, lowered_val))
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
                        ast_field_types = self._get_variant_field_ast_types(
                            sum_t.name, vname)
                        for i, binding in enumerate(bindings):
                            if i < len(variant.fields):
                                field_lt = self._lower_type_resolving_tvars(variant.fields[i])
                                # Track match binding type for monomorphization
                                self._let_var_ltypes[binding] = field_lt
                                fname = field_names[i] if i < len(field_names) else f"_{i}"
                                ast_ft = ast_field_types[i] if i < len(ast_field_types) else None
                                is_recursive = self._is_recursive_sum_field(
                                    variant.fields[i], sum_t.name, ast_ft)
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
                return self._lower_inner_block(arm.body)
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
        # Search imported modules
        if self._all_typed:
            for _mod_path, typed_mod in self._all_typed.items():
                for decl in typed_mod.module.decls:
                    if isinstance(decl, TypeDecl) and decl.name == sum_name and decl.is_sum_type:
                        for variant in decl.variants:
                            if variant.name == vname and variant.fields is not None:
                                return [fname for fname, _ in variant.fields]
        return []

    def _get_variant_field_ast_types(self, sum_name: str, vname: str) -> list:
        """Get AST-level type expressions for a variant's fields."""
        for decl in self._module.decls:
            if isinstance(decl, TypeDecl) and decl.name == sum_name and decl.is_sum_type:
                for variant in decl.variants:
                    if variant.name == vname and variant.fields is not None:
                        return [ftype for _, ftype in variant.fields]
        if self._all_typed:
            for _mp, tmod in self._all_typed.items():
                for decl in tmod.module.decls:
                    if isinstance(decl, TypeDecl) and decl.name == sum_name and decl.is_sum_type:
                        for variant in decl.variants:
                            if variant.name == vname and variant.fields is not None:
                                return [ftype for _, ftype in variant.fields]
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
                            some_body.extend(self._lower_inner_block(arm.body))
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
                            none_body = self._lower_inner_block(arm.body)
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
                            none_body = self._lower_inner_block(arm.body)
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
                            ok_body.extend(self._lower_inner_block(arm.body))
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
                            err_body.extend(self._lower_inner_block(arm.body))
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
                            err_body = self._lower_inner_block(arm.body)
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
                            body = self._lower_inner_block(arm.body)
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
                            body_stmts.extend(self._lower_inner_block(arm.body))
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
                        ast_field_types = self._get_variant_field_ast_types(
                            sum_t.name, vname)
                        for i, binding in enumerate(bindings):
                            if i < len(variant.fields):
                                field_lt = self._lower_type_resolving_tvars(variant.fields[i])
                                # Track match binding type for monomorphization
                                self._let_var_ltypes[binding] = field_lt
                                fname = field_names[i] if i < len(field_names) else f"_{i}"
                                ast_ft = ast_field_types[i] if i < len(ast_field_types) else None
                                is_recursive = self._is_recursive_sum_field(
                                    variant.fields[i], sum_t.name, ast_ft)
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
                block_stmts = self._lower_inner_block(arm.body)
                # Detect discarded-value-release pattern: VarDecl + release call
                if (len(block_stmts) >= 2
                        and isinstance(block_stmts[-1], LExprStmt)
                        and isinstance(block_stmts[-1].expr, LCall)
                        and block_stmts[-1].expr.fn_name in self._RELEASE_FN.values()
                        and isinstance(block_stmts[-2], LVarDecl)
                        and block_stmts[-2].init is not None):
                    decl = block_stmts[-2]
                    self._pending_stmts.extend(block_stmts[:-2])
                    return decl.init
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
            return LCall("fl_string_eq", [subj, val_expr], LBool())
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
        option_ptr_type = LStruct("FL_Option_ptr")

        # next function body: cast self->state to frame, switch on _state
        next_body: list[LStmt] = []

        # frame_type* frame = (frame_type*)self->state;
        frame_var_name = "frame"
        next_body.append(LVarDecl(
            c_name=frame_var_name,
            c_type=frame_ptr_type,
            init=LCast(
                LArrow(LVar("self", LPtr(LStruct("FL_Stream"))),
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
            params=[("self", LPtr(LStruct("FL_Stream")))],
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
                LArrow(LVar("self", LPtr(LStruct("FL_Stream"))),
                       "state", LPtr(LVoid())),
                frame_ptr_type),
        ))
        # free(frame)
        free_body.append(LExprStmt(LCall("free",
                                          [LVar(frame_var_name, frame_ptr_type)],
                                          LVoid())))

        self._fn_defs.append(LFnDef(
            c_name=free_c_name,
            params=[("self", LPtr(LStruct("FL_Stream")))],
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

        # return fl_stream_new(next, free, frame)
        factory_body.append(LReturn(
            LCall("fl_stream_new",
                  [LVar(next_c_name, LPtr(LVoid())),
                   LVar(free_c_name, LPtr(LVoid())),
                   LCast(LVar(frame_var_name, frame_ptr_type), LPtr(LVoid()))],
                  LPtr(LStruct("FL_Stream"))),
        ))

        factory_params: list[tuple[str, LType]] = []
        for p in fn.params:
            p_type = self._type_of(p.type_ann) if p.type_ann else TNone()
            factory_params.append((p.name, self._lower_type(p_type)))

        self._fn_defs.append(LFnDef(
            c_name=factory_c_name,
            params=factory_params,
            ret=LPtr(LStruct("FL_Stream")),
            body=factory_body,
            is_pure=False,
            source_name=f"{module}.{fn_name}",
        ))

    def _resolve_ns_to_module_path(self, ns_name: str) -> str:
        """Resolve a namespace alias (from import) to the full module path."""
        for imp in self._module.imports:
            imp_ns = imp.alias if imp.alias else imp.path[-1]
            if imp_ns == ns_name:
                return ".".join(imp.path)
        return ns_name

    def _resolve_import_module_path(self, receiver: Expr) -> str:
        """Get the module path for a namespace import receiver."""
        if isinstance(receiver, Ident):
            return self._resolve_ns_to_module_path(receiver.name)
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
            case MatchStmt(arms=arms):
                for arm in arms:
                    if isinstance(arm.body, Block):
                        for s in arm.body.stmts:
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
            case MatchStmt(arms=arms):
                for arm in arms:
                    # Collect bindings from match arm patterns
                    match arm.pattern:
                        case SomePattern(inner_var=var):
                            if var and var not in existing_names:
                                subj_type = self._type_of(stmt.subject)
                                if isinstance(subj_type, TOption):
                                    locals_.append((var, subj_type.inner))
                                else:
                                    locals_.append((var, TAny()))
                                existing_names = {n for n, _ in locals_}
                        case BindPattern(name=name):
                            if name not in existing_names:
                                locals_.append((name, self._type_of(stmt.subject)))
                                existing_names = {n for n, _ in locals_}
                        case _:
                            pass
                    if isinstance(arm.body, Block):
                        for s in arm.body.stmts:
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

        option_ptr_type = LStruct("FL_Option_ptr")
        num_yields = len(yield_stmts)

        # Lower body with yields converted to state transitions + gotos
        yield_counter = [0]  # mutable counter shared across recursion
        body_stmts = self._lower_stream_stmts(
            body.stmts, frame_var, elem_type, yield_counter)

        # Rewrite all frame variable references to use frame-> access
        body_stmts = self._rewrite_frame_access(
            body_stmts, frame_var, frame_c_name, frame_names)

        # Terminal: return FL_NONE
        done_label = "_fl_stream_done"
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
            switch_cases.append((i, [LGoto(f"_fl_state_{i}")]))
        switch_default = [LGoto(done_label)]

        frame_state = LArrow(
            LVar(frame_var, LPtr(LStruct(frame_c_name))),
            "_state", LInt(32, True))

        result: list[LStmt] = []
        result.append(LSwitch(value=frame_state, cases=switch_cases,
                               default=switch_default))
        # State 0 label — initial entry
        result.append(LLabel("_fl_state_0"))
        result.extend(body_stmts)

        return result

    def _lower_stream_stmts(self, stmts: list[Stmt], frame_var: str,
                              elem_type: Type,
                              yield_counter: list[int]) -> list[LStmt]:
        """Lower a list of statements for stream body, handling yields
        at any nesting level."""
        result: list[LStmt] = []
        option_ptr_type = LStruct("FL_Option_ptr")

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

                # Return FL_SOME(value) — cast through uintptr_t for value types
                void_value = LCast(LCast(value, LInt(64, False)), LPtr(LVoid()))
                result.append(LReturn(LCompound(
                    fields=[("tag", LLit("1", LByte())),
                            ("value", void_value)],
                    c_type=option_ptr_type)))

                # Resume label for this yield point
                result.append(LLabel(f"_fl_state_{state_num}"))

            elif isinstance(stmt, ReturnStmt):
                result.append(LGoto("_fl_stream_done"))

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

            elif isinstance(stmt, MatchStmt):
                # Set stream context so _lower_block inside match arm
                # lowering delegates to _lower_stream_stmts.
                saved_ctx = self._stream_body_ctx
                self._stream_body_ctx = (frame_var, elem_type, yield_counter)
                saved = self._pending_stmts
                self._pending_stmts = []
                lowered = self._lower_match_stmt(stmt)
                result.extend(self._pending_stmts)
                result.extend(lowered)
                self._pending_stmts = saved
                self._stream_body_ctx = saved_ctx

            elif isinstance(stmt, ForStmt):
                # Lower for-over-stream with yield-aware body lowering.
                # We reconstruct the while loop structure from _lower_for_stream
                # but recurse into _lower_stream_stmts for the body so that
                # yield statements get proper state machine resume labels.
                iter_t = self._type_of(stmt.iterable)
                if isinstance(iter_t, TStream):
                    stream_expr = self._lower_expr(stmt.iterable)
                    stream_lt = LPtr(LStruct("FL_Stream"))
                    stream_elem_t = iter_t.element
                    elem_lt = self._lower_type(stream_elem_t)
                    next_name = self._fresh_temp()
                    # Use stream_expr directly inside the loop (no local temp)
                    # so it survives yield resume via frame rewriting.
                    next_decl = LVarDecl(
                        c_name=next_name,
                        c_type=LStruct("FL_Option_ptr"),
                        init=LCall("fl_stream_next", [stream_expr],
                                   LStruct("FL_Option_ptr")))
                    tag_check = LIf(
                        cond=LBinOp(
                            op="==",
                            left=LFieldAccess(
                                LVar(next_name, LStruct("FL_Option_ptr")),
                                "tag", LByte()),
                            right=LLit("0", LByte()),
                            c_type=LBool()),
                        then=[LBreak()], else_=[])
                    value_access = LFieldAccess(
                        LVar(next_name, LStruct("FL_Option_ptr")),
                        "value", LPtr(LVoid()))
                    if isinstance(elem_lt, LPtr):
                        item_init = LCast(value_access, elem_lt)
                    else:
                        item_init = LCast(LCast(value_access,
                                                LInt(64, False)), elem_lt)
                    item_decl = LVarDecl(c_name=stmt.var, c_type=elem_lt,
                                         init=item_init)
                    # Recurse into body with yield-aware lowering
                    inner_body = self._lower_stream_stmts(
                        stmt.body.stmts, frame_var, elem_type, yield_counter)
                    loop_body = [next_decl, tag_check, item_decl] + inner_body
                    result.append(LWhile(cond=LLit("1", LBool()),
                                         body=loop_body))
                    if stmt.finally_block is not None:
                        result.extend(self._lower_stream_stmts(
                            stmt.finally_block.stmts, frame_var,
                            elem_type, yield_counter))
                else:
                    # Non-stream for loops: lower normally
                    for_stmts = self._lower_for(stmt)
                    result.extend(for_stmts)

            else:
                # Temporarily clear stream context so _lower_stmt doesn't
                # accidentally re-enter stream-aware lowering for leaf stmts.
                saved_ctx = self._stream_body_ctx
                self._stream_body_ctx = None
                saved = self._pending_stmts
                self._pending_stmts = []
                lowered = self._lower_stmt(stmt)
                result.extend(self._pending_stmts)
                result.extend(lowered)
                self._pending_stmts = saved
                self._stream_body_ctx = saved_ctx

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
        name = f"_fl_tmp_{self._tmp_counter}"
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
                    # Resolve namespace alias to full module path
                    ns_name = mp[0] if len(mp) == 1 else ".".join(mp)
                    full_path = self._resolve_ns_to_module_path(ns_name)
                    return TNamed(full_path, name, ())
                builtin = _BUILTIN_TYPE_ANNS.get(name)
                if builtin is not None:
                    return builtin
                # In monomorphized context, substitute type variables
                if self._mono_type_env and name in self._mono_type_env:
                    return self._mono_type_env[name]
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

            case SizedType(inner=inner):
                return self._resolve_type_ann(inner)

            case _:
                return TAny()

    def _ltype_to_type(self, lt: LType | None) -> Type | None:
        """Convert an LType back to the corresponding semantic Type, if possible.

        Used as a fallback when the type map contains TTypeVar/TAny for variables
        whose concrete type is known from their LType (e.g. let-bound vars that
        received the result of a bounded generic call).
        """
        match lt:
            case LInt(width=32, signed=True):
                return TInt(32, True)
            case LInt(width=w, signed=True):
                return TInt(w, True)
            case LInt(width=w, signed=False):
                return TInt(w, False)
            case LFloat(width=64):
                return TFloat(64)
            case LFloat(width=w):
                return TFloat(w)
            case LBool():
                return TBool()
            case LChar():
                return TChar()
            case LByte():
                return TByte()
            case LPtr(inner=LStruct(c_name="FL_String")):
                return TString()
            case _:
                return None

    def _ltype_to_type_name(self, lt: LType | None) -> str | None:
        """Convert an LType to the type-name string used in C function names.

        Used as a fallback in _lower_method_call when the semantic type is
        unavailable (TAny) — e.g. inside cross-module monomorphized bodies
        whose source TypedModule isn't in all_typed.
        """
        match lt:
            case LInt(width=32, signed=True):
                return "int"
            case LInt(width=w, signed=True):
                return f"int{w}"
            case LInt(width=w, signed=False):
                return f"uint{w}"
            case LFloat(width=64):
                return "float"
            case LFloat(width=w):
                return f"float{w}"
            case LBool():
                return "bool"
            case LChar():
                return "char"
            case LByte():
                return "byte"
            case LPtr(inner=LStruct(c_name="FL_String")):
                return "string"
            case _:
                return None

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
            case TNamed(module=mod, name=name):
                resolved_mod = mod if mod else self._find_sum_type_module(name)
                if resolved_mod and '.' not in resolved_mod:
                    resolved_mod = self._resolve_ns_to_module_path(resolved_mod)
                if resolved_mod:
                    return f"{resolved_mod.replace('.', '_')}_{name}"
                return name
            case TSum(name=name):
                mod_path = self._find_sum_type_module(name)
                if mod_path:
                    return f"{mod_path.replace('.', '_')}_{name}"
                return name
            case _:
                return "unknown"

    def _is_recursive_sum_field(self, field_type: Type,
                                enclosing_name: str,
                                ast_type: TypeExpr | None = None) -> bool:
        """Check if a variant field type refers to its enclosing sum type,
        either directly or indirectly through a wrapper struct that embeds it
        by value (e.g. LExprBox wrapping LExpr)."""
        match field_type:
            case TSum(name=name) if name == enclosing_name:
                return True
            case TNamed(name=name) if name == enclosing_name:
                return True
            case _:
                pass
        # Fallback: check AST-level type annotation (cross-module case where
        # typechecker assigns TAny to sum type fields)
        if ast_type is not None and isinstance(ast_type, NamedType):
            if ast_type.name == enclosing_name:
                return True
            # Indirect recursion: a wrapper struct (e.g. LExprBox) that
            # by-value embeds the enclosing sum type. Only check when the
            # AST type name differs from enclosing_name (not direct recursion).
            wrapper_name = ast_type.name
            if wrapper_name != enclosing_name:
                for d in self._module.decls:
                    if (isinstance(d, TypeDecl) and d.name == wrapper_name
                            and not d.variants and d.fields):
                        for fd in d.fields:
                            if (fd.type_ann is not None
                                    and isinstance(fd.type_ann, NamedType)
                                    and fd.type_ann.name == enclosing_name):
                                return True
                        break
                if self._all_typed:
                    for _mp, tmod in self._all_typed.items():
                        for d in tmod.module.decls:
                            if (isinstance(d, TypeDecl) and d.name == wrapper_name
                                    and not d.variants and d.fields):
                                for fd in d.fields:
                                    if (fd.type_ann is not None
                                            and isinstance(fd.type_ann, NamedType)
                                            and fd.type_ann.name == enclosing_name):
                                        return True
                                break
        return False

    # ------------------------------------------------------------------
    # array.push redirect for non-pointer element types (Gap-1)
    # ------------------------------------------------------------------

    def _maybe_repack_array_get(
        self,
        fn_decl: FnDecl | ExternFnDecl,
        lowered_args: list[LExpr],
        arg_exprs: list[Expr],
        result_type: Type,
        result_lt: LType,
    ) -> LExpr | None:
        """Repack fl_array_get_safe result for non-pointer element types.

        fl_array_get_safe returns FL_Option_ptr where .value is a pointer to
        the element data in the array buffer.  For non-pointer element types
        (structs, sum types), we need to dereference that pointer and wrap in
        the correct option struct.
        """
        if _get_c_fn_name(fn_decl) != "fl_array_get_safe":
            return None
        if not fn_decl.type_params:
            return None
        c_fn = _get_c_fn_name(fn_decl)
        # Infer what T is
        env = self._infer_type_env_from_call(fn_decl, arg_exprs, lowered_args)
        if not env and self._mono_type_env:
            # Inside a monomorphized function (e.g. array.slice<Expr>), the
            # module context is swapped to stdlib so _infer_type_env_from_call
            # can't resolve the concrete element type from argument types.
            # Fall back to the outer monomorphization's type env.
            env = self._mono_type_env
        if not env:
            return None
        for tp in fn_decl.type_params:
            concrete = env.get(tp.name)
            if concrete is None:
                continue
            # TTypeVar means the typechecker didn't resolve the element type
            # to a concrete named type.  Try to resolve it by looking up the
            # type name as a TNamed in the current module context.
            if isinstance(concrete, TTypeVar):
                resolved_mod = self._find_sum_type_module(concrete.name)
                if resolved_mod:
                    struct_c_name = mangle(resolved_mod, concrete.name,
                                          file=self._file, line=0, col=0)
                    concrete_lt = LStruct(struct_c_name)
                else:
                    concrete_lt = self._lower_type(concrete)
            else:
                concrete_lt = self._lower_type(concrete)
            # Skip pointer types — FL_Option_ptr is already correct
            if isinstance(concrete_lt, LPtr):
                return None
            # Build the correct option type for non-pointer element types.
            # The result_lt from the caller may be FL_Option_ptr when the
            # typechecker left the element type as TTypeVar, so we rebuild it.
            # Also ensure the option struct typedef is registered.
            effective_result_lt = result_lt
            if isinstance(concrete_lt, LStruct):
                inner_key = _ltype_c_name(concrete_lt)
                if inner_key in self._option_registry:
                    opt_c_name = self._option_registry[inner_key]
                else:
                    opt_c_name = f"FL_Option_{concrete_lt.c_name}"
                    self._option_registry[inner_key] = opt_c_name
                    self._type_defs.append(LTypeDef(
                        c_name=opt_c_name,
                        fields=[("tag", LByte()), ("value", concrete_lt)],
                    ))
                effective_result_lt = LStruct(opt_c_name)
            # For value types already handled by Gap-2 opt_unbox (int, float, etc.)
            c_name = _ltype_c_name(concrete_lt)
            if c_name in _VALUE_TYPE_OPT_UNBOX_FN:
                # Array get_safe returns a pointer to the element, not a boxed
                # value.  Use FL_OPT_DEREF_AS to cast and dereference.
                call = LCall(c_fn, lowered_args,
                             LStruct("FL_Option_ptr"))
                return LOptDerefAs(call, concrete_lt, effective_result_lt)
            # Struct/sum types — use FL_OPT_DEREF_AS
            if isinstance(concrete_lt, LStruct):
                call = LCall(c_fn, lowered_args,
                             LStruct("FL_Option_ptr"))
                return LOptDerefAs(call, concrete_lt, effective_result_lt)
        return None

    def _maybe_redirect_array_push(
        self,
        fn_decl: FnDecl | ExternFnDecl,
        lowered_args: list[LExpr],
        lt: LType,
    ) -> LExpr | None:
        """Redirect fl_array_push_ptr to fl_array_push(&val) for non-pointer elements.

        fl_array_push_ptr hardcodes element_size = sizeof(void*), which is wrong
        for value-type elements like sum type structs.  fl_array_push uses
        arr->element_size and takes a void* pointer to the element data.
        """
        if _get_c_fn_name(fn_decl) != "fl_array_push_ptr":
            return None
        if not fn_decl.type_params or len(lowered_args) < 2:
            return None
        # The second arg is the element value
        elem_arg = lowered_args[1]
        elem_lt = getattr(elem_arg, 'c_type', None)
        # If the element is already a pointer type, fl_array_push_ptr is fine
        if isinstance(elem_lt, LPtr):
            return None
        # Non-pointer element: use fl_array_push_sized(arr, &val, sizeof(ElemType))
        # fl_array_push_sized sets element_size on the array if it was 0 (empty
        # array case), then delegates to fl_array_push for the actual copy.
        # Must store in a temp first since &(fn_call()) is invalid C (rvalue).
        if elem_lt is not None:
            tmp = self._fresh_temp()
            self._pending_stmts.append(LVarDecl(
                c_name=tmp, c_type=elem_lt, init=elem_arg))
            addr_of = LAddrOf(LVar(tmp, elem_lt),
                              LPtr(elem_lt))
        else:
            addr_of = LAddrOf(elem_arg, LPtr(LVoid()))
        size_of = LSizeOf(elem_lt if elem_lt else LVoid())
        return LCall("fl_array_push_sized",
                     [lowered_args[0], addr_of, size_of], lt)

    def _heap_box_struct(self, expr: LExpr, struct_lt: LStruct) -> LExpr:
        """Heap-box a struct value for passing through void* generic params.

        Generates:
            Type* _fl_tmp_N = (Type*)malloc(sizeof(Type));
            *_fl_tmp_N = expr;
        Returns LVar pointing to the temp.
        """
        tmp = self._fresh_temp()
        ptr_type = LPtr(struct_lt)
        self._pending_stmts.append(LVarDecl(
            c_name=tmp,
            c_type=ptr_type,
            init=LCast(
                LCall("malloc", [LSizeOf(struct_lt)], LPtr(LVoid())),
                ptr_type),
        ))
        self._pending_stmts.append(LAssign(
            LDeref(LVar(tmp, ptr_type), struct_lt),
            expr,
        ))
        return LCast(LVar(tmp, ptr_type), LPtr(LVoid()))

    # ------------------------------------------------------------------
    # Value-type boxing for generic native calls (Gap-2)
    # ------------------------------------------------------------------

    def _lower_native_generic_call(
        self,
        fn_decl: FnDecl | ExternFnDecl,
        arg_exprs: list[Expr],
        lowered_args: list[LExpr],
        result_type: Type,
        result_lt: LType,
    ) -> LExpr | None:
        """Wrap a native generic call with box/unbox when T is a value type.

        Returns an LExpr with the correct boxing/unboxing applied, or None
        if no wrapping is needed (T is a pointer type).
        """
        if not fn_decl.type_params:
            return None
        env = self._infer_type_env_from_call(fn_decl, arg_exprs, lowered_args)
        if not env:
            return None

        # Check if any type param resolved to a value type that needs boxing
        needs_boxing = False
        for tp in fn_decl.type_params:
            concrete = env.get(tp.name)
            if concrete is not None:
                concrete_lt = self._lower_type(concrete)
                c_name = _ltype_c_name(concrete_lt)
                if c_name in _VALUE_TYPE_BOX_FN:
                    needs_boxing = True
                    break
                # Struct types (sum types, etc.) also need boxing for void* params
                if isinstance(concrete_lt, LStruct) and c_name not in (
                        "FL_String", "FL_Array", "FL_Map", "FL_Set",
                        "FL_Stream", "FL_Coroutine", "FL_Buffer",
                        "FL_StringBuilder"):
                    needs_boxing = True
                    break
        if not needs_boxing:
            return None

        # Box value-type arguments: for each param whose declared type
        # involves a type param that resolved to a value type, wrap with
        # the box function.
        boxed_args: list[LExpr] = []
        for i, param in enumerate(fn_decl.params):
            if i >= len(lowered_args):
                break
            arg = lowered_args[i]
            if param.type_ann is not None:
                declared = self._types.get(param.type_ann)
                if declared is None:
                    declared = self._resolve_type_ann(param.type_ann)
                # Check if this param's type is (or involves) a type variable
                # that resolved to a value type
                tp_name = self._extract_type_var_name(declared, fn_decl)
                if tp_name and tp_name in env:
                    concrete = env[tp_name]
                    concrete_lt = self._lower_type(concrete)
                    c_name = _ltype_c_name(concrete_lt)
                    box_fn = _VALUE_TYPE_BOX_FN.get(c_name)
                    if box_fn:
                        arg = LCall(box_fn, [arg], LPtr(LVoid()))
                    elif isinstance(concrete_lt, LStruct):
                        # Struct value type: heap-box via address-of cast
                        arg = self._heap_box_struct(arg, concrete_lt)
            boxed_args.append(arg)

        # Make the call with void*-based types
        call = LCall(_get_c_fn_name(fn_decl), boxed_args,
                     LStruct("FL_Option_ptr")
                     if self._return_is_option_of_typevar(fn_decl, env)
                     else result_lt)

        # Unbox return value if it's an option<T> where T is a value type
        if self._return_is_option_of_typevar(fn_decl, env):
            for tp in fn_decl.type_params:
                concrete = env.get(tp.name)
                if concrete is not None:
                    concrete_lt = self._lower_type(concrete)
                    c_name = _ltype_c_name(concrete_lt)
                    opt_unbox_fn = _VALUE_TYPE_OPT_UNBOX_FN.get(c_name)
                    if opt_unbox_fn:
                        return LCall(opt_unbox_fn, [call], result_lt)
                    # Struct value type: dereference via FL_OPT_DEREF_AS
                    if isinstance(concrete_lt, LStruct):
                        return LOptDerefAs(call, concrete_lt, result_lt)
            # Unbox for plain value return (not option)
            for tp in fn_decl.type_params:
                concrete = env.get(tp.name)
                if concrete is not None:
                    concrete_lt = self._lower_type(concrete)
                    c_name = _ltype_c_name(concrete_lt)
                    unbox_fn = _VALUE_TYPE_UNBOX_FN.get(c_name)
                    if unbox_fn:
                        return LCall(unbox_fn, [call], result_lt)

        return call

    def _extract_type_var_name(self, declared: Type, fn_decl: FnDecl | ExternFnDecl) -> str | None:
        """If declared is a type variable matching one of fn_decl's type params, return its name."""
        tp_names = {tp.name for tp in fn_decl.type_params}
        match declared:
            case TTypeVar(name=name) if name in tp_names:
                return name
            case TNamed(module="", name=name, type_args=()) if name in tp_names:
                return name
        return None

    def _return_is_option_of_typevar(self, fn_decl: FnDecl | ExternFnDecl, env: dict[str, Type]) -> bool:
        """Check if the function's return type is option<T> where T is a type param."""
        if fn_decl.return_type is None:
            return False
        ret_type = self._types.get(fn_decl.return_type)
        if ret_type is None:
            ret_type = self._resolve_type_ann(fn_decl.return_type)
        tp_names = {tp.name for tp in fn_decl.type_params}
        match ret_type:
            case TOption(inner=TTypeVar(name=name)) if name in tp_names:
                return True
            case TOption(inner=TNamed(module="", name=name, type_args=())) if name in tp_names:
                return True
        return False

    # ------------------------------------------------------------------
    # Monomorphization helpers (SG-3-2-1 through SG-3-5-1)
    # ------------------------------------------------------------------

    def _is_bounded_generic(self, fn: FnDecl) -> bool:
        """Return True if fn is a bounded generic (has type params with bounds)."""
        return bool(fn.type_params and any(tp.bounds for tp in fn.type_params))

    def _deep_substitute(self, ty: Type, env: dict[str, Type]) -> Type:
        """Recursively replace TTypeVar (and bare TNamed type params) with concrete types.

        'env' maps type parameter names to their concrete types.
        Also handles TNamed("", name, ()) produced by _resolve_type_ann for type params
        that were not recorded in typed.types (cross-module case).
        """
        if not env:
            return ty
        match ty:
            case TTypeVar(name=name) if name in env:
                return env[name]
            # _resolve_type_ann maps unknown bare names to TNamed("", name, ())
            # which includes type parameter names in cross-module functions.
            case TNamed(module="", name=name, type_args=()) if name in env:
                return env[name]
            case TArray(element=elem):
                return TArray(self._deep_substitute(elem, env))
            case TStream(element=elem):
                return TStream(self._deep_substitute(elem, env))
            case TCoroutine(yield_type=yt, send_type=st):
                return TCoroutine(self._deep_substitute(yt, env),
                                  self._deep_substitute(st, env))
            case TBuffer(element=elem):
                return TBuffer(self._deep_substitute(elem, env))
            case TOption(inner=inner):
                return TOption(self._deep_substitute(inner, env))
            case TResult(ok_type=ok, err_type=err):
                return TResult(self._deep_substitute(ok, env),
                               self._deep_substitute(err, env))
            case TMap(key=key, value=val):
                return TMap(self._deep_substitute(key, env),
                            self._deep_substitute(val, env))
            case TSet(element=elem):
                return TSet(self._deep_substitute(elem, env))
            case TTuple(elements=elems):
                return TTuple(tuple(self._deep_substitute(e, env) for e in elems))
            case TFn(params=params, ret=ret, is_pure=is_pure, is_variadic=variadic):
                return TFn(
                    tuple(self._deep_substitute(p, env) for p in params),
                    self._deep_substitute(ret, env),
                    is_pure,
                    is_variadic=variadic,
                )
            case TNamed(module=mod, name=name, type_args=args):
                return TNamed(mod, name,
                              tuple(self._deep_substitute(a, env) for a in args))
            case _:
                # Leaf types (TInt, TFloat, TBool, TChar, TByte, TString,
                # TNone, TAny, TSum, TRecord, TAlias) — return unchanged.
                return ty

    def _build_substituted_type_map(
        self,
        fn_decl: FnDecl,
        env: dict[str, Type],
        src_module: str | None = None,
    ) -> dict[ASTNode, Type]:
        """Build a type map with TTypeVar replaced by concrete types.

        Merges the current module's types with those of src_module (if
        cross-module and all_typed is available). This gives cross-module
        monomorphization access to the source module's node types.
        """
        substituted: dict[ASTNode, Type] = {}

        # Current module's types — TTypeVar → concrete
        for node, ty in self._typed.types.items():
            substituted[node] = self._deep_substitute(ty, env)

        # Cross-module: merge source module's types
        if (src_module and src_module != self._module_path
                and self._all_typed):
            src_typed = self._all_typed.get(src_module)
            if src_typed is not None:
                for node, ty in src_typed.types.items():
                    substituted[node] = self._deep_substitute(ty, env)

        return substituted

    def _infer_type_env_from_call(
        self,
        fn_decl: FnDecl | ExternFnDecl,
        arg_exprs: list[Expr],
        lowered_args: list[LExpr] | None = None,
    ) -> dict[str, Type]:
        """Infer type variable bindings from call-site argument types.

        Matches declared parameter types against actual argument types to
        extract bindings like {"T": TInt(32, True)}. Works for both same-module
        and cross-module functions (handles TNamed from _resolve_type_ann).

        When lowered_args is provided, uses the LType of already-lowered
        arguments as a fallback when the semantic type is TTypeVar or TAny
        (which happens because the typechecker propagates TTypeVar through
        bounded-generic call return types without substituting them).
        """
        tp_names = {tp.name for tp in fn_decl.type_params}
        env: dict[str, Type] = {}
        for i, (param, arg_expr) in enumerate(zip(fn_decl.params, arg_exprs)):
            if param.type_ann is None:
                continue
            # Prefer typed.types (has TTypeVar for same-module params);
            # fall back to _resolve_type_ann for cross-module params.
            declared = self._types.get(param.type_ann)
            if declared is None:
                declared = self._resolve_type_ann(param.type_ann)
            actual = self._type_of(arg_expr)
            # Fallback: if the semantic type is TTypeVar or TAny (typechecker
            # doesn't substitute generic call return types), use the LType of
            # the already-lowered argument expression to get the concrete type.
            if isinstance(actual, (TTypeVar, TAny)) and lowered_args is not None:
                if i < len(lowered_args):
                    lt_type = self._ltype_to_type(getattr(lowered_args[i], 'c_type', None))
                    if lt_type is not None:
                        actual = lt_type
            self._match_type_vars(declared, actual, tp_names, env)
        return env

    def _match_type_vars(
        self,
        declared: Type,
        actual: Type,
        tp_names: set[str],
        env: dict[str, Type],
    ) -> None:
        """Recursively match type variable positions in declared against actual."""
        match declared:
            case TTypeVar(name=name) if name in tp_names:
                if name not in env:
                    env[name] = actual
            # Cross-module: type params come through as TNamed("", "T", ())
            case TNamed(module="", name=name, type_args=()) if name in tp_names:
                if name not in env:
                    env[name] = actual
            case TArray(element=elem):
                if isinstance(actual, TArray):
                    self._match_type_vars(elem, actual.element, tp_names, env)
            case TOption(inner=inner):
                if isinstance(actual, TOption):
                    self._match_type_vars(inner, actual.inner, tp_names, env)
            case TResult(ok_type=ok, err_type=err):
                if isinstance(actual, TResult):
                    self._match_type_vars(ok, actual.ok_type, tp_names, env)
                    self._match_type_vars(err, actual.err_type, tp_names, env)
            case TMap(key=key, value=val):
                if isinstance(actual, TMap):
                    self._match_type_vars(key, actual.key, tp_names, env)
                    self._match_type_vars(val, actual.value, tp_names, env)
            case _:
                pass  # Leaf types — no type variables to match

    def _record_mono_site(
        self,
        src_module: str,
        fn_decl: FnDecl,
        env: dict[str, Type],
    ) -> str:
        """Record a monomorphization site and return its mangled C name."""
        type_args = [
            self._type_name_str(env[tp.name])
            for tp in fn_decl.type_params
            if tp.name in env
        ]
        key = (src_module, fn_decl.name, tuple(type_args))
        if key not in self._mono_sites:
            mono_name = mangle_monomorphized(src_module, fn_decl.name, type_args)
            self._mono_sites[key] = MonoSite(
                fn_decl=fn_decl,
                type_env=env,
                mangled_name=mono_name,
                src_module=src_module,
            )
        return self._mono_sites[key].mangled_name

    def _lower_monomorphized_fn(self, site: MonoSite) -> LFnDef:
        """Lower a bounded generic function with concrete type substitutions.

        Swaps the type map, resolver, and module path for the duration of
        lowering so that all symbol lookups and _type_of calls resolve against
        the source module. After lowering, all state is restored.
        """
        fn_decl = site.fn_decl
        env = site.type_env

        # Build substituted type map (merges current + source module types)
        sub_types = self._build_substituted_type_map(fn_decl, env, site.src_module)

        # Save and swap the type map — all _type_of calls use sub_types
        original_types = self._types
        self._types = sub_types

        # For cross-module monomorphization, swap resolver and module path so
        # that symbol lookups (fn calls, imports) resolve against the source
        # module, not the calling module.
        saved_resolved = self._resolved
        saved_module_path = self._module_path
        if site.src_module != self._module_path and self._all_typed:
            src_typed = self._all_typed.get(site.src_module)
            if src_typed is not None:
                self._resolved = src_typed.resolved
                self._module_path = site.src_module

        # Save per-function context
        saved_return_type = self._current_fn_return_type
        saved_fn_name = self._current_fn_name
        self._current_fn_name = fn_decl.name
        saved_let_var_ltypes = self._let_var_ltypes
        self._let_var_ltypes = {}
        saved_mono_type_env = self._mono_type_env
        self._mono_type_env = env
        saved_mono_caller = self._mono_caller_module_path
        self._mono_caller_module_path = saved_module_path
        saved_container_locals = self._container_locals
        self._container_locals = []
        saved_scope_depth = self._scope_depth
        self._scope_depth = 0

        ret_type_raw = self._type_of_return(fn_decl)
        ret_type = self._deep_substitute(ret_type_raw, env)
        self._current_fn_return_type = ret_type

        # Lower parameters with concrete types
        params: list[tuple[str, LType]] = []
        for p in fn_decl.params:
            p_type_raw = self._type_of(p.type_ann) if p.type_ann else TNone()
            p_type = self._deep_substitute(p_type_raw, env)
            # Variadic params are arrays of the element type
            if p.is_variadic:
                p_type = TArray(p_type)
            p_lt = self._lower_type(p_type)
            params.append((p.name, p_lt))
            self._let_var_ltypes[p.name] = p_lt

        # Lower function body with substituted types
        body: list[LStmt] = []
        ret_lt = self._lower_type(ret_type)
        if fn_decl.body is not None:
            match fn_decl.body:
                case Block():
                    body = self._lower_block(fn_decl.body)
                case Expr():
                    expr_result = self._lower_expr(fn_decl.body)
                    body = list(self._pending_stmts)
                    self._pending_stmts = []
                    # Owned-return: retain non-allocating expression body
                    if not self._is_allocating_expr(fn_decl.body):
                        retain_fn = self._RETAIN_FN.get(
                            type(self._current_fn_return_type)
                        ) if self._current_fn_return_type else None
                        if retain_fn:
                            body.append(LExprStmt(LCall(
                                retain_fn, [expr_result], c_type=LVoid())))
                    body.append(LReturn(expr_result))

        # Scope-exit cleanup for monomorphized functions
        if self._container_locals:
            self._inject_scope_cleanup(body)
            if isinstance(ret_lt, LVoid):
                body.extend([LExprStmt(LCall(fn_name, [LVar(n, ct)], LVoid()))
                             for n, ct, fn_name, depth in self._container_locals
                             if depth == 0])

        # Restore state
        self._types = original_types
        self._resolved = saved_resolved
        self._module_path = saved_module_path
        self._current_fn_return_type = saved_return_type
        self._current_fn_name = saved_fn_name
        self._let_var_ltypes = saved_let_var_ltypes
        self._mono_type_env = saved_mono_type_env
        self._mono_caller_module_path = saved_mono_caller
        self._container_locals = saved_container_locals
        self._scope_depth = saved_scope_depth

        return LFnDef(
            c_name=site.mangled_name,
            params=params,
            ret=ret_lt,
            body=body,
            is_pure=fn_decl.is_pure,
            source_name=f"{site.src_module}.{fn_decl.name}[mono]",
        )

    def _emit_builtin_method_op(
        self,
        op: BuiltinMethodOp,
        recv: LExpr,
        args: list[LExpr],
        lt: LType,
    ) -> LExpr:
        """Emit the C expression for a built-in interface method call (SG-3-5-1)."""
        match op.kind:
            case "compare":
                # _fl_compare(a, b) → ((a) < (b) ? -1 : ((a) > (b) ? 1 : 0))
                return LCall("_fl_compare", [recv, args[0]], LInt(32, True))
            case "binop":
                return LBinOp(op.op, recv, args[0], lt)
            case "checked_binop":
                # Integer arithmetic — uses FL_CHECKED_ADD/SUB/MUL (overflow → panic)
                return LCheckedArith(op=op.op, left=recv, right=args[0], c_type=lt)
            case "unary":
                return LUnary(op.op, recv, lt)
            case "call":
                return LCall(op.op, [recv] + args, lt)
            case _:
                raise EmitError(
                    message=f"unknown BuiltinMethodOp kind: {op.kind!r}",
                    file=self._file, line=0, col=0,
                )
