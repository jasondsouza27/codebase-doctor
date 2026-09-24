"""
Code Knowledge Graph Builder
Builds a directed multi-edge knowledge graph using NetworkX.
Provides reverse dependency traversal, PageRank centrality, and cycle detection.
"""

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from codebase_doctor.models import DependencyEdge, EdgeType, Symbol, SymbolType


class CodeGraph:
    """Directed Knowledge Graph representing the codebase architecture."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.symbols_by_name: Dict[str, Symbol] = {}
        self.symbols_by_file: Dict[str, List[Symbol]] = defaultdict(list)
        self.file_level_graph = nx.DiGraph()
        self._pagerank_cache: Optional[Dict[str, float]] = None

    def add_symbol(self, symbol: Symbol):
        """Adds a symbol as a node in the graph."""
        self.symbols_by_name[symbol.qualified_name] = symbol
        self.symbols_by_file[symbol.file_path].append(symbol)

        self.graph.add_node(
            symbol.qualified_name,
            name=symbol.name,
            type=symbol.symbol_type.value,
            file_path=symbol.file_path,
            line_start=symbol.line_start,
            line_end=symbol.line_end,
            complexity=symbol.complexity,
            docstring=symbol.docstring or "",
        )

        # Ensure file node exists in file-level graph
        if not self.file_level_graph.has_node(symbol.file_path):
            self.file_level_graph.add_node(symbol.file_path, type="file")

    def add_edge(self, edge: DependencyEdge):
        """Adds a directed dependency edge (source -> target)."""
        resolved_target = self._resolve_target(edge.target, source=edge.source, edge_type=edge.edge_type)

        self.graph.add_edge(
            edge.source,
            resolved_target,
            edge_type=edge.edge_type.value,
            line_number=edge.line_number,
            metadata=edge.metadata,
        )

        # Update file-level graph
        src_sym = self.symbols_by_name.get(edge.source)
        tgt_sym = self.symbols_by_name.get(resolved_target)
        src_file = src_sym.file_path if src_sym else (edge.source if self.file_level_graph.has_node(edge.source) else None)
        tgt_file = tgt_sym.file_path if tgt_sym else (resolved_target if self.file_level_graph.has_node(resolved_target) else None)

        if src_file and tgt_file and src_file != tgt_file:
            self.file_level_graph.add_edge(
                src_file,
                tgt_file,
                relation=edge.edge_type.value,
            )

    def remove_file(self, file_path: str):
        """
        Removes all symbols, symbol-level nodes/edges, and file-level nodes
        associated with the given file. Invalidates PageRank cache.
        """
        clean_path = file_path.replace("\\", "/")
        symbols_to_remove = list(self.symbols_by_file.get(clean_path, []))

        for sym in symbols_to_remove:
            if self.graph.has_node(sym.qualified_name):
                self.graph.remove_node(sym.qualified_name)
            self.symbols_by_name.pop(sym.qualified_name, None)

        self.symbols_by_file.pop(clean_path, None)

        if self.file_level_graph.has_node(clean_path):
            self.file_level_graph.remove_node(clean_path)
        if self.graph.has_node(clean_path):
            self.graph.remove_node(clean_path)

        self._pagerank_cache = None

    def rebuild_file_level_graph(self):
        """Reconstructs the file-level dependency graph after all symbols and edges are loaded."""
        self.file_level_graph.clear()
        for f in self.symbols_by_file:
            self.file_level_graph.add_node(f, type="file")

        for u, v, data in self.graph.edges(data=True):
            edge_type_val = data.get("edge_type")
            e_type = EdgeType(edge_type_val) if edge_type_val in EdgeType._value2member_map_ else None
            src_sym = self.symbols_by_name.get(u)
            tgt_sym = self.symbols_by_name.get(v)
            resolved = None
            if not tgt_sym:
                resolved = self._resolve_target(v, source=u, edge_type=e_type)
                tgt_sym = self.symbols_by_name.get(resolved)

            src_file = src_sym.file_path if src_sym else (u if self.file_level_graph.has_node(u) else None)
            tgt_target = resolved or v
            tgt_file = tgt_sym.file_path if tgt_sym else (
                tgt_target if self.file_level_graph.has_node(tgt_target) else (
                    v if self.file_level_graph.has_node(v) else None
                )
            )

            if src_file and tgt_file and src_file != tgt_file:
                self.file_level_graph.add_edge(
                    src_file,
                    tgt_file,
                    relation=data.get("edge_type", "CALLS"),
                )

    def _resolve_target(
        self,
        target: str,
        source: Optional[str] = None,
        edge_type: Optional[EdgeType] = None,
    ) -> str:
        """
        Resolves partial symbol names, header names, or relative paths to names in the graph.
        Context-aware: uses source and edge_type to avoid spurious cross-file / cross-language edges.
        """
        if not target:
            return target

        if target in self.symbols_by_name:
            return target

        clean_tgt = target.replace("\\", "/")
        if clean_tgt.startswith("./"):
            clean_tgt = clean_tgt[2:]

        # 1. Exact match in file-level graph
        if self.file_level_graph.has_node(target):
            return target
        if self.file_level_graph.has_node(clean_tgt):
            return clean_tgt

        # Find calling source file
        src_sym = self.symbols_by_name.get(source) if source else None
        src_file = src_sym.file_path if src_sym else (source if source and self.file_level_graph.has_node(source) else None)

        # 2. Imports, includes, and references
        is_import = edge_type in (EdgeType.IMPORTS, EdgeType.INCLUDES, EdgeType.REFERENCES) if edge_type else False

        if is_import:
            # 2a. Relative path resolution from source file's directory (normalizes .. and .)
            if src_file:
                src_dir = Path(src_file).parent
                base_cand = (src_dir / clean_tgt).as_posix()
                normalized_base = os.path.normpath(base_cand).replace("\\", "/")
                extensions = [
                    "", ".ts", ".tsx", ".js", ".jsx", ".py", ".h", ".hpp", ".cpp", ".c", ".ino",
                    "/index.ts", "/index.tsx", "/index.js", "/index.jsx", "/index.py"
                ]
                for ext in extensions:
                    cand = f"{normalized_base}{ext}"
                    if self.file_level_graph.has_node(cand):
                        if cand in self.symbols_by_file and self.symbols_by_file[cand]:
                            return self.symbols_by_file[cand][0].qualified_name
                        return cand

            # 2b. Path alias resolution (e.g. "@/components/ui/button" -> "frontend/src/components/ui/button.tsx")
            if target.startswith("@/"):
                alias_sub = target[2:]
                for f in self.file_level_graph.nodes:
                    if f.endswith(alias_sub) or any(f.endswith(f"{alias_sub}{ext}") for ext in [".ts", ".tsx", ".js", ".jsx"]):
                        if f in self.symbols_by_file and self.symbols_by_file[f]:
                            return self.symbols_by_file[f][0].qualified_name
                        return f

            # 2c. Header / file basename matching for C/C++/Arduino includes
            for f in self.file_level_graph.nodes:
                f_name = Path(f).name
                if f == clean_tgt or f.endswith(f"/{clean_tgt}") or f_name == clean_tgt or f_name == Path(clean_tgt).name:
                    if f in self.symbols_by_file and self.symbols_by_file[f]:
                        return self.symbols_by_file[f][0].qualified_name
                    return f

            # 2d. Dotted module name matching (Python: e.g. "payment_service" or "esp32.serial_bridge")
            dotted = target.replace("/", ".")
            if dotted in self.symbols_by_name:
                return dotted
            for q in self.symbols_by_name:
                if q == dotted or q.endswith(f".{dotted}"):
                    return q

        # 3. Call resolution (EdgeType.CALLS, DEFINES, INHERITS, INSTANTIATES)
        if src_file:
            # 3a. Prefer local symbols defined in the caller's own file/module
            local_syms = self.get_symbols_for_file(src_file)
            for s in local_syms:
                if s.name == target or s.qualified_name == target or s.qualified_name.endswith(f".{target}"):
                    return s.qualified_name

        # 3b. If qualified name with dots (e.g. "PaymentService.process_payment" or "api.fetchData"), suffix match
        if "." in target:
            candidates = [q for q in self.symbols_by_name if q.endswith(f".{target}") or q.endswith(target)]
            if len(candidates) == 1:
                return candidates[0]
            elif len(candidates) > 1:
                candidates.sort(key=lambda x: len(x))
                return candidates[0]

        # 3c. If target is a capitalized class/type name (PascalCase), search classes/types across repo
        if target and target[0].isupper() and len(target) > 2:
            for sym in self.symbols_by_name.values():
                if sym.name == target and sym.symbol_type in (SymbolType.CLASS, SymbolType.STRUCT, SymbolType.INTERFACE, SymbolType.SCHEMA):
                    return sym.qualified_name

        # Never match bare, lowercase common words globally across languages
        return target

    def get_symbol(self, qualified_or_short_name: str) -> Optional[Symbol]:
        """Finds a symbol by qualified name or short name."""
        if qualified_or_short_name in self.symbols_by_name:
            return self.symbols_by_name[qualified_or_short_name]

        # Search by short name
        for sym in self.symbols_by_name.values():
            if sym.name == qualified_or_short_name:
                return sym
            if sym.qualified_name.endswith(f".{qualified_or_short_name}"):
                return sym

        return None

    def get_symbols_for_file(self, file_path: str) -> List[Symbol]:
        """Returns all symbols declared in a file."""
        norm_path = file_path.replace("\\", "/")
        target_name = Path(norm_path).name
        matches = []
        for p, syms in self.symbols_by_file.items():
            if p == norm_path or Path(p).name == target_name:
                matches.extend(syms)
        return matches

    def get_upstream_dependents(self, node: str, max_depth: int = 5) -> List[Tuple[str, int, List[str]]]:
        """
        Traverses REVERSE edges to find who depends on `node`.
        If A calls B, edge is A -> B.
        Reverse edge is B -> A.
        Returns: List of (dependent_node, depth, path)
        """
        resolved = self._resolve_target(node)
        if resolved not in self.graph:
            # Check if it matches a file path
            return self._get_upstream_file_dependents(node, max_depth)

        from collections import deque
        rev_graph = self.graph.reverse(copy=False)
        visited: Dict[str, Tuple[int, List[str]]] = {}
        queue = deque([(resolved, 0, [resolved])])

        while queue:
            curr, depth, path = queue.popleft()
            if curr != resolved and curr not in visited:
                visited[curr] = (depth, path)

            if depth < max_depth:
                for pred in rev_graph.neighbors(curr):
                    if pred not in visited and pred != resolved and pred not in path:
                        visited[pred] = (depth + 1, path + [pred])
                        queue.append((pred, depth + 1, path + [pred]))

        results = [(k, v[0], v[1]) for k, v in visited.items()]
        results.sort(key=lambda x: (x[1], x[0]))
        return results

    def _get_upstream_file_dependents(self, file_path: str, max_depth: int = 5) -> List[Tuple[str, int, List[str]]]:
        """Finds dependent files using the file-level reverse graph."""
        norm_path = file_path.replace("\\", "/")
        target_name = Path(norm_path).name
        matched_node = None
        for f in self.file_level_graph.nodes:
            if f == norm_path or Path(f).name == target_name:
                matched_node = f
                break

        if not matched_node:
            # Check if any symbol in that file is known
            syms = self.get_symbols_for_file(file_path)
            if syms:
                all_deps = []
                for s in syms:
                    all_deps.extend(self.get_upstream_dependents(s.qualified_name, max_depth))
                return all_deps
            return []

        from collections import deque
        rev_file_graph = self.file_level_graph.reverse(copy=False)
        visited: Dict[str, Tuple[int, List[str]]] = {}
        queue = deque([(matched_node, 0, [matched_node])])

        while queue:
            curr, depth, path = queue.popleft()
            if curr != matched_node and curr not in visited:
                visited[curr] = (depth, path)

            if depth < max_depth:
                for pred in rev_file_graph.neighbors(curr):
                    if pred not in visited and pred != matched_node and pred not in path:
                        visited[pred] = (depth + 1, path + [pred])
                        queue.append((pred, depth + 1, path + [pred]))

        results = [(k, v[0], v[1]) for k, v in visited.items()]
        results.sort(key=lambda x: (x[1], x[0]))
        return results

    def get_downstream_dependencies(self, node: str, max_depth: int = 3) -> List[Tuple[str, int]]:
        """Finds what this node depends on (forward traversal)."""
        resolved = self._resolve_target(node)
        if resolved not in self.graph:
            return []

        visited: Dict[str, int] = {}
        queue: List[Tuple[str, int]] = [(resolved, 0)]

        while queue:
            curr, depth = queue.pop(0)
            if curr != resolved and curr not in visited:
                visited[curr] = depth

            if depth < max_depth:
                for succ in self.graph.neighbors(curr):
                    if succ not in visited:
                        queue.append((succ, depth + 1))

        return sorted(visited.items(), key=lambda x: x[1])

    def compute_pagerank(self) -> Dict[str, float]:
        """Calculates PageRank centrality to identify architectural core nodes."""
        if self._pagerank_cache is not None:
            return self._pagerank_cache

        if len(self.graph) == 0:
            return {}

        try:
            self._pagerank_cache = nx.pagerank(self.graph, alpha=0.85)
        except Exception:
            # Fallback if power iteration fails
            self._pagerank_cache = {n: 1.0 / len(self.graph) for n in self.graph.nodes}

        return self._pagerank_cache

    def detect_circular_dependencies(self) -> List[List[str]]:
        """Detects circular import/call cycles in the codebase."""
        try:
            cycles = list(nx.simple_cycles(self.file_level_graph))
            return cycles
        except Exception:
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Returns structural statistics about the graph including language distribution."""
        languages: Dict[str, int] = defaultdict(int)
        name_map = {
            "python": "Python",
            "arduino": "Arduino/C++",
            "c": "C",
            "cpp": "C++",
            "c_cpp": "C/C++",
            "javascript": "JavaScript",
            "typescript": "TypeScript",
            "java": "Java",
            "kotlin": "Kotlin",
            "go": "Go",
            "rust": "Rust",
            "sql": "SQL",
            "shell": "Shell",
            "config": "Config",
        }
        for sym in self.symbols_by_name.values():
            if sym.symbol_type == SymbolType.MODULE:
                lang = sym.language or "Unknown"
                clean_lang = name_map.get(lang.lower(), lang.title())
                languages[clean_lang] += 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "total_files": self.file_level_graph.number_of_nodes(),
            "total_file_dependencies": self.file_level_graph.number_of_edges(),
            "circular_dependencies_count": len(self.detect_circular_dependencies()),
            "languages": dict(languages),
        }

    def to_cytoscape_elements(self) -> List[Dict[str, Any]]:
        """Exports the graph to Cytoscape.js compatible JSON format."""
        elements = []
        # Add nodes
        for node, data in self.graph.nodes(data=True):
            elements.append({
                "data": {
                    "id": node,
                    "label": data.get("name", node.split(".")[-1]),
                    "type": data.get("type", "unknown"),
                    "file": data.get("file_path", ""),
                    "complexity": data.get("complexity", 1),
                }
            })

        # Add edges
        edge_id = 0
        for u, v, data in self.graph.edges(data=True):
            edge_id += 1
            elements.append({
                "data": {
                    "id": f"e{edge_id}",
                    "source": u,
                    "target": v,
                    "label": data.get("edge_type", "CALLS"),
                }
            })

        return elements
