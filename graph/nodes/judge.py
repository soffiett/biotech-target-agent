"""
Judge node — runs after synthesis, before output reaches the user.
Scores each report section using LLM-as-judge and appends the quality
assessment to state so the UI can display it as a transparency signal.
"""

from eval.llm_judge import judge_report
from graph.state import TargetAssessmentState


def judge_node(state: TargetAssessmentState) -> dict:
    report = state.get("report", {})
    target = state["target"]
    company = state["company"]

    if not report:
        return {"quality_assessment": {"error": "No report to evaluate."}}

    quality = judge_report(report, target, company)
    return {"quality_assessment": quality}
