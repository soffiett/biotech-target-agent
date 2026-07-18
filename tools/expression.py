import requests
from logger import get_logger

log = get_logger(__name__)
HPA_ENTRY = "https://www.proteinatlas.org/{}.json"
GTEX_GENE = "https://gtexportal.org/api/v2/reference/gene"
GTEX_EXPR = "https://gtexportal.org/api/v2/expression/medianGeneExpression"


def search_tissue_expression(gene: str, max_results: int = 5) -> list[dict]:
    """
    Tissue expression profile for a gene: Human Protein Atlas specificity
    summary plus GTEx per-tissue median TPM (top tissues by expression).
    """
    try:
        gtex_resp = requests.get(GTEX_GENE, params={"geneId": gene}, timeout=10)
        gtex_resp.raise_for_status()
        gene_hits = gtex_resp.json().get("data", [])
        exact = next((g for g in gene_hits if g.get("geneSymbol", "").upper() == gene.upper()), None)
        if not exact:
            return [{"error": f"'{gene}' not found in GTEx reference."}]

        gencode_id = exact["gencodeId"]
        ensembl_id = gencode_id.split(".")[0]

        results = []

        hpa_resp = requests.get(HPA_ENTRY.format(ensembl_id), timeout=10)
        if hpa_resp.ok:
            hpa = hpa_resp.json()
            results.append({
                "source": "Human Protein Atlas",
                "rna_tissue_specificity": hpa.get("RNA tissue specificity"),
                "rna_tissue_distribution": hpa.get("RNA tissue distribution"),
                "protein_tissue_specificity": hpa.get("Protein tissue specificity"),
                "protein_tissue_distribution": hpa.get("Protein tissue distribution"),
                "tissue_expression_cluster": hpa.get("Tissue expression cluster"),
            })
        else:
            log.warning(f"HPA lookup returned {hpa_resp.status_code} for {ensembl_id}")

        expr_resp = requests.get(
            GTEX_EXPR,
            params={"gencodeId": gencode_id, "datasetId": "gtex_v8", "itemsPerPage": 60},
            timeout=15,
        )
        expr_resp.raise_for_status()
        rows = expr_resp.json().get("data", [])
        top = sorted(rows, key=lambda r: r.get("median", 0), reverse=True)[:max_results]
        for r in top:
            results.append({
                "source": "GTEx",
                "tissue": r["tissueSiteDetailId"],
                "median_tpm": r["median"],
            })

        return results or [{"error": f"No expression data found for {gene}."}]
    except Exception as e:
        log.error(f"Tissue expression lookup failed for '{gene}': {e}", exc_info=True)
        return [{"error": str(e)}]
