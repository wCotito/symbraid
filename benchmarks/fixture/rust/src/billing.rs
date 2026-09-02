pub fn calculate_invoice_total(lines: &[(f64, f64)], tax_rate: f64) -> f64 {
    let subtotal: f64 = lines.iter().map(|(quantity, unit_price)| quantity * unit_price).sum();
    (subtotal * (1.0 + tax_rate) * 100.0).round() / 100.0
}

pub fn validate_payment(amount: f64, currency: &str) -> bool {
    amount > 0.0 && currency.chars().count() == 3
}
