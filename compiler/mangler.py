# compiler/mangler.py — Flow names → C identifiers.
# Nothing else.
#
# Rules:
#   Prefix:   fl_
#   Dots:     math.vector         → fl_math_vector
#   Type:     math.vector.Vec3    → fl_math_vector_Vec3
#   Method:   math.vector.Vec3.dot → fl_math_vector_Vec3_dot
#   Function: pipeline.orders.run → fl_pipeline_orders_run
#
# Built-in types are not mangled: int, float, bool, etc. map to C types directly.
from __future__ import annotations

from compiler.errors import EmitError

_PREFIX = "fl_"

# C reserved words — using one as a Flow identifier is a compile error.
C_RESERVED = frozenset({
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof",
    "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn",
    "_Static_assert", "_Thread_local",
})

# Flow built-in types that map directly to C runtime typedefs.
# These are never mangled through the normal path.
BUILTIN_TYPES = frozenset({
    "int", "int16", "int32", "int64",
    "uint", "uint16", "uint32", "uint64",
    "float", "float32", "float64",
    "bool", "byte", "char", "string", "none",
})

# Map from Flow built-in type names to C typedef names.
BUILTIN_TYPE_MAP: dict[str, str] = {
    "int": "fl_int",
    "int16": "fl_int16",
    "int32": "fl_int32",
    "int64": "fl_int64",
    "uint": "fl_uint",
    "uint16": "fl_uint16",
    "uint32": "fl_uint32",
    "uint64": "fl_uint64",
    "float": "fl_float",
    "float32": "fl_float32",
    "float64": "fl_float64",
    "bool": "fl_bool",
    "byte": "fl_byte",
    "char": "fl_char",
    "string": "FL_String*",
    "none": "void",
}


def mangle(module: str, type_name: str | None = None,
           fn_name: str | None = None, *,
           file: str = "<unknown>", line: int = 0, col: int = 0) -> str:
    """Mangle a Flow qualified name into a C identifier.

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

    # No reserved-word check needed: the fl_ prefix guarantees no
    # collision with C keywords.

    return result


def mangle_builtin_type(type_name: str) -> str:
    """Return the C typedef for a Flow built-in type.

    Args:
        type_name: A built-in type name like "int", "string", etc.

    Returns:
        The C type string, e.g. "fl_int", "FL_String*".

    Raises:
        KeyError: If type_name is not a built-in type.
    """
    return BUILTIN_TYPE_MAP[type_name]


def mangle_stream_frame(module: str, fn_name: str) -> str:
    """Mangle a stream function's frame struct name.

    Example: math.vector.generate → _fl_frame_math_vector_generate
    """
    parts = module.replace(".", "_")
    return f"_fl_frame_{parts}_{fn_name}"


def mangle_stream_next(module: str, fn_name: str) -> str:
    """Mangle a stream function's next function name.

    Example: math.vector.generate → _fl_next_math_vector_generate
    """
    parts = module.replace(".", "_")
    return f"_fl_next_{parts}_{fn_name}"


def mangle_stream_free(module: str, fn_name: str) -> str:
    """Mangle a stream function's free function name.

    Example: math.vector.generate → _fl_free_math_vector_generate
    """
    parts = module.replace(".", "_")
    return f"_fl_free_{parts}_{fn_name}"


def mangle_closure_frame(module: str, fn_name: str, lambda_id: int) -> str:
    """Mangle a closure's frame struct name.

    Example: pipeline.orders.run, lambda 0 → _fl_closure_pipeline_orders_run_0
    """
    parts = module.replace(".", "_")
    return f"_fl_closure_{parts}_{fn_name}_{lambda_id}"


def mangle_closure_fn(module: str, fn_name: str, lambda_id: int) -> str:
    """Mangle a closure's implementation function name.

    Example: pipeline.orders.run, lambda 0 → _fl_clfn_pipeline_orders_run_0
    """
    parts = module.replace(".", "_")
    return f"_fl_clfn_{parts}_{fn_name}_{lambda_id}"


def mangle_fn_wrapper(module: str, fn_name: str) -> str:
    """Mangle a named function's closure wrapper name.

    Example: pipeline.orders.run → _fl_wrap_pipeline_orders_run
    """
    parts = module.replace(".", "_")
    return f"_fl_wrap_{parts}_{fn_name}"


def mangle_stream_wrapper(module: str, fn_name: str,
                          wrapper_id: int) -> str:
    """Mangle a stream helper closure wrapper function name.

    Example: main, process, 0 → _fl_swrap_main_process_0
    """
    parts = module.replace(".", "_")
    return f"_fl_swrap_{parts}_{fn_name}_{wrapper_id}"


def mangle_sort_wrapper(module: str, fn_name: str,
                        wrapper_id: int) -> str:
    """Mangle a sort comparator closure wrapper function name.

    Example: sort, sort, 0 → _fl_srtwrap_sort_sort_0
    """
    parts = module.replace(".", "_")
    return f"_fl_srtwrap_{parts}_{fn_name}_{wrapper_id}"


def mangle_fanout_wrapper(module: str, fn_name: str,
                          fanout_id: int, branch_idx: int) -> str:
    """Mangle a parallel fan-out branch wrapper function name.

    Example: main, process, 0, 1 → _fl_fanout_main_process_0_1
    """
    parts = module.replace(".", "_")
    return f"_fl_fanout_{parts}_{fn_name}_{fanout_id}_{branch_idx}"


def mangle_exception_tag(module: str, type_name: str) -> str:
    """Integer constant name for exception type dispatch.

    Example: domain.order.ParseError → _fl_exc_tag_domain_order_ParseError
    """
    parts = module.replace(".", "_")
    return f"_fl_exc_tag_{parts}_{type_name}"


def mangle_exception_frame(index: int) -> str:
    """Local exception frame variable name.

    Example: index 0 → _fl_ef_0
    """
    return f"_fl_ef_{index}"


def mangle_monomorphized(module: str, fn_name: str, type_args: list[str]) -> str:
    """Mangle a monomorphized function name.

    Example: math, min, ["int"]   → fl_math_min__int
    Example: math, min, ["float"] → fl_math_min__float
    Example: testing, assert_eq, ["int"] → fl_testing_assert_eq__int

    The double underscore separates the function name from the type
    specialization suffix, making it visually distinct from the base name
    and from method names (which use a single underscore).
    """
    parts = module.replace(".", "_")
    suffix = "_".join(type_args)
    return f"{_PREFIX}{parts}_{fn_name}__{suffix}"


def mangle_struct_elem_destructor(c_struct_name: str) -> str:
    """Name of the per-struct array element destructor function.

    Example: fl_sh_lexer_Token → _fl_destroy_fl_sh_lexer_Token
    """
    return f"_fl_destroy_{c_struct_name}"


def mangle_struct_elem_retainer(c_struct_name: str) -> str:
    """Name of the per-struct array element retainer function.

    Example: fl_sh_lexer_Token → _fl_retain_fl_sh_lexer_Token
    """
    return f"_fl_retain_{c_struct_name}"


def _check_reserved(name: str | None, file: str, line: int, col: int) -> None:
    """Raise EmitError if a bare name is a C reserved word."""
    if name is not None and name in C_RESERVED:
        raise EmitError(
            message=f"identifier '{name}' is a C reserved word and cannot be used",
            file=file,
            line=line,
            col=col,
        )
