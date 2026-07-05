"""
Consistency Check — for novel targets with no ground truth.

Runs the agent twice on the same query and compares recommendations.
A reliable agent should agree with itself even when search results vary.
Divergence signals low reliability and triggers Level 2 (LLM judge) diagnosis.
"""

from graph.orchestrator import graph
from graph.state import make_initial_state
from config import CONSISTENCY_RUNS

RECOMMENDATION_ORDER = ["Against", "Weak", "Moderate", "Strong"]


def _run_once(target: str, company: str, indication: str) -> dict:
    result = graph.invoke(make_initial_state(target, company, indication))
    return result.get("report", {})


def check_consistency(target: str, company: str, indication: str = "") -> dict:
    """
    Run the agent CONSISTENCY_RUNS times and compare outputs.
    Returns a consistency report with agreement level and divergence details.
    """
    reports = []
    for i in range(CONSISTENCY_RUNS):
        print(f"  Consistency run {i + 1}/{CONSISTENCY_RUNS}...")
        report = _run_once(target, company, indication)
        reports.append(report)

    recommendations = [r.get("recommendation", "") for r in reports]
    confidence_scores = [float(r.get("confidence_score", 0)) for r in reports]

    # Recommendation agreement
    unique_recs = set(recommendations)
    rec_consistent = len(unique_recs) == 1

    # Confidence score range
    conf_range = max(confidence_scores) - min(confidence_scores) if confidence_scores else 0
    conf_consistent = conf_range <= 2.0  # allow ±2 points variance

    # Overall consistency
    consistent = rec_consistent and conf_consistent

    # Compute distance between recommendations if they differ
    rec_distance = 0
    if not rec_consistent and len(recommendations) >= 2:
        idxs = [
            RECOMMENDATION_ORDER.index(r) for r in recommendations if r in RECOMMENDATION_ORDER
        ]
        if len(idxs) >= 2:
            rec_distance = max(idxs) - min(idxs)

    return {
        "target": target,
        "company": company,
        "indication": indication,
        "runs": CONSISTENCY_RUNS,
        "recommendations": recommendations,
        "confidence_scores": confidence_scores,
        "recommendation_consistent": rec_consistent,
        "confidence_consistent": conf_consistent,
        "confidence_range": round(conf_range, 1),
        "recommendation_distance": rec_distance,
        "consistent": consistent,
        "reliability": "high" if consistent else ("medium" if rec_distance <= 1 else "low"),
        "reports": reports,
        "trigger_llm_judge": not consistent,
    }
