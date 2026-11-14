"""The report — OWNER: Mahamoodoul. The artefact the judges are guaranteed to see.

Renders one run into Markdown and a single self-contained HTML file. No build
step, no CDN, no JavaScript, no web font: it opens from a file:// URL on a
laptop with no network, because tonight the VM is gone and the conference wifi
will be worse than it is now.

What this file refuses to do, since every one of these is a way to lose the 40%:

  - Collapse the three axes into one number. The joint score is shown *and*
    decomposed, every time, because "excellent on two axes and hopeless on the
    third" scores zero S-tier and a single number hides exactly that.
  - Print a prediction next to a measurement without saying which is which.
    Every axis cell carries its provenance; the legend is not optional.
  - Hide the funnel. Rejected candidates and their exact failure reasons are
    in the report, because "what did you throw away?" is a question a judge
    asks and a pipeline that cannot answer it is not reproducible.
  - Lead with wins. The null result from the proof lane goes above the picks,
    not in an appendix, because a team that names its own failure mode reads as
    credible and one showing only wins reads as overfitted.

Usage is through `write_outputs`; `python3 -m fourwells.report RUNDIR` re-renders
an existing run from its JSONL, which is how the pitch gets iterated without
re-running any model.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .schema import AXES, DesignRecord, read_jsonl

# The three axes, in the order the lab measures them, with how each is obtained.
AXIS_META = {
    "binding": ("Binding", "SPR", "predicted"),
    "epitope": ("Epitope", "competitive binding vs trastuzumab", "predicted"),
    "stability": ("Thermostability", "direct measurement", "predicted"),
}

BASELINE = 0.5  # by construction: the reference scores 0.500 on every axis

# Our own ranker's named mistakes on the blind SPR pool. Facts about the provided
# dataset, not about any one run, so they are constants — regenerate with
# `python3 proof/enrichment.py` and copy the two cases it names.
KNOWN_FAILURES = (
    {
        "label": "Most confident wrong call",
        "cdrh3": "YNAGMYVYTG",
        "detail": "ranked **1 of 114** by a CDRH3 sequence model, and it measures "
                  "124 nM — about 1,300× weaker than trastuzumab. It shares no residue "
                  "with the parent loop, and the model rewarded that because what it "
                  "learned is which residues appear in high-binding variants, not where "
                  "the antibody touches HER2.",
    },
    {
        "label": "Worst miss",
        "cdrh3": "WKGYGSYVHD",
        "detail": "binds at 0.723 nM — a genuinely good binder — and the same model "
                  "ranked it **112 of 114**. A site-independent score cannot see two "
                  "mutations that compensate for each other, so a real binder built that "
                  "way is invisible to it.",
    },
)

_NUMERIC = re.compile(r"^[-+]?[.,]?\d")
_OPERATORS = {">=", "<=", ">", "<", "==", "!=", "="}
_TRAILING = {"needs", "need", "is", "of", "to", "than", "not"}


# ---------------------------------------------------------------- helpers

def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def _verdict(rec: DesignRecord) -> str:
    """Predicted tier, from the axes alone. S beats all three, A two, B one."""
    beat = sum(1 for a in AXES if (rec.axes.get(a) or 0) > BASELINE)
    return {3: "S", 2: "A", 1: "B"}.get(beat, "—")


def _rule_name(rule: str) -> str:
    """Group failures by rule, not by the value that tripped it.

    Gate messages embed the measurement — "CDRH3 identity 0.90 >= 0.7" and
    "CDRH3 identity 0.80 >= 0.7" are one rule failing twice, and tallying the
    raw strings makes one rule look like several.
    """
    # Keep the first clause only — the part after the comma is always the
    # threshold ("…, needs >= 2").
    head = rule.split("(")[0].split(",")[0].strip().rstrip(":")
    words: list[str] = []
    for w in head.split():
        # Stop at a comparison, and *drop* measurements rather than truncating
        # at them: real messages start with one ("3 CDRH3 mutations from …"),
        # and a token that merely contains a digit is usually the rule's own
        # name ("CDRH3", "immunum").
        if w in _OPERATORS:
            break
        if _NUMERIC.match(w):
            continue
        words.append(w)
    while words and words[-1].lower() in _TRAILING:
        words.pop()
    return " ".join(words) or head


def _funnel(records: list[DesignRecord]) -> dict[str, Any]:
    failed: dict[str, int] = {}
    for r in records:
        for rule in r.gates.failed_rules or []:
            key = _rule_name(rule)
            failed[key] = failed.get(key, 0) + 1
    passed = [r for r in records if r.gates.passed]
    return {
        "generated": len(records),
        "passed": len(passed),
        "rejected": len(records) - len(passed),
        "failed_rules": dict(sorted(failed.items(), key=lambda kv: -kv[1])),
        "stub": sum(1 for r in records if r.is_stub),
        "scored": sum(1 for r in records
                      if all(r.axes.get(a) is not None for a in AXES)),
    }


SUBMISSION_CAP = 20  # the organisers take a ranked list of up to 20


def build_shortlist(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    cap: int = SUBMISSION_CAP,
) -> list[DesignRecord]:
    """The actual submission: up to 20 ranked eligible designs.

    The portfolio stage picks the `budget` designs that take the *guaranteed*
    lab slots, which is a different question from what we submit. Placing on the
    day buys more slots (16/12/8 for 1st/2nd/3rd) and each judge can nominate a
    favourite, so a ranked list that stops at four throws away every slot we
    might win. The four stay at the top, in the portfolio's order, because that
    choice is a joint decision and not a sort; everything below them is ordered
    by joint score.
    """
    picked = {r.design_id for r in selected}
    rest = [
        r for r in records
        if r.design_id not in picked
        and r.gates.passed
        and not r.is_baseline
        and r.joint_score is not None
    ]
    rest.sort(key=lambda r: -(r.joint_score or 0))
    out = list(selected) + rest
    return out[:cap]


def _tier_mix(selected: list[DesignRecord]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for r in selected:
        v = _verdict(r)
        mix[v] = mix.get(v, 0) + 1
    return mix


# ---------------------------------------------------------------- markdown

def render_markdown(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    config: dict[str, Any],
    warnings: list[str],
) -> str:
    f = _funnel(records)
    L: list[str] = []
    A = L.append

    A("# FourWells — design shortlist\n")
    A(f"**Target** {config.get('target', '?')} · **Reference** "
      f"{config.get('reference', '?')} · **Lab slots** {config.get('budget', 4)}\n")
    A(f"Run `{config.get('run_id', '?')}` · seed {config.get('seed', '?')} · "
      f"git `{config.get('git_sha', 'unknown')[:12]}` · "
      f"schema {config.get('schema_version', '?')}\n")

    # --- the honest frame, first, not in an appendix ---
    A("## Read this before the table\n")
    A("Every number below is a **prediction**. The lab measures binding by SPR, epitope "
      "preservation by competitive binding, and thermostability directly; none of those "
      "results exist yet. Each axis is a probability that the design beats trastuzumab on "
      "that axis, so the reference scores exactly **0.500** everywhere by construction — "
      "0.5 means *indistinguishable from trastuzumab*, not *average*.\n")
    A("Two findings from our own validation constrain how much any of this deserves to be "
      "trusted, and both are null results:\n")
    A("- A model fit to the 524,346 FACS-labelled CDRH3 variants scores **AUC 0.879** on "
      "held-out distant FACS variants and **0.508 — chance** — on the SPR-measured designs "
      "we are actually allowed to submit. Plain CDRH3 identity to trastuzumab scores "
      "**0.750** on the same designs. We do not rank on that model. "
      "(`proof/tidy/enrichment.md`)")
    A("- A single structure-confidence cutoff means three different things across AF3, "
      "Boltz-2 and Chai-1: at ipTM 0.70, Boltz-2 admits 94% of shuffled non-binding pairs "
      "and Chai-1 discards 92% of known binders. Confidence is a tie-breaker here, never a "
      "filter. (`proof/tidy/iptm_calibration.md`)")
    A("- Trastuzumab is measured **8 times** in the provided SPR file, spanning **6.2×** in "
      "KD. Any predicted improvement smaller than that is inside the assay's noise.\n")

    if warnings:
        A("### Warnings from this run\n")
        for w in warnings:
            A(f"- ⚠️ {w}")
        A("")

    # --- the funnel ---
    A("## Funnel\n")
    A(f"{f['generated']} candidates → **{f['passed']} cleared every entry gate** → "
      f"{len(build_shortlist(records, selected))} submitted, of which the top "
      f"{len(selected)} take the guaranteed lab slots.\n")
    if f["failed_rules"]:
        A("Rejections by rule — a design that fails a gate is never moved to the other "
          "track, so these never reach the lab:\n")
        A("| Rule | Designs rejected |")
        A("| --- | --- |")
        for rule, n in f["failed_rules"].items():
            A(f"| {rule} | {n} |")
        A("")
    if f["scored"] < f["passed"]:
        A(f"Note: {f['passed'] - f['scored']} gate-passing designs have at least one "
          "unscored axis. An unscored axis is not a zero — it is missing evidence, and "
          "those designs cannot be ranked against fully scored ones.\n")

    # --- the shortlist ---
    budget = int(config.get("budget", 4) or 4)
    shortlist = build_shortlist(records, selected)
    mix = _tier_mix(selected)
    A("## The submission — ranked\n")
    A(f"{len(shortlist)} designs, ranked. The organisers take up to {SUBMISSION_CAP}; the "
      f"top **{len(selected)}** marked `lab` take the slots every team is guaranteed. The "
      "rest are not filler — placing on the day buys 16/12/8 more slots and each judge can "
      "nominate a favourite, so stopping the list at four would throw away every slot we "
      "might win.\n")
    A("`joint` is P(beats trastuzumab on all three) = the product of the three axes, not an "
      "average. `Tier` is the predicted tier: S beats all three, A two, B one. Teams rank "
      "by S count, then A, then B.\n")
    A("| # | Design | Track | Tier | joint | " +
      " | ".join(AXIS_META[a][0] for a in AXES) + " | CDRH3 id | Cluster |")
    A("| --- | --- | --- | --- | --- | " + " | ".join("---" for _ in AXES) + " | --- | --- |")
    for i, r in enumerate(shortlist, 1):
        slot = " **lab**" if r.selected else ""
        A(f"| {i}{slot} | `{r.design_id}` | {r.track or '—'} | {_verdict(r)} | "
          f"{_pct(r.joint_score)} | " +
          " | ".join(_pct(r.axes.get(a)) for a in AXES) +
          f" | {_pct(r.cdrh3_identity_to_tras)} | {r.cluster or '—'} |")
    A("")
    if mix:
        A(f"Predicted tier mix in the {len(selected)} lab slots: " +
          ", ".join(f"**{n}× {t}**" for t, n in sorted(mix.items())) + ".")
        A("That mix is the thing we optimise, not the top affinity. Four variants of one "
          "parent is one bet placed four times, so the slots deliberately carry distinct "
          "hypotheses with uncorrelated failure modes.\n")
    if len(shortlist) < SUBMISSION_CAP:
        A(f"Only {len(shortlist)} eligible designs exist in this run, against a cap of "
          f"{SUBMISSION_CAP}. That is a generation-volume gap, not a ranking decision — we "
          "are leaving submission slots empty.\n")

    # --- per-design dossier ---
    A("## Dossiers — the lab slots\n")
    A("Full dossiers for the designs taking the guaranteed slots. Every other design in "
      "the table above has the same fields in `designs.jsonl`.\n")
    for r in selected:
        A(f"### {r.rank}. `{r.design_id}` — predicted tier {_verdict(r)}\n")
        A(f"- **Track** {r.track or '—'} · **Format** {r.format or '—'} · "
          f"**Parent** {r.parent or '—'} · **Cluster** {r.cluster or '—'}")
        A(f"- **Generator** `{r.generator or 'unknown'}`"
          + ("  ⚠️ **stub, not a real design**" if r.is_stub else ""))
        A(f"- **CDRH3** `{r.cdrh3 or '—'}` · identity to trastuzumab "
          f"{_pct(r.cdrh3_identity_to_tras)} · "
          f"{r.cdrh3_mutations_from_tras if r.cdrh3_mutations_from_tras is not None else '—'}"
          " mutations")
        A(f"- **Gates** {'passed' if r.gates.passed else 'FAILED: ' + ', '.join(r.gates.failed_rules or ['?'])}")
        A(f"- **Sequence** ({len(r.sequence)} aa)")
        A(f"  ```\n  {r.sequence}\n  ```")
        A("")
        A("| Axis | Lab measures it by | P(beats trastuzumab) | Provenance |")
        A("| --- | --- | --- | --- |")
        for a in AXES:
            label, how, prov = AXIS_META[a]
            A(f"| {label} | {how} | {_pct(r.axes.get(a))} | {prov} |")
        A("")
        if r.rationale:
            A("**Why it is on the list**\n")
            for line in r.rationale:
                A(f"- {line}")
            A("")
        if r.kill_criterion:
            A(f"**Kill criterion** — {r.kill_criterion}\n")
            A("If that happens, this design was the wrong bet and we want to know which "
              "one of our four assumptions broke.\n")

    # --- the named failure, which is scoring and not humility ---
    A("## Where our ranking is wrong\n")
    A("Measured on the 114 submittable, SPR-measured designs from the provided "
      "optimisation set — the closest thing to a dress rehearsal that exists. These are "
      "our own ranker's mistakes on data we did not fit:\n")
    for case in KNOWN_FAILURES:
        A(f"- **{case['label']}** — `{case['cdrh3']}`: {case['detail']}")
    A("")
    A("Both failures share one cause, and it is the reason the binding axis does not rest "
      "on a CDRH3 sequence model alone: residue preferences learned from a FACS screen do "
      "not locate the binding interface. A team that cannot name its own failure mode has "
      "not looked for one.\n")

    A("## Reproducing this\n")
    A("```")
    A(config.get("command", "fourwells run"))
    A("```")
    A(f"Offline by default. Same seed and inputs reproduce `selected.jsonl` byte for byte. "
      f"Full record for every candidate, rejections included, is in `designs.jsonl`.\n")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- html

_CSS = """
:root{--ink:#16181d;--mut:#5c6370;--line:#e3e6ea;--bg:#fff;--acc:#1f6feb;
--good:#107c41;--bad:#b42318;--warn:#8a5a00;--chip:#f4f6f8}
@media(prefers-color-scheme:dark){:root{--ink:#e6e9ef;--mut:#9aa3b2;--line:#2b3038;
--bg:#14161a;--acc:#6ea8fe;--good:#4ec97f;--bad:#ff7b72;--warn:#e3b341;--chip:#1d2026}}
*{box-sizing:border-box}
body{margin:0;padding:2.5rem 1.25rem 6rem;background:var(--bg);color:var(--ink);
font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:62rem;margin:0 auto}
h1{font-size:1.9rem;margin:0 0 .25rem;letter-spacing:-.02em}
h2{font-size:1.3rem;margin:2.5rem 0 .75rem;padding-bottom:.35rem;
border-bottom:1px solid var(--line);letter-spacing:-.01em}
h3{font-size:1.05rem;margin:2rem 0 .5rem}
p,li{margin:.4rem 0}
code{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
background:var(--chip);padding:.1em .35em;border-radius:3px}
pre{background:var(--chip);padding:.75rem 1rem;border-radius:6px;overflow-x:auto;
border:1px solid var(--line)}
pre code{background:none;padding:0;word-break:break-all;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;margin:.75rem 0;font-size:14px}
th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--mut);font-size:12px;text-transform:uppercase;
letter-spacing:.04em}
td.n{font-variant-numeric:tabular-nums;text-align:right}
.sub{color:var(--mut);font-size:14px;margin:0 0 1.5rem}
.frame{background:var(--chip);border:1px solid var(--line);border-left:3px solid var(--acc);
padding:1rem 1.25rem;border-radius:0 6px 6px 0;margin:1rem 0}
.warn{border-left-color:var(--warn)}
.warn strong{color:var(--warn)}
.chip{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.04em;
padding:.15em .5em;border-radius:3px;background:var(--chip);border:1px solid var(--line);
color:var(--mut);text-transform:uppercase}
.chip.pred{border-color:var(--warn);color:var(--warn)}
.chip.meas{border-color:var(--good);color:var(--good)}
.tier{font-weight:700}
.tier.S{color:var(--good)}.tier.A{color:var(--acc)}.tier.B{color:var(--mut)}
.slot{font-size:11px;font-weight:700;color:var(--good);letter-spacing:.04em}
.card{border:1px solid var(--line);border-radius:8px;padding:1.25rem 1.5rem;margin:1.25rem 0}
.bar{position:relative;height:6px;background:var(--line);border-radius:3px;margin-top:.3rem}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--acc);border-radius:3px}
.bar u{position:absolute;top:-2px;bottom:-2px;left:50%;width:1px;background:var(--mut)}
.stub{color:var(--bad);font-weight:600}
footer{max-width:62rem;margin:3rem auto 0;padding-top:1rem;border-top:1px solid var(--line);
color:var(--mut);font-size:13px}
"""


def _h(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _axis_bar(v: float | None) -> str:
    """A bar with a tick at 0.5, so 'beats the reference' is visible, not computed."""
    if v is None:
        return '<span class="chip">no evidence</span>'
    pct = max(0.0, min(1.0, float(v))) * 100
    return (f'<div>{v:.2f}</div><div class="bar"><i style="width:{pct:.0f}%"></i>'
            f'<u></u></div>')


def render_html(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    config: dict[str, Any],
    warnings: list[str],
) -> str:
    f = _funnel(records)
    budget = int(config.get("budget", 4) or 4)
    mix = _tier_mix(selected[:budget])
    H: list[str] = []
    A = H.append

    A("<!DOCTYPE html>")
    A('<html lang="en"><head><meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width,initial-scale=1">')
    A(f"<title>FourWells — {_h(config.get('target', 'shortlist'))}</title>")
    A(f"<style>{_CSS}</style></head><body><main>")

    A("<h1>FourWells — design shortlist</h1>")
    A(f'<p class="sub">Target <strong>{_h(config.get("target", "?"))}</strong> · '
      f'reference <strong>{_h(config.get("reference", "?"))}</strong> · '
      f'{budget} guaranteed lab slots<br>'
      f'run <code>{_h(config.get("run_id", "?"))}</code> · seed '
      f'{_h(config.get("seed", "?"))} · git <code>'
      f'{_h(str(config.get("git_sha", "unknown"))[:12])}</code></p>')

    # --- the frame ---
    A('<div class="frame">')
    A("<p><strong>Every number on this page is a prediction.</strong> The lab measures "
      "binding by SPR, epitope preservation by competitive binding, and thermostability "
      "directly — none of those results exist yet. Each axis is the probability that the "
      "design beats trastuzumab on that axis, so the reference scores exactly "
      "<strong>0.500</strong> everywhere by construction. The tick on each bar is that "
      "0.500 line: right of it means we predict it beats trastuzumab.</p>")
    A("<p>Two of our own validation results are null, and they constrain this page:</p>")
    A("<ul>")
    A("<li>A model fit to the 524,346 FACS-labelled CDRH3 variants scores AUC "
      "<strong>0.879</strong> on held-out distant FACS variants and <strong>0.508 — "
      "chance</strong> — on the SPR-measured designs we are allowed to submit. Plain CDRH3 "
      "identity scores <strong>0.750</strong> on the same designs. We do not rank on that "
      "model.</li>")
    A("<li>One ipTM cutoff means three different things across AF3, Boltz-2 and Chai-1: at "
      "0.70, Boltz-2 admits 94% of shuffled non-binding pairs and Chai-1 discards 92% of "
      "known binders. Structure confidence is a tie-breaker here, never a filter.</li>")
    A("<li>Trastuzumab is measured 8 times in the provided SPR file, spanning "
      "<strong>6.2×</strong> in K<sub>D</sub>. A predicted improvement smaller than that "
      "is inside the assay's noise.</li>")
    A("</ul></div>")

    if warnings:
        A('<div class="frame warn"><p><strong>Warnings from this run</strong></p><ul>')
        for w in warnings:
            A(f"<li>{_h(w)}</li>")
        A("</ul></div>")

    # --- funnel ---
    A("<h2>Funnel</h2>")
    A(f"<p>{f['generated']} candidates → <strong>{f['passed']} cleared every entry "
      f"gate</strong> → {len(build_shortlist(records, selected))} submitted, of which the "
      f"top {len(selected)} take the guaranteed lab slots.</p>")
    if f["failed_rules"]:
        A("<p>Rejections by rule. A design that fails a gate is never moved to the other "
          "track, so these never reach the lab:</p>")
        A("<table><thead><tr><th>Rule</th><th>Designs rejected</th></tr></thead><tbody>")
        for rule, n in f["failed_rules"].items():
            A(f'<tr><td>{_h(rule)}</td><td class="n">{n}</td></tr>')
        A("</tbody></table>")

    # --- shortlist ---
    shortlist = build_shortlist(records, selected)
    A("<h2>The submission — ranked</h2>")
    A(f"<p>{len(shortlist)} designs, ranked. The organisers take up to {SUBMISSION_CAP}; "
      f"the top <strong>{len(selected)}</strong> marked <span class=\"slot\">LAB</span> "
      "take the slots every team is guaranteed. The rest are not filler — placing on the "
      "day buys 16/12/8 more slots and each judge can nominate a favourite, so stopping at "
      "four would throw away every slot we might win.</p>")
    A("<p><code>joint</code> is P(beats trastuzumab on all three axes) — the product, not "
      "an average. <code>Tier</code> is the predicted tier: <strong>S</strong> beats all "
      "three, <strong>A</strong> two, <strong>B</strong> one. Teams rank by S count, then "
      "A, then B.</p>")
    A("<table><thead><tr><th>#</th><th>Design</th><th>Track</th><th>Tier</th>"
      "<th>joint</th>" + "".join(f"<th>{AXIS_META[a][0]}</th>" for a in AXES) +
      "<th>CDRH3 id</th><th>Cluster</th></tr></thead><tbody>")
    for i, r in enumerate(shortlist, 1):
        slot = ' <span class="slot">LAB</span>' if r.selected else ""
        v = _verdict(r)
        A(f'<tr><td class="n">{i}{slot}</td><td><code>{_h(r.design_id)}</code>'
          + ('<br><span class="stub">stub</span>' if r.is_stub else "") + "</td>"
          f"<td>{_h(r.track or '—')}</td>"
          f'<td class="tier {v}">{v}</td>'
          f'<td class="n">{_pct(r.joint_score)}</td>' +
          "".join(f'<td class="n">{_pct(r.axes.get(a))}</td>' for a in AXES) +
          f'<td class="n">{_pct(r.cdrh3_identity_to_tras)}</td>'
          f"<td>{_h(r.cluster or '—')}</td></tr>")
    A("</tbody></table>")
    if mix:
        A(f"<p>Predicted tier mix in the {len(selected)} lab slots: " +
          ", ".join(f"<strong>{n}× {_h(t)}</strong>" for t, n in sorted(mix.items())) +
          ". That mix is what we optimise, not top affinity — four variants of one parent "
          "is one bet placed four times, so the slots carry distinct hypotheses with "
          "uncorrelated failure modes.</p>")
    if len(shortlist) < SUBMISSION_CAP:
        A(f'<div class="frame warn"><p>Only {len(shortlist)} eligible designs exist in '
          f"this run, against a cap of {SUBMISSION_CAP}. That is a generation-volume gap, "
          "not a ranking decision — we are leaving submission slots empty.</p></div>")

    # --- dossiers ---
    A("<h2>Dossiers — the lab slots</h2>")
    A("<p>Full dossiers for the designs taking the guaranteed slots. Every other design in "
      "the table above has the same fields in <code>designs.jsonl</code>.</p>")
    for r in selected:
        v = _verdict(r)
        A('<div class="card">')
        A(f'<h3>{r.rank}. <code>{_h(r.design_id)}</code> — predicted tier '
          f'<span class="tier {v}">{v}</span></h3>')
        A(f"<p class=\"sub\">{_h(r.track or '—')} · {_h(r.format or '—')} · parent "
          f"{_h(r.parent or '—')} · cluster {_h(r.cluster or '—')} · generator "
          f"<code>{_h(r.generator or 'unknown')}</code>"
          + (' · <span class="stub">STUB, not a real design</span>' if r.is_stub else "")
          + "</p>")
        A("<table><thead><tr><th>Axis</th><th>Lab measures it by</th>"
          "<th>P(beats trastuzumab)</th><th>Provenance</th></tr></thead><tbody>")
        for a in AXES:
            label, how, prov = AXIS_META[a]
            cls = "meas" if prov == "measured" else "pred"
            A(f"<tr><td>{_h(label)}</td><td>{_h(how)}</td><td>{_axis_bar(r.axes.get(a))}"
              f'</td><td><span class="chip {cls}">{_h(prov)}</span></td></tr>')
        A("</tbody></table>")
        A("<table><tbody>")
        A(f"<tr><th>CDRH3</th><td><code>{_h(r.cdrh3 or '—')}</code> — identity to "
          f"trastuzumab {_pct(r.cdrh3_identity_to_tras)}, "
          f"{_h(r.cdrh3_mutations_from_tras if r.cdrh3_mutations_from_tras is not None else '—')}"
          " mutations</td></tr>")
        gates = ("passed" if r.gates.passed
                 else "FAILED: " + ", ".join(r.gates.failed_rules or ["?"]))
        A(f"<tr><th>Gates</th><td>{_h(gates)}</td></tr>")
        A("</tbody></table>")
        A(f"<p><strong>Sequence</strong> ({len(r.sequence)} aa)</p>")
        A(f"<pre><code>{_h(r.sequence)}</code></pre>")
        if r.rationale:
            A("<p><strong>Why it is on the list</strong></p><ul>")
            for line in r.rationale:
                A(f"<li>{_h(line)}</li>")
            A("</ul>")
        if r.kill_criterion:
            A(f'<div class="frame warn"><p><strong>Kill criterion</strong> — '
              f"{_h(r.kill_criterion)}</p><p>If that happens this design was the wrong "
              "bet, and we want to know which of our four assumptions broke.</p></div>")
        A("</div>")

    A("<h2>Where our ranking is wrong</h2>")
    A("<p>Measured on the 114 submittable, SPR-measured designs from the provided "
      "optimisation set — the closest thing to a dress rehearsal that exists. These are "
      "our own ranker's mistakes on data we did not fit:</p><ul>")
    for case in KNOWN_FAILURES:
        A(f"<li><strong>{_h(case['label'])}</strong> — <code>{_h(case['cdrh3'])}</code>: "
          + re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _h(case["detail"]))
          + "</li>")
    A("</ul>")
    A("<p>Both failures share one cause, and it is why the binding axis does not rest on a "
      "CDRH3 sequence model alone: residue preferences learned from a FACS screen do not "
      "locate the binding interface. A team that cannot name its own failure mode has not "
      "looked for one.</p>")

    A("<h2>Reproducing this</h2>")
    A(f"<pre><code>{_h(config.get('command', 'fourwells run'))}</code></pre>")
    A("<p>Offline by default. The same seed and inputs reproduce <code>selected.jsonl</code> "
      "byte for byte. Every candidate, rejections included, is in "
      "<code>designs.jsonl</code>.</p>")

    A("</main><footer>")
    A(f"FourWells · schema {_h(config.get('schema_version', '?'))} · "
      f"{f['generated']} candidates, {f['passed']} eligible, {len(selected)} shortlisted. "
      "Predictions, not measurements.")
    A("</footer></body></html>")
    return "\n".join(H) + "\n"


# ---------------------------------------------------------------- re-render

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="fourwells.report",
        description="Re-render report.md and report.html from a run directory",
    )
    ap.add_argument("rundir", type=Path, help="a directory holding designs.jsonl")
    a = ap.parse_args(argv)

    designs = a.rundir / "designs.jsonl"
    if not designs.exists():
        print(f"no designs.jsonl in {a.rundir}")
        return 1
    records = read_jsonl(designs)
    sel_path = a.rundir / "selected.jsonl"
    selected = (read_jsonl(sel_path) if sel_path.exists()
                else sorted([r for r in records if r.selected], key=lambda r: r.rank or 999))
    cfg_path = a.rundir / "config.json"
    config = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}

    (a.rundir / "report.md").write_text(
        render_markdown(records, selected, config, config.get("warnings", []))
    )
    (a.rundir / "report.html").write_text(
        render_html(records, selected, config, config.get("warnings", []))
    )
    print(f"wrote {a.rundir / 'report.md'}")
    print(f"wrote {a.rundir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
