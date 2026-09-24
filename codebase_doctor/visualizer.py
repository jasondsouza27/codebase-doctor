"""
Code Knowledge Graph Interactive Visualizer
Generates interactive force-directed graphs using vis-network embedded in Streamlit.
Visual node styling:
- Ground Zero (Modified file/symbol) in Red (#ef4444)
- Direct dependents (Depth 1) in Orange (#f97316)
- Transitive dependents (Depth 2+) in Yellow (#eab308)
- Surrounding components in Gray (#64748b)

Interactive features: physics layout, drag/pan/zoom, search filter, physics toggle, and
rich tooltips with symbol names, language, lines, cyclomatic complexity, and risk flags.
"""

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from codebase_doctor.graph import CodeGraph
from codebase_doctor.models import ChangesetImpactReport, ImpactNode, ImpactReport, Symbol, SymbolType
from codebase_doctor.repo_manager import RepoManager


class GraphVisualizer:
    """Renders interactive force-directed graph HTML for Codebase Doctor."""

    COLOR_GROUND_ZERO = {
        "background": "#ef4444",
        "border": "#b91c1c",
        "highlight": {"background": "#f87171", "border": "#dc2626"},
        "hover": {"background": "#f87171", "border": "#dc2626"},
    }
    COLOR_DEPTH_1 = {
        "background": "#f97316",
        "border": "#c2410c",
        "highlight": {"background": "#fb923c", "border": "#ea580c"},
        "hover": {"background": "#fb923c", "border": "#ea580c"},
    }
    COLOR_DEPTH_2_PLUS = {
        "background": "#eab308",
        "border": "#a16207",
        "highlight": {"background": "#facc15", "border": "#ca8a04"},
        "hover": {"background": "#facc15", "border": "#ca8a04"},
    }
    COLOR_SURROUNDING = {
        "background": "#64748b",
        "border": "#475569",
        "highlight": {"background": "#94a3b8", "border": "#64748b"},
        "hover": {"background": "#94a3b8", "border": "#64748b"},
    }

    # Language color palette for global architecture view
    LANGUAGE_COLORS = {
        "python": "#38bdf8",
        "c": "#ec4899",
        "cpp": "#f43f5e",
        "c++": "#f43f5e",
        "arduino/c++": "#10b981",
        "javascript": "#f59e0b",
        "typescript": "#6366f1",
        "java": "#ea580c",
        "go": "#06b6d4",
        "rust": "#e11d48",
        "sql": "#8b5cf6",
        "shell": "#84cc16",
        "config": "#a855f7",
    }

    @classmethod
    def _build_node_tooltip(
        cls,
        name: str,
        role: str,
        role_color: str,
        language: str,
        lines_str: str,
        complexity: int,
        risk_flags: List[str],
        file_path: str = "",
        symbol_type: str = "Component",
    ) -> str:
        """Constructs rich HTML content for node hover tooltip."""
        risks_html = ""
        if risk_flags:
            risk_items = "".join([f"<li style='color:#f87171; margin-bottom:2px;'>[!] {html.escape(r)}</li>" for r in risk_flags[:4]])
            if len(risk_flags) > 4:
                risk_items += f"<li style='color:#94a3b8;'>+{len(risk_flags) - 4} more</li>"
            risks_html = f"<ul style='margin:4px 0 0 16px; padding:0;'>{risk_items}</ul>"
        else:
            risks_html = "<span style='color:#4ade80;'>Clean (0 risk flags)</span>"

        return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; font-size: 12px; line-height: 1.5; color: #f8fafc;">
    <div style="font-size: 14px; font-weight: bold; color: #38bdf8; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 6px;">
        {html.escape(name)}
    </div>
    <div style="margin-bottom: 3px;">
        <span style="color: #94a3b8; font-weight: 600;">Status:</span>
        <span style="color: {role_color}; font-weight: bold; background: rgba(255,255,255,0.08); padding: 1px 6px; border-radius: 4px;">{html.escape(role)}</span>
    </div>
    <div style="margin-bottom: 3px;"><span style="color: #94a3b8; font-weight: 600;">Type:</span> {html.escape(symbol_type)}</div>
    {f'<div style="margin-bottom: 3px;"><span style="color: #94a3b8; font-weight: 600;">File:</span> <code>{html.escape(file_path)}</code></div>' if file_path else ''}
    <div style="margin-bottom: 3px;"><span style="color: #94a3b8; font-weight: 600;">Language:</span> {html.escape(language)}</div>
    <div style="margin-bottom: 3px;"><span style="color: #94a3b8; font-weight: 600;">Lines:</span> {html.escape(lines_str)}</div>
    <div style="margin-bottom: 4px;"><span style="color: #94a3b8; font-weight: 600;">Cyclomatic Complexity:</span> <b style="color: {'#f87171' if complexity >= 10 else ('#facc15' if complexity >= 5 else '#4ade80')};">{complexity}</b></div>
    <div style="margin-top: 6px; border-top: 1px solid #1e293b; padding-top: 4px;">
        <span style="color: #94a3b8; font-weight: 600;">Risk Flags:</span>
        {risks_html}
    </div>
</div>
        """.strip()

    @classmethod
    def generate_impact_graph_html(
        cls,
        graph: CodeGraph,
        report: Union[ImpactReport, ChangesetImpactReport],
        height: int = 580,
        title: str = "",
    ) -> str:
        """
        Generates an interactive force-directed graph HTML for a single-file or changeset impact report.
        Styling:
        - Target / Modified components in RED (#ef4444, Ground Zero)
        - Direct dependents in ORANGE (#f97316, Depth 1)
        - Transitive dependents in YELLOW (#eab308, Depth 2+)
        - Surrounding components in GRAY (#64748b)
        """
        nodes_dict: Dict[str, Dict[str, Any]] = {}
        edges_list: List[Dict[str, Any]] = []

        is_changeset = isinstance(report, ChangesetImpactReport)
        target_files = report.changed_files if is_changeset else ([report.target_file] if report.target_file else [])
        target_symbols = report.target_symbols or []

        # 1. Ground Zero Nodes (Red)
        ground_zero_keys: Set[str] = set()

        # Map risks by file
        risks_by_file: Dict[str, List[str]] = {}
        for r in getattr(report, "detailed_risks", []):
            rf = r.file_path.replace("\\", "/").lower()
            risks_by_file.setdefault(rf, []).append(f"[{r.severity.value}] {r.title}")

        for tf in target_files:
            if not tf:
                continue
            norm_tf = tf.replace("\\", "/")
            stem = Path(norm_tf).stem
            ground_zero_keys.add(norm_tf.lower())
            ground_zero_keys.add(stem.lower())
            ground_zero_keys.add(Path(norm_tf).name.lower())

            syms = graph.get_symbols_for_file(norm_tf)
            max_comp = max((s.complexity for s in syms), default=1)
            lang = RepoManager.detect_language(norm_tf)
            line_cnt = max((s.line_end for s in syms), default=0)
            lines_str = f"1 - {line_cnt} ({line_cnt} lines)" if line_cnt > 0 else "File Module"

            file_risks = risks_by_file.get(norm_tf.lower(), [])
            if not file_risks and report.risk_areas:
                file_risks = report.risk_areas[:3]

            tooltip_html = cls._build_node_tooltip(
                name=Path(norm_tf).name,
                role="Ground Zero (Modified File)",
                role_color="#ef4444",
                language=lang,
                lines_str=lines_str,
                complexity=max_comp,
                risk_flags=file_risks,
                file_path=norm_tf,
                symbol_type="File / Module",
            )

            nodes_dict[norm_tf] = {
                "id": norm_tf,
                "label": f"● {Path(norm_tf).name}",
                "color": cls.COLOR_GROUND_ZERO,
                "size": 30,
                "shape": "box",
                "font": {"color": "#ffffff", "face": "monospace", "size": 13, "bold": True},
                "borderWidth": 3,
                "tooltipHtml": tooltip_html,
                "group": "ground_zero",
            }

        # Add explicitly targeted symbol as Ground Zero if single-target symbol analysis
        if not is_changeset and target_symbols:
            primary_sym_name = target_symbols[0]
            if primary_sym_name and not primary_sym_name.startswith("__") and primary_sym_name.lower() not in ground_zero_keys:
                sym = graph.get_symbol(primary_sym_name)
                sym_file = sym.file_path if sym else ""
                ground_zero_keys.add(primary_sym_name.lower())
                tooltip_html = cls._build_node_tooltip(
                    name=primary_sym_name,
                    role="Ground Zero (Modified Symbol)",
                    role_color="#ef4444",
                    language=sym.language if sym else "Code",
                    lines_str=f"{sym.line_start}-{sym.line_end} ({sym.line_end - sym.line_start + 1} lines)" if sym else "-",
                    complexity=sym.complexity if sym else 1,
                    risk_flags=report.risk_areas[:3] if report.risk_areas else [],
                    file_path=sym_file,
                    symbol_type=sym.symbol_type.value if sym else "Symbol",
                )
                nodes_dict[primary_sym_name] = {
                    "id": primary_sym_name,
                    "label": f"● {primary_sym_name}",
                    "color": cls.COLOR_GROUND_ZERO,
                    "size": 26,
                    "shape": "dot",
                    "font": {"color": "#ffffff", "face": "monospace", "size": 12, "bold": True},
                    "borderWidth": 3,
                    "tooltipHtml": tooltip_html,
                    "group": "ground_zero",
                }

        # 2. Downstream Impacted Nodes (Depth 1 in Orange, Depth 2+ in Yellow)
        impacted_keys: Set[str] = set(ground_zero_keys)

        for comp in report.affected_components:
            name = comp.symbol_name
            norm_name = name.replace("_", "").lower()
            if (
                name.lower() in ground_zero_keys
                or norm_name in ground_zero_keys
                or comp.file_path.lower() in ground_zero_keys
                or Path(comp.file_path).stem.lower() in ground_zero_keys
            ):
                continue

            impacted_keys.add(name.lower())
            impacted_keys.add(norm_name)
            impacted_keys.add(comp.file_path.lower())
            impacted_keys.add(Path(comp.file_path).stem.lower())
            impacted_keys.add(Path(comp.file_path).name.lower())

            depth = comp.depth
            is_depth_1 = depth == 1

            color = cls.COLOR_DEPTH_1 if is_depth_1 else cls.COLOR_DEPTH_2_PLUS
            role_label = "Direct Dependent (Depth 1)" if is_depth_1 else f"Transitive Dependent (Depth {depth})"
            role_color = "#f97316" if is_depth_1 else "#eab308"
            group_name = "depth_1" if is_depth_1 else "depth_2_plus"
            size = 24 if is_depth_1 else 20
            badge = "1°" if is_depth_1 else "2°+"

            sym = graph.get_symbol(name)
            sym_file = comp.file_path or (sym.file_path if sym else "")
            lang = (sym.language if sym else "") or RepoManager.detect_language(sym_file)
            lines_str = f"{sym.line_start}-{sym.line_end} ({sym.line_end - sym.line_start + 1} lines)" if sym else "File Module"
            comp_score = sym.complexity if sym else 1

            comp_risks = risks_by_file.get(sym_file.replace("\\", "/").lower(), [])

            tooltip_html = cls._build_node_tooltip(
                name=name,
                role=role_label,
                role_color=role_color,
                language=lang,
                lines_str=lines_str,
                complexity=comp_score,
                risk_flags=comp_risks,
                file_path=sym_file,
                symbol_type=comp.symbol_type.value if hasattr(comp.symbol_type, "value") else str(comp.symbol_type),
            )

            nodes_dict[name] = {
                "id": name,
                "label": f"{badge} {name}",
                "color": color,
                "size": size,
                "shape": "dot",
                "font": {"color": "#f8fafc", "face": "monospace", "size": 11},
                "borderWidth": 2,
                "tooltipHtml": tooltip_html,
                "group": group_name,
            }

        # Also add affected files if not represented by a component
        for af in report.affected_files:
            norm_af = af.replace("\\", "/")
            stem = Path(norm_af).stem.lower()
            if norm_af.lower() in impacted_keys or stem in impacted_keys:
                continue

            impacted_keys.add(norm_af.lower())
            impacted_keys.add(stem)
            tooltip_html = cls._build_node_tooltip(
                name=Path(norm_af).name,
                role="Impacted Downstream File",
                role_color="#f97316",
                language=RepoManager.detect_language(norm_af),
                lines_str="File Module",
                complexity=1,
                risk_flags=risks_by_file.get(norm_af.lower(), []),
                file_path=norm_af,
                symbol_type="File",
            )
            nodes_dict[norm_af] = {
                "id": norm_af,
                "label": f"○ {Path(norm_af).name}",
                "color": cls.COLOR_DEPTH_1,
                "size": 22,
                "shape": "box",
                "font": {"color": "#f8fafc", "face": "monospace", "size": 11},
                "borderWidth": 2,
                "tooltipHtml": tooltip_html,
                "group": "depth_1",
            }

        # 3. Surrounding Components (Gray)
        # Find immediate internal neighbors of ground_zero and impacted nodes
        surrounding_count = 0
        max_surrounding = 20

        active_node_ids = list(nodes_dict.keys())
        for nid in active_node_ids:
            if surrounding_count >= max_surrounding:
                break

            neighbors: List[str] = []
            if nid in graph.graph:
                neighbors.extend(list(graph.graph.successors(nid)) + list(graph.graph.predecessors(nid)))
            if nid in graph.file_level_graph:
                neighbors.extend(list(graph.file_level_graph.successors(nid)) + list(graph.file_level_graph.predecessors(nid)))

            for neighbor in neighbors:
                if surrounding_count >= max_surrounding:
                    break

                clean_n = neighbor.replace("\\", "/")
                n_stem = Path(clean_n).stem.lower()
                n_short = clean_n.split(".")[-1]
                n_norm = n_short.replace("_", "").lower()

                # Filter out standard library or external non-codebase symbols (e.g. typing.Any, builtins)
                sym = graph.get_symbol(neighbor)
                f_path = sym.file_path if sym else clean_n
                is_internal_file = clean_n in graph.file_level_graph.nodes or f_path in graph.file_level_graph.nodes
                is_internal_symbol = sym is not None or neighbor in graph.symbols_by_name
                if not is_internal_file and not is_internal_symbol:
                    continue

                # Filter out anything already tracked in ground zero or impacted sets
                if (
                    clean_n in nodes_dict
                    or n_short in nodes_dict
                    or clean_n.lower() in impacted_keys
                    or n_stem in impacted_keys
                    or n_norm in impacted_keys
                    or n_short.lower() in impacted_keys
                ):
                    continue

                display_name = sym.name if sym else Path(clean_n).name
                if (
                    display_name.startswith("__")
                    or "test" in display_name.lower()
                    or display_name.lower() in ("any", "dict", "list", "optional", "union", "tuple", "set")
                ):
                    continue

                lang = (sym.language if sym else "") or RepoManager.detect_language(f_path)
                tooltip_html = cls._build_node_tooltip(
                    name=display_name,
                    role="Surrounding Component (Context)",
                    role_color="#94a3b8",
                    language=lang,
                    lines_str=f"{sym.line_start}-{sym.line_end}" if sym else "-",
                    complexity=sym.complexity if sym else 1,
                    risk_flags=[],
                    file_path=f_path,
                    symbol_type=sym.symbol_type.value if sym else "Module",
                )

                nodes_dict[display_name] = {
                    "id": display_name,
                    "label": display_name,
                    "color": cls.COLOR_SURROUNDING,
                    "size": 14,
                    "shape": "dot",
                    "font": {"color": "#94a3b8", "face": "monospace", "size": 10},
                    "borderWidth": 1,
                    "tooltipHtml": tooltip_html,
                    "group": "surrounding",
                }
                impacted_keys.add(display_name.lower())
                impacted_keys.add(display_name.replace("_", "").lower())
                surrounding_count += 1

        # 4. Build Directed Edges
        edge_id = 0
        seen_edges: Set[Tuple[str, str]] = set()

        # Build mapping from symbol names, modules, and file stems to nodes_dict node ID
        node_lookup: Dict[str, str] = {}
        for nid, ndata in nodes_dict.items():
            node_lookup[nid.lower()] = nid
            node_lookup[Path(nid).name.lower()] = nid
            node_lookup[Path(nid).stem.lower()] = nid
            node_lookup[nid.replace("_", "").lower()] = nid
            sym_ref = graph.get_symbol(nid)
            if sym_ref:
                node_lookup[sym_ref.qualified_name.lower()] = nid
                node_lookup[sym_ref.name.lower()] = nid
                if sym_ref.file_path:
                    node_lookup[sym_ref.file_path.replace("\\", "/").lower()] = nid

        def _resolve_to_node_id(key: str) -> Optional[str]:
            k_clean = key.replace("\\", "/").lower()
            if k_clean in node_lookup:
                return node_lookup[k_clean]
            k_short = k_clean.split(".")[-1]
            if k_short in node_lookup:
                return node_lookup[k_short]
            k_stem = Path(k_clean).stem
            if k_stem in node_lookup:
                return node_lookup[k_stem]
            return None

        # Collect edges from symbol graph
        for u, v, data in graph.graph.edges(data=True):
            src = _resolve_to_node_id(u)
            tgt = _resolve_to_node_id(v)

            if src and tgt and src != tgt and (src, tgt) not in seen_edges:
                seen_edges.add((src, tgt))
                edge_id += 1
                edge_type = data.get("edge_type", "CALLS")

                is_active_path = (
                    nodes_dict[src].get("group") in ("ground_zero", "depth_1", "depth_2_plus")
                    and nodes_dict[tgt].get("group") in ("ground_zero", "depth_1", "depth_2_plus")
                )

                edges_list.append({
                    "id": f"e{edge_id}",
                    "from": src,
                    "to": tgt,
                    "label": edge_type,
                    "color": {"color": "#f97316" if is_active_path else "#334155", "highlight": "#38bdf8", "hover": "#38bdf8"},
                    "width": 2.5 if is_active_path else 1.0,
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                    "font": {"color": "#64748b", "size": 9, "face": "monospace", "align": "top"},
                })

        # Collect edges from file-level graph
        for u, v, data in graph.file_level_graph.edges(data=True):
            src = _resolve_to_node_id(u)
            tgt = _resolve_to_node_id(v)

            if src and tgt and src != tgt and (src, tgt) not in seen_edges:
                seen_edges.add((src, tgt))
                edge_id += 1
                is_active_path = (
                    nodes_dict[src].get("group") in ("ground_zero", "depth_1", "depth_2_plus")
                    and nodes_dict[tgt].get("group") in ("ground_zero", "depth_1", "depth_2_plus")
                )
                edges_list.append({
                    "id": f"e{edge_id}",
                    "from": src,
                    "to": tgt,
                    "label": data.get("relation", "IMPORTS"),
                    "color": {"color": "#f97316" if is_active_path else "#334155", "highlight": "#38bdf8"},
                    "width": 2.5 if is_active_path else 1.0,
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                    "font": {"color": "#64748b", "size": 9, "face": "monospace", "align": "top"},
                })

        # Connect any isolated impacted components to their actual dependency target using dependency_path
        connected_nodes = {e["from"] for e in edges_list}.union({e["to"] for e in edges_list})
        gz_nodes = [nid for nid, d in nodes_dict.items() if d.get("group") == "ground_zero"]

        for comp in report.affected_components:
            nid = comp.symbol_name if comp.symbol_name in nodes_dict else _resolve_to_node_id(comp.symbol_name)
            if not nid or nid in connected_nodes:
                continue

            target_cand = None
            if comp.dependency_path and len(comp.dependency_path) >= 2:
                for step in reversed(comp.dependency_path[:-1]):
                    step_nid = _resolve_to_node_id(step)
                    if step_nid and step_nid != nid:
                        target_cand = step_nid
                        break

            if not target_cand and gz_nodes:
                target_cand = gz_nodes[0]

            if target_cand and (nid, target_cand) not in seen_edges and nid != target_cand:
                seen_edges.add((nid, target_cand))
                edge_id += 1
                edges_list.append({
                    "id": f"e_path_{edge_id}",
                    "from": nid,
                    "to": target_cand,
                    "label": "DEPENDS_ON",
                    "color": {"color": "#f97316", "highlight": "#38bdf8"},
                    "width": 2.0,
                    "dashes": True,
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                    "font": {"color": "#64748b", "size": 9, "face": "monospace", "align": "top"},
                })
                connected_nodes.add(nid)
                connected_nodes.add(target_cand)

        nodes_data_list = list(nodes_dict.values())
        return cls._render_vis_canvas(
            nodes=nodes_data_list,
            edges=edges_list,
            height=height,
            title=title or "Interactive Blast Radius Force-Directed Graph",
            show_legend=True,
        )

    @classmethod
    def generate_architecture_graph_html(
        cls,
        graph: CodeGraph,
        height: int = 650,
        max_nodes: int = 60,
    ) -> str:
        """Generates an interactive force-directed architecture graph of the full codebase."""
        nodes_dict: Dict[str, Dict[str, Any]] = {}
        edges_list: List[Dict[str, Any]] = []

        pagerank = graph.compute_pagerank()

        # Sort symbols by PageRank centrality
        sorted_syms = sorted(
            graph.symbols_by_name.values(),
            key=lambda s: pagerank.get(s.qualified_name, 0.0),
            reverse=True,
        )

        for s in sorted_syms[:max_nodes]:
            clean_name = s.name
            if clean_name.startswith("__") or "test" in clean_name.lower():
                continue

            lang = s.language.lower()
            lang_color = cls.LANGUAGE_COLORS.get(lang, "#38bdf8")
            pr_score = pagerank.get(s.qualified_name, 0.01)
            node_size = int(max(14, min(36, 12 + pr_score * 300)))

            tooltip_html = cls._build_node_tooltip(
                name=s.name,
                role=f"Core Component (PageRank: {pr_score:.4f})",
                role_color=lang_color,
                language=s.language,
                lines_str=f"{s.line_start}-{s.line_end} ({s.line_end - s.line_start + 1} lines)",
                complexity=s.complexity,
                risk_flags=[],
                file_path=s.file_path,
                symbol_type=s.symbol_type.value,
            )

            nodes_dict[s.qualified_name] = {
                "id": s.qualified_name,
                "label": s.name,
                "color": {
                    "background": lang_color,
                    "border": "#1e293b",
                    "highlight": {"background": "#ffffff", "border": lang_color},
                },
                "size": node_size,
                "shape": "dot",
                "font": {"color": "#f8fafc", "face": "monospace", "size": 11},
                "borderWidth": 2,
                "tooltipHtml": tooltip_html,
            }

        # Add file nodes
        for f in graph.file_level_graph.nodes:
            clean_f = f.replace("\\", "/")
            if clean_f not in nodes_dict and not Path(clean_f).stem.startswith("__"):
                lang = RepoManager.detect_language(clean_f).lower()
                lang_color = cls.LANGUAGE_COLORS.get(lang, "#64748b")
                tooltip_html = cls._build_node_tooltip(
                    name=Path(clean_f).name,
                    role="File Module",
                    role_color=lang_color,
                    language=RepoManager.detect_language(clean_f),
                    lines_str="File Module",
                    complexity=1,
                    risk_flags=[],
                    file_path=clean_f,
                    symbol_type="File",
                )
                nodes_dict[clean_f] = {
                    "id": clean_f,
                    "label": Path(clean_f).name,
                    "color": {"background": lang_color, "border": "#334155"},
                    "size": 18,
                    "shape": "box",
                    "font": {"color": "#ffffff", "face": "monospace", "size": 10},
                    "borderWidth": 1,
                    "tooltipHtml": tooltip_html,
                }

        # Build edges
        edge_id = 0
        seen_edges: Set[Tuple[str, str]] = set()
        node_keys = set(nodes_dict.keys())

        for u, v, data in graph.graph.edges(data=True):
            if u in node_keys and v in node_keys and u != v and (u, v) not in seen_edges:
                seen_edges.add((u, v))
                edge_id += 1
                edges_list.append({
                    "id": f"e{edge_id}",
                    "from": u,
                    "to": v,
                    "label": data.get("edge_type", "CALLS"),
                    "color": {"color": "#334155", "highlight": "#38bdf8"},
                    "width": 1.2,
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                    "font": {"color": "#64748b", "size": 8, "face": "monospace"},
                })

        for u, v, data in graph.file_level_graph.edges(data=True):
            u_c = u.replace("\\", "/")
            v_c = v.replace("\\", "/")
            if u_c in node_keys and v_c in node_keys and u_c != v_c and (u_c, v_c) not in seen_edges:
                seen_edges.add((u_c, v_c))
                edge_id += 1
                edges_list.append({
                    "id": f"e{edge_id}",
                    "from": u_c,
                    "to": v_c,
                    "label": data.get("relation", "IMPORTS"),
                    "color": {"color": "#475569", "highlight": "#38bdf8"},
                    "width": 1.5,
                    "arrows": {"to": {"enabled": True, "scaleFactor": 0.8}},
                    "font": {"color": "#64748b", "size": 8, "face": "monospace"},
                })

        return cls._render_vis_canvas(
            nodes=list(nodes_dict.values()),
            edges=edges_list,
            height=height,
            title="Complete Architecture Knowledge Graph (PageRank Weighted)",
            show_legend=False,
        )

    @classmethod
    def _render_vis_canvas(
        cls,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        height: int,
        title: str,
        show_legend: bool = True,
    ) -> str:
        """Assembles complete standalone HTML document with vis-network canvas, controls, and tooltip overlay."""
        nodes_json = json.dumps(nodes)
        edges_json = json.dumps(edges)

        legend_html = ""
        if show_legend:
            legend_html = """
            <div class="legend-bar">
                <span class="legend-title">Blast Radius Styling:</span>
                <span class="legend-item"><span class="dot red"></span> Ground Zero (Modified)</span>
                <span class="legend-item"><span class="dot orange"></span> Depth 1 (Direct Dependent)</span>
                <span class="legend-item"><span class="dot yellow"></span> Depth 2+ (Transitive Dependent)</span>
                <span class="legend-item"><span class="dot gray"></span> Surrounding Components</span>
            </div>
            """

        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{html.escape(title)}</title>
    <!-- Primary and fallback CDNs for vis-network -->
    <script type="text/javascript" src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
    <script type="text/javascript">
        if (typeof vis === "undefined") {{
            document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"><\\/script>');
        }}
    </script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #0b1120;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            overflow: hidden;
            width: 100%;
            height: {height}px;
            position: relative;
        }}
        #container {{
            width: 100%;
            height: 100%;
            position: relative;
            background: radial-gradient(circle at 50% 50%, #1e293b 0%, #0b1120 100%);
            border: 1px solid #1e293b;
            border-radius: 8px;
            overflow: hidden;
        }}
        #network-canvas {{
            width: 100%;
            height: 100%;
        }}
        /* Top Control Bar */
        .controls-bar {{
            position: absolute;
            top: 10px;
            left: 12px;
            right: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 10;
            pointer-events: none;
            gap: 10px;
        }}
        .controls-left, .controls-right {{
            display: flex;
            align-items: center;
            gap: 8px;
            pointer-events: auto;
        }}
        .search-input {{
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid #334155;
            color: #f8fafc;
            font-size: 12px;
            padding: 6px 12px;
            border-radius: 6px;
            outline: none;
            width: 180px;
            backdrop-filter: blur(8px);
            transition: all 0.2s;
        }}
        .search-input:focus {{
            border-color: #38bdf8;
            box-shadow: 0 0 8px rgba(56, 189, 248, 0.4);
            width: 220px;
        }}
        .btn {{
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid #475569;
            color: #f8fafc;
            font-size: 12px;
            padding: 6px 10px;
            border-radius: 6px;
            cursor: pointer;
            backdrop-filter: blur(8px);
            transition: background 0.2s;
            user-select: none;
        }}
        .btn:hover {{
            background: #334155;
            border-color: #38bdf8;
        }}
        .legend-bar {{
            position: absolute;
            bottom: 10px;
            left: 12px;
            display: flex;
            align-items: center;
            gap: 14px;
            background: rgba(15, 23, 42, 0.85);
            padding: 6px 14px;
            border-radius: 6px;
            border: 1px solid #1e293b;
            font-size: 11px;
            backdrop-filter: blur(8px);
            z-index: 10;
            pointer-events: auto;
        }}
        .legend-title {{ font-weight: bold; color: #94a3b8; }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
        .dot.red {{ background: #ef4444; box-shadow: 0 0 6px #ef4444; }}
        .dot.orange {{ background: #f97316; box-shadow: 0 0 6px #f97316; }}
        .dot.yellow {{ background: #eab308; box-shadow: 0 0 6px #eab308; }}
        .dot.gray {{ background: #64748b; }}

        /* Floating Tooltip */
        #custom-tooltip {{
            position: absolute;
            display: none;
            background: rgba(15, 23, 42, 0.96);
            border: 1px solid #38bdf8;
            border-radius: 8px;
            padding: 10px 14px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.7);
            pointer-events: none;
            z-index: 100;
            max-width: 340px;
            backdrop-filter: blur(12px);
        }}
    </style>
</head>
<body>
    <div id="container">
        <div class="controls-bar">
            <div class="controls-left">
                <input id="node-search" class="search-input" type="text" placeholder="Search component..." />
            </div>
            <div class="controls-right">
                <button id="btn-physics" class="btn" title="Toggle physics simulation">Pause Physics</button>
                <button id="btn-zoom-in" class="btn" title="Zoom In">+</button>
                <button id="btn-zoom-out" class="btn" title="Zoom Out">−</button>
                <button id="btn-fit" class="btn" title="Fit to Screen">Fit View</button>
            </div>
        </div>

        {legend_html}

        <div id="network-canvas"></div>
        <div id="custom-tooltip"></div>
    </div>

    <script type="text/javascript">
        (function() {{
            var rawNodes = {nodes_json};
            var rawEdges = {edges_json};

            var container = document.getElementById("network-canvas");
            var tooltipEl = document.getElementById("custom-tooltip");
            var searchInput = document.getElementById("node-search");
            var physicsBtn = document.getElementById("btn-physics");
            var zoomInBtn = document.getElementById("btn-zoom-in");
            var zoomOutBtn = document.getElementById("btn-zoom-out");
            var fitBtn = document.getElementById("btn-fit");

            if (!rawNodes || rawNodes.length === 0) {{
                container.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100%;color:#94a3b8;flex-direction:column;font-size:13px;padding:20px;text-align:center;">' +
                    '<span style="font-size:24px;margin-bottom:8px;color:#38bdf8;">◈</span>' +
                    '<h4 style="color:#38bdf8;margin-bottom:6px;">No Components in Graph</h4>' +
                    '<p style="color:#64748b;">The working tree is clean or no modified/dependent components were detected.</p>' +
                    '</div>';
                return;
            }}

            if (typeof vis === "undefined") {{
                // Fallback rendering if CDN is unavailable
                container.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100%;color:#94a3b8;flex-direction:column;">' +
                    '<h3 style="color:#38bdf8;margin-bottom:8px;">Interactive Knowledge Graph (' + rawNodes.length + ' nodes, ' + rawEdges.length + ' edges)</h3>' +
                    '<p>Ground Zero: <b style="color:#ef4444;">' + rawNodes.filter(function(n){{return n.group==='ground_zero';}}).length + '</b> | ' +
                    'Depth 1: <b style="color:#f97316;">' + rawNodes.filter(function(n){{return n.group==='depth_1';}}).length + '</b> | ' +
                    'Depth 2+: <b style="color:#eab308;">' + rawNodes.filter(function(n){{return n.group==='depth_2_plus';}}).length + '</b></p>' +
                    '</div>';
                return;
            }}

            var nodesDataSet = new vis.DataSet(rawNodes);
            var edgesDataSet = new vis.DataSet(rawEdges);

            var data = {{
                nodes: nodesDataSet,
                edges: edgesDataSet
            }};

            var options = {{
                nodes: {{
                    borderWidth: 2,
                    shadow: {{ enabled: true, color: 'rgba(0,0,0,0.5)', size: 10, x: 2, y: 2 }},
                    font: {{ color: '#f8fafc', face: 'monospace', size: 11 }}
                }},
                edges: {{
                    smooth: {{ type: 'cubicBezier', forceDirection: 'none', roundness: 0.2 }},
                    shadow: {{ enabled: false }}
                }},
                physics: {{
                    enabled: true,
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {{
                        gravitationalConstant: -40,
                        centralGravity: 0.008,
                        springLength: 90,
                        springConstant: 0.08,
                        damping: 0.45,
                        avoidOverlap: 0.8
                    }},
                    stabilization: {{
                        enabled: true,
                        iterations: 150,
                        updateInterval: 25
                    }}
                }},
                interaction: {{
                    hover: true,
                    dragNodes: true,
                    dragView: true,
                    zoomView: true,
                    hoverConnectedEdges: true,
                    tooltipDelay: 50
                }}
            }};

            var network = new vis.Network(container, data, options);
            var physicsRunning = true;

            // Physics toggle
            physicsBtn.addEventListener("click", function() {{
                physicsRunning = !physicsRunning;
                network.setOptions({{ physics: {{ enabled: physicsRunning }} }});
                physicsBtn.textContent = physicsRunning ? "Pause Physics" : "Resume Physics";
            }});

            // Zoom and Fit controls
            zoomInBtn.addEventListener("click", function() {{
                var scale = network.getScale();
                network.moveTo({{ scale: scale * 1.3, animation: {{ duration: 200 }} }});
            }});
            zoomOutBtn.addEventListener("click", function() {{
                var scale = network.getScale();
                network.moveTo({{ scale: scale / 1.3, animation: {{ duration: 200 }} }});
            }});
            fitBtn.addEventListener("click", function() {{
                network.fit({{ animation: {{ duration: 400, easingFunction: 'easeInOutQuad' }} }});
            }});

            // Search Filter
            searchInput.addEventListener("input", function(e) {{
                var q = e.target.value.trim().toLowerCase();
                if (!q) {{
                    // Reset styling
                    nodesDataSet.forEach(function(node) {{
                        var orig = rawNodes.find(function(rn) {{ return rn.id === node.id; }});
                        if (orig) {{
                            nodesDataSet.update({{ id: node.id, color: orig.color, opacity: 1.0 }});
                        }}
                    }});
                    return;
                }}

                var matchedId = null;
                nodesDataSet.forEach(function(node) {{
                    var label = (node.label || "").toLowerCase();
                    var idStr = String(node.id).toLowerCase();
                    if (label.indexOf(q) !== -1 || idStr.indexOf(q) !== -1) {{
                        matchedId = node.id;
                        nodesDataSet.update({{
                            id: node.id,
                            color: {{ background: '#38bdf8', border: '#ffffff' }},
                            opacity: 1.0
                        }});
                    }} else {{
                        nodesDataSet.update({{
                            id: node.id,
                            opacity: 0.25
                        }});
                    }}
                }});

                if (matchedId) {{
                    network.focus(matchedId, {{
                        scale: 1.2,
                        animation: {{ duration: 300, easingFunction: 'easeInOutQuad' }}
                    }});
                }}
            }});

            // Hover Tooltip Interactions
            network.on("hoverNode", function(params) {{
                var nodeId = params.node;
                var nodeData = nodesDataSet.get(nodeId);
                if (nodeData && nodeData.tooltipHtml) {{
                    tooltipEl.innerHTML = nodeData.tooltipHtml;
                    tooltipEl.style.display = "block";
                    if (params.pointer && params.pointer.DOM) {{
                        var rect = container.getBoundingClientRect();
                        var x = params.pointer.DOM.x + 16;
                        var y = params.pointer.DOM.y + 16;
                        if (x + 340 > rect.width) x = params.pointer.DOM.x - 350;
                        if (y + 200 > rect.height) y = params.pointer.DOM.y - 200;
                        tooltipEl.style.left = Math.max(10, x) + "px";
                        tooltipEl.style.top = Math.max(10, y) + "px";
                    }}
                }}
            }});

            network.on("blurNode", function() {{
                tooltipEl.style.display = "none";
            }});

            container.addEventListener("mousemove", function(e) {{
                if (tooltipEl.style.display === "block") {{
                    var rect = container.getBoundingClientRect();
                    var x = e.clientX - rect.left + 16;
                    var y = e.clientY - rect.top + 16;

                    // Prevent tooltip from overflowing canvas boundaries
                    if (x + 340 > rect.width) {{
                        x = e.clientX - rect.left - 350;
                    }}
                    if (y + 200 > rect.height) {{
                        y = e.clientY - rect.top - 200;
                    }}

                    tooltipEl.style.left = Math.max(10, x) + "px";
                    tooltipEl.style.top = Math.max(10, y) + "px";
                }}
            }});

            // Once network stabilises, gently slow down physics
            network.once("stabilizationIterationsDone", function() {{
                network.setOptions({{
                    physics: {{
                        forceAtlas2Based: {{ damping: 0.8 }}
                    }}
                }});
            }});
        }})();
    </script>
</body>
</html>
        """.strip()

        return html_template
