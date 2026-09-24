# AI Codebase Doctor — Architectural Specification

This document details the internal architecture, mathematical formulations, algorithms, and design choices powering **AI Codebase Doctor**.

---

## 1. System High-Level Topology

```text
                                  ┌────────────────────────┐
                                  │  Git Repository Source │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │      RepoManager       │
                                  │ (Path normalization,  │
                                  │  git diff, file tree)  │
                                  └───────────┬────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │       CodeParser       │
                                  │  (Python AST Visitor)  │
                                  └───────────┬────────────┘
                                              │
                        ┌─────────────────────┴─────────────────────┐
                        │ Symbols & Local Dependency Edges          │
                        ▼                                           ▼
            ┌────────────────────────┐                  ┌───────────────────────┐
            │       CodeGraph        │                  │     RiskAnalyzer      │
            │  (NetworkX MultiDiGraph)│                  │ (AST & Regex Rules)   │
            └───────────┬────────────┘                  └───────────┬───────────┘
                        │                                           │
            ┌───────────┴────────────┐                              │
            │ Reverse BFS Traversal  │                              │
            ▼                        ▼                              │
┌────────────────────────┐ ┌──────────────────────┐                 │
│     ImpactAnalyzer     │ │       GraphRAG       │                 │
│ (Blast Radius & Tree)  │ │ (Topology + Context) │                 │
└───────────┬────────────┘ └──────────┬───────────┘                 │
            │                         │                             │
            └───────────┬─────────────┘                             │
                        │                                           │
                        ▼                                           │
            ┌────────────────────────┐                              │
            │     TestGenerator      │                              │
            │  (Targeted Pytest)     │                              │
            └───────────┬────────────┘                              │
                        │                                           │
                        ▼                                           │
            ┌────────────────────────┐                              │
            │       TestRunner       │                              │
            │ (Isolated Subprocess)  │                              │
            └───────────┬────────────┘                              │
                        │                                           │
                        └─────────────────────┬─────────────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │    ReportGenerator     │
                                  │ (Rich CLI / MD / HTML) │
                                  └────────────────────────┘
```

---

## 2. Deep Dive: Component by Component

### Component 1: Repository Discovery & Ingestion (`repo_manager.py`)
- **Responsibility**: Ingests either a local path or remotely clones a GitHub repo.
- **Key Operations**:
  - Filters out virtualenvs, node_modules, build artifacts, and hidden cache directories.
  - Normalizes OS-dependent paths (forward slashes) to ensure cross-platform reproducibility (Windows/Linux/macOS).
  - Inspects `git diff` to identify modified files on active working branches or staging areas.

### Component 2: Polyglot AST & Grammar Code Parser (`parser.py`)
- **Multi-Language Design**:
  - Python: AST visitor extracting imports, classes, functions, methods, calls, decorators, and cyclomatic complexity.
  - C / C++ / Embedded / Arduino: Grammar parser extracting `#include` directives, structs, classes, Arduino hooks (`setup()`, `loop()`), hardware calls (`Serial.print()`, `WiFi.begin()`).
  - JavaScript / TypeScript: Scanner extracting ES6 / CommonJS imports (`import`, `require`), classes (`class X extends Y`), async/arrow functions, and calls.
  - Java / Kotlin: Extracting packages, imports, classes, interfaces, methods, and calls.
  - Go: Extracting packages, imports, structs, interfaces, methods with receivers, and calls.
  - SQL: DDL/DML parser extracting `CREATE TABLE`, `CREATE VIEW`, `PROCEDURE`, and relational foreign key dependencies.
  - Shell / Scripts: Extracting `source` imports and shell function declarations.
- **Why Grammar & AST over LLMs alone?**
  - Deterministic $O(N)$ speed with zero token cost.
  - Never hallucinates symbols or edge relationships.
  - Scales across massive legacy multi-language repos.

### Component 3: Code Knowledge Graph (`graph.py`)
- **Data Structure**: `networkx.DiGraph` representing a directed multigraph $G = (V, E)$.
- **Node Set $V$**:
  - Code symbols: Modules, Classes, Functions, Methods, Test cases.
  - Node attributes: `file_path`, `line_start`, `line_end`, `complexity`, `docstring`.
- **Edge Set $E$**:
  - `IMPORTS`: $(M_1, M_2)$
  - `DEFINES`: $(M, C)$ or $(C, F)$
  - `CALLS`: $(F_1, F_2)$
  - `INHERITS`: $(C_1, C_2)$
  - `INSTANTIATES`: $(F, C)$
- **PageRank Centrality**:
  $$\text{PR}(u) = \frac{1 - d}{|V|} + d \sum_{v \in B_u} \frac{\text{PR}(v)}{L(v)}$$
  Identifies architectural core bottlenecks (e.g. `PaymentService` or `database.db`) vs leaf utility scripts.

### Component 4: Change Impact Analysis ("Blast Radius Engine") (`impact.py`)
- **Upstream Traversal (Reverse BFS)**:
  - In a standard call graph, if function $A$ calls $B$, directed edge is $A \to B$.
  - When modifying $B$, the affected components are the **callers** of $B$.
  - We transpose graph $G \to G^T$ and execute a depth-limited Breadth-First Search (BFS) up to depth $k$:
    $$\text{Reachable}(B) = \{ u \in V \mid \exists \text{ path from } B \text{ to } u \text{ in } G^T \}$$
- **Blast Radius Scoring Formula**:
  $$\text{Score} = \min\left(98.0, \; w_1 \frac{|F_{\text{impact}}|}{|F_{\text{total}}|} + w_2 \frac{|V_{\text{impact}}|}{|V_{\text{total}}|} + w_3 \cdot \text{PR}(T) + w_4 \cdot |V_{\text{impact}}|\right)$$
  - Yields a normalized score between 0.0 and 100.0 categorized into Low, Medium, High, and Critical risk tiers.

### Component 5: Risk & Security Analyzer (`risk_analyzer.py`)
Combines static AST pattern checking with domain heuristics:
1. **Security Vulnerabilities**:
   - Hardcoded tokens/secrets via regex heuristics.
   - SQL injection via unparameterized f-string queries in database execute calls.
   - Insecure deserialization via `pickle.loads`.
   - Command injection via `os.system`.
   - Cryptographically weak random number generators (`random` vs `secrets`).
2. **Business Logic Flaws**:
   - **Float Precision in Currency**: Detects floating-point arithmetic on currency variables, recommending `decimal.Decimal`.
   - **Refund Bounds Violations**: Inspects refund handler functions for missing bounds checks against original transaction amount.
   - **State Desynchronization**: Identifies ambiguous transaction status handling across exceptions.

### Component 6: Graph-Augmented RAG (`rag.py` & `llm_provider.py`)
- **Why Traditional Vector RAG Fails on Code**:
  - Vector similarity only matches text embeddings (cosine distance). It has zero concept of caller hierarchy, inheritance, or transitive dependencies.
- **Graph-RAG Solution**:
  1. Identifies query symbols.
  2. Extracts immediate graph neighborhood ($1$-hop callees, $2$-hop reverse callers, upstream blast radius).
  3. Fuses topological structural context with source code snippets.
  4. Prompt provides deterministic architectural facts to the LLM (or offline heuristic engine), eliminating hallucinations.

### Component 7: Automated Test Suite Generator & Runner (`test_generator.py` & `test_runner.py`)
- Synthesizes clean Pytest test cases targeting identified risk areas:
  - `test_refund_after_partial_payment`: tests boundary condition on refund reversal.
  - `test_currency_conversion`: tests precision invariance across exchange rates.
  - `test_failed_payment_retry`: tests state machine failure transition.
  - Downstream integration tests: tests caller contracts.
- Uses `unittest.mock` to stub network gateways and databases for deterministic execution.
- Invokes `pytest` in an isolated subprocess with PYTHONPATH properly bound, parses JSON/stdout results, and outputs pass/fail metrics.
