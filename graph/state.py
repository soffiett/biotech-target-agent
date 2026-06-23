from typing import TypedDict, Annotated, Optional
import operator


class TargetAssessmentState(TypedDict):
    # Inputs
    target: str
    company: str
    indication: str

    # Pre-fetched structured data (OpenTargets + UniProt) — set before parallel nodes
    prefetch_context: dict

    # Parallel node outputs — operator.add merges lists from concurrent nodes
    bio_findings: Annotated[list[dict], operator.add]
    trial_findings: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]

    # Final output
    report: Optional[dict]
    quality_assessment: Optional[dict]

    # Judge → biology re-run loop
    rerun_count: int          # incremented each time biology node runs; caps re-runs at 1
    judge_critique: Optional[dict]  # set by judge when biology scores <= 2; injected into re-run
