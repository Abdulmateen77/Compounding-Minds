"""Held-out report: JSON for the dashboard panel, Markdown for the README and the slide.

The official report is written once. `write_report` refuses to overwrite it unless `force`
is set, so nobody quietly regenerates it after peeking and tuning (README 9).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .split import Split

REPORT_NAME = "heldout_report"
NOT_RESULTS = ("NOT RESULTS. Stub or scripted inputs: this run only exercises the harness. "
               "Do not quote these numbers.")


def build_report(split: Split, agents: dict[str, dict], provenance: dict) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": provenance,
        "disclaimer": "Research tool, not financial advice.",
        "banner": None if provenance.get("real_results") else NOT_RESULTS,
        "split": split.to_dict(),
        "agents": agents,
    }


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _num(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def _signed(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.1f} pts" if pct else f"{x:+.3f}"


def render_markdown(report: dict) -> str:
    out = ["# Held-out report: frozen vs learned vs baselines", ""]
    if report["banner"]:
        out += [f"> **{report['banner']}**", ""]
    sp = report["split"]
    out += [f"Train window {sp['train_window'][0]} to {sp['train_window'][1]}, held-out window "
            f"{sp['held_out_window'][0]} to {sp['held_out_window'][1]}. "
            f"{len(sp['train_companies'])} train companies, {len(sp['held_out_companies'])} held out for good.",
            "Accuracy is higher-is-better. Brier is lower-is-better. Only cells where both the frozen and the "
            "learned agent produced a resolved grade are counted.", ""]
    labels = {"all_companies": "All companies", "seen_companies": "Companies seen in training",
              "unseen_companies": "Held-out companies (never seen)"}
    for agent, r in report["agents"].items():
        out += [f"## {agent}", "",
                f"Corrections applied in training: {r['corrections_applied']}. "
                f"Model version {r['learned_version_start']} to {r['learned_version_end']}. "
                f"Dropped calls (held-out, frozen/learned): {r['held_out_dropped']['frozen']}/{r['held_out_dropped']['learned']}.", ""]
        for seg, label in labels.items():
            s = r["segments"][seg]
            out += [f"### {label} (n = {s['n']})", "",
                    "| | accuracy | Brier |", "|---|---|---|",
                    f"| frozen | {_pct(s['frozen']['accuracy'])} | {_num(s['frozen']['brier'])} |",
                    f"| learned | {_pct(s['learned']['accuracy'])} | {_num(s['learned']['brier'])} |"]
            for name, b in s["baselines"].items():
                out.append(f"| {name} | {_pct(b['accuracy'])} | {_num(b['brier'])} |")
            d = s["learned_minus_frozen"]
            out += ["", f"Learned minus frozen: accuracy {_signed(d['accuracy'], pct=True)}, Brier {_signed(d['brier'])}.", ""]
    out += ["---", "", "*Research tool, not financial advice.*", ""]
    return "\n".join(out)


def write_report(report: dict, out_dir: Path | str, force: bool = False) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    js, md = out / f"{REPORT_NAME}.json", out / f"{REPORT_NAME}.md"
    if js.exists() and not force:
        raise FileExistsError(f"{js} already exists. The held-out report is generated once; "
                              "pass force=True only if you are deliberately replacing it.")
    js.write_text(json.dumps(report, indent=2))
    md.write_text(render_markdown(report))
    return js, md
