# Assessment Report Writing Guide

This guide defines what each section of the assessment report must contain.
Follow it precisely — every requirement listed below is evaluated by a quality
reviewer after the report is submitted.

---

## Biology Rationale

**What this section must do:**
Establish whether the biological evidence is strong enough to justify investing
in this target. This is the most scrutinised section — weak biology is the
single most common reason assessments are sent back for revision.

**Required content:**
1. **Named evidence** — cite specific studies, GWAS datasets, or genetic
   associations by name or finding (e.g. "LOF variants in PCSK9 phenocopy statin
   treatment"). Generic statements like "there is supporting evidence" fail.
2. **Evidence tier** — distinguish Tier 1 (human genetic) from Tier 2 (disease
   biology) from Tier 3 (preclinical models). State which tier(s) are present
   and which are missing.
3. **Disease mechanism link** — explain how modulating this target addresses
   the disease mechanism, not just that the target is expressed or associated.
4. **Honest gap acknowledgement** — if genetic evidence is absent, say so. If
   animal models conflict with human data, flag it. A confident-sounding
   rationale that ignores gaps will be scored lower than one that names them.

**Common failures to avoid:**
- Describing what the target does without explaining why blocking/activating it
  would help patients
- Listing evidence without assessing its strength
- No mention of on-target safety signals

---

## Large Molecule Druggability

**What this section must do:**
Assess whether this target is accessible to a biologic and recommend the most
appropriate format. Must be specific to this target, not a generic description
of antibody development.

**Required content:**
1. **Accessibility verdict** — is the target extracellular, cell-surface, or
   intracellular? Antibodies cannot reach intracellular targets without special
   formats (ADC payload, degrader). State this explicitly.
2. **Format recommendation** — recommend one primary format with a reason:
   - Soluble cytokine/secreted protein → neutralising mAb or trap
   - Cell-surface receptor (blocking) → antagonist mAb
   - Cell-surface (killing/depleting) → ADC or ADCC-optimised mAb
   - Two targets needed → bispecific
   - Long half-life critical → Fc-fusion
3. **PK consideration** — note any target-mediated drug disposition (TMDD)
   risk if target expression is high, or tissue penetration challenge if
   relevant (e.g. CNS, solid tumour core).
4. **Differentiation angle** — if competitors exist, note whether a different
   format, epitope, or SC vs IV formulation could differentiate.

**Common failures to avoid:**
- Recommending "a monoclonal antibody" without justifying why over other formats
- Not addressing whether the epitope is accessible
- Ignoring TMDD risk for highly expressed targets

---

## Clinical Precedent

**What this section must do:**
Map what is already known from the clinic about this target or its pathway.
Clinical data — positive or negative — is the strongest available evidence for
or against a target.

**Required content:**
1. **Direct programs** — are there approved drugs, Phase 3, Phase 2, or Phase 1
   programs for this exact target? If yes, name them, their sponsor, phase,
   and indication.
2. **Failures must be mentioned** — if any program targeting this mechanism
   has failed in Phase 2 or Phase 3, it must appear here with the failure
   reason if known. Omitting failures is a critical error.
3. **Pathway analogs** — if the target itself has no clinical data, name the
   closest validated target in the same pathway and what its clinical results
   imply.
4. **Correct conclusion** — does the clinical data validate the biology, raise
   the competitive bar, or both? State the implication clearly.

**Common failures to avoid:**
- Listing only successes
- Describing trials without stating their current status or outcome
- Confusing Phase 1/2 data (hypothesis-generating) with Phase 3 (confirmatory)

---

## Competitive Landscape

**What this section must do:**
Assess whether there is room for a new entrant and what differentiation would
be required.

**Required content:**
1. **Named competitors** — list the main companies and their assets (approved,
   late-stage, or early) for this target.
2. **Crowding assessment** — is this a validated but crowded space (high bar),
   an open space with first-mover advantage available, or a space where all
   prior entrants failed (red flag)?
3. **Differentiation opportunity** — what would the company need to do
   differently to win: superior efficacy, better safety, new patient population,
   novel format, biomarker-selected trial?

**Common failures to avoid:**
- "The competitive landscape is evolving" without naming who is competing
- Not distinguishing between direct competitors (same target) and indirect
  competitors (same pathway)

---

## Key Risks

**What this section must do:**
Identify 3–5 risks that are specific to this target, ranked by importance.
Generic drug development risks (e.g. "clinical trials may fail") do not count.

**Required content — each risk must include:**
- What the specific risk is (e.g. "on-target IL-6 suppression may increase
  infection risk in elderly patients")
- Why it is a risk for this target specifically
- Whether it is addressable (patient selection, biomarker, dose schedule) or
  fundamental

**Risk categories to consider (pick the most relevant, not all):**
- On-target toxicity in normal tissue
- Prior clinical failures with this mechanism
- Biology gaps (no human genetic validation, conflicting preclinical data)
- Competitive crowding or first-to-market disadvantage
- Patient selection / biomarker strategy uncertainty
- Regulatory precedent (what safety database did the prior approval require?)

**Common failures to avoid:**
- Listing risks that apply to every drug ("regulatory risk", "manufacturing risk")
- More than 5 risks without ranking them
- Risks without any explanation of why they apply to this specific target

---

## Confidence Score (0–10) and Reasoning

**What this section must do:**
Provide a calibrated score with explicit bidirectional reasoning. A score
without reasoning in both directions will be returned for revision.

**Calibration anchors:**

| Score | Meaning |
|-------|---------|
| 9–10  | FDA-approved drug exists for this exact target and indication |
| 7–8   | Strong human genetic evidence AND Phase 2/3 data; clear path |
| 5–6   | Validated pathway, early clinical data, meaningful gaps remain |
| 3–4   | Preclinical only or conflicting clinical signals |
| 1–2   | No human validation, major biology or safety concerns |

**Required reasoning structure:**
- **What pushes the score UP:** name the specific evidence (e.g. "GWAS
  confirmation in three cohorts", "Phase 3 approval in adjacent indication")
- **What caps or holds the score DOWN:** name the specific gap or risk (e.g.
  "no human LOF data", "one Phase 3 failure with same mechanism", "crowded
  class with three approved drugs already")

Both directions are required. A score supported only by positive evidence
— without acknowledging what limits confidence — will be scored as incomplete.
