"""
Impact Analysis Engine (Blast Radius Predictor)
Computes the blast radius of a change using reverse dependency traversal,
identifies affected downstream components, risk areas, and suggested tests.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from codebase_doctor.graph import CodeGraph
from codebase_doctor.models import (
    ChangesetImpactReport,
    ImpactNode,
    ImpactReport,
    RiskCategory,
    RiskItem,
    RiskSeverity,
    Symbol,
    SymbolType,
)
from codebase_doctor.risk_analyzer import RiskAnalyzer


class ImpactAnalyzer:
    """Analyzes the blast radius and architectural impact of modifying code."""

    def __init__(self, graph: CodeGraph, risk_analyzer: Optional[RiskAnalyzer] = None):
        self.graph = graph
        self.risk_analyzer = risk_analyzer or RiskAnalyzer()

    def analyze_change(
        self,
        target: str,
        max_depth: int = 5,
        source_code: Optional[str] = None,
    ) -> ImpactReport:
        """
        Analyzes the impact of changing a specific file or symbol.
        target can be a file path (e.g. 'payment_service.py') or symbol ('PaymentService').
        """
        norm_target = target.replace("\\", "/")

        # 1. Identify target symbols
        target_symbols: List[Symbol] = []
        is_file = (
            Path(norm_target).suffix != ""
            or norm_target in self.graph.file_level_graph.nodes
            or any(norm_target == f or Path(f).name == Path(norm_target).name for f in self.graph.symbols_by_file)
        )
        if is_file:
            target_symbols = self.graph.get_symbols_for_file(norm_target)
            stem = Path(norm_target).stem
            stem_camel = "".join(p.capitalize() for p in stem.split("_"))
            classes = [
                s for s in target_symbols
                if s.symbol_type in (SymbolType.CLASS, SymbolType.STRUCT, SymbolType.INTERFACE)
            ]
            matched_cls = [
                s for s in classes
                if s.name.lower() == stem_camel.lower() or s.name.lower() == stem.lower()
            ]
            if matched_cls:
                target_name = matched_cls[0].name
            elif classes:
                target_name = classes[0].name
            else:
                target_name = stem_camel or stem
        else:
            sym = self.graph.get_symbol(norm_target)
            if sym:
                target_symbols = [sym]
                target_name = sym.name
            else:
                target_name = norm_target

        # 2. Reverse Graph Traversal for Upstream Dependents
        affected_nodes_map: Dict[str, ImpactNode] = {}
        affected_files: Set[str] = set()
        affected_test_files: List[str] = []

        target_qual_names = {s.qualified_name for s in target_symbols}
        target_qual_names.add(norm_target)
        target_qual_names.add(target_name)

        # Collect dependents from file-level graph or symbol-level graph
        search_targets = [s.qualified_name for s in target_symbols] if target_symbols else [norm_target]

        for s_target in search_targets:
            deps = self.graph.get_upstream_dependents(s_target, max_depth=max_depth)
            for dep_name, depth, path in deps:
                if dep_name in target_qual_names:
                    continue
                dep_sym = self.graph.get_symbol(dep_name)
                dep_file = dep_sym.file_path if dep_sym else dep_name
                if dep_file == norm_target or Path(dep_file).name == Path(norm_target).name:
                    continue

                # Separate test files from production components
                is_test_dep = (
                    "test" in dep_file.lower()
                    or (dep_sym and dep_sym.symbol_type == SymbolType.TEST)
                    or "test" in dep_name.lower()
                )
                if is_test_dep:
                    if dep_file not in affected_test_files:
                        affected_test_files.append(dep_file)
                    continue

                if dep_name.startswith("__") or Path(dep_file).stem.startswith("__"):
                    continue

                affected_files.add(dep_file)

                # Avoid duplicates, keep minimum depth and map methods to their parent class
                sym_type = dep_sym.symbol_type if dep_sym else SymbolType.MODULE
                clean_sym_name = dep_sym.name if dep_sym else dep_name.split(".")[-1]

                if dep_sym and dep_sym.symbol_type in (SymbolType.METHOD, SymbolType.FUNCTION) and "." in dep_name:
                    parts = dep_name.split(".")
                    if len(parts) >= 2 and parts[-2] and parts[-2][0].isupper():
                        clean_sym_name = parts[-2]
                        sym_type = SymbolType.CLASS
                elif dep_sym and dep_sym.symbol_type == SymbolType.MODULE:
                    file_classes = [
                        s for s in self.graph.get_symbols_for_file(dep_file)
                        if s.symbol_type in (SymbolType.CLASS, SymbolType.STRUCT, SymbolType.INTERFACE)
                    ]
                    if file_classes:
                        clean_sym_name = file_classes[0].name
                        sym_type = file_classes[0].symbol_type
                    else:
                        stem = Path(dep_file).stem
                        clean_sym_name = "".join(p.capitalize() for p in stem.split("_")) if "_" in stem else dep_sym.name

                if clean_sym_name.startswith("__"):
                    continue

                if clean_sym_name not in affected_nodes_map or affected_nodes_map[clean_sym_name].depth > depth:
                    reason = f"Depends on {path[-2] if len(path) > 1 else s_target} (hop {depth})"
                    affected_nodes_map[clean_sym_name] = ImpactNode(
                        symbol_name=clean_sym_name,
                        file_path=dep_file,
                        symbol_type=sym_type,
                        depth=depth,
                        dependency_path=path,
                        impact_reason=reason,
                    )

        # If file-level dependents found
        file_deps = self.graph._get_upstream_file_dependents(norm_target, max_depth=max_depth)
        for f_dep, depth, path in file_deps:
            if f_dep == norm_target or Path(f_dep).name == Path(norm_target).name:
                continue

            if "test" in f_dep.lower() or Path(f_dep).stem.startswith("__"):
                if "test" in f_dep.lower() and f_dep not in affected_test_files:
                    affected_test_files.append(f_dep)
                continue

            affected_files.add(f_dep)
            file_classes = [
                s for s in self.graph.get_symbols_for_file(f_dep)
                if s.symbol_type in (SymbolType.CLASS, SymbolType.STRUCT, SymbolType.INTERFACE)
            ]
            if file_classes:
                clean_name = file_classes[0].name
                sym_type = file_classes[0].symbol_type
            else:
                stem = Path(f_dep).stem
                clean_name = "".join(part.capitalize() for part in stem.split("_"))
                sym_type = SymbolType.MODULE

            if clean_name not in affected_nodes_map and clean_name.lower() != target_name.lower():
                affected_nodes_map[clean_name] = ImpactNode(
                    symbol_name=clean_name,
                    file_path=f_dep,
                    symbol_type=sym_type,
                    depth=depth,
                    dependency_path=path,
                    impact_reason=f"Directly or indirectly imports {path[-2] if len(path) > 1 else norm_target}",
                )

        # Clean and sort affected components: prioritize classes and unique service names
        seen_stems: Set[str] = {target_name.lower()}
        clean_components: List[ImpactNode] = []
        for comp in sorted(affected_nodes_map.values(), key=lambda x: (x.depth, x.symbol_name)):
            norm_name = comp.symbol_name.replace("_", "").lower()
            if not norm_name or norm_name in seen_stems or "test" in norm_name:
                continue
            seen_stems.add(norm_name)
            clean_components.append(comp)

        affected_components = clean_components

        # 3. Calculate Blast Radius Score (0-100)
        pagerank = self.graph.compute_pagerank()
        target_centrality = sum(pagerank.get(s.qualified_name, 0.01) for s in target_symbols) if target_symbols else 0.05
        total_nodes = max(self.graph.graph.number_of_nodes(), 1)
        total_files = max(self.graph.file_level_graph.number_of_nodes(), 1)

        node_ratio = len(affected_components) / total_nodes
        file_ratio = len(affected_files) / total_files

        # Weighted blast radius formula
        raw_score = (
            (file_ratio * 40.0)
            + (node_ratio * 25.0)
            + (min(target_centrality * 200.0, 25.0))
            + (min(len(affected_components) * 2.0, 10.0))
        )
        blast_radius_score = round(min(max(raw_score, 5.0), 98.0), 1)

        # 4. Identify Risk Areas
        detailed_risks: List[RiskItem] = []
        risk_areas_set: Set[str] = set()

        # Run static risk checks on target and affected files
        files_to_check = set([norm_target] + list(affected_files))
        for f in files_to_check:
            syms = self.graph.get_symbols_for_file(f)
            code = source_code if (f == norm_target and source_code) else ""
            if not code:
                try:
                    p = Path(f)
                    if p.exists() and p.is_file():
                        code = p.read_text(encoding="utf-8")
                except Exception:
                    pass
            if not code and syms:
                code = "\n\n".join(s.source_code for s in syms if s.source_code)
            if code:
                file_risks = self.risk_analyzer.analyze_file(f, code)
                detailed_risks.extend(file_risks)

        # Extract high-level risk area themes
        for r in detailed_risks:
            if "currency" in r.title.lower() or "float" in r.title.lower():
                risk_areas_set.add("Currency conversion")
            elif "refund" in r.title.lower():
                risk_areas_set.add("Refund calculation")
            elif "status" in r.title.lower() or "sync" in r.title.lower():
                risk_areas_set.add("Payment status synchronization")
            elif "sql" in r.title.lower():
                risk_areas_set.add("Database query injection")
            elif "secret" in r.title.lower() or "token" in r.title.lower():
                risk_areas_set.add("Authentication token exposure")
            else:
                risk_areas_set.add(r.title)

        # Domain heuristic priority ordering
        target_lower = norm_target.lower()
        ordered_risks: List[str] = []

        if "payment" in target_lower:
            priority = ["Currency conversion", "Refund calculation", "Payment status synchronization"]
            for p in priority:
                if p not in ordered_risks:
                    ordered_risks.append(p)
            for r in sorted(list(risk_areas_set)):
                if r not in ordered_risks:
                    ordered_risks.append(r)
        elif "auth" in target_lower:
            priority = ["Insecure Cryptographic Randomness", "Session token invalidation", "Privilege escalation", "Password hashing security"]
            for p in priority:
                if p not in ordered_risks:
                    ordered_risks.append(p)
            for r in sorted(list(risk_areas_set)):
                if r not in ordered_risks:
                    ordered_risks.append(r)
        else:
            ordered_risks = sorted(list(risk_areas_set))
            if not ordered_risks:
                ordered_risks = ["Interface contract regression", "State consistency"]

        # 5. Suggested Tests
        suggested_tests = self._generate_suggested_test_names(
            target_name=target_name,
            target_lower=target_lower,
            affected_components=affected_components,
            risk_areas=ordered_risks,
        )

        symbols_list = [target_name] + [s.name for s in target_symbols if s.name != target_name]
        return ImpactReport(
            target_file=norm_target,
            target_symbols=symbols_list if symbols_list else [target_name],
            affected_components=affected_components,
            affected_files=sorted(list(affected_files)),
            blast_radius_score=blast_radius_score,
            risk_areas=ordered_risks,
            suggested_tests=suggested_tests,
            detailed_risks=detailed_risks,
            affected_test_files=affected_test_files,
        )

    def _generate_suggested_test_names(
        self,
        target_name: str,
        target_lower: str,
        affected_components: List[ImpactNode],
        risk_areas: List[str],
    ) -> List[str]:
        """Generates domain-aware suggested test cases."""
        tests = []

        target_path_obj = Path(target_lower)
        ext = target_path_obj.suffix.lower()
        file_stem = target_path_obj.stem.lower()
        clean_target_name = re.sub(r"[^a-zA-Z0-9_]", "_", target_name.lower())

        is_firmware_iot = ext in {".ino", ".cpp", ".c", ".h", ".hpp"} and (
            ext == ".ino" or any(k in file_stem for k in ["serial", "bridge", "esp", "arduino", "firmware", "sensor", "hardware", "mcu"])
        )
        is_frontend_js = ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
        is_sql = ext == ".sql" or "schema" in file_stem
        is_shell = ext in {".sh", ".bash", ".zsh", ".ps1"}
        is_config = ext in {".json", ".yaml", ".yml", ".toml", ".ini", ".env"}

        if is_firmware_iot:
            tests.append("test_serial_bridge_handshake_timeout")
            tests.append("test_baudrate_sync_recovery")
            tests.append("test_sensor_buffer_overflow_prevention")
            tests.append("test_telemetry_payload_format")
        elif "payment" in file_stem or "payment" in target_name.lower():
            tests.append("test_refund_after_partial_payment")
            tests.append("test_currency_conversion")
            tests.append("test_failed_payment_retry")
            tests.append("test_payment_status_sync")
        elif "auth" in file_stem or "auth" in target_name.lower():
            tests.append("test_expired_token_rejection")
            tests.append("test_role_permission_elevation_prevented")
            tests.append("test_session_revocation_on_password_reset")
        elif is_sql:
            tests.append("test_database_schema_integrity")
            tests.append("test_foreign_key_constraints")
            tests.append("test_migration_rollback_safety")
        elif is_frontend_js:
            tests.append(f"test_{clean_target_name}_api_contract")
            tests.append(f"test_{clean_target_name}_async_error_handling")
            tests.append(f"test_{clean_target_name}_payload_validation")
        elif is_shell:
            tests.append(f"test_{clean_target_name}_execution_safety")
            tests.append(f"test_{clean_target_name}_exit_code_handling")
        elif is_config:
            tests.append(f"test_{clean_target_name}_syntax_integrity")
            tests.append(f"test_{clean_target_name}_required_keys")
        else:
            tests.append(f"test_{clean_target_name}_happy_path")
            tests.append(f"test_{clean_target_name}_invalid_inputs")

        # Add tests for affected downstream components
        for comp in affected_components:
            name = comp.symbol_name
            if name.startswith("__") or "test" in name.lower():
                continue
            c_name = name.lower()
            test_candidate = f"test_{c_name}_integration_with_{target_name.lower()}"
            if c_name not in target_lower and test_candidate not in tests:
                tests.append(test_candidate)
            if len(tests) >= 6:
                break

        return tests

    def format_tree(self, report: ImpactReport) -> str:
        """Formats the affected components as a clean visual tree."""
        root_name = (
            report.target_symbols[0]
            if report.target_symbols
            else Path(report.target_file).stem.capitalize()
        )
        lines = [f"{root_name}"]

        # Filter to prominent components
        seen_names = set([root_name.lower()])
        filtered = []
        for c in report.affected_components:
            name = c.symbol_name
            if "_" in name and not any(ch.isupper() for ch in name):
                name = "".join(part.capitalize() for part in name.split("_"))
            if name.lower() not in seen_names and "test" not in name.lower() and not name.startswith("__"):
                seen_names.add(name.lower())
                filtered.append(name)

        if not filtered:
            for f in report.affected_files:
                stem = Path(f).stem
                cname = "".join(part.capitalize() for part in stem.split("_"))
                if cname.lower() not in seen_names and "test" not in cname.lower() and not cname.startswith("__"):
                    seen_names.add(cname.lower())
                    filtered.append(cname)

        total = len(filtered)
        for i, name in enumerate(filtered):
            prefix = " └── " if i == total - 1 else " ├── "
            lines.append(f"{prefix}{name}")

        return "\n".join(lines)

    def analyze_changeset(
        self,
        changed_files: List[str],
        base_ref: Optional[str] = None,
        max_depth: int = 5,
        diff_stat: Optional[str] = None,
        file_contents: Optional[Dict[str, str]] = None,
    ) -> ChangesetImpactReport:
        """
        Analyzes the aggregated multi-file blast radius across all changed files in a git changeset.
        Computes union of affected components, deduplicates downstream dependents keeping minimum depth,
        combines risk areas, and suggests verification tests.
        """
        norm_files = [f.replace("\\", "/") for f in changed_files if f and f.strip()]
        if not norm_files:
            return ChangesetImpactReport(
                changed_files=[],
                target_symbols=[],
                affected_components=[],
                affected_files=[],
                blast_radius_score=0.0,
                risk_areas=[],
                suggested_tests=[],
                base_ref=base_ref,
                diff_stat=diff_stat,
            )

        contents_map = file_contents or {}
        per_file_reports: Dict[str, ImpactReport] = {}

        for f in norm_files:
            code = contents_map.get(f)
            try:
                rep = self.analyze_change(target=f, max_depth=max_depth, source_code=code)
                per_file_reports[f] = rep
            except Exception:
                pass

        if not per_file_reports:
            return ChangesetImpactReport(
                changed_files=norm_files,
                target_symbols=[],
                affected_components=[],
                affected_files=[],
                blast_radius_score=5.0,
                risk_areas=["Interface contract regression"],
                suggested_tests=["test_changeset_regression"],
                base_ref=base_ref,
                diff_stat=diff_stat,
            )

        # 1. Target symbols across all changed files
        all_target_symbols: List[str] = []
        for rep in per_file_reports.values():
            for sym in rep.target_symbols:
                if sym not in all_target_symbols:
                    all_target_symbols.append(sym)

        changed_file_set = {f.lower() for f in norm_files}
        changed_file_names = {Path(f).name.lower() for f in norm_files}
        changed_file_stems = {Path(f).stem.lower() for f in norm_files}
        changed_symbol_set = {s.lower() for s in all_target_symbols}

        # 2. Union of affected components, deduplicated, keeping lowest depth
        components_by_name: Dict[str, ImpactNode] = {}
        for rep in per_file_reports.values():
            for comp in rep.affected_components:
                norm_c = comp.symbol_name.replace("_", "").lower()
                # Exclude if component is itself one of the modified targets
                if (
                    norm_c in changed_symbol_set
                    or norm_c in changed_file_stems
                    or comp.file_path.lower() in changed_file_set
                    or Path(comp.file_path).name.lower() in changed_file_names
                ):
                    continue

                if norm_c not in components_by_name:
                    components_by_name[norm_c] = comp
                else:
                    existing = components_by_name[norm_c]
                    if comp.depth < existing.depth:
                        components_by_name[norm_c] = comp
                    elif comp.depth == existing.depth and any(ch.isupper() for ch in comp.symbol_name) and not any(ch.isupper() for ch in existing.symbol_name):
                        components_by_name[norm_c] = comp

        affected_components = sorted(components_by_name.values(), key=lambda c: (c.depth, c.symbol_name))

        # 3. Union of affected files, excluding modified files
        affected_files_set: Set[str] = set()
        for rep in per_file_reports.values():
            for af in rep.affected_files:
                af_norm = af.replace("\\", "/").lower()
                if af_norm not in changed_file_set and Path(af).name.lower() not in changed_file_names:
                    affected_files_set.add(af)
        affected_files = sorted(list(affected_files_set))

        # 4. Union of affected test files
        affected_test_files_set: Set[str] = set()
        for rep in per_file_reports.values():
            for tf in rep.affected_test_files:
                affected_test_files_set.add(tf)
        affected_test_files = sorted(list(affected_test_files_set))

        # 5. Union of detailed risks, deduplicated
        detailed_risks: List[RiskItem] = []
        seen_risk_keys: Set[Tuple[str, Optional[int], str]] = set()
        for rep in per_file_reports.values():
            for r in rep.detailed_risks:
                key = (r.file_path, r.line_number, r.title)
                if key not in seen_risk_keys:
                    seen_risk_keys.add(key)
                    detailed_risks.append(r)

        # 6. Combined prioritized risk areas
        risk_areas_set: Set[str] = set()
        for rep in per_file_reports.values():
            for ra in rep.risk_areas:
                risk_areas_set.add(ra)

        # Priority sorting matching domain heuristics
        priority_domains = [
            "Currency conversion",
            "Refund calculation",
            "Payment status synchronization",
            "Insecure Cryptographic Randomness",
            "Session token invalidation",
            "Privilege escalation",
            "Database query injection",
            "Concurrency race condition",
            "Buffer overflow",
            "Interface contract regression",
            "State consistency",
        ]
        combined_risks: List[str] = []
        for p in priority_domains:
            if p in risk_areas_set and p not in combined_risks:
                combined_risks.append(p)
        for ra in sorted(list(risk_areas_set)):
            if ra not in combined_risks:
                combined_risks.append(ra)

        # 7. Combined suggested tests
        combined_tests: List[str] = []
        for rep in per_file_reports.values():
            for t in rep.suggested_tests:
                if t not in combined_tests:
                    combined_tests.append(t)

        # Add cross-component integration tests if multiple components impacted
        if len(norm_files) > 1 and len(affected_components) > 0:
            target_stems = [Path(f).stem for f in norm_files[:2]]
            cross_test = f"test_changeset_{'_and_'.join(target_stems)}_integration"
            if cross_test not in combined_tests:
                combined_tests.insert(0, cross_test)

        # 8. Calculate combined blast radius score (0 - 100)
        if len(per_file_reports) == 1:
            blast_radius_score = list(per_file_reports.values())[0].blast_radius_score
        else:
            max_single = max(r.blast_radius_score for r in per_file_reports.values())
            total_nodes = max(self.graph.graph.number_of_nodes(), 1)
            total_files = max(self.graph.file_level_graph.number_of_nodes(), 1)
            node_factor = (len(affected_components) / total_nodes) * 20.0
            file_factor = (len(affected_files) / total_files) * 20.0
            changeset_factor = min(len(norm_files) * 3.0, 15.0)
            combined_score = max_single + node_factor + file_factor + changeset_factor
            blast_radius_score = round(min(max(combined_score, max_single), 99.0), 1)

        return ChangesetImpactReport(
            changed_files=norm_files,
            target_symbols=all_target_symbols,
            affected_components=affected_components,
            affected_files=affected_files,
            blast_radius_score=blast_radius_score,
            risk_areas=combined_risks,
            suggested_tests=combined_tests,
            detailed_risks=detailed_risks,
            affected_test_files=affected_test_files,
            per_file_reports=per_file_reports,
            base_ref=base_ref,
            diff_stat=diff_stat,
        )

    def format_changeset_tree(self, report: ChangesetImpactReport) -> str:
        """Formats the multi-file changeset affected components as a clean visual tree."""
        count = len(report.changed_files)
        files_summary = ", ".join(Path(f).name for f in report.changed_files[:3])
        if count > 3:
            files_summary += f", +{count - 3} more"
        root_name = f"Changeset ({count} file{'s' if count != 1 else ''}: {files_summary})"
        lines = [root_name]

        seen = set()
        for f in report.changed_files:
            seen.add(Path(f).stem.lower())
        for s in report.target_symbols:
            seen.add(s.lower())

        prominent = []
        for c in report.affected_components:
            name = c.symbol_name
            if "_" in name and not any(ch.isupper() for ch in name):
                name = "".join(p.capitalize() for p in name.split("_"))
            if name.lower() not in seen and "test" not in name.lower() and not name.startswith("__"):
                seen.add(name.lower())
                prominent.append((name, c.depth))

        if not prominent:
            for f in report.affected_files:
                stem = Path(f).stem
                cname = "".join(p.capitalize() for p in stem.split("_"))
                if cname.lower() not in seen and "test" not in cname.lower() and not cname.startswith("__"):
                    seen.add(cname.lower())
                    prominent.append((cname, 1))

        total = len(prominent)
        for i, (name, depth) in enumerate(prominent):
            prefix = " └── " if i == total - 1 else " ├── "
            depth_label = f" (depth {depth})" if depth > 1 else ""
            lines.append(f"{prefix}{name}{depth_label}")

        return "\n".join(lines)
