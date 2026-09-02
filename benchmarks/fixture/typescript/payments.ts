export type InvoiceLine = { quantity: number; unitPrice: number };

export function calculateInvoiceTotal(lines: InvoiceLine[], taxRate: number): number {
  const subtotal = lines.reduce((sum, line) => sum + line.quantity * line.unitPrice, 0);
  return Math.round(subtotal * (1 + taxRate) * 100) / 100;
}

export function validatePayment(amount: number, currency: string): boolean {
  return amount > 0 && currency.length === 3;
}

export function validateAccessToken(expiresAt: number, now: number): boolean {
  return Number.isInteger(expiresAt) && expiresAt > now;
}
