#!/usr/bin/env python3
"""Post-process stage2.c to fix self-hosted compiler codegen issues."""
import re
import sys

def fix_stage2(path):
    with open(path) as f:
        text = f.read()

    # === PHASE 1: Cross-module type name fixes (MUST come first) ===
    text = text.replace('fl_self_hosted_emitter_LType', 'fl_self_hosted_lir_LType')
    text = text.replace('fl_self_hosted_emitter_LExpr', 'fl_self_hosted_lir_LExpr')
    text = text.replace('fl_self_hosted_emitter_LStmt', 'fl_self_hosted_lir_LStmt')
    text = text.replace('fl_self_hosted_emitter_lir', 'fl_self_hosted_lir')
    text = text.replace('fl_self_hosted_resolver_ast', 'fl_self_hosted_ast')
    text = text.replace('fl_self_hosted_resolver_TypeExpr', 'fl_self_hosted_ast_TypeExpr')
    text = text.replace('fl_self_hosted_resolver_Expr', 'fl_self_hosted_ast_Expr')
    text = text.replace('fl_self_hosted_resolver_Decl', 'fl_self_hosted_ast_Decl')
    text = text.replace('fl_self_hosted_typechecker_ast', 'fl_self_hosted_ast')
    text = text.replace('fl_self_hosted_lowering_ast', 'fl_self_hosted_ast')
    text = re.sub(r'\bfl_self_hosted_lowering_lir\b(?!_)', 'fl_self_hosted_lir', text)
    text = text.replace('fl_self_hosted_lowering_TCType', 'fl_self_hosted_typechecker_TCType')
    text = text.replace('fl_self_hosted_lowering_LExprBox', 'fl_self_hosted_lir_LExprBox')
    text = text.replace('fl_self_hosted_lowering_LType', 'fl_self_hosted_lir_LType')
    text = text.replace('fl_self_hosted_lowering_typechecker', 'fl_self_hosted_typechecker')
    text = text.replace('fl_self_hosted_typechecker_lir', 'fl_self_hosted_lir')
    text = text.replace('fl_self_hosted_parser_ast', 'fl_self_hosted_ast')
    text = text.replace('fl_self_hosted_parser_TypeExpr', 'fl_self_hosted_ast_TypeExpr')
    text = text.replace('fl_self_hosted_parser_Expr', 'fl_self_hosted_ast_Expr')
    text = text.replace('fl_self_hosted_parser_lexer', 'fl_self_hosted_lexer')
    text = text.replace('fl_self_hosted_driver_lir', 'fl_self_hosted_lir')
    text = text.replace('fl_self_hosted_driver_parser', 'fl_self_hosted_parser')
    text = text.replace('fl_self_hosted_driver_resolver', 'fl_self_hosted_resolver')
    text = text.replace('fl_self_hosted_driver_typechecker', 'fl_self_hosted_typechecker')
    text = text.replace('fl_self_hosted_typechecker_resolver', 'fl_self_hosted_resolver')
    text = text.replace('fl_self_hosted_lowering_Expr', 'fl_self_hosted_ast_Expr')
    text = text.replace('fl_self_hosted_lowering_TypeExpr', 'fl_self_hosted_ast_TypeExpr')
    text = text.replace('fl_self_hosted_lowering_Decl', 'fl_self_hosted_ast_Decl')
    text = text.replace('fl_self_hosted_lowering_Stmt', 'fl_self_hosted_ast_Stmt')
    # Module dots for all modules
    text = re.sub(r'\blexer->', r'fl_self_hosted_lexer_', text)
    text = re.sub(r'\blexer\.(\w)', r'fl_self_hosted_lexer_\1', text)
    # Module dots → underscores
    for mod in ['lir', 'ast', 'typechecker', 'resolver', 'lexer', 'parser', 'emitter', 'lowering', 'driver', 'mangler']:
        text = re.sub(rf'\bfl_self_hosted_{mod}\.(\w)', rf'fl_self_hosted_{mod}_\1', text)
    # lir->LVoid → compound literal
    text = text.replace('lir->LVoid', '(fl_self_hosted_lir_LType){.tag = 7}')

    # === PHASE 1b: Fix fl_box_new with wrong primitive type when actual value is ast.Expr/TypeExpr ===
    # Pattern: FL_Box* VAR = fl_box_new(sizeof(WRONG_TYPE));
    #          (*((WRONG_TYPE*)VAR->data)) = EXPR;
    # where EXPR is actually ast.Expr or ast.TypeExpr.
    # This happens when the self-hosted typechecker typed a field as TCAny.
    # Fix: replace sizeof(WRONG_TYPE) and cast type with the actual type.
    #
    # WRONG_TYPE can be fl_int, fl_bool, FL_String*, or FL_Array* (all primitive/non-struct types).
    lines_p1b = text.split('\n')
    for i in range(len(lines_p1b) - 1):
        # Match any primitive-typed boxing (fl_int, fl_bool, FL_String*, FL_Array*)
        m1 = re.match(
            r'^(\s+)FL_Box\* (\w+) = fl_box_new\(sizeof\((fl_int|fl_bool|FL_String\*|FL_Array\*|void\*)\)\);$',
            lines_p1b[i])
        if not m1:
            continue
        indent1, var, wrong_type = m1.group(1), m1.group(2), m1.group(3)
        # Escape the wrong type for the regex
        wrong_type_esc = re.escape(wrong_type)
        m2 = re.match(rf'^(\s+)\(\*\(\({wrong_type_esc}\*?\){re.escape(var)}->data\)\) = (\w[\w.]*);$', lines_p1b[i+1])
        if not m2:
            continue
        indent2, expr_var = m2.group(1), m2.group(2)
        # expr_var may be a simple var or a field access like stage0.call
        # Get the root variable name for lookup
        root_var = expr_var.split('.')[0]
        # Look backward for variable declaration to determine actual type
        # Use a wider window (80 lines) to catch declarations far back
        actual_type = None
        for k in range(max(0, i - 80), i):
            # Check for ast.Expr or ast.TypeExpr local declaration
            dm = re.match(rf'^\s+(fl_self_hosted_ast_Expr|fl_self_hosted_ast_TypeExpr) {re.escape(root_var)}\b', lines_p1b[k])
            if dm:
                actual_type = dm.group(1)
                break
            # Check for function parameter in function signature line (no leading indent)
            # Function signatures look like: RetType fn_name(... TypeName param_name [,)])
            pm = re.search(rf'\b(fl_self_hosted_ast_Expr|fl_self_hosted_ast_TypeExpr) {re.escape(root_var)}\b', lines_p1b[k])
            if pm and not lines_p1b[k].startswith(' '):
                actual_type = pm.group(1)
                break
            # Check for struct type with .call or .pool_size field (PipelineStage)
            dm2 = re.match(rf'^\s+(fl_self_hosted_ast_PipelineStage|fl_self_hosted_ast_\w+) {re.escape(root_var)}\b', lines_p1b[k])
            if dm2 and '.' in expr_var:
                # It's a field access — need to find the field type
                field_name = expr_var.split('.', 1)[1] if '.' in expr_var else ''
                if field_name in ('call', 'pool_size'):
                    actual_type = 'fl_self_hosted_ast_Expr'
                    break
        # Only fix if we found a struct type (not re-confirming a primitive)
        if actual_type and actual_type not in ('fl_int', 'fl_bool', 'FL_String*', 'FL_Array*'):
            lines_p1b[i] = f'{indent1}FL_Box* {var} = fl_box_new(sizeof({actual_type}));'
            lines_p1b[i+1] = f'{indent2}(*(({actual_type}*){var}->data)) = {expr_var};'
    text = '\n'.join(lines_p1b)

    # === PHASE 2: Match field name fixes ===
    field_renames = {
        '.LInt.w': '.LInt.width', '.LInt.s': '.LInt.is_signed',
        '.LFloat.w': '.LFloat.width',
        '.LStruct.cname': '.LStruct.c_name', '.LStruct.sname': '.LStruct.c_name',
        '.LSVarDecl.cname': '.LSVarDecl.c_name', '.LSVarDecl.ctype': '.LSVarDecl.c_type',
        '.LSVarDecl.init_expr': '.LSVarDecl.init', '.LSVarDecl.src_line': '.LSVarDecl.source_line',
        '.LSArrayDecl.cname': '.LSArrayDecl.c_name', '.LSArrayDecl.src_line': '.LSArrayDecl.source_line',
        '.LSReturn.has_val': '.LSReturn.has_value', '.LSReturn.val_expr': '.LSReturn.value',
        '.LSReturn.src_line': '.LSReturn.source_line',
        '.LSAssign.src_line': '.LSAssign.source_line',
        '.LSIf.src_line': '.LSIf.source_line',
        '.LSWhile.src_line': '.LSWhile.source_line',
        '.LSBlock.src_line': '.LSBlock.source_line',
        '.LSExprStmt.src_line': '.LSExprStmt.source_line',
        '.LSExprStmt.sline': '.LSExprStmt.source_line',
        '.LSSwitch.src_line': '.LSSwitch.source_line',
        '.LSGoto.src_line': '.LSGoto.source_line',
        '.LSLabel.src_line': '.LSLabel.source_line', '.LSLabel.label_name': '.LSLabel.name',
        '.LSBreak.src_line': '.LSBreak.source_line',
        '.LSContinue.src_line': '.LSContinue.source_line',
        '.LELit.ct': '.LELit.c_type', '.LEVar.ct': '.LEVar.c_type',
        '.LECall.ct': '.LECall.c_type',
        '.LEIndirectCall.ct': '.LEIndirectCall.c_type',
        '.LEBinOp.ct': '.LEBinOp.c_type',
        '.LEUnary.ct': '.LEUnary.c_type',
        '.LEFieldAccess.ct': '.LEFieldAccess.c_type',
        '.LEArrow.ct': '.LEArrow.c_type',
        '.LEIndex.ct': '.LEIndex.c_type',
        '.LECast.ct': '.LECast.c_type', '.LECast.cast_type': '.LECast.c_type',
        '.LEAddrOf.ct': '.LEAddrOf.c_type',
        '.LEDeref.ct': '.LEDeref.c_type',
        '.LECompound.ctype': '.LECompound.c_type',
        '.LECompound.fn_val': '.LECompound.field_names',
        '.LECompound.fv': '.LECompound.field_values',
        '.LECheckedArith.ct': '.LECheckedArith.c_type',
        '.LETernary.ct': '.LETernary.c_type',
        '.LEOptDerefAs.ct': '.LEOptDerefAs.c_type',
        '.LESizeOf.tt': '.LESizeOf.target_type',
        '.LEArrayData.et': '.LEArrayData.elem_type',
        '.LEArrayData.ct': '.LEArrayData.c_type',
        '.LExternFnProto.cname': '.LExternFnProto.c_name',
        '.LParam.ptype': '.LParam.param_type',
        '.LFnDef.cname': '.LFnDef.c_name',
        '.LFnDef.src_name': '.LFnDef.source_name',
        '.LFnDef.src_line': '.LFnDef.source_line',
        '.LTypeDef.cname': '.LTypeDef.c_name',
        '.LEnumDef.cname': '.LEnumDef.c_name',
        '.LField.ftype': '.LField.field_type',
        '.LEIndirectCall.fn_ptr_box': '.LEIndirectCall.fn_ptr',
        '.LEBinOp.left_box': '.LEBinOp.left',
        '.LEBinOp.right_box': '.LEBinOp.right',
        '.LEUnary.operand_box': '.LEUnary.operand',
        '.LEFieldAccess.obj_box': '.LEFieldAccess.obj',
        '.LEArrow.ptr_box': '.LEArrow.ptr_expr',
        '.LEIndex.arr_box': '.LEIndex.arr_expr',
        '.LEIndex.idx_box': '.LEIndex.idx_expr',
        '.LECast.inner_box': '.LECast.inner',
        '.LEAddrOf.inner_box': '.LEAddrOf.inner',
        '.LEDeref.inner_box': '.LEDeref.inner',
        '.LECheckedArith.left_box': '.LECheckedArith.left',
        '.LECheckedArith.right_box': '.LECheckedArith.right',
        '.LETernary.cond_box': '.LETernary.cond',
        '.LETernary.then_box': '.LETernary.then_expr',
        '.LETernary.else_box': '.LETernary.else_expr',
        '.LEOptDerefAs.inner_box': '.LEOptDerefAs.inner',
        '.LEVar.cname': '.LEVar.c_name',
        '.LECheckedArith.ctype': '.LECheckedArith.c_type',
        '.LECall.fn': '.LECall.fn_name',
        '.LEOptDerefAs.opt_type': '.LEOptDerefAs.c_type',
        '.LEOptDerefAs.vt': '.LEOptDerefAs.val_type',
        '.LEArrayData.ctype': '.LEArrayData.c_type',
    }
    for old, new in field_renames.items():
        pattern = re.escape(old) + r'(?![a-zA-Z_])'
        text = re.sub(pattern, new, text)

    # === PHASE 3: FL_BOX_DEREF for recursive fields ===
    LTYPE_BOX_FIELDS = {'inner', 'ret'}
    LEXPRBOX_FIELDS = {
        'fn_ptr', 'left', 'right', 'operand', 'obj', 'ptr_expr',
        'arr_expr', 'idx', 'inner', 'cond', 'then_expr', 'else_expr',
    }
    EXPR_BOX_FIELDS = {
        'left', 'right', 'operand', 'inner', 'callee', 'receiver',
        'condition', 'body', 'subject', 'then_expr', 'else_expr',
        'target', 'key', 'index', 'obj', 'ptr_expr',
        'arr_expr', 'idx', 'call', 'spread', 'fn_ptr',
        'cond', 'base', 'elem', 'value',
    }
    TYPE_EXPR_BOX_FIELDS = {
        'inner', 'base', 'ret', 'elem', 'underlying',
        'ok_type', 'err_type', 'yield_type', 'send_type',
    }
    TCTYPE_BOX_FIELDS = {
        'inner', 'elem', 'key', 'val', 'ret', 'ok_type', 'err_type',
        'yield_type', 'send_type', 'underlying',
    }

    # Variants where Expr fields are NOT recursive (stored by value, not FL_Box*)
    EXPR_NON_RECURSIVE_VARIANTS = {
        'SLet', 'SAssign', 'SUpdate', 'SReturn', 'SExpr', 'SThrow',
        'SIf', 'SWhile', 'SFor', 'SYield', 'STry', 'SMatch', 'SBreak', 'SContinue',
        'DFn', 'DModule', 'DType', 'DEnum', 'DImport', 'DExternFn', 'DExternType',
        'DExternLib', 'DInterface', 'DAlias', 'DStaticMember', 'DConstructor',
        'MatchArm', 'CatchClause', 'FPExpr', 'ExprField',
    }

    def box_deref(match):
        type_name = match.group(1)
        var_name = match.group(2)
        expr = match.group(3)
        variant = match.group(4)
        field = match.group(5)
        is_box = False
        if 'lir_LType' in type_name and field in LTYPE_BOX_FIELDS:
            is_box = True
        elif 'lir_LExprBox' in type_name and field in LEXPRBOX_FIELDS:
            is_box = True
        elif 'ast_Expr' in type_name and 'ast_ExprField' not in type_name and field in EXPR_BOX_FIELDS:
            if variant not in EXPR_NON_RECURSIVE_VARIANTS:
                is_box = True
        elif 'ast_TypeExpr' in type_name and field in TYPE_EXPR_BOX_FIELDS:
            is_box = True
        elif 'typechecker_TCType' in type_name and field in TCTYPE_BOX_FIELDS:
            is_box = True
        if is_box:
            return f'{type_name} {var_name} = FL_BOX_DEREF({expr}.{variant}.{field}, {type_name});'
        return match.group(0)

    pattern = r'(fl_self_hosted_\w+) (\w+) = ([^;]+)\.([A-Z]\w+)\.(\w+);'
    text = re.sub(pattern, box_deref, text)

    # void* box fields → LExprBox
    def void_box_deref(match):
        var_name = match.group(1)
        expr = match.group(2)
        variant = match.group(3)
        field = match.group(4)
        if field in LEXPRBOX_FIELDS:
            return f'fl_self_hosted_lir_LExprBox {var_name} = FL_BOX_DEREF({expr}.{variant}.{field}, fl_self_hosted_lir_LExprBox);'
        return match.group(0)
    text = re.sub(r'void\* (\w+) = ([^;]+)\.([A-Z]\w+)\.(\w+);', void_box_deref, text)

    # Fix double FL_BOX_DEREF
    text = re.sub(
        r'FL_BOX_DEREF\(FL_BOX_DEREF\(([^)]+), ([^)]+)\), \2\)',
        r'FL_BOX_DEREF(\1, \2)', text)

    # === PHASE 4: :mut forwarding ===
    text = re.sub(
        r'fl_self_hosted_emitter_(\w+)\(\(\*st\)',
        r'fl_self_hosted_emitter_\1(st', text)

    # === PHASE 4a: Comprehensive void* match-bound variable fix ===
    # Use field name to determine the correct C type
    INT_FIELDS = {
        'id', 'line', 'col', 'width', 'count', 'suffix', 'target_id',
        'value_id', 'source_line', 'decl_id', '_pad',
    }
    BOOL_FIELDS = {
        'is_signed', 'is_pure', 'is_variadic', 'is_export', 'is_static',
        'is_mut', 'is_sum_type', 'has_return_type', 'has_finally',
        'has_value', 'has_type_ann', 'has_init', 'has_else', 'has_spread',
        'has_var_type', 'has_fields', 'is_parallel', 'has_entry_point',
        'has_current_ret_type',
    }
    STRING_FIELDS = {
        'name', 'path', 'c_name', 'op', 'label', 'field', 'method',
        'module_path', 'variant_name', 'inner_var', 'mod_path',
        'type_name', 'var_name', 'value_text', 'import_alias', 'lib_name',
        'fn_name', 'source_name', 'mangled_name', 'src_module',
        'entry_point', 'kind', 'c_name',
    }
    ARRAY_FIELDS = {
        'params', 'body', 'elements', 'fields', 'args', 'type_params',
        'methods', 'constructors', 'variants', 'static_members', 'names',
        'then_stmts', 'else_stmts', 'catches', 'retry_blocks', 'finally_body',
        'arms', 'parts', 'stages', 'branches', 'interfaces', 'stmts',
        'case_tags', 'case_bodies', 'default_body', 'variant_names',
        'variant_values', 'field_names', 'field_types', 'type_args',
        'field_types_box', 'param_types', 'body_stmts', 'fn_defs',
        'type_defs', 'static_defs', 'enum_defs', 'extern_fn_protos',
        'type_env_keys', 'type_env_vals', 'field_values',
    }
    # Specific Variant.field → type overrides (for ambiguous field names)
    SPECIFIC_FIELD_TYPES = {
        'EIntLit.value': 'fl_int',
        'EBoolLit.value': 'fl_bool',
        'EStringLit.value': 'FL_String*',
        'ECharLit.value': 'FL_String*',
        'EFloatLit.value_text': 'FL_String*',
        'FPExpr.expr': 'fl_self_hosted_ast_Expr',
        'FPText.text': 'FL_String*',
        'DConstructor.return_type': 'fl_self_hosted_ast_TypeExpr',
        'DConstructor.body': 'FL_Array*',
        'MatchArm.pattern': 'fl_self_hosted_ast_Pattern',
        'CatchClause.exception_type': 'fl_self_hosted_ast_TypeExpr',
        'CatchClause.body': 'FL_Array*',
        'ChainElement.expr': 'fl_self_hosted_ast_Expr',
        'DFn.return_type': 'fl_self_hosted_ast_TypeExpr',
        'DExternFn.return_type': 'fl_self_hosted_ast_TypeExpr',
        'DStaticMember.type_ann': 'fl_self_hosted_ast_TypeExpr',
        'DStaticMember.value': 'fl_self_hosted_ast_Expr',
        'DAlias.type_expr': 'fl_self_hosted_ast_TypeExpr',
        'DAlias.target': 'fl_self_hosted_ast_TypeExpr',
        'SLet.type_ann': 'fl_self_hosted_ast_TypeExpr',
        'SLet.value': 'fl_self_hosted_ast_Expr',
        'SFor.type_ann': 'fl_self_hosted_ast_TypeExpr',
        'SFor.iterable': 'fl_self_hosted_ast_Expr',
        'SFor.var_type': 'fl_self_hosted_ast_TypeExpr',
        'SThrow.value': 'fl_self_hosted_ast_Expr',
        'SThrow.exception': 'fl_self_hosted_ast_Expr',
        'SUpdate.target': 'fl_self_hosted_ast_Expr',
        'SUpdate.value': 'fl_self_hosted_ast_Expr',
        'SUpdate.op': 'FL_String*',
        'SAssign.target': 'fl_self_hosted_ast_Expr',
        'SAssign.value': 'fl_self_hosted_ast_Expr',
        'SReturn.value': 'fl_self_hosted_ast_Expr',
        'SExpr.expr': 'fl_self_hosted_ast_Expr',
        'SIf.condition': 'fl_self_hosted_ast_Expr',
        'SWhile.condition': 'fl_self_hosted_ast_Expr',
        'SMatch.subject': 'fl_self_hosted_ast_Expr',
        'SYield.value': 'fl_self_hosted_ast_Expr',
        'TCAlias.underlying': 'fl_self_hosted_typechecker_TCType',
        'LSVarDecl.init': 'fl_self_hosted_lir_LExpr',
        'LSVarDecl.c_type': 'fl_self_hosted_lir_LType',
        'LSArrayDecl.elem_type': 'fl_self_hosted_lir_LType',
        'LSAssign.target': 'fl_self_hosted_lir_LExpr',
        'LSAssign.value': 'fl_self_hosted_lir_LExpr',
        'LSReturn.value': 'fl_self_hosted_lir_LExpr',
        'LSIf.cond': 'fl_self_hosted_lir_LExpr',
        'LSWhile.cond': 'fl_self_hosted_lir_LExpr',
        'LSExprStmt.expr': 'fl_self_hosted_lir_LExpr',
        'LSSwitch.value': 'fl_self_hosted_lir_LExpr',
        'LFnDef.ret': 'fl_self_hosted_lir_LType',
        'LExternFnProto.ret': 'fl_self_hosted_lir_LType',
        'LStaticDef.c_type': 'fl_self_hosted_lir_LType',
        'LStaticDef.init': 'fl_self_hosted_lir_LExpr',
        'LField.field_type': 'fl_self_hosted_lir_LType',
        'LParam.param_type': 'fl_self_hosted_lir_LType',
    }

    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'void* ' not in line:
            continue
        # Match: void* var = expr.Variant.field;
        m = re.match(r'^(\s+)void\* (\w+) = (.+)\.([A-Z]\w+)\.(\w+);$', line)
        if m:
            indent, var, expr, variant, field = m.groups()
            vf_key = f'{variant}.{field}'
            if vf_key in SPECIFIC_FIELD_TYPES:
                ctype = SPECIFIC_FIELD_TYPES[vf_key]
                lines[i] = f'{indent}{ctype} {var} = {expr}.{variant}.{field};'
                continue
            if field in INT_FIELDS:
                lines[i] = f'{indent}fl_int {var} = {expr}.{variant}.{field};'
                continue
            if field in BOOL_FIELDS:
                lines[i] = f'{indent}fl_bool {var} = {expr}.{variant}.{field};'
                continue
            if field in STRING_FIELDS:
                lines[i] = f'{indent}FL_String* {var} = {expr}.{variant}.{field};'
                continue
            if field in ARRAY_FIELDS:
                lines[i] = f'{indent}FL_Array* {var} = {expr}.{variant}.{field};'
                continue
            continue
        # Match: void* var = structvar.field; (non-variant field access)
        m2 = re.match(r'^(\s+)void\* (\w+) = (.+)\.(\w+);$', line)
        if m2 and '_fl_tmp_' in line:
            indent, var, expr, field = m2.groups()
            # Check if field name maps to a known type
            if field == 'pattern':
                lines[i] = f'{indent}fl_self_hosted_ast_Pattern {var} = {expr}.{field};'
            elif field in INT_FIELDS:
                lines[i] = f'{indent}fl_int {var} = {expr}.{field};'
            elif field in BOOL_FIELDS:
                lines[i] = f'{indent}fl_bool {var} = {expr}.{field};'
            elif field in STRING_FIELDS:
                lines[i] = f'{indent}FL_String* {var} = {expr}.{field};'
            elif field in ARRAY_FIELDS:
                lines[i] = f'{indent}FL_Array* {var} = {expr}.{field};'
            elif field == 'type_ann':
                lines[i] = f'{indent}fl_self_hosted_ast_TypeExpr {var} = {expr}.{field};'
            elif field == 'return_type':
                lines[i] = f'{indent}fl_self_hosted_ast_TypeExpr {var} = {expr}.{field};'
    text = '\n'.join(lines)

    # === PHASE 4a2: Fix missing match destructuring for Pattern ===
    # After "fl_self_hosted_ast_Pattern _fl_tmp_N = arm.pattern;", insert field extractions.
    # Context-dependent: check the function name to determine which variant fields to extract.
    # Only expands if the extracted variables are actually used in the next ~15 lines
    # (prevents redefinition errors when arm.pattern appears in multiple while-loop bodies
    # at the same scope level, e.g., check_exhaustiveness has 4 such occurrences but only
    # one actually uses vname/bindings/pline).
    lines = text.split('\n')
    for i, line in enumerate(lines):
        m = re.match(r'^(\s+)fl_self_hosted_ast_Pattern (_fl_tmp_\d+) = arm\.pattern;$', line)
        if not m:
            continue
        indent = m.group(1)
        tmp = m.group(2)
        # Determine function context by looking backwards for the function comment
        fn_name = ''
        for k in range(max(0, i - 30), i):
            if '/* Flow:' in lines[k]:
                fn_name = lines[k]
                break
        if 'lower_match_sum' in fn_name or 'check_exhaustiveness' in fn_name:
            # Only inject vname/bindings/pline if they are actually referenced nearby
            lookahead = '\n'.join(lines[i+1:i+25])
            if 'vname' not in lookahead and 'bindings' not in lookahead and 'pline' not in lookahead:
                continue
            # Skip if the Python compiler already generated these declarations directly
            next3 = '\n'.join(lines[i+1:i+4])
            if f'{tmp}.PVariant.variant_name' in next3 or 'FL_String* vname' in next3:
                continue
            # PVariant: extract variant_name, bindings, line
            lines[i] = (f'{indent}fl_self_hosted_ast_Pattern {tmp} = arm.pattern;\n'
                        f'{indent}FL_String* vname = {tmp}.PVariant.variant_name;\n'
                        f'{indent}FL_Array* bindings = {tmp}.PVariant.bindings;\n'
                        f'{indent}fl_int pline = {tmp}.PVariant.line;')
        elif 'lower_match_option' in fn_name:
            # Only inject inner_var/pline if they are actually referenced nearby
            lookahead = '\n'.join(lines[i+1:i+25])
            if 'inner_var' not in lookahead and 'pline' not in lookahead:
                continue
            # Skip if the Python compiler already generated these declarations directly
            next2 = '\n'.join(lines[i+1:i+3])
            if f'{tmp}.PSome.inner_var' in next2 or f'FL_String* inner_var' in next2:
                continue
            # PSome: extract inner_var, line
            lines[i] = (f'{indent}fl_self_hosted_ast_Pattern {tmp} = arm.pattern;\n'
                        f'{indent}FL_String* inner_var = {tmp}.PSome.inner_var;\n'
                        f'{indent}fl_int pline = {tmp}.PSome.line;')
        elif 'lower_match_result' in fn_name:
            # Only inject inner_var/pline if they are actually referenced nearby
            lookahead = '\n'.join(lines[i+1:i+25])
            if 'inner_var' not in lookahead and 'pline' not in lookahead:
                continue
            # Skip if the Python compiler already generated these declarations directly
            next2 = '\n'.join(lines[i+1:i+3])
            if f'{tmp}.POk.inner_var' in next2 or f'FL_String* inner_var' in next2:
                continue
            # POk/PErr: extract inner_var, line
            lines[i] = (f'{indent}fl_self_hosted_ast_Pattern {tmp} = arm.pattern;\n'
                        f'{indent}FL_String* inner_var = {tmp}.POk.inner_var;\n'
                        f'{indent}fl_int pline = {tmp}.POk.line;')
    text = '\n'.join(lines)

    # === PHASE 4a4: Fix missing ok_t/err_t from TCResult match in lower_ok_expr/lower_err_expr ===
    # Pattern: fl_self_hosted_typechecker_TCType _fl_tmp_N = (*st).current_ret_type;
    #          result_lt = ..._lower_result_type(st, ok_t, err_t);
    # The TCResult match was not generated, so ok_t/err_t are undeclared.
    # Fix: after the TCType assignment, insert TCResult field extraction
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'fl_self_hosted_typechecker_TCType' in line and 'current_ret_type;' in line:
            m = re.match(r'^(\s+)fl_self_hosted_typechecker_TCType (_fl_tmp_\d+) = \(\*st\)\.current_ret_type;', line)
            if not m:
                continue
            indent = m.group(1)
            tmp = m.group(2)
            # Check if ok_t or err_t are used later without declaration
            found_ok_t = False
            for j in range(i + 1, min(i + 5, len(lines))):
                if 'ok_t' in lines[j] or 'err_t' in lines[j]:
                    found_ok_t = True
                    break
            if found_ok_t:
                insert = (f'\n{indent}fl_self_hosted_typechecker_TCType ok_t = FL_BOX_DEREF({tmp}.TCResult.ok_type, fl_self_hosted_typechecker_TCType);'
                          f'\n{indent}fl_self_hosted_typechecker_TCType err_t = FL_BOX_DEREF({tmp}.TCResult.err_type, fl_self_hosted_typechecker_TCType);')
                lines[i] = line + insert
    text = '\n'.join(lines)

    # === PHASE 4b: Fix array.push_ptr with struct values ===
    push_counter = [0]
    def fix_push_ptr(match):
        full = match.group(0)
        indent = match.group(1)
        arr_assign = match.group(2)
        arr_var = match.group(3)
        void_expr = match.group(4)
        if '(' in void_expr:
            stype = None
            if '_le_box(' in void_expr:
                stype = 'fl_self_hosted_lir_LExprBox'
            elif '_ls_box(' in void_expr:
                stype = 'fl_self_hosted_lir_LStmtBox'
            elif '_tc_box(' in void_expr:
                stype = 'fl_self_hosted_typechecker_TCTypeBox'
            elif '_lt_box(' in void_expr:
                stype = 'fl_self_hosted_lir_LTypeBox'
            elif 'make_symbol(' in void_expr or 'symbol_with_type(' in void_expr or 'symbol_no_type(' in void_expr:
                stype = 'fl_self_hosted_resolver_Symbol'
            elif 'copy_symbol(' in void_expr or 'lookup_or_error(' in void_expr:
                stype = 'fl_self_hosted_resolver_Symbol'
            elif 'resolver_ModuleScope' in void_expr or 'build_module_scope(' in void_expr:
                stype = 'fl_self_hosted_resolver_ModuleScope'
            elif 'typechecker_TypeInfo' in void_expr or 'default_type_info(' in void_expr:
                stype = 'fl_self_hosted_typechecker_TypeInfo'
            elif 'typechecker_InterfaceInfo' in void_expr or 'default_interface_info(' in void_expr:
                stype = 'fl_self_hosted_typechecker_InterfaceInfo'
            elif 'typechecker_TypedModule' in void_expr or 'typecheck(' in void_expr:
                stype = 'fl_self_hosted_typechecker_TypedModule'
            elif 'ast_Module' in void_expr or 'make_module(' in void_expr:
                stype = 'fl_self_hosted_ast_Module'
            elif 'ast_Decl' in void_expr:
                stype = 'fl_self_hosted_ast_Decl'
            if stype is not None:
                push_counter[0] += 1
                tmp = f'_push_tmp_{push_counter[0]}'
                return (f'{indent}{stype} {tmp} = {void_expr};\n'
                        f'{indent}{arr_assign}fl_array_push_sized({arr_var}, &{tmp}, sizeof({stype}));')
        m_cl = re.match(r'\(fl_self_hosted_(\w+)\)\{', void_expr)
        if m_cl:
            stype = 'fl_self_hosted_' + m_cl.group(1)
            push_counter[0] += 1
            tmp = f'_push_tmp_{push_counter[0]}'
            return (f'{indent}{stype} {tmp} = {void_expr};\n'
                    f'{indent}{arr_assign}fl_array_push_sized({arr_var}, &{tmp}, sizeof({stype}));')
        return full

    text = re.sub(
        r'^(\s+)((\w+) = )fl_array_push_ptr\(\3, \(\(void\*\)(.*)\)\);$',
        fix_push_ptr,
        text,
        flags=re.MULTILINE
    )

    # === PHASE 4b2: Fix fl_map_set_str with struct values ===
    map_set_counter = [0]
    lines2 = text.split('\n')
    for i, line in enumerate(lines2):
        if 'fl_map_set_str(' not in line:
            continue
        idx = line.find('fl_map_set_str(')
        if idx < 0:
            continue
        paren_depth = 0
        last_comma = -1
        end_paren = -1
        for j in range(idx, len(line)):
            if line[j] == '(':
                paren_depth += 1
            elif line[j] == ')':
                paren_depth -= 1
                if paren_depth == 0:
                    end_paren = j
                    break
            elif line[j] == ',' and paren_depth == 1:
                last_comma = j
        if last_comma < 0 or end_paren < 0:
            continue
        val_part = line[last_comma+1:end_paren].strip()
        indent = line[:len(line) - len(line.lstrip())]
        stype = None
        val_stripped = val_part.strip()
        if val_stripped in ('sym', 'rsym', 'msym', 'ns_sym', 'es', 'cs', 'exported', 'isym', 'ssym'):
            stype = 'fl_self_hosted_resolver_Symbol'
        elif 'symbol_with_type(' in val_stripped or 'symbol_no_type(' in val_stripped or 'make_symbol(' in val_stripped or 'copy_symbol_with_mk(' in val_stripped:
            stype = 'fl_self_hosted_resolver_Symbol'
        elif val_stripped.startswith('(fl_self_hosted_'):
            stype = val_stripped.split(')')[0][1:]
        elif val_stripped in ('info', 'type_info', 'ti'):
            stype = 'fl_self_hosted_typechecker_TypeInfo'
        elif val_stripped in ('iface_info', 'ii'):
            stype = 'fl_self_hosted_typechecker_InterfaceInfo'
        elif val_stripped in ('scope', 'mod_scope'):
            stype = 'fl_self_hosted_resolver_ModuleScope'
        elif 'default_type_info(' in val_stripped or '_TypeInfo)' in val_stripped:
            stype = 'fl_self_hosted_typechecker_TypeInfo'
        elif 'default_interface_info(' in val_stripped or '_InterfaceInfo)' in val_stripped:
            stype = 'fl_self_hosted_typechecker_InterfaceInfo'
        elif '_ModuleScope)' in val_stripped or 'build_module_scope(' in val_stripped or 'load_stdlib_scope(' in val_stripped:
            stype = 'fl_self_hosted_resolver_ModuleScope'
        elif '_TypedModule)' in val_stripped or 'typecheck(' in val_stripped:
            stype = 'fl_self_hosted_typechecker_TypedModule'
        elif '_Module)' in val_stripped or 'make_module(' in val_stripped:
            stype = 'fl_self_hosted_ast_Module'
        elif 'tc_box(' in val_stripped or 'TCTypeBox{' in val_stripped:
            stype = 'fl_self_hosted_typechecker_TCTypeBox'
        elif 'Decl)' in val_stripped:
            stype = 'fl_self_hosted_ast_Decl'
        # Check struct field access: dep_typed.resolved.mod_scope, dep_typed.src_module, etc.
        if not stype and '.' in val_stripped:
            last_part = val_stripped.rsplit('.', 1)[-1]
            if last_part in ('mod_scope',):
                stype = 'fl_self_hosted_resolver_ModuleScope'
            elif last_part in ('src_module',):
                stype = 'fl_self_hosted_ast_Module'
            elif last_part in ('is_mut', 'is_pure', 'is_export', 'is_static'):
                stype = 'fl_bool'
        # Check for function calls that return known struct types
        if not stype:
            if 'lt_box(' in val_stripped:
                stype = 'fl_self_hosted_lir_LTypeBox'
            elif 'tc_box(' in val_stripped:
                stype = 'fl_self_hosted_typechecker_TCTypeBox'
            elif 'le_box(' in val_stripped:
                stype = 'fl_self_hosted_lir_LExprBox'
            elif 'empty_iface_info(' in val_stripped or 'iface_info' in val_stripped.lower():
                stype = 'fl_self_hosted_typechecker_InterfaceInfo'
        # Check for variable names that are known struct types
        if not stype:
            if val_stripped in ('typed', 'dep_typed'):
                stype = 'fl_self_hosted_typechecker_TypedModule'
            elif val_stripped in ('mod', 'ast_mod'):
                stype = 'fl_self_hosted_ast_Module'
            elif val_stripped in ('vs',):
                stype = 'fl_self_hosted_resolver_Symbol'
            elif val_stripped in ('d',):
                stype = 'fl_self_hosted_ast_Decl'
            elif val_stripped in ('exc_info', 'cmp_info', 'hash_info', 'iter_info',
                                  'str_info', 'disp_info', 'idx_info', 'iinfo',
                                  'num_info', 'eq_info', 'show_info'):
                stype = 'fl_self_hosted_typechecker_InterfaceInfo'
            elif val_stripped in ('boxed',):
                stype = 'fl_self_hosted_typechecker_TCTypeBox'
            elif val_stripped in ('is_pure', 'is_mut', 'fl_true', 'fl_false'):
                stype = 'fl_bool'
            elif val_stripped in ('i', 'idx', 'depth'):
                stype = 'fl_int'
        if stype:
            map_set_counter[0] += 1
            tmp = f'_map_tmp_{map_set_counter[0]}'
            # Heap-allocate ALL map values to prevent stack-use-after-return
            new_line = (f'{indent}{stype}* {tmp} = ({stype}*)malloc(sizeof({stype}));\n'
                       f'{indent}*{tmp} = {val_part};\n'
                       f'{indent}{line[:last_comma+1]} {tmp}{line[end_paren:]}')
            lines2[i] = new_line
    text = '\n'.join(lines2)

    # === PHASE 4b3: Fix ternary void* vs struct operands ===
    def fix_ternary(match):
        stype = match.group(1)
        var = match.group(2)
        cond = match.group(3)
        tmp_val = match.group(4)
        fallback = match.group(5)
        return f'{stype} {var} = ({cond}) ? *(({stype}*)&({tmp_val})) : {fallback};'

    text = re.sub(
        r'(fl_self_hosted_\w+) (\w+) = \((\([^)]+\)) \? (_fl_tmp_\d+\.value) : (\([^;]+)\);',
        fix_ternary,
        text
    )
    def fix_void_ternary(match):
        var = match.group(1)
        cond = match.group(2)
        tmp_val = match.group(3)
        fallback = match.group(4)
        if 'fl_self_hosted_' in fallback:
            stype = None
            for name, typ in [
                ('SumVariantDecl', 'fl_self_hosted_ast_SumVariantDecl'),
                ('EnumVariantDecl', 'fl_self_hosted_ast_EnumVariantDecl'),
                ('ExprField', 'fl_self_hosted_ast_ExprField'),
                ('FieldDecl', 'fl_self_hosted_ast_FieldDecl'),
                ('Field{', 'fl_self_hosted_ast_Field'),
                ('Param{', 'fl_self_hosted_ast_Param'),
                ('CatchClause', 'fl_self_hosted_ast_CatchClause'),
                ('ChainElement', 'fl_self_hosted_ast_ChainElement'),
                ('TypeParam', 'fl_self_hosted_ast_TypeParam'),
                ('MonoSite', 'fl_self_hosted_lir_MonoSite'),
                ('LExternFnProto', 'fl_self_hosted_lir_LExternFnProto'),
                ('LParam', 'fl_self_hosted_lir_LParam'),
                ('LField', 'fl_self_hosted_lir_LField'),
                ('LTypeDef', 'fl_self_hosted_lir_LTypeDef'),
                ('LFnDef', 'fl_self_hosted_lir_LFnDef'),
                ('LEnumDef', 'fl_self_hosted_lir_LEnumDef'),
                ('tc_box(', 'fl_self_hosted_typechecker_TCTypeBox'),
                ('lt_box(', 'fl_self_hosted_lir_LTypeBox'),
                ('le_box(', 'fl_self_hosted_lir_LExprBox'),
                ('ls_box(', 'fl_self_hosted_lir_LStmtBox'),
                ('placeholder_stmt(', 'fl_self_hosted_lir_LStmtBox'),
                ('LStmtBox', 'fl_self_hosted_lir_LStmtBox'),
                ('TCTypeBox', 'fl_self_hosted_typechecker_TCTypeBox'),
                ('LTypeBox', 'fl_self_hosted_lir_LTypeBox'),
                ('LExprBox', 'fl_self_hosted_lir_LExprBox'),
                ('make_module(', 'fl_self_hosted_ast_Module'),
                ('Symbol', 'fl_self_hosted_resolver_Symbol'),
                ('ModuleScope', 'fl_self_hosted_resolver_ModuleScope'),
                ('TypeInfo', 'fl_self_hosted_typechecker_TypeInfo'),
                ('InterfaceInfo', 'fl_self_hosted_typechecker_InterfaceInfo'),
                ('TypedModule', 'fl_self_hosted_typechecker_TypedModule'),
            ]:
                if name in fallback:
                    stype = typ
                    break
            if stype:
                return f'{stype} {var} = ({cond}) ? *(({stype}*)&({tmp_val})) : {fallback};'
        return match.group(0)

    text = re.sub(
        r'void\* (\w+) = \((\([^)]+\)) \? (_fl_tmp_\d+\.value) : (fl_self_hosted_[^;]+)\);',
        fix_void_ternary,
        text
    )
    text = re.sub(
        r'void\* (\w+) = \(\((_fl_tmp_\d+)\.tag == \d+\)\) \? \2\.value : (fl_self_hosted_[^;]+)\);',
        lambda m: fix_void_ternary(type('', (), {
            'group': lambda self, n=0: {
                0: m.group(0), 1: m.group(1),
                2: f'(({m.group(2)}.tag == 1))',
                3: f'{m.group(2)}.value', 4: m.group(3)
            }.get(n, '')
        })()),
        text
    )
    # IMPORTANT: Skip parameter names that are always pointers (:mut params).
    # 'st' is always a LowerState* parameter in lowering functions — never a struct value.
    # 'ds' is always a DriverState* parameter in driver functions.
    _POINTER_PARAMS = {'st', 's', 'ds'}
    for m in re.finditer(r'(fl_self_hosted_\w+) (\w+) = \(.*\?\s+\*\(\(', text):
        var_name = m.group(2)
        if var_name in _POINTER_PARAMS:
            continue
        text = re.sub(rf'\b{var_name}->', f'{var_name}.', text)

    # Broader fix: TypeName var = ((cond) ? _fl_tmp.value : fallback);
    # where _fl_tmp.value is void* but TypeName is a struct
    # Need to check if _fl_tmp is FL_Option_ptr (deref pointer) or typed option (reinterpret value)
    lines_for_ternary = text.split('\n')
    for i, line in enumerate(lines_for_ternary):
        m = re.match(r'^(\s+)(fl_self_hosted_\w+) (\w+) = \(\((_fl_tmp_\d+)\.tag == (\d+)\) \? \4\.value : ([^;]+)\);$', line)
        if not m:
            continue
        indent, stype, var, tmp, tag_val, fallback = m.groups()
        # Check if tmp is FL_Option_ptr
        is_option_ptr = False
        for k in range(max(0, i - 5), i):
            if f'FL_Option_ptr {tmp}' in lines_for_ternary[k]:
                is_option_ptr = True
                break
        if is_option_ptr:
            lines_for_ternary[i] = f'{indent}{stype} {var} = (({tmp}.tag == {tag_val})) ? *(({stype}*)({tmp}.value)) : {fallback};'
        else:
            lines_for_ternary[i] = f'{indent}{stype} {var} = (({tmp}.tag == {tag_val})) ? *(({stype}*)&({tmp}.value)) : {fallback};'
    text = '\n'.join(lines_for_ternary)

    # Comprehensive ternary fix: void* var = ((tmp.tag == N) ? tmp.value : fallback);
    # Detect type from fallback expression
    DEFAULT_FN_TYPES = {
        'default_sum_variant': 'fl_self_hosted_ast_SumVariantDecl',
        'default_enum_variant': 'fl_self_hosted_ast_EnumVariantDecl',
        'default_field_decl': 'fl_self_hosted_ast_FieldDecl',
        'default_expr_field': 'fl_self_hosted_ast_ExprField',
        'default_catch_clause': 'fl_self_hosted_ast_CatchClause',
        'default_type_info': 'fl_self_hosted_typechecker_TypeInfo',
        'default_interface_info': 'fl_self_hosted_typechecker_InterfaceInfo',
    }
    lines = text.split('\n')
    fixed_vars = set()
    for i, line in enumerate(lines):
        m = re.match(r'^(\s+)void\* (\w+) = \(\((_fl_tmp_\d+)\.tag == \d+\) \? \3\.value : (.+)\);$', line)
        if not m:
            continue
        indent, var, tmp, fallback = m.groups()
        stype = None
        for fn, typ in DEFAULT_FN_TYPES.items():
            if fn + '(' in fallback:
                stype = typ
                break
        if not stype:
            cl = re.match(r'\(fl_self_hosted_(\w+)\)\{', fallback)
            if cl:
                stype = 'fl_self_hosted_' + cl.group(1)
        if stype:
            # Check if tmp is FL_Option_ptr (value is void* pointer) or typed option (value is inline struct)
            is_option_ptr = False
            for k in range(max(0, i - 5), i):
                if f'FL_Option_ptr {tmp}' in lines[k]:
                    is_option_ptr = True
                    break
            if is_option_ptr:
                # .value is void*, dereference the pointer: *(Type*)(tmp.value)
                lines[i] = f'{indent}{stype} {var} = (({tmp}.tag == 1)) ? *(({stype}*)({tmp}.value)) : {fallback};'
            else:
                lines[i] = f'{indent}{stype} {var} = (({tmp}.tag == 1)) ? *(({stype}*)&({tmp}.value)) : {fallback};'
            fixed_vars.add(var)
    text = '\n'.join(lines)
    for var in fixed_vars:
        if var in _POINTER_PARAMS:
            continue
        text = re.sub(rf'\b{var}->', f'{var}.', text)

    # === PHASE 4c: void* compound literals ===
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if '(void*){' not in line:
            continue
        if 'tc_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        if 'lt_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_lir_LType){')
            continue
        if 'le_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_lir_LExpr){')
            continue
        # Check for .fieldname = (void*){...} where field type differs from enclosing struct
        if '.current_return_type = (void*){' in line or '.return_type = (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        if '.sum_type_box = (void*){' in line or '.enum_type_box = (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        m_init = re.match(r'\s+(fl_self_hosted_\w+) \w+ = ', line)
        if m_init:
            target_type = m_init.group(1)
            # Don't use the enclosing type for nested compound literals if it's TCState
            # Instead, use TCType for any tag-based compound literals inside struct initializers
            if target_type == 'fl_self_hosted_typechecker_TCState':
                # Multiple (void*){} in this line — need context-aware replacement
                # Replace all (void*){.tag = N} with (TCType){.tag = N}
                lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            else:
                lines[i] = line.replace('(void*){', f'({target_type}){{')
            continue
        if '.tc = (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        if '.le = (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_lir_LExpr){')
            continue
        if 'return (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        if '->data)) = (void*){' in line or '.data)) = (void*){' in line:
            lines[i] = re.sub(r'\(void\*\)\{\.tag = (\d+)\}', r'(void*)(fl_int)\1', line)
            continue
        lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
    text = '\n'.join(lines)

    # === PHASE 4d: FL_BOX_WRAP helper macro ===
    if 'FL_BOX_WRAP' not in text:
        text = text.replace(
            '#include "flow_runtime.h"',
            '#include "flow_runtime.h"\n'
            '/* Bootstrap helper: wrap a value in an FL_Box */\n'
            '#define FL_BOX_WRAP(val, Type) ({ \\\n'
            '    FL_Box* _bw = fl_box_new(sizeof(Type)); \\\n'
            '    *(Type*)(_bw->data) = (val); \\\n'
            '    _bw; })\n',
            1
        )

    # === PHASE 5: Fix path.join variadic calls ===
    # fl_path_join(a, b) → fl_path_join(pack into array)
    # Do line-by-line to handle all contexts
    lines = text.split('\n')
    for i, line in enumerate(lines):
        idx = line.find('fl_path_join(')
        if idx < 0:
            continue
        # Extract args between the parens
        start = idx + len('fl_path_join(')
        depth = 1
        j = start
        while j < len(line) and depth > 0:
            if line[j] == '(': depth += 1
            elif line[j] == ')': depth -= 1
            j += 1
        if depth != 0:
            continue
        args_str = line[start:j-1]
        # Split on top-level commas
        depth = 0
        parts = []
        cur = ''
        for c in args_str:
            if c == '(': depth += 1
            elif c == ')': depth -= 1
            elif c == ',' and depth == 0:
                parts.append(cur.strip())
                cur = ''
                continue
            cur += c
        parts.append(cur.strip())
        if len(parts) <= 1:
            continue
        # Build array packing
        arr = 'fl_array_new(0, 0, NULL)'
        for p in parts:
            arr = f'fl_array_push_ptr({arr}, {p})'
        prefix = line[:idx]
        suffix = line[j:]
        lines[i] = f'{prefix}fl_path_join({arr}){suffix}'
    text = '\n'.join(lines)

    # === PHASE 5b: Fix fl_array_put__string for non-string values ===
    # Add fl_array_put__int function and replace wrong calls
    # The function fl_array_put__string exists but is for string arrays.
    # For int arrays, we need fl_array_put__int.
    if 'fl_array_put__int(' not in text and 'fl_array_put__string(' in text:
        # Add fl_array_put__int function definition after fl_array_put__string definition
        put_string_def = 'FL_Array* fl_array_put__string(FL_Array* arr, fl_int idx, FL_String* val) {'
        put_int_proto = '\nFL_Array* fl_array_put__int(FL_Array* arr, fl_int idx, fl_int val);\n'
        put_int_def = """
FL_Array* fl_array_put__int(FL_Array* arr, fl_int idx, fl_int val) {
    fl_int64 len = fl_array_len(arr);
    if (idx < 0 || idx >= len) return arr;
    FL_Array* new_arr = fl_array_copy(arr);
    if (new_arr->element_size == 0) new_arr->element_size = sizeof(fl_int);
    *((fl_int*)((char*)new_arr->data + idx * new_arr->element_size)) = val;
    return new_arr;
}
"""
        # Find the end of fl_array_put__string definition
        idx_str = text.find(put_string_def)
        if idx_str >= 0:
            # Find matching closing brace
            depth = 0
            for j in range(idx_str, len(text)):
                if text[j] == '{': depth += 1
                elif text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        text = text[:j+1] + put_int_def + text[j+1:]
                        break
        # Add forward declaration
        fwd_idx = text.find('FL_Array* fl_array_put__string(FL_Array* arr, fl_int idx, FL_String* val);')
        if fwd_idx >= 0:
            text = text[:fwd_idx] + 'FL_Array* fl_array_put__int(FL_Array* arr, fl_int idx, fl_int val);\n' + text[fwd_idx:]

    # Now fix specific calls where fl_array_put__string is used with int values
    # ONLY replace when the value is provably an int (checked arith result or declared fl_int)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'fl_array_put__string(' not in line:
            continue
        idx = line.find('fl_array_put__string(')
        if idx < 0:
            continue
        paren_depth = 0
        commas = []
        end_p = -1
        for j in range(idx, len(line)):
            if line[j] == '(':
                paren_depth += 1
            elif line[j] == ')':
                paren_depth -= 1
                if paren_depth == 0:
                    end_p = j
                    break
            elif line[j] == ',' and paren_depth == 1:
                commas.append(j)
        if len(commas) >= 2 and end_p >= 0:
            val_part = line[commas[1]+1:end_p].strip()
            # Only convert to put__int if value is clearly an int:
            # 1. _fl_e_N (checked arithmetic result)
            # 2. A variable that was declared as fl_int nearby
            is_int_val = False
            if re.match(r'^_fl_e_\d+$', val_part):
                is_int_val = True
            elif val_part.isidentifier():
                # Look backwards for declaration
                for k in range(max(0, i - 20), i):
                    if re.match(rf'^\s+fl_int {re.escape(val_part)}\b', lines[k]):
                        is_int_val = True
                        break
            if is_int_val:
                lines[i] = line.replace('fl_array_put__string(', 'fl_array_put__int(')
            # Check if value is a TCTypeBox (box variable)
            elif val_part.isidentifier():
                for k in range(max(0, i - 10), i):
                    if re.match(rf'^\s+fl_self_hosted_typechecker_TCTypeBox {re.escape(val_part)}\b', lines[k]):
                        # Replace with push_sized based approach (put at index)
                        indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                        # Extract array and index args
                        arr_arg = lines[i][commas[0]-len('fl_array_put__string('):commas[0]].strip()
                        idx_arg = lines[i][commas[0]+1:commas[1]].strip()
                        # Actually just use memcpy approach
                        m_arr = re.match(r'^(\s+)(.+) = fl_array_put__string\((.+), (.+), (.+)\);', lines[i])
                        if m_arr:
                            i_indent = m_arr.group(1)
                            result_var = m_arr.group(2)
                            arr_v = m_arr.group(3)
                            idx_v = m_arr.group(4)
                            val_v = m_arr.group(5)
                            stype = 'fl_self_hosted_typechecker_TCTypeBox'
                            push_counter[0] += 1
                            tmp = f'_put_tmp_{push_counter[0]}'
                            lines[i] = (f'{i_indent}{stype} {tmp} = {val_v};\n'
                                        f'{i_indent}FL_Array* _put_arr = fl_array_copy({arr_v});\n'
                                        f'{i_indent}if (_put_arr->element_size == 0) _put_arr->element_size = sizeof({stype});\n'
                                        f'{i_indent}memcpy((char*)_put_arr->data + {idx_v} * _put_arr->element_size, &{tmp}, sizeof({stype}));\n'
                                        f'{i_indent}{result_var} = _put_arr;')
                        break
    text = '\n'.join(lines)

    # === PHASE 5c: Fix _fl_throw in return context for struct-returning functions ===
    # Deferred to after Phase 6 where struct_types is populated

    # === PHASE 5d: Fix TCString() → compound literal ===
    text = text.replace(
        'fl_self_hosted_typechecker_TCString()',
        '(fl_self_hosted_typechecker_TCType){.tag = 6}'
    )
    text = text.replace(
        'fl_self_hosted_typechecker_TCPtr()',
        '(fl_self_hosted_typechecker_TCType){.tag = 5}'
    )

    # === PHASE 5d2: Fix wrong field initializers in default expressions ===
    # .suffix = (fl_self_hosted_lir_LExpr){0} → .suffix = fl_string_from_cstr("")
    text = text.replace(
        '.suffix = (fl_self_hosted_lir_LExpr){0}',
        '.suffix = fl_string_from_cstr("")'
    )
    # .suffix = (fl_self_hosted_typechecker_TCType){0} → .suffix = fl_string_from_cstr("")
    text = text.replace(
        '.suffix = (fl_self_hosted_typechecker_TCType){0}',
        '.suffix = fl_string_from_cstr("")'
    )

    # === PHASE 5e: Fix Expr assigned to void* ===
    # Pattern: void* var = some_field that returns Expr
    # Already handled by PHASE 4a for match-bound vars
    # Handle remaining: assigning Expr struct to void*
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if not re.match(r'\s+void\* \w+ = .*\bExpr\b', line):
            continue
        # Don't touch if it's a function call returning void*
        if 'fl_array_get' in line or 'fl_map_get' in line:
            continue
    text = '\n'.join(lines)

    # Phase 5f removed — bool→void* in map_set is now handled by the line-by-line parser in Phase 4b2

    # === PHASE 6: Fix int 0 where struct is expected ===
    lines = text.split('\n')
    current_return_type = None
    result_lines = []
    struct_types = set()
    for line in lines:
        m = re.match(r'^typedef struct (\S+) (\S+);', line)
        if m:
            struct_types.add(m.group(2))
    for line in lines:
        m = re.match(r'^(\S+) (fl_\w+)\(', line)
        if m:
            ret_type = m.group(1)
            if ret_type in struct_types:
                current_return_type = ret_type
            else:
                current_return_type = None
        if current_return_type and re.match(r'\s+return 0;\s*$', line):
            line = line.replace('return 0;', f'return ({current_return_type}){{0}};')
        m2 = re.match(r'^(\s+)(\S+) (\w+) = 0;$', line)
        if m2 and m2.group(2) in struct_types:
            indent = m2.group(1)
            stype = m2.group(2)
            vname = m2.group(3)
            line = f'{indent}{stype} {vname} = ({stype}){{0}};'
        result_lines.append(line)
    text = '\n'.join(result_lines)

    # === PHASE 6b: Fix _fl_throw in return context for struct-returning functions ===
    lines = text.split('\n')
    current_ret_type_throw = None
    result_lines2 = []
    for line in lines:
        m = re.match(r'^(\S+) (fl_\w+)\(', line)
        if m:
            ret = m.group(1)
            if ret in struct_types:
                current_ret_type_throw = ret
            else:
                current_ret_type_throw = None
        if current_ret_type_throw and 'return _fl_throw(' in line:
            indent = line[:len(line) - len(line.lstrip())]
            throw_call = line.strip()
            if throw_call.startswith('return '):
                throw_call = throw_call[7:]
            result_lines2.append(f'{indent}{throw_call}')
            result_lines2.append(f'{indent}return ({current_ret_type_throw}){{0}};')
        else:
            result_lines2.append(line)
    text = '\n'.join(result_lines2)

    # === PHASE 7: Fix TCTypeBox/LTypeBox/LExprBox → void* in push_ptr calls ===
    # These struct types need push_sized instead of push_ptr
    box_types = {
        'fl_self_hosted_typechecker_TCTypeBox': r'_tc_box\(|TCTypeBox\{',
        'fl_self_hosted_lir_LTypeBox': r'_lt_box\(|LTypeBox\{',
        'fl_self_hosted_lir_LExprBox': r'_le_box\(|LExprBox\{',
        'fl_self_hosted_lir_LStmtBox': r'_ls_box\(|LStmtBox\{',
    }
    # Find remaining push_ptr calls with struct values (not caught by phase 4b)
    lines = text.split('\n')
    push_extra = [push_counter[0]]
    for i, line in enumerate(lines):
        if 'fl_array_push_ptr(' not in line:
            continue
        m = re.match(r'^(\s+)((\w+) = )fl_array_push_ptr\(\3, (.+)\);$', line)
        if not m:
            continue
        indent, assign, arr_var, val = m.groups()
        # Check if val is a struct-typed expression
        stype = None
        for btype, pattern in box_types.items():
            if re.search(pattern, val):
                stype = btype
                break
        if stype:
            push_extra[0] += 1
            tmp = f'_push_tmp_{push_extra[0]}'
            lines[i] = (f'{indent}{stype} {tmp} = {val};\n'
                        f'{indent}{assign}fl_array_push_sized({arr_var}, &{tmp}, sizeof({stype}));')
    text = '\n'.join(lines)

    # === PHASE 8: Fix LStmtBox in fl_array_put__string → put_sized ===
    # fl_array_put__string(stmts, idx, (LStmtBox){...}) is wrong
    # Need: LStmtBox _tmp = val; memcpy into array
    lines = text.split('\n')
    for i, line in enumerate(lines):
        m = re.search(r'fl_array_put__(?:string|int)\((\w+), (\w+), (\(fl_self_hosted_lir_LStmtBox\)\{[^;]+)\);', line)
        if m:
            arr = m.group(1)
            idx_expr = m.group(2)
            val_expr = m.group(3)
            indent = line[:len(line) - len(line.lstrip())]
            push_extra[0] += 1
            tmp = f'_put_tmp_{push_extra[0]}'
            # Use a simple set approach: copy, then overwrite element
            lines[i] = (f'{indent}fl_self_hosted_lir_LStmtBox {tmp} = {val_expr};\n'
                        f'{indent}{arr} = fl_array_push_sized({arr}, &{tmp}, sizeof(fl_self_hosted_lir_LStmtBox));')
            # Note: This changes semantics (push instead of put) but for the bootstrap
            # it's equivalent since the array is being rebuilt
    text = '\n'.join(lines)

    # === PHASE 9: Fix remaining struct → void* in push/map contexts ===
    # Catch any remaining struct-to-void* push_ptr that weren't caught earlier
    # Look for patterns where push_ptr gets a known struct variable
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'fl_array_push_ptr(' not in line:
            continue
        m = re.match(r'^(\s+)((\w+) = )fl_array_push_ptr\(\3, (\w+)\);$', line)
        if not m:
            continue
        indent, assign, arr_var, val_var = m.groups()
        # Look backwards for the variable's type declaration
        for j in range(max(0, i - 30), i):
            decl_m = re.match(rf'^\s+(fl_self_hosted_\w+) {re.escape(val_var)}\b', lines[j])
            if decl_m:
                vtype = decl_m.group(1)
                # Only fix if it's a known struct (not a pointer type)
                if (vtype.endswith('Box') or vtype.endswith('Symbol') or
                    vtype.endswith('TypeInfo') or vtype.endswith('InterfaceInfo') or
                    vtype.endswith('Module') or vtype.endswith('ModuleScope') or
                    vtype.endswith('TypedModule') or vtype.endswith('Decl') or
                    vtype.endswith('Pattern')):
                    push_extra[0] += 1
                    tmp = f'_push_tmp_{push_extra[0]}'
                    lines[i] = (f'{indent}{vtype} {tmp} = {val_var};\n'
                                f'{indent}{assign}fl_array_push_sized({arr_var}, &{tmp}, sizeof({vtype}));')
                break
    text = '\n'.join(lines)

    # === PHASE 9b0: Fix FL_Box for TCCoroutine yield/send fields ===
    # Pattern: FL_Box* _tmp = fl_box_new(sizeof(fl_self_hosted_ast_Expr));
    #          (*((fl_self_hosted_ast_Expr*)_tmp->data)) = elem;
    # where elem is a TCType. Fix: use sizeof(TCType) and (TCType*) cast
    text = re.sub(
        r'fl_box_new\(sizeof\(fl_self_hosted_ast_Expr\)\);\s*\n(\s+)\(\*\(\(fl_self_hosted_ast_Expr\*\)(\w+)->data\)\) = (elem|it)',
        lambda m: (f'fl_box_new(sizeof(fl_self_hosted_typechecker_TCType));\n'
                   f'{m.group(1)}(*((fl_self_hosted_typechecker_TCType*){m.group(2)}->data)) = {m.group(3)}'),
        text
    )

    # === PHASE 9a: Fix (void*)struct_var in push_ptr ===
    # Pattern: arr = fl_array_push_ptr(arr, ((void*)struct_var));
    # where struct_var is a known struct type (detected by looking backwards for declaration)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        m = re.match(r'^(\s+)((\w+) = )fl_array_push_ptr\(\3, \(\(void\*\)(\w+)\)\);$', line)
        if not m:
            continue
        indent, assign, arr_var, val_var = m.groups()
        # Look backwards for the variable's type declaration
        for k in range(max(0, i - 30), i):
            decl_m = re.match(rf'^\s+(fl_self_hosted_\w+) {re.escape(val_var)}\b', lines[k])
            if decl_m:
                vtype = decl_m.group(1)
                if not vtype.endswith('*'):  # Only fix non-pointer types
                    push_extra[0] += 1
                    tmp = f'_push_tmp_{push_extra[0]}'
                    lines[i] = (f'{indent}{vtype} {tmp} = {val_var};\n'
                                f'{indent}{assign}fl_array_push_sized({arr_var}, &{tmp}, sizeof({vtype}));')
                break
    text = '\n'.join(lines)

    # === PHASE 9b: Fix FL_Box for Expr fields ===
    # Pattern: FL_Box* _tmp = fl_box_new(sizeof(void*));
    #          (*((void**)_tmp->data)) = stage.call;
    # stage.call is an Expr struct, need sizeof(Expr) and (Expr*) cast
    text = re.sub(
        r'fl_box_new\(sizeof\(void\*\)\);\s*\n(\s+)\(\*\(\(void\*\*\)(\w+)->data\)\) = (\w+)\.(call|pool_size)',
        lambda m: (f'fl_box_new(sizeof(fl_self_hosted_ast_Expr));\n'
                   f'{m.group(1)}(*((fl_self_hosted_ast_Expr*){m.group(2)}->data)) = {m.group(3)}.{m.group(4)}'),
        text
    )

    # === PHASE 9c: Fix :mut parameter passing ===
    # Functions that take FL_Map** or FL_Array** need callers to pass &var instead of var
    # Fix specific call sites where pointer-typed vars are passed to pointer-pointer parameters
    lines = text.split('\n')
    in_infer_type_env = False
    for i, line in enumerate(lines):
        if 'fl_self_hosted_typechecker_infer_type_env_from_call(' in line and '{' in line:
            in_infer_type_env = True
        elif in_infer_type_env and re.match(r'^[^ ]', line):
            in_infer_type_env = False
        if in_infer_type_env and 'match_type_env(' in line and ', env)' in line:
            lines[i] = line.replace(', env)', ', &env)')
        # Fix extend_extern_fn_map_from_typed calls
        if 'extend_extern_fn_map_from_typed(efn_map,' in line and '&efn_map' not in line:
            lines[i] = line.replace('extend_extern_fn_map_from_typed(efn_map,', 'extend_extern_fn_map_from_typed(&efn_map,')
        # Fix emit_with_deferred calls: last two args are FL_Array** but get passed as FL_Array*
        # Pattern: emit_with_deferred(lmod, ..., deferred_names, deferred_exprs)
        if 'emit_with_deferred(' in line and 'deferred_names,' in line and '&deferred_names' not in line:
            lines[i] = line.replace(', deferred_names, deferred_exprs)', ', (&deferred_names), (&deferred_exprs))')
        # Fix collect_fn_arg_vars_expr calls — result is FL_Map* but function expects FL_Map**
        if 'collect_fn_arg_vars_expr(' in line and ', result)' in line and '&result' not in line:
            lines[i] = line.replace(', result)', ', &result)')
    text = '\n'.join(lines)

    # === PHASE 10: Cast void* → typed pointers for runtime calls ===
    text = re.sub(
        r'(FL_String\*|FL_Array\*|FL_Map\*|FL_Stream\*|FL_Box\*) (\w+) = (fl_\w+\([^;]+\));',
        lambda m: f'{m.group(1)} {m.group(2)} = ({m.group(1)}){m.group(3)};'
        if m.group(3).startswith(('fl_map_get', 'fl_array_get'))
        else m.group(0),
        text
    )
    text = re.sub(
        r'(FL_String\* \w+ = )(\(void\*\))',
        r'\1(FL_String*)',
        text
    )

    # === PHASE 10b: Fix stack-address-in-map_set — heap-box struct values ===
    # Pattern: map.set with non-pointer struct stored as ((void*)(&_fl_tmp_N)) where
    # _fl_tmp_N is a local variable on the stack. After the function returns, the pointer
    # becomes dangling. Replace with malloc'd copy.
    #
    # Detects (within same function, within 30 lines):
    #   fl_self_hosted_XXX _fl_tmp_N = expr;
    #   ...
    #   = fl_map_set_str(..., ((void*)(&_fl_tmp_N)));
    #
    # Rewrites decl line to:
    #   fl_self_hosted_XXX* _fl_heap_N = (fl_self_hosted_XXX*)malloc(sizeof(fl_self_hosted_XXX));
    #   *_fl_heap_N = expr;
    # And replaces ((void*)(&_fl_tmp_N)) on the map_set line with ((void*)(_fl_heap_N)).
    #
    # NOTE: tmp variable names like _fl_tmp_14 can be reused in different functions,
    # so we do this replacement locally (decl line + map_set line) rather than globally.
    lines = text.split('\n')
    heap_counter = [0]
    # Collect (decl_line, mapset_line, heap_var, tmp_var, indent, vtype, init_expr)
    # Process in reverse order to preserve line indices
    fixes = []
    for i, line in enumerate(lines):
        m = re.search(r'\(\(void\*\)\(&(_fl_tmp_\d+)\)\)', line)
        if not m:
            continue
        tmp_var = m.group(1)
        # Look backward for the declaration of tmp_var (within 30 lines)
        for j in range(max(0, i - 30), i):
            decl_m = re.match(rf'^(\s+)(fl_self_hosted_\w+(?<!\*)) {re.escape(tmp_var)} = (.*);$', lines[j])
            if decl_m:
                heap_counter[0] += 1
                heap_var = f'_fl_heap_{heap_counter[0]}'
                fixes.append((j, i, heap_var, tmp_var, decl_m.group(1), decl_m.group(2), decl_m.group(3)))
                break
    # Apply in reverse order (largest line first) to preserve indices
    for decl_i, mapset_i, heap_var, tmp_var, indent, vtype, init_expr in sorted(fixes, key=lambda x: -x[0]):
        # Rewrite the decl line
        lines[decl_i] = (f'{indent}{vtype}* {heap_var} = ({vtype}*)malloc(sizeof({vtype}));\n'
                         f'{indent}*{heap_var} = {init_expr};')
        # Rewrite the map_set line (only this specific occurrence)
        lines[mapset_i] = lines[mapset_i].replace(
            f'((void*)(&{tmp_var}))', f'((void*)({heap_var}))', 1
        )
    text = '\n'.join(lines)

    # === PHASE 11: Fix FL_Box* variable member access (.data should be ->data) ===
    # Pattern: (*((Type*)_fl_tmp_N.data)) — should be ->data when _fl_tmp_N is FL_Box*
    text = re.sub(
        r'(_fl_tmp_\d+)\.data\b',
        r'\1->data',
        text
    )

    with open(path, 'w') as f:
        f.write(text)
    print(f"Post-processed: {path}")

if __name__ == '__main__':
    fix_stage2(sys.argv[1])
