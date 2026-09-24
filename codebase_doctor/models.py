"""
Codebase Doctor - Core Data Models
Defines all domain entities for AST parsing, Graph modeling, Impact analysis, and Reporting.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SymbolType(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    TEST = "test"
    STRUCT = "struct"
    INTERFACE = "interface"
    ENUM = "enum"
    ENDPOINT = "endpoint"
    SCHEMA = "schema"
    GLOBAL = "global"


class EdgeType(str, Enum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    DEFINES = "DEFINES"
    INHERITS = "INHERITS"
    INSTANTIATES = "INSTANTIATES"
    TESTS = "TESTS"
    INCLUDES = "INCLUDES"
    REFERENCES = "REFERENCES"


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    SECURITY = "SECURITY"
    BUSINESS_LOGIC = "BUSINESS_LOGIC"
    CONCURRENCY = "CONCURRENCY"
    REGRESSION = "REGRESSION"
    ERROR_HANDLING = "ERROR_HANDLING"
    MEMORY_SAFETY = "MEMORY_SAFETY"
    HARDWARE_IOT = "HARDWARE_IOT"


@dataclass
class Symbol:
    """Represents a code symbol (Function, Class, Method, Struct, or Module)."""
    name: str
    qualified_name: str
    symbol_type: SymbolType
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    complexity: int = 1
    source_code: str = ""
    language: str = "python"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "symbol_type": self.symbol_type.value,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "docstring": self.docstring,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "decorators": self.decorators,
            "complexity": self.complexity,
            "language": self.language,
        }


@dataclass
class DependencyEdge:
    """Represents a directed relationship between two symbols."""
    source: str
    target: str
    edge_type: EdgeType
    line_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type.value,
            "line_number": self.line_number,
            "metadata": self.metadata,
        }


@dataclass
class RiskItem:
    """Represents an identified risk area, bug, or vulnerability."""
    category: RiskCategory
    severity: RiskSeverity
    title: str
    description: str
    file_path: str
    line_number: Optional[int] = None
    affected_symbol: Optional[str] = None
    remediation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "affected_symbol": self.affected_symbol,
            "remediation": self.remediation,
        }


@dataclass
class ImpactNode:
    """Represents a component impacted by a code modification."""
    symbol_name: str
    file_path: str
    symbol_type: SymbolType
    depth: int  # Distance from change source (1 = direct dependent)
    dependency_path: List[str] = field(default_factory=list)
    impact_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol_name": self.symbol_name,
            "file_path": self.file_path,
            "symbol_type": self.symbol_type.value,
            "depth": self.depth,
            "dependency_path": self.dependency_path,
            "impact_reason": self.impact_reason,
        }


@dataclass
class ImpactReport:
    """Result of analyzing the blast radius of a change."""
    target_file: str
    target_symbols: List[str]
    affected_components: List[ImpactNode]
    affected_files: List[str]
    blast_radius_score: float  # 0.0 to 100.0
    risk_areas: List[str]
    suggested_tests: List[str]
    detailed_risks: List[RiskItem] = field(default_factory=list)
    affected_test_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_file": self.target_file,
            "target_symbols": self.target_symbols,
            "affected_components": [c.to_dict() for c in self.affected_components],
            "affected_files": self.affected_files,
            "blast_radius_score": self.blast_radius_score,
            "risk_areas": self.risk_areas,
            "suggested_tests": self.suggested_tests,
            "detailed_risks": [r.to_dict() for r in self.detailed_risks],
            "affected_test_files": self.affected_test_files,
        }


@dataclass
class ChangesetImpactReport:
    """Aggregated blast radius and impact report for a multi-file git changeset or diff."""
    changed_files: List[str]
    target_symbols: List[str]
    affected_components: List[ImpactNode]
    affected_files: List[str]
    blast_radius_score: float  # 0.0 to 100.0
    risk_areas: List[str]
    suggested_tests: List[str]
    detailed_risks: List[RiskItem] = field(default_factory=list)
    affected_test_files: List[str] = field(default_factory=list)
    per_file_reports: Dict[str, ImpactReport] = field(default_factory=dict)
    base_ref: Optional[str] = None
    diff_stat: Optional[str] = None

    @property
    def target_file(self) -> str:
        """Alias for compatibility with single-target interfaces."""
        return ", ".join(self.changed_files) if self.changed_files else "changeset"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_file": self.target_file,
            "changed_files": self.changed_files,
            "target_symbols": self.target_symbols,
            "affected_components": [c.to_dict() for c in self.affected_components],
            "affected_files": self.affected_files,
            "blast_radius_score": self.blast_radius_score,
            "risk_areas": self.risk_areas,
            "suggested_tests": self.suggested_tests,
            "detailed_risks": [r.to_dict() for r in self.detailed_risks],
            "affected_test_files": self.affected_test_files,
            "per_file_reports": {k: v.to_dict() for k, v in self.per_file_reports.items()},
            "base_ref": self.base_ref,
            "diff_stat": self.diff_stat,
        }


@dataclass
class TestResult:
    """Result of running an individual test."""
    __test__ = False

    test_name: str
    passed: bool
    duration_sec: float
    error_message: Optional[str] = None
    stdout: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "passed": self.passed,
            "duration_sec": self.duration_sec,
            "error_message": self.error_message,
        }


@dataclass
class TestSuiteExecution:
    """Overall results from running generated or existing tests."""
    __test__ = False

    total: int
    passed: int
    failed: int
    skipped: int
    duration_sec: float
    results: List[TestResult] = field(default_factory=list)
    raw_output: str = ""

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100.0) if self.total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_sec": self.duration_sec,
            "pass_rate": self.pass_rate,
            "results": [r.to_dict() for r in self.results],
        }
