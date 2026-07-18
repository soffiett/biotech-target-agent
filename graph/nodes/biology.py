import json
import time
import anthropic
from tools.pubmed import search_pubmed
from tools.web_search import search_web
from tools.biorxiv import search_biorxiv
from tools.gwas import search_gwas_evidence
from tools.clinvar_omim import search_rare_variants
from tools.depmap import search_crispr_dependency
from tools.expression import search_tissue_expression
from tools.reactome import search_pathways
from graph.state import TargetAssessmentState
from config import (
    SEARCH_MODEL,
    SEARCH_MAX_TOKENS,
    MAX_TOOL_ITERATIONS,
    BIOLOGY_SYSTEM_PROMPT,
)
from models.schemas import BiologyFinding
from logger import get_logger
from observability.tracker import get_tracker

log = get_logger(__name__)

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
        "name": "search_biorxiv",
        "description": (
            "Search bioRxiv and medRxiv preprints. Use for cutting-edge findings not yet "
            "peer-reviewed — especially useful for fast-moving targets in immunology or oncology."
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
    {
        "name": "search_gwas_evidence",
        "description": (
            "Human genetic association evidence for the target-indication pair, from GWAS "
            "credible sets via OpenTargets (L2G-scored). Strongest tier of evidence — use early. "
            "Automatically scoped to the current target and indication."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "default": 5}},
        },
    },
    {
        "name": "search_rare_variants",
        "description": (
            "Rare, high-penetrance variant evidence for the target from ClinVar (pathogenic "
            "classifications + associated conditions) with an OMIM cross-reference. "
            "Strongest tier of evidence for Mendelian disease genes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "default": 5}},
        },
    },
    {
        "name": "search_crispr_dependency",
        "description": (
            "CRISPR knockout dependency (DepMap gene-effect scores) for the target, broken down "
            "by tissue/cell-line. Shows whether cells require this gene to survive — strong "
            "functional evidence, but skewed toward cancer cell lines."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "default": 5}},
        },
    },
    {
        "name": "search_tissue_expression",
        "description": (
            "Tissue expression profile for the target from Human Protein Atlas (specificity "
            "summary) and GTEx (per-tissue median TPM). Indicates disease-tissue relevance and "
            "on-target safety risk from expression in normal tissue — necessary but not "
            "sufficient evidence on its own."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "default": 5}},
        },
    },
    {
        "name": "search_pathways",
        "description": (
            "Pathways containing the target, from Reactome. Useful for mechanism-of-action "
            "context and identifying related druggable nodes — indirect evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"max_results": {"type": "integer", "default": 5}},
        },
    },
]

# Evidence-type tag per tool, used to label structured findings for synthesis weighting.
EVIDENCE_TYPE_BY_TOOL = {
    "search_gwas_evidence": "human_genetics",
    "search_rare_variants": "rare_variant",
    "search_crispr_dependency": "crispr_dependency",
    "search_tissue_expression": "tissue_expression",
    "search_pathways": "pathway_biology",
    "search_pubmed": "literature",
    "search_biorxiv": "preprint",
    "search_web": "company_disclosure",
}

def _run_tool(name: str, inputs: dict, target: str, indication: str) -> list[dict]:
    """Dispatch a tool call and return its raw structured result (list of dicts)."""
    try:
        max_results = inputs.get("max_results", 5)
        if name == "search_pubmed":
            return search_pubmed(inputs["query"], max_results)
        if name == "search_biorxiv":
            return search_biorxiv(inputs["query"], max_results)
        if name == "search_web":
            return search_web(inputs["query"], max_results)
        if name == "search_gwas_evidence":
            return search_gwas_evidence(target, indication, max_results)
        if name == "search_rare_variants":
            return search_rare_variants(target, max_results)
        if name == "search_crispr_dependency":
            return search_crispr_dependency(target, max_results)
        if name == "search_tissue_expression":
            return search_tissue_expression(target, max_results)
        if name == "search_pathways":
            return search_pathways(target, max_results)
    except Exception as e:
        return [{"error": str(e)}]
    return [{"error": "unknown tool"}]


def _format_tool_result(results: list[dict]) -> str:
    """Render a tool's structured results as compact, readable lines for downstream synthesis."""
    lines = []
    for item in results:
        if not isinstance(item, dict):
            continue
        if "error" in item:
            lines.append(f"(no data: {item['error']})")
            continue
        lines.append("; ".join(f"{k}={v}" for k, v in item.items() if v not in (None, "", [])))
    return "\n".join(lines)


def _trim_tool_result(result: str, max_chars: int = 4000) -> str:
    """
    Truncate a tool result before it enters the message history.
    Each search returns up to 5 results as JSON — without trimming, 5 iterations
    × 5 results × ~400 chars each = ~10k chars of accumulated context, leaving
    little room for the model to generate its final summary.
    """
    if len(result) <= max_chars:
        return result
    return result[:max_chars] + f"\n... [truncated at {max_chars} chars to limit context size]"


def _harvest_text(content) -> list[dict]:
    """Pull any non-empty text blocks into validated BiologyFinding dicts."""
    out = []
    for block in content:
        if hasattr(block, "text") and block.text.strip():
            out.append(
                BiologyFinding(
                    type="biology_summary",
                    content=block.text,
                    source="biology_agent",
                ).model_dump()
            )
    return out


def biology_node(state: TargetAssessmentState) -> dict:
    target = state["target"]
    company = state["company"]
    indication = state.get("indication", "not specified")
    prefetch_summary = state.get(
        "prefetch_context", {}).get("combined_summary", "")

    biology_focus = state.get("prefetch_context", {}).get(
        "biology_focus",
        "Cover all areas: target biology, genetic evidence, disease mechanism, and druggability.",
    )

    judge_critique = state.get("judge_critique")
    rerun_count = state.get("rerun_count", 0)

    past_queries = state.get("bio_search_queries", [])

    if judge_critique and rerun_count > 0:
        issues = "\n".join(
            f"  - {i}" for i in judge_critique.get("biology_issues", []))
        past_block = (
            "\n## Searches Already Completed (DO NOT REPEAT)\n"
            + "\n".join(f"  - {q}" for q in past_queries)
            if past_queries else ""
        )
        critique_section = (
            f"\n\n## Judge Critique — Previous Attempt Scored {judge_critique['biology_score']}/5\n"
            f"Specific issues identified:\n{issues}\n"
            f"Required improvement: {judge_critique.get('top_improvement', '')}\n"
            f"{past_block}\n\n"
            "Focus exclusively on the gaps above. Use different search queries from any listed above."
        )
        log.info(f"[{target}/{company}] Biology re-run (attempt {rerun_count + 1}) — "
                 f"addressing judge critique, {len(past_queries)} past queries injected")
    else:
        critique_section = ""

    messages = [
        {
            "role": "user",
            "content": (
                f"Assess the biological rationale for targeting **{target}**.\n"
                f"Company: {company}\n"
                f"Indication: {indication}\n\n"
                f"## Pre-fetched Evidence Baseline\n{prefetch_summary}\n\n"
                f"## Your Research Focus\n{biology_focus}\n"
                f"{critique_section}\n"
                "Use the genetics, rare-variant, CRISPR-dependency, expression, and pathway tools "
                "for structured evidence, and PubMed/bioRxiv/web search for narrative context. "
                "Address the focus areas above — do not re-confirm what the baseline already establishes."
            ),
        }
    ]

    findings, errors, search_queries = [], [], []
    tool_call_count = 0
    total_input_tokens = total_output_tokens = 0
    _t0 = time.perf_counter()
    log.info(f"[{target}/{company}] Biology agent started")

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Retry up to 3 times on rate limit with exponential backoff
        for attempt in range(3):
            try:
                response = _client.messages.create(
                    model=SEARCH_MODEL,
                    max_tokens=SEARCH_MAX_TOKENS,
                    system=BIOLOGY_SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError:
                wait = 30 * (attempt + 1)
                log.warning(
                    f"[{target}/{company}] Rate limit hit (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
        else:
            errors.append("Biology agent hit rate limit after 3 retries.")
            break

        messages.append({"role": "assistant", "content": response.content})
        total_input_tokens  += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # --- NEW: handle truncation explicitly ---
        if response.stop_reason == "max_tokens":
            log.warning(
                f"[{target}/{company}] Biology response truncated at max_tokens "
                f"(iteration {iteration + 1})"
            )
            # Salvage any partial text the model did produce before the cutoff.
            partial = _harvest_text(response.content)
            if partial:
                findings.extend(partial)
                log.info(
                    f"[{target}/{company}] Salvaged {len(partial)} partial finding(s) before truncation")

            # If it was cut off mid-tool-call, the tool_use block may be malformed
            # or unanswerable — do not attempt to run it. Record and stop cleanly.
            truncated_tool_call = any(
                getattr(b, "type", None) == "tool_use" for b in response.content
            )
            if truncated_tool_call:
                errors.append(
                    "Biology agent truncated mid-tool-call; findings may be incomplete.")
            else:
                errors.append(
                    "Biology agent truncated mid-text; findings may be incomplete.")
            break
        # --- END NEW ---

        if response.stop_reason == "end_turn":
            findings.extend(_harvest_text(response.content))
            log.info(
                f"[{target}/{company}] Biology agent done — {tool_call_count} tool calls, {len(findings)} findings")
            break

        if response.stop_reason == "tool_use":
            # Harvest any text the agent wrote before calling the tool — this is
            # the agent's analysis of what the previous search found, and is
            # substantive evidence even though the turn isn't over yet.
            interim = _harvest_text(response.content)
            if interim:
                findings.extend(interim)
                log.debug(f"[{target}/{company}] Harvested {len(interim)} interim finding(s) at iteration {iteration + 1}")

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_call_count += 1
                    query_str = block.input.get("query", "")
                    log.debug(
                        f"[{target}/{company}] Biology tool call: {block.name}({query_str})")
                    if query_str:
                        search_queries.append(f"[{block.name}] {query_str}")

                    raw_result = _run_tool(block.name, block.input, target, indication)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _trim_tool_result(json.dumps(raw_result)),
                    })

                    formatted = _format_tool_result(raw_result)
                    if formatted:
                        findings.append(
                            BiologyFinding(
                                type="tool_evidence",
                                content=formatted,
                                source=block.name,
                                evidence_type=EVIDENCE_TYPE_BY_TOOL.get(block.name, "agent_narrative"),
                            ).model_dump()
                        )
            messages.append({"role": "user", "content": tool_results})
            continue

        # --- NEW: unknown stop_reason — don't silently spin ---
        log.warning(
            f"[{target}/{company}] Unexpected stop_reason '{response.stop_reason}' — ending loop")
        errors.append(
            f"Biology agent ended on unexpected stop_reason: {response.stop_reason}")
        break

    tracker = get_tracker()
    if tracker:
        tracker.record_node(
            "biology",
            model=SEARCH_MODEL,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            latency_s=time.perf_counter() - _t0,
            tool_calls=tool_call_count,
            error=bool(errors),
        )

    return {
        "bio_findings": findings,
        "errors": errors,
        "rerun_count": rerun_count + 1,
        "bio_search_queries": search_queries,
    }
