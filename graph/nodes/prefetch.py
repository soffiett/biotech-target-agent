from tools.opentargets import get_opentargets_data, format_for_context as ot_format
from graph.state import TargetAssessmentState
from logger import get_logger

log = get_logger(__name__)


def prefetch_node(state: TargetAssessmentState) -> dict:
    """
    Runs before the parallel agents. Fetches structured, deterministic data from
    OpenTargets so downstream agents start with a grounded evidence baseline.
    """
    target = state["target"]
    errors = []

    log.info(f"[{target}] Prefetch started")

    ot_data = get_opentargets_data(target)

    if "error" in ot_data:
        log.error(f"[{target}] OpenTargets failed: {ot_data['error']}")
        errors.append(f"OpenTargets: {ot_data['error']}")
        summary = "OpenTargets data unavailable."
    else:
        log.info(f"[{target}] OpenTargets OK — "
                 f"{len(ot_data.get('known_drugs', []))} clinical candidates, "
                 f"{len(ot_data.get('top_diseases', []))} disease associations")
        summary = ot_format(ot_data)[:1500]

    return {
        "prefetch_context": {
            "opentargets": ot_data,
            "combined_summary": summary,
        },
        "errors": errors,
    }
