import anthropic
from rag.vectorstore import query_knowledge_base
from graph.state import TargetAssessmentState
from config import (
    SYNTHESIS_MODEL,
    SYNTHESIS_MAX_TOKENS,
    RAG_TOP_K,
    SYNTHESIS_SYSTEM_PROMPT,
)

_client = anthropic.Anthropic()

# Force structured output via tool use
REPORT_TOOL = {
    "name": "create_assessment_report",
    "description": "Submit the final structured assessment of the drug target.",
    "input_schema": {
        "type": "object",
        "properties": {
            "biology_rationale": {
                "type": "string",
                "description": "Assessment of biological evidence supporting this target (genetic, preclinical, mechanistic).",
            },
            "druggability_assessment": {
                "type": "string",
                "description": "Assessment of whether this target is suitable for a large molecule approach — accessibility, format, PK considerations.",
            },
            "clinical_precedent": {
                "type": "string",
                "description": "Summary of existing clinical trials for this target or related mechanisms, including phase and status.",
            },
            "competitive_landscape": {
                "type": "string",
                "description": "Overview of other programs (approved or in development) targeting this biology.",
            },
            "key_risks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Top 3–5 risks or concerns. Be specific.",
            },
            "confidence_score": {
                "type": "number",
                "description": "0–10. 8–10: highly validated target, clear path. 5–7: moderate evidence, meaningful uncertainties. 0–4: weak evidence or significant red flags.",
            },
            "confidence_reasoning": {
                "type": "string",
                "description": "Explain what drives the score up and what holds it back.",
            },
            "recommendation": {
                "type": "string",
                "enum": ["Strong", "Moderate", "Weak", "Against"],
                "description": "Strong: pursue. Moderate: worth exploring with caveats. Weak: significant concerns. Against: fundamental issues.",
            },
            "recommendation_summary": {
                "type": "string",
                "description": "2–3 sentence plain-English summary of the assessment for a non-expert audience.",
            },
        },
        "required": [
            "biology_rationale",
            "druggability_assessment",
            "clinical_precedent",
            "competitive_landscape",
            "key_risks",
            "confidence_score",
            "confidence_reasoning",
            "recommendation",
            "recommendation_summary",
        ],
    },
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

    report = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_assessment_report":
            report = block.input
            break

    return {"report": report}
