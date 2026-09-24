"""
Invoice Service (Legacy 2017)
Generates tax receipts, billing statements, and line-item PDF data.
Depends on PaymentService.
"""

from typing import Any, Dict
from payment_service import PaymentService
from database import db


class InvoiceService:
    """Generates customer invoices and verifies payment settlements."""

    def __init__(self):
        self.payment_service = PaymentService()

    def generate_invoice(self, transaction_id: str) -> Dict[str, Any]:
        """Generates formal tax invoice for a payment transaction."""
        tx = db.get_transaction(transaction_id)
        if not tx:
            raise ValueError(f"Transaction {transaction_id} not found")

        # Re-verify currency conversion or fee deduction using PaymentService
        converted_fee = self.payment_service.convert_currency(
            amount=tx.get("usd_amount", 0.0),
            from_curr="USD",
            to_curr=tx.get("currency", "USD"),
        )

        invoice = {
            "invoice_number": f"INV-{transaction_id}",
            "transaction_id": transaction_id,
            "customer_id": tx.get("customer_id"),
            "subtotal": tx.get("usd_amount", 0.0),
            "tax": round(tx.get("usd_amount", 0.0) * 0.08, 2),
            "total": converted_fee,
            "status": "ISSUED",
        }
        return invoice
