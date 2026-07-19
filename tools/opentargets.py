import re
import requests
from logger import get_logger

log = get_logger(__name__)

# OpenTargets clinical-precedence vocabulary → (canonical_label, evidence_score).
# The score is OpenTargets' own maturity ordinal (0.01–1.0); we reuse it directly
# rather than inventing a parallel rank scale. Downstream code compares scores.
_STAGE_TABLE = {
    "UNKNOWN":        ("UNKNOWN",       0.01),
    "PRECLINICAL":    ("PRECLINICAL",   0.01),
    "IND":            ("IND",           0.05),
    "EARLY PHASE I":  ("EARLY_PHASE_1", 0.05),
    "PHASE I":        ("PHASE_1",       0.10),
    "PHASE I/II":     ("PHASE_1_2",     0.15),
    "PHASE II":       ("PHASE_2",       0.20),
    "PHASE II/III":   ("PHASE_2_3",     0.50),
    "PHASE III":      ("PHASE_3",       0.70),
    "PREAPPROVAL":    ("PREAPPROVAL",   0.80),
    "APPROVAL":       ("APPROVED",      1.00),
    "PHASE IV":       ("PHASE_4",       1.00),
    "WITHDRAWAL":     ("WITHDRAWN",     1.00),
}


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
        log.error(
            f"OpenTargets API error {resp.status_code}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json().get("data", {})

# Tolerant lookup: OpenTargets' exact vocabulary isn't guaranteed stable and has
# used several formats across versions ("PHASE III", "Phase III", "PHASE_III",
# "PHASE3", "PHASE_3"). We normalize aggressively and log misses so format drift
# is visible. _STAGE_TABLE keys are roman numerals, but the live API has been
# observed returning arabic digits ("PHASE_3") — mapped to roman below so both
# forms resolve to the same entry instead of silently falling through to UNKNOWN.
_ARABIC_TO_ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV"}


def _normalize_stage(raw: str) -> tuple[str, float]:
    """
    Map a raw OpenTargets clinical-stage string to (canonical_label, maturity_score).
    maturity_score is OpenTargets' own clinical-precedence evidence score (0.01–1.0).
    Unrecognized values are logged and treated as UNKNOWN, so upstream format drift
    surfaces in logs instead of silently corrupting downstream focus routing.
    """
    if not raw:
        return _STAGE_TABLE["UNKNOWN"]

    # Normalize whitespace/case, split a letter immediately followed by a digit
    # ("PHASE3" -> "PHASE 3"), then map arabic digit tokens to roman numerals —
    # so "PHASE3", "PHASE_3", and "PHASE III" all resolve to the same entry.
    key = " ".join(raw.upper().replace("_", " ").split())
    key = re.sub(r"(?<=[A-Z])(?=\d)", " ", key)
    key = " ".join(_ARABIC_TO_ROMAN.get(tok, tok) for tok in key.split())
    if key in _STAGE_TABLE:
        return _STAGE_TABLE[key]

    log.warning(
        f"OpenTargets: unrecognized clinical stage '{raw}' — treated as UNKNOWN")
    return _STAGE_TABLE["UNKNOWN"]


def resolve_target_ensembl_id(target_symbol: str) -> str | None:
    """Resolve a gene symbol/alias to its Ensembl ID via OpenTargets' search index."""
    search_data = _graphql(_SEARCH_QUERY, {"q": target_symbol})
    hits = search_data.get("search", {}).get("hits", [])
    target_hits = [h for h in hits if h.get("entity") == "target"]
    return target_hits[0]["id"] if target_hits else None


def get_opentargets_data(target_symbol: str) -> dict:
    """
    Look up a target on OpenTargets Platform.
    Returns disease associations and known clinical candidates.
    """
    try:
        log.debug(f"OpenTargets search for: {target_symbol}")
        ensembl_id = resolve_target_ensembl_id(target_symbol)

        if not ensembl_id:
            return {
                "error": f"Target '{target_symbol}' not found in OpenTargets.",
                "error_type": "not_found",
            }

        log.debug(f"OpenTargets found Ensembl ID: {ensembl_id}")

        target_data = _graphql(_TARGET_QUERY, {"ensemblId": ensembl_id})
        t = target_data.get("target")
        if not t:
            return {
                "error": f"No profile found for Ensembl ID {ensembl_id}.",
                "error_type": "not_found",
            }

        # Disease associations
        diseases = []
        for row in t.get("associatedDiseases", {}).get("rows", []):
            scores = {s["id"]: round(s["score"], 3)
                      for s in row.get("datatypeScores", [])}
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
            raw_stage = row.get("maxClinicalStage", "")
            stage_label, maturity = _normalize_stage(raw_stage)
            indications = list({
                d.get("diseaseFromSource", "")
                for d in row.get("diseases", [])
                if d.get("diseaseFromSource")
            })[:3]
            drugs.append({
                "name": drug.get("name", ""),
                "max_stage": raw_stage,           # raw, for display/debug
                "stage_label": stage_label,       # canonical enum-like label
                "maturity": maturity,             # OpenTargets precedence score 0.01–1.0
                "is_approved": stage_label == "APPROVED",
                "is_withdrawn": stage_label == "WITHDRAWN",
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
        log.error(
            f"OpenTargets lookup failed for '{target_symbol}': {e}", exc_info=True)
        return {"error": str(e), "error_type": "upstream_failure"}


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
            status = dr.get("stage_label") or dr.get("max_stage", "unknown")
            withdrawn = " [WITHDRAWN]" if dr.get("is_withdrawn") else ""
            lines.append(f"- {dr['name']} ({status}){withdrawn}")
    else:
        lines.append("- No clinical candidates found.")

    return "\n".join(lines)
