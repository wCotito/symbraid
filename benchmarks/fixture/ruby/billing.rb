module FixtureBilling
  def self.calculate_invoice_total(lines, tax_rate)
    subtotal = lines.sum { |line| line[:quantity] * line[:unit_price] }
    (subtotal * (1 + tax_rate)).round(2)
  end

  def self.validate_payment(amount, currency)
    amount.positive? && currency.length == 3
  end
end
