import json
import anthropic
from tools.clinicaltrials import search_clinical_trials
from tools.web_search import search_web
from graph.state import TargetAssessmentState
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


def clinical_trials_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    indication = state.get("indication", "not specified")

    prefetch_summary = state.get("prefetch_context", {}).get("combined_summary", "")

    messages = [
        {
            "role": "user",
            "content": (
                f"Map the clinical landscape for **{target}** as a large molecule target.\n"
                f"Company developing it: {company}\n"
                f"Indication: {indication}\n\n"
                f"## Pre-fetched Evidence Baseline\n{prefetch_summary}\n\n"
                "The known drugs above are a starting point — search ClinicalTrials.gov to get "
                "current phase, status, and any recent updates. Investigate failures and gaps."
            ),
        }
    ]

    findings, errors = [], []

    for _ in range(MAX_TOOL_ITERATIONS):
        response = _client.messages.create(
            model=SEARCH_MODEL,
            max_tokens=SEARCH_MAX_TOKENS,
            system=CLINICAL_TRIALS_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text") and block.text.strip():
                    findings.append({"type": "trial_summary", "content": block.text, "source": "clinical_trials_agent"})
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _run_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})

    return {"trial_findings": findings, "errors": errors}
