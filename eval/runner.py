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
from datetime import datetime, timezone
from pathlib import Path

# Must load env vars before importing graph.orchestrator — it imports node modules
# that create an Anthropic client at import time (see app.py for the same ordering).
from dotenv import load_dotenv
load_dotenv()

from graph.orchestrator import graph
from graph.state import make_initial_state
from eval.ground_truth import TEST_CASES, evaluate_report, summarize_results
from eval.llm_judge import judge_report
from eval.consistency_check import check_consistency

TRANSCRIPT_DIR = Path(__file__).parent / "transcripts"


def _run_agent(target: str, company: str, indication: str) -> tuple[dict, dict]:
    """Run the full pipeline and return (report, full_state)."""
    full_state = graph.invoke(make_initial_state(target, company, indication))
    return full_state.get("report", {}), full_state


def _save_transcript(
    full_state: dict,
    eval_result: dict | None = None,
    llm_judge: dict | None = None,
    label: str = "",
) -> Path:
    """
    Write a human-readable markdown transcript of one eval run.
    Captures the full agent process so regressions can be diagnosed by reading
    what each node produced, not just the final pass/fail.
    Only called from the eval runner — never from the production app.
    """
    TRANSCRIPT_DIR.mkdir(exist_ok=True)

    target    = full_state.get("target", "unknown")
    company   = full_state.get("company", "unknown")
    ts        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    slug      = f"{target}_{company}_{ts}".replace(" ", "_").replace("/", "-")
    out_path  = TRANSCRIPT_DIR / f"{slug}.md"

    report   = full_state.get("report") or {}
    quality  = full_state.get("quality_assessment") or {}
    bio      = full_state.get("bio_findings", [])
    trials   = full_state.get("trial_findings", [])
    errors   = full_state.get("errors", [])
    rerun    = full_state.get("rerun_count", 0)
    critique = full_state.get("judge_critique")
    ot       = full_state.get("prefetch_context", {}).get("opentargets", {})

    lines = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines += [
        f"# Eval Transcript: {target} / {company}",
        f"**Indication:** {full_state.get('indication', 'not specified')}  ",
        f"**Run:** {ts}  ",
        f"**Label:** {label or '—'}",
        "",
    ]

    # ── Eval result (if ground truth available) ──────────────────────────────
    if eval_result:
        status = "✓ PASS" if eval_result.get("overall_pass") else "✗ FAIL"
        lines += [
            "## Ground Truth Result",
            f"**{status}**  ",
            f"Expected: `{eval_result.get('ground_truth')}`  ",
            f"Got: `{report.get('recommendation')}` (confidence {report.get('confidence_score')})  ",
            f"Rationale: {eval_result.get('ground_truth_rationale', '—')}",
            "",
        ]

    # ── Prefetch context ─────────────────────────────────────────────────────
    lines += ["## Prefetch (OpenTargets)", ""]
    drugs = ot.get("known_drugs", [])
    if drugs:
        lines.append(f"**Known drugs ({len(drugs)}):** " +
                     ", ".join(d.get("name", "?") for d in drugs[:5]))
    else:
        lines.append("No known drugs found.")
    diseases = ot.get("top_diseases", [])
    lines.append(f"**Top disease associations:** {len(diseases)} returned")
    lines.append("")

    # ── Biology findings ─────────────────────────────────────────────────────
    lines += [f"## Biology Agent ({len(bio)} finding(s), {rerun} run(s))", ""]
    if rerun > 1 and critique:
        lines += [
            f"**Re-run triggered** — biology scored {critique.get('biology_score')}/5",
            f"Issues: {'; '.join(critique.get('biology_issues', []))}",
            "",
        ]
    for i, f in enumerate(bio, 1):
        lines.append(f"### Finding {i}")
        lines.append(f["content"] if isinstance(f, dict) else str(f))
        lines.append("")

    # ── Clinical trial findings ───────────────────────────────────────────────
    lines += [f"## Clinical Trials Agent ({len(trials)} finding(s))", ""]
    for i, f in enumerate(trials, 1):
        lines.append(f"### Finding {i}")
        lines.append(f["content"] if isinstance(f, dict) else str(f))
        lines.append("")

    # ── Assessment report ─────────────────────────────────────────────────────
    lines += [
        "## Synthesis Report",
        f"**Recommendation:** {report.get('recommendation', '—')}  ",
        f"**Confidence:** {report.get('confidence_score', '—')}/10  ",
        f"**Summary:** {report.get('recommendation_summary', '—')}",
        "",
        "### Biology Rationale",
        report.get("biology_rationale", "—"), "",
        "### Druggability",
        report.get("druggability_assessment", "—"), "",
        "### Clinical Precedent",
        report.get("clinical_precedent", "—"), "",
        "### Competitive Landscape",
        report.get("competitive_landscape", "—"), "",
        "### Key Risks",
    ]
    for r in report.get("key_risks", []):
        lines.append(f"- {r}")
    lines += [
        "",
        "### Confidence Reasoning",
        report.get("confidence_reasoning", "—"), "",
    ]

    # ── Judge scores ──────────────────────────────────────────────────────────
    lines += ["## Judge Scores", ""]
    if "error" in quality:
        lines.append(f"**Judge error:** {quality['error']}")
    else:
        lines.append(f"**Overall quality:** {quality.get('overall_quality', '—')}/5  ")
        lines.append(f"**Strongest:** {quality.get('strongest_section', '—')}  ")
        lines.append(f"**Weakest:** {quality.get('weakest_section', '—')}  ")
        lines.append(f"**Top improvement:** {quality.get('top_improvement', '—')}")
        lines.append("")
        for s in quality.get("section_scores", []):
            bar = "█" * s["score"] + "░" * (5 - s["score"])
            lines.append(f"**{s['section']}** `{bar}` {s['score']}/5 — {s['reasoning']}")
            for issue in s.get("issues", []):
                lines.append(f"  - ⚠ {issue}")
    lines.append("")

    # ── LLM judge (standalone, from runner) ──────────────────────────────────
    if llm_judge and "error" not in llm_judge:
        lines += ["## LLM Judge (Standalone)", ""]
        lines.append(f"**Overall:** {llm_judge.get('overall_quality', '—')}/5  ")
        lines.append(f"**Weakest:** {llm_judge.get('weakest_section', '—')}  ")
        lines.append(f"**Top improvement:** {llm_judge.get('top_improvement', '—')}")
        lines.append("")

    # ── Errors ───────────────────────────────────────────────────────────────
    if errors:
        lines += ["## Pipeline Errors", ""]
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


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
        report, full_state = _run_agent(case["target"], case["company"], case["indication"])
        result = evaluate_report(report, case)
        results.append({**result, "report": report})

        status = "✓ PASS" if result["overall_pass"] else "✗ FAIL"
        print(f"  {status} | Expected: {case['expected_recommendation']} | "
              f"Got: {report.get('recommendation')} | "
              f"Confidence: {report.get('confidence_score')}\n")

        judge = None
        # Auto-trigger Level 2 on failures
        if not result["overall_pass"] and verbose:
            print(f"  → Triggering LLM judge to diagnose failure...")
            judge = judge_report(report, case["target"], case["company"])
            result["llm_judge"] = judge
            print(f"  → Weakest section: {judge.get('weakest_section')}")
            print(f"  → Top improvement: {judge.get('top_improvement')}\n")

        transcript_path = _save_transcript(full_state, eval_result=result, llm_judge=judge,
                                           label=case.get("rationale", ""))
        print(f"  → Transcript: {transcript_path.name}")

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
        report, full_state = _run_agent(target, company, indication)
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

        transcript_path = _save_transcript(full_state, eval_result=result, llm_judge=judge,
                                           label=ground_truth_case.get("rationale", ""))
        print(f"Transcript: {transcript_path}")

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
