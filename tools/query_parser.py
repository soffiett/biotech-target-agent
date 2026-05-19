import anthropic

_client = anthropic.Anthropic()

_PARSE_TOOL = {
    "name": "extract_query_fields",
    "description": "Extract structured fields from a free-form biotech query.",
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "The drug target or molecule (e.g. PD-L1, IL-6R, VEGF, HER2). Empty string if not found.",
            },
            "company": {
                "type": "string",
                "description": "The biotech or pharma company name. Empty string if not found.",
            },
            "indication": {
                "type": "string",
                "description": "The disease or therapeutic indication (e.g. NSCLC, rheumatoid arthritis). Empty string if not found.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "low"],
                "description": "'high' if all key fields were clearly stated, 'low' if ambiguous or missing fields.",
            },
        },
        "required": ["target", "company", "indication", "confidence"],
    },
}

_SYSTEM = (
    "You are a biotech query parser. Extract the drug target, company, and indication "
    "from the user's free-form input. Be liberal in interpretation — infer from context "
    "when possible (e.g. 'Roche's cancer antibody targeting VEGF' → target=VEGF, company=Roche, indication=cancer). "
    "Use standard nomenclature for targets (e.g. 'PDL1' → 'PD-L1')."
)


def parse_query(text: str) -> dict:
    """Parse free-form user text into {target, company, indication, confidence}."""
    response = _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=_SYSTEM,
        tools=[_PARSE_TOOL],
        tool_choice={"type": "tool", "name": "extract_query_fields"},
        messages=[{"role": "user", "content": text}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_query_fields":
            return block.input

    return {"target": "", "company": "", "indication": "", "confidence": "low"}
