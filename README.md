# Biotech Target Assessment Agent

A multi-agent system that evaluates whether a biotech company's drug target is likely to yield a successful large molecule therapeutic.

## Architecture

```
User Input (target + company + indication)
              │
     [LangGraph Orchestrator]
              │ parallel fan-out
    ┌─────────┴──────────┐
    ▼                    ▼
[Biology Agent]   [Clinical Trial Agent]
  Haiku 4.5          Haiku 4.5
  · PubMed API       · ClinicalTrials.gov v2
  · Tavily web       · Tavily web
    search             search
    └─────────┬──────────┘
              ▼
      [Synthesis Agent]
         Sonnet 4.6
         · ChromaDB RAG tool
         · Structured report
              │
        Assessment Report
```

**Biology Agent** — searches PubMed and the web to assess: genetic evidence, disease biology, preclinical validation, target expression, and safety signals.

**Clinical Trial Agent** — searches ClinicalTrials.gov for the target and related mechanisms; maps the competitive landscape and identifies clinical precedent.

**Synthesis Agent** — combines both outputs with curated knowledge base context (ChromaDB RAG) to produce a structured report with a confidence score and recommendation.

## Setup

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
# Edit .env and fill in:
# ANTHROPIC_API_KEY  — https://console.anthropic.com
# TAVILY_API_KEY     — https://tavily.com (free tier: 1000 searches/month)
# NCBI_EMAIL         — any email (required by PubMed API policy)
```

### 3. Run

```bash
streamlit run app.py
```

The knowledge base (ChromaDB) is built automatically on first launch from the curated documents in `rag/data/`.

## Knowledge Base

Three seed documents are pre-loaded into ChromaDB and retrieved by the synthesis agent:

| File | Content |
|------|---------|
| `target_validation_framework.md` | Tiered evidence framework (genetic → functional) and red flags |
| `large_molecule_druggability.md` | Antibody format selection, extracellular vs intracellular targets, PK |
| `clinical_development_stages.md` | Phase success rates, accelerated pathways, common failure reasons |

Add your own `.md` files to `rag/data/` and delete `rag/chroma_db/` to re-ingest.

## Cost Estimate

| Component | Model / Service | Estimated cost per query |
|-----------|----------------|--------------------------|
| Biology agent | Claude Haiku 4.5 | ~$0.005–0.01 |
| Trial agent | Claude Haiku 4.5 | ~$0.005–0.01 |
| Synthesis | Claude Sonnet 4.6 | ~$0.02–0.05 |
| Web search | Tavily (free tier) | $0 (up to 1000/month) |
| Embeddings | sentence-transformers (local) | $0 |
| **Total** | | **~$0.03–0.07 per query** |

## Tech Stack

- **Orchestration**: LangGraph (StateGraph with parallel nodes)
- **LLMs**: Claude Haiku 4.5 (search agents) + Claude Sonnet 4.6 (synthesis)
- **Vector store**: ChromaDB (local, persistent)
- **Embeddings**: `BAAI/bge-base-en-v1.5` via sentence-transformers (runs on CPU or GPU)
- **Data sources**: PubMed E-utilities API, ClinicalTrials.gov v2 API, Tavily
- **UI**: Streamlit

## Example Queries

| Target | Company | Indication |
|--------|---------|------------|
| PD-L1 | Genentech | NSCLC |
| IL-6R | Roche | Rheumatoid Arthritis |
| TROP2 | Gilead | Triple-negative breast cancer |
| TIGIT | Roche | Melanoma |
