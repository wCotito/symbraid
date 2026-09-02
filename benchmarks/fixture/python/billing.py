"""Billing helpers for the benchmark fixture."""


def calculate_invoice_total(lines: list[dict[str, float]], tax_rate: float) -> float:
    subtotal = sum(line["quantity"] * line["unit_price"] for line in lines)
    return round(subtotal * (1.0 + tax_rate), 2)


def validate_payment(amount: float, currency: str) -> bool:
    return amount > 0 and len(currency) == 3
