package fixture;

import java.util.List;

public final class BillingService {
    public record InvoiceLine(double quantity, double unitPrice) {}

    public static double calculateInvoiceTotal(List<InvoiceLine> lines, double taxRate) {
        double subtotal = lines.stream().mapToDouble(line -> line.quantity() * line.unitPrice()).sum();
        return Math.round(subtotal * (1 + taxRate) * 100) / 100.0;
    }

    public static boolean validatePayment(double amount, String currency) {
        return amount > 0 && currency != null && currency.length() == 3;
    }
}
