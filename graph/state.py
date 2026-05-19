from typing import TypedDict, Annotated, Optional
import operator


class TargetAssessmentState(TypedDict):
    # Inputs
    target: str
    company: str
    indication: str

    # Parallel node outputs — operator.add merges lists from concurrent nodes
    bio_findings: Annotated[list[dict], operator.add]
    trial_findings: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]

    # Final output
    report: Optional[dict]
