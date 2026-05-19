from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


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
