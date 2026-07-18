import re
import requests
from logger import get_logger

log = get_logger(__name__)
REACTOME_SEARCH = "https://reactome.org/ContentService/search/query"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text or "")


def search_pathways(gene: str, max_results: int = 5) -> list[dict]:
    """Pathways containing a gene/protein, from Reactome."""
    try:
        resp = requests.get(
            REACTOME_SEARCH,
            params={
                "query": gene,
                "species": "Homo sapiens",
                "types": "Pathway",
                "cluster": "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        entries = []
        for group in resp.json().get("results", []):
            entries.extend(group.get("entries", []))

        pathways = [e for e in entries if e.get("type") == "Pathway"][:max_results]
        if not pathways:
            return [{"error": f"No Reactome pathways found for {gene}."}]

        return [
            {
                "name": _strip_tags(p.get("name", "")),
                "reactome_id": p.get("stId", ""),
                "summary": _strip_tags(p.get("summation", ""))[:400],
                "url": f"https://reactome.org/content/detail/{p.get('stId', '')}",
            }
            for p in pathways
        ]
    except Exception as e:
        log.error(f"Reactome lookup failed for '{gene}': {e}", exc_info=True)
        return [{"error": str(e)}]
