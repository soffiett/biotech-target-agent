import requests
from tools.opentargets import resolve_target_ensembl_id
from logger import get_logger

log = get_logger(__name__)
OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"

_DEPMAP_QUERY = """
query DepMap($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    approvedSymbol
    isEssential
    depMapEssentiality {
      tissueName
      screens { cellLineName diseaseFromSource geneEffect }
    }
  }
}
"""


def search_crispr_dependency(gene: str, max_results: int = 5) -> list[dict]:
    """
    CRISPR knockout dependency (DepMap gene-effect/Chronos scores) by tissue,
    via OpenTargets. Gene-effect is negative when knockout reduces cell-line
    fitness (i.e. the target is a dependency) — most negative tissues are
    ranked first.
    """
    try:
        ensembl_id = resolve_target_ensembl_id(gene)
        if not ensembl_id:
            return [{"error": f"Target '{gene}' not found in OpenTargets."}]

        resp = requests.post(OT_GRAPHQL, json={"query": _DEPMAP_QUERY, "variables": {"ensemblId": ensembl_id}}, timeout=15)
        resp.raise_for_status()
        t = resp.json().get("data", {}).get("target")
        if not t:
            return [{"error": f"No DepMap profile found for {gene}."}]

        tissues = t.get("depMapEssentiality") or []
        if not tissues:
            return [{"error": f"No CRISPR dependency data available for {gene} in DepMap."}]

        ranked = []
        for tis in tissues:
            effects = [s["geneEffect"] for s in tis.get("screens", []) if s.get("geneEffect") is not None]
            if not effects:
                continue
            most_dependent = min(tis["screens"], key=lambda s: s.get("geneEffect", 0))
            ranked.append({
                "tissue": tis["tissueName"],
                "n_cell_lines_screened": len(effects),
                "mean_gene_effect": round(sum(effects) / len(effects), 3),
                "most_dependent_cell_line": most_dependent.get("cellLineName"),
                "most_dependent_cell_line_disease": most_dependent.get("diseaseFromSource"),
                "min_gene_effect": round(most_dependent.get("geneEffect", 0), 3),
            })
        ranked.sort(key=lambda r: r["mean_gene_effect"])

        return [{"symbol": t.get("approvedSymbol"), "is_common_essential": t.get("isEssential")}] + ranked[:max_results]
    except Exception as e:
        log.error(f"DepMap lookup failed for '{gene}': {e}", exc_info=True)
        return [{"error": str(e)}]
