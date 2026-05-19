import json
import anthropic
from tools.clinicaltrials import search_clinical_trials
from tools.web_search import search_web
from graph.state import TargetAssessmentState

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

SYSTEM_PROMPT = """You are a clinical development expert and biotech analyst.
Your task: map the clinical landscape for a drug target to assess precedent and competitive risk.

Perform 3–5 searches covering:
1. Direct trials — is this exact target already in clinical trials? What phase and status?
2. Approved drugs — are there already approved biologics for this target? (validates biology, raises competitive bar)
3. Related targets — if no direct trials, what other targets in the same pathway are in the clinic?
4. Recent failures — have any programs targeting this mechanism failed? If so, why?
5. Competitive landscape — who else is in the clinic for this target?

Summarize findings with: trial phase, status, sponsor, indication, and what it means for the target's clinical viability."""


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

    messages = [
        {
            "role": "user",
            "content": (
                f"Map the clinical landscape for **{target}** as a large molecule target.\n"
                f"Company developing it: {company}\n"
                f"Indication: {indication}\n\n"
                "Search ClinicalTrials.gov and the web, then summarize the clinical precedent, "
                "current trials, and competitive risk."
            ),
        }
    ]

    findings, errors = [], []

    for _ in range(8):
        response = _client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
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
