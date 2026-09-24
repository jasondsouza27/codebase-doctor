# AI Codebase Doctor — Technical Interview Mastery Guide

This guide gives you the exact script, architectural explanations, and defense answers you need to explain this project to technical interviewers, hiring managers, and system architects.

---

## 1. The 30-Second Elevator Pitch

> *"I built **AI Codebase Doctor**, an autonomous architectural intelligence system designed for large, 5-to-10-year-old legacy codebases.*
>
> *When a developer asks: **'If I modify this authentication function or payment service, what else could break?'**, they normally spend hours grepping through thousands of files. My system connects to a repository, parses the Abstract Syntax Tree to extract classes, calls, and imports, and constructs a directed Code Knowledge Graph.*
>
> *Using reverse graph traversal and PageRank centrality, it calculates the change blast radius, detects security and financial bugs, and automatically generates and executes Pytest regression tests for all affected downstream services.*
>
> *For example, when a developer modifies `payment_service.py`, the system predicts downstream impact on `OrderService`, `InvoiceService`, `RefundService`, and `NotificationService`, flags risks like float currency drift, and runs automated tests with 100% pass rates."*

---

## 2. The 3-Minute Technical Walkthrough

When the interviewer says: *"Walk me through the architecture and how you built it."*

### Structure your response in 4 distinct phases:

1. **Phase 1: Deterministic Parsing & Symbol Extraction (AST Engine)**
   - *"First, I didn't want to rely on regular expressions or pure LLMs for code understanding because regex fails on nested scopes and LLMs hallucinate symbols.*
   - *I implemented an AST visitor using Python's standard `ast` module. As it walks the syntax tree, it extracts modules, classes, functions, decorators, parameters, and McCabe cyclomatic complexity, while tracking import mappings and call expressions."*

2. **Phase 2: Topological Graph Modeling & Centrality (NetworkX DiGraph)**
   - *"Next, I model the entire codebase as a directed Knowledge Graph using NetworkX. Nodes represent symbols (classes, functions, modules), and edges represent relationships (`CALLS`, `IMPORTS`, `INHERITS`, `DEFINES`).*
   - *I run PageRank centrality over the graph. This immediately reveals which modules are the 'load-bearing pillars' of the architecture—components like `PaymentService` or `AuthService` have high centrality scores, meaning regressions there have high blast radius."*

3. **Phase 3: Change Impact Analysis & Reverse Graph Traversal**
   - *"To answer 'what could break if I modify component X?', I perform a reverse Breadth-First Search (BFS). In a call graph, if $A$ calls $B$, the edge is $A \to B$. But if $B$ changes, the components at risk are its upstream callers. By transposing the graph and traversing reverse edges, the system deterministically finds every direct caller at depth 1 and transitive callers at depth 2+.*
   - *I combine this with a weighted Blast Radius Scoring formula (0–100) taking into account affected file ratio, node ratio, and PageRank."*

4. **Phase 4: Risk Auditing, Graph-RAG, and Automated Test Execution**
   - *"Finally, the system combines static AST pattern matching for security flaws (like SQL injection or insecure tokens) and business logic flaws (like floating-point math in currency operations or missing refund bounds checks).*
   - *It uses Graph-Augmented RAG to answer developer queries by feeding both code and topological neighborhood into the context.*
   - *Then, it auto-synthesizes Pytest regression test suites targeting the identified risk areas, runs them in an isolated subprocess with mocks, and formats an executive report across CLI, Markdown, HTML, and a Streamlit dashboard."*

---

## 3. Step-by-Step Reference: What is being done & Why

| Step | What is being done? | Why is it done this way? (Interview Defense) |
| :--- | :--- | :--- |
| **1. Ingestion & Cloning** | Recursively walk repo or auto-clone GitHub URL via `git clone --depth 1`, ignore `.git`, `venv`, parse `git diff`. | Normalizes cross-platform paths; handles local dirs and remote GitHub repos identically; prevents indexing virtualenvs. |
| **2. AST Parsing** | Walk Python AST (`ast.NodeVisitor`) to extract classes, functions, calls, and imports. | AST parsing is deterministic, syntax-guaranteed, and runs in $O(N)$ time. Regex breaks on multi-line statements, and LLMs hallucinate code structure. |
| **3. Two-Pass Indexing** | Pass 1 registers all symbols; Pass 2 resolves and links dependency edges & file graph. | Resolves forward references! In single-pass parsers, if file A imports file B before B is parsed, target symbols are unknown and edges get dropped. |
| **4. Knowledge Graph** | Build `networkx.DiGraph` with typed nodes (`CLASS`, `FUNCTION`) and edges (`CALLS`, `IMPORTS`). | Represents code as a mathematical graph, allowing graph theory algorithms (BFS/DFS, PageRank, cycle detection) to run in milliseconds. |
| **5. PageRank Centrality** | Calculate PageRank scores for all symbol nodes. | Distinguishes core infrastructural services from leaf utility scripts. A change to a node with 0.05 PageRank is far riskier than one with 0.001. |
| **6. Impact Analysis** | Reverse BFS traversal on transposed graph $G^T$ using `collections.deque` and visited tracking. | Forward traversal answers *"what do I call?"*. Reverse traversal answers *"who depends on me?"*. Visited sets prevent exponential path explosion in cyclic graphs. |
| **7. Static Risk Audit** | AST inspection for float math, missing bounds checks, raw SQL, and hardcoded secrets. | Catches common production bugs statically before deployment (e.g., IEEE-754 float rounding errors in financial transactions). |
| **8. Graph-Augmented RAG** | Retrieve target symbol + its 1-hop callers and callees into LLM prompt; filter stopwords and type-rank. | Traditional vector RAG only retrieves by text similarity and has zero understanding of call stacks. Graph-RAG provides structural truth to the LLM. |
| **9. Test Generation** | Auto-generate executable Pytest files with real assertions and mocks (`unittest.mock`). | Developers often skip writing tests for legacy changes. Auto-generating tests targeting high-risk areas ensures zero regressions without dummy shortcuts. |
| **10. Test Runner** | Execute tests in an isolated subprocess and parse exit codes/stdout. | Verifies the generated tests actually run, pass, and don't introduce syntax errors or broken assertions. |
| **11. Multi-format Reporting** | Rich terminal tree, Markdown, self-contained HTML, Streamlit UI. | Makes architectural findings consumable by developers (CLI), PR reviewers (Markdown), and engineering leads (HTML/Dashboard). |

---

## 4. Tough Interview Questions & Bulletproof Answers

### Q1: "Why not just paste the whole codebase into Claude 3.5 Sonnet or Gemini 1.5 Pro with a 1M token context window?"
> **Answer**:
> *"While long-context LLMs are impressive, using them as the primary code analyzer has three major flaws:*
> 1. **Cost & Latency**: Sending 500,000 lines of code on every git commit costs dollars per run and takes 30-60 seconds. Our AST + Graph traversal runs in 200 milliseconds locally for free.
> 2. **Attention Degradation (Needle-in-a-Haystack)**: LLMs suffer from 'lost in the middle' phenomenon. In a 500-file codebase, subtle call paths 3 hops away get missed.
> 3. **Non-Determinism**: A graph traversal is mathematically deterministic. If function $A$ calls function $B$, it is a 100% guaranteed edge. An LLM might hallucinate a dependency on one run and miss it on the next.
> *Our design uses a **hybrid approach**: deterministic AST and Graph Theory for structural truth, and LLMs for semantic reasoning on the pre-filtered subgraph."*

---

### Q2: "How does your system handle Python's dynamic typing and runtime duck-typing?"
> **Answer**:
> *"Dynamic languages like Python pose a classic static analysis challenge: a variable `service` might only have its class bound at runtime.*
> *In our system, we handle this through three levels of resolution:*
> 1. **Import and Instantiation Tracking**: We track `ps = PaymentService()` inside `__init__`, mapping the attribute `self.ps` to `PaymentService`.
> 2. **Heuristic Suffix Matching**: When a call `self.gateway.charge()` is observed, we match `charge` against methods in the imported namespace.
> 3. **File-Level Graph Fallback**: If a symbol cannot be resolved to a specific method due to dynamic dispatch, we fall back to file-level dependency edges (`order_service.py` $\to$ `payment_service.py`).
> *For a production system with millions of lines, I would integrate **Tree-sitter** and Python's **Language Server Protocol (Pyright/Mypy)** to extract type-inferred semantic ASTs."*

---

### Q3: "How does this architecture scale to a 10-million-line monorepo?"
> **Answer**:
> *"At 10 million lines of code (LOC), in-memory Python dictionaries and NetworkX would consume tens of gigabytes of RAM. Here is how I would scale it:*
> 1. **Persistent Graph Database**: Replace NetworkX with **Neo4j** or **Amazon Neptune**. Graph queries (`MATCH (t:Symbol)-[:CALLS*1..3]->(dep)`) execute via indexed graph traversals in milliseconds.
> 2. **Incremental Indexing via Git Diffs**: Instead of re-parsing the entire codebase on every commit, we use a worker queue (Celery/Kafka). On git push, we only re-parse the files in `git diff --name-only HEAD~1`, updating only the changed nodes and edges in the graph.
> 3. **Distributed Parsers**: AST parsing of individual files is an embarrassingly parallel problem. We can distribute file parsing across multiple CPU cores or Kubernetes worker pods using ray or multiprocessing."*

---

### Q4: "What makes Graph-RAG better than standard Vector RAG for codebases?"
> **Answer**:
> *"Standard Vector RAG embeds text chunks into high-dimensional space and queries by cosine similarity. If you ask 'What breaks if I modify auth?', Vector RAG retrieves chunks that mention 'auth'.*
> *It will completely miss `OrderService.checkout` if `checkout` calls `verify_token` without the word 'auth' appearing in the `checkout` docstring.*
> *In contrast, **Graph-Augmented RAG** performs graph traversal first. It discovers that `OrderService.checkout` has an incoming edge to `verify_token`. It then injects this exact caller relationship into the prompt context. The LLM receives the real call graph topology, not just semantically similar words."*

---

### Q5: "How do you ensure auto-generated tests don't cause destructive side-effects like charging real credit cards or deleting databases?"
> **Answer**:
> *"Safety is paramount. In our `TestGenerator`, we employ three safeguards:*
> 1. **Automated Mocking (`unittest.mock.patch`)**: The generator inspects external dependencies (classes named `Gateway`, `Database`, `Client`, `API`) and injects mock patches around calls like `.charge()`, `.execute()`, or `.send_receipt()`.
> 2. **Ephemeral Sandboxed Execution**: Tests run in an isolated subprocess with controlled environment variables and mock databases.
> 3. **Deterministic Seed Data**: We supply synthetic fixtures (e.g. test customer IDs, mock transaction dictionaries) rather than pulling live production credentials."*

---

## 5. Suggested Evolution (What you would build in v2)

If asked: *"What would you add next?"*
1. **Multi-Language Tree-sitter Support**: Add parsers for TypeScript, Go, and Java using Tree-sitter grammar bindings.
2. **CI/CD GitHub Action Integration**: Package Codebase Doctor as a GitHub Action that posts the blast radius tree and test results directly as a PR comment.
3. **Automated Regression Repair**: If an affected downstream test fails after a change, use the LLM to auto-suggest the contract adaptation diff for the caller!
