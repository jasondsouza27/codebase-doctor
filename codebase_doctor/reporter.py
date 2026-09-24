import sys
from pathlib import Path
from typing import Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from codebase_doctor.models import ChangesetImpactReport, ImpactReport, TestSuiteExecution


class ReportGenerator:
    """Formats and exports audit reports across CLI, Markdown, and HTML."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(highlight=False)

    def print_terminal_report(
        self,
        report: ImpactReport,
        test_execution: Optional[TestSuiteExecution] = None,
    ):
        """Prints a rich colored terminal report matching the project specifications."""
        target_name = report.target_symbols[0] if report.target_symbols else Path(report.target_file).stem

        # Header panel
        header = Text()
        header.append("AI Codebase Doctor - Impact & Risk Analysis\n", style="bold cyan")
        header.append(f"Target: {report.target_file} ({target_name})\n", style="bold white")
        header.append(f"Blast Radius Score: {report.blast_radius_score} / 100", style="bold yellow")
        self.console.print(Panel(header, border_style="cyan"))

        # Affected Components Tree
        self.console.print("\n[bold green]Potentially affected:[/bold green]\n")

        # Deduplicate and prioritize high-level components/services
        seen = {target_name.replace("_", "").lower()}
        prominent_comps = []
        for comp in report.affected_components:
            name = comp.symbol_name
            norm_name = name.replace("_", "").lower()
            if name.startswith("__") or "test" in norm_name or norm_name in seen:
                continue
            seen.add(norm_name)
            prominent_comps.append(name)

        if not prominent_comps:
            for f in report.affected_files:
                stem = Path(f).stem
                cname = "".join(p.capitalize() for p in stem.split("_"))
                norm_c = cname.replace("_", "").lower()
                if norm_c not in seen and "test" not in norm_c and not norm_c.startswith("__"):
                    seen.add(norm_c)
                    prominent_comps.append(cname)

        clean_display_names = []
        for name in prominent_comps:
            norm_n = name.replace("_", "").lower()
            has_camel = any(norm_n == o.replace("_", "").lower() and o != name and o[0].isupper() for o in prominent_comps)
            if has_camel and "_" in name:
                continue
            if "_" in name and not any(c.isupper() for c in name):
                name = "".join(p.capitalize() for p in name.split("_"))
            if name not in clean_display_names:
                clean_display_names.append(name)

        tree_lines = [f"[bold white]{target_name}[/bold white]"]
        for i, name in enumerate(clean_display_names):
            prefix = " └── " if i == len(clean_display_names) - 1 else " ├── "
            tree_lines.append(f"{prefix}[cyan]{name}[/cyan]")
        self.console.print("\n".join(tree_lines))

        # Risk Areas
        self.console.print("\n[bold red]Risk areas:[/bold red]")
        for risk in report.risk_areas:
            self.console.print(f"- {risk}")

        # Suggested Tests
        self.console.print("\n[bold yellow]Suggested tests:[/bold yellow]")
        for test_name in report.suggested_tests:
            self.console.print(f"✓ [bold white]{test_name}[/bold white]")

        # Test Execution Results
        if test_execution:
            self.console.print("\n[bold magenta]Automated Test Execution Results:[/bold magenta]")
            table = Table(title=f"Pytest Execution: {test_execution.passed}/{test_execution.total} Passed ({test_execution.duration_sec}s)")
            table.add_column("Test Case", style="cyan")
            table.add_column("Status", style="bold")
            table.add_column("Message", style="dim")

            for res in test_execution.results:
                status_str = "[green]PASSED[/green]" if res.passed else "[red]FAILED[/red]"
                table.add_row(res.test_name, status_str, res.error_message or "OK")

            self.console.print(table)

    def generate_markdown(
        self,
        report: ImpactReport,
        test_execution: Optional[TestSuiteExecution] = None,
    ) -> str:
        """Generates a GitHub-flavored Markdown report."""
        target_name = report.target_symbols[0] if report.target_symbols else Path(report.target_file).stem

        lines = [
            f"# AI Codebase Doctor Report: `{report.target_file}`",
            "",
            f"**Target Symbol**: `{target_name}`  ",
            f"**Blast Radius Score**: `{report.blast_radius_score} / 100`  ",
            f"**Files Impacted**: `{len(report.affected_files)}`  ",
            "",
            "## Potentially Affected Components",
            "```text",
            f"{target_name}",
        ]

        seen = {target_name.lower()}
        comps = []
        for c in report.affected_components:
            name = c.symbol_name
            norm_name = name.replace("_", "").lower()
            if name.startswith("__") or "test" in norm_name or norm_name in seen:
                continue
            seen.add(norm_name)
            comps.append(name)

        if not comps:
            for f in report.affected_files:
                stem = Path(f).stem
                cname = "".join(p.capitalize() for p in stem.split("_"))
                norm_c = cname.replace("_", "").lower()
                if norm_c not in seen and "test" not in norm_c and not norm_c.startswith("__"):
                    seen.add(norm_c)
                    comps.append(cname)

        clean_display_names = []
        for name in comps:
            norm_n = name.replace("_", "").lower()
            has_camel = any(norm_n == o.replace("_", "").lower() and o != name and o[0].isupper() for o in comps)
            if has_camel and "_" in name:
                continue
            if "_" in name and not any(c.isupper() for c in name):
                name = "".join(p.capitalize() for p in name.split("_"))
            if name not in clean_display_names:
                clean_display_names.append(name)

        for i, name in enumerate(clean_display_names):
            prefix = " └── " if i == len(clean_display_names) - 1 else " ├── "
            lines.append(f"{prefix}{name}")

        lines.append("```")
        lines.append("")
        lines.append("## Risk Areas")
        for risk in report.risk_areas:
            lines.append(f"- **{risk}**")

        lines.append("")
        lines.append("## Suggested Tests")
        for test in report.suggested_tests:
            lines.append(f"- [x] `{test}`")

        if test_execution:
            lines.append("")
            lines.append("## Automated Test Execution Results")
            lines.append(f"**Passed**: `{test_execution.passed}/{test_execution.total}` | **Duration**: `{test_execution.duration_sec}s`")
            lines.append("")
            lines.append("| Test Function | Status | Error |")
            lines.append("| :--- | :--- | :--- |")
            for res in test_execution.results:
                status = "PASS" if res.passed else "FAIL"
                lines.append(f"| `{res.test_name}` | {status} | {res.error_message or '-'} |")

        return "\n".join(lines)

    def export_html(
        self,
        report: ImpactReport,
        output_file: Path,
        test_execution: Optional[TestSuiteExecution] = None,
    ):
        """Exports a self-contained modern HTML report."""
        target_name = report.target_symbols[0] if report.target_symbols else Path(report.target_file).stem

        seen = {target_name.lower()}
        comps = []
        for c in report.affected_components:
            name = c.symbol_name
            norm_name = name.replace("_", "").lower()
            if name.startswith("__") or "test" in norm_name or norm_name in seen:
                continue
            seen.add(norm_name)
            comps.append(name)

        clean_names = []
        for name in comps:
            if "_" in name and not any(c.isupper() for c in name):
                name = "".join(p.capitalize() for p in name.split("_"))
            if name not in clean_names:
                clean_names.append(name)

        tree_lines = [f"<strong>{target_name}</strong>"]
        for i, name in enumerate(clean_names):
            prefix = "&nbsp;└── " if i == len(clean_names) - 1 else "&nbsp;├── "
            tree_lines.append(f"{prefix}{name}")
        tree_html = "<br>".join(tree_lines)

        test_table_html = ""
        if test_execution:
            rows = "".join([
                f"<tr><td><code>{r.test_name}</code></td><td class='{'pass' if r.passed else 'fail'}'>{'PASS' if r.passed else 'FAIL'}</td><td>{r.error_message or 'OK'}</td></tr>"
                for r in test_execution.results
            ])
            test_table_html = f"""
            <div class="card">
                <h3>Automated Test Results ({test_execution.passed}/{test_execution.total} Passed in {test_execution.duration_sec}s)</h3>
                <table>
                    <thead><tr><th>Test</th><th>Status</th><th>Details</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AI Codebase Doctor - {target_name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
        h1, h2, h3 {{ color: #38bdf8; }}
        .badge {{ background: #ef4444; color: white; padding: 4px 10px; border-radius: 12px; font-weight: bold; }}
        .tree {{ background: #090d16; padding: 1rem; border-radius: 6px; font-family: monospace; color: #4ade80; }}
        ul {{ list-style-type: square; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #334155; color: #94a3b8; }}
        .pass {{ color: #4ade80; font-weight: bold; }}
        .fail {{ color: #f87171; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>AI Codebase Doctor Report</h1>
    <div class="card">
        <h2>Target: <code>{report.target_file}</code> ({target_name})</h2>
        <p>Blast Radius Score: <span class="badge">{report.blast_radius_score} / 100</span></p>
    </div>

    <div class="card">
        <h3>Potentially Affected Components</h3>
        <div class="tree">
            {tree_html}
        </div>
    </div>

    <div class="card">
        <h3>Risk Areas</h3>
        <ul>
            {"".join([f"<li>{r}</li>" for r in report.risk_areas])}
        </ul>
    </div>

    <div class="card">
        <h3>Suggested Tests</h3>
        <ul>
            {"".join([f"<li>✓ <code>{t}</code></li>" for t in report.suggested_tests])}
        </ul>
    </div>

    {test_table_html}
</body>
</html>"""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html, encoding="utf-8")

    def print_terminal_changeset_report(
        self,
        report: ChangesetImpactReport,
        test_execution: Optional[TestSuiteExecution] = None,
    ):
        """Prints a rich colored terminal report for a multi-file git changeset."""
        file_count = len(report.changed_files)
        files_preview = ", ".join(Path(f).name for f in report.changed_files[:3])
        if file_count > 3:
            files_preview += f", +{file_count - 3} more"

        # Header panel
        header = Text()
        header.append("AI Codebase Doctor - Changeset Impact & Risk Analysis\n", style="bold cyan")
        header.append(f"Changed Files ({file_count}): {files_preview}\n", style="bold white")
        if report.base_ref:
            header.append(f"Diff Base: {report.base_ref}\n", style="dim")
        header.append(f"Aggregated Blast Radius Score: {report.blast_radius_score} / 100", style="bold yellow")
        self.console.print(Panel(header, border_style="cyan"))

        # Changed Files Table
        files_table = Table(title="Modified Files in Changeset")
        files_table.add_column("File Path", style="cyan")
        files_table.add_column("Target Symbols / Scope", style="green")
        for f in report.changed_files:
            rep = report.per_file_reports.get(f)
            syms = ", ".join(rep.target_symbols[:3]) if rep and rep.target_symbols else "-"
            files_table.add_row(f, syms)
        self.console.print(files_table)

        # Potentially Affected Downstream Tree
        self.console.print("\n[bold green]Potentially affected downstream dependents:[/bold green]\n")
        seen = {Path(f).stem.lower() for f in report.changed_files}
        seen.update(s.lower() for s in report.target_symbols)

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

        root_label = f"[bold white]Changeset ({file_count} files modified)[/bold white]"
        tree_lines = [root_label]
        for i, (name, depth) in enumerate(prominent):
            prefix = " └── " if i == len(prominent) - 1 else " ├── "
            depth_str = f" [dim](depth {depth})[/dim]" if depth > 1 else ""
            tree_lines.append(f"{prefix}[cyan]{name}[/cyan]{depth_str}")

        if len(tree_lines) == 1:
            tree_lines.append(" └── [dim](No external downstream components affected)[/dim]")
        self.console.print("\n".join(tree_lines))

        # Combined Risk Areas
        self.console.print("\n[bold red]Aggregated Risk areas:[/bold red]")
        if report.risk_areas:
            for risk in report.risk_areas:
                self.console.print(f"- {risk}")
        else:
            self.console.print("[dim]- No high-risk architectural patterns detected[/dim]")

        # Suggested Tests
        self.console.print("\n[bold yellow]Suggested verification tests:[/bold yellow]")
        for test_name in report.suggested_tests:
            self.console.print(f"✓ [bold white]{test_name}[/bold white]")

        # Automated Test Execution Results
        if test_execution:
            self.console.print("\n[bold magenta]Automated Test Execution Results:[/bold magenta]")
            table = Table(title=f"Pytest Execution: {test_execution.passed}/{test_execution.total} Passed ({test_execution.duration_sec}s)")
            table.add_column("Test Case", style="cyan")
            table.add_column("Status", style="bold")
            table.add_column("Message", style="dim")

            for res in test_execution.results:
                status_str = "[green]PASSED[/green]" if res.passed else "[red]FAILED[/red]"
                table.add_row(res.test_name, status_str, res.error_message or "OK")

            self.console.print(table)

    def generate_pr_markdown(
        self,
        report: ChangesetImpactReport,
        test_execution: Optional[TestSuiteExecution] = None,
        diff_stat: Optional[str] = None,
    ) -> str:
        """Generates a comprehensive GitHub PR review comment in Markdown."""
        file_count = len(report.changed_files)
        base_desc = report.base_ref or "working tree (uncommitted)"

        badge_color = "red" if report.blast_radius_score >= 60 else ("yellow" if report.blast_radius_score >= 30 else "green")
        badge = f"**{report.blast_radius_score} / 100** ({badge_color.upper()})"

        test_summary = "Not Run"
        test_status = "Manual"
        if test_execution:
            test_summary = f"{test_execution.passed}/{test_execution.total} Passed ({test_execution.duration_sec}s)"
            test_status = "PASS" if test_execution.failed == 0 else f"FAIL ({test_execution.failed})"

        lines = [
            "# AI Codebase Doctor - PR Blast Radius Assessment",
            "",
            "> **Automated Architectural Safeguard Report**  ",
            f"> Evaluated changeset against `{base_desc}` across **{file_count}** modified file{'s' if file_count != 1 else ''}.",
            "",
            "## Executive Summary",
            "| Metric | Value | Status |",
            "| :--- | :--- | :--- |",
            f"| **Aggregated Blast Radius** | {badge} | {'High Ripple Effect' if report.blast_radius_score >= 60 else ('Moderate' if report.blast_radius_score >= 30 else 'Contained')} |",
            f"| **Files Modified** | `{file_count}` files | Changeset |",
            f"| **Direct / Indirect Dependents** | `{len(report.affected_components)}` components | Impacted |",
            f"| **Downstream Files Impacted** | `{len(report.affected_files)}` files | Dependencies |",
            f"| **Risk Areas Identified** | `{len(report.risk_areas)}` areas | Warnings |",
            f"| **Test Verification Suite** | `{test_summary}` | {test_status} |",
            "",
            "### Modified Files in this Changeset:",
        ]

        for f in report.changed_files:
            rep = report.per_file_reports.get(f)
            sym_count = len(rep.target_symbols) if rep else 0
            lines.append(f"- `{f}` ({sym_count} symbols indexed)")

        if diff_stat or report.diff_stat:
            stat_content = diff_stat or report.diff_stat
            lines.extend([
                "",
                "<details>",
                "<summary><b>Git Diff Stat</b> (click to expand)</summary>",
                "",
                "```text",
                stat_content.strip(),
                "```",
                "</details>",
            ])

        lines.extend([
            "",
            "## Combined Blast Radius & Ripple Effect",
            "```text",
        ])

        seen = {Path(f).stem.lower() for f in report.changed_files}
        seen.update(s.lower() for s in report.target_symbols)

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

        files_label = ", ".join(Path(f).name for f in report.changed_files[:3])
        if file_count > 3:
            files_label += f", +{file_count - 3} more"
        lines.append(f"Changeset ({file_count} files: {files_label})")

        for i, (name, depth) in enumerate(prominent):
            prefix = " └── " if i == len(prominent) - 1 else " ├── "
            depth_str = f" (depth {depth})" if depth > 1 else ""
            lines.append(f"{prefix}{name}{depth_str}")

        if not prominent:
            lines.append(" └── (No external downstream components affected)")
        lines.append("```")

        lines.extend([
            "",
            "## Identified Architectural & Logic Risk Areas",
        ])
        if report.risk_areas:
            for r in report.risk_areas:
                lines.append(f"- **{r}**")
        else:
            lines.append("- *No high-risk architectural anomalies detected.*")

        lines.extend([
            "",
            "## Suggested Verification Tests",
            "Reviewers and CI should ensure coverage for:",
        ])
        for t in report.suggested_tests:
            lines.append(f"- [x] `{t}`")

        if test_execution:
            lines.extend([
                "",
                "## Automated Test Execution Results",
                f"**Result**: `{test_execution.passed}/{test_execution.total} Passed` in `{test_execution.duration_sec}s`",
                "",
                "| Test Function | Status | Error Details |",
                "| :--- | :--- | :--- |",
            ])
            for res in test_execution.results:
                status = "PASS" if res.passed else "FAIL"
                lines.append(f"| `{res.test_name}` | {status} | {res.error_message or '-'} |")

        lines.extend([
            "",
            "## Reviewer Recommendations",
            "- [ ] Check interface contract stability between modified files and downstream dependents.",
            "- [ ] Validate boundary conditions in detected risk areas before merging.",
            "- [ ] Ensure CI runs all generated and regression test suites.",
            "",
            "---",
            "*Generated by [AI Codebase Doctor](https://github.com/codebase-doctor) • Continuous Architectural Safeguards*",
        ])

        return "\n".join(lines)

    def export_changeset_html(
        self,
        report: ChangesetImpactReport,
        output_file: Path,
        test_execution: Optional[TestSuiteExecution] = None,
    ):
        """Exports a self-contained modern HTML report for a git changeset."""
        file_count = len(report.changed_files)
        files_label = ", ".join(Path(f).name for f in report.changed_files[:3])
        if file_count > 3:
            files_label += f", +{file_count - 3} more"

        tree_lines = [f"<strong>Changeset ({file_count} files: {files_label})</strong>"]
        for i, comp in enumerate(report.affected_components):
            prefix = "&nbsp;└── " if i == len(report.affected_components) - 1 else "&nbsp;├── "
            tree_lines.append(f"{prefix}{comp.symbol_name} (depth {comp.depth})")
        if not report.affected_components:
            tree_lines.append("&nbsp;└── (No external downstream components affected)")
        tree_html = "<br>".join(tree_lines)

        test_table_html = ""
        if test_execution:
            rows = "".join([
                f"<tr><td><code>{r.test_name}</code></td><td class='{'pass' if r.passed else 'fail'}'>{'PASS' if r.passed else 'FAIL'}</td><td>{r.error_message or 'OK'}</td></tr>"
                for r in test_execution.results
            ])
            test_table_html = f"""
            <div class="card">
                <h3>Automated Test Results ({test_execution.passed}/{test_execution.total} Passed in {test_execution.duration_sec}s)</h3>
                <table>
                    <thead><tr><th>Test</th><th>Status</th><th>Details</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AI Codebase Doctor - Changeset Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
        h1, h2, h3 {{ color: #38bdf8; }}
        .badge {{ background: #ef4444; color: white; padding: 4px 10px; border-radius: 12px; font-weight: bold; }}
        .tree {{ background: #090d16; padding: 1rem; border-radius: 6px; font-family: monospace; color: #4ade80; }}
        ul {{ list-style-type: square; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #334155; color: #94a3b8; }}
        .pass {{ color: #4ade80; font-weight: bold; }}
        .fail {{ color: #f87171; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>AI Codebase Doctor - Changeset Report</h1>
    <div class="card">
        <h2>Modified Files ({file_count}): <code>{", ".join(report.changed_files)}</code></h2>
        <p>Aggregated Blast Radius Score: <span class="badge">{report.blast_radius_score} / 100</span></p>
    </div>

    <div class="card">
        <h3>Potentially Affected Downstream Components</h3>
        <div class="tree">
            {tree_html}
        </div>
    </div>

    <div class="card">
        <h3>Combined Risk Areas</h3>
        <ul>
            {"".join([f"<li>{r}</li>" for r in report.risk_areas])}
        </ul>
    </div>

    <div class="card">
        <h3>Suggested Tests</h3>
        <ul>
            {"".join([f"<li>✓ <code>{t}</code></li>" for t in report.suggested_tests])}
        </ul>
    </div>

    {test_table_html}
</body>
</html>"""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html_content, encoding="utf-8")
