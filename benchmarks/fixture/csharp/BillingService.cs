namespace Fixture;

public static class BillingService
{
    public static decimal CalculateInvoiceTotal((decimal Quantity, decimal UnitPrice)[] lines, decimal taxRate)
    {
        var subtotal = lines.Sum(line => line.Quantity * line.UnitPrice);
        return Math.Round(subtotal * (1 + taxRate), 2);
    }

    public static bool ValidatePayment(decimal amount, string currency) => amount > 0 && currency.Length == 3;
}
