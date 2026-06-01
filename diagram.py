"""
Generates a visual diagram of the agentic workflow.
Run: python diagram.py
Output: workflow_diagram.png
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(1, 1, figsize=(18, 14))
ax.set_xlim(0, 18)
ax.set_ylim(0, 14)
ax.axis("off")
fig.patch.set_facecolor("#f8f9fa")

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "ui":       "#4A90D9",
    "parser":   "#7B68EE",
    "prefetch": "#20B2AA",
    "agent":    "#E8834E",
    "tool":     "#95C8A0",
    "rag":      "#D4A843",
    "synthesis":"#C0504D",
    "judge":    "#8B6AB0",
    "output":   "#2E7D32",
    "arrow":    "#555555",
    "bg":       "#FFFFFF",
}


def box(ax, x, y, w, h, label, sublabel="", color="#4A90D9", fontsize=9):
    rect = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.08",
        facecolor=color, edgecolor="white",
        linewidth=2, alpha=0.92, zorder=3,
    )
    ax.add_patch(rect)
    if sublabel:
        ax.text(x, y + 0.15, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color="white", zorder=4)
        ax.text(x, y - 0.22, sublabel, ha="center", va="center",
                fontsize=7, color="white", alpha=0.9, zorder=4)
    else:
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color="white", zorder=4)


def arrow(ax, x1, y1, x2, y2, label="", color="#555555"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.8),
        zorder=2,
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.1, my, label, fontsize=7, color=color, zorder=5)


def section_label(ax, x, y, text):
    ax.text(x, y, text, fontsize=8, color="#888888",
            fontstyle="italic", ha="center", zorder=4)


# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(9, 13.5, "Biotech Target Assessment — Agentic Workflow",
        ha="center", va="center", fontsize=14, fontweight="bold", color="#222222")

# ── Row 1: UI + Parser ────────────────────────────────────────────────────────
box(ax,  5,  12.5, 3.2, 0.9,  "Streamlit UI",
    "Free-form text or structured fields", C["ui"], fontsize=9)
box(ax, 13,  12.5, 3.2, 0.9,  "Query Parser",
    "Haiku 4.5 · Extracts target / company / indication", C["parser"], fontsize=9)

arrow(ax, 6.6, 12.5, 11.4, 12.5)

# ── Row 2: Prefetch ───────────────────────────────────────────────────────────
box(ax, 9, 11.2, 4.5, 0.85, "Prefetch Node",
    "OpenTargets · Disease scores · Clinical candidates", C["prefetch"], fontsize=9)

arrow(ax, 13, 12.05, 10.5, 11.62)          # parser → prefetch
section_label(ax, 9, 10.7, "Runs before parallel agents — deterministic baseline")

# ── Row 3: Parallel agents ────────────────────────────────────────────────────
box(ax, 4.5, 9.7, 4.2, 0.85, "Biology Agent",
    "Haiku 4.5", C["agent"], fontsize=9)
box(ax, 13.5, 9.7, 4.2, 0.85, "Clinical Trial Agent",
    "Haiku 4.5", C["agent"], fontsize=9)

arrow(ax, 7,   10.77, 5.3,  10.12)         # prefetch → biology
arrow(ax, 11,  10.77, 12.7, 10.12)         # prefetch → clinical trials

# ── Row 4: Tools ──────────────────────────────────────────────────────────────
# Biology tools
box(ax, 1.6,  8.3, 2.2, 0.7, "PubMed",       "Peer-reviewed papers",    C["tool"], 8)
box(ax, 4.5,  8.3, 2.2, 0.7, "bioRxiv",      "Preprints · Europe PMC",  C["tool"], 8)
box(ax, 7.4,  8.3, 2.2, 0.7, "Tavily",       "Web search",              C["tool"], 8)

arrow(ax, 4.5, 9.27, 1.6,  8.65)
arrow(ax, 4.5, 9.27, 4.5,  8.65)
arrow(ax, 4.5, 9.27, 7.4,  8.65)

# Clinical trial tools
box(ax, 10.6, 8.3, 2.6, 0.7, "ClinicalTrials.gov", "v2 API",       C["tool"], 8)
box(ax, 13.8, 8.3, 2.2, 0.7, "Tavily",             "Web search",   C["tool"], 8)

arrow(ax, 13.5, 9.27, 10.6, 8.65)
arrow(ax, 13.5, 9.27, 13.8, 8.65)

section_label(ax, 4.5, 7.85, "← Biology tools")
section_label(ax, 13,  7.85, "Clinical trial tools →")

# ── Row 5: Synthesis ──────────────────────────────────────────────────────────
box(ax, 9, 6.8, 4.5, 0.85, "Synthesis Agent",
    "Sonnet 4.6 · Combines all findings", C["synthesis"], fontsize=9)

arrow(ax, 4.5,  9.27, 7.5,  7.22)          # biology → synthesis
arrow(ax, 13.5, 9.27, 10.5, 7.22)          # trials → synthesis

# ── RAG box ───────────────────────────────────────────────────────────────────
box(ax, 2.2, 6.8, 3.2, 1.4,
    "ChromaDB RAG",
    "Target validation framework\nDruggability guide\nClinical stage rates",
    C["rag"], fontsize=8)

arrow(ax, 3.8, 6.8, 6.75, 6.8)             # RAG → synthesis
section_label(ax, 2.2, 5.95, "BAAI/bge-base-en-v1.5\nLocal embeddings")

# ── Row 6: Judge ──────────────────────────────────────────────────────────────
box(ax, 9, 5.4, 4.5, 0.85, "Judge Node",
    "Sonnet 4.6 · Scores report quality 1–5 per section", C["judge"], fontsize=9)

arrow(ax, 9, 6.37, 9, 5.82)               # synthesis → judge

# ── Row 7: Output ─────────────────────────────────────────────────────────────
box(ax, 9, 3.9, 7.5, 1.6,
    "Assessment Report",
    "Recommendation (Strong/Moderate/Weak/Against)  ·  Confidence Score 0–10\n"
    "Biology Rationale  ·  Druggability  ·  Clinical Precedent\n"
    "Competitive Landscape  ·  Key Risks  ·  Report Quality Panel",
    C["output"], fontsize=8.5)

arrow(ax, 9, 4.97, 9, 4.7)                # judge → output

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    (C["ui"],       "UI / Entry point"),
    (C["parser"],   "Query parser"),
    (C["prefetch"], "Pre-fetch node"),
    (C["agent"],    "Search agent (Haiku)"),
    (C["tool"],     "External API tool"),
    (C["rag"],      "RAG knowledge base"),
    (C["synthesis"],"Synthesis (Sonnet)"),
    (C["judge"],    "Judge node (Sonnet)"),
    (C["output"],   "Final output"),
]
for i, (color, label) in enumerate(legend_items):
    lx = 14.8 + (i % 2) * 1.6
    ly = 3.0 - (i // 2) * 0.55
    patch = FancyBboxPatch((lx - 0.15, ly - 0.17), 0.3, 0.34,
                           boxstyle="round,pad=0.03", facecolor=color,
                           edgecolor="white", linewidth=1, zorder=3)
    ax.add_patch(patch)
    ax.text(lx + 0.25, ly, label, fontsize=7, va="center", color="#333333", zorder=4)

ax.text(15.6, 3.2, "Legend", fontsize=8, fontweight="bold", color="#555555")

plt.tight_layout()
plt.savefig("workflow_diagram.png", dpi=150, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: workflow_diagram.png")
plt.show()
