# Small Molecule Druggability Guide

## What Is a Small Molecule?
Small molecule therapeutics are low molecular weight (typically <900 Da) synthetic compounds that
can cross cell membranes, enabling both extracellular and intracellular target engagement. Includes
oral kinase inhibitors, allosteric modulators, nuclear receptor ligands, and degrader modalities
(PROTACs, molecular glues).

## Ideal Small Molecule Targets

### Druggable Pocket Requirement
Unlike large molecules, subcellular location is not the limiting factor — a small molecule can reach
intracellular targets. The limiting factor is whether a druggable pocket exists:
- **Enzymes with a defined active site**: kinases (ATP-binding pocket), proteases, phosphatases —
  classic, well-precedented target class
- **GPCRs and ion channels**: orthosteric or allosteric binding sites — historically the most
  successful small-molecule target class
- **Nuclear receptors**: ligand-binding domain (e.g. estrogen, androgen receptor)
- **Protein-protein interaction (PPI) interfaces**: harder — usually flat/featureless, but "hot spot"
  pockets exist for some (e.g. MDM2-p53)

### Location Is Not a Barrier
- Intracellular kinases, nuclear receptors, and cytoplasmic enzymes are all directly accessible —
  the opposite of the large-molecule accessibility constraint
- CNS targets are reachable if the compound is designed for blood-brain-barrier penetration (its own
  med-chem challenge, but a fundamentally different one than for antibodies)

### "Undruggable" Targets
Featureless PPI surfaces (e.g. many transcription-factor interfaces) lack a pocket for classical
inhibitors. Historically undruggable targets (mutant KRAS before covalent G12C inhibitors, MYC,
STAT3) may require:
- Covalent fragment approaches exploiting a rare reactive residue
- **PROTACs / molecular glues** — degrade the target via the ubiquitin-proteasome system; only need
  a ternary-complex-competent surface, not a functional inhibitory pocket
- **Antisense oligonucleotides (ASO) / siRNA** — act on the transcript, bypassing protein structure
  entirely; viable when there is no tractable protein-level pocket at all

## Format Selection Guide

| Target Type | Preferred Format | Rationale |
|------------|-----------------|-----------|
| Kinase (ATP pocket) | ATP-competitive or allosteric inhibitor | Well-precedented, oral bioavailability achievable |
| GPCR / ion channel | Orthosteric or allosteric small molecule | Historically most successful modality for this class |
| Nuclear receptor | Ligand-binding-domain agonist/antagonist | Direct, oral, well-precedented (e.g. endocrine therapy) |
| No functional pocket, surface groove | PROTAC / molecular glue | Degrades target via endogenous ubiquitin-proteasome system |
| No protein-level tractability at all | Antisense oligonucleotide (ASO) / siRNA | Acts on mRNA, bypasses protein structure entirely |
| Featureless PPI interface | Often intractable for small molecule | Consider large molecule (if extracellular) or a degrader |

## Pharmacokinetic Considerations
- Oral bioavailability is the major differentiator vs. biologics, but requires favorable
  physicochemical properties (roughly Lipinski's Rule of Five: MW <500, logP <5, H-bond donors <5,
  acceptors <10)
- Typical half-life is hours, requiring once/twice-daily dosing (vs. weeks for mAbs) unless
  specifically engineered for extended release
- CYP450 metabolism and drug-drug interaction risk is a small-molecule-specific liability largely
  absent in biologics
- Tissue and CNS penetration can exceed large molecules — an advantage for solid-tumor-core or CNS
  indications

## Competitive Format Considerations
- Generic risk after patent expiry (vs. biosimilar risk for large molecules) is typically a steeper
  revenue cliff
- Combination potential with other orals is often simpler (fixed-dose combinations) than combining
  biologics
- Covalent vs. reversible inhibition can be a differentiator (durability vs. reversibility/safety)
