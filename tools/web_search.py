import os
import requests
from logger import get_logger

log = get_logger(__name__)


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using Tavily API."""
    log.debug(f"Tavily search: '{query}' (max={max_results})")
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": os.environ["TAVILY_API_KEY"],
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        },
        timeout=15,
    )
    resp.raise_for_status()

    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", "")[:600],
        }
        for r in resp.json().get("results", [])
    ]
