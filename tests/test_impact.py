"""
Unit tests for ImpactAnalyzer.
"""

from codebase_doctor.doctor import CodebaseDoctor


def test_impact_analyzer_demo_repo():
    doctor = CodebaseDoctor(repo_path="demo_repo")
    doctor.scan()

    report = doctor.analyze_change("payment_service.py")

    assert report.target_symbols[0] == "PaymentService"
    assert report.blast_radius_score > 30.0

    # Ensure high-level dependents exist
    comp_names = [c.symbol_name for c in report.affected_components]
    file_stems = [f for f in report.affected_files]

    assert any("order" in str(f).lower() for f in file_stems)
    assert any("invoice" in str(f).lower() for f in file_stems)

    # Risk areas
    assert "Currency conversion" in report.risk_areas
    assert "Refund calculation" in report.risk_areas

    # Suggested tests
    assert "test_refund_after_partial_payment" in report.suggested_tests
    assert "test_currency_conversion" in report.suggested_tests
