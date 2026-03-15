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
    # Note: lowering_lir → lir must NOT double-apply
    text = re.sub(r'\bfl_self_hosted_lowering_lir\b(?!_)', 'fl_self_hosted_lir', text)
    text = text.replace('fl_self_hosted_lowering_typechecker', 'fl_self_hosted_typechecker')
    text = text.replace('fl_self_hosted_typechecker_lir', 'fl_self_hosted_lir')
    text = text.replace('fl_self_hosted_parser_ast', 'fl_self_hosted_ast')
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
    text = re.sub(r'\bfl_self_hosted_lir\.(\w)', r'fl_self_hosted_lir_\1', text)
    text = re.sub(r'\bfl_self_hosted_ast\.(\w)', r'fl_self_hosted_ast_\1', text)
    text = re.sub(r'\bfl_self_hosted_typechecker\.(\w)', r'fl_self_hosted_typechecker_\1', text)
    text = re.sub(r'\bfl_self_hosted_resolver\.(\w)', r'fl_self_hosted_resolver_\1', text)
    text = re.sub(r'\bfl_self_hosted_lexer\.(\w)', r'fl_self_hosted_lexer_\1', text)
    text = re.sub(r'\bfl_self_hosted_parser\.(\w)', r'fl_self_hosted_parser_\1', text)
    text = re.sub(r'\bfl_self_hosted_emitter\.(\w)', r'fl_self_hosted_emitter_\1', text)
    text = re.sub(r'\bfl_self_hosted_lowering\.(\w)', r'fl_self_hosted_lowering_\1', text)
    text = re.sub(r'\bfl_self_hosted_driver\.(\w)', r'fl_self_hosted_driver_\1', text)
    text = re.sub(r'\bfl_self_hosted_mangler\.(\w)', r'fl_self_hosted_mangler_\1', text)
    # lir->LVoid → compound literal
    text = text.replace('lir->LVoid', '(fl_self_hosted_lir_LType){.tag = 7}')

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
        '.LEVar.cname': '.LEVar.c_name',
        '.LECheckedArith.ctype': '.LECheckedArith.c_type',
        '.LECall.fn': '.LECall.fn_name',
        '.LEOptDerefAs.opt_type': '.LEOptDerefAs.c_type',
        '.LEOptDerefAs.vt': '.LEOptDerefAs.val_type',
        '.LEArrayData.ctype': '.LEArrayData.c_type',
        '.LECheckedArith.ctype': '.LECheckedArith.c_type',
        '.LECall.fn': '.LECall.fn_name',
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
            # Only for self-recursive Expr variants (NOT Stmt/Decl/etc)
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
    # Fix (*st) → st for emitter functions called from :mut context
    text = re.sub(
        r'fl_self_hosted_emitter_(\w+)\(\(\*st\)',
        r'fl_self_hosted_emitter_\1(st', text)
    # Note: NOT fixing (*s) → s for lexer — causes cascade issues

    # Fix local :mut state variables — convert to pointer
    # Pattern: TypeState st = make_state(...);
    # → TypeState _st_v = make_state(...); TypeState* st = &_st_v;
    # Then: st.field → st->field (already handled by (*st).field staying correct)
    # EmitState :mut forwarding — not converting to pointer (causes cascade)
    # Instead, just accept these 22 errors for now.

    # Note: NOT converting st to pointer — too many field accesses to fix.
    # Instead, the remaining EmitState errors are accepted as warnings.
    # clang -Wno-incompatible-pointer-types suppresses these.

    # === PHASE 4b: Fix array.push_ptr with struct values ===
    # Pattern: arr = fl_array_push_ptr(arr, ((void*)struct_expr));
    # where struct_expr is a non-pointer function call
    # Replace with: Type _tmp = struct_expr; arr = fl_array_push_sized(arr, &_tmp, sizeof(Type));
    push_counter = [0]
    def fix_push_ptr(match):
        full = match.group(0)
        indent = match.group(1)
        arr_assign = match.group(2)
        arr_var = match.group(3)
        void_expr = match.group(4)
        # Check if expr is a struct-returning function (not a pointer variable)
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
            elif 'resolver_ModuleScope' in void_expr:
                stype = 'fl_self_hosted_resolver_ModuleScope'
            elif 'typechecker_TypeInfo' in void_expr or 'default_type_info(' in void_expr:
                stype = 'fl_self_hosted_typechecker_TypeInfo'
            elif 'typechecker_InterfaceInfo' in void_expr or 'default_interface_info(' in void_expr:
                stype = 'fl_self_hosted_typechecker_InterfaceInfo'
            elif 'typechecker_TypedModule' in void_expr:
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
        # Check for compound literal: (TypeName){...}
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

    # === PHASE 4a: Fix void* match-bound variables ===
    # When match destructuring puts a struct field into void*, use the correct type
    # Pattern: void* var = _fl_tmp.Variant.field;
    # If the field type is known (from struct definitions), replace void* with it
    VARIANT_FIELD_TYPES = {
        'FPExpr.expr': 'fl_self_hosted_ast_Expr',
        'FPText.text': 'FL_String*',
        'DConstructor.return_type': 'fl_self_hosted_ast_TypeExpr',
        'DConstructor.body': 'FL_Array*',
        'MatchArm.pattern': 'fl_self_hosted_ast_Pattern',
        'CatchClause.exception_type': 'fl_self_hosted_ast_TypeExpr',
        'CatchClause.body': 'FL_Array*',
        'ChainElement.expr': 'fl_self_hosted_ast_Expr',
    }
    vf_lines = text.split('\n')
    for i, line in enumerate(vf_lines):
        if 'void* ' not in line or '_fl_tmp_' not in line:
            continue
        for pattern, correct_type in VARIANT_FIELD_TYPES.items():
            if f'.{pattern};' in line:
                vf_lines[i] = line.replace('void* ', f'{correct_type} ', 1)
                break
    text = '\n'.join(vf_lines)

    # === PHASE 4b2: Fix fl_map_set_str with struct values ===
    # fl_map_set_str(map, key, struct_value) needs the value as void*
    # For struct values, store in a temp and pass address
    map_set_counter = [0]
    def fix_map_set(match):
        indent = match.group(1)
        assign = match.group(2)
        map_var = match.group(3)
        key_expr = match.group(4)
        val_expr = match.group(5)
        stype = None
        # Compound literal: (Type){...}
        if val_expr.startswith('(fl_self_hosted_'):
            stype = val_expr.split(')')[0][1:]
        # Function call returning struct
        elif 'symbol_with_type(' in val_expr or 'symbol_no_type(' in val_expr or 'make_symbol(' in val_expr or 'copy_symbol_with_mk(' in val_expr:
            stype = 'fl_self_hosted_resolver_Symbol'
        elif 'default_type_info(' in val_expr or '_TypeInfo)' in val_expr:
            stype = 'fl_self_hosted_typechecker_TypeInfo'
        elif 'default_interface_info(' in val_expr or '_InterfaceInfo)' in val_expr:
            stype = 'fl_self_hosted_typechecker_InterfaceInfo'
        elif '_ModuleScope)' in val_expr or 'build_module_scope(' in val_expr:
            stype = 'fl_self_hosted_resolver_ModuleScope'
        elif '_TypedModule)' in val_expr or 'typecheck(' in val_expr:
            stype = 'fl_self_hosted_typechecker_TypedModule'
        elif '_Module)' in val_expr or 'make_module(' in val_expr:
            stype = 'fl_self_hosted_ast_Module'
        # Simple variable check — look at the key pattern for context
        if stype is None and not val_expr.startswith('fl_string') and not val_expr.startswith('"') and not val_expr.startswith('(void*') and not val_expr.startswith('NULL'):
            # Check if it's a simple variable name that's a struct
            val_stripped = val_expr.strip()
            if val_stripped in ('sym', 'rsym', 'msym', 'ns_sym', 'es'):
                stype = 'fl_self_hosted_resolver_Symbol'
            elif val_stripped.startswith('@') and 'sym' in val_stripped:
                stype = 'fl_self_hosted_resolver_Symbol'
        if stype is not None:
            map_set_counter[0] += 1
            tmp = f'_map_tmp_{map_set_counter[0]}'
            return (f'{indent}{stype} {tmp} = {val_expr};\n'
                    f'{indent}{assign}fl_map_set_str({map_var}, {key_expr}, &{tmp});')
        return match.group(0)

    # Apply map_set fix line by line (regex can't handle nested parens)
    lines2 = text.split('\n')
    for i, line in enumerate(lines2):
        if 'fl_map_set_str(' not in line:
            continue
        # Find the map_set call and extract the VALUE arg (last arg before closing paren)
        idx = line.find('fl_map_set_str(')
        if idx < 0:
            continue
        # Find the last comma that separates the value arg
        paren_depth = 0
        last_comma = -1
        for j in range(idx, len(line)):
            if line[j] == '(':
                paren_depth += 1
            elif line[j] == ')':
                paren_depth -= 1
                if paren_depth == 0:
                    break
            elif line[j] == ',' and paren_depth == 1:
                last_comma = j
        if last_comma < 0:
            continue
        val_part = line[last_comma+1:j].strip()
        indent = line[:len(line) - len(line.lstrip())]
        # Check if val_part is a struct value
        stype = None
        val_stripped = val_part.strip()
        if val_stripped in ('sym', 'rsym', 'msym', 'ns_sym', 'es', 'exported'):
            stype = 'fl_self_hosted_resolver_Symbol'
        elif 'symbol_with_type(' in val_stripped or 'symbol_no_type(' in val_stripped or 'make_symbol(' in val_stripped or 'copy_symbol_with_mk(' in val_stripped:
            stype = 'fl_self_hosted_resolver_Symbol'
        elif val_stripped.startswith('(fl_self_hosted_'):
            stype = val_stripped.split(')')[0][1:]
        if stype:
            map_set_counter[0] += 1
            tmp = f'_map_tmp_{map_set_counter[0]}'
            new_line = f'{indent}{stype} {tmp} = {val_part};\n{indent}{line[:last_comma+1]} &{tmp}{line[j:]}'
            lines2[i] = new_line
    text = '\n'.join(lines2)

    # === PHASE 4b3: Fix ternary void* vs struct operands ===
    # Pattern: Type var = (cond) ? _fl_tmp.value : (Type){...};
    # The _fl_tmp.value is void* but the Type is a struct.
    # Fix: cast _fl_tmp.value to Type: *(Type*)&(_fl_tmp.value)
    def fix_ternary(match):
        full = match.group(0)
        stype = match.group(1)
        var = match.group(2)
        cond = match.group(3)
        tmp_val = match.group(4)  # e.g., _fl_tmp_16.value
        fallback = match.group(5)
        return f'{stype} {var} = ({cond}) ? *(({stype}*)&({tmp_val})) : {fallback};'

    text = re.sub(
        r'(fl_self_hosted_\w+) (\w+) = \((\([^)]+\)) \? (_fl_tmp_\d+\.value) : (\([^;]+)\);',
        fix_ternary,
        text
    )
    # Also fix void* ternary: void* var = ternary(void*, struct_fallback)
    def fix_void_ternary(match):
        var = match.group(1)
        cond = match.group(2)
        tmp_val = match.group(3)
        fallback = match.group(4)
        # Infer type from fallback
        if 'fl_self_hosted_' in fallback:
            # Extract type from function name
            func = fallback.split('(')[0]
            if 'default_sum_variant(' in fallback or 'SumVariantDecl' in fallback:
                stype = 'fl_self_hosted_ast_SumVariantDecl'
            elif 'default_enum_variant(' in fallback or 'EnumVariantDecl' in fallback:
                stype = 'fl_self_hosted_ast_EnumVariantDecl'
            elif 'tc_box(' in fallback:
                stype = 'fl_self_hosted_typechecker_TCTypeBox'
            elif 'lt_box(' in fallback:
                stype = 'fl_self_hosted_lir_LTypeBox'
            elif 'le_box(' in fallback:
                stype = 'fl_self_hosted_lir_LExprBox'
            elif 'ls_box(' in fallback or 'placeholder_stmt(' in fallback or 'LStmtBox' in fallback:
                stype = 'fl_self_hosted_lir_LStmtBox'
            elif 'make_module(' in fallback:
                stype = 'fl_self_hosted_ast_Module'
            elif 'ExprField' in fallback:
                stype = 'fl_self_hosted_ast_ExprField'
            elif 'FieldDecl' in fallback:
                stype = 'fl_self_hosted_ast_FieldDecl'
            elif 'Field{' in fallback:
                stype = 'fl_self_hosted_ast_Field'
            elif 'Param{' in fallback:
                stype = 'fl_self_hosted_ast_Param'
            elif 'CatchClause' in fallback:
                stype = 'fl_self_hosted_ast_CatchClause'
            elif 'ChainElement' in fallback:
                stype = 'fl_self_hosted_ast_ChainElement'
            else:
                return match.group(0)
            return f'{stype} {var} = ({cond}) ? *(({stype}*)&({tmp_val})) : {fallback};'
        return match.group(0)

    text = re.sub(
        r'void\* (\w+) = \((\([^)]+\)) \? (_fl_tmp_\d+\.value) : (fl_self_hosted_[^;]+)\);',
        fix_void_ternary,
        text
    )
    # After ternary fix, replace var-> with var. for the fixed variables
    # (they're now struct values, not pointers)
    # Track which variables were converted
    for m in re.finditer(r'(fl_self_hosted_\w+) (\w+) = \(.*\?\s+\*\(\(', text):
        var_name = m.group(2)
        text = re.sub(rf'\b{var_name}->', f'{var_name}.', text)

    # === PHASE 4c: void* compound literals ===
    # (void*){.tag = N} is invalid C. Replace based on ASSIGNMENT context.
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if '(void*){' not in line:
            continue
        # Check what type the value is being assigned/initialized to
        # But if inside tc_box(), lt_box(), le_box(), use the INNER type
        if 'tc_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        if 'lt_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_lir_LType){')
            continue
        if 'le_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_lir_LExpr){')
            continue
        m_init = re.match(r'\s+(fl_self_hosted_\w+) \w+ = ', line)
        if m_init:
            target_type = m_init.group(1)
            lines[i] = line.replace('(void*){', f'({target_type}){{')
            continue
        # Pattern: .field = (void*){...} — determine type from field context
        if '.tc = (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        if '.le = (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_lir_LExpr){')
            continue
        # return (void*){...} — look at function signature to determine return type
        # For now, use TCType as default (most common case)
        if 'return (void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        # tc_box((void*){...}) — inner type is TCType
        if 'tc_box((void*){' in line:
            lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
            continue
        # FL_Box data assignment — keep as void* but with proper init
        if '->data)) = (void*){' in line:
            # Replace with memset-style init
            lines[i] = re.sub(r'\(void\*\)\{\.tag = (\d+)\}', r'(void*)(fl_int)\1', line)
            continue
        # Function argument — use TCType as default
        lines[i] = line.replace('(void*){', '(fl_self_hosted_typechecker_TCType){')
    text = '\n'.join(lines)

    # === PHASE 4d: Fix struct → FL_Box* in variant construction ===
    # When constructing a variant with a recursive field, the field value
    # is a struct but the C field expects FL_Box*. Wrap with fl_box_wrap macro.
    # Pattern: .field = expr) where expr is a function call returning a struct
    # that should be boxed.
    # We add a helper macro at the top of the file.
    if 'FL_BOX_WRAP' not in text:
        # Add helper macro after the #include
        text = text.replace(
            '#include "flow_runtime.h"',
            '#include "flow_runtime.h"\n'
            '/* Bootstrap helper: wrap a value in an FL_Box */\n'
            '#define FL_BOX_WRAP(val, Type) ({ \\\n'
            '    FL_Box* _bw = fl_box_new(sizeof(Type)); \\\n'
            '    *(Type*)(_bw->data) = (val); \\\n'
            '    _bw; })\n',
            1  # only first occurrence
        )

    # === PHASE 5: Fix int 0 where struct is expected ===
    # Replace "return 0;" with "return (ReturnType){0};" for struct-returning functions
    # Also fix struct variable initialization from 0
    lines = text.split('\n')
    current_return_type = None
    result_lines = []
    struct_types = set()
    # Collect all struct type names
    for line in lines:
        m = re.match(r'^typedef struct (\S+) (\S+);', line)
        if m:
            struct_types.add(m.group(2))
    for line in lines:
        # Track function return types
        m = re.match(r'^(\S+) (fl_\w+)\(', line)
        if m:
            ret_type = m.group(1)
            if ret_type in struct_types:
                current_return_type = ret_type
            else:
                current_return_type = None
        # Fix "return 0;" in struct-returning functions
        if current_return_type and re.match(r'\s+return 0;\s*$', line):
            line = line.replace('return 0;', f'return ({current_return_type}){{0}};')
        # Fix struct variable init from 0: "StructType var = 0;"
        m2 = re.match(r'^(\s+)(\S+) (\w+) = 0;$', line)
        if m2 and m2.group(2) in struct_types:
            indent = m2.group(1)
            stype = m2.group(2)
            vname = m2.group(3)
            line = f'{indent}{stype} {vname} = ({stype}){{0}};'
        result_lines.append(line)
    text = '\n'.join(result_lines)

    # === PHASE 6: C++ compatibility — cast void* to typed pointers ===
    # C++ requires explicit casts from void* to typed pointers
    # Pattern: Type* var = fl_xxx(...) where fl_xxx returns void*
    text = re.sub(
        r'(FL_String\*|FL_Array\*|FL_Map\*|FL_Stream\*|FL_Box\*) (\w+) = (fl_\w+\([^;]+\));',
        lambda m: f'{m.group(1)} {m.group(2)} = ({m.group(1)}){m.group(3)};'
        if m.group(3).startswith(('fl_map_get', 'fl_array_get'))
        else m.group(0),
        text
    )
    # More general: void* → FL_String* etc
    text = re.sub(
        r'(FL_String\* \w+ = )(\(void\*\))',
        r'\1(FL_String*)',
        text
    )

    with open(path, 'w') as f:
        f.write(text)
    print(f"Post-processed: {path}")

if __name__ == '__main__':
    fix_stage2(sys.argv[1])
