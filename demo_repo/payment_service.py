"""
Payment Service (Legacy 2016)
Core financial processing module for customer transactions, currency exchange, and refunds.
"""

from typing import Any, Dict, Optional
from database import db


class PaymentGateway:
    """Mock external third-party payment gateway (e.g. Stripe / Adyen)."""

    def charge(self, amount: float, currency: str, customer_id: str) -> Dict[str, Any]:
        return {
            "gateway_tx_id": f"gw_{customer_id}_99",
            "status": "APPROVED",
            "authorized_amount": amount,
        }

    def refund(self, transaction_id: str, amount: float) -> bool:
        return True


class PaymentService:
    """Handles payments, multi-currency conversion, and refund dispatch."""

    def __init__(self):
        self.gateway = PaymentGateway()
        self.supported_currencies = {"USD", "EUR", "GBP", "JPY"}
        self.exchange_rates = {
            "USD": 1.0,
            "EUR": 0.92,
            "GBP": 0.79,
            "JPY": 155.4,
        }

    def process_payment(self, amount: float, currency: str, customer_id: str) -> Dict[str, Any]:
        """Processes customer charge through the payment gateway."""
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero")

        # Convert to USD if in foreign currency
        usd_amount = self.convert_currency(amount, currency, "USD")
        status = "PENDING"

        try:
            res = self.gateway.charge(usd_amount, "USD", customer_id)
            if res.get("status") == "APPROVED":
                status = "SUCCESS"
            else:
                status = "FAILED"
        except Exception:
            status = "FAILED"
            raise

        tx_record = {
            "customer_id": customer_id,
            "original_amount": amount,
            "currency": currency,
            "usd_amount": usd_amount,
            "status": status,
        }
        db.save_transaction(res.get("gateway_tx_id", "fallback_tx"), tx_record)
        return tx_record

    def convert_currency(self, amount: float, from_curr: str, to_curr: str) -> float:
        """
        Converts currency using floating point math.
        Risk area: Float precision drift on high volumes.
        """
        if from_curr == to_curr:
            return amount

        rate_from = self.exchange_rates.get(from_curr, 1.0)
        rate_to = self.exchange_rates.get(to_curr, 1.0)

        # Float arithmetic risk
        usd_base = amount / rate_from
        converted = usd_base * rate_to
        return round(converted, 2)

    def calculate_refund(self, transaction_id: str, refund_amount: float) -> Dict[str, Any]:
        """
        Calculates refund amount.
        Risk area: Missing boundary check against original payment amount.
        """
        tx = db.get_transaction(transaction_id)
        # Potential defect: If tx is None or refund_amount > tx amount, proceeds anyway
        return {
            "transaction_id": transaction_id,
            "refund_amount": refund_amount,
            "status": "CALCULATED",
        }

    def refund(self, transaction_id: str, amount: float) -> bool:
        """Executes refund through the gateway."""
        calc = self.calculate_refund(transaction_id, amount)
        success = self.gateway.refund(transaction_id, calc["refund_amount"])
        if success:
            db.save_transaction(f"ref_{transaction_id}", {"refunded": amount, "status": "REFUNDED"})
        return success
