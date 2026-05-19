import streamlit as st
from dotenv import load_dotenv
from graph.orchestrator import graph
from rag.ingestion import ingest_static_documents

load_dotenv()

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

# ── Input form ──────────────────────────────────────────────────────────────
with st.form("assessment_form"):
    col1, col2, col3 = st.columns(3)
    with col1:
        target = st.text_input("Drug Target *", placeholder="e.g., PD-L1, IL-6R, VEGF")
    with col2:
        company = st.text_input("Company *", placeholder="e.g., Genentech, BioNTech")
    with col3:
        indication = st.text_input("Indication (optional)", placeholder="e.g., NSCLC, rheumatoid arthritis")

    submitted = st.form_submit_button("Run Assessment", type="primary", use_container_width=True)

if submitted and not (target and company):
    st.warning("Please provide both a target name and a company name.")
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
            "bio_findings": [],
            "trial_findings": [],
            "errors": [],
            "report": None,
        })

        status.update(label="Assessment complete", state="complete")

    report = result.get("report", {})
    errors = result.get("errors", [])

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
