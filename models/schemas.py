from typing import Optional, Literal
from pydantic import BaseModel, Field, ValidationError
from enum import Enum


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


class Recommendation(str, Enum):
    STRONG = "Strong"
    MODERATE = "Moderate"
    WEAK = "Weak"
    AGAINST = "Against"


class BiologyFinding(BaseModel):
    type: str
    content: str
    source: str


class TrialFinding(BaseModel):
    type: str
    content: str
    source: str


class AssessmentReport(BaseModel):
    target: str
    company: str
    biology_rationale: str
    druggability_assessment: str
    clinical_precedent: str
    competitive_landscape: str
    key_risks: list[str]
    confidence_score: float = Field(ge=0, le=10)
    confidence_reasoning: str
    recommendation: Recommendation
    recommendation_summary: str
