<?php

final class BillingService
{
    public function calculateInvoiceTotal(array $lines, float $taxRate): float
    {
        $subtotal = array_sum(array_map(
            static fn (array $line): float => $line['quantity'] * $line['unit_price'],
            $lines,
        ));

        return round($subtotal * (1 + $taxRate), 2);
    }

    public function validatePayment(array $payment): bool
    {
        return ($payment['amount'] ?? 0) > 0 && ($payment['currency'] ?? '') !== '';
    }
}

