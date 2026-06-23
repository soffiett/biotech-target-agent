import streamlit as st
from dotenv import load_dotenv

# Must load env vars before importing any module that creates an Anthropic client
load_dotenv()

from graph.orchestrator import graph
from rag.ingestion import ingest_static_documents
from tools.query_parser import parse_query

st.set_page_config(
    page_title="Biotech Target Assessor",
    page_icon="🔬",
    layout="wide",
)

st.title("Biotech Target Assessment Agent")
st.caption(
    "Multi-agent system that evaluates whether a drug target is likely to yield "
    "a successful large molecule therapeutic."
)


@st.cache_resource(show_spinner="Loading knowledge base...")
def init_rag() -> None:
    ingest_static_documents()


init_rag()

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
        parsed = parse_query(raw_query)

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
    with st.status("Running multi-agent assessment...", expanded=True) as status:
        st.write("Biology agent searching PubMed and web...")
        st.write("Clinical trial agent searching ClinicalTrials.gov...")

        result = graph.invoke({
            "target": target,
            "company": company,
            "indication": indication or "not specified",
            "prefetch_context": {},
            "bio_findings": [],
            "trial_findings": [],
            "errors": [],
            "report": None,
            "quality_assessment": None,
            "rerun_count": 0,
            "judge_critique": None,
        })

        status.update(label="Assessment complete", state="complete")

    report = result.get("report", {})
    errors = result.get("errors", [])
    quality = result.get("quality_assessment", {})

    if not report:
        st.error("No report was generated. Check your API keys and try again.")
        st.stop()

    # ── Report header ────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"Assessment: {target} — {company}")

    score = report.get("confidence_score", 0)
    rec = report.get("recommendation", "N/A")
    rec_color = {"Strong": "green", "Moderate": "blue", "Weak": "orange", "Against": "red"}.get(rec, "gray")

    col1, col2, col3 = st.columns(3)
    col1.metric("Confidence Score", f"{score:.1f} / 10")
    col2.metric("Recommendation", rec)
    col3.metric("Indication", indication or "General")

    st.info(report.get("recommendation_summary", ""))

    # ── Report quality panel ─────────────────────────────────────────────────
    if quality and "error" not in quality:
        overall_q = quality.get("overall_quality", 0)
        q_color = "green" if overall_q >= 4 else "orange" if overall_q >= 3 else "red"
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

    # ── Detailed sections ────────────────────────────────────────────────────
    with st.expander("Biology Rationale", expanded=True):
        st.write(report.get("biology_rationale", ""))

    with st.expander("Large Molecule Druggability"):
        st.write(report.get("druggability_assessment", ""))

    with st.expander("Clinical Precedent"):
        st.write(report.get("clinical_precedent", ""))

    with st.expander("Competitive Landscape"):
        st.write(report.get("competitive_landscape", ""))

    with st.expander("Key Risks"):
        for risk in report.get("key_risks", []):
            st.warning(risk)

    with st.expander("Confidence Score Reasoning"):
        st.write(report.get("confidence_reasoning", ""))

    if errors:
        with st.expander("Warnings / Errors"):
            for err in errors:
                st.error(err)
