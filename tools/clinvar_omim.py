import os
import time
import requests
from logger import get_logger

log = get_logger(__name__)
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def search_rare_variants(gene: str, max_results: int = 5) -> list[dict]:
    """
    Rare, high-penetrance variant evidence for a gene: pathogenic ClinVar
    classifications plus an OMIM record cross-reference.
    """
    email = os.getenv("NCBI_EMAIL", "biotech-agent@example.com")
    try:
        search_resp = requests.get(
            f"{EUTILS}/esearch.fcgi",
            params={
                "db": "clinvar",
                "term": f"{gene}[gene] AND pathogenic[clinical_significance]",
                "retmax": max_results,
                "sort": "relevance",
                "retmode": "json",
                "email": email,
            },
            timeout=10,
        )
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

        omim_ref = _fetch_omim_summary(gene, email)

        if not ids:
            log.warning(f"ClinVar returned 0 pathogenic variants for gene: '{gene}'")
            return [omim_ref] if omim_ref else [
                {"error": f"No pathogenic ClinVar variants found for {gene}."}
            ]

        time.sleep(0.4)  # NCBI rate limit: max 3 requests/sec without API key
        summary_resp = requests.get(
            f"{EUTILS}/esummary.fcgi",
            params={"db": "clinvar", "id": ",".join(ids), "retmode": "json", "email": email},
            timeout=10,
        )
        summary_resp.raise_for_status()
        result = summary_resp.json().get("result", {})

        variants = []
        for vid in result.get("uids", []):
            v = result.get(vid, {})
            classification = v.get("germline_classification", {})
            conditions = [
                t.get("trait_name") for t in classification.get("trait_set", [])
                if t.get("trait_name")
            ]
            variants.append({
                "title": v.get("title", ""),
                "clinical_significance": classification.get("description", ""),
                "review_status": classification.get("review_status", ""),
                "conditions": conditions,
                "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{vid}/",
            })

        if omim_ref:
            variants.append(omim_ref)
        return variants
    except Exception as e:
        log.error(f"ClinVar/OMIM lookup failed for '{gene}': {e}", exc_info=True)
        return [{"error": str(e)}]


def _fetch_omim_summary(gene: str, email: str) -> dict | None:
    """
    Best-effort OMIM cross-reference via NCBI E-utilities. NCBI's public `omim`
    db only exposes the gene/phenotype record title, not full phenotype-mapping
    detail (that requires a registered omim.org API key) — used here just to
    confirm a Mendelian disease-gene record exists and surface its title.
    """
    try:
        resp = requests.get(
            f"{EUTILS}/esearch.fcgi",
            params={"db": "omim", "term": f"{gene}[gene]", "retmode": "json", "retmax": 1, "email": email},
            timeout=10,
        )
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None

        time.sleep(0.4)
        summ_resp = requests.get(
            f"{EUTILS}/esummary.fcgi",
            params={"db": "omim", "id": ids[0], "retmode": "json", "email": email},
            timeout=10,
        )
        summ_resp.raise_for_status()
        rec = summ_resp.json().get("result", {}).get(ids[0], {})
        return {
            "source": "OMIM",
            "mim_number": ids[0],
            "title": rec.get("title", ""),
            "url": f"https://omim.org/entry/{ids[0]}",
        }
    except Exception as e:
        log.warning(f"OMIM lookup failed for '{gene}': {e}")
        return None
