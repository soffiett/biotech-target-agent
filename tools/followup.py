"""
Follow-up Q&A — single Sonnet call grounded in the completed assessment report.

Not a LangGraph node: no orchestration needed, no cross-node state sharing.
The report is injected into the system prompt; conversation history is managed
by the caller (st.session_state in app.py).
"""

import anthropic
from config import FOLLOWUP_MODEL, FOLLOWUP_MAX_TOKENS
from logger import get_logger

log = get_logger(__name__)

_client = anthropic.Anthropic()

_SYSTEM_TEMPLATE = """You are a drug discovery analyst answering follow-up questions \
about a completed target assessment report.

## Assessment: {target} ({company}) — {indication}

Recommendation: {recommendation} | Confidence: {confidence_score}/10
Summary: {recommendation_summary}

### Biology Rationale
{biology_rationale}

### Large Molecule Druggability
{druggability_assessment}

### Clinical Precedent
{clinical_precedent}

### Competitive Landscape
{competitive_landscape}

### Key Risks
{key_risks}

### Confidence Score Reasoning
{confidence_reasoning}

---

Rules you must follow:
1. Begin every answer by naming the report section(s) you are drawing from, \
e.g. "From the Biology Rationale section: ..."
2. If the answer is not in the report, respond with exactly: \
"This report does not cover that. Consider re-running the assessment with a more specific query."
3. Never speculate about specific trial results, drug approvals, or safety data \
beyond what is stated in the report above.
4. If the user asks for medical or investment advice, decline and redirect to the report findings.
5. Keep answers concise — 2–4 sentences unless the question genuinely requires more detail."""


def _format_system_prompt(report: dict, target: str, company: str, indication: str) -> str:
    risks = report.get("key_risks", [])
    risks_text = "\n".join(f"- {r}" for r in risks) if risks else "None listed."

    return _SYSTEM_TEMPLATE.format(
        target=target,
        company=company,
        indication=indication or "not specified",
        recommendation=report.get("recommendation", "N/A"),
        confidence_score=report.get("confidence_score", "N/A"),
        recommendation_summary=report.get("recommendation_summary", ""),
        biology_rationale=report.get("biology_rationale", ""),
        druggability_assessment=report.get("druggability_assessment", ""),
        clinical_precedent=report.get("clinical_precedent", ""),
        competitive_landscape=report.get("competitive_landscape", ""),
        key_risks=risks_text,
        confidence_reasoning=report.get("confidence_reasoning", ""),
    )


def ask_followup(
    question: str,
    report: dict,
    target: str,
    company: str,
    indication: str,
    history: list[dict],
) -> str:
    """
    Send a follow-up question grounded in the assessment report.

    Args:
        question:   The user's current question.
        report:     The completed report dict from synthesis_node.
        target:     Drug target name (for system prompt context).
        company:    Company name.
        indication: Disease indication.
        history:    Prior turns as [{"role": "user"|"assistant", "content": str}, ...].
                    Should NOT include the current question — this function appends it.

    Returns:
        The assistant's answer as a plain string.
    """
    system = _format_system_prompt(report, target, company, indication)
    messages = history + [{"role": "user", "content": question}]

    log.info(f"[{target}/{company}] Follow-up question (turn {len(history) // 2 + 1})")

    response = _client.messages.create(
        model=FOLLOWUP_MODEL,
        max_tokens=FOLLOWUP_MAX_TOKENS,
        system=system,
        messages=messages,
    )

    answer = response.content[0].text if response.content else (
        "I was unable to generate a response. Please try rephrasing your question."
    )

    log.info(f"[{target}/{company}] Follow-up answered — {response.usage.output_tokens} tokens")
    return answer
