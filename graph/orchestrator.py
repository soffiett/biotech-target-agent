from langgraph.graph import StateGraph, START, END
from graph.state import TargetAssessmentState
from graph.nodes.prefetch import prefetch_node
from graph.nodes.biology import biology_node
from graph.nodes.clinical_trials import clinical_trials_node
from graph.nodes.synthesis import synthesis_node
from graph.nodes.judge import judge_node


def _route_after_judge(state: TargetAssessmentState) -> str:
    """
    After judge scores the report, decide whether to re-run the biology agent.
    Triggers a re-run if biology scored <= 2/5 and we haven't re-run yet.
    rerun_count is incremented by biology_node each time it runs, so >= 2 means
    biology has already run twice (initial + one re-run) — stop regardless of score.
    """
    if state.get("rerun_count", 0) >= 2:
        return END

    quality = state.get("quality_assessment", {})
    section_scores = quality.get("section_scores", [])
    bio_entry = next((s for s in section_scores if s["section"] == "biology_rationale"), None)

    if bio_entry and bio_entry.get("score", 5) <= 2:
        return "biology"

    return END


def build_graph() -> StateGraph:
    workflow = StateGraph(TargetAssessmentState)

    workflow.add_node("prefetch", prefetch_node)
    workflow.add_node("biology", biology_node)
    workflow.add_node("clinical_trials", clinical_trials_node)
    workflow.add_node("synthesis", synthesis_node)
    workflow.add_node("judge", judge_node)

    # Prefetch runs first — sets OpenTargets context and per-agent focus instructions
    workflow.add_edge(START, "prefetch")

    # Fan out to parallel agents after prefetch
    workflow.add_edge("prefetch", "biology")
    workflow.add_edge("prefetch", "clinical_trials")

    # Both feed into synthesis once complete (LangGraph joins active branches only,
    # so re-run path biology → synthesis does not wait for clinical_trials again)
    workflow.add_edge("biology", "synthesis")
    workflow.add_edge("clinical_trials", "synthesis")

    # Judge scores the report; conditionally re-runs biology if it scored too low
    workflow.add_edge("synthesis", "judge")
    workflow.add_conditional_edges(
        "judge",
        _route_after_judge,
        {"biology": "biology", END: END},
    )

    return workflow.compile()


# Module-level graph instance — imported by app.py
graph = build_graph()
