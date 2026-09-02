package fixture

import "math"

type InvoiceLine struct {
	Quantity  float64
	UnitPrice float64
}

func CalculateInvoiceTotal(lines []InvoiceLine, taxRate float64) float64 {
	var subtotal float64
	for _, line := range lines {
		subtotal += line.Quantity * line.UnitPrice
	}
	return math.Round(subtotal*(1+taxRate)*100) / 100
}

func ValidatePayment(amount float64, currency string) bool {
	return amount > 0 && len(currency) == 3
}
