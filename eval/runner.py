"""
Evaluation Runner — orchestrates all three evaluation levels.

Usage:
  # Run full ground truth suite
  python -m eval.runner

  # Evaluate a specific target (auto-detects ground truth vs novel)
  python -m eval.runner --target PD-L1 --company Genentech --indication NSCLC

  # Force consistency check on a known target
  python -m eval.runner --target TIGIT --company Roche --mode consistency
"""

import argparse
import json
import sys
from graph.orchestrator import graph
from graph.state import make_initial_state
from eval.ground_truth import TEST_CASES, evaluate_report, summarize_results
from eval.llm_judge import judge_report
from eval.consistency_check import check_consistency


def _run_agent(target: str, company: str, indication: str) -> dict:
    result = graph.invoke(make_initial_state(target, company, indication))
    return result.get("report", {})


def _find_ground_truth(target: str, indication: str) -> dict | None:
    """Check if this target has a curated ground truth test case."""
    for case in TEST_CASES:
        if (case["target"].lower() == target.lower() and
                (not indication or case["indication"].lower() in indication.lower())):
            return case
    return None


def run_full_suite(verbose: bool = True) -> dict:
    """Run Level 1 evaluation on all ground truth test cases."""
    print(f"\n{'='*60}")
    print("LEVEL 1: GROUND TRUTH EVALUATION")
    print(f"Running {len(TEST_CASES)} test cases...")
    print(f"{'='*60}\n")

    results = []
    for case in TEST_CASES:
        print(f"Testing: {case['target']} / {case['company']} / {case['indication']}")
        report = _run_agent(case["target"], case["company"], case["indication"])
        result = evaluate_report(report, case)
        results.append({**result, "report": report})

        status = "✓ PASS" if result["overall_pass"] else "✗ FAIL"
        print(f"  {status} | Expected: {case['expected_recommendation']} | "
              f"Got: {report.get('recommendation')} | "
              f"Confidence: {report.get('confidence_score')}\n")

        # Auto-trigger Level 2 on failures
        if not result["overall_pass"] and verbose:
            print(f"  → Triggering LLM judge to diagnose failure...")
            judge = judge_report(report, case["target"], case["company"])
            result["llm_judge"] = judge
            print(f"  → Weakest section: {judge.get('weakest_section')}")
            print(f"  → Top improvement: {judge.get('top_improvement')}\n")

    summary = summarize_results(results)
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Pass rate:  {summary['pass_rate']}%  ({summary['passed']}/{summary['total_cases']})")
    print(f"Avg score:  {summary['avg_score']}")
    print(f"{'='*60}\n")

    return {"summary": summary, "results": results}


def run_single(target: str, company: str, indication: str, mode: str = "auto") -> dict:
    """Evaluate a single target — auto-detects which eval path to use."""
    print(f"\n{'='*60}")
    print(f"EVALUATING: {target} / {company} / {indication or 'any'}")
    print(f"{'='*60}\n")

    ground_truth_case = _find_ground_truth(target, indication)

    if mode == "consistency" or (mode == "auto" and not ground_truth_case):
        # Novel target — consistency check + Level 2
        print("No ground truth found → running consistency check...\n")
        consistency = check_consistency(target, company, indication)

        print(f"Consistency: {consistency['reliability'].upper()}")
        print(f"Recommendations: {consistency['recommendations']}")
        print(f"Confidence range: {consistency['confidence_range']} points\n")

        # Use the first report for Level 2 judging
        report = consistency["reports"][0] if consistency["reports"] else {}
        print("Running LLM judge on first report...\n")
        judge = judge_report(report, target, company)

        print(f"Overall quality: {judge.get('overall_quality')}/5")
        print(f"Weakest section: {judge.get('weakest_section')}")
        print(f"Top improvement: {judge.get('top_improvement')}\n")

        return {"consistency": consistency, "llm_judge": judge}

    else:
        # Known target — Level 1 + Level 2 on failure
        print(f"Ground truth found: {ground_truth_case['rationale']}\n")
        report = _run_agent(target, company, indication)
        result = evaluate_report(report, ground_truth_case)

        status = "✓ PASS" if result["overall_pass"] else "✗ FAIL"
        print(f"{status} | Expected: {ground_truth_case['expected_recommendation']} | "
              f"Got: {report.get('recommendation')} | "
              f"Confidence: {report.get('confidence_score')}\n")

        judge = None
        if not result["overall_pass"] or mode == "full":
            print("Running LLM judge...\n")
            judge = judge_report(report, target, company)
            print(f"Overall quality: {judge.get('overall_quality')}/5")
            print(f"Weakest section: {judge.get('weakest_section')}")
            print(f"Top improvement: {judge.get('top_improvement')}\n")

        return {"ground_truth": result, "llm_judge": judge, "report": report}


def main():
    parser = argparse.ArgumentParser(description="Biotech Target Assessment — Evaluation Runner")
    parser.add_argument("--target", type=str, help="Drug target (e.g. PD-L1)")
    parser.add_argument("--company", type=str, help="Company name (e.g. Genentech)")
    parser.add_argument("--indication", type=str, default="", help="Disease indication (optional)")
    parser.add_argument(
        "--mode",
        choices=["auto", "consistency", "full", "suite"],
        default="auto",
        help="auto: smart routing | consistency: force consistency check | full: L1+L2 | suite: all test cases",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    if args.mode == "suite" or (not args.target and not args.company):
        results = run_full_suite()
    elif args.target and args.company:
        results = run_single(args.target, args.company, args.indication, args.mode)
    else:
        parser.print_help()
        sys.exit(1)

    if args.json:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
