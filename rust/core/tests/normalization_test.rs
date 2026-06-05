use kepl_core::utils::normalization::canonical_string_expr;

#[test]
fn normalization_expression_builds() {
    let expr = canonical_string_expr("supplier");

    let debug = format!("{expr:?}");

    assert!(!debug.is_empty());
}
