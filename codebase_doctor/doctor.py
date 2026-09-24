"""
Codebase Doctor Main Controller
Orchestrates repository ingestion, AST parsing, graph construction, impact analysis,
risk detection, Graph-RAG Q&A, and automated test generation & execution.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from rich.console import Console

from codebase_doctor.graph import CodeGraph
from codebase_doctor.impact import ImpactAnalyzer
from codebase_doctor.llm_provider import BaseLLMProvider, get_llm_provider
from codebase_doctor.models import ChangesetImpactReport, DependencyEdge, ImpactReport, Symbol, TestSuiteExecution
from codebase_doctor.parser import CodeParser
from codebase_doctor.rag import GraphRAG
from codebase_doctor.repo_manager import RepoManager
from codebase_doctor.reporter import ReportGenerator
from codebase_doctor.risk_analyzer import RiskAnalyzer
from codebase_doctor.test_generator import TestGenerator
from codebase_doctor.test_runner import TestRunner
from codebase_doctor.visualizer import GraphVisualizer


class CodebaseDoctor:
    """The complete AI Codebase Doctor system."""

    def __init__(
        self,
        repo_path: str = ".",
        llm: Optional[BaseLLMProvider] = None,
        console: Optional[Console] = None,
    ):
        self.repo_manager = RepoManager(repo_path)
        self.repo_root = self.repo_manager.root_path
        self.console = console or Console()
        self.llm = llm or get_llm_provider()

        self.parser = CodeParser(self.repo_root)
        self.graph = CodeGraph()
        self.risk_analyzer = RiskAnalyzer()
        self.impact_analyzer = ImpactAnalyzer(self.graph, self.risk_analyzer)
        self.rag = GraphRAG(self.graph, self.llm)
        self.test_generator = TestGenerator(self.llm)
        self.test_runner = TestRunner(self.repo_root)
        self.reporter = ReportGenerator(self.console)

        self.file_hashes: Dict[str, str] = {}
        self.edges_by_file: Dict[str, List[DependencyEdge]] = defaultdict(list)
        self.is_indexed = False

    def scan(self, incremental: bool = False) -> Dict[str, Any]:
        """
        Scans repository, parses ASTs, and builds the dependency graph.
        If incremental=True and the repository has already been indexed, only
        added, modified, or deleted files are re-parsed and re-linked.
        """
        if incremental and self.is_indexed and self.file_hashes:
            changes = self.repo_manager.get_incremental_changes(self.file_hashes)
            added_files = changes["added"]
            modified_files = changes["modified"]
            deleted_files = changes["deleted"]
            unchanged_files = changes["unchanged"]

            if not added_files and not modified_files and not deleted_files:
                stats = self.graph.get_stats()
                stats.update({
                    "incremental": True,
                    "changed": False,
                    "added": 0,
                    "modified": 0,
                    "deleted": 0,
                    "unchanged": len(unchanged_files),
                })
                return stats

            # 1. Clean up deleted and modified files from graph
            for rel_path in deleted_files + modified_files:
                self.graph.remove_file(rel_path)
                self.edges_by_file.pop(rel_path, None)
                self.file_hashes.pop(rel_path, None)

            # 2. Re-parse added and modified files
            files_to_parse = added_files + modified_files
            for rel_path in files_to_parse:
                file_path = self.repo_root / rel_path
                try:
                    source_code = self.repo_manager.read_file(str(file_path))
                    symbols, edges = self.parser.parse_file(file_path, source_code=source_code)
                    for sym in symbols:
                        self.graph.add_symbol(sym)
                    self.edges_by_file[rel_path] = edges
                    self.file_hashes[rel_path] = self.repo_manager.compute_file_hash(file_path)
                except Exception as e:
                    self.console.print(f"[yellow][warn] Failed to parse {rel_path}: {e}[/]")

            # 3. Fast re-link edges across the graph
            self.graph.graph.clear_edges()
            for edges in self.edges_by_file.values():
                for edge in edges:
                    self.graph.add_edge(edge)

            # Rebuild file-level graph & PageRank
            self.graph.rebuild_file_level_graph()
            self.graph.compute_pagerank()

            stats = self.graph.get_stats()
            stats.update({
                "incremental": True,
                "changed": True,
                "added": len(added_files),
                "modified": len(modified_files),
                "deleted": len(deleted_files),
                "unchanged": len(unchanged_files),
            })
            return stats

        # Full scan (Pass 1 & Pass 2)
        source_files = self.repo_manager.get_source_files()
        self.graph = CodeGraph()
        self.impact_analyzer.graph = self.graph
        self.rag.graph = self.graph
        self.edges_by_file.clear()
        self.file_hashes.clear()
        all_parsed: List[Tuple[str, List[Symbol], List[DependencyEdge]]] = []

        # Pass 1: Parse all files and register all symbols first
        for file_path in source_files:
            rel_path = self.repo_manager.get_relative_path(file_path)
            source_code = self.repo_manager.read_file(str(file_path))
            symbols, edges = self.parser.parse_file(file_path, source_code=source_code)
            for sym in symbols:
                self.graph.add_symbol(sym)
            self.edges_by_file[rel_path] = edges
            self.file_hashes[rel_path] = self.repo_manager.compute_file_hash(file_path)
            all_parsed.append((rel_path, symbols, edges))

        # Pass 2: With all symbols known across the repo, resolve and add all edges
        for rel_path, symbols, edges in all_parsed:
            for edge in edges:
                self.graph.add_edge(edge)

        # Reconstruct and verify complete file-level graph
        self.graph.rebuild_file_level_graph()

        # Trigger PageRank pre-computation
        self.graph.compute_pagerank()
        self.is_indexed = True

        stats = self.graph.get_stats()
        stats.update({
            "incremental": False,
            "changed": True,
            "added": len(source_files),
            "modified": 0,
            "deleted": 0,
            "unchanged": 0,
        })
        return stats

    def analyze_change(
        self,
        target: str,
        max_depth: int = 5,
    ) -> ImpactReport:
        """
        Analyzes the blast radius and risk areas when modifying a file or symbol.
        e.g. target='payment_service.py' or 'PaymentService'
        """
        if not self.is_indexed:
            self.scan()

        # Read source code if target is a file
        source_code = None
        try:
            source_code = self.repo_manager.read_file(target)
        except Exception:
            pass

        return self.impact_analyzer.analyze_change(
            target=target,
            max_depth=max_depth,
            source_code=source_code,
        )

    def ask(self, question: str) -> Dict[str, Any]:
        """Answers architectural or code questions using Graph-Augmented RAG."""
        if not self.is_indexed:
            self.scan()
        return self.rag.answer_query(question)

    def generate_and_run_tests(
        self,
        report: ImpactReport,
        output_dir: Optional[Path] = None,
    ) -> Tuple[TestSuiteExecution, Path]:
        """Generates pytest test suite and immediately executes it."""
        out_dir = output_dir or (self.repo_root / "tests")
        _, test_path = self.test_generator.generate_tests_for_impact(report, output_dir=out_dir)
        execution = self.test_runner.run_tests(test_path)
        return execution, test_path

    def run_full_diagnosis(
        self,
        target: str,
        auto_run_tests: bool = True,
    ) -> Tuple[ImpactReport, Optional[TestSuiteExecution]]:
        """
        Executes end-to-end diagnosis:
        1. Scan codebase & build graph
        2. Analyze blast radius of target
        3. Identify risks
        4. Auto-generate tests
        5. Run tests automatically
        6. Print formatted report
        """
        if not self.is_indexed:
            self.scan()

        report = self.analyze_change(target)
        test_execution = None

        if auto_run_tests:
            test_execution, _ = self.generate_and_run_tests(report)

        self.reporter.print_terminal_report(report, test_execution)
        return report, test_execution

    def analyze_diff(
        self,
        base_ref: Optional[str] = None,
        run_tests: bool = False,
        max_depth: int = 5,
        output_dir: Optional[Path] = None,
        changed_files: Optional[List[str]] = None,
    ) -> Tuple[ChangesetImpactReport, Optional[TestSuiteExecution]]:
        """
        Analyzes the aggregated multi-file blast radius across git changes:
        - If base_ref is provided: diffs against base_ref.
        - If base_ref is None: inspects uncommitted changes (working tree & staged).
        - If changed_files is provided explicitly: analyzes those files directly.
        """
        if not self.is_indexed:
            self.scan()

        files_to_analyze = (
            changed_files
            if changed_files is not None
            else self.repo_manager.get_changed_files(base_ref=base_ref)
        )
        diff_stats = (
            self.repo_manager.get_diff_stats(base_ref=base_ref)
            if self.repo_manager.is_git_repo()
            else {}
        )

        file_contents: Dict[str, str] = {}
        for f in files_to_analyze:
            try:
                file_contents[f] = self.repo_manager.read_file(f)
            except Exception:
                pass

        report = self.impact_analyzer.analyze_changeset(
            changed_files=files_to_analyze,
            base_ref=base_ref,
            max_depth=max_depth,
            diff_stat=diff_stats.get("stat_text"),
            file_contents=file_contents,
        )

        test_execution = None
        if run_tests and (report.changed_files or report.suggested_tests):
            test_execution, _ = self.generate_and_run_tests_for_changeset(report, output_dir=output_dir)

        return report, test_execution

    def generate_and_run_tests_for_changeset(
        self,
        report: ChangesetImpactReport,
        output_dir: Optional[Path] = None,
    ) -> Tuple[TestSuiteExecution, Optional[Path]]:
        """Generates and executes tests for the changeset blast radius."""
        if not report.changed_files:
            empty_exec = TestSuiteExecution(total=0, passed=0, failed=0, skipped=0, duration_sec=0.0)
            return empty_exec, None

        # Prioritize primary modified file for test harness execution, with combined changeset test coverage
        primary_file = report.changed_files[0]
        primary_report = ImpactReport(
            target_file=primary_file,
            target_symbols=report.target_symbols,
            affected_components=report.affected_components,
            affected_files=report.affected_files,
            blast_radius_score=report.blast_radius_score,
            risk_areas=report.risk_areas,
            suggested_tests=report.suggested_tests,
            detailed_risks=report.detailed_risks,
            affected_test_files=report.affected_test_files,
        )

        out_dir = output_dir or (self.repo_root / "tests")
        _, test_path = self.test_generator.generate_tests_for_impact(primary_report, output_dir=out_dir)
        execution = self.test_runner.run_tests(test_path)
        return execution, test_path

    def generate_visual_graph(
        self,
        report: Union[ImpactReport, ChangesetImpactReport],
        height: int = 580,
    ) -> str:
        """Generates interactive force-directed graph HTML for a change or changeset."""
        if not self.is_indexed:
            self.scan()
        return GraphVisualizer.generate_impact_graph_html(self.graph, report, height=height)

    def generate_architecture_graph(self, height: int = 650) -> str:
        """Generates interactive force-directed architecture graph HTML for the entire codebase."""
        if not self.is_indexed:
            self.scan()
        return GraphVisualizer.generate_architecture_graph_html(self.graph, height=height)

    def generate_pr_markdown(
        self,
        report: ChangesetImpactReport,
        test_execution: Optional[TestSuiteExecution] = None,
    ) -> str:
        """Generates GitHub PR review comment in Markdown."""
        return self.reporter.generate_pr_markdown(report, test_execution)
