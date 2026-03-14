#!/bin/bash
# Post-processing script for stage2.c to fix known codegen issues
# in the self-hosted compiler output.
set -e

FILE="$1"
if [ -z "$FILE" ]; then echo "Usage: $0 <stage2.c>"; exit 1; fi

# 1. FL_BOX_DEREF for recursive box fields
#    Pattern: <StructType> var = expr.Variant.field;
#    where field is FL_Box* but var expects the struct type
sed -i 's/void\* \([a-zA-Z_]*_box\) = \([^;]*\)\.\([A-Z][A-Za-z]*\)\.\([a-zA-Z_]*_box\);/fl_self_hosted_lir_LExprBox \1 = FL_BOX_DEREF(\2.\3.\4, fl_self_hosted_lir_LExprBox);/g' "$FILE"

# LType FL_BOX_DEREF (avoid double-deref)
sed -i '/FL_BOX_DEREF/!{s/fl_self_hosted_lir_LType \([a-z_]*\) = \([^;]*\)\.LPtr\.inner;/fl_self_hosted_lir_LType \1 = FL_BOX_DEREF(\2.LPtr.inner, fl_self_hosted_lir_LType);/g}' "$FILE"
sed -i '/FL_BOX_DEREF/!{s/fl_self_hosted_lir_LType \([a-z_]*\) = \([^;]*\)\.LFnPtr\.ret;/fl_self_hosted_lir_LType \1 = FL_BOX_DEREF(\2.LFnPtr.ret, fl_self_hosted_lir_LType);/g}' "$FILE"

# AST Expr FL_BOX_DEREF
sed -i 's/fl_self_hosted_ast_Expr \([a-z_]*\) = \([^;]*\)\.\([A-Z][A-Za-z]*\)\.\([a-z_]*\);/fl_self_hosted_ast_Expr \1 = FL_BOX_DEREF(\2.\3.\4, fl_self_hosted_ast_Expr);/g' "$FILE"

# 2. Cross-module type name fixes
sed -i 's/fl_self_hosted_emitter_LType/fl_self_hosted_lir_LType/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_LExpr/fl_self_hosted_lir_LExpr/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_LStmt/fl_self_hosted_lir_LStmt/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_lir/fl_self_hosted_lir/g' "$FILE"
sed -i 's/fl_self_hosted_lir\./fl_self_hosted_lir_/g' "$FILE"

# 3. :mut parameter forwarding for emitter functions
sed -i 's/fl_self_hosted_emitter_emit_raw((\*st)/fl_self_hosted_emitter_emit_raw(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_indented((\*st)/fl_self_hosted_emitter_emit_indented(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_ltype((\*st)/fl_self_hosted_emitter_emit_ltype(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_expr((\*st)/fl_self_hosted_emitter_emit_expr(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_args((\*st)/fl_self_hosted_emitter_emit_args(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_ltype_params((\*st)/fl_self_hosted_emitter_emit_ltype_params(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_fresh_temp((\*st)/fl_self_hosted_emitter_fresh_temp(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_stmt((\*st)/fl_self_hosted_emitter_emit_stmt(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_var_decl((\*st)/fl_self_hosted_emitter_emit_var_decl(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_assign((\*st)/fl_self_hosted_emitter_emit_assign(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_return((\*st)/fl_self_hosted_emitter_emit_return(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_do_indent((\*st)/fl_self_hosted_emitter_do_indent(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_do_dedent((\*st)/fl_self_hosted_emitter_do_dedent(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_line_directive((\*st)/fl_self_hosted_emitter_emit_line_directive(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_emit_switch((\*st)/fl_self_hosted_emitter_emit_switch(st/g' "$FILE"
sed -i 's/fl_self_hosted_emitter_flush_pre_stmts((\*st)/fl_self_hosted_emitter_flush_pre_stmts(st/g' "$FILE"

# 4. Fix double FL_BOX_DEREF
sed -i 's/FL_BOX_DEREF(FL_BOX_DEREF(\([^)]*\), \([^)]*\)), \2)/FL_BOX_DEREF(\1, \2)/g' "$FILE"

# 5. Match field name fixes for LIR types (match binding names → struct field names)
# LType fields
sed -i 's/\.LInt\.w\b/.LInt.width/g' "$FILE"
sed -i 's/\.LInt\.s\b/.LInt.is_signed/g' "$FILE"
sed -i 's/\.LFloat\.w\b/.LFloat.width/g' "$FILE"
sed -i 's/\.LStruct\.cname\b/.LStruct.c_name/g' "$FILE"
sed -i 's/\.LStruct\.sname\b/.LStruct.c_name/g' "$FILE"
# LStmt fields
sed -i 's/\.LSVarDecl\.cname\b/.LSVarDecl.c_name/g; s/\.LSVarDecl\.ctype\b/.LSVarDecl.c_type/g' "$FILE"
sed -i 's/\.LSVarDecl\.init_expr\b/.LSVarDecl.init/g; s/\.LSVarDecl\.src_line\b/.LSVarDecl.source_line/g' "$FILE"
sed -i 's/\.LSArrayDecl\.cname\b/.LSArrayDecl.c_name/g; s/\.LSArrayDecl\.src_line\b/.LSArrayDecl.source_line/g' "$FILE"
sed -i 's/\.LSReturn\.has_val\b/.LSReturn.has_value/g; s/\.LSReturn\.val_expr\b/.LSReturn.value/g; s/\.LSReturn\.src_line\b/.LSReturn.source_line/g' "$FILE"
sed -i 's/\.LSAssign\.src_line\b/.LSAssign.source_line/g' "$FILE"
sed -i 's/\.LSIf\.src_line\b/.LSIf.source_line/g' "$FILE"
sed -i 's/\.LSWhile\.src_line\b/.LSWhile.source_line/g' "$FILE"
sed -i 's/\.LSBlock\.src_line\b/.LSBlock.source_line/g' "$FILE"
sed -i 's/\.LSExprStmt\.src_line\b/.LSExprStmt.source_line/g; s/\.LSExprStmt\.sline\b/.LSExprStmt.source_line/g' "$FILE"
sed -i 's/\.LSSwitch\.src_line\b/.LSSwitch.source_line/g' "$FILE"
sed -i 's/\.LSGoto\.src_line\b/.LSGoto.source_line/g' "$FILE"
sed -i 's/\.LSLabel\.src_line\b/.LSLabel.source_line/g; s/\.LSLabel\.label_name\b/.LSLabel.label/g' "$FILE"
sed -i 's/\.LSBreak\.src_line\b/.LSBreak.source_line/g' "$FILE"
sed -i 's/\.LSContinue\.src_line\b/.LSContinue.source_line/g' "$FILE"
# LExpr fields
sed -i 's/\.LELit\.ct\b/.LELit.c_type/g; s/\.LEVar\.ct\b/.LEVar.c_type/g; s/\.LECall\.ct\b/.LECall.c_type/g' "$FILE"
sed -i 's/\.LEIndirectCall\.ct\b/.LEIndirectCall.c_type/g; s/\.LEBinOp\.ct\b/.LEBinOp.c_type/g' "$FILE"
sed -i 's/\.LEUnary\.ct\b/.LEUnary.c_type/g; s/\.LEFieldAccess\.ct\b/.LEFieldAccess.c_type/g' "$FILE"
sed -i 's/\.LEArrow\.ct\b/.LEArrow.c_type/g; s/\.LEIndex\.ct\b/.LEIndex.c_type/g' "$FILE"
sed -i 's/\.LECast\.ct\b/.LECast.c_type/g; s/\.LEAddrOf\.ct\b/.LEAddrOf.c_type/g' "$FILE"
sed -i 's/\.LEDeref\.ct\b/.LEDeref.c_type/g; s/\.LECompound\.ctype\b/.LECompound.c_type/g' "$FILE"
sed -i 's/\.LECheckedArith\.ct\b/.LECheckedArith.c_type/g; s/\.LETernary\.ct\b/.LETernary.c_type/g' "$FILE"
sed -i 's/\.LEOptDerefAs\.ct\b/.LEOptDerefAs.c_type/g' "$FILE"
sed -i 's/\.LESizeOf\.tt\b/.LESizeOf.target_type/g' "$FILE"
sed -i 's/\.LEArrayData\.et\b/.LEArrayData.elem_type/g; s/\.LEArrayData\.ct\b/.LEArrayData.c_type/g' "$FILE"
# Other struct fields
sed -i 's/\.LExternFnProto\.cname\b/.LExternFnProto.c_name/g' "$FILE"
sed -i 's/\.LParam\.ptype\b/.LParam.param_type/g' "$FILE"
sed -i 's/\.LFnDef\.cname\b/.LFnDef.c_name/g; s/\.LFnDef\.src_name\b/.LFnDef.source_name/g; s/\.LFnDef\.src_line\b/.LFnDef.source_line/g' "$FILE"
sed -i 's/\.LTypeDef\.cname\b/.LTypeDef.c_name/g' "$FILE"
sed -i 's/\.LEnumDef\.cname\b/.LEnumDef.c_name/g' "$FILE"
sed -i 's/\.LField\.ftype\b/.LField.field_type/g' "$FILE"
# LExpr box field renames (match bindings use short names)
sed -i 's/\.LEIndirectCall\.fn_ptr_box\b/.LEIndirectCall.fn_ptr/g' "$FILE"
sed -i 's/\.LEBinOp\.left_box\b/.LEBinOp.left/g; s/\.LEBinOp\.right_box\b/.LEBinOp.right/g' "$FILE"
sed -i 's/\.LEUnary\.operand_box\b/.LEUnary.operand/g' "$FILE"
sed -i 's/\.LEFieldAccess\.obj_box\b/.LEFieldAccess.obj/g' "$FILE"
sed -i 's/\.LEArrow\.ptr_box\b/.LEArrow.ptr/g' "$FILE"
sed -i 's/\.LEIndex\.arr_box\b/.LEIndex.arr/g; s/\.LEIndex\.idx_box\b/.LEIndex.idx/g' "$FILE"
sed -i 's/\.LECast\.inner_box\b/.LECast.inner/g' "$FILE"
sed -i 's/\.LEAddrOf\.inner_box\b/.LEAddrOf.inner/g' "$FILE"
sed -i 's/\.LEDeref\.inner_box\b/.LEDeref.inner/g' "$FILE"
sed -i 's/\.LECheckedArith\.left_box\b/.LECheckedArith.left/g; s/\.LECheckedArith\.right_box\b/.LECheckedArith.right/g' "$FILE"
sed -i 's/\.LETernary\.cond_box\b/.LETernary.cond/g; s/\.LETernary\.then_box\b/.LETernary.then_expr/g; s/\.LETernary\.else_box\b/.LETernary.else_expr/g' "$FILE"
sed -i 's/\.LEOptDerefAs\.inner_box\b/.LEOptDerefAs.inner/g' "$FILE"
sed -i 's/\.LECompound\.fn_val\b/.LECompound.field_names/g; s/\.LECompound\.fv\b/.LECompound.field_values/g' "$FILE"

echo "Post-processing complete: $FILE"
