from tools.opentargets import get_opentargets_data, format_for_context as ot_format
from tools.uniprot import get_uniprot_data, format_for_context as up_format
from graph.state import TargetAssessmentState


def prefetch_node(state: TargetAssessmentState) -> dict:
    """
    Runs before the parallel agents. Fetches structured, deterministic data from
    OpenTargets and UniProt so downstream agents start with a grounded evidence baseline.
    """
    target = state["target"]
    errors = []

    # Fetch in sequence — both are fast (~200–400ms each)
    ot_data = get_opentargets_data(target)
    up_data = get_uniprot_data(target)

    if "error" in ot_data:
        errors.append(f"OpenTargets: {ot_data['error']}")
    if "error" in up_data:
        errors.append(f"UniProt: {up_data['error']}")

    # Format into a single readable context block injected into both agents
    combined = "\n\n".join([
        ot_format(ot_data),
        up_format(up_data),
    ])

    return {
        "prefetch_context": {
            "opentargets": ot_data,
            "uniprot": up_data,
            "combined_summary": combined,
        },
        "errors": errors,
    }
