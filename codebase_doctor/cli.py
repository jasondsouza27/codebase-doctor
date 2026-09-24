import os
import sys
from pathlib import Path
import click

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.table import Table

from codebase_doctor.doctor import CodebaseDoctor

console = Console(highlight=False)


@click.group()
def main():
    """AI Codebase Doctor: Understand legacy codebases, blast radiuses, and risk areas."""
    pass


@main.command()
@click.argument("url")
@click.option("--target", "-t", default=None, help="Target local directory to clone into")
def clone(url, target):
    """Clones a remote GitHub/Git repository for analysis."""
    console.print(f"[bold cyan][git] Cloning repository:[/] {url}")
    from codebase_doctor.repo_manager import RepoManager
    mgr = RepoManager(root_path=url, clone_dir=target)
    console.print(f"[green][ok] Successfully cloned to:[/] {mgr.root_path}")


@main.command()
@click.option("--repo", "-r", default=".", help="Path to repository root or remote Git URL")
@click.option("--incremental", "-i", is_flag=True, default=False, help="Perform incremental scan of changed files only")
def scan(repo, incremental):
    """Parses codebase and prints architecture & graph statistics."""
    if any(str(repo).startswith(p) for p in ("http://", "https://", "git@", "github.com/")):
        console.print(f"[bold yellow][git] Cloning remote repository:[/] {repo}")
    scan_mode = "Incremental" if incremental else "Full"
    console.print(f"[bold cyan][scan] {scan_mode} scanning codebase at:[/] {repo}")
    doctor = CodebaseDoctor(repo_path=repo, console=console)
    stats = doctor.scan(incremental=incremental)

    if stats.get("incremental"):
        console.print(
            f"[bold green][ok] Incremental delta:[/] "
            f"+{stats.get('added', 0)} added, "
            f"~{stats.get('modified', 0)} modified, "
            f"-{stats.get('deleted', 0)} deleted, "
            f"{stats.get('unchanged', 0)} unchanged."
        )

    table = Table(title="Codebase Architecture Overview")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")

    table.add_row("Total Files Indexed", str(stats["total_files"]))
    table.add_row("Total Code Symbols (Classes/Functions)", str(stats["total_nodes"]))
    table.add_row("Total Dependency Relationships", str(stats["total_edges"]))
    table.add_row("Inter-file Dependencies", str(stats["total_file_dependencies"]))
    table.add_row("Circular Import Cycles", str(stats["circular_dependencies_count"]))

    console.print(table)

    # Languages breakdown
    languages = stats.get("languages", {}) or doctor.repo_manager.get_languages()
    if languages:
        lang_table = Table(title="Polyglot Language Distribution")
        lang_table.add_column("Language", style="magenta")
        lang_table.add_column("Files", style="bold cyan")
        lang_table.add_column("Share", style="green")
        total_files = max(stats["total_files"], 1)
        for lang_name, count in languages.items():
            pct = f"{round(count / total_files * 100, 1)}%"
            lang_table.add_row(lang_name, str(count), pct)
        console.print(lang_table)

    # Top Central Core Components
    pagerank = doctor.graph.compute_pagerank()
    if pagerank:
        top_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:5]
        central_table = Table(title="Top 5 Critical Core Components (PageRank Centrality)")
        central_table.add_column("Component", style="yellow")
        central_table.add_column("Centrality Score", style="bold white")
        for node, score in top_nodes:
            central_table.add_row(node, f"{score:.4f}")
        console.print(central_table)


@main.command()
@click.argument("target")
@click.option("--repo", "-r", default=".", help="Path to repository root")
@click.option("--run-tests/--no-tests", default=True, help="Automatically generate and run tests")
@click.option("--export-md", default=None, help="Path to export Markdown report")
@click.option("--export-html", default=None, help="Path to export HTML report")
def impact(target, repo, run_tests, export_md, export_html):
    """Predicts blast radius, risk areas, and tests when modifying TARGET."""
    doctor = CodebaseDoctor(repo_path=repo, console=console)
    report, execution = doctor.run_full_diagnosis(target, auto_run_tests=run_tests)

    if export_md:
        md_content = doctor.reporter.generate_markdown(report, execution)
        Path(export_md).write_text(md_content, encoding="utf-8")
        console.print(f"[green][saved] Markdown report saved to:[/] {export_md}")

    if export_html:
        doctor.reporter.export_html(report, Path(export_html), execution)
        console.print(f"[green][saved] HTML report saved to:[/] {export_html}")


@main.command()
@click.argument("question")
@click.option("--repo", "-r", default=".", help="Path to repository root")
def ask(question, repo):
    """Ask an architectural question using Graph-Augmented RAG."""
    console.print(f"[bold cyan][query] AI Doctor Query:[/] {question}")
    doctor = CodebaseDoctor(repo_path=repo, console=console)
    res = doctor.ask(question)

    console.print(f"\n[bold green]Answer:[/bold green]\n{res['answer']}")
    if res.get("retrieved_nodes"):
        console.print(f"\n[dim]Retrieved graph nodes: {', '.join(res['retrieved_nodes'])}[/dim]")


@main.command()
@click.option("--repo", "-r", default=".", help="Path to repository root")
def risks(repo):
    """Scans codebase for security, currency, and logic risks."""
    doctor = CodebaseDoctor(repo_path=repo, console=console)
    doctor.scan()

    all_risks = []
    for f in doctor.repo_manager.get_source_files():
        rel = doctor.repo_manager.get_relative_path(f)
        code = doctor.repo_manager.read_file(str(f))
        all_risks.extend(doctor.risk_analyzer.analyze_file(rel, code))

    if not all_risks:
        console.print("[green][ok] No high-severity security or logic risks detected![/green]")
        return

    table = Table(title=f"Detected Risks & Vulnerabilities ({len(all_risks)} issues)")
    table.add_column("Severity", style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("File:Line", style="dim")

    for r in all_risks:
        sev_color = "red" if r.severity.value in ("CRITICAL", "HIGH") else "yellow"
        table.add_row(
            f"[{sev_color}]{r.severity.value}[/{sev_color}]",
            r.category.value,
            r.title,
            f"{r.file_path}:{r.line_number or '-'}",
        )

    console.print(table)


@main.command()
@click.option("--repo", "-r", default=".", help="Path to repository root")
@click.option("--base", "-b", default=None, help="Base Git ref or branch to diff against (e.g. main, HEAD~1)")
@click.option("--run-tests/--no-tests", default=True, help="Automatically generate and run tests for impacted components")
@click.option("--export-pr", default=None, help="Path to export GitHub PR comment markdown")
@click.option("--export-html", default=None, help="Path to export HTML report")
def diff(repo, base, run_tests, export_pr, export_html):
    """Inspects git changes (working tree or branch diff) and calculates changeset blast radius."""
    doctor = CodebaseDoctor(repo_path=repo, console=console)

    if not doctor.repo_manager.is_git_repo():
        console.print(f"[bold red][error] Not a git repository:[/] {doctor.repo_root}")
        return

    desc = f"branch diff against '{base}'" if base else "uncommitted changes in working tree"
    console.print(f"[bold cyan][diff] Inspecting git changeset ({desc}) at:[/] {doctor.repo_root}")

    try:
        report, execution = doctor.analyze_diff(base_ref=base, run_tests=run_tests)
    except ValueError as e:
        console.print(f"[bold red][error] {e}[/]")
        return

    if not report.changed_files:
        console.print(f"[bold yellow][info] No changed files detected in git working tree or against '{base or 'HEAD'}'.[/]")
        return

    doctor.reporter.print_terminal_changeset_report(report, execution)

    if export_pr:
        pr_md = doctor.generate_pr_markdown(report, execution)
        pr_path = Path(export_pr)
        pr_path.parent.mkdir(parents=True, exist_ok=True)
        pr_path.write_text(pr_md, encoding="utf-8")
        console.print(f"[green][saved] GitHub PR comment markdown saved to:[/] {export_pr}")

    if export_html:
        doctor.reporter.export_changeset_html(report, Path(export_html), execution)
        console.print(f"[green][saved] HTML report saved to:[/] {export_html}")


if __name__ == "__main__":
    main()
