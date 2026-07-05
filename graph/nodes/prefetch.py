from tools.opentargets import get_opentargets_data, format_for_context as ot_format
from graph.state import TargetAssessmentState
from logger import get_logger

log = get_logger(__name__)


def _build_focus_instructions(ot_data: dict) -> dict:
    """
    Derive agent-specific research focus from OpenTargets structured data.
    The prefetch result (approved drugs, clinical stage, genetic scores) determines
    what each downstream agent should prioritize — avoiding redundant searches on
    already-established facts and directing effort toward gaps.
    """
    if "error" in ot_data:
        return {
            "biology_focus": (
                "OpenTargets data unavailable. Cover all areas: target biology, "
                "genetic evidence, disease mechanism, and druggability."
            ),
            "clinical_focus": (
                "OpenTargets data unavailable. Search broadly for any clinical "
                "programs targeting this pathway."
            ),
        }

    drugs = ot_data.get("known_drugs", [])
    diseases = ot_data.get("top_diseases", [])

    approved = [d for d in drugs if d["is_approved"]]
    withdrawn = [d for d in drugs if d.get("is_withdrawn")]
    # Late-stage = in Phase II/III or later, but not yet approved and not withdrawn.
    # 0.5 is the Phase II/III precedence score; approval is 1.0, so this window is
    # [0.5, 1.0) minus the withdrawn cases (which score 1.0 anyway).
    late_stage = [
        d for d in drugs
        if 0.5 <= d.get("maturity", 0) < 1.0 and not d["is_approved"]
    ]
    top_genetic = max((d["genetic_association"] for d in diseases), default=0)

    # Biology focus: shift from "does it work?" to "what's the nuance?" as evidence matures
    if approved:
        bio_focus = (
            f"OpenTargets confirms {len(approved)} approved drug(s) for this target — "
            "target validation is established. Do NOT spend time re-proving the basic rationale. "
            "Focus on: (1) mechanism of action and how a biologic engages the target, "
            "(2) resistance mechanisms or treatment failures in approved therapies, "
            "(3) on-target safety signals and toxicity patterns, "
            "(4) patient stratification and predictive biomarkers."
        )
    elif late_stage:
        bio_focus = (
            f"OpenTargets shows {len(late_stage)} Phase 2/3 program(s) — basic target validation exists. "
            "Focus on: (1) what distinguishes responders from non-responders mechanistically, "
            "(2) preclinical biomarkers that predict clinical response, "
            "(3) combination approaches and synergistic biology, "
            "(4) alternative indications where the biology may differ."
        )
    elif top_genetic > 0.5:
        bio_focus = (
            f"OpenTargets shows strong genetic association (score {top_genetic:.2f}) but limited clinical precedent. "
            "Genetic evidence is the strongest signal — now assess translatability. "
            "Focus on: (1) functional validation in disease-relevant models, "
            "(2) the translational gap between genetic findings and drugable biology, "
            "(3) target expression profile and cell-type specificity, "
            "(4) structural druggability for a large molecule format."
        )
    else:
        bio_focus = (
            "OpenTargets shows limited genetic and clinical evidence — this is an early/novel target. "
            "Be thorough and skeptical: (1) what is the disease mechanism rationale? "
            "(2) any preclinical models where target modulation has therapeutic effect? "
            "(3) indirect genomic or expression evidence? "
            "(4) Flag clearly if the evidence base is thin — do not overstate."
        )

    # Clinical focus: shift from discovery to competitive intelligence as stage advances
    if approved:
        clin_focus = (
            f"{len(approved)} approved drug(s) exist — the market is established. Focus on: "
            "(1) competitive crowding and what differentiation a new biologic would need, "
            "(2) underserved indications or combination opportunities, "
            "(3) biosimilar or next-generation program landscape, "
            "(4) any recent approvals or label expansions that change the picture."
        )
    elif late_stage:
        clin_focus = (
            f"{len(late_stage)} mid-to-late stage program(s) in the clinic. Focus on: "
            "(1) which trials are still enrolling vs. completed vs. failed and why, "
            "(2) failure root causes — patient selection, dose, endpoint, or mechanism? "
            "(3) differentiation opportunity for a new entrant given what failed, "
            "(4) timelines and whether this space is getting crowded."
        )
    else:
        clin_focus = (
            "Limited clinical precedent for this target. Search broadly: "
            "(1) any Phase 1/2 trials for this target or close pathway analogs, "
            "(2) investigator-initiated or academic studies, "
            "(3) programs that failed early and documented reasons, "
            "(4) whether any company has publicly dropped this target and why."
        )

    return {"biology_focus": bio_focus, "clinical_focus": clin_focus}


def prefetch_node(state: TargetAssessmentState) -> dict:
    """
    Runs before the parallel agents. Fetches structured, deterministic data from
    OpenTargets so downstream agents start with a grounded evidence baseline.
    Also derives per-agent research focus from the structured data so each agent
    searches for gaps rather than re-confirming established facts.
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
        log.info(
            f"[{target}] OpenTargets OK — "
            f"{len(ot_data.get('known_drugs', []))} clinical candidates, "
            f"{len(ot_data.get('top_diseases', []))} disease associations"
        )
        summary = ot_format(ot_data)[:1500]

    focus = _build_focus_instructions(ot_data)
    log.debug(f"[{target}] Biology focus: {focus['biology_focus'][:80]}...")
    log.debug(f"[{target}] Clinical focus: {focus['clinical_focus'][:80]}...")

    return {
        "prefetch_context": {
            "opentargets": ot_data,
            "combined_summary": summary,
            "biology_focus": focus["biology_focus"],
            "clinical_focus": focus["clinical_focus"],
        },
        "errors": errors,
    }
