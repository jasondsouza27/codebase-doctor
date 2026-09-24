"""
Unit and integration tests for Git Diff and Changeset Blast Radius Analysis.
"""

import subprocess
from pathlib import Path
from click.testing import CliRunner

from codebase_doctor.cli import main
from codebase_doctor.doctor import CodebaseDoctor
from codebase_doctor.models import ChangesetImpactReport
from codebase_doctor.repo_manager import RepoManager


def _init_git_repo(path: Path):
    """Helper to initialize a real git repo in a temporary directory."""
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(path), capture_output=True, check=True)


def test_repo_manager_git_operations(tmp_path):
    repo_dir = tmp_path / "test_git_repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    file_a = repo_dir / "service_a.py"
    file_a.write_text("def func_a():\n    return 42\n", encoding="utf-8")

    # Initial commit
    subprocess.run(["git", "add", "service_a.py"], cwd=str(repo_dir), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), capture_output=True, check=True)

    mgr = RepoManager(str(repo_dir))
    assert mgr.is_git_repo() is True

    # 1. Clean working tree initially
    changed_clean = mgr.get_changed_files()
    assert len(changed_clean) == 0 or "service_a.py" in changed_clean

    # 2. Modify service_a.py (unstaged)
    file_a.write_text("def func_a():\n    return 99\n\ndef new_func():\n    pass\n", encoding="utf-8")
    changed_unstaged = mgr.get_changed_files()
    assert "service_a.py" in changed_unstaged

    # 3. Verify git diff text
    diff_text = mgr.get_git_diff()
    assert "return 99" in diff_text or "new_func" in diff_text

    # 4. Verify diff stats
    stats = mgr.get_diff_stats()
    assert stats["files_changed"] >= 1 or stats["insertions"] >= 1

    # 5. Untracked file
    file_b = repo_dir / "service_b.py"
    file_b.write_text("def func_b():\n    pass\n", encoding="utf-8")
    changed_with_untracked = mgr.get_changed_files(include_untracked=True)
    assert "service_b.py" in changed_with_untracked


def test_changeset_blast_radius_multi_file_aggregation():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    # Modify both payment_service.py and order_service.py
    cs_report = doctor.impact_analyzer.analyze_changeset(
        changed_files=["payment_service.py", "order_service.py"]
    )

    assert isinstance(cs_report, ChangesetImpactReport)
    assert len(cs_report.changed_files) == 2
    assert "payment_service.py" in cs_report.changed_files
    assert "order_service.py" in cs_report.changed_files

    # OrderService is a modified target, so it must NOT be a downstream casualty
    downstream_names = [c.symbol_name.lower() for c in cs_report.affected_components]
    assert "orderservice" not in downstream_names
    assert "paymentservice" not in downstream_names

    # InvoiceService is a dependent of PaymentService, so it should be in affected components
    assert any("invoice" in c.symbol_name.lower() or "invoiceservice" in c.symbol_name.lower() for c in cs_report.affected_components)

    # Aggregated blast radius score must be higher than 0 and bounded
    assert 0 < cs_report.blast_radius_score <= 100

    # Risk areas should combine payment risks
    assert any("currency" in r.lower() or "refund" in r.lower() for r in cs_report.risk_areas)

    # Suggested tests should be generated
    assert len(cs_report.suggested_tests) >= 3

    # Format changeset tree
    tree_text = doctor.impact_analyzer.format_changeset_tree(cs_report)
    assert "Changeset" in tree_text
    assert "payment_service" in tree_text or "order_service" in tree_text


def test_doctor_analyze_diff_and_pr_markdown(tmp_path):
    repo_dir = tmp_path / "pr_test_repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    f_pay = repo_dir / "payment_service.py"
    f_pay.write_text("""
class PaymentService:
    def process_payment(self, amount: float):
        return {"status": "SUCCESS", "amount": amount}
""", encoding="utf-8")

    f_order = repo_dir / "order_service.py"
    f_order.write_text("""
from payment_service import PaymentService

class OrderService:
    def place_order(self, total: float):
        ps = PaymentService()
        return ps.process_payment(total)
""", encoding="utf-8")

    subprocess.run(["git", "add", "."], cwd=str(repo_dir), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), capture_output=True, check=True)

    # Make uncommitted modifications
    f_pay.write_text("""
class PaymentService:
    def process_payment(self, amount: float):
        # Modified logic
        tax = amount * 0.15
        return {"status": "SUCCESS", "amount": amount + tax}
""", encoding="utf-8")

    doctor = CodebaseDoctor(repo_path=str(repo_dir))
    report, exec_res = doctor.analyze_diff(run_tests=False)

    assert "payment_service.py" in report.changed_files
    assert any("order" in c.symbol_name.lower() or "order" in c.file_path.lower() for c in report.affected_components)

    # PR comment generation
    pr_md = doctor.generate_pr_markdown(report, exec_res)
    assert "# AI Codebase Doctor - PR Blast Radius Assessment" in pr_md
    assert "payment_service.py" in pr_md
    assert "Blast Radius" in pr_md
    assert "Reviewer Recommendations" in pr_md


def test_cli_diff_command(tmp_path):
    runner = CliRunner()

    # 1. Non-git repo
    res_non_git = runner.invoke(main, ["diff", "--repo", str(tmp_path)])
    assert "Not a git repository" in res_non_git.output or res_non_git.exit_code == 0

    # 2. Git repo with modifications
    repo_dir = tmp_path / "cli_git_repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    code_file = repo_dir / "calc.py"
    code_file.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=str(repo_dir), capture_output=True, check=True)

    # Modify calc.py
    code_file.write_text("def add(a, b): return a + b + 1\n", encoding="utf-8")

    pr_out_path = repo_dir / "pr_comment.md"
    result = runner.invoke(main, [
        "diff",
        "--repo", str(repo_dir),
        "--no-tests",
        "--export-pr", str(pr_out_path),
    ])

    assert result.exit_code == 0
    assert pr_out_path.exists()
    pr_content = pr_out_path.read_text(encoding="utf-8")
    assert "calc.py" in pr_content
    assert "Blast Radius" in pr_content


def test_invalid_base_ref_handling(tmp_path):
    repo_dir = tmp_path / "invalid_base_repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    code_file = repo_dir / "app.py"
    code_file.write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=str(repo_dir), capture_output=True, check=True)

    mgr = RepoManager(str(repo_dir))
    import pytest
    with pytest.raises(ValueError) as excinfo:
        mgr.get_changed_files(base_ref="non_existent_branch_xyz")
    assert "non_existent_branch_xyz" in str(excinfo.value)

    # CLI diff with invalid base prints error and exits cleanly
    runner = CliRunner()
    res = runner.invoke(main, ["diff", "--repo", str(repo_dir), "--base", "non_existent_branch_xyz"])
    assert res.exit_code == 0
    assert "not found or invalid" in res.output or "non_existent_branch_xyz" in res.output


def test_doctor_analyze_diff_changed_files_override():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report, _ = doctor.analyze_diff(changed_files=["payment_service.py", "order_service.py"])
    assert len(report.changed_files) == 2
    assert "payment_service.py" in report.changed_files
    assert "order_service.py" in report.changed_files

    # to_dict compatibility
    rep_dict = report.to_dict()
    assert "target_file" in rep_dict
    assert "payment_service.py" in rep_dict["target_file"]
