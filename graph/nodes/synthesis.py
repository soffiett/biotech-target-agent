import copy
import anthropic
from pydantic import ValidationError
from rag.vectorstore import query_knowledge_base
from graph.state import TargetAssessmentState
from models.schemas import AssessmentReport
from config import (
    SYNTHESIS_MODEL,
    SYNTHESIS_MAX_TOKENS,
    RAG_TOP_K,
    SYNTHESIS_SYSTEM_PROMPT,
)
from logger import get_logger

log = get_logger(__name__)

_client = anthropic.Anthropic()


def _resolve_refs(schema: dict) -> dict:
    """
    Inline $defs/$ref entries produced by Pydantic so the schema is
    self-contained. The Anthropic tool API does not support $ref references.
    """
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def _inline(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                resolved = {k: v for k, v in defs.get(ref_name, obj).items()
                            if k != "title"}
                return resolved
            return {k: _inline(v) for k, v in obj.items() if k != "title"}
        if isinstance(obj, list):
            return [_inline(i) for i in obj]
        return obj

    return _inline(schema)


def _build_report_tool_schema() -> dict:
    """
    Derive the tool input_schema from AssessmentReport.
    target and company are injected from LangGraph state, not filled by the LLM.
    """
    raw = AssessmentReport.model_json_schema()
    schema = _resolve_refs(raw)
    for field in ("target", "company"):
        schema.get("properties", {}).pop(field, None)
        if field in schema.get("required", []):
            schema["required"].remove(field)
    return schema


# Tool schema is generated from the Pydantic model — descriptions stay in one place.
REPORT_TOOL = {
    "name": "create_assessment_report",
    "description": "Submit the final structured assessment of the drug target.",
    "input_schema": _build_report_tool_schema(),
}


def synthesis_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    bio_findings = state.get("bio_findings", [])
    trial_findings = state.get("trial_findings", [])

    # Pull relevant frameworks from the knowledge base
    rag_results = query_knowledge_base(
        f"large molecule drug target validation {target} druggability clinical",
        n_results=RAG_TOP_K,
    )
    rag_context = "\n\n".join(
        f"[{r['source']}]\n{r['content']}" for r in rag_results
    ) or "No additional context retrieved."

    bio_context = "\n\n".join(
        f["content"] for f in bio_findings if f.get("content")
    ) or "No biology findings available."

    trial_context = "\n\n".join(
        f["content"] for f in trial_findings if f.get("content")
    ) or "No clinical trial findings available."

    user_message = f"""Synthesize the following research to assess: **{target}** (Company: {company})

## Biology Research
{bio_context}

## Clinical Trial Landscape
{trial_context}

## Knowledge Base: Target Validation Frameworks
{rag_context}

Now create the structured assessment report."""

    response = _client.messages.create(
        model=SYNTHESIS_MODEL,
        max_tokens=SYNTHESIS_MAX_TOKENS,
        system=SYNTHESIS_SYSTEM_PROMPT,
        tools=[REPORT_TOOL],
        tool_choice={"type": "tool", "name": "create_assessment_report"},
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        log.error(
            f"[{target}/{company}] Synthesis hit max_tokens — "
            "report tool call was truncated and cannot be used"
        )
        return {
            "report": {},
            "errors": [
                "Synthesis agent hit token limit before completing the report. "
                "Try a shorter indication or reduce context size."
            ],
        }

    report = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_assessment_report":
            try:
                validated = AssessmentReport.model_validate({
                    **block.input,
                    "target": target,
                    "company": company,
                })
                report = validated.model_dump()
                log.info(
                    f"[{target}/{company}] Synthesis done — "
                    f"recommendation={report['recommendation']} "
                    f"confidence={report['confidence_score']}"
                )
            except ValidationError as e:
                log.warning(
                    f"[{target}/{company}] Report validation failed: {e} — using raw output")
                report = {**block.input, "target": target, "company": company}
            break

    if not report:
        log.error(f"[{target}/{company}] Synthesis failed — no report returned")

    return {"report": report}
