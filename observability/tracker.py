"""
Lightweight per-run observability tracker.

Collects token usage, latency, tool call counts, and cost estimates for every
node in the pipeline. Writes one JSON record per run to observability/runs.jsonl.

Usage
-----
In app.py (run start):
    from observability.tracker import start_run
    tracker = start_run(target, company, indication)

In each node:
    from observability.tracker import get_tracker
    tracker = get_tracker()
    if tracker:
        tracker.record_node("biology", response, latency_s=elapsed, tool_calls=n)

In app.py (run end):
    tracker.finalize(report)
    tracker.save()
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from logger import get_logger

log = get_logger(__name__)

RUNS_FILE = Path(__file__).parent / "runs.jsonl"

# Cost per million tokens (USD) — update when pricing changes
_COST_PER_MTK = {
    "claude-haiku-4-5":  {"input": 0.80,  "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00},
}


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_MTK.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


@dataclass
class NodeRecord:
    node: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    tool_calls: int = 0
    error: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return _cost_usd(self.model, self.input_tokens, self.output_tokens)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "latency_s": round(self.latency_s, 2),
            "tool_calls": self.tool_calls,
            "cost_usd": round(self.cost_usd, 5),
            "error": self.error,
        }


class RunTracker:
    def __init__(self, target: str, company: str, indication: str) -> None:
        self.target = target
        self.company = company
        self.indication = indication
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self._start = time.perf_counter()
        self._nodes: dict[str, NodeRecord] = {}
        self._followup_turns: list[dict] = []
        self._recommendation: Optional[str] = None
        self._confidence_score: Optional[float] = None
        self._rerun_triggered: bool = False

    # ── Node recording ────────────────────────────────────────────────────────

    def record_node(
        self,
        node: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_s: float,
        tool_calls: int = 0,
        error: bool = False,
    ) -> None:
        """
        Record metrics for one node. For nodes with multi-iteration loops
        (biology, clinical_trials), pass the CUMULATIVE token totals across
        all Anthropic calls in that node's loop.
        """
        rec = NodeRecord(
            node=node,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_s=latency_s,
            tool_calls=tool_calls,
            error=error,
        )
        # If judge triggers a biology re-run, accumulate into the existing record
        if node in self._nodes:
            existing = self._nodes[node]
            rec.input_tokens  += existing.input_tokens
            rec.output_tokens += existing.output_tokens
            rec.latency_s     += existing.latency_s
            rec.tool_calls    += existing.tool_calls
            if error:
                rec.error = True

        self._nodes[node] = rec
        log.info(
            f"[tracker] {node}: {rec.input_tokens}in/{rec.output_tokens}out tokens "
            f"| {rec.latency_s:.1f}s | {rec.tool_calls} tool calls "
            f"| ${rec.cost_usd:.4f}"
        )

    def record_followup(
        self, model: str, input_tokens: int, output_tokens: int, latency_s: float
    ) -> None:
        self._followup_turns.append({
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_s": round(latency_s, 2),
            "cost_usd": round(_cost_usd(model, input_tokens, output_tokens), 5),
        })

    # ── Finalization ──────────────────────────────────────────────────────────

    def finalize(self, report: dict) -> None:
        self._recommendation   = report.get("recommendation")
        self._confidence_score = report.get("confidence_score")
        self._rerun_triggered  = "biology" in self._nodes and self._nodes["biology"].tool_calls > 0

    def to_dict(self) -> dict:
        nodes_out = {name: rec.to_dict() for name, rec in self._nodes.items()}
        total_input  = sum(r.input_tokens  for r in self._nodes.values())
        total_output = sum(r.output_tokens for r in self._nodes.values())
        total_cost   = sum(r.cost_usd      for r in self._nodes.values())

        followup_cost = sum(t["cost_usd"] for t in self._followup_turns)

        return {
            "run_id":           self.run_id,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "target":           self.target,
            "company":          self.company,
            "indication":       self.indication,
            "recommendation":   self._recommendation,
            "confidence_score": self._confidence_score,
            "rerun_triggered":  self._rerun_triggered,
            "total_latency_s":  round(time.perf_counter() - self._start, 2),
            "nodes":            nodes_out,
            "followup_turns":   self._followup_turns,
            "totals": {
                "input_tokens":  total_input,
                "output_tokens": total_output,
                "total_tokens":  total_input + total_output,
                "pipeline_cost_usd":  round(total_cost, 5),
                "followup_cost_usd":  round(followup_cost, 5),
                "total_cost_usd":     round(total_cost + followup_cost, 5),
            },
        }

    def save(self) -> None:
        RUNS_FILE.parent.mkdir(exist_ok=True)
        record = self.to_dict()
        with open(RUNS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        log.info(
            f"[tracker] Run saved — total ${record['totals']['total_cost_usd']:.4f} "
            f"| {record['totals']['total_tokens']} tokens "
            f"| {record['total_latency_s']}s"
        )

    def summary(self) -> str:
        """One-line summary for Streamlit status display."""
        d = self.to_dict()
        return (
            f"${d['totals']['total_cost_usd']:.3f} | "
            f"{d['totals']['total_tokens']} tokens | "
            f"{d['total_latency_s']}s"
        )


# ── Module-level singleton ────────────────────────────────────────────────────
# Safe for single-user Streamlit (one session = one thread).

_current_run: Optional[RunTracker] = None


def start_run(target: str, company: str, indication: str) -> RunTracker:
    global _current_run
    _current_run = RunTracker(target, company, indication)
    return _current_run


def get_tracker() -> Optional[RunTracker]:
    return _current_run
