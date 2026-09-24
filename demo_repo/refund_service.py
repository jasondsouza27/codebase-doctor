"""
Refund Service (Legacy 2018)
Coordinates customer dispute resolutions, partial returns, and chargebacks.
Depends directly on PaymentService.
"""

from typing import Any, Dict
from payment_service import PaymentService
from database import db


class RefundService:
    """Manages return workflows and triggers payment reversals."""

    def __init__(self):
        self.payment_service = PaymentService()

    def process_refund_request(self, transaction_id: str, amount: float, reason: str) -> Dict[str, Any]:
        """Validates and processes customer refund via PaymentService."""
        tx = db.get_transaction(transaction_id)
        if not tx:
            raise ValueError(f"Cannot refund nonexistent transaction {transaction_id}")

        # Calls payment service refund & calculation
        calc = self.payment_service.calculate_refund(transaction_id, amount)
        success = self.payment_service.refund(transaction_id, amount)

        return {
            "refund_id": f"ref_{transaction_id}",
            "transaction_id": transaction_id,
            "amount": amount,
            "reason": reason,
            "status": "COMPLETED" if success else "FAILED",
        }
