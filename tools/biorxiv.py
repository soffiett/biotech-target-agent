import requests

# Europe PMC indexes bioRxiv and medRxiv preprints with a proper search API
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def search_biorxiv(query: str, max_results: int = 5) -> list[dict]:
    """
    Search bioRxiv and medRxiv preprints via Europe PMC.
    Returns recent preprints not yet in PubMed — critical for fast-moving fields.
    """
    try:
        resp = requests.get(
            EPMC_SEARCH,
            params={
                "query": query,
                "resultType": "lite",
                "pageSize": max_results,
                "format": "json",
                "src": "PPR",       # PPR = preprints only (bioRxiv + medRxiv)
                "sort": "CITED desc",
            },
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("resultList", {}).get("result", [])

        return [
            {
                "title": r.get("title", ""),
                "authors": r.get("authorString", "")[:100],
                "year": r.get("pubYear", ""),
                "abstract": r.get("abstractText", "")[:800] if r.get("abstractText") else "",
                "source": r.get("source", "PPR"),
                "doi": r.get("doi", ""),
                "url": f"https://doi.org/{r['doi']}" if r.get("doi") else "",
            }
            for r in results
        ]

    except Exception as e:
        return [{"error": str(e)}]
