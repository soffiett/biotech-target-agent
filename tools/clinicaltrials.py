import requests
from logger import get_logger

log = get_logger(__name__)
CT_BASE = "https://clinicaltrials.gov/api/v2/studies"

FIELDS = ",".join([
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Phase",
    "LeadSponsorName",
    "StartDate",
    "PrimaryCompletionDate",
    "BriefSummary",
    "Condition",
    "InterventionName",
])


def search_clinical_trials(query: str, max_results: int = 10) -> list[dict]:
    """Search ClinicalTrials.gov v2 API for studies related to a target or drug."""
    log.debug(f"ClinicalTrials search: '{query}' (max={max_results})")
    resp = requests.get(
        CT_BASE,
        params={
            "query.term": query,
            "fields": FIELDS,
            "pageSize": max_results,
            "format": "json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    log.debug(f"ClinicalTrials returned {len(data.get('studies', []))} studies for '{query}'")

    studies = []
    for study in data.get("studies", []):
        proto = study.get("protocolSection", {})
        id_mod = proto.get("identificationModule", {})
        status_mod = proto.get("statusModule", {})
        design_mod = proto.get("designModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
        desc_mod = proto.get("descriptionModule", {})
        cond_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})

        nct_id = id_mod.get("nctId", "")
        phases = design_mod.get("phases", [])

        interventions = [
            i.get("name", "")
            for i in arms_mod.get("interventions", [])
            if i.get("type") in ("BIOLOGICAL", "DRUG")
        ]

        phase_str = phases[0] if phases else "N/A"
        conditions_str = ", ".join(cond_mod.get("conditions", [])[:3]) or "N/A"
        interventions_str = ", ".join(interventions[:2]) or "N/A"
        title = id_mod.get("briefTitle", "N/A")
        status = status_mod.get("overallStatus", "N/A")
        sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "N/A")

        # Compact one-line format keeps each record ~120 chars instead of ~700,
        # preventing tool result JSON from dominating the agent's context window.
        studies.append(
            f"{nct_id} | {phase_str} | {status} | {sponsor} | {interventions_str} | {conditions_str} | "
            f"https://clinicaltrials.gov/study/{nct_id} | {title}"
        )

    return studies
