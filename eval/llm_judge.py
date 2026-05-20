"""
Level 2 Evaluation — LLM-as-Judge

Uses Claude Sonnet to score each section of the assessment report
against a structured rubric. Triggered automatically on Level 1 failures
and run standalone for novel targets with no ground truth.
"""

import anthropic
from config import EVAL_JUDGE_MODEL, EVAL_JUDGE_MAX_TOKENS
from logger import get_logger

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
        "Evaluate the druggability assessment section:\n"
        "- Does it address whether the target is accessible to a large molecule (extracellular vs intracellular)?\n"
        "- Does it recommend an appropriate biologic format (mAb, bispecific, ADC, Fc-fusion)?\n"
        "- Does it consider PK/pharmacology relevant to biologics?\n"
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
        "- Is it appropriately cautious for a novel target vs. appropriately confident for a validated one?"
    ),
}

_JUDGE_TOOL = {
    "name": "submit_section_scores",
    "description": "Submit scores for all report sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "section_scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string"},
                        "score": {
                            "type": "integer",
                            "description": "1–5 (1=poor, 3=adequate, 5=excellent)",
                        },
                        "reasoning": {"type": "string"},
                        "issues": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific problems found, if any.",
                        },
                    },
                    "required": ["section", "score", "reasoning", "issues"],
                },
            },
            "overall_quality": {
                "type": "integer",
                "description": "Overall report quality 1–5.",
            },
            "strongest_section": {"type": "string"},
            "weakest_section": {"type": "string"},
            "top_improvement": {
                "type": "string",
                "description": "The single most important thing to improve.",
            },
        },
        "required": ["section_scores", "overall_quality", "strongest_section", "weakest_section", "top_improvement"],
    },
}

_SYSTEM = (
    "You are an expert drug discovery analyst evaluating the quality of a drug target assessment report. "
    "Score each section rigorously against the rubric. Be critical — a score of 5 means the section is "
    "genuinely excellent, not just adequate. A score of 3 means adequate but with clear gaps. "
    "Be specific in your reasoning and issues."
)


def judge_report(report: dict, target: str, company: str) -> dict:
    """
    Run LLM-as-judge evaluation on a single report.
    Returns structured scores per section plus overall quality assessment.
    """
    # Build rubric evaluation prompts for each section
    section_evals = []
    for section, criteria in RUBRIC.items():
        content = report.get(section, "")
        if isinstance(content, list):
            content = "\n".join(f"- {item}" for item in content)
        section_evals.append(
            f"### Section: {section}\n"
            f"**Content:**\n{content}\n\n"
            f"**Rubric:**\n{criteria}"
        )

    user_message = (
        f"Evaluate this drug target assessment report for: **{target}** (Company: {company})\n\n"
        + "\n\n---\n\n".join(section_evals)
        + "\n\nScore each section 1–5 and provide your overall quality assessment."
    )

    response = _client.messages.create(
        model=EVAL_JUDGE_MODEL,
        max_tokens=EVAL_JUDGE_MAX_TOKENS,
        system=_SYSTEM,
        tools=[_JUDGE_TOOL],
        tool_choice={"type": "tool", "name": "submit_section_scores"},
        messages=[{"role": "user", "content": user_message}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_section_scores":
            scores = block.input
            log.debug(f"Judge raw response keys: {list(scores.keys())}")
            log.debug(f"Judge stop_reason: {response.stop_reason}")

            section_scores = scores.get("section_scores", [])

            if not section_scores:
                log.warning("Judge returned empty section_scores — likely token limit reached")

            avg = (
                sum(s.get("score", 0) for s in section_scores) / len(section_scores)
                if section_scores else 0.0
            )
            return {
                "target": target,
                "company": company,
                "section_scores": section_scores,
                "overall_quality": scores.get("overall_quality", 0),
                "avg_section_score": round(avg, 2),
                "strongest_section": scores.get("strongest_section", "unknown"),
                "weakest_section": scores.get("weakest_section", "unknown"),
                "top_improvement": scores.get("top_improvement", ""),
            }

    log.error(f"Judge returned no tool_use block. stop_reason={response.stop_reason}")
    return {"error": "Judge failed to return structured scores."}
