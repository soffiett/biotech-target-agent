"""
Judge node — runs after synthesis, before output reaches the user.
Scores each report section using LLM-as-judge and appends the quality
assessment to state so the UI can display it as a transparency signal.
"""

from eval.llm_judge import judge_report
from graph.state import TargetAssessmentState
from logger import get_logger

log = get_logger(__name__)


def judge_node(state: TargetAssessmentState) -> dict:
    report = state.get("report", {})
    target = state["target"]
    company = state["company"]

    if not report:
        log.error(f"[{target}/{company}] Judge skipped — no report in state")
        return {"quality_assessment": {"error": "No report to evaluate."}, "judge_critique": None}

    log.info(f"[{target}/{company}] Judge started")
    quality = judge_report(report, target, company)

    if "error" in quality:
        log.error(f"[{target}/{company}] Judge failed: {quality['error']}")
        return {"quality_assessment": quality, "judge_critique": None}

    log.info(
        f"[{target}/{company}] Judge done — overall quality={quality.get('overall_quality')}/5 "
        f"weakest={quality.get('weakest_section')}"
    )

    # Extract biology critique for potential re-run
    section_scores = quality.get("section_scores", [])
    bio_entry = next((s for s in section_scores if s["section"] == "biology_rationale"), None)
    judge_critique = None
    if bio_entry and bio_entry.get("score", 5) <= 2:
        judge_critique = {
            "biology_score": bio_entry["score"],
            "biology_issues": bio_entry.get("issues", []),
            "top_improvement": quality.get("top_improvement", ""),
        }
        log.info(
            f"[{target}/{company}] Biology scored {bio_entry['score']}/5 — "
            f"critique queued for re-run"
        )

    return {"quality_assessment": quality, "judge_critique": judge_critique}
