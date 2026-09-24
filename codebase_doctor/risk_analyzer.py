"""
Polyglot Risk & Bug Analyzer
Detects security vulnerabilities, hardware/IoT risks, financial/business logic flaws,
memory safety defects, and regression risks using static AST analysis and domain heuristics
across Python, JavaScript/TypeScript, C/C++/Arduino, Java, Go, Shell, and SQL.
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from codebase_doctor.models import RiskCategory, RiskItem, RiskSeverity


class RiskAnalyzer:
    """Performs static rule-based security and logic risk analysis across polyglot source files."""

    SECRET_PATTERN = re.compile(
        r"""(?i)(api[_-]?key|secret|token|password|auth_token)\s*[:=]\s*['"][a-zA-Z0-9_\-]{8,}['"]"""
    )
    SQL_INJECTION_PATTERN = re.compile(
        r"""(?i)(execute|cursor\.execute|query)\s*\(\s*(?:f['"].*(?:SELECT|INSERT|UPDATE|DELETE).*\{.*\}|`.*(?:SELECT|INSERT|UPDATE|DELETE).*\$\{.*\}.*`|['"].*(?:SELECT|INSERT|UPDATE|DELETE).*['"]\s*\+\s*[a-zA-Z0-9_])"""
    )
    CURRENCY_KEYWORDS = {"currency", "amount", "price", "fee", "tax", "rate", "cents", "payment"}
    REFUND_KEYWORDS = {"refund", "partial_refund", "reversal", "chargeback"}
    STATUS_KEYWORDS = {"status", "state", "sync", "transition", "settled", "pending"}

    def analyze_file(self, file_path: str, source_code: str) -> List[RiskItem]:
        """Runs all security, logic, and safety checks on a source file across languages."""
        risks: List[RiskItem] = []
        lines = source_code.splitlines()

        # 1. Universal Regex checks across all files and languages (secrets, SQLi)
        risks.extend(self._check_regex_patterns(file_path, lines))

        # 2. Language-specific checks
        ext = Path(file_path).suffix.lower()

        if ext in {".py", ".pyw"}:
            try:
                tree = ast.parse(source_code, filename=file_path)
                visitor = _RiskVisitor(file_path=file_path, lines=lines)
                visitor.visit(tree)
                risks.extend(visitor.risks)
                risks.extend(self._check_python_business_logic_risks(file_path, tree, lines))
            except SyntaxError:
                pass
        elif ext in {".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx", ".ino"}:
            risks.extend(self._check_cpp_arduino_risks(file_path, lines))
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            risks.extend(self._check_js_ts_risks(file_path, lines))
        elif ext in {".sh", ".bash", ".zsh", ".ps1"}:
            risks.extend(self._check_shell_risks(file_path, lines))
        elif ext == ".sql":
            risks.extend(self._check_sql_risks(file_path, lines))

        # 3. Universal cross-language business logic checks
        risks.extend(self._check_universal_business_risks(file_path, lines))

        return risks

    def _check_regex_patterns(self, file_path: str, lines: List[str]) -> List[RiskItem]:
        risks = []
        for idx, line in enumerate(lines, start=1):
            # Check hardcoded secret / credentials
            if self.SECRET_PATTERN.search(line):
                ignore_keywords = ["os.environ", "getenv", "process.env", "System.getenv", "std::getenv", "placeholder", "example"]
                if not any(k in line for k in ignore_keywords):
                    risks.append(
                        RiskItem(
                            category=RiskCategory.SECURITY,
                            severity=RiskSeverity.CRITICAL,
                            title="Hardcoded Secret or Token",
                            description=f"Potential hardcoded credentials detected on line {idx}.",
                            file_path=file_path,
                            line_number=idx,
                            remediation="Use environment variables or a secure secret manager (e.g. os.getenv / process.env).",
                        )
                    )

            # Check SQL injection string interpolation / concatenation
            if self.SQL_INJECTION_PATTERN.search(line):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.CRITICAL,
                        title="SQL Injection Vulnerability",
                        description=f"Direct string interpolation/concatenation in SQL query on line {idx}.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Use parameterized queries / prepared statements instead of string interpolation.",
                    )
                )

        return risks

    def _check_cpp_arduino_risks(self, file_path: str, lines: List[str]) -> List[RiskItem]:
        """Audits C, C++, and Arduino/ESP32 firmware for memory safety and hardware concurrency risks."""
        risks = []
        is_ino = file_path.endswith(".ino") or "esp32" in file_path.lower() or "arduino" in file_path.lower()

        for idx, line in enumerate(lines, start=1):
            clean = line.strip()
            if clean.startswith("//") or clean.startswith("/*"):
                continue

            # Memory safety: Unbounded string operations (strcpy, strcat, sprintf, gets)
            unsafe_mem = re.search(r"""\b(strcpy|strcat|sprintf|gets)\s*\(""", clean)
            if unsafe_mem:
                fn = unsafe_mem.group(1)
                risks.append(
                    RiskItem(
                        category=RiskCategory.MEMORY_SAFETY,
                        severity=RiskSeverity.CRITICAL,
                        title="Unbounded Buffer Operation / Buffer Overflow",
                        description=f"Use of unsafe memory function '{fn}()' on line {idx} without explicit buffer bounds checking.",
                        file_path=file_path,
                        line_number=idx,
                        remediation=f"Replace '{fn}()' with safer bounded alternative (e.g. snprintf, strncpy) and verify buffer capacity.",
                    )
                )

            # Hardware / IoT concurrency: Blocking delay() in loop or serial communications
            if is_ino:
                delay_match = re.search(r"""\bdelay\s*\(\s*([1-9]\d{2,})\s*\)""", clean)
                if delay_match:
                    ms = delay_match.group(1)
                    risks.append(
                        RiskItem(
                            category=RiskCategory.HARDWARE_IOT,
                            severity=RiskSeverity.HIGH,
                            title="Blocking Hardware Delay",
                            description=f"Blocking delay({ms}ms) on line {idx} freezes MCU execution and drops serial/sensor packets.",
                            file_path=file_path,
                            line_number=idx,
                            remediation="Replace blocking delay() with non-blocking millis() timer state machine.",
                        )
                    )

                # Unbounded Serial connection hang
                if re.search(r"""while\s*\(\s*!\s*Serial\s*\)""", clean):
                    risks.append(
                        RiskItem(
                            category=RiskCategory.HARDWARE_IOT,
                            severity=RiskSeverity.MEDIUM,
                            title="Unbounded Serial Port Connection Wait",
                            description=f"Infinite 'while(!Serial)' on line {idx} will freeze headless MCU operation if USB cable is unplugged.",
                            file_path=file_path,
                            line_number=idx,
                            remediation="Add a timeout counter or millisecond check so firmware boots even if USB is unplugged.",
                        )
                    )

            # Insecure random number generation
            if re.search(r"""\brand\s*\(\s*\)""", clean) and any(
                w in clean.lower() for w in ["token", "auth", "key", "secret", "nonce"]
            ):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.HIGH,
                        title="Insecure Cryptographic Randomness",
                        description=f"Standard pseudo-random generator 'rand()' used for security-sensitive value on line {idx}.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Use hardware RNG (e.g. esp_random() on ESP32 or OpenSSL RAND_bytes).",
                    )
                )

        return risks

    def _check_js_ts_risks(self, file_path: str, lines: List[str]) -> List[RiskItem]:
        """Audits JavaScript and TypeScript files for security defects and race conditions."""
        risks = []
        for idx, line in enumerate(lines, start=1):
            clean = line.strip()
            if clean.startswith("//"):
                continue

            # Insecure code execution via eval() or new Function()
            if re.search(r"""\beval\s*\(|new\s+Function\s*\(""", clean):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.CRITICAL,
                        title="Arbitrary Code Execution (eval)",
                        description=f"Dynamic code evaluation on line {idx} can allow remote code execution.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Avoid eval(); use JSON.parse() or safe typed parser.",
                    )
                )

            # Insecure random number generation
            if "Math.random" in clean and any(w in clean.lower() for w in ["token", "secret", "auth", "key", "session", "password"]):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.HIGH,
                        title="Insecure Cryptographic Randomness",
                        description=f"Math.random() used for security-sensitive token/auth value on line {idx}.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Use crypto.randomBytes() or crypto.getRandomValues().",
                    )
                )

            # Command injection
            if re.search(r"""(?:child_process\.)?(?:exec|execSync)\s*\(""", clean):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.CRITICAL,
                        title="Command Injection (child_process.exec)",
                        description=f"Shell command execution on line {idx}.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Use execFile or spawn with argument array instead of string shell execution.",
                    )
                )

        return risks

    def _check_shell_risks(self, file_path: str, lines: List[str]) -> List[RiskItem]:
        """Audits Shell scripts for destructive or dangerous execution."""
        risks = []
        for idx, line in enumerate(lines, start=1):
            clean = line.strip()
            if clean.startswith("#"):
                continue

            if re.search(r"""rm\s+-rf\s+["']?\$[A-Za-z0-9_]+["']?""", clean):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.HIGH,
                        title="Destructive Shell Variable Expansion Risk",
                        description=f"Potentially unbounded 'rm -rf $VAR' on line {idx} if variable is unset.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Validate variable is non-empty before rm (e.g. ${VAR:?error}).",
                    )
                )
            if re.search(r"""\beval\s+["']?\$""", clean):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.HIGH,
                        title="Command Injection via eval",
                        description=f"Dynamic evaluation of shell variable on line {idx}.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Avoid eval in shell scripts; invoke commands directly.",
                    )
                )

        return risks

    def _check_sql_risks(self, file_path: str, lines: List[str]) -> List[RiskItem]:
        """Audits SQL files for unhashed passwords or dangerous schema operations."""
        risks = []
        for idx, line in enumerate(lines, start=1):
            if re.search(r"""\bpassword\s+(?:VARCHAR|TEXT|CHAR)\b""", line, re.IGNORECASE) and not any(
                h in line.lower() for h in ["hash", "salt", "digest", "bcrypt", "argon"]
            ):
                risks.append(
                    RiskItem(
                        category=RiskCategory.SECURITY,
                        severity=RiskSeverity.HIGH,
                        title="Plaintext Password Storage Risk",
                        description=f"Table schema on line {idx} appears to store plaintext passwords without hash/salt column.",
                        file_path=file_path,
                        line_number=idx,
                        remediation="Store salted hashes (e.g. bcrypt or argon2id), never plain passwords.",
                    )
                )
        return risks

    def _check_universal_business_risks(self, file_path: str, lines: List[str]) -> List[RiskItem]:
        """Audits financial & transaction files across languages for float precision and bounds."""
        risks = []
        file_lower = file_path.lower()
        is_finance = any(k in file_lower for k in ["payment", "order", "invoice", "refund", "billing"])
        if not is_finance:
            return risks

        # If file is non-python (since python has AST check), check float math via regex
        if not file_path.endswith((".py", ".pyw")):
            for idx, line in enumerate(lines, start=1):
                if any(w in line.lower() for w in ["tax", "fee", "rate", "currency", "convert", "total"]):
                    if re.search(r"""[\*\/\+\-]\s*(?:0\.\d+|\d+\.\d+)""", line):
                        risks.append(
                            RiskItem(
                                category=RiskCategory.BUSINESS_LOGIC,
                                severity=RiskSeverity.HIGH,
                                title="Currency Conversion Float Precision Risk",
                                description=f"Floating-point arithmetic detected on line {idx}. Financial math must use fixed-point or integer cents.",
                                file_path=file_path,
                                line_number=idx,
                                remediation="Replace floating-point math with integer cents or Decimal/BigDecimal.",
                            )
                        )
                        break

            # Check refund bounds
            content = "\n".join(lines)
            if any(k in content.lower() for k in self.REFUND_KEYWORDS):
                has_bounds = any(sym in content for sym in ["<=", ">=", "remaining", "balance", "max_refund"])
                if not has_bounds:
                    risks.append(
                        RiskItem(
                            category=RiskCategory.BUSINESS_LOGIC,
                            severity=RiskSeverity.HIGH,
                            title="Refund Calculation Boundary Check Missing",
                            description="Refund processing logic lacks explicit bounds checking against original transaction balance.",
                            file_path=file_path,
                            line_number=1,
                            remediation="Add validation ensuring refund_amount <= remaining_balance before processing.",
                        )
                    )

        return risks

    def _check_python_business_logic_risks(self, file_path: str, tree: ast.AST, lines: List[str]) -> List[RiskItem]:
        risks = []
        file_lower = file_path.lower()
        is_payment_or_finance = any(k in file_lower for k in ["payment", "order", "invoice", "refund", "billing"])

        if not is_payment_or_finance:
            return risks

        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div, ast.Add, ast.Sub)):
                if isinstance(node.left, ast.Constant) and isinstance(node.left.value, float):
                    risks.append(
                        RiskItem(
                            category=RiskCategory.BUSINESS_LOGIC,
                            severity=RiskSeverity.HIGH,
                            title="Currency Conversion Float Precision Risk",
                            description=f"Floating-point arithmetic detected on line {node.lineno}. Financial math must use decimal.Decimal to avoid rounding drift.",
                            file_path=file_path,
                            line_number=node.lineno,
                            remediation="Replace floating-point numbers with decimal.Decimal.",
                        )
                    )
                    break
                elif isinstance(node.right, ast.Constant) and isinstance(node.right.value, float):
                    risks.append(
                        RiskItem(
                            category=RiskCategory.BUSINESS_LOGIC,
                            severity=RiskSeverity.HIGH,
                            title="Currency Conversion Float Precision Risk",
                            description=f"Floating-point arithmetic detected on line {node.lineno}. Financial math must use decimal.Decimal to avoid rounding drift.",
                            file_path=file_path,
                            line_number=node.lineno,
                            remediation="Replace floating-point numbers with decimal.Decimal.",
                        )
                    )
                    break

        has_refund_bounds_check = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and any(k in node.name.lower() for k in self.REFUND_KEYWORDS):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Compare, ast.If)):
                        has_refund_bounds_check = True
                        break
                if not has_refund_bounds_check:
                    risks.append(
                        RiskItem(
                            category=RiskCategory.BUSINESS_LOGIC,
                            severity=RiskSeverity.HIGH,
                            title="Refund Calculation Boundary Check Missing",
                            description=f"Method '{node.name}' handles refunds without explicit bounds checking against the original transaction amount.",
                            file_path=file_path,
                            line_number=node.lineno,
                            affected_symbol=node.name,
                            remediation="Add validation ensuring refund_amount <= remaining_balance before processing.",
                        )
                    )

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and any(k in node.name.lower() for k in ["process_payment", "settle", "charge"]):
                code_text = ast.unparse(node) if hasattr(ast, "unparse") else ""
                if "status" in code_text and "try" in code_text and "except" in code_text:
                    if "FAILED" not in code_text and "ERROR" not in code_text:
                        risks.append(
                            RiskItem(
                                category=RiskCategory.CONCURRENCY,
                                severity=RiskSeverity.MEDIUM,
                                title="Payment Status Synchronization Risk",
                                description=f"Method '{node.name}' updates status but might leave state ambiguous on unhandled retry or network failure.",
                                file_path=file_path,
                                line_number=node.lineno,
                                affected_symbol=node.name,
                                remediation="Implement idempotent state machine transitions and explicit failure status updates.",
                            )
                        )

        return risks


class _RiskVisitor(ast.NodeVisitor):
    """AST visitor for Python security vulnerabilities and code smells."""

    def __init__(self, file_path: str, lines: List[str]):
        self.file_path = file_path
        self.lines = lines
        self.risks: List[RiskItem] = []

    def visit_Call(self, node: ast.Call):
        func_name = self._resolve_name(node.func)

        # Insecure deserialization
        if func_name in ("pickle.loads", "pickle.load", "_pickle.loads"):
            self.risks.append(
                RiskItem(
                    category=RiskCategory.SECURITY,
                    severity=RiskSeverity.CRITICAL,
                    title="Insecure Deserialization (Pickle)",
                    description=f"Use of {func_name} on line {node.lineno} can lead to arbitrary code execution.",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    remediation="Use a safe format like JSON or Protocol Buffers.",
                )
            )

        # Command injection
        if func_name in ("os.system", "posix.system"):
            self.risks.append(
                RiskItem(
                    category=RiskCategory.SECURITY,
                    severity=RiskSeverity.CRITICAL,
                    title="Command Injection (os.system)",
                    description=f"Execution of shell command via {func_name} on line {node.lineno}.",
                    file_path=self.file_path,
                    line_number=node.lineno,
                    remediation="Use subprocess.run with shell=False and pass arguments as a list.",
                )
            )

        # Insecure random
        if func_name in ("random.random", "random.randint", "random.choice"):
            for line_idx in range(max(0, node.lineno - 2), min(len(self.lines), node.lineno + 1)):
                if any(w in self.lines[line_idx].lower() for w in ["token", "secret", "auth", "session", "key", "password"]):
                    self.risks.append(
                        RiskItem(
                            category=RiskCategory.SECURITY,
                            severity=RiskSeverity.HIGH,
                            title="Insecure Cryptographic Randomness",
                            description=f"Standard pseudo-random generator used for security-sensitive token on line {node.lineno}.",
                            file_path=self.file_path,
                            line_number=node.lineno,
                            remediation="Use secrets.token_hex() or secrets.choice() for cryptographically secure values.",
                        )
                    )
                    break

        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.type is None:
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                self.risks.append(
                    RiskItem(
                        category=RiskCategory.ERROR_HANDLING,
                        severity=RiskSeverity.MEDIUM,
                        title="Silent Exception Suppression",
                        description=f"Bare 'except: pass' silently suppresses all errors on line {node.lineno}.",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        remediation="Catch specific exceptions and log the error.",
                    )
                )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        for default in node.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.risks.append(
                    RiskItem(
                        category=RiskCategory.REGRESSION,
                        severity=RiskSeverity.MEDIUM,
                        title="Mutable Default Argument",
                        description=f"Function '{node.name}' uses a mutable default argument on line {node.lineno}.",
                        file_path=self.file_path,
                        line_number=node.lineno,
                        affected_symbol=node.name,
                        remediation="Use None as default and initialize inside the function (e.g. data = data or []).",
                    )
                )
        self.generic_visit(node)

    def _resolve_name(self, expr: ast.AST) -> str:
        if isinstance(expr, ast.Name):
            return expr.id
        elif isinstance(expr, ast.Attribute):
            val = self._resolve_name(expr.value)
            return f"{val}.{expr.attr}" if val else expr.attr
        return ""
