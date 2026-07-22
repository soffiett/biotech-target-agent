import copy
import re
import time
from pathlib import Path
import anthropic
from pydantic import ValidationError
from rag.vectorstore import query_knowledge_base
from graph.state import TargetAssessmentState
from models.schemas import AssessmentReport
from config import (
    SYNTHESIS_MODEL,
    SYNTHESIS_MAX_TOKENS,
    SYNTHESIS_TEMPERATURE,
    RAG_TOP_K,
    SYNTHESIS_SYSTEM_PROMPT,
)
from logger import get_logger
from observability.tracker import get_tracker

log = get_logger(__name__)

_client = anthropic.Anthropic()

# Loaded once at import time — injected into every synthesis call so the agent
# always knows the section-by-section writing standard it is being evaluated against.
_RAG_DATA_DIR = Path(__file__).parent.parent.parent / "rag" / "data"
_SKILL_PATH = _RAG_DATA_DIR / "synthesis_skill.md"
_SYNTHESIS_SKILL = _SKILL_PATH.read_text(encoding="utf-8") if _SKILL_PATH.exists() else ""

# The modality decision needs both guides compared against each other every time —
# retrieving one or the other via similarity search would gamble on which modality
# "wins" the search before the model has even assessed the target, so both are
# always injected directly rather than left to RAG_TOP_K similarity ranking.
_MODALITY_GUIDES = "\n\n".join(
    p.read_text(encoding="utf-8")
    for p in (_RAG_DATA_DIR / "large_molecule_druggability.md", _RAG_DATA_DIR / "small_molecule_druggability.md")
    if p.exists()
)


def _resolve_refs(schema: dict) -> dict:
    """
    Inline $defs/$ref entries produced by Pydantic so the schema is
    self-contained. The Anthropic tool API does not support $ref references.
    """
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def _inline(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                resolved = {k: v for k, v in defs.get(ref_name, obj).items()
                            if k != "title"}
                return resolved
            return {k: _inline(v) for k, v in obj.items() if k != "title"}
        if isinstance(obj, list):
            return [_inline(i) for i in obj]
        return obj

    return _inline(schema)


def _build_report_tool_schema() -> dict:
    """
    Derive the tool input_schema from AssessmentReport.
    target and company are injected from LangGraph state; recommendation is
    derived deterministically from confidence_score (see _derive_recommendation)
    rather than left to the model — none of the three are filled by the LLM.
    """
    raw = AssessmentReport.model_json_schema()
    schema = _resolve_refs(raw)
    for field in ("target", "company", "recommendation"):
        schema.get("properties", {}).pop(field, None)
        if field in schema.get("required", []):
            schema["required"].remove(field)
    return schema


# Bands mirror confidence_score's own documented calibration (models/schemas.py)
# and synthesis_skill.md's calibration anchors — the single authoritative mapping
# from the numeric score to the categorical recommendation, so the two fields
# can't drift apart the way they were observed to (e.g. confidence_score=8.0
# paired with recommendation="Moderate" from letting the model pick both).
def _derive_recommendation(confidence_score: float) -> str:
    if confidence_score >= 7.5:
        return "Strong"
    if confidence_score >= 5.0:
        return "Moderate"
    if confidence_score >= 3.5:
        return "Weak"
    return "Against"


# Tool schema is generated from the Pydantic model — descriptions stay in one place.
REPORT_TOOL = {
    "name": "create_assessment_report",
    "description": "Submit the final structured assessment of the drug target.",
    "input_schema": _build_report_tool_schema(),
}


# Order (highest evidentiary weight first) and section labels for grouping bio_findings
# by evidence_type — lets the synthesis model see which tier each piece of evidence
# came from instead of one undifferentiated blob.
_EVIDENCE_SECTION_ORDER = [
    ("agent_narrative", "Biology Agent Analysis"),
    ("human_genetics", "Human Genetics (GWAS / OpenTargets)"),
    ("rare_variant", "Rare Variants (ClinVar / OMIM)"),
    ("crispr_dependency", "CRISPR Dependency (DepMap)"),
    ("tissue_expression", "Tissue Expression (HPA / GTEx)"),
    ("pathway_biology", "Pathway Biology (Reactome)"),
    ("literature", "Literature (PubMed)"),
    ("preprint", "Preprints (bioRxiv)"),
    ("company_disclosure", "Company Disclosures / Web"),
]


def _group_bio_context(bio_findings: list[dict]) -> str:
    """Group biology findings into labeled sections by evidence_type, ordered by weight."""
    by_type: dict[str, list[str]] = {}
    for f in bio_findings:
        if not f.get("content"):
            continue
        by_type.setdefault(f.get("evidence_type", "agent_narrative"), []).append(f["content"])

    sections = []
    for etype, label in _EVIDENCE_SECTION_ORDER:
        items = by_type.pop(etype, None)
        if items:
            sections.append(f"### {label}\n" + "\n\n".join(items))
    for etype, items in by_type.items():  # any evidence_type not in the fixed order above
        sections.append(f"### {etype}\n" + "\n\n".join(items))

    return "\n\n".join(sections) or "No biology findings available."


# Sections with prose content and their target word limits from synthesis_skill.md
_SECTION_WORD_LIMITS = {
    "biology_rationale": 200,
    "druggability_assessment": 150,
    "clinical_precedent": 200,
    "competitive_landscape": 150,
    "confidence_reasoning": 100,
}


def _warn_verbose_sections(report: dict, target: str, company: str) -> None:
    for section, limit in _SECTION_WORD_LIMITS.items():
        content = report.get(section, "")
        if not isinstance(content, str):
            continue
        word_count = len(content.split())
        if word_count > limit:
            log.warning(
                f"[{target}/{company}] Section '{section}' is {word_count} words "
                f"(limit {limit}) — synthesis may be too verbose; judge input will be large"
            )


def _normalize_key_risks(raw: dict) -> dict:
    """
    Coerce key_risks into a list[str] if the model returned a single string —
    an observed failure mode despite the tool schema requiring an array. Left
    uncorrected, this fails AssessmentReport validation and, worse, silently
    survives into the raw fallback report, where `for risk in key_risks`
    iterates the string character-by-character in the UI.
    """
    risks = raw.get("key_risks")
    if not isinstance(risks, str):
        return raw

    items = [i.strip() for i in re.split(r"\n?\d+\.\s+", risks) if i.strip()]
    return {**raw, "key_risks": items or [risks]}


def synthesis_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    bio_findings = state.get("bio_findings", [])
    trial_findings = state.get("trial_findings", [])

    # Pull relevant frameworks from the knowledge base (modality guides are injected
    # directly below, not retrieved here — see _MODALITY_GUIDES)
    rag_results = query_knowledge_base(
        f"drug target validation {target} safety immunogenicity clinical development phase success rate",
        n_results=RAG_TOP_K,
    )
    rag_context = "\n\n".join(
        f"[{r['source']}]\n{r['content']}" for r in rag_results
    ) or "No additional context retrieved."

    bio_context = _group_bio_context(bio_findings)

    trial_context = "\n\n".join(
        f["content"] for f in trial_findings if f.get("content")
    ) or "No clinical trial findings available."

    skill_block = f"\n\n## Report Writing Standard\n{_SYNTHESIS_SKILL}" if _SYNTHESIS_SKILL else ""
    modality_block = f"\n\n## Modality Reference (compare both before choosing)\n{_MODALITY_GUIDES}" if _MODALITY_GUIDES else ""

    user_message = f"""Synthesize the following research to assess: **{target}** (Company: {company})

## Biology Research
{bio_context}

## Clinical Trial Landscape
{trial_context}
{skill_block}
{modality_block}

## Knowledge Base: Target Validation Frameworks
{rag_context}

Now create the structured assessment report. Follow the Report Writing Standard above for every section."""

    _t0 = time.perf_counter()
    response = _client.messages.create(
        model=SYNTHESIS_MODEL,
        max_tokens=SYNTHESIS_MAX_TOKENS,
        temperature=SYNTHESIS_TEMPERATURE,
        system=SYNTHESIS_SYSTEM_PROMPT,
        tools=[REPORT_TOOL],
        tool_choice={"type": "tool", "name": "create_assessment_report"},
        messages=[{"role": "user", "content": user_message}],
    )
    _latency = time.perf_counter() - _t0

    if response.stop_reason == "max_tokens":
        log.error(
            f"[{target}/{company}] Synthesis hit max_tokens — "
            "report tool call was truncated and cannot be used"
        )
        return {
            "report": {},
            "errors": [
                "Synthesis agent hit token limit before completing the report. "
                "Try a shorter indication or reduce context size."
            ],
        }

    report = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_assessment_report":
            normalized_input = _normalize_key_risks(block.input)
            try:
                confidence_score = float(normalized_input.get("confidence_score", 0))
            except (TypeError, ValueError):
                confidence_score = 0.0
            recommendation = _derive_recommendation(confidence_score)
            try:
                validated = AssessmentReport.model_validate({
                    **normalized_input,
                    "target": target,
                    "company": company,
                    "recommendation": recommendation,
                })
                report = validated.model_dump()
                log.info(
                    f"[{target}/{company}] Synthesis done — "
                    f"recommendation={report['recommendation']} "
                    f"confidence={report['confidence_score']}"
                )
            except ValidationError as e:
                log.warning(
                    f"[{target}/{company}] Report validation failed: {e} — using raw output")
                report = {
                    **normalized_input,
                    "target": target,
                    "company": company,
                    "recommendation": recommendation,
                }
                # Whatever else failed validation, key_risks must still be a list —
                # the UI iterates it directly and a stray string renders as garbage
                # (one st.warning() per character).
                if not isinstance(report.get("key_risks"), list):
                    report["key_risks"] = [str(report.get("key_risks", ""))] if report.get("key_risks") else []
            break

    if not report:
        log.error(f"[{target}/{company}] Synthesis failed — no report returned")
    else:
        _warn_verbose_sections(report, target, company)

    tracker = get_tracker()
    if tracker:
        tracker.record_node(
            "synthesis",
            model=SYNTHESIS_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=_latency,
            error=not report,
        )

    return {"report": report}
