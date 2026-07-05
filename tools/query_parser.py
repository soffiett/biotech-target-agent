import anthropic
from config import SEARCH_MODEL, PARSER_MAX_TOKENS, QUERY_PARSER_SYSTEM_PROMPT
from models.schemas import ParsedQuery
from pydantic import ValidationError
_client = anthropic.Anthropic()

# Schema is generated from the model so the tool definition and type can't drift apart.
_PARSE_TOOL = {
    "name": "extract_query_fields",
    "description": "Extract structured fields from a free-form biotech query.",
    "input_schema": ParsedQuery.model_json_schema(),
}


def parse_query(text: str) -> ParsedQuery:
    """Parse free-form user text into a validated ParsedQuery."""
    fallback = ParsedQuery(target="", company="",
                           indication="", confidence="low")

    response = _client.messages.create(
        model=SEARCH_MODEL,
        max_tokens=PARSER_MAX_TOKENS,
        system=QUERY_PARSER_SYSTEM_PROMPT,
        tools=[_PARSE_TOOL],
        tool_choice={"type": "tool", "name": "extract_query_fields"},
        messages=[{"role": "user", "content": text}],
    )

    # A forced tool call can still be truncated if it hits the token cap,
    # yielding a partial/malformed input dict.
    if response.stop_reason == "max_tokens":
        return fallback

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_query_fields":
            try:
                return ParsedQuery.model_validate(block.input)
            except ValidationError:
                return fallback

    return fallback
