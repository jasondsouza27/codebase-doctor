"""
Notification Service (Legacy 2018)
Sends transactional emails, SMS receipts, and webhook events.
Depends on OrderService and PaymentService.
"""

from typing import Any, Dict
from payment_service import PaymentService
from order_service import OrderService


class NotificationService:
    """Dispatches event notifications for orders and payments."""

    def __init__(self):
        self.payment_service = PaymentService()
        self.order_service = OrderService()

    def send_payment_receipt(self, customer_email: str, transaction_id: str, amount: float) -> bool:
        """Sends receipt email for processed payment."""
        print(f"[EMAIL] Sending payment receipt of ${amount} for tx {transaction_id} to {customer_email}")
        return True

    def notify_order_status(self, customer_email: str, order_id: str) -> bool:
        """Fetches order and dispatches status update."""
        print(f"[SMS/EMAIL] Notifying {customer_email} regarding order {order_id}")
        return True
