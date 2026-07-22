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


EvidenceType = Literal[
    "human_genetics",       # GWAS / OpenTargets genetic association
    "rare_variant",         # ClinVar / OMIM
    "crispr_dependency",    # DepMap
    "tissue_expression",    # HPA / GTEx
    "pathway_biology",      # Reactome
    "literature",           # PubMed
    "preprint",             # bioRxiv / medRxiv
    "company_disclosure",   # general web search (press releases, investor decks)
    "agent_narrative",      # the agent's own free-text analysis, not tied to one source
]


class BiologyFinding(BaseModel):
    """A single finding produced by the biology search agent."""
    type: str = Field(description="Finding category, e.g. 'biology_summary'.")
    content: str = Field(description="Full text of the finding.")
    source: str = Field(description="Agent or tool that produced this finding.")
    evidence_type: EvidenceType = Field(
        default="agent_narrative",
        description="Evidence category, used to weight sources during synthesis.",
    )


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
            "Modality-agnostic druggability assessment: which therapeutic modality "
            "(small molecule, large molecule/antibody, or other e.g. PROTAC, oligonucleotide) "
            "the target's biology actually supports, which modality the company is pursuing, "
            "and whether that choice fits the biology — accessibility, binding pocket, format, "
            "PK considerations."
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
            "0–4: weak evidence, significant red flags, OR the company's chosen modality is a "
            "poor fit for the target's biology per druggability_assessment — a modality mismatch "
            "caps this score regardless of how strong the underlying biological validation is."
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
            "Weak: significant concerns. Against: fundamental issues. "
            "Derived deterministically from confidence_score (see synthesis.py "
            "_derive_recommendation) rather than chosen independently by the model — "
            "the two were observed to drift (e.g. confidence_score=8.0 paired with "
            "recommendation='Moderate'). Not part of the tool schema the model fills in."
        )
    )
    recommendation_summary: str = Field(
        description="2–3 sentence plain-English summary of the assessment for a non-expert audience."
    )
