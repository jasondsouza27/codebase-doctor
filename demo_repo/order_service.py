"""
Order Service (Legacy 2017)
Manages customer carts, checkouts, and order lifecycle states.
Depends on PaymentService and AuthService.
"""

from typing import Any, Dict, List, Optional
from payment_service import PaymentService
from auth_service import AuthService
from database import db


class OrderService:
    """Manages order creation and checkout processing."""

    def __init__(self):
        self.payment_service = PaymentService()
        self.auth_service = AuthService()

    def create_order(self, customer_id: str, items: List[Dict[str, Any]], session_token: Optional[str] = None) -> Dict[str, Any]:
        """Creates a pending order with optional user session verification."""
        if session_token and not self.auth_service.verify_token(session_token):
            raise PermissionError("Invalid authentication session token")
        total = sum(item.get("price", 0.0) * item.get("qty", 1) for item in items)
        order = {
            "order_id": f"ord_{customer_id}_101",
            "customer_id": customer_id,
            "items": items,
            "total_amount": total,
            "currency": "USD",
            "status": "CREATED",
        }
        db.save_transaction(order["order_id"], order)
        return order

    def checkout(self, order_id: str, session_token: Optional[str] = None) -> Dict[str, Any]:
        """Processes payment for an order and finalizes state."""
        order = db.get_transaction(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if session_token and not self.auth_service.verify_token(session_token):
            raise PermissionError("Session expired or invalid")

        # Calls payment service
        payment_record = self.payment_service.process_payment(
            amount=order["total_amount"],
            currency=order.get("currency", "USD"),
            customer_id=order["customer_id"],
        )

        if payment_record["status"] == "SUCCESS":
            order["status"] = "PAID"
        else:
            order["status"] = "PAYMENT_FAILED"

        db.save_transaction(order_id, order)
        return order
