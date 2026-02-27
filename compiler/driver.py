# compiler/driver.py — Pipeline orchestration.
# No compiler logic. Calls other modules in order.
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from compiler.ast_nodes import Module, ImportDecl, ExternLibDecl, FnDecl
from compiler.errors import ResolveError
from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.resolver import Resolver, ModuleScope
from compiler.typechecker import TypeChecker
from compiler.lowering import Lowerer
from compiler.emitter import Emitter

# Stdlib module names that live in the stdlib/ directory.
_STDLIB_MODULES = frozenset({"io", "sys", "conv", "string", "char", "path", "math", "sort", "bytes", "file", "random", "time", "testing", "net", "json", "array", "string_builder", "map", "csv"})


# ---------------------------------------------------------------------------
# Parsed module cache entry
# ---------------------------------------------------------------------------

@dataclass
class _ParsedModule:
    source_path: Path
    display_path: str
    module: Module          # parsed AST
    module_key: str         # dot-separated, e.g. "self_hosted.lexer"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _display_path(path: Path) -> str:
    """Return a relative display path for a source file."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _stdlib_dir() -> Path:
    """Return the path to the stdlib/ directory."""
    return Path(__file__).resolve().parent.parent / "stdlib"


def _infer_project_root(source_path: Path, module_path: list[str]) -> Path:
    """Infer the project root from a source file and its module declaration.

    If the module declares ``module a.b.c`` and the file is at
    ``/proj/a/b/c.flow``, the project root is ``/proj``.
    If there is no module path (empty list), the root is the file's parent.
    """
    parent = source_path.resolve().parent
    if not module_path:
        return parent
    # The module path minus the last segment gives the directory nesting
    # above the file.  e.g. module a.b.c -> path components ["a", "b"]
    # that should be stripped from the parent dir.
    nesting = module_path[:-1]
    root = parent
    for part in reversed(nesting):
        if root.name == part:
            root = root.parent
        else:
            # Fall back to the file's parent if the path doesn't match.
            return parent
    return root


def _resolve_import_path(project_root: Path, import_path: list[str]) -> Path:
    """Map an import path to a filesystem path relative to the project root.

    ``import a.b.c`` → ``<project_root>/a/b/c.flow``
    """
    return project_root / Path(*import_path).with_suffix(".flow")


# ---------------------------------------------------------------------------
# Stdlib discovery
# ---------------------------------------------------------------------------

# Module-level cache: one parse+resolve+typecheck per stdlib module per process.
# Keyed by module name. Value is a TypedModule (typed as object to avoid
# exposing TypedModule in the function signature).
_stdlib_typed_cache: dict[str, object] = {}


def _get_stdlib_typed(module_name: str) -> object:
    """Return the TypedModule for a stdlib module, running the full pipeline once.

    Caches the result so each stdlib module is parsed+resolved+type-checked
    at most once per process. The cache ensures AST node identity is stable:
    all downstream passes (Resolver, Lowerer) that reference stdlib FnDecls
    see the SAME Python objects whose types are stored in the TypedModule.types
    dict, enabling correct cross-module monomorphization.
    """
    if module_name not in _stdlib_typed_cache:
        stdlib_path = _stdlib_dir() / f"{module_name}.flow"
        source = stdlib_path.read_text()
        display = f"stdlib/{module_name}.flow"
        tokens = Lexer(source, display).tokenize()
        module = Parser(tokens, display).parse()
        resolved = Resolver(module).resolve()
        _stdlib_typed_cache[module_name] = TypeChecker(resolved).check()
    return _stdlib_typed_cache[module_name]


def _load_stdlib_module(module_name: str) -> ModuleScope:
    """Return the ModuleScope for a stdlib module (via the typed module cache)."""
    return _get_stdlib_typed(module_name).resolved.module_scope  # type: ignore[attr-defined]


def _discover_stdlib_imports(module: Module) -> dict[str, ModuleScope]:
    """Discover and load stdlib modules needed by the given parsed Module."""
    imported: dict[str, ModuleScope] = {}
    for imp in module.imports:
        module_key = ".".join(imp.path)
        if module_key in _STDLIB_MODULES:
            if module_key not in imported:
                imported[module_key] = _load_stdlib_module(module_key)
    return imported


def _stdlib_needs_compilation(typed_module) -> bool:
    """Return True if the stdlib module has non-generic FnDecl with bodies that need compilation."""
    for decl in typed_module.module.decls:
        if isinstance(decl, FnDecl) and decl.body is not None:
            if not decl.type_params and not decl.native_name:
                return True
    return False


def _inject_compilable_stdlib(modules):
    """Prepend stdlib modules with compilable bodies to the modules list."""
    needed: set[str] = set()
    for _, typed, _ in modules:
        for imp in typed.module.imports:
            mod_key = ".".join(imp.path)
            if mod_key in _STDLIB_MODULES and mod_key not in needed:
                stdlib_typed = _get_stdlib_typed(mod_key)
                if _stdlib_needs_compilation(stdlib_typed):
                    needed.add(mod_key)

    # Prepend stdlib modules (they must come before user modules that call them)
    for mod_key in sorted(needed):  # sorted for deterministic output
        stdlib_typed = _get_stdlib_typed(mod_key)
        display = f"stdlib/{mod_key}.flow"
        modules.insert(0, (display, stdlib_typed, False))

    return modules


# ---------------------------------------------------------------------------
# Dependency graph and topological sort
# ---------------------------------------------------------------------------

def _has_user_imports(module: Module) -> bool:
    """Return True if the module has any non-stdlib imports."""
    for imp in module.imports:
        module_key = ".".join(imp.path)
        if module_key not in _STDLIB_MODULES:
            return True
    return False


def _user_imports(module: Module) -> list[ImportDecl]:
    """Return the list of non-stdlib imports from a module."""
    result: list[ImportDecl] = []
    for imp in module.imports:
        module_key = ".".join(imp.path)
        if module_key not in _STDLIB_MODULES:
            result.append(imp)
    return result


def _parse_file(source_path: Path) -> _ParsedModule:
    """Parse a single .flow file into a _ParsedModule."""
    source = source_path.read_text()
    display = _display_path(source_path)
    tokens = Lexer(source, display).tokenize()
    module = Parser(tokens, display).parse()
    module_key = ".".join(module.path) if module.path else source_path.stem
    return _ParsedModule(
        source_path=source_path,
        display_path=display,
        module=module,
        module_key=module_key,
    )


def _build_dependency_graph(
    root_path: Path, project_root: Path
) -> list[_ParsedModule]:
    """Discover all transitively imported user modules via BFS, then
    topologically sort them (leaves first, root last).

    Raises ResolveError on circular imports or missing files.
    """
    # BFS discovery: parse each module once and record adjacency.
    cache: dict[str, _ParsedModule] = {}   # module_key -> _ParsedModule
    adjacency: dict[str, list[str]] = {}   # module_key -> [dep_keys]
    # Map module_key -> the ImportDecl that first referenced it (for errors).
    import_sites: dict[str, ImportDecl] = {}

    root_pm = _parse_file(root_path)
    cache[root_pm.module_key] = root_pm

    queue: deque[_ParsedModule] = deque([root_pm])

    while queue:
        pm = queue.popleft()
        deps: list[str] = []
        for imp in _user_imports(pm.module):
            dep_key = ".".join(imp.path)
            deps.append(dep_key)
            if dep_key in cache:
                continue

            # Resolve filesystem path.
            dep_path = _resolve_import_path(project_root, imp.path)
            if not dep_path.exists():
                # Fall back to stdlib directory for Flow-implemented modules.
                stdlib_path = _stdlib_dir() / Path(*imp.path).with_suffix(".flow")
                if stdlib_path.exists():
                    dep_path = stdlib_path
                else:
                    raise ResolveError(
                        message=(f"cannot find module '{dep_key}': "
                                 f"expected file at '{dep_path}'"),
                        file=pm.display_path,
                        line=imp.line,
                        col=imp.col,
                    )

            dep_pm = _parse_file(dep_path)

            # Validate module declaration matches import path.
            declared_key = ".".join(dep_pm.module.path) if dep_pm.module.path else ""
            if declared_key and declared_key != dep_key:
                raise ResolveError(
                    message=(f"module at '{dep_path}' declares "
                             f"'module {declared_key}' but import "
                             f"expects '{dep_key}'"),
                    file=str(dep_path),
                    line=1,
                    col=1,
                )

            cache[dep_key] = dep_pm
            import_sites[dep_key] = imp
            queue.append(dep_pm)

        adjacency[pm.module_key] = deps

    # DFS topological sort with 3-color cycle detection.
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {k: WHITE for k in cache}
    order: list[_ParsedModule] = []
    # Track path for cycle error message.
    path_stack: list[str] = []

    def dfs(key: str) -> None:
        if color[key] == BLACK:
            return
        if color[key] == GRAY:
            # Build cycle path for error message.
            cycle_start = path_stack.index(key)
            cycle = path_stack[cycle_start:] + [key]
            cycle_str = " -> ".join(cycle)
            # Find the import statement in the importing module that
            # closes the cycle back to `key`.
            importing_key = path_stack[-1] if path_stack else key
            importing_pm = cache[importing_key]
            imp_line, imp_col = 1, 1
            for imp in importing_pm.module.imports:
                if ".".join(imp.path) == key:
                    imp_line, imp_col = imp.line, imp.col
                    break
            raise ResolveError(
                message=f"circular import detected: {cycle_str}",
                file=importing_pm.display_path,
                line=imp_line,
                col=imp_col,
            )

        color[key] = GRAY
        path_stack.append(key)
        for dep_key in adjacency.get(key, []):
            if dep_key in cache:  # skip stdlib deps (not in cache)
                dfs(dep_key)
        path_stack.pop()
        color[key] = BLACK
        order.append(cache[key])

    dfs(root_pm.module_key)
    return order


def _run_pipeline(source_path: str) -> tuple[str, object]:
    """Run pipeline through type checking. Returns (display_path, typed_module).

    The return type for typed_module is TypedModule but typed as object
    to avoid exposing the type in the signature (driver owns no compiler logic).
    """
    path = Path(source_path)
    source = path.read_text()

    # Use a relative display path for the source comment in generated C.
    try:
        display_path = str(path.relative_to(Path.cwd()))
    except ValueError:
        display_path = source_path

    tokens = Lexer(source, display_path).tokenize()
    module = Parser(tokens, display_path).parse()

    # Load stdlib modules referenced by imports.
    imported_modules = _discover_stdlib_imports(module)

    resolved = Resolver(module, imported_modules).resolve()
    typed = TypeChecker(resolved).check()
    return display_path, typed


# ---------------------------------------------------------------------------
# Multi-module pipeline
# ---------------------------------------------------------------------------

def _run_multi_pipeline(
    source_path: str,
) -> list[tuple[str, object, bool]]:
    """Run the full pipeline for a source file and all its transitive imports.

    Returns a list of ``(display_path, typed_module, is_root)`` tuples in
    dependency order (leaves first, root last).

    Fast path: if the root module has no user imports, delegates directly
    to ``_run_pipeline`` and avoids the graph machinery entirely.
    """
    root = Path(source_path)
    # Quick parse to check for user imports.
    root_source = root.read_text()
    root_display = _display_path(root)
    root_tokens = Lexer(root_source, root_display).tokenize()
    root_module = Parser(root_tokens, root_display).parse()

    if not _has_user_imports(root_module):
        # Fast path: single-file compilation.
        display, typed = _run_pipeline(source_path)
        return [(display, typed, True)]

    # Multi-module path.
    project_root = _infer_project_root(root.resolve(), root_module.path)
    topo_order = _build_dependency_graph(root.resolve(), project_root)

    # Resolve and type-check each module in topological order.
    # Accumulate ModuleScopes for downstream importers.
    available_scopes: dict[str, ModuleScope] = {}
    available_typed: dict[str, object] = {}
    results: list[tuple[str, object, bool]] = []

    root_key = topo_order[-1].module_key  # root is last in topo order

    for pm in topo_order:
        # Build imported_modules: stdlib + already-resolved user modules.
        imported = _discover_stdlib_imports(pm.module)
        for imp in _user_imports(pm.module):
            dep_key = ".".join(imp.path)
            if dep_key in available_scopes:
                imported[dep_key] = available_scopes[dep_key]

        # Collect typed modules for user imports so the typechecker can
        # resolve cross-module type references (e.g., http.HttpResponse).
        imported_typed: dict[str, object] = {}
        for imp in _user_imports(pm.module):
            dep_key = ".".join(imp.path)
            if dep_key in available_typed:
                imported_typed[dep_key] = available_typed[dep_key]

        resolved = Resolver(pm.module, imported).resolve()
        typed = TypeChecker(resolved, imported_typed).check()

        available_scopes[pm.module_key] = resolved.module_scope
        available_typed[pm.module_key] = typed

        is_root = (pm.module_key == root_key)
        results.append((pm.display_path, typed, is_root))

    return results


# ---------------------------------------------------------------------------
# Lowering + emitting helpers for multi-module
# ---------------------------------------------------------------------------

def _build_all_typed(
    modules: list[tuple[str, object, bool]],
) -> dict[str, object]:
    """Build all_typed dict: user modules + stdlib TypedModules for monomorphization.

    The stdlib entries use _get_stdlib_typed (cached), which ensures AST node
    identity is stable across Resolver and Lowerer (same parse, same objects).
    """
    all_typed: dict[str, object] = {}
    for _display_path, typed, _is_root in modules:
        mod_path = ".".join(typed.module.path) if typed.module.path else "main"  # type: ignore[attr-defined]
        all_typed[mod_path] = typed

    # Merge in stdlib TypedModules for cross-module generic monomorphization.
    for _display_path, typed, _is_root in modules:
        for imp in typed.module.imports:  # type: ignore[attr-defined]
            module_key = ".".join(imp.path)
            if module_key in _STDLIB_MODULES and module_key not in all_typed:
                try:
                    all_typed[module_key] = _get_stdlib_typed(module_key)
                except Exception:
                    pass  # non-fatal: monomorphization falls back to LType dispatch
    return all_typed


def _lower_and_emit_multi(
    modules: list[tuple[str, object, bool]],
    *,
    line_directives: bool = False,
) -> str:
    """Lower and emit C for a list of (display_path, typed_module, is_root).

    Dependency modules (is_root=False) are emitted without #include or main().
    The root module is emitted with the full header and entry point.
    Output structure: root_header + dep_code + root_body + root_entry_point.

    The root emitter's header is exactly 3 lines (comment, source, #include).
    We split its output after those 3 lines and insert dependency code there.
    """
    dep_parts: list[str] = []
    collected_static_inits: list[tuple[str, str]] = []
    dep_type_names: set[str] = set()

    all_typed = _build_all_typed(modules)

    # Lower and emit dependency modules (no header, no entry point).
    for display_path, typed, is_root in modules:
        if is_root:
            continue
        lmodule = Lowerer(typed, all_typed=all_typed).lower()
        for td in lmodule.type_defs:
            dep_type_names.add(td.c_name)
        emitter = Emitter(lmodule, display_path, is_root=False,
                          line_directives=line_directives)
        dep_parts.append(emitter.emit())
        collected_static_inits.extend(emitter.deferred_static_inits)

    # Lower and emit root module (with header and entry point).
    # Filter out type definitions already emitted by dependency modules.
    root_part = ""
    for display_path, typed, is_root in modules:
        if not is_root:
            continue
        lmodule = Lowerer(typed, all_typed=all_typed).lower()
        if dep_type_names:
            lmodule.type_defs = [
                td for td in lmodule.type_defs
                if td.c_name not in dep_type_names
            ]
        emitter = Emitter(
            lmodule, display_path, is_root=True,
            extra_static_inits=collected_static_inits,
            line_directives=line_directives)
        root_part = emitter.emit()
        break

    if not dep_parts:
        return root_part

    # Split root output after the 3-line header to insert dep code.
    pos = 0
    for _ in range(3):
        pos = root_part.index('\n', pos) + 1
    header = root_part[:pos]
    root_body = root_part[pos:]

    return header + "".join(dep_parts) + root_body


def compile_source(source_path: str, *, output: str | None = None,
                   verbose: bool = False,
                   line_directives: bool = True) -> int:
    """Run the full pipeline: lex → parse → resolve → typecheck → lower → emit → clang."""
    modules = _run_multi_pipeline(source_path)
    modules = _inject_compilable_stdlib(modules)

    if len(modules) == 1:
        # Single module fast path — still needs stdlib all_typed for mono.
        display_path, typed, _ = modules[0]
        all_typed = _build_all_typed(modules)
        lmodule = Lowerer(typed, all_typed=all_typed).lower()
        c_source = Emitter(lmodule, display_path,
                           line_directives=line_directives).emit()
    else:
        c_source = _lower_and_emit_multi(modules,
                                          line_directives=line_directives)

    if verbose:
        sys.stderr.write(c_source)

    # Collect extern lib names from all modules for linker flags.
    extern_libs: list[str] = []
    seen_libs: set[str] = set()
    for _, typed, _ in modules:
        for decl in typed.module.decls:
            if isinstance(decl, ExternLibDecl) and decl.lib_name not in seen_libs:
                extern_libs.append(decl.lib_name)
                seen_libs.add(decl.lib_name)

    # Determine output binary path.
    if output is None:
        output_path = str(Path(source_path).with_suffix(""))
    else:
        output_path = output

    # Locate runtime files relative to this module.
    compiler_root = Path(__file__).resolve().parent.parent
    runtime_c = compiler_root / "runtime" / "flow_runtime.c"
    runtime_include = compiler_root / "runtime"

    # Write C source to a temp file and invoke clang.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".c")
    try:
        os.write(tmp_fd, c_source.encode("utf-8"))
        os.close(tmp_fd)

        clang_cmd = [
            "clang", "-std=c11", "-Wall", "-Wextra",
            "-pthread",
            "-o", output_path,
            tmp_path,
            str(runtime_c),
            "-I", str(runtime_include),
            "-lm",
        ] + [f"-l{lib}" for lib in extern_libs]

        result = subprocess.run(
            clang_cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            return 1

        return 0
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_source(source_path: str, *, verbose: bool = False,
               args: list[str] | None = None,
               line_directives: bool = True) -> int:
    """Compile to a temp binary, run it, clean up."""
    tmp_fd, tmp_bin = tempfile.mkstemp(prefix="fl_run_")
    os.close(tmp_fd)
    try:
        rc = compile_source(source_path, output=tmp_bin, verbose=verbose,
                            line_directives=line_directives)
        if rc != 0:
            return rc
        try:
            result = subprocess.run([tmp_bin] + (args or []))
        except KeyboardInterrupt:
            return 130
        return result.returncode
    finally:
        try:
            os.unlink(tmp_bin)
        except OSError:
            pass


def emit_only(source_path: str, *, output: str | None = None,
              verbose: bool = False,
              line_directives: bool = False) -> int:
    """Run pipeline through emit, output C source."""
    modules = _run_multi_pipeline(source_path)
    modules = _inject_compilable_stdlib(modules)

    if len(modules) == 1:
        # Single module fast path — still needs stdlib all_typed for mono.
        display_path, typed, _ = modules[0]
        all_typed = _build_all_typed(modules)
        lmodule = Lowerer(typed, all_typed=all_typed).lower()
        c_source = Emitter(lmodule, display_path,
                           line_directives=line_directives).emit()
    else:
        c_source = _lower_and_emit_multi(modules,
                                          line_directives=line_directives)

    if output is not None:
        Path(output).write_text(c_source)
    else:
        sys.stdout.write(c_source)

    return 0


def check_only(source_path: str, *, verbose: bool = False) -> int:
    """Run pipeline through type checking only."""
    _run_multi_pipeline(source_path)
    return 0


# ---------------------------------------------------------------------------
# Lint-only pipeline
# ---------------------------------------------------------------------------

def lint_only(
    source_path: str,
    *,
    fix: bool = False,
    rules: list[str] | None = None,
    exclude: list[str] | None = None,
) -> int:
    """Run lex + parse + lint on a single file. Returns 0 if clean, 1 if issues."""
    from compiler.linter import (
        build_context, lint, apply_fixes, format_diagnostic,
        get_rules, LintRule,
    )
    from compiler.errors import LexError, ParseError

    path = Path(source_path)
    source = path.read_text()
    display = _display_path(path)

    # Lex — if lex fails, we can't lint at all.
    try:
        tokens = Lexer(source, display).tokenize()
    except LexError:
        raise

    # Parse — if parse fails, run token/source-level rules only.
    module = None
    try:
        module = Parser(tokens, display).parse()
    except ParseError:
        pass

    selected_rules = get_rules(include=rules, exclude=exclude)
    ctx = build_context(source, display, tokens, module)
    diags = lint(ctx, rules=selected_rules)

    if fix and diags:
        new_source = apply_fixes(source, diags)
        if new_source != source:
            path.write_text(new_source)
            # Re-lint after fix to report remaining issues.
            source = new_source
            try:
                tokens = Lexer(source, display).tokenize()
            except LexError:
                raise
            module = None
            try:
                module = Parser(tokens, display).parse()
            except ParseError:
                pass
            ctx = build_context(source, display, tokens, module)
            diags = lint(ctx, rules=selected_rules)

    for d in diags:
        print(format_diagnostic(d), file=sys.stderr)

    return 0 if not diags else 1
