"""
AI Codebase Doctor - Interactive Streamlit Dashboard
Web interface for Codebase Knowledge Graph, Blast Radius Prediction,
Security Auditing, Graph-RAG Q&A, and Automated Test Execution.
"""

import os
import sys
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add current directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from codebase_doctor.doctor import CodebaseDoctor
from codebase_doctor.llm_provider import get_llm_provider
from codebase_doctor.models import RiskSeverity

# Page configuration
st.set_page_config(
    page_title="AI Codebase Doctor",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title { font-size: 2.2rem; font-weight: 800; color: #38bdf8; margin-bottom: 0.2rem; }
    .sub-title { font-size: 1.1rem; color: #94a3b8; margin-bottom: 1.5rem; }
    .metric-card { background-color: #1e293b; border-radius: 8px; padding: 1rem; border: 1px solid #334155; }
    .tree-box { background-color: #0f172a; padding: 1.2rem; border-radius: 6px; font-family: monospace; color: #4ade80; border: 1px solid #334155; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_doctor(repo_path: str, provider: str, api_key: str = "", model_name: str = ""):
    """Initializes and caches the CodebaseDoctor instance."""
    llm = get_llm_provider(
        provider_name=provider,
        api_key=api_key if api_key else None,
        model_name=model_name if model_name else None,
    )
    doctor = CodebaseDoctor(repo_path=repo_path, llm=llm)
    doctor.scan()
    return doctor


# Sidebar
st.sidebar.title("AI Codebase Doctor")
st.sidebar.markdown("Inspect blast radiuses & safeguard legacy changes.")

repo_choice = st.sidebar.text_input("Repository Path", value="demo_repo")

engine_options = [
    "Groq (Fast Cloud LLM)",
    "Google Gemini",
    "OpenAI (GPT-4o)",
    "Ollama (Local LLM)",
    "Offline Heuristic (No API Key)",
]
engine_key_map = {
    "Groq (Fast Cloud LLM)": "groq",
    "Google Gemini": "gemini",
    "OpenAI (GPT-4o)": "openai",
    "Ollama (Local LLM)": "ollama",
    "Offline Heuristic (No API Key)": "offline",
}

selected_label = st.sidebar.selectbox(
    "AI Engine",
    options=engine_options,
    index=0,
    help="Groq and Gemini offer genuine cloud LLM deep reasoning; Offline uses deterministic AST/Graph rules.",
)
provider_choice = engine_key_map[selected_label]

custom_api_key = ""
custom_model = ""

if provider_choice == "groq":
    has_env = bool(os.getenv("GROQ_API_KEY"))
    custom_model = st.sidebar.selectbox(
        "Groq Model",
        options=[
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
        ],
        index=0,
    )
    with st.sidebar.expander("API Key Configuration", expanded=not has_env):
        user_key_input = st.text_input(
            "Groq API Key",
            value="",
            placeholder="Active from .env" if has_env else "Paste gsk_... key",
            type="password",
            help="By default, reads securely from .env. Only enter here if you want to override it.",
        )
    custom_api_key = user_key_input.strip() if user_key_input.strip() else os.getenv("GROQ_API_KEY", "")
    if custom_api_key:
        source_label = "custom override" if user_key_input.strip() else "secure .env"
        st.sidebar.success(f"[OK] Groq Ready: `{custom_model}` ({source_label})")
    else:
        st.sidebar.warning("[!] No Groq API Key found in .env or input.")

elif provider_choice == "gemini":
    has_env = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    custom_model = st.sidebar.selectbox(
        "Gemini Model",
        options=["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
        index=0,
    )
    with st.sidebar.expander("API Key Configuration", expanded=not has_env):
        user_key_input = st.text_input(
            "Gemini API Key",
            value="",
            placeholder="Active from .env" if has_env else "Paste AI Studio key",
            type="password",
            help="By default, reads securely from .env. Only enter here if you want to override it.",
        )
    custom_api_key = user_key_input.strip() if user_key_input.strip() else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "")
    if custom_api_key:
        source_label = "custom override" if user_key_input.strip() else "secure .env"
        st.sidebar.success(f"[OK] Gemini Ready: `{custom_model}` ({source_label})")
    else:
        st.sidebar.info("[i] Paste your Google AI Studio Gemini API Key in the field above or in .env")

elif provider_choice == "openai":
    has_env = bool(os.getenv("OPENAI_API_KEY"))
    custom_model = st.sidebar.selectbox(
        "OpenAI Model",
        options=["gpt-4o-mini", "gpt-4o"],
        index=0,
    )
    with st.sidebar.expander("API Key Configuration", expanded=not has_env):
        user_key_input = st.text_input(
            "OpenAI API Key",
            value="",
            placeholder="Active from .env" if has_env else "Paste sk-... key",
            type="password",
            help="By default, reads securely from .env. Only enter here if you want to override it.",
        )
    custom_api_key = user_key_input.strip() if user_key_input.strip() else os.getenv("OPENAI_API_KEY", "")
    if custom_api_key:
        source_label = "custom override" if user_key_input.strip() else "secure .env"
        st.sidebar.success(f"[OK] OpenAI Ready: `{custom_model}` ({source_label})")
    else:
        st.sidebar.warning("[!] No OpenAI API Key found in .env or input.")

elif provider_choice == "ollama":
    custom_model = st.sidebar.text_input("Ollama Model", value="llama3")
    ollama_check = get_llm_provider("ollama", model_name=custom_model)
    is_up, status_msg = ollama_check.is_available()
    if is_up:
        st.sidebar.success(f"[OK] {status_msg}")
    else:
        st.sidebar.error(f"[ERR] {status_msg}")

elif provider_choice == "offline":
    st.sidebar.info("Fast deterministic graph & AST traversal without API calls.")

col_rescan1, col_rescan2 = st.sidebar.columns(2)
with col_rescan1:
    if st.button("Full Re-Scan", use_container_width=True):
        st.cache_resource.clear()
        st.session_state.pop("last_inc_scan", None)
        st.rerun()
with col_rescan2:
    if st.button("Incremental", use_container_width=True):
        try:
            doc = load_doctor(repo_choice, provider_choice, custom_api_key, custom_model)
            inc_res = doc.scan(incremental=True)
            st.session_state["last_inc_scan"] = inc_res
            st.rerun()
        except Exception as exc:
            st.sidebar.error(f"[ERR] Incremental scan failed: {exc}")

if "last_inc_scan" in st.session_state:
    res = st.session_state["last_inc_scan"]
    if res.get("changed"):
        st.sidebar.success(f"[OK] Incremental: +{res.get('added',0)} ~{res.get('modified',0)} -{res.get('deleted',0)}")
    else:
        st.sidebar.info(f"[OK] Up-to-date ({res.get('unchanged',0)} files unchanged)")

# Load doctor
try:
    doctor = load_doctor(repo_choice, provider_choice, custom_api_key, custom_model)
    stats = doctor.graph.get_stats()
except Exception as e:
    st.error(f"Failed to scan repository at '{repo_choice}': {e}")
    st.stop()

# Header
st.markdown('<div class="main-title">AI Codebase Doctor</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-title">Active Repository: <code>{doctor.repo_root}</code> | Graph Nodes: <b>{stats["total_nodes"]}</b> | Dependencies: <b>{stats["total_edges"]}</b></div>',
    unsafe_allow_html=True,
)

# Tabs
tab_impact, tab_diff, tab_rag, tab_risks, tab_overview, tab_export = st.tabs([
    "Change Impact & Tests",
    "Git Diff & PR Review",
    "AI Doctor Q&A (Graph-RAG)",
    "Security & Risk Audit",
    "Architecture & Graph",
    "Export Reports",
])

# TAB 1: Change Impact & Blast Radius
with tab_impact:
    st.subheader("Predict Blast Radius of a Code Change")
    st.caption("Select any source file (Python, C/C++/Arduino, JS/TS, Java, Go, SQL, etc.) to calculate its ripple effect across all dependent services.")

    all_source_files = doctor.repo_manager.get_source_files(exclude_tests=True)
    languages_found = doctor.repo_manager.get_languages()
    lang_options = ["All Languages"] + sorted(list(languages_found.keys()))

    col_filter, col_file, col_opt = st.columns([1.5, 3.5, 1.5])
    with col_filter:
        selected_lang = st.selectbox("Language Filter", options=lang_options, index=0)

    with col_file:
        if selected_lang == "All Languages":
            files = [doctor.repo_manager.get_relative_path(f) for f in all_source_files]
        else:
            files = [
                doctor.repo_manager.get_relative_path(f)
                for f in all_source_files
                if doctor.repo_manager.detect_language(str(f)) == selected_lang
            ]

        def format_file_label(rel_p: str) -> str:
            lang = doctor.repo_manager.detect_language(rel_p)
            return f"{rel_p}  [{lang}]"

        if not files:
            st.warning(f"No source files found for language: {selected_lang}")
            selected_file = None
        else:
            selected_file = st.selectbox(
                "Select Modified File",
                options=files,
                format_func=format_file_label,
                index=0,
                help="Choose any source file (Python, C/C++, TS/JS, SQL, etc.) to inspect its architectural blast radius.",
            )
    with col_opt:
        auto_run = st.checkbox("Auto-run Generated Tests", value=True)

    if st.button("Diagnose Change Impact", type="primary", disabled=selected_file is None):
        if selected_file:
            with st.spinner("Analyzing graph blast radius and generating tests..."):
                report = doctor.analyze_change(selected_file)
                st.session_state["single_impact_report"] = report
                st.session_state["single_impact_file"] = selected_file
                if auto_run:
                    test_execution, test_path = doctor.generate_and_run_tests(report)
                    st.session_state["single_test_execution"] = test_execution
                else:
                    st.session_state["single_test_execution"] = None

    if "single_impact_report" in st.session_state and selected_file == st.session_state.get("single_impact_file"):
        report = st.session_state["single_impact_report"]
        test_execution = st.session_state.get("single_test_execution")

        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Blast Radius Score", f"{report.blast_radius_score} / 100")
        with col_m2:
            st.metric("Direct/Indirect Dependents", len(report.affected_components))
        with col_m3:
            st.metric("Impacted Files", len(report.affected_files))

        # Interactive Visual Graph (Item 1)
        st.markdown("### Interactive Blast Radius Force-Directed Graph")
        st.caption("[● Red] **Ground Zero (Modified)** | [● Orange] **Depth 1 (Direct)** | [● Yellow] **Depth 2+ (Transitive)** | [○ Gray] **Surrounding**. Drag nodes, pan/zoom, or hover for cyclomatic complexity and risk flags.")
        graph_html = doctor.generate_visual_graph(report, height=520)
        components.html(graph_html, height=540)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### Potentially Affected Components")
            tree_text = doctor.impact_analyzer.format_tree(report)
            st.code(tree_text, language="text")

            st.markdown("### Risk Areas")
            for r in report.risk_areas:
                st.markdown(f"- **{r}**")

        with c2:
            st.markdown("### Suggested Verification Tests")
            for t in report.suggested_tests:
                st.markdown(f"• ` {t} `")

            if test_execution:
                st.markdown("### Automated Pytest Results")
                status_color = "green" if test_execution.failed == 0 else "red"
                st.markdown(
                    f"**Status**: :{status_color}[{test_execution.passed}/{test_execution.total} Passed] "
                    f"in `{test_execution.duration_sec}s`"
                )

                test_table = [
                    {
                        "Test Function": res.test_name,
                        "Status": "PASS" if res.passed else "FAIL",
                        "Duration": f"{res.duration_sec}s",
                        "Message": res.error_message or "-",
                    }
                    for res in test_execution.results
                ]
                st.dataframe(test_table, use_container_width=True)

# TAB 2: Git Diff & Changeset PR Review
with tab_diff:
    st.subheader("Git Diff & Changeset Blast Radius Review")
    st.caption("Inspect uncommitted working tree changes or diff against a base branch (e.g. main, HEAD~1) to predict the aggregated multi-file blast radius and export a PR comment.")

    is_git = doctor.repo_manager.is_git_repo()
    all_repo_files = [doctor.repo_manager.get_relative_path(f) for f in doctor.repo_manager.get_source_files(exclude_tests=True)]

    if not is_git:
        st.info(
            f"Repository at `{doctor.repo_root}` is not an initialized Git repository. "
            "You can run a **Simulated Multi-File Changeset Analysis** below to inspect the aggregated blast radius across multiple files."
        )
        source_mode = "Simulated Multi-File Changeset"
    else:
        source_mode = st.radio(
            "Changeset Source",
            options=["Git Working Tree Changes", "Git Diff against Base Branch / Ref", "Simulated Multi-File Changeset"],
            index=0,
            horizontal=True,
        )

    base_ref_val = None
    simulated_files = None

    if source_mode == "Git Working Tree Changes":
        st.caption("Inspecting uncommitted working tree changes, staged commits, and untracked files (falling back to HEAD~1 if clean).")
    elif source_mode == "Git Diff against Base Branch / Ref":
        col_b1, col_b2 = st.columns([3, 1])
        with col_b1:
            base_ref_val = st.text_input("Base Git Ref / Branch", value="main", help="e.g. main, master, HEAD~1, origin/main")
        with col_b2:
            st.caption("Diffs current working tree and commits against specified base branch.")
    else:
        st.markdown("**Simulate a Multi-File Pull Request Changeset:**")
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            if st.button("Preset: Payment + Order", key="preset_pay_order"):
                st.session_state["sim_files_selected"] = [f for f in ["payment_service.py", "order_service.py"] if f in all_repo_files]
        with col_p2:
            if st.button("Preset: Auth + Serial Bridge", key="preset_auth_serial"):
                st.session_state["sim_files_selected"] = [f for f in ["auth_service.py", "esp32/serial_bridge.ino"] if f in all_repo_files]
        with col_p3:
            if st.button("Preset: Frontend + DB Schema", key="preset_fe_db"):
                st.session_state["sim_files_selected"] = [f for f in ["frontend/payment_dashboard.js", "db/schema.sql"] if f in all_repo_files]

        default_sim = st.session_state.get("sim_files_selected", all_repo_files[:2] if len(all_repo_files) >= 2 else all_repo_files)
        simulated_files = st.multiselect(
            "Select Modified Files in Simulated Changeset",
            options=all_repo_files,
            default=[f for f in default_sim if f in all_repo_files],
            help="Select 2 or more files to simulate a multi-file PR changeset and observe aggregated blast radius calculation.",
        )

    col_btn, col_opt = st.columns([2, 4])
    with col_opt:
        diff_auto_run = st.checkbox("Auto-run Verification Tests for Changeset", value=True, key="diff_auto_run")
    with col_btn:
        btn_label = "Analyze Simulated Changeset" if source_mode == "Simulated Multi-File Changeset" else "Analyze Git Changeset"
        if st.button(btn_label, type="primary", key="btn_diff_analyze"):
            with st.spinner("Analyzing changeset and calculating aggregated blast radius..."):
                try:
                    if source_mode == "Simulated Multi-File Changeset":
                        cs_report, cs_exec = doctor.analyze_diff(
                            run_tests=diff_auto_run,
                            changed_files=simulated_files or [],
                        )
                        st.session_state["changeset_base"] = "simulation"
                    else:
                        cs_report, cs_exec = doctor.analyze_diff(
                            base_ref=base_ref_val,
                            run_tests=diff_auto_run,
                        )
                        st.session_state["changeset_base"] = base_ref_val

                    st.session_state["changeset_report"] = cs_report
                    st.session_state["changeset_exec"] = cs_exec
                except ValueError as err:
                    st.error(f"Git Diff Error: {err}")
                except Exception as ex:
                    st.error(f"Analysis Error: {ex}")

    if "changeset_report" in st.session_state:
        cs_report = st.session_state["changeset_report"]
        cs_exec = st.session_state.get("changeset_exec")
        cs_base = st.session_state.get("changeset_base")

        if not cs_report.changed_files:
            st.info(f"No changed files detected in git working tree or against '{cs_base or 'HEAD'}'.")
        else:
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.metric("Modified Files", len(cs_report.changed_files))
                with col_m2:
                    st.metric("Aggregated Blast Radius", f"{cs_report.blast_radius_score} / 100")
                with col_m3:
                    st.metric("Downstream Dependents", len(cs_report.affected_components))
                with col_m4:
                    st.metric("Downstream Files", len(cs_report.affected_files))

                with st.expander(f"View {len(cs_report.changed_files)} Modified Files & Git Diff"):
                    st.markdown("**Changed Files in Changeset:**")
                    for cf in cs_report.changed_files:
                        c_lang = doctor.repo_manager.detect_language(cf)
                        st.markdown(f"- `{cf}` `[{c_lang}]`")
                    diff_text = doctor.repo_manager.get_git_diff(base_ref=cs_base)
                    if diff_text:
                        st.markdown("**Git Diff Output:**")
                        st.code(diff_text[:5000] + ("\n... (truncated)" if len(diff_text) > 5000 else ""), language="diff")

                # Interactive Visual Graph for Changeset (Item 1 & Item 2)
                st.markdown("### Interactive Changeset Blast Radius Graph")
                st.caption("[● Red] **Red = Modified Files in PR (Ground Zero)** | [● Orange] **Orange = Direct Dependents** | [● Yellow] **Yellow = Transitive Dependents** | [○ Gray] **Gray = Surrounding**")
                cs_graph_html = doctor.generate_visual_graph(cs_report, height=520)
                components.html(cs_graph_html, height=540)

                col_c1, col_c2 = st.columns([1, 1])
                with col_c1:
                    st.markdown("### Combined Blast Radius Tree")
                    tree_str = doctor.impact_analyzer.format_changeset_tree(cs_report)
                    st.code(tree_str, language="text")

                    st.markdown("### Aggregated Risk Areas")
                    if cs_report.risk_areas:
                        for r in cs_report.risk_areas:
                            st.markdown(f"- **{r}**")
                    else:
                        st.markdown("- *No high-severity logic or security risks detected.*")

                with col_c2:
                    st.markdown("### Suggested Verification Tests")
                    for t in cs_report.suggested_tests:
                        st.markdown(f"• ` {t} `")

                    if cs_exec:
                        st.markdown("### Automated Pytest Results")
                        status_color = "green" if cs_exec.failed == 0 else "red"
                        st.markdown(
                            f"**Status**: :{status_color}[{cs_exec.passed}/{cs_exec.total} Passed] in `{cs_exec.duration_sec}s`"
                        )
                        test_table = [
                            {
                                "Test Function": res.test_name,
                                "Status": "PASS" if res.passed else "FAIL",
                                "Duration": f"{res.duration_sec}s",
                                "Message": res.error_message or "-",
                            }
                            for res in cs_exec.results
                        ]
                        st.dataframe(test_table, use_container_width=True)

                st.markdown("---")
                st.markdown("### Export GitHub PR Comment Markdown")
                pr_md = doctor.generate_pr_markdown(cs_report, cs_exec)
                col_d_btn, col_d_view = st.columns([1.5, 3.5])
                with col_d_btn:
                    st.download_button(
                        label="Download PR Comment (Markdown)",
                        data=pr_md,
                        file_name="pr_blast_radius_report.md",
                        mime="text/markdown",
                        type="primary",
                    )
                with col_d_view:
                    with st.expander("Preview GitHub PR Comment Markdown"):
                        st.code(pr_md, language="markdown")

# TAB 2: AI Doctor Q&A
with tab_rag:
    st.subheader("Ask AI Codebase Doctor")
    st.caption("Ask architectural questions like: 'If I modify this authentication function, what else could break?'")

    sample_questions = [
        "If I modify this authentication function, what else could break?",
        "Explain how payment_service interacts with order_service and refunds.",
        "What are the highest risk areas in our payment processing flow?",
    ]
    selected_sample = st.selectbox("Or choose a sample question:", ["(Custom Query)"] + sample_questions)

    user_query = st.text_input(
        "Question",
        value="" if selected_sample == "(Custom Query)" else selected_sample,
        placeholder="e.g. If I change PaymentService, what will break?",
    )

    if st.button("Ask Doctor", type="primary"):
        if user_query.strip():
            engine_name = type(doctor.llm).__name__
            with st.spinner(f"Traversing knowledge graph & generating architectural answer with {engine_name}..."):
                resp = doctor.ask(user_query)
                st.caption(f"Engine: **{engine_name}** | Graph-RAG Topology Augmented")
                st.markdown(resp["answer"])

                with st.expander("Retrieved Graph Nodes & Context (Ground Truth)"):
                    st.write("**Matched Nodes:**", resp.get("retrieved_nodes", []))
                    st.caption(resp.get("context_summary", ""))
                    if resp.get("context_block"):
                        st.text_area("Prompt Context Injected into Model", resp["context_block"], height=220)

# TAB 3: Security & Risk Audit
with tab_risks:
    st.subheader("Polyglot Security & Logic Risk Scanner")
    st.caption("Audits codebases across Python, C/C++/Arduino, JavaScript/TypeScript, SQL, and Shell for vulnerabilities, memory bugs, and logic flaws.")

    all_risks = []
    for f in doctor.repo_manager.get_source_files():
        rel = doctor.repo_manager.get_relative_path(f)
        code = doctor.repo_manager.read_file(str(f))
        all_risks.extend(doctor.risk_analyzer.analyze_file(rel, code))

    if not all_risks:
        st.success("No critical security or logic risks detected!")
    else:
        st.warning(f"Found {len(all_risks)} potential risks across the codebase.")
        risk_data = [
            {
                "Severity": r.severity.value,
                "Category": r.category.value,
                "Title": r.title,
                "File": r.file_path,
                "Language": doctor.repo_manager.detect_language(r.file_path),
                "Line": r.line_number or "-",
                "Remediation": r.remediation,
            }
            for r in all_risks
        ]
        st.dataframe(risk_data, use_container_width=True)

# TAB 4: Architecture & Graph Overview
with tab_overview:
    st.subheader("Codebase Graph Architecture")

    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric("Source Files", stats["total_files"])
    with col_s2:
        st.metric("Symbols (Classes/Funcs)", stats["total_nodes"])
    with col_s3:
        st.metric("Edges (Calls/Imports)", stats["total_edges"])
    with col_s4:
        st.metric("Circular Cycles", stats["circular_dependencies_count"])

    # Polyglot Language Breakdown
    repo_langs = doctor.repo_manager.get_languages()
    if repo_langs:
        st.markdown("### Polyglot Language Distribution")
        lang_cols = st.columns(min(len(repo_langs), 6))
        for i, (lang_name, count) in enumerate(list(repo_langs.items())[:6]):
            with lang_cols[i % len(lang_cols)]:
                pct = round(count / max(stats["total_files"], 1) * 100, 1)
                st.metric(label=lang_name, value=f"{count} files", delta=f"{pct}%")

    pagerank = doctor.graph.compute_pagerank()
    if pagerank:
        st.markdown("### Top Architectural Core Components (PageRank Centrality)")
        top_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:10]
        pr_data = [{"Component": n, "PageRank Score": round(s, 4)} for n, s in top_nodes]
        st.dataframe(pr_data, use_container_width=True)

    st.markdown("### Interactive Global Architecture Knowledge Graph")
    st.caption("Force-directed interactive architecture graph with nodes sized by PageRank centrality and colored by language. Drag, pan, zoom, or search components.")
    arch_graph_html = doctor.generate_architecture_graph(height=600)
    components.html(arch_graph_html, height=620)

# TAB 5: Export
with tab_export:
    st.subheader("Export Executive Health Report")
    all_export_files = [doctor.repo_manager.get_relative_path(f) for f in doctor.repo_manager.get_source_files(exclude_tests=True)]
    if all_export_files:
        export_target = st.selectbox(
            "Report Target",
            options=all_export_files,
            format_func=lambda x: f"{x}  [{doctor.repo_manager.detect_language(x)}]",
            index=0,
        )

        if st.button("Generate Markdown & HTML Exports"):
            rep = doctor.analyze_change(export_target)
            exec_res = None
            try:
                exec_res, _ = doctor.generate_and_run_tests(rep)
            except Exception:
                pass
            md = doctor.reporter.generate_markdown(rep, exec_res)

            st.download_button(
                label="Download Markdown Report",
                data=md,
                file_name=f"codebase_doctor_report_{Path(export_target).stem}.md",
                mime="text/markdown",
            )
            st.success("Report ready for export!")
    else:
        st.info("No source files available for report export.")
