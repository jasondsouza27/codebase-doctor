"""
Unit tests for RiskAnalyzer static security and business logic checks.
"""

from codebase_doctor.risk_analyzer import RiskAnalyzer
from codebase_doctor.models import RiskCategory, RiskSeverity


def test_risk_analyzer_detects_secrets():
    code = 'API_KEY = "sk_live_1234567890abcdef12345"'
    analyzer = RiskAnalyzer()
    risks = analyzer.analyze_file("config.py", code)
    assert any("secret" in r.title.lower() or "credentials" in r.description.lower() for r in risks)


def test_risk_analyzer_detects_sql_injection():
    code = '''
def find_user(user_id):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    cursor.execute(f"SELECT * FROM accounts WHERE id = {user_id}")
'''
    analyzer = RiskAnalyzer()
    risks = analyzer.analyze_file("dao.py", code)
    assert any("sql" in r.title.lower() for r in risks)


def test_risk_analyzer_detects_currency_float_math():
    code = '''
def calculate_tax(amount):
    return amount * 1.0825
'''
    analyzer = RiskAnalyzer()
    risks = analyzer.analyze_file("payment_service.py", code)
    assert any("currency" in r.title.lower() or "float" in r.title.lower() for r in risks)


def test_risk_analyzer_detects_command_injection():
    code = '''
import os
def run_cmd(user_input):
    os.system(user_input)
'''
    analyzer = RiskAnalyzer()
    risks = analyzer.analyze_file("runner.py", code)
    assert any("command" in r.title.lower() for r in risks)
