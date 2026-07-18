"""
Level 1 Evaluation — Ground Truth Scoring

Tests the agent against targets with known, unambiguous outcomes, across modalities
(biologics and small molecules):
- FDA-approved therapeutics with strong evidence (expected: Strong)
- Documented Phase 3 failures (expected: Against/Weak)

Run after any prompt change to catch regressions.
"""

# Curated test cases with defensible ground truth
# Source: FDA Purple Book (approvals), published trial results (failures)
TEST_CASES = [
    {
        "target": "PD-L1",
        "company": "Genentech",
        "indication": "NSCLC",
        "expected_recommendation": "Strong",
        "confidence_min": 7.0,
        "rationale": "FDA approved (atezolizumab / Tecentriq, 2016) for multiple indications",
        "source": "FDA Purple Book",
    },
    {
        "target": "IL-6R",
        "company": "Roche",
        "indication": "rheumatoid arthritis",
        "expected_recommendation": "Strong",
        "confidence_min": 7.0,
        "rationale": "FDA approved (tocilizumab / Actemra, 2010)",
        "source": "FDA Purple Book",
    },
    {
        "target": "VEGF",
        "company": "Genentech",
        "indication": "colorectal cancer",
        "expected_recommendation": "Strong",
        "confidence_min": 7.0,
        "rationale": "FDA approved (bevacizumab / Avastin, 2004)",
        "source": "FDA Purple Book",
    },
    {
        "target": "HER2",
        "company": "Genentech",
        "indication": "breast cancer",
        "expected_recommendation": "Strong",
        "confidence_min": 7.0,
        "rationale": "FDA approved (trastuzumab / Herceptin, 1998)",
        "source": "FDA Purple Book",
    },
    {
        "target": "TROP2",
        "company": "Gilead",
        "indication": "triple-negative breast cancer",
        "expected_recommendation": "Strong",
        "confidence_min": 6.0,
        "rationale": "FDA approved as ADC (sacituzumab govitecan / Trodelvy, 2021)",
        "source": "FDA Purple Book",
    },
    {
        "target": "TIGIT",
        "company": "Roche",
        "indication": "NSCLC",
        "expected_recommendation": "Against",
        "confidence_max": 5.0,
        "rationale": "Tiragolumab Phase 3 (SKYSCRAPER-01) failed OS endpoint, 2023",
        "source": "Published trial results (NEJM 2023)",
    },
    {
        "target": "CD28",
        "company": "TeGenero",
        "indication": "autoimmune",
        "expected_recommendation": "Against",
        "confidence_max": 3.0,
        "rationale": "TGN1412 catastrophic Phase 1 failure — cytokine storm in all 6 volunteers (2006)",
        "source": "Published safety report",
    },
    {
        "target": "VISTA",
        "company": "ImmuNext",
        "indication": "solid tumors",
        "expected_recommendation": "Weak",
        "confidence_max": 5.0,
        "rationale": "Early Phase 1 only, limited efficacy data, biology not fully understood",
        "source": "ClinicalTrials.gov",
    },
    # ── Additional Strong cases (different modalities / pathways) ─────────────
    {
        "target": "PCSK9",
        "company": "Amgen",
        "indication": "hypercholesterolemia",
        "expected_recommendation": "Strong",
        "confidence_min": 7.5,
        "rationale": (
            "FDA approved (evolocumab / Repatha, 2015); FOURIER trial showed 15% reduction "
            "in CV events; strong human genetic validation (LOF variants → low LDL, no adverse effects)"
        ),
        "source": "FDA Purple Book; NEJM 2017 FOURIER trial",
    },
    {
        "target": "IL-17A",
        "company": "Novartis",
        "indication": "plaque psoriasis",
        "expected_recommendation": "Strong",
        "confidence_min": 7.5,
        "rationale": (
            "FDA approved (secukinumab / Cosentyx, 2015); CLEAR trial PASI-90 ~79% vs ~44% ustekinumab; "
            "class validated by ixekizumab (Eli Lilly, 2016) and bimekizumab"
        ),
        "source": "FDA Purple Book; NEJM 2015",
    },
    # ── Small-molecule Strong cases (modality-agnostic coverage) ──────────────
    # These test that strong biology + the right modality scores high without
    # being penalized just for not being a biologic — the large-molecule-only
    # assumption this system used to make would have under-scored all three.
    {
        "target": "BCR-ABL",
        "company": "Novartis",
        "indication": "chronic myeloid leukemia",
        "expected_recommendation": "Strong",
        "confidence_min": 8.0,
        "rationale": (
            "FDA approved (imatinib / Gleevec, accelerated approval 2001, full approval 2002 "
            "after IRIS trial); 10-year overall survival 83.3% vs. ~50% pre-imatinib historical "
            "controls; textbook oncogene-addiction target — intracellular fusion kinase, "
            "correctly targeted with an ATP-competitive small molecule, not a biologic"
        ),
        "source": "FDA Purple Book; O'Brien et al. NEJM 2003 (IRIS); Hochhaus et al. NEJM 2017 (10-yr IRIS)",
    },
    {
        "target": "EGFR T790M",
        "company": "AstraZeneca",
        "indication": "NSCLC",
        "expected_recommendation": "Strong",
        "confidence_min": 7.5,
        "rationale": (
            "FDA accelerated approval (osimertinib / Tagrisso, Nov 2015) for T790M-positive NSCLC "
            "progressing on prior EGFR TKI; AURA trial ORR 61%, AURA2 ORR 70%; confirmatory Phase 3 "
            "showed 70% reduction in progression risk vs. chemotherapy — an intracellular kinase "
            "resistance mutation correctly addressed with a third-generation small-molecule TKI"
        ),
        "source": "FDA approval Nov 2015; AURA/AURA2 trial data; confirmatory Phase 3 (NEJM)",
    },
    {
        "target": "PI3K/mTOR",
        "company": "Celcuity",
        "indication": "breast cancer",
        "expected_recommendation": "Strong",
        "confidence_min": 7.0,
        "confidence_max": 8.5,
        "rationale": (
            "FDA approved (gedatolisib / REVTORPYK, July 14, 2026) with fulvestrant ± palbociclib "
            "for HR+/HER2-, PIK3CA wild-type advanced breast cancer; Phase 3 VIKTORIA-1 showed 76% "
            "(triplet) and 67% (doublet) reduction in progression risk vs. fulvestrant; PI3K/mTOR "
            "are intracellular kinases with well-defined ATP pockets — correctly targeted with a "
            "pan-isoform small-molecule inhibitor, not a biologic. Score should stay just below the "
            "9-10 ceiling: no unified GWAS/ClinVar evidence exists for the pathway as a composite "
            "target (genetic support is at the individual PIK3CA/PTEN node level), and the space is "
            "crowded (alpelisib, inavolisib, capivasertib, everolimus already approved)"
        ),
        "source": "FDA.gov drug approval page (gedatolisib, July 2026); Celcuity VIKTORIA-1 Phase 3 results",
    },
    # ── Moderate case — approved but modest efficacy / narrow label ───────────
    {
        "target": "BAFF",
        "company": "GSK",
        "indication": "systemic lupus erythematosus",
        "expected_recommendation": "Moderate",
        "confidence_min": 4.0,
        "confidence_max": 7.0,
        "rationale": (
            "FDA approved (belimumab / Benlysta, 2011) but modest clinical benefit — SRI-4 response ~57% vs "
            "43% placebo; two large Phase 3 trials required; narrow label (active, autoantibody-positive SLE); "
            "target is validated but differentiation from standard-of-care is limited"
        ),
        "source": "FDA Purple Book; Lancet 2011 BLISS-52/BLISS-76",
    },
    # ── Against cases — documented Phase 2/3 failures ────────────────────────
    {
        "target": "BACE1",
        "company": "Merck",
        "indication": "Alzheimer's disease",
        "expected_recommendation": "Against",
        "confidence_max": 4.0,
        "rationale": (
            "Verubecestat (MK-8931) Phase 2/3 EPOCH trial stopped early 2018 — futility plus "
            "cognitive worsening signal; class-wide failure (atabecestat, lanabecestat also failed); "
            "amyloid lowering not sufficient for clinical benefit; target mechanism now widely questioned"
        ),
        "source": "NEJM 2019; Merck press release Feb 2018",
    },
    {
        "target": "EGFRvIII",
        "company": "Celldex",
        "indication": "glioblastoma",
        "expected_recommendation": "Against",
        "confidence_max": 4.0,
        "rationale": (
            "Rindopepimut Phase 3 ACT IV trial stopped at interim analysis 2016 — met futility criteria, "
            "no OS benefit over standard-of-care; antigen loss on recurrence is a fundamental escape mechanism"
        ),
        "source": "JAMA 2017 ACT IV trial results",
    },
]

RECOMMENDATION_ORDER = ["Against", "Weak", "Moderate", "Strong"]


def score_recommendation(predicted: str, expected: str) -> dict:
    """
    Score the recommendation.
    - Exact match: full credit
    - One step off (e.g. Moderate vs Strong): partial credit
    - Two+ steps off: fail
    """
    pred_idx = RECOMMENDATION_ORDER.index(predicted) if predicted in RECOMMENDATION_ORDER else -1
    exp_idx = RECOMMENDATION_ORDER.index(expected) if expected in RECOMMENDATION_ORDER else -1

    if pred_idx == -1 or exp_idx == -1:
        return {"pass": False, "score": 0, "detail": f"Invalid recommendation: '{predicted}'"}

    distance = abs(pred_idx - exp_idx)
    passed = distance == 0
    partial = distance == 1

    return {
        "pass": passed,
        "partial": partial,
        "score": 1.0 if passed else 0.5 if partial else 0.0,
        "detail": f"Expected '{expected}', got '{predicted}' (distance={distance})",
    }


def score_confidence(confidence: float, case: dict) -> dict:
    """Check if the confidence score is in the expected range."""
    min_ok = confidence >= case.get("confidence_min", 0)
    max_ok = confidence <= case.get("confidence_max", 10)
    passed = min_ok and max_ok

    bounds = []
    if "confidence_min" in case:
        bounds.append(f"≥{case['confidence_min']}")
    if "confidence_max" in case:
        bounds.append(f"≤{case['confidence_max']}")

    return {
        "pass": passed,
        "score": 1.0 if passed else 0.0,
        "detail": f"Score {confidence:.1f} — expected {' and '.join(bounds)}",
    }


def evaluate_report(report: dict, case: dict) -> dict:
    """Run Level 1 evaluation for a single test case."""
    recommendation = report.get("recommendation", "")
    confidence = float(report.get("confidence_score", 0))

    rec_result = score_recommendation(recommendation, case["expected_recommendation"])
    conf_result = score_confidence(confidence, case)

    overall_pass = rec_result["pass"] and conf_result["pass"]
    overall_score = (rec_result["score"] + conf_result["score"]) / 2

    return {
        "target": case["target"],
        "company": case["company"],
        "indication": case["indication"],
        "ground_truth": case["expected_recommendation"],
        "ground_truth_rationale": case["rationale"],
        "ground_truth_source": case["source"],
        "recommendation_result": rec_result,
        "confidence_result": conf_result,
        "overall_pass": overall_pass,
        "overall_score": overall_score,
    }


def summarize_results(results: list[dict]) -> dict:
    """Aggregate scores across all test cases."""
    total = len(results)
    passed = sum(1 for r in results if r["overall_pass"])
    avg_score = sum(r["overall_score"] for r in results) / total if total else 0

    return {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "avg_score": round(avg_score, 3),
    }
