"""
AI Codebase Doctor
A deep code intelligence system that parses codebases, builds dependency graphs,
predicts change blast radiuses, finds risks, and auto-generates & runs tests.
"""

__version__ = "1.0.0"

from codebase_doctor.doctor import CodebaseDoctor
from codebase_doctor.graph import CodeGraph
from codebase_doctor.impact import ImpactAnalyzer
from codebase_doctor.models import (
    DependencyEdge,
    EdgeType,
    ImpactNode,
    ImpactReport,
    ChangesetImpactReport,
    RiskCategory,
    RiskItem,
    RiskSeverity,
    Symbol,
    SymbolType,
    TestResult,
    TestSuiteExecution,
)
from codebase_doctor.parser import CodeParser
from codebase_doctor.rag import GraphRAG
from codebase_doctor.repo_manager import RepoManager
from codebase_doctor.risk_analyzer import RiskAnalyzer
from codebase_doctor.test_generator import TestGenerator
from codebase_doctor.test_runner import TestRunner
from codebase_doctor.visualizer import GraphVisualizer

__all__ = [
    "CodebaseDoctor",
    "RepoManager",
    "CodeParser",
    "CodeGraph",
    "ImpactAnalyzer",
    "RiskAnalyzer",
    "GraphRAG",
    "TestGenerator",
    "TestRunner",
    "GraphVisualizer",
    "Symbol",
    "SymbolType",
    "EdgeType",
    "DependencyEdge",
    "RiskItem",
    "RiskCategory",
    "RiskSeverity",
    "ImpactNode",
    "ImpactReport",
    "ChangesetImpactReport",
    "TestResult",
    "TestSuiteExecution",
]
