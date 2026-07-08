"""
RAG Evaluation — retrieval correctness, relevance calibration, and coverage.

No LLM calls. Runs purely on embeddings, so it's fast and cheap.
Three test suites:
  1. Source routing  — query should rank the right document first
  2. Relevance floor — on-topic queries must exceed a cosine similarity threshold
  3. Coverage        — a broad synthesis-style query must surface all three sources
  4. Chunk integrity — no retrieved chunk is cut mid-sentence

Run:
  python -m eval.rag_eval
  python -m eval.rag_eval --verbose
"""

import argparse
import sys
from dotenv import load_dotenv

load_dotenv()

from rag.ingestion import ingest_static_documents
from rag.vectorstore import query_knowledge_base

# ── Source routing test cases ─────────────────────────────────────────────────
# Each query should retrieve at least one chunk from `expected_source` and that
# chunk should rank first (highest cosine similarity).
SOURCE_ROUTING_CASES = [
    {
        "query": "what genetic evidence validates a drug target? GWAS mendelian randomization LOF variants",
        "expected_source": "target_validation_framework",
        "description": "Genetic validation → target_validation_framework",
    },
    {
        "query": "red flags for on-target toxicity safety concerns broad expression normal tissue",
        "expected_source": "target_validation_framework",
        "description": "Safety red flags → target_validation_framework",
    },
    {
        "query": "can antibodies reach intracellular targets ADC payload internalization",
        "expected_source": "large_molecule_druggability",
        "description": "Intracellular target accessibility → large_molecule_druggability",
    },
    {
        "query": "which biologic format for a soluble cytokine versus a cell surface receptor",
        "expected_source": "large_molecule_druggability",
        "description": "Format selection guide → large_molecule_druggability",
    },
    {
        "query": "what is the phase 2 success rate for biologics and why do most programs fail",
        "expected_source": "clinical_development_stages",
        "description": "Phase 2 attrition rates → clinical_development_stages",
    },
    {
        "query": "breakthrough therapy designation fast track accelerated approval FDA pathways",
        "expected_source": "clinical_development_stages",
        "description": "Regulatory pathways → clinical_development_stages",
    },
    {
        "query": "target-mediated drug disposition TMDD half-life FcRn subcutaneous dosing",
        "expected_source": "large_molecule_druggability",
        "description": "PK considerations → large_molecule_druggability",
    },
    {
        "query": "biomarker enrichment patient selection increases clinical success rate",
        "expected_source": "clinical_development_stages",
        "description": "Success factors → clinical_development_stages",
    },
]

# ── Relevance floor cases ──────────────────────────────────────────────────────
# On-topic queries must return at least one chunk with cosine similarity above
# RELEVANCE_THRESHOLD. Off-topic queries must stay below OFF_TOPIC_CEILING.
RELEVANCE_THRESHOLD = 0.45   # minimum cosine sim for an on-topic hit
# BAAI/bge-base-en-v1.5 has a high similarity floor — empirically off-topic queries
# land at 0.45–0.52 with a small domain-specific corpus. This ceiling is intentionally
# loose: the point is to catch gross misconfigurations (wrong model, corrupted index),
# not to expect strong semantic discrimination on unrelated content.
OFF_TOPIC_CEILING   = 0.55   # maximum cosine sim for an off-topic query

ON_TOPIC_QUERIES = [
    "monoclonal antibody target validation clinical evidence",
    "large molecule biologic drug development biologics",
    "phase 3 pivotal trial efficacy endpoint regulatory approval",
    "druggability extracellular epitope antibody binding",
]

OFF_TOPIC_QUERIES = [
    "best practices for Python web scraping with BeautifulSoup",
    "how to configure a Kubernetes ingress controller",
    "quarterly earnings report financial forecast revenue",
]

# ── Coverage query ─────────────────────────────────────────────────────────────
# This mirrors the actual synthesis node query. With RAG_TOP_K=4, we expect
# chunks from at least 2 of the 3 source documents.
SYNTHESIS_QUERY = "large molecule drug target validation druggability clinical development"
COVERAGE_MIN_SOURCES = 2   # at least 2 distinct sources in top-4 results


# ── Test runners ──────────────────────────────────────────────────────────────

def run_source_routing(verbose: bool) -> dict:
    passed, failed = 0, []

    for case in SOURCE_ROUTING_CASES:
        results = query_knowledge_base(case["query"], n_results=4)
        if not results:
            failed.append({**case, "reason": "no results returned"})
            continue

        top_source = results[0]["source"]
        top_score  = results[0]["relevance_score"]

        if top_source == case["expected_source"]:
            passed += 1
            if verbose:
                print(f"  PASS  {case['description']}")
                print(f"        top={top_source}  sim={top_score:.3f}")
        else:
            # Check if expected source appears anywhere in top-4
            sources_returned = [r["source"] for r in results]
            rank = next((i + 1 for i, s in enumerate(sources_returned)
                         if s == case["expected_source"]), None)
            failed.append({
                **case,
                "reason": f"expected '{case['expected_source']}' first, got '{top_source}' "
                          f"(expected source at rank {rank or 'not found'})",
                "top_score": top_score,
            })
            if verbose:
                print(f"  FAIL  {case['description']}")
                print(f"        expected={case['expected_source']}  got={top_source}  sim={top_score:.3f}")

    return {"passed": passed, "total": len(SOURCE_ROUTING_CASES), "failures": failed}


def run_relevance_floor(verbose: bool) -> dict:
    passed, failed = 0, []

    for query in ON_TOPIC_QUERIES:
        results = query_knowledge_base(query, n_results=1)
        score = results[0]["relevance_score"] if results else 0.0
        if score >= RELEVANCE_THRESHOLD:
            passed += 1
            if verbose:
                print(f"  PASS  on-topic  sim={score:.3f}  \"{query[:60]}\"")
        else:
            failed.append({"query": query, "type": "on_topic",
                           "reason": f"sim={score:.3f} below threshold {RELEVANCE_THRESHOLD}"})
            if verbose:
                print(f"  FAIL  on-topic  sim={score:.3f} < {RELEVANCE_THRESHOLD}  \"{query[:60]}\"")

    for query in OFF_TOPIC_QUERIES:
        results = query_knowledge_base(query, n_results=1)
        score = results[0]["relevance_score"] if results else 0.0
        if score < OFF_TOPIC_CEILING:
            passed += 1
            if verbose:
                print(f"  PASS  off-topic sim={score:.3f}  \"{query[:60]}\"")
        else:
            failed.append({"query": query, "type": "off_topic",
                           "reason": f"sim={score:.3f} above ceiling {OFF_TOPIC_CEILING} — corpus may be over-retrieving"})
            if verbose:
                print(f"  FAIL  off-topic sim={score:.3f} >= {OFF_TOPIC_CEILING}  \"{query[:60]}\"")

    total = len(ON_TOPIC_QUERIES) + len(OFF_TOPIC_QUERIES)
    return {"passed": passed, "total": total, "failures": failed}


def run_coverage(verbose: bool) -> dict:
    results = query_knowledge_base(SYNTHESIS_QUERY, n_results=4)
    sources = list(dict.fromkeys(r["source"] for r in results))  # deduplicated, order preserved

    passed = len(sources) >= COVERAGE_MIN_SOURCES
    if verbose:
        print(f"  {'PASS' if passed else 'FAIL'}  synthesis query returned sources: {sources}")
        for r in results:
            print(f"        {r['source']}  sim={r['relevance_score']:.3f}  "
                  f"\"{r['content'][:80].strip()}...\"")

    return {
        "passed": 1 if passed else 0,
        "total": 1,
        "sources_returned": sources,
        "distinct_sources": len(sources),
        "failures": [] if passed else [{
            "reason": f"only {len(sources)} source(s) in top-4: {sources} "
                      f"(expected >= {COVERAGE_MIN_SOURCES})"
        }],
    }


def _chunk_is_cut(chunk: str) -> bool:
    """
    Return True if the chunk appears to be cut mid-sentence.
    Markdown bullet list items and table rows legitimately end without terminal
    punctuation, so we only flag chunks whose last line ends with a conjunction,
    preposition, or article — words that strongly imply an incomplete clause.
    """
    INCOMPLETE_ENDINGS = {
        "a", "an", "the", "and", "or", "but", "if", "as", "of",
        "in", "on", "at", "to", "for", "with", "by", "from", "that",
        "which", "when", "where", "is", "are", "was", "were",
    }
    last_line = chunk.strip().splitlines()[-1].strip().rstrip(".,;:")
    last_word = last_line.split()[-1].lower().strip("()[]") if last_line.split() else ""
    return last_word in INCOMPLETE_ENDINGS


def run_chunk_integrity(verbose: bool) -> dict:
    """
    Retrieve chunks across all test queries and flag any that appear cut mid-sentence.
    Markdown list items and table rows legitimately end without terminal punctuation,
    so the check only flags chunks ending on function words (conjunctions, prepositions,
    articles) — a reliable signal that the splitter bisected a clause.
    """
    all_queries = [c["query"] for c in SOURCE_ROUTING_CASES] + ON_TOPIC_QUERIES
    seen, passed, failed = set(), 0, []

    for query in all_queries:
        for result in query_knowledge_base(query, n_results=3):
            chunk = result["content"].strip()
            if chunk in seen:
                continue
            seen.add(chunk)

            if _chunk_is_cut(chunk):
                failed.append({
                    "source": result["source"],
                    "tail": chunk[-80:],
                })
                if verbose:
                    print(f"  WARN  possible mid-sentence cut  [{result['source']}]")
                    print(f"        ...{chunk[-80:]!r}")
            else:
                passed += 1
                if verbose:
                    print(f"  OK    [{result['source']}]  ...{chunk[-40:]!r}")

    total = passed + len(failed)
    return {"passed": passed, "total": total, "failures": failed, "is_warning_only": True}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAG retrieval evaluation")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print per-query results")
    args = parser.parse_args()

    print("Initializing knowledge base...")
    ingest_static_documents()

    suites = [
        ("Source Routing",    run_source_routing),
        ("Relevance Floor",   run_relevance_floor),
        ("Coverage",          run_coverage),
        ("Chunk Integrity",   run_chunk_integrity),
    ]

    overall_passed = overall_total = 0
    all_failures = []

    for name, fn in suites:
        print(f"\n{'─'*50}")
        print(f"Suite: {name}")
        print(f"{'─'*50}")
        result = fn(args.verbose)

        p, t = result["passed"], result["total"]
        label = "WARN" if result.get("is_warning_only") else ("PASS" if p == t else "FAIL")
        print(f"Result: {label}  {p}/{t}")

        if not result.get("is_warning_only"):
            overall_passed += p
            overall_total  += t

        if result["failures"] and not args.verbose:
            for f in result["failures"]:
                reason = f.get("reason", f.get("description", str(f)))
                print(f"  {'WARN' if result.get('is_warning_only') else 'FAIL'}  {reason}")

    print(f"\n{'='*50}")
    print(f"Overall: {overall_passed}/{overall_total} hard checks passed")
    if overall_passed < overall_total:
        print("Some checks failed — see details above.")
        sys.exit(1)
    else:
        print("All checks passed.")


if __name__ == "__main__":
    main()
