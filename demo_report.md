# AI Codebase Doctor Report: `payment_service.py`

**Target Symbol**: `PaymentService`  
**Blast Radius Score**: `52.0 / 100`  
**Files Impacted**: `4`  

## Potentially Affected Components
```text
PaymentService
 ├── InvoiceService
 ├── NotificationService
 ├── OrderService
 └── RefundService
```

## Risk Areas
- **Currency conversion**
- **Refund calculation**
- **Payment status synchronization**

## Suggested Tests
- [x] `test_refund_after_partial_payment`
- [x] `test_currency_conversion`
- [x] `test_failed_payment_retry`
- [x] `test_payment_status_sync`
- [x] `test_invoice_service_integration_with_paymentservice`
- [x] `test_notification_service_integration_with_paymentservice`

## Automated Test Execution Results
**Passed**: `6/6` | **Duration**: `1.065s`

| Test Function | Status | Error |
| :--- | :--- | :--- |
| `test_refund_after_partial_payment` | PASS | - |
| `test_currency_conversion` | PASS | - |
| `test_failed_payment_retry` | PASS | - |
| `test_payment_status_sync` | PASS | - |
| `test_invoice_service_integration_with_paymentservice` | PASS | - |
| `test_notification_service_integration_with_paymentservice` | PASS | - |