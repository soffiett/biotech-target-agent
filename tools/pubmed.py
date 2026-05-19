import os
import time
import requests
import xml.etree.ElementTree as ET

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def search_pubmed(query: str, max_results: int = 5) -> list[dict]:
    """Search PubMed and return paper summaries with abstracts."""
    email = os.getenv("NCBI_EMAIL", "biotech-agent@example.com")

    search_resp = requests.get(
        f"{PUBMED_BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "sort": "relevance",
            "retmode": "json",
            "email": email,
        },
        timeout=10,
    )
    search_resp.raise_for_status()
    ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

    if not ids:
        return []

    time.sleep(0.4)  # NCBI rate limit: max 3 requests/sec without API key

    fetch_resp = requests.get(
        f"{PUBMED_BASE}/efetch.fcgi",
        params={
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "xml",
            "rettype": "abstract",
            "email": email,
        },
        timeout=15,
    )
    fetch_resp.raise_for_status()
    return _parse_pubmed_xml(fetch_resp.text)


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    papers = []

    for article in root.findall(".//PubmedArticle"):
        try:
            pmid = article.findtext(".//PMID", "")
            title = article.findtext(".//ArticleTitle", "")
            abstract_parts = article.findall(".//AbstractText")
            abstract = " ".join(
                (p.text or "") for p in abstract_parts if p.text
            )
            year = article.findtext(".//PubDate/Year", "")

            authors = [
                a.findtext("LastName", "")
                for a in article.findall(".//Author")[:3]
                if a.findtext("LastName")
            ]

            papers.append({
                "pmid": pmid,
                "title": title,
                "abstract": abstract[:1200],
                "year": year,
                "authors": ", ".join(authors),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })
        except Exception:
            continue

    return papers
