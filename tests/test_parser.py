"""
Unit tests for CodeParser AST extraction.
"""

from pathlib import Path
from codebase_doctor.parser import CodeParser
from codebase_doctor.models import SymbolType, EdgeType


def test_parser_extracts_classes_and_functions():
    code = '''
import os
from math import sqrt

class Calculator:
    """A math helper."""
    def add(self, a: int, b: int) -> int:
        return a + b

def standalone_func(x):
    calc = Calculator()
    return calc.add(x, 2)
'''
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("dummy.py"), source_code=code)

    sym_names = {s.name: s for s in symbols}
    assert "Calculator" in sym_names
    assert sym_names["Calculator"].symbol_type == SymbolType.CLASS
    assert sym_names["Calculator"].docstring == "A math helper."

    assert "add" in sym_names
    assert sym_names["add"].symbol_type == SymbolType.METHOD
    assert sym_names["add"].parameters == ["self", "a", "b"]

    assert "standalone_func" in sym_names
    assert sym_names["standalone_func"].symbol_type == SymbolType.FUNCTION

    # Check edges
    edge_types = {e.edge_type for e in edges}
    assert EdgeType.IMPORTS in edge_types
    assert EdgeType.DEFINES in edge_types
    assert EdgeType.CALLS in edge_types or EdgeType.INSTANTIATES in edge_types


def test_parser_handles_syntax_errors_gracefully():
    code = "def broken(;: unclosed"
    parser = CodeParser(repo_root=Path("."))
    symbols, edges = parser.parse_file(Path("broken.py"), source_code=code)
    assert len(symbols) == 1
    assert "SyntaxError" in symbols[0].docstring
