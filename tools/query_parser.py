import anthropic
from config import SEARCH_MODEL, PARSER_MAX_TOKENS, QUERY_PARSER_SYSTEM_PROMPT

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

def parse_query(text: str) -> dict:
    """Parse free-form user text into {target, company, indication, confidence}."""
    response = _client.messages.create(
        model=SEARCH_MODEL,
        max_tokens=PARSER_MAX_TOKENS,
        system=QUERY_PARSER_SYSTEM_PROMPT,
        tools=[_PARSE_TOOL],
        tool_choice={"type": "tool", "name": "extract_query_fields"},
        messages=[{"role": "user", "content": text}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_query_fields":
            return block.input

    return {"target": "", "company": "", "indication": "", "confidence": "low"}
