"""
Existing legacy test suite for demo_repo services.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from payment_service import PaymentService
from order_service import OrderService


def test_payment_service_basic():
    ps = PaymentService()
    res = ps.process_payment(100.0, "USD", "cust_1")
    assert res["status"] == "SUCCESS"


def test_order_service_checkout():
    os_service = OrderService()
    order = os_service.create_order("cust_1", [{"name": "book", "price": 25.0, "qty": 2}])
    assert order["status"] == "CREATED"
    final_order = os_service.checkout(order["order_id"])
    assert final_order["status"] == "PAID"
