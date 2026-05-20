import requests
from logger import get_logger

log = get_logger(__name__)
OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"

_SEARCH_QUERY = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["target"]) {
    hits { id name entity }
  }
}
"""

_TARGET_QUERY = """
query Target($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    approvedName
    biotype
    functionDescriptions
    associatedDiseases(page: {index: 0, size: 6}) {
      rows {
        disease { name }
        score
        datatypeScores { id score }
      }
    }
    drugAndClinicalCandidates {
      count
      rows {
        maxClinicalStage
        drug { name maximumClinicalStage }
        diseases { diseaseFromSource }
      }
    }
  }
}
"""


def _graphql(query: str, variables: dict) -> dict:
    resp = requests.post(
        OT_GRAPHQL,
        json={"query": query, "variables": variables},
        timeout=15,
    )
    if not resp.ok:
        log.error(f"OpenTargets API error {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json().get("data", {})


def get_opentargets_data(target_symbol: str) -> dict:
    """
    Look up a target on OpenTargets Platform.
    Returns disease associations and known clinical candidates.
    """
    try:
        log.debug(f"OpenTargets search for: {target_symbol}")
        search_data = _graphql(_SEARCH_QUERY, {"q": target_symbol})
        hits = search_data.get("search", {}).get("hits", [])
        target_hits = [h for h in hits if h.get("entity") == "target"]

        if not target_hits:
            return {"error": f"Target '{target_symbol}' not found in OpenTargets."}

        ensembl_id = target_hits[0]["id"]
        log.debug(f"OpenTargets found Ensembl ID: {ensembl_id}")

        target_data = _graphql(_TARGET_QUERY, {"ensemblId": ensembl_id})
        t = target_data.get("target")
        if not t:
            return {"error": f"No profile found for Ensembl ID {ensembl_id}."}

        # Disease associations
        diseases = []
        for row in t.get("associatedDiseases", {}).get("rows", []):
            scores = {s["id"]: round(s["score"], 3) for s in row.get("datatypeScores", [])}
            diseases.append({
                "disease": row["disease"]["name"],
                "overall_score": round(row["score"], 3),
                "genetic_association": scores.get("genetic_association", 0),
                "somatic_mutation": scores.get("somatic_mutation", 0),
                "clinical": scores.get("clinical", 0),
                "literature": scores.get("literature", 0),
            })

        # Clinical candidates and approved drugs
        drugs = []
        for row in t.get("drugAndClinicalCandidates", {}).get("rows", []):
            drug = row.get("drug", {})
            stage = row.get("maxClinicalStage", "")
            indications = list({
                d.get("diseaseFromSource", "")
                for d in row.get("diseases", [])
                if d.get("diseaseFromSource")
            })[:3]
            drugs.append({
                "name": drug.get("name", ""),
                "max_stage": stage,
                "is_approved": stage == "APPROVAL",
                "indications": indications,
            })

        return {
            "ensembl_id": ensembl_id,
            "symbol": t.get("approvedSymbol", ""),
            "name": t.get("approvedName", ""),
            "biotype": t.get("biotype", ""),
            "function": " ".join(t.get("functionDescriptions", []))[:600],
            "top_diseases": diseases,
            "known_drugs": drugs,
        }

    except Exception as e:
        log.error(f"OpenTargets lookup failed for '{target_symbol}': {e}", exc_info=True)
        return {"error": str(e)}


def format_for_context(data: dict) -> str:
    """Convert OpenTargets data into a readable string for agent context."""
    if "error" in data:
        return f"OpenTargets: {data['error']}"

    lines = [
        f"## OpenTargets: {data['symbol']} ({data['name']})",
        f"Biotype: {data['biotype']}",
        f"Function: {data['function']}",
        "",
        "### Top Disease Associations (score 0–1)",
    ]
    for d in data["top_diseases"][:5]:
        lines.append(
            f"- {d['disease']}: overall={d['overall_score']} "
            f"| genetic={d['genetic_association']} "
            f"| clinical={d['clinical']}"
        )

    lines += ["", "### Clinical Candidates & Approved Drugs"]
    if data["known_drugs"]:
        for dr in data["known_drugs"][:8]:
            status = "APPROVED" if dr["is_approved"] else dr["max_stage"]
            indications = ", ".join(dr["indications"]) or "unknown indication"
            lines.append(f"- {dr['name']} ({status}) — {indications}")
    else:
        lines.append("- No clinical candidates found.")

    return "\n".join(lines)
