#include <cmath>
#include <string>
#include <utility>
#include <vector>

double calculate_invoice_total(const std::vector<std::pair<double, double>>& lines, double tax_rate) {
    double subtotal = 0;
    for (const auto& [quantity, unit_price] : lines) subtotal += quantity * unit_price;
    return std::round(subtotal * (1 + tax_rate) * 100) / 100;
}

bool validate_payment(double amount, const std::string& currency) {
    return amount > 0 && currency.size() == 3;
}
