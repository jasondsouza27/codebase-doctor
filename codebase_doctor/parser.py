"""
Polyglot AST & Grammar Codebase Parser
Extracts symbols (modules, classes, structs, functions, methods, schemas),
imports, includes, calls, inheritance, and complexity across Python, JavaScript/TypeScript,
C/C++/Arduino, Java, Go, Rust, SQL, Shell, and Configuration files.
"""

import ast
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codebase_doctor.models import DependencyEdge, EdgeType, Symbol, SymbolType

try:
    import tree_sitter
    import tree_sitter_javascript as _ts_js
    import tree_sitter_typescript as _ts_ts
    import tree_sitter_cpp as _ts_cpp
    import tree_sitter_go as _ts_go
    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False

_TS_LANG_CACHE: Dict[str, Any] = {}


def _get_ts_language(lang_key: str):
    """Retrieves or instantiates cached Tree-sitter Language object."""
    if not _HAS_TREE_SITTER:
        return None
    if lang_key in _TS_LANG_CACHE:
        return _TS_LANG_CACHE[lang_key]
    try:
        if lang_key == "javascript":
            lang = tree_sitter.Language(_ts_js.language())
        elif lang_key == "typescript":
            lang = tree_sitter.Language(_ts_ts.language_typescript())
        elif lang_key == "tsx":
            lang = tree_sitter.Language(_ts_ts.language_tsx())
        elif lang_key == "cpp":
            lang = tree_sitter.Language(_ts_cpp.language())
        elif lang_key == "go":
            lang = tree_sitter.Language(_ts_go.language())
        else:
            lang = None
        _TS_LANG_CACHE[lang_key] = lang
        return lang
    except Exception:
        return None


class CodeParser:
    """Parses polyglot source code files into Symbols and DependencyEdges."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def parse_file(
        self, file_path: Path, source_code: Optional[str] = None
    ) -> Tuple[List[Symbol], List[DependencyEdge]]:
        """Parses a source file into symbols and local dependency edges."""
        if source_code is None:
            try:
                source_code = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                source_code = file_path.read_text(encoding="latin-1")

        rel_path = self._get_rel_path(file_path)
        mod_name = self._path_to_module_name(rel_path)
        ext = file_path.suffix.lower()
        file_name = file_path.name.lower()

        if ext in {".py", ".pyw"}:
            return self._parse_python(file_path, rel_path, mod_name, source_code)
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}:
            if _HAS_TREE_SITTER:
                try:
                    return _TreeSitterJSVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
                except Exception:
                    pass
            return _JSVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext in {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".ino"}:
            if _HAS_TREE_SITTER:
                try:
                    return _TreeSitterCppVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
                except Exception:
                    pass
            return _CppArduinoVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext in {".java", ".kt", ".scala"}:
            return _JavaVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext == ".go":
            if _HAS_TREE_SITTER:
                try:
                    return _TreeSitterGoVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
                except Exception:
                    pass
            return _GoVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext == ".rs":
            return _RustVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext == ".sql":
            return _SqlVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext in {".sh", ".bash", ".zsh", ".ps1"}:
            return _ShellVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        elif ext in {".json", ".yaml", ".yml", ".toml", ".xml", ".env", ".ini", ".cfg"} or file_name in {
            "dockerfile",
            "makefile",
        }:
            return _ConfigVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()
        else:
            return _GenericVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code).parse()

    def _get_rel_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.repo_root.resolve())).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def _path_to_module_name(self, rel_path: str) -> str:
        """Converts relative path to dotted module name, stripping suffix."""
        path_obj = Path(rel_path)
        parts = list(path_obj.parts)
        if parts:
            stem = path_obj.stem
            if stem == "__init__":
                parts = parts[:-1]
            else:
                parts[-1] = stem
        return ".".join(parts) if parts else path_obj.stem

    def _parse_python(
        self, file_path: Path, rel_path: str, mod_name: str, source_code: str
    ) -> Tuple[List[Symbol], List[DependencyEdge]]:
        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as e:
            mod_symbol = Symbol(
                name=mod_name.split(".")[-1],
                qualified_name=mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=rel_path,
                line_start=1,
                line_end=max(len(source_code.splitlines()), 1),
                docstring=f"SyntaxError during parse: {e}",
                source_code=source_code,
                language="python",
            )
            return [mod_symbol], []

        visitor = _ASTVisitor(mod_name=mod_name, rel_path=rel_path, source_code=source_code)
        visitor.visit(tree)
        return visitor.symbols, visitor.edges


def _mask_text(source: str, mask_comments: bool = True, mask_strings: bool = False, style: str = "c") -> str:
    """
    Masks comments and/or string literals with spaces to avoid false-positive regex matches,
    while preserving newlines and exact line counts.
    style: 'c' (// and /* */), 'sql' (-- and /* */), 'hash' (#)
    """
    if not source:
        return ""

    chars = list(source)
    n = len(chars)
    i = 0

    while i < n:
        # Check string literals: always track string boundaries so comments inside strings are ignored
        is_quote = chars[i] in ('"', "'") or (style == "c" and chars[i] == "`")
        if is_quote:
            quote = chars[i]
            if mask_strings:
                chars[i] = " "
            i += 1
            while i < n and chars[i] != quote:
                if chars[i] == "\\" and i + 1 < n:
                    if mask_strings:
                        chars[i] = " "
                        chars[i + 1] = " "
                    i += 2
                    continue
                if mask_strings and chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i < n and chars[i] == quote:
                if mask_strings:
                    chars[i] = " "
                i += 1
            continue

        # Check comments
        if mask_comments:
            if style == "c":
                if chars[i] == "/" and i + 1 < n and chars[i + 1] == "/":
                    chars[i] = " "
                    chars[i + 1] = " "
                    i += 2
                    while i < n and chars[i] != "\n":
                        chars[i] = " "
                        i += 1
                    continue
                elif chars[i] == "/" and i + 1 < n and chars[i + 1] == "*":
                    chars[i] = " "
                    chars[i + 1] = " "
                    i += 2
                    while i < n:
                        if chars[i] == "*" and i + 1 < n and chars[i + 1] == "/":
                            chars[i] = " "
                            chars[i + 1] = " "
                            i += 2
                            break
                        if chars[i] != "\n":
                            chars[i] = " "
                        i += 1
                    continue

            elif style == "sql":
                if chars[i] == "-" and i + 1 < n and chars[i + 1] == "-":
                    chars[i] = " "
                    chars[i + 1] = " "
                    i += 2
                    while i < n and chars[i] != "\n":
                        chars[i] = " "
                        i += 1
                    continue
                elif chars[i] == "/" and i + 1 < n and chars[i + 1] == "*":
                    chars[i] = " "
                    chars[i + 1] = " "
                    i += 2
                    while i < n:
                        if chars[i] == "*" and i + 1 < n and chars[i + 1] == "/":
                            chars[i] = " "
                            chars[i + 1] = " "
                            i += 2
                            break
                        if chars[i] != "\n":
                            chars[i] = " "
                        i += 1
                    continue

            elif style == "hash":
                if chars[i] == "#":
                    chars[i] = " "
                    i += 1
                    while i < n and chars[i] != "\n":
                        chars[i] = " "
                        i += 1
                    continue

        i += 1

    return "".join(chars)


# ==============================================================================
# Python AST Visitor
# ==============================================================================


class _ASTVisitor(ast.NodeVisitor):
    """Internal AST visitor that walks a Python file AST to extract symbols and edges."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()

        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []

        self.scope_stack: List[str] = [mod_name]
        self.current_class: Optional[str] = None
        self.imports: Dict[str, str] = {}

        mod_doc = ast.get_docstring(ast.parse(source_code)) if source_code.strip() else None
        self.symbols.append(
            Symbol(
                name=mod_name.split(".")[-1],
                qualified_name=mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                docstring=mod_doc,
                source_code=source_code,
                language="python",
            )
        )

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            alias_name = alias.asname or alias.name
            self.imports[alias_name] = alias.name
            self.edges.append(
                DependencyEdge(
                    source=self.scope_stack[-1],
                    target=alias.name,
                    edge_type=EdgeType.IMPORTS,
                    line_number=node.lineno,
                    metadata={"alias": alias_name},
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        if node.level and node.level > 0:
            mod_parts = self.mod_name.split(".")
            base_parts = mod_parts[: -node.level] if len(mod_parts) >= node.level else []
            if module:
                module = ".".join(base_parts + [module]) if base_parts else module
            else:
                module = ".".join(base_parts)

        for alias in node.names:
            alias_name = alias.asname or alias.name
            full_target = f"{module}.{alias.name}" if module else alias.name
            self.imports[alias_name] = full_target
            self.edges.append(
                DependencyEdge(
                    source=self.scope_stack[-1],
                    target=full_target,
                    edge_type=EdgeType.IMPORTS,
                    line_number=node.lineno,
                    metadata={"imported_name": alias.name, "alias": alias_name, "module": module},
                )
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_name = node.name
        qualified_name = f"{self.scope_stack[-1]}.{class_name}"

        for base in node.bases:
            base_name = self._resolve_expr_name(base)
            if base_name:
                resolved_base = self.imports.get(base_name, base_name)
                self.edges.append(
                    DependencyEdge(
                        source=qualified_name,
                        target=resolved_base,
                        edge_type=EdgeType.INHERITS,
                        line_number=node.lineno,
                    )
                )

        decorators = [self._resolve_expr_name(d) for d in node.decorator_list if self._resolve_expr_name(d)]
        end_lineno = getattr(node, "end_lineno", node.lineno)
        src_snippet = "\n".join(self.lines[node.lineno - 1 : end_lineno])

        cls_symbol = Symbol(
            name=class_name,
            qualified_name=qualified_name,
            symbol_type=SymbolType.CLASS,
            file_path=self.rel_path,
            line_start=node.lineno,
            line_end=end_lineno,
            docstring=ast.get_docstring(node),
            decorators=decorators,
            complexity=self._calc_complexity(node),
            source_code=src_snippet,
            language="python",
        )
        self.symbols.append(cls_symbol)

        self.edges.append(
            DependencyEdge(
                source=self.scope_stack[-1],
                target=qualified_name,
                edge_type=EdgeType.DEFINES,
                line_number=node.lineno,
            )
        )

        prev_class = self.current_class
        self.current_class = qualified_name
        self.scope_stack.append(qualified_name)

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node)

    def _handle_function(self, node: ast.AST):
        fn_name = node.name
        is_method = self.current_class is not None
        parent_scope = self.scope_stack[-1]
        qualified_name = f"{parent_scope}.{fn_name}"
        is_test = fn_name.startswith("test_") or "test" in self.rel_path.lower()

        params = [arg.arg for arg in node.args.args]
        ret_type = None
        if getattr(node, "returns", None):
            ret_type = self._resolve_expr_name(node.returns)

        decorators = [self._resolve_expr_name(d) for d in node.decorator_list if self._resolve_expr_name(d)]
        end_lineno = getattr(node, "end_lineno", node.lineno)
        src_snippet = "\n".join(self.lines[node.lineno - 1 : end_lineno])

        fn_type = SymbolType.TEST if is_test else (SymbolType.METHOD if is_method else SymbolType.FUNCTION)

        fn_symbol = Symbol(
            name=fn_name,
            qualified_name=qualified_name,
            symbol_type=fn_type,
            file_path=self.rel_path,
            line_start=node.lineno,
            line_end=end_lineno,
            docstring=ast.get_docstring(node),
            parameters=params,
            return_type=ret_type,
            decorators=decorators,
            complexity=self._calc_complexity(node),
            source_code=src_snippet,
            language="python",
        )
        self.symbols.append(fn_symbol)

        self.edges.append(
            DependencyEdge(
                source=parent_scope,
                target=qualified_name,
                edge_type=EdgeType.DEFINES,
                line_number=node.lineno,
            )
        )

        self.scope_stack.append(qualified_name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_Call(self, node: ast.Call):
        call_name = self._resolve_expr_name(node.func)
        if call_name:
            root_id = call_name.split(".")[0]
            resolved_call = call_name
            if root_id in self.imports:
                imported_target = self.imports[root_id]
                remainder = call_name[len(root_id) :]
                resolved_call = imported_target + remainder

            edge_type = EdgeType.CALLS
            if call_name[0].isupper() or (len(call_name.split(".")) > 1 and call_name.split(".")[-1][0].isupper()):
                edge_type = EdgeType.INSTANTIATES

            self.edges.append(
                DependencyEdge(
                    source=self.scope_stack[-1],
                    target=resolved_call,
                    edge_type=edge_type,
                    line_number=node.lineno,
                    metadata={"raw_call": call_name},
                )
            )

        self.generic_visit(node)

    def _resolve_expr_name(self, expr: ast.AST) -> str:
        if expr is None:
            return ""
        if isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            val = self._resolve_expr_name(expr.value)
            return f"{val}.{expr.attr}" if val else expr.attr
        elif isinstance(expr, ast.Constant):
            return str(expr.value)
        elif isinstance(expr, ast.Call):
            return self._resolve_expr_name(expr.func)
        elif isinstance(expr, ast.Subscript):
            val = self._resolve_expr_name(expr.value)
            slice_name = self._resolve_expr_name(expr.slice)
            return f"{val}[{slice_name}]" if slice_name else val
        return ""

    def _calc_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.While,
                    ast.For,
                    ast.AsyncFor,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.Assert,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity


# ==============================================================================
# JavaScript / TypeScript Tree-sitter AST Visitor
# ==============================================================================


class _TreeSitterJSVisitor:
    """Parses JavaScript and TypeScript source files using Tree-sitter AST."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []
        self.is_ts = rel_path.endswith((".ts", ".tsx"))
        self.is_tsx = rel_path.endswith((".tsx", ".jsx"))
        self.lang = "typescript" if self.is_ts else "javascript"

        lang_key = "tsx" if self.is_tsx else ("typescript" if self.is_ts else "javascript")
        self.ts_lang = _get_ts_language(lang_key)
        if not self.ts_lang:
            raise RuntimeError(f"Tree-sitter grammar unavailable for {lang_key}")
        self.parser = tree_sitter.Parser(self.ts_lang)

    def _node_text(self, node) -> str:
        if not node:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _clean_str(self, text: str) -> str:
        return text.strip().strip("'\"`")

    def _calc_complexity(self, node) -> int:
        comp = 1
        branch_types = {
            "if_statement", "for_statement", "for_in_statement", "while_statement",
            "do_statement", "switch_case", "catch_clause", "ternary_expression"
        }
        for child in node.children:
            if child.type in branch_types:
                comp += 1
            elif child.type == "binary_expression":
                op = child.child_by_field_name("operator")
                if op and self._node_text(op) in ("&&", "||", "??"):
                    comp += 1
            comp += self._calc_complexity(child) - 1
        return comp

    def _extract_params(self, param_node) -> list:
        if not param_node:
            return []
        params = []
        for child in param_node.children:
            if child.type in ("identifier", "required_parameter", "optional_parameter"):
                p_name = child.child_by_field_name("name")
                if p_name:
                    params.append(self._node_text(p_name))
                else:
                    t = self._node_text(child).split(":")[0].strip()
                    if t and t not in (",", "(", ")"):
                        params.append(t)
            elif child.type == "assignment_pattern":
                left = child.child_by_field_name("left")
                if left:
                    params.append(self._node_text(left))
        return params

    def _get_call_name(self, node) -> str:
        if not node:
            return ""
        if node.type == "identifier":
            return self._node_text(node)
        elif node.type == "member_expression":
            obj = self._get_call_name(node.child_by_field_name("object"))
            prop = self._get_call_name(node.child_by_field_name("property"))
            return f"{obj}.{prop}" if obj and prop else (obj or prop)
        return self._node_text(node).split("(")[0].strip()

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.source_bytes = self.source_code.encode("utf-8")
        tree = self.parser.parse(self.source_bytes)

        # Module symbol
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language=self.lang,
            )
        )

        scope_stack = [self.mod_name]
        call_filter = {
            "if", "for", "while", "catch", "switch", "function", "class", "return",
            "import", "require", "typeof", "delete", "new", "super", "console.log",
            "console.error", "console.warn", "console.info", "assert",
            "setstate", "usestate", "useeffect", "usecallback", "usememo", "useref",
            "map", "filter", "reduce", "foreach", "push", "slice", "splice", "join",
            "split", "replace", "indexof", "includes", "startswith", "endswith",
            "trim", "tolowercase", "touppercase", "then", "resolve", "reject",
        }

        def walk(node):
            ntype = node.type

            # Imports: import ... from '...'
            if ntype in ("import_statement", "import_declaration"):
                src_node = node.child_by_field_name("source")
                if src_node:
                    target = self._clean_str(self._node_text(src_node))
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=target,
                            edge_type=EdgeType.IMPORTS,
                            line_number=node.start_point[0] + 1,
                            metadata={"imported_path": target},
                        )
                    )

            # Export statement with source: export { foo } from 'bar'
            elif ntype == "export_statement":
                src_node = node.child_by_field_name("source")
                if src_node:
                    target = self._clean_str(self._node_text(src_node))
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=target,
                            edge_type=EdgeType.IMPORTS,
                            line_number=node.start_point[0] + 1,
                            metadata={"imported_path": target},
                        )
                    )

            # Class declaration
            elif ntype in ("class_declaration", "class"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    cls_name = self._node_text(name_node)
                    qual_cls = f"{self.mod_name}.{cls_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    self.symbols.append(
                        Symbol(
                            name=cls_name,
                            qualified_name=qual_cls,
                            symbol_type=SymbolType.CLASS,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            source_code=self._node_text(node).splitlines()[0],
                            language=self.lang,
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=qual_cls,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

                    # Inheritance
                    for child in node.children:
                        if child.type in ("class_heritage", "extends_clause"):
                            for sub in child.children:
                                if sub.type in ("identifier", "member_expression"):
                                    base_name = self._node_text(sub)
                                    if base_name and base_name != "extends":
                                        self.edges.append(
                                            DependencyEdge(
                                                source=qual_cls,
                                                target=base_name,
                                                edge_type=EdgeType.INHERITS,
                                                line_number=line_start,
                                            )
                                        )

                    scope_stack.append(qual_cls)
                    body = node.child_by_field_name("body")
                    if body:
                        for b_child in body.children:
                            walk(b_child)
                    scope_stack.pop()
                    return

            # Interface declaration
            elif ntype == "interface_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    intf_name = self._node_text(name_node)
                    qual_intf = f"{self.mod_name}.{intf_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    self.symbols.append(
                        Symbol(
                            name=intf_name,
                            qualified_name=qual_intf,
                            symbol_type=SymbolType.INTERFACE,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            source_code=self._node_text(node).splitlines()[0],
                            language=self.lang,
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=qual_intf,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

            # Method definition inside class
            elif ntype == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    fn_name = self._node_text(name_node)
                    if fn_name != "constructor":
                        parent_scope = scope_stack[-1]
                        qual_fn = f"{parent_scope}.{fn_name}"
                        line_start = node.start_point[0] + 1
                        line_end = node.end_point[0] + 1
                        params = self._extract_params(node.child_by_field_name("parameters"))
                        is_test = fn_name.startswith("test") or "test" in self.rel_path.lower()
                        complexity = self._calc_complexity(node)
                        self.symbols.append(
                            Symbol(
                                name=fn_name,
                                qualified_name=qual_fn,
                                symbol_type=SymbolType.TEST if is_test else SymbolType.METHOD,
                                file_path=self.rel_path,
                                line_start=line_start,
                                line_end=line_end,
                                parameters=params,
                                complexity=complexity,
                                source_code=self._node_text(node).splitlines()[0],
                                language=self.lang,
                            )
                        )
                        self.edges.append(
                            DependencyEdge(
                                source=parent_scope,
                                target=qual_fn,
                                edge_type=EdgeType.DEFINES,
                                line_number=line_start,
                            )
                        )

            # Function declaration
            elif ntype == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    fn_name = self._node_text(name_node)
                    parent_scope = scope_stack[-1]
                    qual_fn = f"{parent_scope}.{fn_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    params = self._extract_params(node.child_by_field_name("parameters"))
                    is_test = fn_name.startswith("test") or "test" in self.rel_path.lower()
                    complexity = self._calc_complexity(node)
                    self.symbols.append(
                        Symbol(
                            name=fn_name,
                            qualified_name=qual_fn,
                            symbol_type=SymbolType.TEST if is_test else SymbolType.FUNCTION,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            parameters=params,
                            complexity=complexity,
                            source_code=self._node_text(node).splitlines()[0],
                            language=self.lang,
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=parent_scope,
                            target=qual_fn,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

            # Variable declaration: const Foo = (...) => ... or const Foo = forwardRef(...)
            elif ntype in ("variable_declarator", "variable_declaration", "lexical_declaration"):
                if ntype == "variable_declarator":
                    name_node = node.child_by_field_name("name")
                    val_node = node.child_by_field_name("value")
                    if name_node and val_node:
                        vname = self._node_text(name_node)
                        if val_node.type in ("arrow_function", "function_expression"):
                            line_start = node.start_point[0] + 1
                            line_end = node.end_point[0] + 1
                            qual_fn = f"{self.mod_name}.{vname}"
                            params = self._extract_params(val_node.child_by_field_name("parameters"))
                            is_test = vname.startswith("test") or "test" in self.rel_path.lower()
                            complexity = self._calc_complexity(val_node)
                            self.symbols.append(
                                Symbol(
                                    name=vname,
                                    qualified_name=qual_fn,
                                    symbol_type=SymbolType.TEST if is_test else SymbolType.FUNCTION,
                                    file_path=self.rel_path,
                                    line_start=line_start,
                                    line_end=line_end,
                                    parameters=params,
                                    complexity=complexity,
                                    source_code=self._node_text(node).splitlines()[0],
                                    language=self.lang,
                                )
                            )
                            self.edges.append(
                                DependencyEdge(
                                    source=self.mod_name,
                                    target=qual_fn,
                                    edge_type=EdgeType.DEFINES,
                                    line_number=line_start,
                                )
                            )
                        elif val_node.type == "call_expression":
                            fn_call = self._get_call_name(val_node.child_by_field_name("function"))
                            if fn_call in ("require", "import"):
                                args = val_node.child_by_field_name("arguments")
                                if args and len(args.children) >= 2:
                                    target = self._clean_str(self._node_text(args.children[1]))
                                    self.edges.append(
                                        DependencyEdge(
                                            source=self.mod_name,
                                            target=target,
                                            edge_type=EdgeType.IMPORTS,
                                            line_number=val_node.start_point[0] + 1,
                                            metadata={"imported_path": target},
                                        )
                                    )
                            elif any(k in fn_call for k in ("forwardRef", "memo")):
                                qual_fn = f"{self.mod_name}.{vname}"
                                line_start = node.start_point[0] + 1
                                line_end = node.end_point[0] + 1
                                self.symbols.append(
                                    Symbol(
                                        name=vname,
                                        qualified_name=qual_fn,
                                        symbol_type=SymbolType.FUNCTION,
                                        file_path=self.rel_path,
                                        line_start=line_start,
                                        line_end=line_end,
                                        source_code=self._node_text(node).splitlines()[0],
                                        language=self.lang,
                                    )
                                )
                                self.edges.append(
                                    DependencyEdge(
                                        source=self.mod_name,
                                        target=qual_fn,
                                        edge_type=EdgeType.DEFINES,
                                        line_number=line_start,
                                    )
                                )

            # Calls
            elif ntype == "call_expression":
                fn_node = node.child_by_field_name("function")
                call_name = self._get_call_name(fn_node)
                if call_name:
                    if call_name in ("require", "import"):
                        args = node.child_by_field_name("arguments")
                        if args and len(args.children) >= 2:
                            target = self._clean_str(self._node_text(args.children[1]))
                            if target:
                                self.edges.append(
                                    DependencyEdge(
                                        source=self.mod_name,
                                        target=target,
                                        edge_type=EdgeType.IMPORTS,
                                        line_number=node.start_point[0] + 1,
                                        metadata={"imported_path": target},
                                    )
                                )
                    elif call_name.lower() not in call_filter and not call_name.startswith("this."):
                        edge_type = EdgeType.INSTANTIATES if (call_name[0].isupper() or "." in call_name and call_name.split(".")[-1][0].isupper()) else EdgeType.CALLS
                        self.edges.append(
                            DependencyEdge(
                                source=self.mod_name,
                                target=call_name,
                                edge_type=edge_type,
                                line_number=node.start_point[0] + 1,
                            )
                        )

            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return self.symbols, self.edges


# ==============================================================================
# JavaScript / TypeScript Fallback Parser
# ==============================================================================


class _JSVisitor:
    """Parses JavaScript and TypeScript source files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []
        self.lang = "typescript" if rel_path.endswith((".ts", ".tsx")) else "javascript"

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        # Root module symbol
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language=self.lang,
            )
        )

        # 1. Imports: ES6 imports, require(), dynamic import()
        # Single-line and multiline import matching
        import_pat = re.compile(
            r"""import\s+(?:type\s+)?(?:(?:\*|\{[^}]*\}|[A-Za-z0-9_$,\s]+)\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\)"""
        )
        for m in import_pat.finditer(self.source_code):
            target_pkg = m.group(1) or m.group(2) or m.group(3)
            if target_pkg:
                line_num = self.source_code[: m.start()].count("\n") + 1
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=target_pkg.strip(),
                        edge_type=EdgeType.IMPORTS,
                        line_number=line_num,
                        metadata={"imported_path": target_pkg.strip()},
                    )
                )

        masked_code = _mask_text(self.source_code, mask_comments=True, mask_strings=False, style="c")
        masked_lines = masked_code.splitlines()

        # 2. Classes & Interfaces
        class_pat = re.compile(
            r"""(?:export\s+)?(?:default\s+)?(class|interface)\s+([A-Za-z0-9_]+)(?:\s+extends\s+([A-Za-z0-9_.]+))?"""
        )
        for line_num, line in enumerate(masked_lines, start=1):
            m = class_pat.search(line)
            if m:
                kind, cls_name, base_cls = m.group(1), m.group(2), m.group(3)
                qual_cls = f"{self.mod_name}.{cls_name}"
                sym_type = SymbolType.INTERFACE if kind == "interface" else SymbolType.CLASS
                raw_line = self.lines[line_num - 1] if line_num - 1 < len(self.lines) else line
                self.symbols.append(
                    Symbol(
                        name=cls_name,
                        qualified_name=qual_cls,
                        symbol_type=sym_type,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 30, max(len(self.lines), line_num)),
                        source_code=raw_line.strip(),
                        language=self.lang,
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual_cls,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )
                if base_cls:
                    self.edges.append(
                        DependencyEdge(
                            source=qual_cls,
                            target=base_cls,
                            edge_type=EdgeType.INHERITS,
                            line_number=line_num,
                        )
                    )

        # 3. Functions, Components, & Methods (supports multiline parameters, arrow functions, React generics, and class methods)
        fn_pats = [
            (re.compile(r"""(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*(?:\*\s*)?([A-Za-z0-9_]+)\s*\(([^)]*)\)""", re.MULTILINE), False),
            (re.compile(r"""(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?(?:\(([^)]*)\)|([A-Za-z0-9_]+))\s*(?::\s*[^=>{\n]+)?\s*=>""", re.MULTILINE), False),
            (re.compile(r"""(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:React\.)?(?:forwardRef|memo)(?:<[^>]+>)?\s*\(""", re.MULTILINE), False),
            (re.compile(r"""^\s*(?:async\s+)?(?:static\s+)?([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*(?::\s*[^=>{\n]+)?\s*\{""", re.MULTILINE), True),
        ]
        keywords = {"if", "for", "while", "catch", "switch", "function", "class", "return", "import", "constructor", "export", "default", "type"}

        for pat, is_method in fn_pats:
            for m in pat.finditer(masked_code):
                fn_name = m.group(1)
                if not fn_name or fn_name in keywords:
                    continue
                line_num = masked_code[: m.start()].count("\n") + 1
                if any(s.name == fn_name and s.line_start == line_num for s in self.symbols):
                    continue

                params_raw = (m.group(2) if len(m.groups()) >= 2 and m.group(2) else (m.group(3) if len(m.groups()) >= 3 and m.group(3) else "")) or ""
                params = [p.strip().split(":")[0].strip() for p in params_raw.split(",") if p.strip()]
                qual_fn = f"{self.mod_name}.{fn_name}"
                is_test = fn_name.startswith("test") or "test" in self.rel_path.lower()
                raw_line = self.lines[line_num - 1] if line_num - 1 < len(self.lines) else ""
                self.symbols.append(
                    Symbol(
                        name=fn_name,
                        qualified_name=qual_fn,
                        symbol_type=SymbolType.TEST if is_test else (SymbolType.METHOD if is_method else SymbolType.FUNCTION),
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        parameters=params,
                        source_code=raw_line.strip(),
                        language=self.lang,
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual_fn,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

        # 4. Calls (performed on masked code without comments and string literals)
        code_no_strings = _mask_text(self.source_code, mask_comments=True, mask_strings=True, style="c")
        call_pat = re.compile(r"""\b([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\s*\(""")
        call_filter = {
            "if", "for", "while", "catch", "switch", "function", "class", "return",
            "import", "require", "typeof", "delete", "new", "super", "console.log",
            "console.error", "console.warn", "console.info", "assert", "fetch",
            "setstate", "usestate", "useeffect", "usecallback", "usememo", "useref",
            "map", "filter", "reduce", "foreach", "push", "slice", "splice", "join",
            "split", "replace", "indexof", "includes", "startswith", "endswith",
            "trim", "tolowercase", "touppercase", "then", "catch", "resolve", "reject",
        }
        for line_num, line in enumerate(code_no_strings.splitlines(), start=1):
            for m in call_pat.finditer(line):
                call_name = m.group(1)
                if call_name.lower() in call_filter or call_name in keywords:
                    continue
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=call_name,
                        edge_type=EdgeType.CALLS,
                        line_number=line_num,
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# C / C++ / Arduino Tree-sitter AST Visitor
# ==============================================================================


class _TreeSitterCppVisitor:
    """Parses C, C++, and Arduino source files using Tree-sitter AST."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []
        is_ino = rel_path.endswith(".ino")
        self.lang = "arduino" if is_ino else ("c" if rel_path.endswith(".c") else "cpp")
        self.ts_lang = _get_ts_language("cpp")
        if not self.ts_lang:
            raise RuntimeError("Tree-sitter grammar unavailable for C/C++")
        self.parser = tree_sitter.Parser(self.ts_lang)

    def _node_text(self, node) -> str:
        if not node:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _clean_str(self, text: str) -> str:
        return text.strip().strip("<>\"'")

    def _get_declarator_name(self, node) -> tuple:
        """Returns (name, class_scope, param_list)"""
        if not node:
            return "", None, []
        ntype = node.type
        if ntype == "function_declarator":
            d = node.child_by_field_name("declarator")
            params_node = node.child_by_field_name("parameters")
            params = self._extract_params(params_node)
            name, cls = self._unwrap_name(d)
            return name, cls, params
        elif ntype == "pointer_declarator":
            d = node.child_by_field_name("declarator")
            return self._get_declarator_name(d)
        else:
            name, cls = self._unwrap_name(node)
            return name, cls, []

    def _unwrap_name(self, node) -> tuple:
        if not node:
            return "", None
        ntype = node.type
        if ntype in ("identifier", "field_identifier", "type_identifier"):
            return self._node_text(node), None
        elif ntype == "qualified_identifier":
            scope_node = node.child_by_field_name("scope")
            name_node = node.child_by_field_name("name")
            cls = self._node_text(scope_node) if scope_node else None
            name = self._node_text(name_node) if name_node else ""
            return name, cls
        for child in node.children:
            if child.type in ("identifier", "field_identifier", "type_identifier", "qualified_identifier"):
                return self._unwrap_name(child)
        return self._node_text(node).split("(")[0].strip(), None

    def _extract_params(self, params_node) -> list:
        if not params_node:
            return []
        params = []
        for child in params_node.children:
            if child.type == "parameter_declaration":
                d = child.child_by_field_name("declarator")
                if d:
                    name, _ = self._unwrap_name(d)
                    if name:
                        params.append(name.replace("*", "").replace("&", ""))
                else:
                    t = child.child_by_field_name("type")
                    if t:
                        params.append(self._node_text(t))
        return params

    def _calc_complexity(self, node) -> int:
        comp = 1
        branch_types = {
            "if_statement", "for_statement", "for_range_loop", "while_statement",
            "do_statement", "case_statement", "catch_clause", "conditional_expression"
        }
        for child in node.children:
            if child.type in branch_types:
                comp += 1
            elif child.type == "binary_expression":
                op = child.child_by_field_name("operator")
                if op and self._node_text(op) in ("&&", "||"):
                    comp += 1
            comp += self._calc_complexity(child) - 1
        return comp

    def _get_call_name(self, node) -> str:
        if not node:
            return ""
        if node.type in ("identifier", "field_identifier"):
            return self._node_text(node)
        elif node.type == "field_expression":
            arg = self._get_call_name(node.child_by_field_name("argument"))
            field = self._get_call_name(node.child_by_field_name("field"))
            return f"{arg}.{field}" if arg and field else (arg or field)
        elif node.type == "qualified_identifier":
            scope = self._get_call_name(node.child_by_field_name("scope"))
            name = self._get_call_name(node.child_by_field_name("name"))
            return f"{scope}::{name}" if scope and name else (scope or name)
        return self._node_text(node).split("(")[0].strip()

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.source_bytes = self.source_code.encode("utf-8")
        tree = self.parser.parse(self.source_bytes)

        # Module symbol
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language=self.lang,
            )
        )

        scope_stack = [self.mod_name]
        keywords = {"if", "while", "for", "switch", "catch", "return", "sizeof"}

        def walk(node):
            ntype = node.type

            # Includes: #include <WiFi.h> or #include "sensor.h"
            if ntype == "preproc_include":
                path_node = node.child_by_field_name("path")
                if path_node:
                    header = self._clean_str(self._node_text(path_node))
                    raw_text = self._node_text(node)
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=header,
                            edge_type=EdgeType.INCLUDES,
                            line_number=node.start_point[0] + 1,
                            metadata={"header": header, "is_local": '"' in raw_text},
                        )
                    )

            # Struct specifier
            elif ntype == "struct_specifier":
                name_node = node.child_by_field_name("name")
                body_node = node.child_by_field_name("body")
                if name_node and body_node:
                    name = self._node_text(name_node)
                    qual_name = f"{self.mod_name}.{name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    self.symbols.append(
                        Symbol(
                            name=name,
                            qualified_name=qual_name,
                            symbol_type=SymbolType.STRUCT,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            source_code=self._node_text(node).splitlines()[0],
                            language=self.lang,
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=qual_name,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

            # Class specifier
            elif ntype == "class_specifier":
                name_node = node.child_by_field_name("name")
                body_node = node.child_by_field_name("body")
                if name_node and body_node:
                    cls_name = self._node_text(name_node)
                    qual_cls = f"{self.mod_name}.{cls_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    self.symbols.append(
                        Symbol(
                            name=cls_name,
                            qualified_name=qual_cls,
                            symbol_type=SymbolType.CLASS,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            source_code=self._node_text(node).splitlines()[0],
                            language=self.lang,
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=qual_cls,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

                    # Inheritance (base class clause)
                    for child in node.children:
                        if child.type == "base_class_clause":
                            for sub in child.children:
                                if sub.type in ("type_identifier", "identifier"):
                                    base_name = self._node_text(sub)
                                    self.edges.append(
                                        DependencyEdge(
                                            source=qual_cls,
                                            target=base_name,
                                            edge_type=EdgeType.INHERITS,
                                            line_number=line_start,
                                        )
                                    )

                    scope_stack.append(qual_cls)
                    for b_child in body_node.children:
                        walk(b_child)
                    scope_stack.pop()
                    return

            # Function definition (top level or method)
            elif ntype == "function_definition":
                declarator = node.child_by_field_name("declarator")
                fn_name, cls_scope, params = self._get_declarator_name(declarator)
                if fn_name and fn_name not in keywords:
                    parent_scope = f"{self.mod_name}.{cls_scope}" if cls_scope else scope_stack[-1]
                    qual_fn = f"{parent_scope}.{fn_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    is_test = fn_name.startswith("test") or "test" in self.rel_path.lower()
                    is_method = cls_scope is not None or len(scope_stack) > 1
                    sym_type = SymbolType.TEST if is_test else (SymbolType.METHOD if is_method else SymbolType.FUNCTION)
                    complexity = self._calc_complexity(node)
                    self.symbols.append(
                        Symbol(
                            name=fn_name,
                            qualified_name=qual_fn,
                            symbol_type=sym_type,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            parameters=params,
                            complexity=complexity,
                            source_code=self._node_text(node).splitlines()[0],
                            language=self.lang,
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=parent_scope,
                            target=qual_fn,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

                    scope_stack.append(qual_fn)
                    body = node.child_by_field_name("body")
                    if body:
                        for b_child in body.children:
                            walk(b_child)
                    scope_stack.pop()
                    return

            # Calls
            elif ntype == "call_expression":
                fn_node = node.child_by_field_name("function")
                call_name = self._get_call_name(fn_node)
                if call_name and call_name not in keywords:
                    self.edges.append(
                        DependencyEdge(
                            source=scope_stack[-1] if len(scope_stack) > 1 else self.mod_name,
                            target=call_name,
                            edge_type=EdgeType.CALLS,
                            line_number=node.start_point[0] + 1,
                        )
                    )

            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return self.symbols, self.edges


# ==============================================================================
# C / C++ / Arduino Fallback Parser
# ==============================================================================


class _CppArduinoVisitor:
    """Parses C, C++, and Arduino (.ino, .cpp, .h) source files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []
        is_ino = rel_path.endswith(".ino")
        self.lang = "arduino" if is_ino else ("c" if rel_path.endswith(".c") else "cpp")

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        # Root module symbol
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language=self.lang,
            )
        )

        # 1. Includes (#include "..." or #include <...>)
        inc_pat = re.compile(r"""#include\s*["<](.*?)[">]""")
        for line_num, line in enumerate(self.lines, start=1):
            m = inc_pat.search(line)
            if m:
                target_header = m.group(1)
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=target_header,
                        edge_type=EdgeType.INCLUDES,
                        line_number=line_num,
                        metadata={"header": target_header, "is_local": '"' in line},
                    )
                )

        masked_code = _mask_text(self.source_code, mask_comments=True, mask_strings=True, style="c")
        masked_lines = masked_code.splitlines()

        # 2. Classes and Structs (requires opening body brace {)
        cls_pat = re.compile(
            r"""\b(class|struct)\s+([A-Za-z0-9_]+)(?:\s*:\s*(?:public|protected|private)?\s*([A-Za-z0-9_]+))?\s*\{""",
            re.MULTILINE,
        )
        for m in cls_pat.finditer(masked_code):
            kind, name, base = m.group(1), m.group(2), m.group(3)
            line_num = masked_code[: m.start()].count("\n") + 1
            qual_name = f"{self.mod_name}.{name}"
            sym_type = SymbolType.STRUCT if kind == "struct" else SymbolType.CLASS
            raw_line = self.lines[line_num - 1] if line_num - 1 < len(self.lines) else ""
            self.symbols.append(
                Symbol(
                    name=name,
                    qualified_name=qual_name,
                    symbol_type=sym_type,
                    file_path=self.rel_path,
                    line_start=line_num,
                    line_end=min(line_num + 30, max(len(self.lines), line_num)),
                    source_code=raw_line.strip(),
                    language=self.lang,
                )
            )
            self.edges.append(
                DependencyEdge(
                    source=self.mod_name,
                    target=qual_name,
                    edge_type=EdgeType.DEFINES,
                    line_number=line_num,
                )
            )
            if base:
                self.edges.append(
                    DependencyEdge(
                        source=qual_name,
                        target=base,
                        edge_type=EdgeType.INHERITS,
                        line_number=line_num,
                    )
                )

        # 3. Functions & Methods (supports multiline signatures and Allman-style { on subsequent lines)
        fn_pat = re.compile(
            r"""\b(?:void|int|float|double|bool|char|long|unsigned|auto|uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|size_t|String|[A-Za-z0-9_]+[\*&]?)\s+(?:([A-Za-z0-9_]+)::)?([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*(?:const)?\s*\{""",
            re.MULTILINE,
        )
        keywords = {"if", "while", "for", "switch", "catch", "return", "sizeof"}
        for m in fn_pat.finditer(masked_code):
            cls_scope, fn_name, params_raw = m.group(1), m.group(2), m.group(3)
            if not fn_name or fn_name in keywords:
                continue
            line_num = masked_code[: m.start()].count("\n") + 1
            if any(s.name == fn_name and s.line_start == line_num for s in self.symbols):
                continue

            parent = f"{self.mod_name}.{cls_scope}" if cls_scope else self.mod_name
            qual_fn = f"{parent}.{fn_name}"
            params = [p.strip().split()[-1].replace("*", "").replace("&", "") for p in params_raw.split(",") if p.strip()]
            is_test = fn_name.startswith("test") or "test" in self.rel_path.lower()
            sym_type = SymbolType.TEST if is_test else (SymbolType.METHOD if cls_scope else SymbolType.FUNCTION)
            raw_line = self.lines[line_num - 1] if line_num - 1 < len(self.lines) else ""
            self.symbols.append(
                Symbol(
                    name=fn_name,
                    qualified_name=qual_fn,
                    symbol_type=sym_type,
                    file_path=self.rel_path,
                    line_start=line_num,
                    line_end=min(line_num + 25, max(len(self.lines), line_num)),
                    parameters=params,
                    source_code=raw_line.strip(),
                    language=self.lang,
                )
            )
            self.edges.append(
                DependencyEdge(
                    source=parent,
                    target=qual_fn,
                    edge_type=EdgeType.DEFINES,
                    line_number=line_num,
                )
            )

        # 4. Calls (including Serial.print, WiFi.begin, etc.)
        call_pat = re.compile(r"""\b([A-Za-z0-9_]+(?:\.|->|::)[A-Za-z0-9_]+|[A-Za-z0-9_]+)\s*\(""")
        for line_num, line in enumerate(masked_lines, start=1):
            for m in call_pat.finditer(line):
                call_name = m.group(1)
                if call_name.lower() in keywords or call_name in keywords:
                    continue
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=call_name,
                        edge_type=EdgeType.CALLS,
                        line_number=line_num,
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# Java / JVM Parser
# ==============================================================================


class _JavaVisitor:
    """Parses Java and Kotlin source files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []
        self.lang = "kotlin" if rel_path.endswith(".kt") else "java"

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        # Root module
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language=self.lang,
            )
        )

        # Imports
        imp_pat = re.compile(r"""import\s+(?:static\s+)?([A-Za-z0-9_.*]+);""")
        for line_num, line in enumerate(self.lines, start=1):
            m = imp_pat.search(line)
            if m:
                target_pkg = m.group(1).rstrip(".*")
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=target_pkg,
                        edge_type=EdgeType.IMPORTS,
                        line_number=line_num,
                    )
                )

        masked_code = _mask_text(self.source_code, mask_comments=True, mask_strings=False, style="c")
        masked_lines = masked_code.splitlines()

        # Classes & Interfaces
        cls_pat = re.compile(
            r"""(?:public|protected|private)?\s*(?:abstract|final|static)?\s*(class|interface|enum)\s+([A-Za-z0-9_]+)(?:\s+extends\s+([A-Za-z0-9_.]+))?"""
        )
        for line_num, line in enumerate(masked_lines, start=1):
            m = cls_pat.search(line)
            if m:
                kind, name, base = m.group(1), m.group(2), m.group(3)
                qual_name = f"{self.mod_name}.{name}"
                sym_type = SymbolType.INTERFACE if kind == "interface" else (SymbolType.ENUM if kind == "enum" else SymbolType.CLASS)
                self.symbols.append(
                    Symbol(
                        name=name,
                        qualified_name=qual_name,
                        symbol_type=sym_type,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 30, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language=self.lang,
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual_name,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )
                if base:
                    self.edges.append(
                        DependencyEdge(
                            source=qual_name,
                            target=base,
                            edge_type=EdgeType.INHERITS,
                            line_number=line_num,
                        )
                    )

        # Methods (supports multiline parameter signatures)
        method_pat = re.compile(
            r"""(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:[A-Za-z0-9_<>[\]]+)\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*(?:throws\s+[A-Za-z0-9_,\s]+)?\s*\{""",
            re.MULTILINE,
        )
        keywords = {"if", "while", "for", "switch", "catch", "return"}
        for m in method_pat.finditer(masked_code):
            name, params_raw = m.group(1), m.group(2)
            if not name or name in keywords:
                continue
            line_num = masked_code[: m.start()].count("\n") + 1
            if any(s.name == name and s.line_start == line_num for s in self.symbols):
                continue
            qual_name = f"{self.mod_name}.{name}"
            params = [p.strip().split()[-1] for p in params_raw.split(",") if p.strip()]
            is_test = name.startswith("test") or "test" in self.rel_path.lower()
            raw_line = self.lines[line_num - 1] if line_num - 1 < len(self.lines) else ""
            self.symbols.append(
                Symbol(
                    name=name,
                    qualified_name=qual_name,
                    symbol_type=SymbolType.TEST if is_test else SymbolType.METHOD,
                    file_path=self.rel_path,
                    line_start=line_num,
                    line_end=min(line_num + 20, max(len(self.lines), line_num)),
                    parameters=params,
                    source_code=raw_line.strip(),
                    language=self.lang,
                )
            )
            self.edges.append(
                DependencyEdge(
                    source=self.mod_name,
                    target=qual_name,
                    edge_type=EdgeType.DEFINES,
                    line_number=line_num,
                )
            )

        return self.symbols, self.edges


# ==============================================================================
# Go Tree-sitter AST Visitor
# ==============================================================================


class _TreeSitterGoVisitor:
    """Parses Go source files using Tree-sitter AST."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []
        self.ts_lang = _get_ts_language("go")
        if not self.ts_lang:
            raise RuntimeError("Tree-sitter grammar unavailable for Go")
        self.parser = tree_sitter.Parser(self.ts_lang)

    def _node_text(self, node) -> str:
        if not node:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _clean_str(self, text: str) -> str:
        return text.strip().strip('"\'`')

    def _extract_params(self, params_node) -> list:
        if not params_node:
            return []
        params = []
        for child in params_node.children:
            if child.type == "parameter_declaration":
                name = child.child_by_field_name("name")
                if name:
                    params.append(self._node_text(name))
                else:
                    t = child.child_by_field_name("type")
                    if t:
                        params.append(self._node_text(t))
        return params

    def _calc_complexity(self, node) -> int:
        comp = 1
        branch_types = {
            "if_statement", "for_statement", "expression_case_clause", "type_case_clause",
            "communication_case"
        }
        for child in node.children:
            if child.type in branch_types:
                comp += 1
            elif child.type == "binary_expression":
                op = child.child_by_field_name("operator")
                if op and self._node_text(op) in ("&&", "||"):
                    comp += 1
            comp += self._calc_complexity(child) - 1
        return comp

    def _get_call_name(self, node) -> str:
        if not node:
            return ""
        if node.type == "identifier":
            return self._node_text(node)
        elif node.type == "selector_expression":
            operand = self._get_call_name(node.child_by_field_name("operand"))
            field = self._get_call_name(node.child_by_field_name("field"))
            return f"{operand}.{field}" if operand and field else (operand or field)
        return self._node_text(node).split("(")[0].strip()

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.source_bytes = self.source_code.encode("utf-8")
        tree = self.parser.parse(self.source_bytes)

        # Module symbol
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language="go",
            )
        )

        scope_stack = [self.mod_name]
        keywords = {"if", "for", "switch", "select", "return", "go", "defer", "panic", "recover", "make", "new", "len", "cap", "append"}

        def walk(node):
            ntype = node.type

            # Imports
            if ntype == "import_declaration":
                for child in node.children:
                    specs = child.children if child.type == "import_spec_list" else [child]
                    for spec in specs:
                        if spec.type == "import_spec":
                            p = spec.child_by_field_name("path")
                            if p:
                                pkg = self._clean_str(self._node_text(p))
                                self.edges.append(
                                    DependencyEdge(
                                        source=self.mod_name,
                                        target=pkg,
                                        edge_type=EdgeType.IMPORTS,
                                        line_number=spec.start_point[0] + 1,
                                    )
                                )

            # Type declarations (struct / interface)
            elif ntype == "type_declaration":
                for child in node.children:
                    if child.type == "type_spec":
                        name_node = child.child_by_field_name("name")
                        type_node = child.child_by_field_name("type")
                        if name_node and type_node:
                            name = self._node_text(name_node)
                            kind = type_node.type
                            qual_name = f"{self.mod_name}.{name}"
                            sym_type = SymbolType.INTERFACE if kind == "interface_type" else (
                                SymbolType.STRUCT if kind == "struct_type" else SymbolType.CLASS
                            )
                            line_start = child.start_point[0] + 1
                            line_end = child.end_point[0] + 1
                            self.symbols.append(
                                Symbol(
                                    name=name,
                                    qualified_name=qual_name,
                                    symbol_type=sym_type,
                                    file_path=self.rel_path,
                                    line_start=line_start,
                                    line_end=line_end,
                                    source_code=self._node_text(child).splitlines()[0],
                                    language="go",
                                )
                            )
                            self.edges.append(
                                DependencyEdge(
                                    source=self.mod_name,
                                    target=qual_name,
                                    edge_type=EdgeType.DEFINES,
                                    line_number=line_start,
                                )
                            )

            # Function declaration
            elif ntype == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    fn_name = self._node_text(name_node)
                    parent_scope = scope_stack[-1]
                    qual_fn = f"{parent_scope}.{fn_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    params = self._extract_params(node.child_by_field_name("parameters"))
                    is_test = fn_name.startswith("Test") or "test" in self.rel_path.lower()
                    complexity = self._calc_complexity(node)
                    self.symbols.append(
                        Symbol(
                            name=fn_name,
                            qualified_name=qual_fn,
                            symbol_type=SymbolType.TEST if is_test else SymbolType.FUNCTION,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            parameters=params,
                            complexity=complexity,
                            source_code=self._node_text(node).splitlines()[0],
                            language="go",
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=parent_scope,
                            target=qual_fn,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

                    scope_stack.append(qual_fn)
                    body = node.child_by_field_name("body")
                    if body:
                        for b_child in body.children:
                            walk(b_child)
                    scope_stack.pop()
                    return

            # Method declaration (func (r *Receiver) Method())
            elif ntype == "method_declaration":
                name_node = node.child_by_field_name("name")
                recv_node = node.child_by_field_name("receiver")
                if name_node:
                    fn_name = self._node_text(name_node)
                    recv_text = self._node_text(recv_node) if recv_node else ""
                    # Extract receiver type name: e.g. "(c *Config)" -> "Config"
                    recv_type = recv_text.replace("(", "").replace(")", "").replace("*", "").strip().split()[-1] if recv_text else ""
                    parent_scope = f"{self.mod_name}.{recv_type}" if recv_type else self.mod_name
                    qual_fn = f"{parent_scope}.{fn_name}"
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    params = self._extract_params(node.child_by_field_name("parameters"))
                    is_test = fn_name.startswith("Test") or "test" in self.rel_path.lower()
                    complexity = self._calc_complexity(node)
                    self.symbols.append(
                        Symbol(
                            name=fn_name,
                            qualified_name=qual_fn,
                            symbol_type=SymbolType.TEST if is_test else SymbolType.METHOD,
                            file_path=self.rel_path,
                            line_start=line_start,
                            line_end=line_end,
                            parameters=params,
                            complexity=complexity,
                            source_code=self._node_text(node).splitlines()[0],
                            language="go",
                        )
                    )
                    self.edges.append(
                        DependencyEdge(
                            source=parent_scope,
                            target=qual_fn,
                            edge_type=EdgeType.DEFINES,
                            line_number=line_start,
                        )
                    )

                    scope_stack.append(qual_fn)
                    body = node.child_by_field_name("body")
                    if body:
                        for b_child in body.children:
                            walk(b_child)
                    scope_stack.pop()
                    return

            # Calls
            elif ntype == "call_expression":
                fn_node = node.child_by_field_name("function")
                call_name = self._get_call_name(fn_node)
                if call_name and call_name not in keywords:
                    self.edges.append(
                        DependencyEdge(
                            source=scope_stack[-1] if len(scope_stack) > 1 else self.mod_name,
                            target=call_name,
                            edge_type=EdgeType.CALLS,
                            line_number=node.start_point[0] + 1,
                        )
                    )

            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return self.symbols, self.edges


# ==============================================================================
# Go Fallback Parser
# ==============================================================================


class _GoVisitor:
    """Parses Go source files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language="go",
            )
        )

        # Imports
        imp_pat = re.compile(r"""(?:import\s+"(.*?)"|import\s*\((.*?)\))""", re.DOTALL)
        for m in imp_pat.finditer(self.source_code):
            raw = m.group(1) or m.group(2) or ""
            for line in raw.splitlines():
                clean_pkg = line.strip().strip('"')
                if clean_pkg:
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=clean_pkg,
                            edge_type=EdgeType.IMPORTS,
                        )
                    )

        # Structs / Interfaces
        type_pat = re.compile(r"""type\s+([A-Za-z0-9_]+)\s+(struct|interface)""")
        for line_num, line in enumerate(self.lines, start=1):
            m = type_pat.search(line)
            if m:
                name, kind = m.group(1), m.group(2)
                qual_name = f"{self.mod_name}.{name}"
                sym_type = SymbolType.INTERFACE if kind == "interface" else SymbolType.STRUCT
                self.symbols.append(
                    Symbol(
                        name=name,
                        qualified_name=qual_name,
                        symbol_type=sym_type,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language="go",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual_name,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

        # Functions & Methods
        fn_pat = re.compile(
            r"""func\s+(?:\((?:[A-Za-z0-9_]+\s+\*?([A-Za-z0-9_]+))\)\s*)?([A-Za-z0-9_]+)\s*\((.*?)\)"""
        )
        for line_num, line in enumerate(self.lines, start=1):
            m = fn_pat.search(line)
            if m:
                receiver, fn_name, params_raw = m.group(1), m.group(2), m.group(3)
                qual_name = f"{self.mod_name}.{receiver}.{fn_name}" if receiver else f"{self.mod_name}.{fn_name}"
                params = [p.strip().split()[0] for p in params_raw.split(",") if p.strip()]
                is_test = fn_name.startswith("Test") or "test" in self.rel_path.lower()
                self.symbols.append(
                    Symbol(
                        name=fn_name,
                        qualified_name=qual_name,
                        symbol_type=SymbolType.TEST if is_test else (SymbolType.METHOD if receiver else SymbolType.FUNCTION),
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        parameters=params,
                        source_code=line.strip(),
                        language="go",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual_name,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# Rust Parser
# ==============================================================================


class _RustVisitor:
    """Parses Rust source files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language="rust",
            )
        )

        use_pat = re.compile(r"""use\s+([A-Za-z0-9_:]+);""")
        for line_num, line in enumerate(self.lines, start=1):
            m = use_pat.search(line)
            if m:
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=m.group(1),
                        edge_type=EdgeType.IMPORTS,
                        line_number=line_num,
                    )
                )

        struct_pat = re.compile(r"""(?:pub\s+)?(struct|enum|trait)\s+([A-Za-z0-9_]+)""")
        for line_num, line in enumerate(self.lines, start=1):
            m = struct_pat.search(line)
            if m:
                kind, name = m.group(1), m.group(2)
                qual = f"{self.mod_name}.{name}"
                sym_type = SymbolType.INTERFACE if kind == "trait" else SymbolType.STRUCT
                self.symbols.append(
                    Symbol(
                        name=name,
                        qualified_name=qual,
                        symbol_type=sym_type,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language="rust",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

        fn_pat = re.compile(r"""(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*\((.*?)\)""")
        for line_num, line in enumerate(self.lines, start=1):
            m = fn_pat.search(line)
            if m:
                name, params_raw = m.group(1), m.group(2)
                qual = f"{self.mod_name}.{name}"
                is_test = name.startswith("test") or "test" in self.rel_path.lower()
                self.symbols.append(
                    Symbol(
                        name=name,
                        qualified_name=qual,
                        symbol_type=SymbolType.TEST if is_test else SymbolType.FUNCTION,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        parameters=[p.strip().split(":")[0].strip() for p in params_raw.split(",") if p.strip()],
                        source_code=line.strip(),
                        language="rust",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# SQL Parser
# ==============================================================================


class _SqlVisitor:
    """Parses SQL DDL & DML schema and procedure files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language="sql",
            )
        )

        table_pat = re.compile(
            r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:[`"\[]?([A-Za-z0-9_]+)[`"\]]?)""",
            re.IGNORECASE,
        )
        view_pat = re.compile(
            r"""CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:[`"\[]?([A-Za-z0-9_]+)[`"\]]?)""",
            re.IGNORECASE,
        )
        proc_pat = re.compile(
            r"""CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+([A-Za-z0-9_]+)""",
            re.IGNORECASE,
        )
        ref_pat = re.compile(r"""REFERENCES\s+(?:[`"\[]?([A-Za-z0-9_]+)[`"\]]?)""", re.IGNORECASE)

        masked_code = _mask_text(self.source_code, mask_comments=True, mask_strings=False, style="sql")
        masked_lines = masked_code.splitlines()

        for line_num, line in enumerate(masked_lines, start=1):
            # Table definition
            m = table_pat.search(line)
            if m:
                tbl_name = m.group(1)
                qual = f"{self.mod_name}.{tbl_name}"
                self.symbols.append(
                    Symbol(
                        name=tbl_name,
                        qualified_name=qual,
                        symbol_type=SymbolType.SCHEMA,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 30, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language="sql",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

            # View definition
            m_v = view_pat.search(line)
            if m_v:
                view_name = m_v.group(1)
                qual = f"{self.mod_name}.{view_name}"
                self.symbols.append(
                    Symbol(
                        name=view_name,
                        qualified_name=qual,
                        symbol_type=SymbolType.SCHEMA,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language="sql",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

            # Procedure / Function definition
            m_p = proc_pat.search(line)
            if m_p:
                proc_name = m_p.group(1)
                qual = f"{self.mod_name}.{proc_name}"
                self.symbols.append(
                    Symbol(
                        name=proc_name,
                        qualified_name=qual,
                        symbol_type=SymbolType.FUNCTION,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language="sql",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

            # Foreign key references
            for m_r in ref_pat.finditer(line):
                target_tbl = m_r.group(1)
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=target_tbl,
                        edge_type=EdgeType.REFERENCES,
                        line_number=line_num,
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# Shell / Bash Parser
# ==============================================================================


class _ShellVisitor:
    """Parses Shell and Bash script files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language="shell",
            )
        )

        source_pat = re.compile(r"""(?:source|\.)\s+([^\s;]+)""")
        fn_pat = re.compile(r"""(?:function\s+([A-Za-z0-9_]+)|([A-Za-z0-9_]+)\s*\(\)\s*\{)""")

        masked_code = _mask_text(self.source_code, mask_comments=True, mask_strings=False, style="hash")
        masked_lines = masked_code.splitlines()

        for line_num, line in enumerate(masked_lines, start=1):
            m_s = source_pat.search(line)
            if m_s:
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=m_s.group(1),
                        edge_type=EdgeType.IMPORTS,
                        line_number=line_num,
                    )
                )

            m_f = fn_pat.search(line)
            if m_f:
                name = m_f.group(1) or m_f.group(2)
                qual = f"{self.mod_name}.{name}"
                self.symbols.append(
                    Symbol(
                        name=name,
                        qualified_name=qual,
                        symbol_type=SymbolType.FUNCTION,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=min(line_num + 20, max(len(self.lines), line_num)),
                        source_code=line.strip(),
                        language="shell",
                    )
                )
                self.edges.append(
                    DependencyEdge(
                        source=self.mod_name,
                        target=qual,
                        edge_type=EdgeType.DEFINES,
                        line_number=line_num,
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# Config / Dockerfile / Data Parser
# ==============================================================================


class _ConfigVisitor:
    """Parses JSON, YAML, Dockerfile, and configuration files."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()
        self.symbols: List[Symbol] = []
        self.edges: List[DependencyEdge] = []

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        self.symbols.append(
            Symbol(
                name=self.mod_name.split(".")[-1],
                qualified_name=self.mod_name,
                symbol_type=SymbolType.MODULE,
                file_path=self.rel_path,
                line_start=1,
                line_end=max(len(self.lines), 1),
                source_code=self.source_code,
                language="config",
            )
        )

        # Dockerfile FROM inspection
        if "dockerfile" in self.rel_path.lower():
            for line_num, line in enumerate(self.lines, start=1):
                if line.strip().upper().startswith("FROM "):
                    img = line.strip().split()[1]
                    self.edges.append(
                        DependencyEdge(
                            source=self.mod_name,
                            target=img,
                            edge_type=EdgeType.IMPORTS,
                            line_number=line_num,
                        )
                    )

        # Docker compose services & depends_on
        service_pat = re.compile(r"""^\s{2}([A-Za-z0-9_-]+):""")
        dep_pat = re.compile(r"""depends_on:\s*\[(.*?)\]""")
        for line_num, line in enumerate(self.lines, start=1):
            m_s = service_pat.search(line)
            if m_s and not line.strip().startswith("#"):
                svc = m_s.group(1)
                qual = f"{self.mod_name}.{svc}"
                self.symbols.append(
                    Symbol(
                        name=svc,
                        qualified_name=qual,
                        symbol_type=SymbolType.ENDPOINT,
                        file_path=self.rel_path,
                        line_start=line_num,
                        line_end=line_num,
                        source_code=line.strip(),
                        language="config",
                    )
                )

        return self.symbols, self.edges


# ==============================================================================
# Generic Fallback Visitor
# ==============================================================================


class _GenericVisitor:
    """Fallback visitor for unclassified text/code assets."""

    def __init__(self, mod_name: str, rel_path: str, source_code: str):
        self.mod_name = mod_name
        self.rel_path = rel_path
        self.source_code = source_code
        self.lines = source_code.splitlines()

    def parse(self) -> Tuple[List[Symbol], List[DependencyEdge]]:
        mod_sym = Symbol(
            name=self.mod_name.split(".")[-1],
            qualified_name=self.mod_name,
            symbol_type=SymbolType.MODULE,
            file_path=self.rel_path,
            line_start=1,
            line_end=max(len(self.lines), 1),
            source_code=self.source_code,
            language="generic",
        )
        return [mod_sym], []
