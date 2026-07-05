import json
import time
import anthropic
from tools.clinicaltrials import search_clinical_trials
from tools.web_search import search_web
from graph.state import TargetAssessmentState
from logger import get_logger
from config import (
    SEARCH_MODEL,
    SEARCH_MAX_TOKENS,
    MAX_TOOL_ITERATIONS,
    CLINICAL_TRIALS_SYSTEM_PROMPT,
)

_client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "search_clinical_trials",
        "description": (
            "Search ClinicalTrials.gov for studies. Use to find: trials for this exact target, "
            "trials for drugs with the same mechanism, or related pathway targets in the clinic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — can be target name, drug name, or disease + mechanism.",
                },
                "max_results": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web for clinical trial news, pipeline updates, FDA decisions, "
            "or competitor program status not captured on ClinicalTrials.gov."
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
        if name == "search_clinical_trials":
            return json.dumps(search_clinical_trials(inputs["query"], inputs.get("max_results", 10)))
        if name == "search_web":
            return json.dumps(search_web(inputs["query"], inputs.get("max_results", 5)))
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": "unknown tool"})


def _harvest_text(content) -> list[dict]:
    """Pull any non-empty text blocks into finding dicts."""
    out = []
    for block in content:
        if hasattr(block, "text") and block.text.strip():
            out.append({
                "type": "trial_summary",
                "content": block.text,
                "source": "clinical_trials_agent",
            })
    return out


def clinical_trials_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    indication = state.get("indication", "not specified")

    prefetch_summary = state.get("prefetch_context", {}).get("combined_summary", "")

    clinical_focus = state.get("prefetch_context", {}).get(
        "clinical_focus",
        "Search broadly for any clinical programs targeting this pathway.",
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Map the clinical landscape for **{target}** as a large molecule target.\n"
                f"Company developing it: {company}\n"
                f"Indication: {indication}\n\n"
                f"## Pre-fetched Evidence Baseline\n{prefetch_summary}\n\n"
                f"## Your Research Focus\n{clinical_focus}\n\n"
                "Search ClinicalTrials.gov and the web. Address the focus areas above — "
                "do not re-confirm what the baseline already lists."
            ),
        }
    ]

    findings, errors = [], []
    tool_call_count = 0
    log = get_logger(__name__)
    log.info(f"[{target}/{company}] Clinical trials agent started")

    for _ in range(MAX_TOOL_ITERATIONS):
        # Retry up to 3 times on rate limit with exponential backoff
        for attempt in range(3):
            try:
                response = _client.messages.create(
                    model=SEARCH_MODEL,
                    max_tokens=SEARCH_MAX_TOKENS,
                    system=CLINICAL_TRIALS_SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                wait = 30 * (attempt + 1)
                log.warning(f"[{target}/{company}] Rate limit hit (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
        else:
            errors.append("Clinical trials agent hit rate limit after 3 retries.")
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "max_tokens":
            log.warning(
                f"[{target}/{company}] Clinical trials response truncated at max_tokens "
                f"(iteration {_ + 1})"
            )
            partial = _harvest_text(response.content)
            if partial:
                findings.extend(partial)
                log.info(
                    f"[{target}/{company}] Salvaged {len(partial)} partial finding(s) before truncation")
            truncated_tool_call = any(
                getattr(b, "type", None) == "tool_use" for b in response.content
            )
            if truncated_tool_call:
                errors.append(
                    "Clinical trials agent truncated mid-tool-call; findings may be incomplete.")
            else:
                errors.append(
                    "Clinical trials agent truncated mid-text; findings may be incomplete.")
            break

        if response.stop_reason == "end_turn":
            findings.extend(_harvest_text(response.content))
            log.info(f"[{target}/{company}] Trial agent done — {tool_call_count} tool calls, {len(findings)} findings")
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call_count += 1
                    log.debug(f"[{target}/{company}] Trial tool call: {block.name}({block.input.get('query', '')})")
                    result = _run_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})
            continue

        log.warning(
            f"[{target}/{company}] Unexpected stop_reason '{response.stop_reason}' — ending loop")
        errors.append(
            f"Clinical trials agent ended on unexpected stop_reason: {response.stop_reason}")
        break

    return {"trial_findings": findings, "errors": errors}
