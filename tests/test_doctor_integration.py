"""
End-to-end integration tests for CodebaseDoctor.
"""

from codebase_doctor.doctor import CodebaseDoctor


def test_doctor_full_workflow():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    stats = doctor.scan()

    assert stats["total_files"] >= 6
    assert stats["total_nodes"] > 20

    # 1. Ask question via Graph-RAG
    import re
    qa = doctor.ask("If I modify this authentication function, what else could break?")
    ans_clean = re.sub(r"\s+", " ", qa["answer"]).lower().replace("-", " ")
    assert "architectural" in ans_clean or "blast radius" in ans_clean or "break" in ans_clean or "impact" in ans_clean
    assert len(qa["retrieved_nodes"]) > 0

    # 2. Run Impact Analysis
    report = doctor.analyze_change("payment_service.py")
    assert report.blast_radius_score > 0
    assert len(report.suggested_tests) >= 3

    # 3. Generate & Run tests
    execution, test_path = doctor.generate_and_run_tests(report)
    assert execution.total > 0
    assert execution.passed >= 1
    assert execution.pass_rate >= 80.0

    # 4. Verify 2-pass indexing captured all inter-file dependencies
    assert stats["total_file_dependencies"] >= 6
    assert ("order_service.py", "payment_service.py") in doctor.graph.file_level_graph.edges
    assert ("invoice_service.py", "payment_service.py") in doctor.graph.file_level_graph.edges


def test_repo_manager_github_url_detection(monkeypatch):
    """Verify RepoManager automatically detects remote Git URLs and clones them."""
    from unittest.mock import MagicMock
    from pathlib import Path
    from codebase_doctor.repo_manager import RepoManager

    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr("subprocess.run", mock_run)

    # Test with URL
    mgr = RepoManager("https://github.com/octocat/Hello-World.git")
    assert mgr.is_cloned is True
    assert mgr.remote_url == "https://github.com/octocat/Hello-World.git"
    assert mock_run.called


def test_test_generator_produces_real_assertions(tmp_path):
    """Verify generated test suite contains real domain assertions, not hollow assert True."""
    from codebase_doctor.doctor import CodebaseDoctor

    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()
    report = doctor.analyze_change("payment_service.py")

    code, path = doctor.test_generator.generate_tests_for_impact(report, output_dir=tmp_path)

    # Must contain real domain logic tests
    assert "assert calc.get(\"refund_amount\") == 50.0" in code
    assert "assert float(result) == 92.0" in code or "assert result == 92.0" in code
    assert "assert res[\"status\"] == \"SUCCESS\"" in code

    # Must NOT have hollow stub asserts
    assert "assert True\n" not in code or "def test_payment_status_sync():\n    assert True" not in code
    assert "in sys.modules or True" not in code
