# AI Codebase Doctor

> **Autonomous architectural intelligence for legacy codebases.**
> Predict change blast radiuses, detect hidden security/financial risks, answer architectural questions with Graph-RAG, and auto-generate & run regression tests.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests Passing](https://img.shields.io/badge/tests-44%20passed-brightgreen.svg)]()

---

## The Real-World Problem

In 5–10 year-old enterprise codebases, when a developer asks:
> *"If I modify this authentication function or payment service, what else could break?"*

Normally, engineers must manually grep through hundreds of files, trace mental call stacks, or pray their integration tests catch regressions.

**AI Codebase Doctor** solves this deterministically. It connects to any Git repository, builds a multi-level Code Knowledge Graph using AST parsing, calculates the exact blast radius of a change using reverse graph traversal, discovers domain/security risks, auto-generates executable Pytest suites for affected callers, and runs them automatically.

---

## Quick Demo

```bash
python -m codebase_doctor.cli impact payment_service.py --repo demo_repo
```

### System Response:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ AI Codebase Doctor - Impact & Risk Analysis                                 │
│ Target: payment_service.py (PaymentService)                                 │
│ Blast Radius Score: 64.8 / 100                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Potentially affected:
PaymentService
├── RefundService
├── InvoiceService
├── NotificationService
└── OrderService

Risk areas:
 - Currency conversion
 - Payment status synchronization
 - Refund calculation

Suggested tests:
 ✓ test_refund_after_partial_payment
 ✓ test_currency_conversion
 ✓ test_failed_payment_retry
 ✓ test_payment_status_sync_on_network_timeout
 ✓ test_refundservice_integration_with_paymentservice
 ✓ test_invoice_service_integration_with_paymentservice

Automated Test Execution Results:
                   Pytest Execution: 6/6 Passed (0.846s)                   
┌──────────────────────────────────────────────────────┬────────┬─────────┐
│ Test Case                                            │ Status │ Message │
├──────────────────────────────────────────────────────┼────────┼─────────┤
│ test_refund_after_partial_payment                    │ PASSED │ OK      │
│ test_currency_conversion                             │ PASSED │ OK      │
│ test_failed_payment_retry                            │ PASSED │ OK      │
│ test_payment_status_sync                             │ PASSED │ OK      │
│ test_refundservice_integration_with_paymentservice   │ PASSED │ OK      │
│ test_invoice_service_integration_with_paymentservice │ PASSED │ OK      │
└──────────────────────────────────────────────────────┴────────┴─────────┘
```

---

## Architectural Pipeline

```text
┌─────────────────────────┐
│ Git Repo / Local Folder │
└────────────┬────────────┘
             │ 1. Repository Discovery & Ingestion
             ▼
┌─────────────────────────┐
│   AST Semantic Parser   │ ➔ Extracts Classes, Methods, Calls, Imports,
└────────────┬────────────┘   Complexity (McCabe), & Docstrings
             │ 2. Symbol & Edge Resolution
             ▼
┌─────────────────────────┐
│   Code Knowledge Graph  │ ➔ Directed Graph (NetworkX), PageRank Centrality,
└────────────┬────────────┘   Circular Dependency Detection
             │ 3. Reverse Graph BFS Traversal
             ▼
┌─────────────────────────┐
│  Impact & Blast Radius  │ ➔ Identifies direct & transitive callers,
│         Engine          │   calculates Blast Radius Score (0-100)
└────────────┬────────────┘
             │ 4. Static & Heuristic Scan
             ▼
┌─────────────────────────┐
│  Risk & Bug Analyzer    │ ➔ Detects SQL Injection, Float Currency Drift,
└────────────┬────────────┘   Refund Bound Flaws, Silent Error Suppression
             │ 5. Automated Generation
             ▼
┌─────────────────────────┐
│   Test Suite Generator  │ ➔ Produces self-contained Pytest suites targeting
└────────────┬────────────┘   risk areas with unit mocks
             │ 6. Subprocess Execution
             ▼
┌─────────────────────────┐
│   Pytest Test Runner    │ ➔ Executes generated tests, captures stdout/err,
└────────────┬────────────┘   records pass/fail metrics
             │ 7. Multi-Channel Output
             ▼
┌───────────────────────────────────────────────────┐
│  Rich CLI  |  Markdown / HTML  |  Streamlit App   │
└───────────────────────────────────────────────────┘
```

---

## Getting Started

### 1. Installation

```bash
git clone https://github.com/your-org/codebase-doctor.git
cd "codebase knowledge graph"
pip install -r requirements.txt
```

### 2. Run CLI Commands

#### Scan Codebase Architecture & PageRank:
```bash
# Full codebase scan
python -m codebase_doctor.cli scan --repo demo_repo

# Incremental scan (only re-parses modified/added files)
python -m codebase_doctor.cli scan --repo demo_repo --incremental
```

#### Predict Blast Radius & Auto-Run Tests:
```bash
python -m codebase_doctor.cli impact payment_service.py --repo demo_repo
```

#### Export Markdown and HTML Reports:
```bash
python -m codebase_doctor.cli impact payment_service.py --repo demo_repo --export-md report.md --export-html report.html
```

#### Query Architecture via Graph-Augmented RAG:
```bash
python -m codebase_doctor.cli ask "If I modify this authentication function, what else could break?" --repo demo_repo
```

#### Scan Entire Codebase for Security & Logic Risks:
```bash
python -m codebase_doctor.cli risks --repo demo_repo
```

### 3. Launch the Interactive Web Dashboard

```bash
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser to interact with the visual dependency tree, test runner, and Graph-RAG chat. Includes instant **Full Re-Scan** and **Incremental** scan controls.

---

## Running the Test Suite

```bash
python -m pytest tests -v
```
All 44 comprehensive unit, graph, cycle, risk, Tree-sitter AST, incremental indexing, and integration tests pass deterministically.

---

## In-Depth Documentation

- [ARCHITECTURE.md](file:///c:/Users/Jason%20Dsouza/OneDrive/Desktop/codebase%20knowledge%20graph/ARCHITECTURE.md): Full deep-dive into AST visitor patterns, Graph Theory, PageRank centrality, and Graph-RAG.
- [INTERVIEW_GUIDE.md](file:///c:/Users/Jason%20Dsouza/OneDrive/Desktop/codebase%20knowledge%20graph/INTERVIEW_GUIDE.md): **Step-by-step interview script**, system design answers, scaling to 10M LOC, and trade-off defense.
