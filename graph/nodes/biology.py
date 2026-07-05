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
from models.schemas import BiologyFinding
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


def _harvest_text(content) -> list[dict]:
    """Pull any non-empty text blocks into validated BiologyFinding dicts."""
    out = []
    for block in content:
        if hasattr(block, "text") and block.text.strip():
            out.append(
                BiologyFinding(
                    type="biology_summary",
                    content=block.text,
                    source="biology_agent",
                ).model_dump()
            )
    return out


def biology_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    indication = state.get("indication", "not specified")
    prefetch_summary = state.get(
        "prefetch_context", {}).get("combined_summary", "")

    biology_focus = state.get("prefetch_context", {}).get(
        "biology_focus",
        "Cover all areas: target biology, genetic evidence, disease mechanism, and druggability.",
    )

    judge_critique = state.get("judge_critique")
    rerun_count = state.get("rerun_count", 0)

    if judge_critique and rerun_count > 0:
        issues = "\n".join(
            f"  - {i}" for i in judge_critique.get("biology_issues", []))
        critique_section = (
            f"\n\n## Judge Critique — Previous Attempt Scored {judge_critique['biology_score']}/5\n"
            f"Specific issues identified:\n{issues}\n"
            f"Required improvement: {judge_critique.get('top_improvement', '')}\n\n"
            "Your previous biology findings are already recorded in state — do NOT repeat searches "
            "you already ran. Focus exclusively on the gaps above."
        )
        log.info(f"[{target}/{company}] Biology re-run (attempt {rerun_count + 1}) — "
                 f"addressing judge critique")
    else:
        critique_section = ""

    messages = [
        {
            "role": "user",
            "content": (
                f"Assess the biological rationale for targeting **{target}** as a large molecule therapeutic.\n"
                f"Company: {company}\n"
                f"Indication: {indication}\n\n"
                f"## Pre-fetched Evidence Baseline\n{prefetch_summary}\n\n"
                f"## Your Research Focus\n{biology_focus}\n"
                f"{critique_section}\n"
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
                log.warning(
                    f"[{target}/{company}] Rate limit hit (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
        else:
            errors.append("Biology agent hit rate limit after 3 retries.")
            break

        messages.append({"role": "assistant", "content": response.content})

        # --- NEW: handle truncation explicitly ---
        if response.stop_reason == "max_tokens":
            log.warning(
                f"[{target}/{company}] Biology response truncated at max_tokens "
                f"(iteration {iteration + 1})"
            )
            # Salvage any partial text the model did produce before the cutoff.
            partial = _harvest_text(response.content)
            if partial:
                findings.extend(partial)
                log.info(
                    f"[{target}/{company}] Salvaged {len(partial)} partial finding(s) before truncation")

            # If it was cut off mid-tool-call, the tool_use block may be malformed
            # or unanswerable — do not attempt to run it. Record and stop cleanly.
            truncated_tool_call = any(
                getattr(b, "type", None) == "tool_use" for b in response.content
            )
            if truncated_tool_call:
                errors.append(
                    "Biology agent truncated mid-tool-call; findings may be incomplete.")
            else:
                errors.append(
                    "Biology agent truncated mid-text; findings may be incomplete.")
            break
        # --- END NEW ---

        if response.stop_reason == "end_turn":
            findings.extend(_harvest_text(response.content))
            log.info(
                f"[{target}/{company}] Biology agent done — {tool_call_count} tool calls, {len(findings)} findings")
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call_count += 1
                    log.debug(
                        f"[{target}/{company}] Biology tool call: {block.name}({block.input.get('query', '')})")
                    result = _run_tool(block.name, block.input)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})
            continue

        # --- NEW: unknown stop_reason — don't silently spin ---
        log.warning(
            f"[{target}/{company}] Unexpected stop_reason '{response.stop_reason}' — ending loop")
        errors.append(
            f"Biology agent ended on unexpected stop_reason: {response.stop_reason}")
        break

    return {
        "bio_findings": findings,
        "errors": errors,
        "rerun_count": rerun_count + 1,
    }
