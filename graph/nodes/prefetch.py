from tools.opentargets import get_opentargets_data, format_for_context as ot_format
from tools.uniprot import get_uniprot_data, format_for_context as up_format
from graph.state import TargetAssessmentState
from logger import get_logger

log = get_logger(__name__)


def prefetch_node(state: TargetAssessmentState) -> dict:
    """
    Runs before the parallel agents. Fetches structured, deterministic data from
    OpenTargets and UniProt so downstream agents start with a grounded evidence baseline.
    """
    target = state["target"]
    errors = []

    log.info(f"[{target}] Prefetch started")

    # Fetch in sequence — both are fast (~200–400ms each)
    ot_data = get_opentargets_data(target)
    up_data = get_uniprot_data(target)

    if "error" in ot_data:
        log.error(f"[{target}] OpenTargets failed: {ot_data['error']}")
        errors.append(f"OpenTargets: {ot_data['error']}")
    else:
        log.info(f"[{target}] OpenTargets OK — {len(ot_data.get('known_drugs', []))} known drugs, "
                 f"{len(ot_data.get('top_diseases', []))} disease associations")

    if "error" in up_data:
        log.error(f"[{target}] UniProt failed: {up_data['error']}")
        errors.append(f"UniProt: {up_data['error']}")
    else:
        log.info(f"[{target}] UniProt OK — {up_data.get('protein_name', 'unknown protein')}")

    # Format into a readable context block injected into both agents
    # Cap at 1500 chars to avoid contributing to token burst from parallel agents
    combined = "\n\n".join([
        ot_format(ot_data),
        up_format(up_data),
    ])[:1500]

    return {
        "prefetch_context": {
            "opentargets": ot_data,
            "uniprot": up_data,
            "combined_summary": combined,
        },
        "errors": errors,
    }
