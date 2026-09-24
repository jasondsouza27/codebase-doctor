"""
Automated Test Runner
Executes Pytest in a subprocess, parses stdout/stderr, and returns structured execution metrics.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from codebase_doctor.models import TestResult, TestSuiteExecution


class TestRunner:
    """Executes pytest suites and captures structured test outcomes."""
    __test__ = False

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path.cwd()

    def run_tests(self, target_path: Path, timeout_seconds: int = 60) -> TestSuiteExecution:
        """
        Runs pytest on the specified file or directory and parses the results.
        """
        start_time = time.time()
        cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", str(target_path)]

        # Set PYTHONPATH so tested modules are importable
        env = os.environ.copy()
        repo_str = str(self.repo_root.resolve())
        env["PYTHONPATH"] = f"{repo_str}{os.pathsep}{env.get('PYTHONPATH', '')}"

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
            raw_output = proc.stdout + "\n" + proc.stderr
            duration = time.time() - start_time
            return self._parse_pytest_output(raw_output, duration)
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestSuiteExecution(
                total=1,
                passed=0,
                failed=1,
                skipped=0,
                duration_sec=duration,
                results=[
                    TestResult(
                        test_name=str(target_path),
                        passed=False,
                        duration_sec=duration,
                        error_message=f"Test execution timed out after {timeout_seconds}s",
                    )
                ],
                raw_output=f"Timeout after {timeout_seconds} seconds.",
            )
        except Exception as e:
            duration = time.time() - start_time
            return TestSuiteExecution(
                total=1,
                passed=0,
                failed=1,
                skipped=0,
                duration_sec=duration,
                results=[
                    TestResult(
                        test_name=str(target_path),
                        passed=False,
                        duration_sec=duration,
                        error_message=str(e),
                    )
                ],
                raw_output=str(e),
            )

    def _parse_pytest_output(self, output: str, duration: float) -> TestSuiteExecution:
        """Parses Pytest verbose output to extract individual test statuses."""
        results: List[TestResult] = []
        passed = 0
        failed = 0
        skipped = 0

        # Pattern: test_file.py::test_name PASSED / FAILED / SKIPPED
        line_pattern = re.compile(r"^(.*?)::(.*?)\s+(PASSED|FAILED|SKIPPED|ERROR)(.*)$")

        for line in output.splitlines():
            line_clean = line.strip()
            match = line_pattern.match(line_clean)
            if match:
                file_part, test_fn, status, _ = match.groups()
                is_pass = status == "PASSED"
                if is_pass:
                    passed += 1
                elif status in ("FAILED", "ERROR"):
                    failed += 1
                else:
                    skipped += 1

                results.append(
                    TestResult(
                        test_name=test_fn,
                        passed=is_pass,
                        duration_sec=0.01,
                        error_message=None if is_pass else f"Status: {status}",
                    )
                )

        total = passed + failed + skipped

        # Summary line fallback if verbose lines weren't caught
        if total == 0:
            summary_match = re.search(r"(=+)\s*(.*?)\s*(=+)", output)
            if "passed" in output.lower():
                pass_match = re.search(r"(\d+)\s+passed", output)
                if pass_match:
                    passed = int(pass_match.group(1))
            if "failed" in output.lower():
                fail_match = re.search(r"(\d+)\s+failed", output)
                if fail_match:
                    failed = int(fail_match.group(1))
            total = passed + failed + skipped

        return TestSuiteExecution(
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_sec=round(duration, 3),
            results=results,
            raw_output=output,
        )
