"""
Level 2 Evaluation — LLM-as-Judge

Uses Claude Sonnet to score each section of the assessment report
against a structured rubric. Triggered automatically on Level 1 failures
and run standalone for novel targets with no ground truth.
"""

import time
import anthropic
from config import EVAL_JUDGE_MODEL
from logger import get_logger
from observability.tracker import get_tracker

log = get_logger(__name__)

_client = anthropic.Anthropic()

# Sections to evaluate and what good looks like for each
RUBRIC = {
    "biology_rationale": (
        "Evaluate the biology rationale section:\n"
        "- Does it cite specific evidence (named studies, genetic associations, expression data)?\n"
        "- Does it distinguish strong vs weak evidence?\n"
        "- Does it address disease mechanism, not just target biology in isolation?\n"
        "- Does it acknowledge gaps or uncertainties where they exist?"
    ),
    "druggability_assessment": (
        "Evaluate the druggability assessment section. This assessment is modality-agnostic — it "
        "should not assume large molecule or small molecule going in:\n"
        "- Does it determine which modality (small molecule, large molecule, or other e.g. PROTAC, "
        "oligonucleotide) the target's biology actually supports (druggable pocket for small "
        "molecule; extracellular/cell-surface/secreted for large molecule)?\n"
        "- Does it state which modality the company is actually pursuing, and whether that choice "
        "fits the target's biology — flagging a mismatch clearly if one exists?\n"
        "- Does it recommend an appropriate format within the fitting modality (e.g. mAb/bispecific/"
        "ADC for large molecule; kinase inhibitor/PROTAC for small molecule)?\n"
        "- Does it consider PK/pharmacology relevant to the modality in play (TMDD/tissue penetration "
        "for large molecule; oral bioavailability/CYP450 for small molecule)?\n"
        "- Is the assessment specific to this target, not generic?"
    ),
    "clinical_precedent": (
        "Evaluate the clinical precedent section:\n"
        "- Does it accurately describe the clinical stage (Phase 1/2/3) of relevant programs?\n"
        "- Does it mention both successes AND failures for this target or pathway?\n"
        "- Does it draw the correct conclusions from the clinical data?\n"
        "- Is it current (not missing major recent trial results)?"
    ),
    "competitive_landscape": (
        "Evaluate the competitive landscape section:\n"
        "- Does it identify the main competitors for this target?\n"
        "- Does it assess how crowded or open the competitive space is?\n"
        "- Does it consider differentiation opportunities?\n"
        "- Is it specific rather than generic?"
    ),
    "key_risks": (
        "Evaluate the key risks section:\n"
        "- Are the risks specific to this target (not generic drug development risks)?\n"
        "- Are the most important risks included (on-target toxicity, clinical failures, biology gaps)?\n"
        "- Is each risk actionable or at least clearly defined?\n"
        "- Are 3–5 risks listed, ranked by importance?"
    ),
    "confidence_score": (
        "Evaluate whether the confidence score (0–10) is well-calibrated:\n"
        "- Is it consistent with the strength of evidence described in the report?\n"
        "- Does the confidence_reasoning explain what drives the score up and what holds it back?\n"
        "- Is it appropriately cautious for a novel target vs. appropriately confident for a validated one?\n"
        "- Critically: if the druggability assessment concluded the company's chosen modality is a "
        "poor fit for the target's biology (e.g. an antibody program against a purely intracellular "
        "target), was the score actually capped low (≤4) to reflect that hard constraint, rather "
        "than being pulled up by strong biology/clinical validation alone? A high score despite an "
        "acknowledged modality mismatch is a miscalibration and should be flagged as a specific issue."
    ),
}

_SECTION_TOOL = {
    "name": "submit_section_score",
    "description": "Submit score for one report section.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "description": "1–5 (1=poor, 3=adequate, 5=excellent)",
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences explaining the score.",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific problems found, if any. Empty list if none.",
            },
        },
        "required": ["score", "reasoning", "issues"],
    },
}

_SYSTEM = (
    "You are an expert drug discovery analyst evaluating one section of a drug target assessment report. "
    "Score it rigorously against the rubric. Be critical — 5 means genuinely excellent, "
    "3 means adequate with clear gaps, 1 means the section fails its purpose. "
    "Keep your reasoning to 1–2 sentences. List only real, specific issues."
)


def _score_section(
    section: str,
    content: str,
    criteria: str,
    target: str,
    company: str,
) -> dict:
    """
    Score a single report section with its own API call.
    One call per section keeps each prompt small and avoids max_tokens truncation.
    """
    user_message = (
        f"Evaluate the **{section}** section for: {target} (Company: {company})\n\n"
        f"**Section content:**\n{content}\n\n"
        f"**Rubric:**\n{criteria}"
    )

    _t0 = time.perf_counter()
    response = _client.messages.create(
        model=EVAL_JUDGE_MODEL,
        max_tokens=512,
        system=_SYSTEM,
        tools=[_SECTION_TOOL],
        tool_choice={"type": "tool", "name": "submit_section_score"},
        messages=[{"role": "user", "content": user_message}],
    )
    _latency = time.perf_counter() - _t0

    tracker = get_tracker()
    if tracker:
        tracker.record_node(
            f"judge_{section}",
            model=EVAL_JUDGE_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_s=_latency,
        )

    if response.stop_reason == "max_tokens":
        log.error(f"Judge hit max_tokens on section '{section}' — 512 tokens should be ample; check content length")
        return {"section": section, "score": 0, "reasoning": "Judge hit token limit.", "issues": [], "error": True}

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_section_score":
            return {"section": section, **block.input}

    log.error(f"Judge returned no tool_use block for section '{section}'")
    return {"section": section, "score": 0, "reasoning": "Judge failed to return a score.", "issues": [], "error": True}


def judge_report(report: dict, target: str, company: str) -> dict:
    """
    Run LLM-as-judge evaluation on a single report.
    Scores each section in a separate API call so no single call can be
    truncated by token limits. Derives overall/strongest/weakest from scores.
    """
    section_scores = []
    for section, criteria in RUBRIC.items():
        if section == "confidence_score":
            # confidence_score is an integer; the reasoning lives in a separate field.
            # Combine both so the judge can evaluate calibration against the stated rationale.
            content = (
                f"Score: {report.get('confidence_score', 'N/A')}/10\n"
                f"Reasoning: {report.get('confidence_reasoning', '(no reasoning provided)')}"
            )
        else:
            content = report.get(section, "")
        if isinstance(content, list):
            content = "\n".join(f"- {item}" for item in content)
        result = _score_section(section, content, criteria, target, company)
        section_scores.append(result)
        log.info(f"[{target}/{company}] Judge scored '{section}': {result.get('score')}/5")

    scored = [s for s in section_scores if not s.get("error")]
    failed = [s["section"] for s in section_scores if s.get("error")]

    if not scored:
        return {"error": "Judge failed to score any section."}

    avg = sum(s["score"] for s in scored) / len(scored)
    strongest = max(scored, key=lambda s: s["score"])
    weakest = min(scored, key=lambda s: s["score"])

    # top_improvement: surface the first specific issue from the weakest section,
    # or fall back to its reasoning if no issues were listed
    top_issue = (weakest.get("issues") or [weakest.get("reasoning", "")])[0]
    top_improvement = f"{weakest['section']}: {top_issue}"

    result = {
        "target": target,
        "company": company,
        "section_scores": section_scores,
        "overall_quality": round(avg),
        "avg_section_score": round(avg, 2),
        "strongest_section": strongest["section"],
        "weakest_section": weakest["section"],
        "top_improvement": top_improvement,
    }
    if failed:
        result["failed_sections"] = failed
        log.warning(f"[{target}/{company}] Judge failed on sections: {failed}")

    return result
