"""
Unit and integration tests for incremental indexing and delta scanning.
"""

from pathlib import Path
from codebase_doctor.doctor import CodebaseDoctor
from codebase_doctor.graph import CodeGraph
from codebase_doctor.models import DependencyEdge, EdgeType, Symbol, SymbolType
from codebase_doctor.repo_manager import RepoManager


def test_repo_manager_hashing_and_incremental_changes(tmp_path):
    mgr = RepoManager(str(tmp_path))

    file_a = tmp_path / "service_a.py"
    file_b = tmp_path / "service_b.py"

    file_a.write_text("def func_a(): pass\n", encoding="utf-8")
    file_b.write_text("def func_b(): pass\n", encoding="utf-8")

    initial_state = mgr.get_file_state()
    assert "service_a.py" in initial_state
    assert "service_b.py" in initial_state

    # 1. No changes
    changes = mgr.get_incremental_changes(initial_state)
    assert changes["added"] == []
    assert changes["modified"] == []
    assert changes["deleted"] == []
    assert len(changes["unchanged"]) == 2

    # 2. Modify service_a
    file_a.write_text("def func_a_v2(): pass\n", encoding="utf-8")
    changes_mod = mgr.get_incremental_changes(initial_state)
    assert changes_mod["modified"] == ["service_a.py"]
    assert changes_mod["unchanged"] == ["service_b.py"]

    # 3. Add service_c
    file_c = tmp_path / "service_c.py"
    file_c.write_text("def func_c(): pass\n", encoding="utf-8")
    changes_add = mgr.get_incremental_changes(initial_state)
    assert "service_c.py" in changes_add["added"]

    # 4. Delete service_b
    file_b.unlink()
    changes_del = mgr.get_incremental_changes(initial_state)
    assert "service_b.py" in changes_del["deleted"]


def test_code_graph_remove_file():
    graph = CodeGraph()

    sym_a = Symbol(
        name="func_a",
        qualified_name="service_a.func_a",
        symbol_type=SymbolType.FUNCTION,
        file_path="service_a.py",
        line_start=1,
        line_end=5,
    )
    sym_b = Symbol(
        name="func_b",
        qualified_name="service_b.func_b",
        symbol_type=SymbolType.FUNCTION,
        file_path="service_b.py",
        line_start=1,
        line_end=5,
    )

    graph.add_symbol(sym_a)
    graph.add_symbol(sym_b)
    graph.add_edge(
        DependencyEdge(
            source="service_a.func_a",
            target="service_b.func_b",
            edge_type=EdgeType.CALLS,
            line_number=2,
        )
    )

    assert graph.graph.has_node("service_a.func_a")
    assert graph.graph.has_node("service_b.func_b")
    assert graph.file_level_graph.has_node("service_a.py")
    assert graph.file_level_graph.has_node("service_b.py")

    # Remove service_a.py
    graph.remove_file("service_a.py")

    assert not graph.graph.has_node("service_a.func_a")
    assert "service_a.func_a" not in graph.symbols_by_name
    assert "service_a.py" not in graph.symbols_by_file
    assert not graph.file_level_graph.has_node("service_a.py")

    # Target symbol service_b remains intact
    assert graph.graph.has_node("service_b.func_b")
    assert graph.file_level_graph.has_node("service_b.py")


def test_doctor_incremental_workflow(tmp_path):
    # Setup isolated test repository
    file_main = tmp_path / "main.py"
    file_util = tmp_path / "util.py"

    file_main.write_text(
        "import util\ndef run():\n    return util.compute()\n",
        encoding="utf-8",
    )
    file_util.write_text(
        "def compute():\n    return 42\n",
        encoding="utf-8",
    )

    doctor = CodebaseDoctor(repo_path=str(tmp_path))

    # 1. Initial full scan
    stats1 = doctor.scan()
    assert stats1["incremental"] is False
    assert stats1["total_files"] == 2
    assert "util.compute" in doctor.graph.symbols_by_name
    assert "main.run" in doctor.graph.symbols_by_name

    # 2. Re-scan with no changes
    stats2 = doctor.scan(incremental=True)
    assert stats2["incremental"] is True
    assert stats2["changed"] is False
    assert stats2["unchanged"] == 2
    assert stats2["added"] == 0
    assert stats2["modified"] == 0

    # 3. Add a new file
    file_new = tmp_path / "extra.py"
    file_new.write_text("def helper(): pass\n", encoding="utf-8")

    stats3 = doctor.scan(incremental=True)
    assert stats3["incremental"] is True
    assert stats3["changed"] is True
    assert stats3["added"] == 1
    assert stats3["modified"] == 0
    assert "extra.helper" in doctor.graph.symbols_by_name

    # 4. Modify util.py
    file_util.write_text(
        "def compute_v2():\n    return 100\n",
        encoding="utf-8",
    )
    stats4 = doctor.scan(incremental=True)
    assert stats4["incremental"] is True
    assert stats4["changed"] is True
    assert stats4["modified"] == 1
    assert "util.compute_v2" in doctor.graph.symbols_by_name
    assert "util.compute" not in doctor.graph.symbols_by_name

    # 5. Delete extra.py
    file_new.unlink()
    stats5 = doctor.scan(incremental=True)
    assert stats5["incremental"] is True
    assert stats5["changed"] is True
    assert stats5["deleted"] == 1
    assert "extra.helper" not in doctor.graph.symbols_by_name
