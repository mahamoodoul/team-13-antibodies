"""The report — OWNER: Mahamoodoul. The artefact the judges are guaranteed to see.

Renders one run into Markdown and a single self-contained HTML file. No build
step, no CDN, no framework, no web font: it opens from a file:// URL on a
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
    "binding": ("Binding proxy", "SPR", "heuristic prediction"),
    "epitope": ("Epitope proxy", "competitive binding vs trastuzumab", "heuristic prediction"),
    "stability": ("Developability proxy", "thermostability requires a separate measurement", "heuristic prediction"),
}

LEGACY_WARNING = (
    "Legacy heuristic preview — not a submission. These normalized scores are not "
    "calibrated probabilities. The legacy stability score is a developability proxy, "
    "not a thermostability prediction. Experimental tiers and laboratory improvement "
    "are unknown. Use the Experiments workflow for official validation, separate "
    "scientific evidence and guarded exports."
)


def _legacy_text(text: str) -> str:
    """Correct the presentation of historical dossiers; preserve raw records."""
    return (text.replace("Joint P(S-tier)", "Legacy score product")
            .replace("Predicted P(competes)", "Legacy epitope proxy")
            .replace("predicted P ", "legacy proxy ")
            .replace("(P ", "(legacy proxy "))

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

    A("# FourWells — legacy shortlist preview\n")
    A(f"**{LEGACY_WARNING}**\n")
    A(f"**Target** {config.get('target', '?')} · **Reference** "
      f"{config.get('reference', '?')} · **Lab slots** {config.get('budget', 4)}\n")
    A(f"Run `{config.get('run_id', '?')}` · seed {config.get('seed', '?')} · "
      f"git `{config.get('git_sha', 'unknown')[:12]}` · "
      f"schema {config.get('schema_version', '?')}\n")

    # --- the honest frame, first, not in an appendix ---
    A("## Read this before the table\n")
    A("The values below are historical heuristic predictions. The lab measures binding "
      "by SPR, epitope preservation by competitive binding, and thermostability directly. "
      "The reference scores **0.500** by mathematical construction; this does not establish "
      "experimental equivalence, calibrated uncertainty or a probability of improvement.\n")
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
      "KD. This replicate spread motivates caution; it is not a calibrated uncertainty "
      "interval for a new candidate.\n")

    if warnings:
        A("### Warnings from this run\n")
        for w in warnings:
            A(f"- ⚠️ {w}")
        A("")

    # --- the funnel ---
    A("## Funnel\n")
    A(f"{f['generated']} records → **{f['passed']} passed the legacy screen** → "
      f"{len(build_shortlist(records, selected))} preview entries, including "
      f"{len(selected)} preview picks. An official abguard pass is a separate requirement.\n")
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
    A("## The submission — ranked (legacy preview only)\n")
    A(f"{len(shortlist)} preview entries, capped at {SUBMISSION_CAP}; "
      f"the top **{len(selected)}** marked `lab` are historical preview picks. "
      "Their inclusion does not establish official eligibility.\n")
    A("`joint` is the product of three heuristic proxies, not a success probability. "
      "`Tier` is a legacy proxy label from thresholds at 0.5, not an experimental or "
      "validated predicted tier.\n")
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
        A(f"Legacy proxy labels for the {len(selected)} preview picks: " +
          ", ".join(f"**{n}× {t}**" for t, n in sorted(mix.items())) + ".")
        A("Sequence clusters describe diversity; they do not establish independent "
          "failure modes or experimental performance.\n")
    if len(shortlist) < SUBMISSION_CAP:
        A(f"This legacy preview contains {len(shortlist)} records against a cap of "
          f"{SUBMISSION_CAP}. Eligibility must be checked in the scientific workflow.\n")

    # --- per-design dossier ---
    A("## Dossiers — preview picks\n")
    A("Historical dossiers for the preview picks. Every other record in "
      "the table above has the same fields in `designs.jsonl`.\n")
    for r in selected:
        A(f"### {r.rank}. `{r.design_id}` — legacy proxy label {_verdict(r)}\n")
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
        A("| Proxy | Lab validation required | Heuristic score | Provenance |")
        A("| --- | --- | --- | --- |")
        for a in AXES:
            label, how, prov = AXIS_META[a]
            A(f"| {label} | {how} | {_pct(r.axes.get(a))} | {prov} |")
        A("")
        if r.rationale:
            A("**Why it is on the list**\n")
            for line in r.rationale:
                A(f"- {_legacy_text(line)}")
            A("")
        if r.kill_criterion:
            A(f"**Kill criterion** — {_legacy_text(r.kill_criterion)}\n")
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
# One file, no build step, no server, no CDN, no framework. Vanilla JS against
# a JSON blob embedded in the page, which is why it still opens from a file://
# URL on a laptop with no network — the property that made us cut React, not a
# dislike of interactivity. The interactive parts are the ones a judge actually
# uses: sort by any axis, filter to a track or tier, and compare designs
# side by side, because "why these four and not those four" is the question.

_CSS = """
:root{--ink:#16181d;--mut:#5c6370;--line:#e3e6ea;--bg:#fff;--card:#fff;--acc:#1f6feb;
--good:#107c41;--bad:#b42318;--warn:#8a5a00;--chip:#f4f6f8;--hi:#eaf2ff}
@media(prefers-color-scheme:dark){:root{--ink:#e6e9ef;--mut:#9aa3b2;--line:#2b3038;
--bg:#14161a;--card:#191c21;--acc:#6ea8fe;--good:#4ec97f;--bad:#ff7b72;--warn:#e3b341;
--chip:#1d2026;--hi:#1b2433}}
*{box-sizing:border-box}
body{margin:0;padding:2.5rem 1.25rem 6rem;background:var(--bg);color:var(--ink);
font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
main{max-width:72rem;margin:0 auto}
h1{font-size:1.9rem;margin:0 0 .25rem;letter-spacing:-.02em}
h2{font-size:1.3rem;margin:2.5rem 0 .75rem;padding-bottom:.35rem;
border-bottom:1px solid var(--line);letter-spacing:-.01em}
h3{font-size:1.05rem;margin:0 0 .5rem}
p,li{margin:.4rem 0}
a{color:var(--acc)}
code{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
background:var(--chip);padding:.1em .35em;border-radius:3px}
pre{background:var(--chip);padding:.75rem 1rem;border-radius:6px;overflow-x:auto;
border:1px solid var(--line)}
pre code{background:none;padding:0;word-break:break-all;white-space:pre-wrap}
table{border-collapse:collapse;width:100%;margin:.75rem 0;font-size:14px}
th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--mut);font-size:12px;text-transform:uppercase;
letter-spacing:.04em}
td.n,th.n{font-variant-numeric:tabular-nums;text-align:right}
.sub{color:var(--mut);font-size:14px;margin:0 0 1.5rem}
.frame{background:var(--chip);border:1px solid var(--line);border-left:3px solid var(--acc);
padding:1rem 1.25rem;border-radius:0 6px 6px 0;margin:1rem 0}
.frame.warn{border-left-color:var(--warn)}
.chip{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.04em;
padding:.15em .5em;border-radius:3px;background:var(--chip);border:1px solid var(--line);
color:var(--mut);text-transform:uppercase}
.chip.pred{border-color:var(--warn);color:var(--warn)}
.chip.meas{border-color:var(--good);color:var(--good)}
.tier{font-weight:700}
.tier.S{color:var(--good)}.tier.A{color:var(--acc)}.tier.B{color:var(--mut)}
.slot{font-size:10px;font-weight:700;color:var(--good);letter-spacing:.06em;
border:1px solid var(--good);border-radius:3px;padding:0 .3em;margin-left:.3em}
.stub{color:var(--bad);font-weight:600;font-size:11px}
.stats{display:flex;flex-wrap:wrap;gap:.75rem;margin:1.25rem 0}
.stat{flex:1 1 8rem;border:1px solid var(--line);border-radius:8px;padding:.7rem .9rem;
background:var(--card)}
.stat b{display:block;font-size:1.5rem;line-height:1.2;font-variant-numeric:tabular-nums}
.stat span{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
.bar{position:relative;height:6px;background:var(--line);border-radius:3px;margin-top:.3rem;
min-width:4rem}
.bar i{position:absolute;top:0;bottom:0;left:0;background:var(--acc);border-radius:3px}
.bar u{position:absolute;top:-2px;bottom:-2px;left:50%;width:1px;background:var(--mut)}
.bar.win i{background:var(--good)}
.controls{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.75rem 0}
.controls input,.controls select{font:inherit;font-size:13px;padding:.35rem .5rem;
border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
.controls input[type=search]{flex:1 1 12rem}
.btn{font:inherit;font-size:13px;padding:.35rem .7rem;border:1px solid var(--line);
border-radius:6px;background:var(--card);color:var(--ink);cursor:pointer}
.btn:hover{background:var(--hi)}
.btn[aria-pressed=true]{border-color:var(--acc);color:var(--acc)}
#tbl tbody tr{cursor:pointer}
#tbl tbody tr:hover{background:var(--hi)}
#tbl tbody tr.open{background:var(--hi)}
#tbl th[data-k]{cursor:pointer;user-select:none;white-space:nowrap}
#tbl th[data-k]:hover{color:var(--ink)}
#tbl th .ar{opacity:.4;font-size:10px}
.card{border:1px solid var(--line);border-radius:8px;padding:1.25rem 1.5rem;margin:1rem 0;
background:var(--card)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:1rem}
.kv{font-size:13px;color:var(--mut)}
.kv b{color:var(--ink);font-weight:600}
.none{color:var(--mut);font-style:italic;padding:1rem 0}
.cmpbar{position:sticky;bottom:0;background:var(--card);border-top:1px solid var(--line);
padding:.6rem 1rem;margin:0 -1.25rem -6rem;display:none;gap:.5rem;align-items:center;
font-size:13px;flex-wrap:wrap}
.cmpbar.on{display:flex}
footer{max-width:72rem;margin:3rem auto 0;padding-top:1rem;border-top:1px solid var(--line);
color:var(--mut);font-size:13px}
@media print{.controls,.cmpbar,.btn{display:none}#detail,#cmp{break-inside:avoid}}
"""

# Vanilla JS. Reads the embedded JSON, renders the table, and keeps the three
# interactions a judge uses. No dependency, no fetch, no storage.
_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('data').textContent);
var AX=D.axes, rows=D.designs, cap=D.cap, sortK='rank', sortA=true, sel=new Set();

function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML}
function num(v){return v==null?'—':(+v).toFixed(2)}
function bar(v){
  if(v==null) return '<span class="chip">no evidence</span>';
  var p=Math.max(0,Math.min(1,+v))*100, w=(+v>0.5)?' win':'';
  return '<div class="n">'+(+v).toFixed(2)+'</div><div class="bar'+w+'">'+
         '<i style="width:'+p.toFixed(0)+'%"></i><u></u></div>';
}
function visible(){
  var q=document.getElementById('q').value.trim().toLowerCase();
  var tr=document.getElementById('ftrack').value, ti=document.getElementById('ftier').value;
  var labOnly=document.getElementById('flab').getAttribute('aria-pressed')==='true';
  return rows.filter(function(r){
    if(labOnly&&!r.lab) return false;
    if(tr&&r.track!==tr) return false;
    if(ti&&r.tier!==ti) return false;
    if(q){
      var hay=(r.id+' '+(r.cdrh3||'')+' '+(r.cluster||'')+' '+(r.track||'')).toLowerCase();
      if(hay.indexOf(q)<0) return false;
    }
    return true;
  });
}
function val(r,k){
  // Axis columns are keyed "ax.binding" and live one level down, so a plain
  // r[k] silently resolves to undefined and the sort becomes a no-op.
  if(k.indexOf('.')<0) return r[k];
  var parts=k.split('.'), v=r;
  for(var i=0;i<parts.length&&v!=null;i++) v=v[parts[i]];
  return v;
}
function sorted(list){
  var s=list.slice();
  s.sort(function(a,b){
    var x=val(a,sortK), y=val(b,sortK);
    if(x==null&&y==null) return 0;
    if(x==null) return 1; if(y==null) return -1;
    if(typeof x==='string') return sortA? x.localeCompare(y): y.localeCompare(x);
    return sortA? x-y : y-x;
  });
  return s;
}
function draw(){
  var list=sorted(visible()), tb=document.getElementById('tb'), h='';
  list.forEach(function(r){
    h+='<tr data-id="'+esc(r.id)+'"'+(sel.has(r.id)?' class="open"':'')+'>'
      +'<td class="n">'+r.rank+(r.lab?'<span class="slot">LAB</span>':'')+'</td>'
      +'<td><code>'+esc(r.id)+'</code>'+(r.stub?'<br><span class="stub">stub</span>':'')+'</td>'
      +'<td>'+esc(r.track||'—')+'</td>'
      +'<td class="tier '+esc(r.tier)+'">'+esc(r.tier)+'</td>'
      +'<td class="n">'+num(r.joint)+'</td>';
    AX.forEach(function(a){ h+='<td class="n">'+num(r.ax[a])+'</td>'; });
    h+='<td class="n">'+num(r.identity)+'</td><td>'+esc(r.cluster||'—')+'</td></tr>';
  });
  tb.innerHTML=h || '<tr><td colspan="'+(6+AX.length)+'" class="none">'
    +'No design matches these filters.</td></tr>';
  document.getElementById('count').textContent=list.length+' of '+rows.length+' shown';
  document.querySelectorAll('#tbl th[data-k]').forEach(function(th){
    var a=th.querySelector('.ar');
    if(a) a.textContent = th.dataset.k===sortK ? (sortA?'▲':'▼') : '';
  });
}
function detail(r,scroll){
  var h='<div class="card"><h3>'+esc(r.id)+' <span class="tier '+esc(r.tier)+'">'
    +esc(r.tier)+'</span>'+(r.lab?'<span class="slot">LAB</span>':'')+'</h3>'
    +'<p class="kv">'+esc(r.track||'—')+' · '+esc(r.format||'—')
    +' · parent <b>'+esc(r.parent||'—')+'</b> · cluster <b>'
    +esc(r.cluster||'—')+'</b> · generator <code>'+esc(r.generator||'unknown')
    +'</code>'+(r.stub?' · <span class="stub">STUB, not a real design</span>':'')+'</p>';
  h+='<div class="grid">';
  AX.forEach(function(a){
    h+='<div><div class="kv"><b>'+esc(D.axisLabel[a])+'</b> — lab measures by '
      +esc(D.axisHow[a])+'</div>'+bar(r.ax[a])
      +'<div style="margin-top:.35rem"><span class="chip pred">predicted proxy, unvalidated</span></div></div>';
  });
  h+='</div>';
  h+='<p class="kv" style="margin-top:1rem">CDRH3 <code>'+esc(r.cdrh3||'—')
    +'</code> · identity to trastuzumab <b>'+num(r.identity)+'</b> · <b>'
    +(r.muts==null?'—':r.muts)+'</b> mutations · gates <b>'
    +esc(r.gates)+'</b> · '+r.len+' aa</p>';
  h+='<pre><code>'+esc(r.seq)+'</code></pre>';
  if(r.why&&r.why.length){
    h+='<p><strong>Why it is on the list</strong></p><ul>';
    r.why.forEach(function(w){h+='<li>'+esc(w)+'</li>';}); h+='</ul>';
  }
  if(r.kill) h+='<div class="frame warn"><p><strong>Kill criterion</strong> — '
    +esc(r.kill)+'</p></div>';
  h+='</div>';
  document.getElementById('detail').innerHTML=h;
  // Only scroll when the user asked for this dossier. On first paint we fill the
  // panel but leave the page at the top, where the honest framing lives.
  if(scroll) document.getElementById('detail').scrollIntoView({block:'nearest'});
}
function compare(){
  var picks=rows.filter(function(r){return sel.has(r.id)});
  var bar2=document.getElementById('cmpbar');
  bar2.className = picks.length? 'cmpbar on':'cmpbar';
  document.getElementById('cmpn').textContent=picks.length+' selected';
  if(picks.length<2){document.getElementById('cmp').innerHTML='';return}
  var h='<h2>Side by side</h2><table><thead><tr><th>Axis</th>';
  picks.forEach(function(r){h+='<th class="n">'+esc(r.id)+(r.lab?' LAB':'')+'</th>'});
  h+='</tr></thead><tbody>';
  AX.forEach(function(a){
    var vals=picks.map(function(r){return r.ax[a]}).filter(function(v){return v!=null});
    var best=vals.length?Math.max.apply(null,vals):null;
    h+='<tr><th>'+esc(D.axisLabel[a])+'</th>';
    picks.forEach(function(r){
      var v=r.ax[a], win=(v!=null&&best!=null&&v>=best);
      h+='<td class="n">'+(win?'<strong>'+num(v)+'</strong>':num(v))+'</td>';
    });
    h+='</tr>';
  });
  h+='<tr><th>Legacy score product</th>';
  picks.forEach(function(r){h+='<td class="n">'+num(r.joint)+'</td>'});
  h+='</tr><tr><th>Legacy proxy label</th>';
  picks.forEach(function(r){h+='<td class="n tier '+esc(r.tier)+'">'+esc(r.tier)+'</td>'});
  h+='</tr><tr><th>Cluster</th>';
  picks.forEach(function(r){h+='<td class="n">'+esc(r.cluster||'—')+'</td>'});
  h+='</tr><tr><th>CDRH3 identity</th>';
  picks.forEach(function(r){h+='<td class="n">'+num(r.identity)+'</td>'});
  h+='</tr></tbody></table>';
  var cl={}; picks.forEach(function(r){cl[r.cluster]=1});
  var n=Object.keys(cl).length;
  h+='<p class="kv">'+n+' distinct cluster'+(n===1?'':'s')+' among '+picks.length
    +' designs. '+(n<picks.length
      ? 'Some records share a sequence hypothesis; correlated failures remain possible.'
      : 'Different sequence hypotheses can still share failure modes.')+'</p>';
  document.getElementById('cmp').innerHTML=h;
}
document.getElementById('tb').addEventListener('click',function(e){
  var tr=e.target.closest('tr[data-id]'); if(!tr) return;
  var r=rows.find(function(x){return x.id===tr.dataset.id}); if(!r) return;
  if(e.shiftKey||e.metaKey||e.ctrlKey){
    if(sel.has(r.id)) sel.delete(r.id); else sel.add(r.id);
    draw(); compare();
  } else { detail(r,true); }
});
document.querySelectorAll('#tbl th[data-k]').forEach(function(th){
  th.addEventListener('click',function(){
    if(sortK===th.dataset.k) sortA=!sortA; else {sortK=th.dataset.k; sortA=(sortK==='rank'||sortK==='id');}
    draw();
  });
});
['q','ftrack','ftier'].forEach(function(id){
  document.getElementById(id).addEventListener('input',draw);
});
document.getElementById('flab').addEventListener('click',function(){
  var on=this.getAttribute('aria-pressed')==='true';
  this.setAttribute('aria-pressed',on?'false':'true'); draw();
});
document.getElementById('cmpclear').addEventListener('click',function(){
  sel.clear(); draw(); compare();
});
document.getElementById('cmplab').addEventListener('click',function(){
  sel.clear(); rows.forEach(function(r){if(r.lab) sel.add(r.id)}); draw(); compare();
});
draw();
if(rows.length) detail(rows[0],false);
})();
"""


def _h(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _axis_bar(v: float | None) -> str:
    """A bar with a tick at 0.5, so 'beats the reference' is visible, not computed."""
    if v is None:
        return '<span class="chip">no evidence</span>'
    pct = max(0.0, min(1.0, float(v))) * 100
    win = " win" if float(v) > BASELINE else ""
    return (f'<div class="n">{v:.2f}</div><div class="bar{win}">'
            f'<i style="width:{pct:.0f}%"></i><u></u></div>')


def _payload(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    shortlist: list[DesignRecord],
) -> str:
    """The data the page runs on, embedded rather than fetched.

    `</script` is escaped by encoding every '<' — a generator name or a
    rationale line is data, and data must not be able to close the script tag.
    """
    picked = {r.design_id for r in selected}
    designs = []
    for i, r in enumerate(shortlist, 1):
        designs.append({
            "rank": i,
            "id": r.design_id,
            "lab": r.design_id in picked,
            "track": r.track,
            "format": r.format,
            "parent": r.parent,
            "generator": r.generator,
            "cluster": r.cluster,
            "tier": _verdict(r),
            "joint": r.joint_score,
            "ax": {a: r.axes.get(a) for a in AXES},
            "identity": r.cdrh3_identity_to_tras,
            "cdrh3": r.cdrh3,
            "muts": r.cdrh3_mutations_from_tras,
            "gates": "legacy screen passed (official validation separate)" if r.gates.passed else
                     "FAILED: " + ", ".join(r.gates.failed_rules or ["?"]),
            "seq": r.sequence,
            "len": len(r.sequence),
            "why": [_legacy_text(line) for line in r.rationale],
            "kill": _legacy_text(r.kill_criterion) if r.kill_criterion else None,
            "stub": bool(r.is_stub),
        })
    blob = {
        "axes": list(AXES),
        "axisLabel": {a: AXIS_META[a][0] for a in AXES},
        "axisHow": {a: AXIS_META[a][1] for a in AXES},
        "cap": SUBMISSION_CAP,
        "designs": designs,
    }
    return json.dumps(blob, separators=(",", ":")).replace("<", "\\u003c")


def render_html(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    config: dict[str, Any],
    warnings: list[str],
) -> str:
    f = _funnel(records)
    shortlist = build_shortlist(records, selected)
    mix = _tier_mix(selected)
    tracks = sorted({r.track for r in shortlist if r.track})
    tiers = sorted({_verdict(r) for r in shortlist})
    H: list[str] = []
    A = H.append

    A("<!DOCTYPE html>")
    A('<html lang="en"><head><meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width,initial-scale=1">')
    A(f"<title>FourWells — {_h(config.get('target', 'shortlist'))}</title>")
    A(f"<style>{_CSS}</style></head><body><main>")

    A("<h1>FourWells — legacy shortlist preview</h1>")
    A(f'<div class="frame warn"><p><strong>{_h(LEGACY_WARNING)}</strong></p></div>')
    A(f'<p class="sub">Target <strong>{_h(config.get("target", "?"))}</strong> · '
      f'reference <strong>{_h(config.get("reference", "?"))}</strong><br>'
      f'run <code>{_h(config.get("run_id", "?"))}</code> · seed '
      f'{_h(config.get("seed", "?"))} · git <code>'
      f'{_h(str(config.get("git_sha", "unknown"))[:12])}</code> · schema '
      f'{_h(config.get("schema_version", "?"))}</p>')

    # --- the numbers, at a glance ---
    A('<div class="stats">')
    for val, label in (
        (f["generated"], "candidates"),
        (f["passed"], "passed legacy screen"),
        (len(shortlist), f"preview entries (cap {SUBMISSION_CAP})"),
        (len(selected), "preview picks"),
        ("".join(f"{n}×{t} " for t, n in sorted(mix.items())).strip() or "—",
         "legacy proxy labels"),
    ):
        A(f'<div class="stat"><b>{_h(val)}</b><span>{_h(label)}</span></div>')
    A("</div>")

    # --- the honest frame ---
    A('<div class="frame">')
    A("<p><strong>These are historical heuristic predictions.</strong> Experimental binding "
      "requires SPR, epitope preservation requires competitive binding, and thermostability "
      "requires a separate predictor or measurement. The reference scores "
      "<strong>0.500</strong> by mathematical construction. The bar tick marks that "
      "heuristic reference value, not calibrated probability or experimental equivalence.</p>")
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
      "<strong>6.2×</strong> in K<sub>D</sub>. This observed spread motivates caution; "
      "it is not a calibrated uncertainty interval for a new candidate.</li>")
    A("</ul></div>")

    if warnings:
        A('<div class="frame warn"><p><strong>Warnings from this run</strong></p><ul>')
        for w in warnings:
            A(f"<li>{_h(w)}</li>")
        A("</ul></div>")

    # --- funnel ---
    A("<h2>Funnel</h2>")
    A(f"<p>{f['generated']} records → <strong>{f['passed']} passed the legacy screen"
      f"</strong> → {len(shortlist)} preview entries, including {len(selected)} preview "
      "picks. Official abguard eligibility and experimental performance remain separate.</p>")
    if f["failed_rules"]:
        A("<p>Rejections by rule. A design that fails a gate is never moved to the other "
          "track, so these never reach the lab:</p>")
        A("<table><thead><tr><th>Rule</th><th class=\"n\">Designs rejected</th></tr>"
          "</thead><tbody>")
        for rule, n in f["failed_rules"].items():
            A(f'<tr><td>{_h(rule)}</td><td class="n">{n}</td></tr>')
        A("</tbody></table>")
    if len(shortlist) < SUBMISSION_CAP:
        A(f'<div class="frame warn"><p>This preview contains {len(shortlist)} records '
          f"against a cap of {SUBMISSION_CAP}. Use the scientific workflow for official "
          "validation and guarded submission exports.</p></div>")

    # --- the interactive table ---
    A("<h2>The submission — ranked (legacy preview only)</h2>")
    A("<p><code>joint</code> multiplies three heuristic proxies; it is not a success "
      "probability. <code>Tier</code> is a legacy threshold label, not a validated "
      "experimental or predicted tier. No design is submitted by this page.</p>")
    A('<p class="kv">Click any row for its dossier. Shift-click (or ⌘/Ctrl-click) two or '
      "more rows to compare them side by side. Click a column heading to sort.</p>")
    A('<div class="controls">')
    A('<input type="search" id="q" placeholder="Search id, CDRH3, cluster, track…" '
      'aria-label="Search designs">')
    A('<select id="ftrack" aria-label="Filter by track"><option value="">All tracks</option>'
      + "".join(f'<option value="{_h(t)}">{_h(t)}</option>' for t in tracks) + "</select>")
    A('<select id="ftier" aria-label="Filter by predicted tier">'
      '<option value="">All tiers</option>'
      + "".join(f'<option value="{_h(t)}">tier {_h(t)}</option>' for t in tiers)
      + "</select>")
    A('<button class="btn" id="flab" aria-pressed="false">Lab slots only</button>')
    A('<span class="kv" id="count"></span>')
    A("</div>")

    A('<table id="tbl"><thead><tr>')
    A('<th class="n" data-k="rank">#<span class="ar"></span></th>')
    A('<th data-k="id">Design<span class="ar"></span></th>')
    A('<th data-k="track">Track<span class="ar"></span></th>')
    A('<th data-k="tier">Tier<span class="ar"></span></th>')
    A('<th class="n" data-k="joint">joint<span class="ar"></span></th>')
    for a in AXES:
        A(f'<th class="n" data-k="ax.{a}">{_h(AXIS_META[a][0])}<span class="ar"></span></th>')
    A('<th class="n" data-k="identity">CDRH3 id<span class="ar"></span></th>')
    A('<th data-k="cluster">Cluster<span class="ar"></span></th>')
    A("</tr></thead><tbody id=\"tb\"></tbody></table>")

    A('<div id="cmp"></div>')
    A("<h2>Dossier</h2>")
    A('<div id="detail"></div>')

    # --- the named failure ---
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
    A("<p>Offline by default. The same seed and inputs reproduce "
      "<code>selected.jsonl</code> byte for byte. Every candidate, rejections included, is "
      "in <code>designs.jsonl</code>; this page is a view of it and never the record of "
      "truth.</p>")

    A("</main>")
    A('<div class="cmpbar" id="cmpbar"><span id="cmpn">0 selected</span>'
      '<button class="btn" id="cmplab">Compare the lab slots</button>'
      '<button class="btn" id="cmpclear">Clear</button>'
      '<span class="kv">Shift-click rows to add or remove.</span></div>')
    A("<footer>")
    A(f"FourWells · schema {_h(config.get('schema_version', '?'))} · "
      f"{f['generated']} records, {f['passed']} legacy screen passes, {len(shortlist)} preview entries. "
      "Heuristic predictions, not measurements or calibrated probabilities. No network required.")
    A("</footer>")
    A(f'<script type="application/json" id="data">'
      f"{_payload(records, selected, shortlist)}</script>")
    A(f"<script>{_JS}</script>")
    A("</body></html>")
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
