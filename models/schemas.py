from typing import Literal, Optional
from pydantic import BaseModel, Field, ValidationError


class ParsedQuery(BaseModel):
    """Structured fields extracted from a free-form biotech query."""
    target: str = Field(
        description="Drug target or molecule (e.g. PD-L1, HER2). Empty string if not found.")
    company: str = Field(
        description="Biotech or pharma company name. Empty string if not found.")
    indication: str = Field(
        description="Disease or therapeutic indication (e.g. NSCLC). Empty string if not found.")
    confidence: Literal["high", "low"] = Field(
        description="'high' if all key fields clearly stated, else 'low'.")


class BiologyFinding(BaseModel):
    """A single finding produced by the biology search agent."""
    type: str = Field(description="Finding category, e.g. 'biology_summary'.")
    content: str = Field(description="Full text of the finding.")
    source: str = Field(description="Agent or tool that produced this finding.")


class TrialFinding(BaseModel):
    """A single finding produced by the clinical trials search agent."""
    type: str = Field(description="Finding category, e.g. 'trial_summary'.")
    content: str = Field(description="Full text of the finding.")
    source: str = Field(description="Agent or tool that produced this finding.")


class AssessmentReport(BaseModel):
    """Structured drug target assessment report produced by the synthesis agent."""
    target: str = Field(description="Drug target symbol (e.g. PD-L1).")
    company: str = Field(description="Company developing the therapeutic.")
    biology_rationale: str = Field(
        description=(
            "Assessment of biological evidence supporting this target "
            "(genetic, preclinical, mechanistic)."
        )
    )
    druggability_assessment: str = Field(
        description=(
            "Assessment of whether this target is suitable for a large molecule approach — "
            "accessibility, format, PK considerations."
        )
    )
    clinical_precedent: str = Field(
        description=(
            "Summary of existing clinical trials for this target or related mechanisms, "
            "including phase and status."
        )
    )
    competitive_landscape: str = Field(
        description="Overview of other programs (approved or in development) targeting this biology."
    )
    key_risks: list[str] = Field(
        description="Top 3–5 risks or concerns. Be specific."
    )
    confidence_score: float = Field(
        ge=0, le=10,
        description=(
            "0–10. 8–10: highly validated target, clear path. "
            "5–7: moderate evidence, meaningful uncertainties. "
            "0–4: weak evidence or significant red flags."
        )
    )
    confidence_reasoning: str = Field(
        description=(
            "Structured reasoning for the confidence score. Must explicitly state: "
            "(1) what evidence drives the score UPWARD — e.g. genetic validation, approved drugs, "
            "strong preclinical models, guideline endorsement, clinical biomarker data; "
            "(2) what caps or holds the score back — e.g. commercial saturation, clinical failures, "
            "biology gaps, safety signals, mechanism-adjacent competition, non-responder ceiling. "
            "A bare number without this bidirectional justification is not acceptable."
        )
    )
    recommendation: Literal["Strong", "Moderate", "Weak", "Against"] = Field(
        description=(
            "Strong: pursue. Moderate: worth exploring with caveats. "
            "Weak: significant concerns. Against: fundamental issues."
        )
    )
    recommendation_summary: str = Field(
        description="2–3 sentence plain-English summary of the assessment for a non-expert audience."
    )
