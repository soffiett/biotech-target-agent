# TRACE: Target Ranking via Agentic Corroboration of Evidence

A multi-agent system that evaluates whether a biotech company's drug target is likely to yield a successful therapeutic — modality-agnostic, determining whether small molecule, large molecule (antibody/biologic), or another modality best fits the target's biology.

Built with LangGraph, Claude Haiku + Sonnet, and free public APIs (OpenTargets, GWAS credible sets, ClinVar/OMIM, DepMap, HPA/GTEx, Reactome, PubMed, ClinicalTrials.gov, bioRxiv). Designed for accuracy on a personal budget.

**Deployed on AWS ECS Fargate** (ARM64 Graviton2) with ECR, Secrets Manager, and CloudWatch logging.

---

## Architecture

```
User Input (free-form text or structured fields)
              │
        [Query Parser]           Haiku 4.5
              │
        [Prefetch Node]          OpenTargets API → derives per-agent research focus
              │
     ┌────────┴────────┐
     ▼                 ▼
[Biology Agent]                       [Clinical Trial Agent]     Haiku 4.5 — run in parallel
 · GWAS/OpenTargets · ClinVar/OMIM      · ClinicalTrials.gov
 · DepMap · HPA/GTEx · Reactome         · Tavily
 · PubMed · bioRxiv · Tavily
     └─────────────────┬─────────────────┘
                        ▼
      [Synthesis Agent]          Sonnet 4.6 · ChromaDB RAG · modality-agnostic druggability
              │
         [Judge Node]            Sonnet 4.6 — scores each section 1–5
          · if biology ≤ 2/5 → re-runs Biology Agent with critique (max 1×)
              │
     [Assessment Report]
```

### Node responsibilities

| Node | Model | Role |
|------|-------|------|
| **Query Parser** | Haiku 4.5 | Extracts target / company / indication from free-form text |
| **Prefetch** | — (API calls) | Fetches OpenTargets structured data; derives a tailored research brief for each downstream agent based on clinical stage and genetic evidence; distinguishes "target not found" from "OpenTargets unreachable" so a transient outage isn't read as evidence about the target |
| **Biology Agent** | Haiku 4.5 | Runs 5 structured evidence tools (GWAS/OpenTargets, ClinVar/OMIM, DepMap, HPA/GTEx, Reactome) plus PubMed/bioRxiv/web search; every finding is tagged with an `evidence_type` used to weight it during synthesis; re-runs with judge critique injected if initial score ≤ 2/5 |
| **Clinical Trial Agent** | Haiku 4.5 | Searches ClinicalTrials.gov and web using a focus brief set by prefetch; maps trial phase, status, failures, and competitive landscape |
| **Synthesis Agent** | Sonnet 4.6 | Combines all findings (grouped by evidence-tier weight) with RAG context to produce a structured, modality-agnostic report — determines whether small molecule, large molecule, or another modality fits the target and caps confidence if the company's actual approach doesn't match |
| **Judge Node** | Sonnet 4.6 | Scores each section (1–5) against a rubric, including whether a modality mismatch was correctly reflected in the confidence score; routes back to Biology Agent if biology score ≤ 2/5, otherwise surfaces report to user |

### Evidence weighting

Biology findings are tagged by source at collection time (not inferred from prose) and grouped into
labeled sections in order of decreasing evidentiary weight before reaching synthesis:

`human_genetics` (GWAS/OpenTargets) & `rare_variant` (ClinVar/OMIM) → `crispr_dependency` (DepMap) →
`tissue_expression` (HPA/GTEx) & `pathway_biology` (Reactome) → `literature` (PubMed) →
`preprint` (bioRxiv) & `company_disclosure` (web search)

`SYNTHESIS_SYSTEM_PROMPT` instructs the model to weight sections accordingly and flag explicitly if
the rationale rests only on the weakest tiers.

### Context engineering

The prefetch node reads OpenTargets structured output (approved drugs, clinical stage, genetic association scores) and generates a different research brief for each agent before they run:

| Signal from OpenTargets | Biology agent directed to... | Clinical agent directed to... |
|------------------------|------------------------------|-------------------------------|
| Approved drug exists | Focus on mechanism, resistance, safety — skip proof-of-concept | Map differentiation gaps, biosimilars, label expansions |
| Phase 2/3 programs | Assess responder biomarkers and combination biology | Investigate failure root causes and timelines |
| High genetic score, no drugs | Validate translational gap and druggability | Search for Phase 1 / dropped programs |
| Novel target | Be thorough and flag thin evidence explicitly | Search pathway analogs and academic studies |

---

## Data Sources

### Pre-fetch (always called, deterministic)

| Source | What it provides |
|--------|-----------------|
| **OpenTargets** | Disease-target association scores, genetic evidence score, known drugs/clinical programs |

### Biology Agent tools

Structured evidence tools — one deterministic call each, auto-scoped to the current target/indication
(the model doesn't retype the gene symbol, since GTEx/ClinVar require exact matches):

| Source | Tool | Evidence type | What it provides |
|--------|------|---------------|-------------------|
| **GWAS credible sets** (OpenTargets GraphQL) | `tools/gwas.py` | `human_genetics` | L2G-scored genetic association evidence for the target-disease pair |
| **ClinVar + OMIM** (NCBI E-utilities) | `tools/clinvar_omim.py` | `rare_variant` | Pathogenic variant classifications, associated conditions, MIM record cross-reference |
| **DepMap** (via OpenTargets) | `tools/depmap.py` | `crispr_dependency` | CRISPR knockout gene-effect scores by tissue/cell line |
| **HPA + GTEx** | `tools/expression.py` | `tissue_expression` | Tissue specificity summary (HPA) and per-tissue median TPM (GTEx) |
| **Reactome** | `tools/reactome.py` | `pathway_biology` | Pathways containing the target, for mechanism context |

Literature & narrative tools:

| Source | What it provides |
|--------|-----------------|
| **PubMed** (NCBI E-utilities) | Peer-reviewed literature — disease mechanism, animal models, biomarker studies |
| **bioRxiv / medRxiv** (Europe PMC) | Preprints — cutting-edge findings not yet peer-reviewed |
| **Tavily** | Web search — company pipeline pages, press releases, investor decks |

### Clinical Trial Agent tools

| Source | What it provides |
|--------|-----------------|
| **ClinicalTrials.gov v2** | Trial phase, status, sponsor, indication for same target and related mechanisms |
| **Tavily** | Recent trial news, FDA decisions, competitor updates |

### RAG Knowledge Base (ChromaDB, local)

Four curated seed documents. Two (target validation, clinical development stages) are retrieved by
similarity search; the two modality druggability guides are always injected directly into every
synthesis call instead, so the model compares both before determining fit rather than depending on
search to surface the right one before it knows the target's modality:

| File | Content | How it reaches the model |
|------|---------|---------------------------|
| `target_validation_framework.md` | Tiered evidence tiers (genetic → functional), red flags | Retrieved (similarity search) |
| `clinical_development_stages.md` | Phase success rates, accelerated pathways, common failure reasons | Retrieved (similarity search) |
| `large_molecule_druggability.md` | Antibody/biologic format selection, extracellular vs intracellular, PK | Always injected |
| `small_molecule_druggability.md` | Binding-pocket tractability, PROTACs/oligonucleotides, oral PK | Always injected |

Add your own `.md` files to `rag/data/` and delete `rag/chroma_db/` to re-ingest. Add a filename to
`_PROMPT_INJECTED` in `rag/ingestion.py` if it should always be present rather than retrieved.

---

## Report Output

Each assessment produces:

- **Recommendation**: Strong / Moderate / Weak / Against
- **Confidence score**: 0–10 with reasoning
- **Biology rationale**: genetic evidence, disease mechanism, preclinical validation, safety
- **Druggability & modality assessment**: which modality (small molecule, large molecule, or other) fits the target's biology, whether the company's actual approach matches, format recommendation, PK
- **Clinical precedent**: trials for this target and related mechanisms, phase + status
- **Competitive landscape**: approved drugs, other programs, crowding risk
- **Key risks**: 3–5 specific, actionable concerns
- **Report quality panel**: section-by-section scores from the judge node

---

## Evaluation Module

The `eval/` module tests agent quality at development time — run it after changing prompts or models.

```
eval/
├── ground_truth.py       # 16 curated test cases with defensible ground truth
├── llm_judge.py          # Section-by-section rubric scoring using Sonnet
├── consistency_check.py  # Runs agent twice, flags low-reliability outputs
├── rag_eval.py           # Retrieval-only eval: source routing, relevance, coverage, chunk integrity
└── runner.py             # Smart routing: L1 + L2 for known targets, consistency + L2 for novel
```

**Ground truth dataset — 16 targets across all four recommendation tiers, both modalities:**

| Tier | Count | Examples |
|------|-------|---------|
| Strong | 10 | PD-L1, IL-6R, VEGF, HER2, TROP2, PCSK9, IL-17A (large molecule); BCR-ABL, EGFR T790M, PI3K/mTOR (small molecule) |
| Moderate | 1 | BAFF (approved but modest efficacy, narrow label) |
| Weak | 1 | VISTA (Phase 1 only, limited data) |
| Against | 4 | TIGIT, CD28, BACE1, EGFRvIII |

Sources: FDA Purple Book (approvals), published Phase 3 trial results (NEJM, JAMA, Lancet).

**Routing logic:**
- **Known target** (in ground truth DB) → Level 1 ground truth score → Level 2 LLM judge on failure
- **Novel target** (no ground truth) → Consistency check (run twice) → Level 2 LLM judge

```bash
# Run full test suite (all 13 ground truth cases)
python -m eval.runner

# Evaluate a specific known target
python -m eval.runner --target TIGIT --company Roche --indication NSCLC

# Evaluate a novel target (auto-routes to consistency + judge)
python -m eval.runner --target VISTA --company ImmuNext --indication "solid tumors"

# Run RAG retrieval eval (no LLM calls, completes in ~3s)
python -m eval.rag_eval
python -m eval.rag_eval --verbose
```

---

## Deployment (AWS)

The app is containerised with Docker and deployed to AWS ECS Fargate.

### Infrastructure

| Component | AWS Service |
|-----------|------------|
| Container image | ECR (Elastic Container Registry) |
| Container runtime | ECS Fargate (ARM64 Graviton2) |
| API keys | Secrets Manager |
| Logs | CloudWatch `/ecs/biotech-target-agent` |

### Deploy from scratch

**Prerequisites:** AWS CLI configured, Docker Desktop running.

```bash
# One-time infrastructure setup
./deploy/setup.sh

# Build, push, and deploy
./deploy/deploy.sh

# Get current public URL
./deploy/get-url.sh
```

### Manage the running service

```bash
# Watch live logs
aws logs tail /ecs/biotech-target-agent --follow --region us-west-1

# Stop service (save cost when not demoing)
aws ecs update-service --cluster biotech-target-agent \
    --service biotech-target-agent --desired-count 0 --region us-west-1

# Restart service
aws ecs update-service --cluster biotech-target-agent \
    --service biotech-target-agent --desired-count 1 --region us-west-1
```

### Cost estimate (AWS)

| Resource | Cost |
|----------|------|
| Fargate 0.5 vCPU + 1GB RAM (ARM64) | ~$22/month |
| Secrets Manager (3 secrets) | ~$1.20/month |
| CloudWatch logs | ~$0.50/month |
| ECR storage | free (under 500MB) |
| **Total** | **~$24/month** |

---

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/your-username/biotech-target-agent.git
cd biotech-target-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. API keys

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=...   # https://console.anthropic.com
TAVILY_API_KEY=...      # https://tavily.com (free tier: 1000 searches/month)
NCBI_EMAIL=...          # any email — required by PubMed API policy
```

OpenTargets, GWAS credible sets, ClinVar/OMIM, DepMap, HPA/GTEx, Reactome, ClinicalTrials.gov, and bioRxiv are all free with no key required.

### 3. Run

```bash
streamlit run app.py
```

The ChromaDB knowledge base is built automatically on first launch. The `BAAI/bge-base-en-v1.5` embedding model (~440MB) is downloaded once and cached locally.

---

## Cost Estimate

| Component | Model / Service | Cost per query |
|-----------|----------------|---------------|
| Query parser | Claude Haiku 4.5 | ~$0.001 |
| Prefetch | OpenTargets (free API) | $0 |
| Biology agent | Claude Haiku 4.5 | ~$0.005–0.01 |
| Clinical trial agent | Claude Haiku 4.5 | ~$0.005–0.01 |
| Synthesis | Claude Sonnet 4.6 | ~$0.02–0.05 |
| Judge node | Claude Sonnet 4.6 | ~$0.02–0.03 |
| Biology re-run (if triggered) | Claude Haiku 4.5 + Sonnet 4.6 | ~$0.03 extra |
| Web search | Tavily (free tier: 1000/month) | $0 |
| Embeddings | sentence-transformers (local CPU) | $0 |
| **Total** | | **~$0.05–0.13 per query** |

---

## Tech Stack

- **Orchestration**: LangGraph (StateGraph — prefetch → parallel → synthesis → judge → conditional re-run)
- **LLMs**: Claude Haiku 4.5 (search agents, parser) + Claude Sonnet 4.6 (synthesis, judge)
- **Vector store**: ChromaDB (local, persistent)
- **Embeddings**: `BAAI/bge-base-en-v1.5` via sentence-transformers (CPU)
- **APIs**: OpenTargets GraphQL (genetics, DepMap essentiality), NCBI E-utilities (PubMed, ClinVar, OMIM), GTEx Portal API v2, Human Protein Atlas, Reactome ContentService, ClinicalTrials.gov v2, Europe PMC (bioRxiv), Tavily
- **UI**: Streamlit

---

## Example Queries

A cross-section of the ground truth dataset — useful for quick manual testing:

| Target | Company | Indication | Expected |
|--------|---------|------------|----------|
| PD-L1 | Genentech | NSCLC | Strong |
| PCSK9 | Amgen | Hypercholesterolemia | Strong |
| BCR-ABL | Novartis | Chronic myeloid leukemia | Strong (small molecule) |
| BAFF | GSK | Systemic lupus erythematosus | Moderate |
| VISTA | ImmuNext | Solid tumors | Weak |
| TIGIT | Roche | NSCLC | Against |
| BACE1 | Merck | Alzheimer's disease | Against |

---

## Project Structure

```
biotech-target-agent/
├── app.py                        # Streamlit UI
├── config.py                     # All model names, prompts, and constants
├── requirements.txt
├── .env.example
├── graph/
│   ├── state.py                  # LangGraph shared state (TypedDict)
│   ├── orchestrator.py           # Graph definition and compilation
│   └── nodes/
│       ├── prefetch.py           # OpenTargets pre-fetch + per-agent focus injection
│       ├── biology.py            # Biology search agent
│       ├── clinical_trials.py    # Clinical trial search agent
│       ├── synthesis.py          # Report synthesis agent
│       └── judge.py              # LLM-as-judge quality node
├── tools/
│   ├── query_parser.py           # Free-form input → structured fields
│   ├── opentargets.py            # OpenTargets GraphQL API (prefetch + resolve_target_ensembl_id)
│   ├── gwas.py                   # GWAS credible-set genetic evidence (OpenTargets GraphQL)
│   ├── clinvar_omim.py           # Rare/pathogenic variant evidence (NCBI E-utilities)
│   ├── depmap.py                 # CRISPR dependency by tissue (OpenTargets GraphQL)
│   ├── expression.py             # Tissue expression (Human Protein Atlas + GTEx)
│   ├── reactome.py               # Pathway membership (Reactome ContentService)
│   ├── pubmed.py                 # PubMed E-utilities API
│   ├── biorxiv.py                # bioRxiv/medRxiv via Europe PMC
│   ├── clinicaltrials.py         # ClinicalTrials.gov v2 API
│   └── web_search.py             # Tavily web search
├── rag/
│   ├── vectorstore.py            # ChromaDB + sentence-transformers
│   ├── ingestion.py              # Markdown → chunks → embeddings (some files always
│   │                              # prompt-injected instead — see _PROMPT_INJECTED)
│   └── data/                     # Curated biotech knowledge documents
├── eval/
│   ├── ground_truth.py           # 13 curated test cases + L1 scoring
│   ├── llm_judge.py              # Section rubric scoring (L2)
│   ├── consistency_check.py      # Reliability check for novel targets
│   ├── rag_eval.py               # RAG retrieval eval (no LLM calls)
│   └── runner.py                 # Evaluation orchestrator
├── models/
│   └── schemas.py                # Pydantic output models
├── deploy/
│   ├── setup.sh                  # One-time AWS infrastructure setup
│   ├── deploy.sh                 # Build, push, and deploy to Fargate
│   └── get-url.sh                # Print current public IP
├── Dockerfile                    # Container definition (linux/arm64)
└── .dockerignore
```
