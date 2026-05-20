from langgraph.graph import StateGraph, START, END
from graph.state import TargetAssessmentState
from graph.nodes.prefetch import prefetch_node
from graph.nodes.biology import biology_node
from graph.nodes.clinical_trials import clinical_trials_node
from graph.nodes.synthesis import synthesis_node


def build_graph() -> StateGraph:
    workflow = StateGraph(TargetAssessmentState)

    workflow.add_node("prefetch", prefetch_node)
    workflow.add_node("biology", biology_node)
    workflow.add_node("clinical_trials", clinical_trials_node)
    workflow.add_node("synthesis", synthesis_node)

    # Prefetch runs first — sets OpenTargets + UniProt context
    workflow.add_edge(START, "prefetch")

    # Fan out to parallel agents after prefetch
    workflow.add_edge("prefetch", "biology")
    workflow.add_edge("prefetch", "clinical_trials")

    # Both feed into synthesis once complete
    workflow.add_edge("biology", "synthesis")
    workflow.add_edge("clinical_trials", "synthesis")

    workflow.add_edge("synthesis", END)

    return workflow.compile()


# Module-level graph instance — imported by app.py
graph = build_graph()
