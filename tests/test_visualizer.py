"""
Unit and integration tests for GraphVisualizer (Interactive Force-Directed Graph).
"""

from pathlib import Path
from codebase_doctor.doctor import CodebaseDoctor
from codebase_doctor.models import ChangesetImpactReport, ImpactNode, ImpactReport, Symbol, SymbolType
from codebase_doctor.visualizer import GraphVisualizer


def test_visualizer_single_file_impact():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report = doctor.analyze_change("payment_service.py")
    html_out = GraphVisualizer.generate_impact_graph_html(doctor.graph, report, height=500)

    # 1. HTML structure and vis-network presence
    assert "<!DOCTYPE html>" in html_out
    assert "vis-network" in html_out
    assert 'id="network-canvas"' in html_out
    assert 'id="custom-tooltip"' in html_out

    # 2. Node styling: Ground Zero (Red), Depth 1 (Orange)
    assert "#ef4444" in html_out  # Red Ground Zero
    assert "#f97316" in html_out  # Orange Depth 1

    # 3. Tooltips include required metadata
    assert "Cyclomatic Complexity" in html_out
    assert "Language:" in html_out
    assert "Risk Flags:" in html_out
    assert "Lines:" in html_out

    # 4. Interactive controls present
    assert "btn-physics" in html_out
    assert "btn-zoom-in" in html_out
    assert "btn-fit" in html_out
    assert "node-search" in html_out


def test_visualizer_changeset_impact():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    cs_report = doctor.impact_analyzer.analyze_changeset(
        changed_files=["payment_service.py", "order_service.py"]
    )

    html_out = GraphVisualizer.generate_impact_graph_html(doctor.graph, cs_report, height=520)

    assert "<!DOCTYPE html>" in html_out
    assert "payment_service.py" in html_out or "PaymentService" in html_out
    assert "order_service.py" in html_out or "OrderService" in html_out

    # Both changed files should be Ground Zero (Red)
    assert "#ef4444" in html_out

    # Downstream dependents should be in Orange or Yellow
    assert "#f97316" in html_out or "#eab308" in html_out


def test_visualizer_architecture_graph():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    arch_html = GraphVisualizer.generate_architecture_graph_html(doctor.graph, height=600)

    assert "<!DOCTYPE html>" in arch_html
    assert "vis-network" in arch_html
    assert "network-canvas" in arch_html
    assert "PageRank" in arch_html


def test_visualizer_filters_external_stdlib_and_separates_tiers():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report = doctor.analyze_change("payment_service.py")
    html_out = GraphVisualizer.generate_impact_graph_html(doctor.graph, report, height=500)

    import json
    import re
    m = re.search(r"var rawNodes = (\[.*?\]);", html_out)
    assert m is not None
    nodes = json.loads(m.group(1))

    node_ids = [n["id"] for n in nodes]
    # No standard library types in graph nodes
    assert "typing.Any" not in node_ids
    assert "typing.Dict" not in node_ids
    assert "typing.Optional" not in node_ids
    assert "__init__" not in node_ids

    # Direct dependents must have group 'depth_1' and NOT 'surrounding'
    groups_by_id = {n["id"]: n["group"] for n in nodes}
    assert groups_by_id.get("InvoiceService") == "depth_1"
    assert groups_by_id.get("OrderService") == "depth_1"
    assert groups_by_id.get("NotificationService") == "depth_1"
    assert groups_by_id.get("RefundService") == "depth_1"


def test_visualizer_empty_report():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    empty_report = doctor.impact_analyzer.analyze_changeset(changed_files=[])
    html_out = GraphVisualizer.generate_impact_graph_html(doctor.graph, empty_report, height=500)
    assert "<!DOCTYPE html>" in html_out
    assert "No Components in Graph" in html_out or "No modified or impacted" in html_out
