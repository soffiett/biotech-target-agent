import requests
from tools.opentargets import resolve_target_ensembl_id
from logger import get_logger

log = get_logger(__name__)
OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"

_DISEASE_SEARCH = """
query DiseaseSearch($q: String!) {
  search(queryString: $q, entityNames: ["disease"]) {
    hits { id name entity }
  }
}
"""

_EVIDENCE_QUERY = """
query Evidence($ensemblId: String!, $efoId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    evidences(efoIds: [$efoId], datasourceIds: ["gwas_credible_sets"], size: $size) {
      count
      rows {
        score
        literature
        disease { name }
        credibleSet { studyId }
      }
    }
  }
}
"""


def _graphql(query: str, variables: dict) -> dict:
    resp = requests.post(OT_GRAPHQL, json={"query": query, "variables": variables}, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", {})


def search_gwas_evidence(gene: str, indication: str, max_results: int = 5) -> list[dict]:
    """
    Human genetic association evidence (GWAS credible sets, L2G-scored) for a
    gene-disease pair, via OpenTargets. Distinct from prefetch's aggregate
    genetic_association score — these are the underlying study/variant hits.
    """
    try:
        ensembl_id = resolve_target_ensembl_id(gene)
        if not ensembl_id:
            return [{"error": f"Target '{gene}' not found in OpenTargets."}]

        disease_data = _graphql(_DISEASE_SEARCH, {"q": indication})
        hits = disease_data.get("search", {}).get("hits", [])
        if not hits:
            return [{"error": f"No disease match for '{indication}' in OpenTargets."}]
        efo_id, disease_name = hits[0]["id"], hits[0]["name"]

        evidence_data = _graphql(
            _EVIDENCE_QUERY,
            {"ensemblId": ensembl_id, "efoId": efo_id, "size": max_results},
        )
        rows = evidence_data.get("target", {}).get("evidences", {}).get("rows", [])
        if not rows:
            return [{"error": f"No GWAS credible-set evidence found for {gene} in '{disease_name}'."}]

        return [
            {
                "trait": r.get("disease", {}).get("name") or disease_name,
                "l2g_score": round(r["score"], 3) if r.get("score") is not None else None,
                "gwas_catalog_study_id": r.get("credibleSet", {}).get("studyId"),
                "pubmed_ids": r.get("literature") or [],
            }
            for r in rows
        ]
    except Exception as e:
        log.error(f"GWAS evidence lookup failed for '{gene}'/'{indication}': {e}", exc_info=True)
        return [{"error": str(e)}]
