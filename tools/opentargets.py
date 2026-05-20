import requests

OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"

# Step 1 — find the Ensembl ID from a gene symbol or name
_SEARCH_QUERY = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["target"]) {
    hits { id name entity }
  }
}
"""

# Step 2 — get full target profile using the Ensembl ID
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
        datatypeScores { componentId score }
      }
    }
    knownDrugs(size: 10) {
      rows {
        drug { name maximumClinicalTrialPhase isApproved }
        disease { name }
        phase
        status
        mechanismOfAction
      }
    }
    safetyLiabilities {
      event
      effects { direction dosing }
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
    resp.raise_for_status()
    return resp.json().get("data", {})


def get_opentargets_data(target_symbol: str) -> dict:
    """
    Look up a target on OpenTargets Platform.
    Returns a structured dict with disease associations, known drugs, and safety flags.
    Returns {"error": ...} if the target is not found.
    """
    try:
        # Search for Ensembl ID
        search_data = _graphql(_SEARCH_QUERY, {"q": target_symbol})
        hits = search_data.get("search", {}).get("hits", [])
        target_hits = [h for h in hits if h.get("entity") == "target"]

        if not target_hits:
            return {"error": f"Target '{target_symbol}' not found in OpenTargets."}

        ensembl_id = target_hits[0]["id"]

        # Fetch full profile
        target_data = _graphql(_TARGET_QUERY, {"ensemblId": ensembl_id})
        t = target_data.get("target")
        if not t:
            return {"error": f"No profile found for Ensembl ID {ensembl_id}."}

        # Parse disease associations with datatype scores
        diseases = []
        for row in t.get("associatedDiseases", {}).get("rows", []):
            scores = {s["componentId"]: round(s["score"], 3) for s in row.get("datatypeScores", [])}
            diseases.append({
                "disease": row["disease"]["name"],
                "overall_score": round(row["score"], 3),
                "genetic_association": scores.get("genetic_association", 0),
                "somatic_mutation": scores.get("somatic_mutation", 0),
                "known_drug": scores.get("known_drug", 0),
                "affected_pathway": scores.get("affected_pathway", 0),
                "literature": scores.get("literature", 0),
            })

        # Parse known drugs
        drugs = []
        for row in t.get("knownDrugs", {}).get("rows", []):
            drug = row.get("drug", {})
            drugs.append({
                "name": drug.get("name", ""),
                "max_phase": drug.get("maximumClinicalTrialPhase"),
                "is_approved": drug.get("isApproved", False),
                "indication": row.get("disease", {}).get("name", ""),
                "phase": row.get("phase"),
                "status": row.get("status", ""),
                "mechanism": row.get("mechanismOfAction", ""),
            })

        # Parse safety flags
        safety = [
            {
                "event": s.get("event", ""),
                "effects": [f"{e.get('direction', '')} {e.get('dosing', '')}".strip() for e in s.get("effects", [])],
            }
            for s in t.get("safetyLiabilities", [])
        ]

        return {
            "ensembl_id": ensembl_id,
            "symbol": t.get("approvedSymbol", ""),
            "name": t.get("approvedName", ""),
            "biotype": t.get("biotype", ""),
            "function": " ".join(t.get("functionDescriptions", []))[:800],
            "top_diseases": diseases,
            "known_drugs": drugs,
            "safety_liabilities": safety,
        }

    except Exception as e:
        return {"error": str(e)}


def format_for_context(data: dict) -> str:
    """Convert OpenTargets data into a readable string for agent context."""
    if "error" in data:
        return f"OpenTargets: {data['error']}"

    lines = [
        f"## OpenTargets Profile: {data['symbol']} ({data['name']})",
        f"Biotype: {data['biotype']}",
        f"Function: {data['function']}",
        "",
        "### Top Disease Associations (score 0–1)",
    ]
    for d in data["top_diseases"][:5]:
        lines.append(
            f"- {d['disease']}: overall={d['overall_score']} "
            f"| genetic={d['genetic_association']} "
            f"| clinical={d['known_drug']}"
        )

    lines += ["", "### Known Drugs / Clinical Programs"]
    if data["known_drugs"]:
        for dr in data["known_drugs"][:8]:
            status = "APPROVED" if dr["is_approved"] else f"Phase {dr['max_phase']}"
            lines.append(f"- {dr['name']} ({status}) — {dr['indication']} — {dr['mechanism']}")
    else:
        lines.append("- No known drugs found.")

    lines += ["", "### Safety Liabilities"]
    if data["safety_liabilities"]:
        for s in data["safety_liabilities"][:5]:
            effects = ", ".join(s["effects"]) if s["effects"] else "unspecified"
            lines.append(f"- {s['event']}: {effects}")
    else:
        lines.append("- No safety liabilities flagged.")

    return "\n".join(lines)
