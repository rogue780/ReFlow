# compiler/mangler.py — ReFlow names → C identifiers.
# Nothing else.
#
# Rules:
#   Prefix:   rf_
#   Dots:     math.vector         → rf_math_vector
#   Type:     math.vector.Vec3    → rf_math_vector_Vec3
#   Method:   math.vector.Vec3.dot → rf_math_vector_Vec3_dot
#   Function: pipeline.orders.run → rf_pipeline_orders_run
#
# Built-in types are not mangled: int, float, bool, etc. map to C types directly.
from __future__ import annotations

from compiler.errors import EmitError

_PREFIX = "rf_"

# C reserved words — using one as a ReFlow identifier is a compile error.
C_RESERVED = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
    "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
    "_Static_assert", "_Thread_local",
})

# ReFlow built-in types that map directly to C runtime typedefs.
# These are never mangled through the normal path.
BUILTIN_TYPES = frozenset({
    "int", "int16", "int32", "int64",
    "uint", "uint16", "uint32", "uint64",
    "float", "float32", "float64",
    "bool", "byte", "char", "string", "none",
})

# Map from ReFlow built-in type names to C typedef names.
BUILTIN_TYPE_MAP: dict[str, str] = {
    "int": "rf_int",
    "int16": "rf_int16",
    "int32": "rf_int32",
    "int64": "rf_int64",
    "uint": "rf_uint",
    "uint16": "rf_uint16",
    "uint32": "rf_uint32",
    "uint64": "rf_uint64",
    "float": "rf_float",
    "float32": "rf_float32",
    "float64": "rf_float64",
    "bool": "rf_bool",
    "byte": "rf_byte",
    "char": "rf_char",
    "string": "RF_String*",
    "none": "void",
}


def mangle(module: str, type_name: str | None = None,
           fn_name: str | None = None, *,
           file: str = "<unknown>", line: int = 0, col: int = 0) -> str:
    """Mangle a ReFlow qualified name into a C identifier.

    Args:
        module: Dot-separated module path, e.g. "math.vector"
        type_name: Optional type name, e.g. "Vec3"
        fn_name: Optional function/method name, e.g. "dot"
        file, line, col: Source location for error reporting.

    Returns:
        Mangled C identifier string.

    Raises:
        EmitError: If the resulting identifier collides with a C reserved word.
    """
    parts = module.replace(".", "_")
    result = _PREFIX + parts

    if type_name is not None:
        result += "_" + type_name

    if fn_name is not None:
        result += "_" + fn_name

    # No reserved-word check needed: the rf_ prefix guarantees no
    # collision with C keywords.

    return result


def mangle_builtin_type(type_name: str) -> str:
    """Return the C typedef for a ReFlow built-in type.

    Args:
        type_name: A built-in type name like "int", "string", etc.

    Returns:
        The C type string, e.g. "rf_int", "RF_String*".

    Raises:
        KeyError: If type_name is not a built-in type.
    """
    return BUILTIN_TYPE_MAP[type_name]


def mangle_stream_frame(module: str, fn_name: str) -> str:
    """Mangle a stream function's frame struct name.

    Example: math.vector.generate → _rf_frame_math_vector_generate
    """
    parts = module.replace(".", "_")
    return f"_rf_frame_{parts}_{fn_name}"


def mangle_stream_next(module: str, fn_name: str) -> str:
    """Mangle a stream function's next function name.

    Example: math.vector.generate → _rf_next_math_vector_generate
    """
    parts = module.replace(".", "_")
    return f"_rf_next_{parts}_{fn_name}"


def mangle_stream_free(module: str, fn_name: str) -> str:
    """Mangle a stream function's free function name.

    Example: math.vector.generate → _rf_free_math_vector_generate
    """
    parts = module.replace(".", "_")
    return f"_rf_free_{parts}_{fn_name}"


def mangle_closure_frame(module: str, fn_name: str, lambda_id: int) -> str:
    """Mangle a closure's frame struct name.

    Example: pipeline.orders.run, lambda 0 → _rf_closure_pipeline_orders_run_0
    """
    parts = module.replace(".", "_")
    return f"_rf_closure_{parts}_{fn_name}_{lambda_id}"


def mangle_closure_fn(module: str, fn_name: str, lambda_id: int) -> str:
    """Mangle a closure's implementation function name.

    Example: pipeline.orders.run, lambda 0 → _rf_clfn_pipeline_orders_run_0
    """
    parts = module.replace(".", "_")
    return f"_rf_clfn_{parts}_{fn_name}_{lambda_id}"


def mangle_fn_wrapper(module: str, fn_name: str) -> str:
    """Mangle a named function's closure wrapper name.

    Example: pipeline.orders.run → _rf_wrap_pipeline_orders_run
    """
    parts = module.replace(".", "_")
    return f"_rf_wrap_{parts}_{fn_name}"


def _check_reserved(name: str | None, file: str, line: int, col: int) -> None:
    """Raise EmitError if a bare name is a C reserved word."""
    if name is not None and name in C_RESERVED:
        raise EmitError(
            message=f"identifier '{name}' is a C reserved word and cannot be used",
            file=file,
            line=line,
            col=col,
        )
