"""
Graph-Augmented Retrieval (Graph-RAG) Engine
Combines semantic retrieval with graph topology (callers, callees, blast radius)
to answer complex architectural and impact questions about the codebase.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from codebase_doctor.graph import CodeGraph
from codebase_doctor.llm_provider import BaseLLMProvider, get_llm_provider
from codebase_doctor.models import Symbol, SymbolType


class GraphRAG:
    """Answers queries about the codebase by fusing graph topology with code retrieval."""

    def __init__(self, graph: CodeGraph, llm: Optional[BaseLLMProvider] = None):
        self.graph = graph
        self.llm = llm or get_llm_provider()

    def answer_query(self, question: str) -> Dict[str, Any]:
        """Answers an architectural or code question using Graph-RAG."""
        # 1. Identify relevant symbols from question text
        matched_symbols = self._find_relevant_symbols(question)

        # 2. Extract graph neighborhood context
        context_snippets = []
        context_nodes = []

        for sym in matched_symbols[:3]:
            context_nodes.append(sym.qualified_name)
            # Find direct callers and callees
            callers = [u for u, _, _ in self.graph.get_upstream_dependents(sym.qualified_name, max_depth=2)[:5]]
            callees = [v for v, _ in self.graph.get_downstream_dependencies(sym.qualified_name, max_depth=2)[:5]]

            lang_tag = getattr(sym, "language", "") or "text"
            snippet = (
                f"=== Symbol: {sym.qualified_name} ({sym.symbol_type.value}, {lang_tag}) in {sym.file_path} ===\n"
                f"Parameters: {', '.join(sym.parameters) if sym.parameters else 'None'}\n"
                f"Complexity: {sym.complexity}\n"
                f"Docstring: {sym.docstring or 'None'}\n"
                f"Direct Callers (Depends on this): {', '.join(callers) if callers else 'None (entry point or unreferenced)'}\n"
                f"Calls (Dependencies): {', '.join(callees) if callees else 'None'}\n"
                f"Source Implementation:\n```{lang_tag}\n{sym.source_code[:1200]}\n```\n"
            )
            context_snippets.append(snippet)

        if not context_snippets:
            # Fallback to key central nodes in graph
            pagerank = self.graph.compute_pagerank()
            top_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:3]
            for node_name, score in top_nodes:
                sym = self.graph.get_symbol(node_name)
                if sym:
                    context_nodes.append(sym.qualified_name)
                    lang_tag = getattr(sym, "language", "") or "text"
                    context_snippets.append(
                        f"=== Core Node: {sym.qualified_name} (Centrality: {score:.3f}, {lang_tag}) in {sym.file_path} ===\n"
                        f"Docstring: {sym.docstring or 'None'}\n"
                        f"Source Snippet:\n```{lang_tag}\n{sym.source_code[:800]}\n```\n"
                    )

        # 3. Build Prompt
        context_block = "\n".join(context_snippets)
        system_prompt = (
            "You are an expert AI Codebase Doctor and Senior Software Architect. "
            "You analyze legacy codebases, explain architectural ripple effects, identify what could break, "
            "and suggest precise testing strategies using both code and the dependency graph provided."
        )
        user_prompt = (
            f"Here is the architectural knowledge graph context from the codebase:\n\n"
            f"{context_block}\n\n"
            f"User Question: {question}\n\n"
            f"Provide a clear, detailed, and structured response addressing:\n"
            f"1. Potential blast radius and what components could break.\n"
            f"2. Specific contract, state, or concurrency risks.\n"
            f"3. Concrete verification and testing suggestions."
        )

        # 4. Generate answer
        answer = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)

        return {
            "question": question,
            "answer": answer,
            "retrieved_nodes": context_nodes,
            "context_summary": f"Retrieved {len(context_nodes)} symbols with graph relationships.",
            "context_block": context_block,
        }

    STOPWORDS: Set[str] = {
        "a", "an", "the", "and", "or", "if", "i", "this", "that", "what", "else", "could", "would",
        "break", "breaks", "modify", "modifies", "changing", "change", "function", "class", "method",
        "service", "file", "code", "in", "on", "at", "to", "for", "with", "about", "how", "does",
        "do", "is", "are", "why", "we", "my", "our",
    }

    def _find_relevant_symbols(self, query: str) -> List[Symbol]:
        """Matches symbols against query using names, stems, filenames, and docstrings."""
        import re as _re
        query_lower = query.lower()

        # Extract explicit filenames from query (e.g. "real_time_detection.py", "auth_service.py")
        filename_pattern = _re.compile(r'[\w\-]+\.(?:py|js|ts|java|go|rs|c|cpp|h|ino|sql|rb|php|kt|cs)\b', _re.IGNORECASE)
        query_filenames = [m.group().lower() for m in filename_pattern.finditer(query)]
        # Also extract stems (e.g. "real_time_detection" from "real_time_detection.py")
        query_file_stems = [fn.rsplit('.', 1)[0] for fn in query_filenames]

        raw_words = query_lower.replace("_", " ").replace("?", " ").replace("!", " ").replace(".", " ").split()
        query_words = {w for w in raw_words if w not in self.STOPWORDS and len(w) > 2}
        scored_symbols: List[Tuple[Symbol, int]] = []

        for sym in self.graph.symbols_by_name.values():
            score = 0
            sym_name_lower = sym.name.lower()
            sym_qual_lower = sym.qualified_name.lower()
            sym_file_lower = sym.file_path.lower().replace("\\", "/") if sym.file_path else ""

            # HIGH PRIORITY: File path match — if the user explicitly mentions a filename
            for fn in query_filenames:
                if sym_file_lower.endswith(fn) or fn in sym_file_lower:
                    score += 30
            for stem in query_file_stems:
                if stem in sym_name_lower or stem in sym_qual_lower:
                    score += 25

            # Exact name match in query
            if sym_name_lower in query_lower and sym_name_lower not in self.STOPWORDS:
                score += 20

            # Word token match
            for word in query_words:
                if word == sym_name_lower:
                    score += 15
                elif word in sym_name_lower:
                    score += 10
                elif sym_name_lower.startswith(word) or word.startswith(sym_name_lower):
                    score += 8
                elif word in sym_qual_lower:
                    score += 5
                elif sym.docstring and word in sym.docstring.lower():
                    score += 3

            # Query intent matching (e.g. if user asks for "function" or "class")
            if "function" in query_lower and sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                score += 5
            elif "class" in query_lower and sym.symbol_type == SymbolType.CLASS:
                score += 5

            # Granularity preference: prefer specific functions/classes over whole modules
            if sym.symbol_type in (SymbolType.FUNCTION, SymbolType.METHOD):
                score += 4
            elif sym.symbol_type == SymbolType.CLASS:
                score += 2
            elif sym.symbol_type == SymbolType.MODULE:
                score -= 1

            # Deprioritize test functions unless query specifically queries tests
            if sym.symbol_type == SymbolType.TEST or "test" in sym.file_path.lower() or sym.name.startswith("test_"):
                if "test" not in query_words:
                    score -= 20

            if score > 0:
                scored_symbols.append((sym, score))

        scored_symbols.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in scored_symbols]

