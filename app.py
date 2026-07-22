import streamlit as st
from dotenv import load_dotenv

# Must load env vars before importing any module that creates an Anthropic client
load_dotenv()

from graph.orchestrator import graph
from graph.state import make_initial_state
from rag.ingestion import ingest_static_documents
from tools.query_parser import parse_query
from tools.followup import ask_followup
from observability.tracker import start_run

st.set_page_config(
    page_title="TRACE",
    page_icon="🔬",
    layout="wide",
)

# Short display labels for the progress status line — keyed by evidence_type
# (see models/schemas.py EvidenceType) so this stays in sync with whatever
# tools biology_node actually calls, instead of a hardcoded source list.
_EVIDENCE_SOURCE_LABELS = {
    "human_genetics": "GWAS",
    "rare_variant": "ClinVar/OMIM",
    "crispr_dependency": "DepMap",
    "tissue_expression": "HPA/GTEx",
    "pathway_biology": "Reactome",
    "literature": "PubMed",
    "preprint": "bioRxiv",
    "company_disclosure": "web",
}

st.title("TRACE: Target Ranking via Agentic Corroboration of Evidence")
st.caption(
    "Multi-agent system that evaluates whether a drug target is likely to yield "
    "a successful therapeutic, and which modality (small molecule, large molecule, "
    "or other) fits it best."
)


@st.cache_resource(show_spinner="Loading knowledge base...")
def init_rag() -> None:
    ingest_static_documents()


init_rag()

st.session_state.setdefault("assessment", None)
st.session_state.setdefault("followup_history", [])

# ── Input ───────────────────────────────────────────────────────────────────
st.write("Describe the target in your own words, or fill in the fields directly.")

raw_query = st.text_area(
    "Free-form query",
    placeholder=(
        "e.g. 'Assess Genentech's antibody targeting PD-L1 for non-small cell lung cancer'\n"
        "or 'Is TROP2 a good target for an ADC in triple-negative breast cancer? Company: Gilead'"
    ),
    height=90,
    label_visibility="collapsed",
)

parsed: dict = {}
if raw_query.strip():
    with st.spinner("Parsing query..."):
        parsed = parse_query(raw_query).model_dump()

    if parsed.get("confidence") == "low":
        st.caption("Some fields couldn't be inferred — please review below.")

# Editable fields pre-filled from parsed query (or blank for direct entry)
with st.form("assessment_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        target = st.text_input("Drug Target *", value=parsed.get("target", ""), placeholder="e.g., PD-L1")
    with col2:
        company = st.text_input("Company *", value=parsed.get("company", ""), placeholder="e.g., Genentech")
    with col3:
        indication = st.text_input("Indication (optional)", value=parsed.get("indication", ""), placeholder="e.g., NSCLC")

    submitted = st.form_submit_button("Run Assessment", type="primary", use_container_width=True)

if submitted and not (target and company):
    st.warning("Target and Company are required. Edit the fields above or refine your query.")
    st.stop()

# ── Run assessment ───────────────────────────────────────────────────────────
if submitted and target and company:
    # Clear prior session so report and follow-up start fresh
    st.session_state["followup_history"] = []
    st.session_state["assessment"] = None

    tracker = start_run(target, company, indication)
    initial_state = make_initial_state(target, company, indication)
    result = dict(initial_state)

    with st.status("Running multi-agent assessment...", expanded=True) as status:
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, update in event.items():
                for key, val in update.items():
                    if key in ("bio_findings", "trial_findings", "errors") and isinstance(val, list):
                        result[key] = result.get(key, []) + val
                    else:
                        result[key] = val

                if node_name == "prefetch":
                    ot = update.get("prefetch_context", {}).get("opentargets", {})
                    n_drugs = len(ot.get("known_drugs", []))
                    n_diseases = len(ot.get("top_diseases", []))
                    st.write(
                        f"Prefetch: OpenTargets returned {n_drugs} clinical candidate(s), "
                        f"{n_diseases} disease association(s) — research focus set"
                    )
                elif node_name == "biology":
                    rc = update.get("rerun_count", 1)
                    if rc > 1:
                        critique = result.get("judge_critique", {})
                        score = critique.get("biology_score", "?") if critique else "?"
                        st.write(
                            f"Biology re-run triggered (previous score: {score}/5) — "
                            "searching for gaps identified by judge"
                        )
                    else:
                        findings = update.get("bio_findings", [])
                        n = len(findings)
                        sources = dict.fromkeys(
                            _EVIDENCE_SOURCE_LABELS[f["evidence_type"]]
                            for f in findings
                            if f.get("evidence_type") in _EVIDENCE_SOURCE_LABELS
                        )
                        sources_str = ", ".join(sources) or "no sources returned data"
                        st.write(f"Biology agent: {n} finding(s) from {sources_str}")
                elif node_name == "clinical_trials":
                    n = len(update.get("trial_findings", []))
                    st.write(f"Clinical trial agent: {n} finding(s) from ClinicalTrials.gov")
                elif node_name == "synthesis":
                    rep = update.get("report") or {}
                    rec = rep.get("recommendation", "")
                    score = rep.get("confidence_score", "")
                    st.write(f"Synthesis complete — {rec}, confidence {score}/10")
                elif node_name == "judge":
                    qa = update.get("quality_assessment") or {}
                    overall = qa.get("overall_quality", "?")
                    critique = update.get("judge_critique")
                    msg = f"Judge: overall report quality {overall}/5"
                    if critique:
                        msg += (
                            f" — biology scored {critique['biology_score']}/5, "
                            "re-running with targeted critique"
                        )
                    st.write(msg)

        status.update(label="Assessment complete", state="complete")

    if not result.get("report"):
        st.error("No report was generated. Check your API keys and try again.")
        st.stop()

    tracker.finalize(result.get("report", {}), rerun_count=result.get("rerun_count", 0))
    tracker.save()

    # Persist to session state — report display and follow-up panel read from
    # here on every subsequent Streamlit re-run (e.g. chat input submissions).
    st.session_state["assessment"] = {
        "report":    result.get("report", {}),
        "errors":    result.get("errors", []),
        "quality":   result.get("quality_assessment", {}),
        "target":    target,
        "company":   company,
        "indication": indication,
    }

# ── Report display and follow-up (persists across chat re-runs) ──────────────
if st.session_state.get("assessment"):
    a = st.session_state["assessment"]
    report    = a["report"]
    errors    = a["errors"]
    quality   = a["quality"]
    target    = a["target"]
    company   = a["company"]
    indication = a["indication"]

    # ── Report header ────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"Assessment: {target} — {company}")

    score = report.get("confidence_score", 0)
    rec = report.get("recommendation", "N/A")

    col1, col2, col3 = st.columns(3)
    col1.metric("Confidence Score", f"{score:.1f} / 10")
    col2.metric("Recommendation", rec)
    col3.metric("Indication", indication or "General")

    st.info(report.get("recommendation_summary", ""))

    # ── Detailed sections ────────────────────────────────────────────────────
    with st.expander("Biology Rationale", expanded=True):
        st.write(report.get("biology_rationale", ""))
    with st.expander("Druggability & Modality Assessment"):
        st.write(report.get("druggability_assessment", ""))
    with st.expander("Clinical Precedent"):
        st.write(report.get("clinical_precedent", ""))
    with st.expander("Competitive Landscape"):
        st.write(report.get("competitive_landscape", ""))
    with st.expander("Key Risks"):
        risks = report.get("key_risks", [])
        if isinstance(risks, str):
            # Defensive: a malformed report can carry key_risks as a single string —
            # iterating it directly would render one st.warning() per character.
            risks = [risks] if risks else []
        for risk in risks:
            st.warning(risk)
    with st.expander("Confidence Score Reasoning"):
        st.write(report.get("confidence_reasoning", ""))

    if errors:
        with st.expander("Warnings / Errors"):
            for err in errors:
                st.error(err)

    # ── Report quality panel (transparency signal, shown last) ──────────────
    if quality and "error" not in quality:
        overall_q = quality.get("overall_quality", 0)
        q_label = {5: "Excellent", 4: "Good", 3: "Adequate", 2: "Weak", 1: "Poor"}.get(overall_q, "")

        with st.expander(f"Report Quality: {overall_q}/5 — {q_label}", expanded=False):
            qcol1, qcol2 = st.columns(2)
            qcol1.metric("Strongest section", quality.get("strongest_section", "—"))
            qcol2.metric("Weakest section", quality.get("weakest_section", "—"))
            st.caption("Top improvement:")
            st.warning(quality.get("top_improvement", ""))
            st.caption("Section scores:")
            for s in quality.get("section_scores", []):
                score_bar = "█" * s["score"] + "░" * (5 - s["score"])
                st.markdown(f"**{s['section']}** `{score_bar}` {s['score']}/5 — {s['reasoning']}")
                for issue in s.get("issues", []):
                    st.caption(f"  ⚠ {issue}")

    # ── Follow-up Q&A ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Ask a Follow-up")
    st.caption(
        "Answers are grounded in this assessment report only — not medical or investment advice."
    )

    history = st.session_state.setdefault("followup_history", [])

    for msg in history:
        st.chat_message(msg["role"]).write(msg["content"])

    question = st.chat_input("Ask a question about this report...")
    if question:
        st.chat_message("user").write(question)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = ask_followup(
                    question=question,
                    report=report,
                    target=target,
                    company=company,
                    indication=indication,
                    history=history,
                )
            st.write(answer)
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
