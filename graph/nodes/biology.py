import json
import anthropic
from tools.pubmed import search_pubmed
from tools.web_search import search_web
from graph.state import TargetAssessmentState

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

SYSTEM_PROMPT = """You are a computational biologist and drug discovery scientist specializing in biologics.
Your task: research a drug target to assess the biological rationale for a large molecule therapeutic.

Cover these areas using 4–6 targeted searches:
1. Disease biology — what role does this target play in the disease mechanism?
2. Genetic / human evidence — GWAS hits, LOF variants, Mendelian randomization studies?
3. Preclinical validation — animal models, in vitro studies, patient tissue data?
4. Target expression — is it expressed in disease tissue but limited in normal tissue?
5. Company approach — what is the company's specific biological hypothesis?
6. Safety signals — any known on-target toxicity concerns?

After your searches, write a structured summary covering each area. Be concise and evidence-based."""


def _run_tool(name: str, inputs: dict) -> str:
    try:
        if name == "search_pubmed":
            return json.dumps(search_pubmed(inputs["query"], inputs.get("max_results", 5)))
        if name == "search_web":
            return json.dumps(search_web(inputs["query"], inputs.get("max_results", 5)))
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": "unknown tool"})


def biology_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    indication = state.get("indication", "not specified")

    messages = [
        {
            "role": "user",
            "content": (
                f"Assess the biological rationale for targeting **{target}** as a large molecule therapeutic.\n"
                f"Company: {company}\n"
                f"Indication: {indication}\n\n"
                f"Search PubMed and the web, then provide your structured findings."
            ),
        }
    ]

    findings, errors = [], []

    for _ in range(8):  # max tool-call iterations
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
                    findings.append({"type": "biology_summary", "content": block.text, "source": "biology_agent"})
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _run_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})

    return {"bio_findings": findings, "errors": errors}
