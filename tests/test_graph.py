"""
Unit tests for CodeGraph data structure and graph analytics.
"""

from codebase_doctor.graph import CodeGraph
from codebase_doctor.models import DependencyEdge, EdgeType, Symbol, SymbolType


def test_graph_upstream_dependents_and_pagerank():
    graph = CodeGraph()

    # Create 3 symbols: A (calls B), B (calls C), C (core utility)
    sym_a = Symbol(name="A", qualified_name="mod.A", symbol_type=SymbolType.FUNCTION, file_path="mod.py", line_start=1, line_end=5)
    sym_b = Symbol(name="B", qualified_name="mod.B", symbol_type=SymbolType.FUNCTION, file_path="mod.py", line_start=6, line_end=10)
    sym_c = Symbol(name="C", qualified_name="mod.C", symbol_type=SymbolType.FUNCTION, file_path="mod.py", line_start=11, line_end=15)

    graph.add_symbol(sym_a)
    graph.add_symbol(sym_b)
    graph.add_symbol(sym_c)

    # A -> B, B -> C
    graph.add_edge(DependencyEdge(source="mod.A", target="mod.B", edge_type=EdgeType.CALLS))
    graph.add_edge(DependencyEdge(source="mod.B", target="mod.C", edge_type=EdgeType.CALLS))

    # Upstream of C: should find B (depth 1) and A (depth 2)
    deps = graph.get_upstream_dependents("mod.C", max_depth=3)
    dep_names = [d[0] for d in deps]

    assert "mod.B" in dep_names
    assert "mod.A" in dep_names

    # PageRank: C is called most deeply, should have high centrality
    pr = graph.compute_pagerank()
    assert pr["mod.C"] >= pr["mod.A"]


def test_graph_circular_dependency_ring_and_cycle_termination():
    """Verify that a 3-node cycle (A -> B -> C -> A) is detected and reverse BFS terminates safely."""
    graph = CodeGraph()

    sym_a = Symbol(name="A", qualified_name="pkg.a.A", symbol_type=SymbolType.CLASS, file_path="pkg/a.py", line_start=1, line_end=10)
    sym_b = Symbol(name="B", qualified_name="pkg.b.B", symbol_type=SymbolType.CLASS, file_path="pkg/b.py", line_start=1, line_end=10)
    sym_c = Symbol(name="C", qualified_name="pkg.c.C", symbol_type=SymbolType.CLASS, file_path="pkg/c.py", line_start=1, line_end=10)

    for sym in [sym_a, sym_b, sym_c]:
        graph.add_symbol(sym)

    # A -> B -> C -> A
    graph.add_edge(DependencyEdge(source="pkg.a.A", target="pkg.b.B", edge_type=EdgeType.CALLS))
    graph.add_edge(DependencyEdge(source="pkg.b.B", target="pkg.c.C", edge_type=EdgeType.CALLS))
    graph.add_edge(DependencyEdge(source="pkg.c.C", target="pkg.a.A", edge_type=EdgeType.CALLS))
    graph.rebuild_file_level_graph()

    # Cycle detection
    cycles = graph.detect_circular_dependencies()
    assert len(cycles) >= 1
    cycle_files = set(cycles[0])
    assert "pkg/a.py" in cycle_files and "pkg/b.py" in cycle_files and "pkg/c.py" in cycle_files

    # Upstream traversal on A should terminate cleanly without infinite recursion
    deps = graph.get_upstream_dependents("pkg.a.A", max_depth=5)
    dep_names = [d[0] for d in deps]
    assert "pkg.c.C" in dep_names
    assert "pkg.b.B" in dep_names
    assert "pkg.a.A" not in dep_names  # Root should not be in dependents


def test_graph_forward_reference_resolution():
    """Verify that edges added before target symbol is registered resolve correctly via rebuild."""
    graph = CodeGraph()

    # Add source symbol
    sym_src = Symbol(name="Caller", qualified_name="caller.Caller", symbol_type=SymbolType.CLASS, file_path="caller.py", line_start=1, line_end=5)
    graph.add_symbol(sym_src)

    # Add edge pointing to Callee BEFORE Callee is registered
    graph.add_edge(DependencyEdge(source="caller.Caller", target="callee.Callee", edge_type=EdgeType.CALLS))

    # Callee file level edge is not there yet because Callee isn't known
    assert ("caller.py", "callee.py") not in graph.file_level_graph.edges

    # Now register target symbol (Callee)
    sym_tgt = Symbol(name="Callee", qualified_name="callee.Callee", symbol_type=SymbolType.CLASS, file_path="callee.py", line_start=1, line_end=5)
    graph.add_symbol(sym_tgt)

    # Rebuild file level graph
    graph.rebuild_file_level_graph()
    assert ("caller.py", "callee.py") in graph.file_level_graph.edges
