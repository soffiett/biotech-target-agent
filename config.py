# ── Model names ──────────────────────────────────────────────────────────────
# Haiku: fast and cheap — used for search agents and query parsing
SEARCH_MODEL = "claude-haiku-4-5"

# Sonnet: stronger reasoning — used for the final synthesis report
SYNTHESIS_MODEL = "claude-sonnet-4-6"

# ── Token limits ──────────────────────────────────────────────────────────────
SEARCH_MAX_TOKENS = 2048
SYNTHESIS_MAX_TOKENS = 4096
PARSER_MAX_TOKENS = 256

# ── Agentic loop ──────────────────────────────────────────────────────────────
# Max number of tool-call iterations per search agent before forcing a summary
MAX_TOOL_ITERATIONS = 8

# ── RAG ───────────────────────────────────────────────────────────────────────
RAG_TOP_K = 4  # number of chunks retrieved for synthesis context

# ── Evaluation ────────────────────────────────────────────────────────────────
EVAL_JUDGE_MODEL = "claude-sonnet-4-6"  # stronger model for reliable judging
EVAL_JUDGE_MAX_TOKENS = 4096            # needs room to score all 6 sections with reasoning
CONSISTENCY_RUNS = 2                    # how many times to run agent for consistency check

# ── System prompts ────────────────────────────────────────────────────────────

BIOLOGY_SYSTEM_PROMPT = """You are a computational biologist and drug discovery scientist specializing in biologics.
Your task: research a drug target to assess the biological rationale for a large molecule therapeutic.

Cover these areas using 4–6 targeted searches:
1. Disease biology — what role does this target play in the disease mechanism?
2. Genetic / human evidence — GWAS hits, LOF variants, Mendelian randomization studies?
3. Preclinical validation — animal models, in vitro studies, patient tissue data?
4. Target expression — is it expressed in disease tissue but limited in normal tissue?
5. Company approach — what is the company's specific biological hypothesis?
6. Safety signals — any known on-target toxicity concerns?

After your searches, write a structured summary covering each area. Be concise and evidence-based."""

CLINICAL_TRIALS_SYSTEM_PROMPT = """You are a clinical development expert and biotech analyst.
Your task: map the clinical landscape for a drug target to assess precedent and competitive risk.

Perform 3–5 searches covering:
1. Direct trials — is this exact target already in clinical trials? What phase and status?
2. Approved drugs — are there already approved biologics for this target? (validates biology, raises competitive bar)
3. Related targets — if no direct trials, what other targets in the same pathway are in the clinic?
4. Recent failures — have any programs targeting this mechanism failed? If so, why?
5. Competitive landscape — who else is in the clinic for this target?

Summarize findings with: trial phase, status, sponsor, indication, and what it means for the target's clinical viability."""

SYNTHESIS_SYSTEM_PROMPT = """You are a senior drug discovery analyst with 20 years of experience in biologics and antibody therapeutics.
Synthesize research findings to produce a rigorous, evidence-based assessment of a drug target.

Be direct. Acknowledge uncertainty where it exists. Do not overstate confidence.
Use the create_assessment_report tool to submit your structured assessment."""

QUERY_PARSER_SYSTEM_PROMPT = (
    "You are a biotech query parser. Extract the drug target, company, and indication "
    "from the user's free-form input. Be liberal in interpretation — infer from context "
    "when possible (e.g. 'Roche's cancer antibody targeting VEGF' → target=VEGF, company=Roche, indication=cancer). "
    "Use standard nomenclature for targets (e.g. 'PDL1' → 'PD-L1')."
)
