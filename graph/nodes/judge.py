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
        return {"quality_assessment": {"error": "No report to evaluate."}}

    log.info(f"[{target}/{company}] Judge started")
    quality = judge_report(report, target, company)

    if "error" in quality:
        log.error(f"[{target}/{company}] Judge failed: {quality['error']}")
    else:
        log.info(f"[{target}/{company}] Judge done — overall quality={quality.get('overall_quality')}/5 "
                 f"weakest={quality.get('weakest_section')}")

    return {"quality_assessment": quality}
