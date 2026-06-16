import json
import time
import anthropic
from tools.pubmed import search_pubmed
from tools.web_search import search_web
from tools.biorxiv import search_biorxiv
from graph.state import TargetAssessmentState
from config import (
    SEARCH_MODEL,
    SEARCH_MAX_TOKENS,
    MAX_TOOL_ITERATIONS,
    BIOLOGY_SYSTEM_PROMPT,
)
from logger import get_logger

log = get_logger(__name__)

_client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "search_pubmed",
        "description": (
            "Search PubMed for peer-reviewed publications. Use for: target biology, "
            "disease mechanism, genetic evidence, animal models, biomarker studies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "PubMed query. Use MeSH terms and boolean operators.",
                },
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_biorxiv",
        "description": (
            "Search bioRxiv and medRxiv preprints. Use for cutting-edge findings not yet "
            "peer-reviewed — especially useful for fast-moving targets in immunology or oncology."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web for company pipeline info, press releases, investor presentations, "
            "and recent news not yet in PubMed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
]


def _run_tool(name: str, inputs: dict) -> str:
    try:
        if name == "search_pubmed":
            return json.dumps(search_pubmed(inputs["query"], inputs.get("max_results", 5)))
        if name == "search_biorxiv":
            return json.dumps(search_biorxiv(inputs["query"], inputs.get("max_results", 5)))
        if name == "search_web":
            return json.dumps(search_web(inputs["query"], inputs.get("max_results", 5)))
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": "unknown tool"})


def biology_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    indication = state.get("indication", "not specified")
    prefetch_summary = state.get("prefetch_context", {}).get("combined_summary", "")

    biology_focus = state.get("prefetch_context", {}).get(
        "biology_focus",
        "Cover all areas: target biology, genetic evidence, disease mechanism, and druggability.",
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Assess the biological rationale for targeting **{target}** as a large molecule therapeutic.\n"
                f"Company: {company}\n"
                f"Indication: {indication}\n\n"
                f"## Pre-fetched Evidence Baseline\n{prefetch_summary}\n\n"
                f"## Your Research Focus\n{biology_focus}\n\n"
                "Search PubMed, bioRxiv, and the web. Address the focus areas above — "
                "do not re-confirm what the baseline already establishes."
            ),
        }
    ]

    findings, errors = [], []
    tool_call_count = 0

    log.info(f"[{target}/{company}] Biology agent started")

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Retry up to 3 times on rate limit with exponential backoff
        for attempt in range(3):
            try:
                response = _client.messages.create(
                    model=SEARCH_MODEL,
                    max_tokens=SEARCH_MAX_TOKENS,
                    system=BIOLOGY_SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                wait = 30 * (attempt + 1)
                log.warning(f"[{target}/{company}] Rate limit hit (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
        else:
            errors.append("Biology agent hit rate limit after 3 retries.")
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text") and block.text.strip():
                    findings.append({"type": "biology_summary", "content": block.text, "source": "biology_agent"})
            log.info(f"[{target}/{company}] Biology agent done — {tool_call_count} tool calls, {len(findings)} findings")
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call_count += 1
                    log.debug(f"[{target}/{company}] Biology tool call: {block.name}({block.input.get('query', '')})")
                    result = _run_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})

    return {"bio_findings": findings, "errors": errors}
