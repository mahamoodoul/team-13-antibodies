"""The order sheet — OWNER: Mahamoodoul. One page, handed to the lab.

This is not a smaller report. The report argues; the order sheet instructs. It
answers exactly four questions and nothing else:

    what do we want synthesised, in what order, why that one, and when do we
    call it a failure

Three decisions worth defending, because each is a way the sheet could mislead
the people who run the assay:

  - **The bar is the geometric mean of trastuzumab's own eight replicates**
    (0.0954 nM), not the single row people cite (0.152 nM). KD is
    log-distributed and those eight values span 6.24x, so five of the parent's
    own replicates "beat" 0.152. Every predicted improvement smaller than that
    spread is printed as inside the noise, next to the number, where it cannot
    be skimmed past. `data/reference/trastuzumab.json` is the source.
  - **Priority is not rank.** Ranks 1-4 are the guaranteed wells; 5-20 are
    reserves that only get made if we place or a judge nominates. The lab needs
    to know which is which, because a reserve arriving as "priority 5" reads
    like a queue and it is actually a contingency.
  - **It refuses to print a clean sheet for a run that is not submission-ready.**
    A stub run, or one abguard never saw, gets a banner and every row marked. An
    order sheet is the one artefact that leaves our hands and turns into
    molecules, so "looks final but is not" is the failure mode to design out.

Usage: `python3 -m fourwells.ordersheet RUNDIR`, or `fourwells order-sheet RUNDIR`.
Writes `order-sheet.md` and a self-contained, printable `order-sheet.html`.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .report import SUBMISSION_CAP, build_shortlist
from .schema import AXES, DesignRecord, read_jsonl

# Trastuzumab's measured bar, from the 8 SPR replicates whose CDRH3 is the
# parent loop. Read off data/reference/trastuzumab.json rather than retyped, so
# the sheet cannot drift from the reference the rest of the pipeline uses.
REFERENCE_FILE = Path(__file__).resolve().parent.parent / "data" / "reference" / "trastuzumab.json"

GUARANTEED_WELLS = 4  # every team gets 4; placing buys 16/12/8, judges +2


def _bar() -> dict[str, Any]:
    """The affinity bar and its noise, or an explicit absence."""
    try:
        blob = json.loads(REFERENCE_FILE.read_text())
        m = blob["baseline_measurements"]
        return {
            "geometric_mean_nM": m["geometric_mean_nM"],
            "fold_spread": m["fold_spread"],
            "n": m["n"],
        }
    except (OSError, KeyError, json.JSONDecodeError):
        return {"geometric_mean_nM": None, "fold_spread": None, "n": 0}


def readiness(records: list[DesignRecord], shortlist: list[DesignRecord]) -> list[str]:
    """Why this sheet must not be sent to a synthesis vendor yet.

    Deliberately recomputed here from the records rather than read from the
    portfolio audit: the sheet can be re-rendered from a run directory long
    after the audit was written, and a blocker that only lives in the audit is
    a blocker that silently disappears on re-render.
    """
    out: list[str] = []

    stubs = [r.design_id for r in shortlist if r.is_stub]
    if stubs:
        out.append(
            f"{len(stubs)} of {len(shortlist)} rows are STUB records "
            f"({', '.join(stubs[:4])}{', …' if len(stubs) > 4 else ''}) — random CDRH3 "
            "substitutions from the offline fallback generator, not designs. "
            "Commit a real Foundry batch under data/generated/ first."
        )

    unseen = [
        r.design_id
        for r in shortlist
        if ((r.gates.checks or {}).get("abguard") or {}).get("status") != "pass"
    ]
    if unseen:
        out.append(
            f"{len(unseen)} of {len(shortlist)} rows have no abguard pass. abguard "
            "assigns the track and is the organisers' authority — run it on the VM."
        )

    if any((r.gates.checks or {}).get("provided_note") for r in shortlist):
        out.append(
            "the provided-antibody set is absent, so the novelty distance rules are "
            "UNCHECKED, not passed (data/reference/provided_antibodies.json)."
        )

    tracks = {r.track for r in shortlist if r.track}
    if len(tracks) == 1:
        out.append(
            f"every row is {next(iter(tracks))} — the two tracks are judged "
            "independently, so the other track is an empty entry."
        )

    if len(shortlist) < SUBMISSION_CAP:
        out.append(
            f"{len(shortlist)} rows against a cap of {SUBMISSION_CAP} — "
            f"{SUBMISSION_CAP - len(shortlist)} submission slots left empty."
        )

    return out


def _priority(rank: int) -> str:
    return "LAB" if rank <= GUARANTEED_WELLS else "reserve"


# Rationale lines the sheet deliberately drops. The joint arithmetic is already
# a column, and the three per-axis breakdowns belong in the report, which argues
# the case — the sheet only has to say why this one is on the list at all.
_NOT_A_REASON = (
    "joint p(", "binding:", "epitope:", "stability:", "structure confidence",
)


def _pick(rec: DesignRecord, prefix: str) -> str | None:
    for line in rec.rationale or []:
        text = str(line).strip().lstrip("-• ").strip()
        if text.lower().startswith(prefix):
            return text
    return None


def _why(rec: DesignRecord) -> str:
    """Why this one is on the list — one line, and not the arithmetic.

    The portfolio stage writes a line that begins "On the list because", which
    is exactly this question answered in its own words, so prefer it verbatim
    rather than paraphrasing a ranking decision this module did not make.
    """
    chosen = _pick(rec, "on the list because")
    if chosen:
        return chosen[0].upper() + chosen[1:]

    for line in rec.rationale or []:
        text = str(line).strip().lstrip("-• ").strip()
        if text and not text.lower().startswith(_NOT_A_REASON):
            return text

    if rec.cluster:
        return f"Represents cluster {rec.cluster} — no rationale recorded"
    return "No rationale recorded — do not order"


def _hypothesis(rec: DesignRecord) -> str:
    """What this design tests that its neighbours do not.

    The reason four wells never go to four variants of one parent, so it is on
    the sheet and not only in the report: whoever drops a design for logistics
    needs to see which hypothesis leaves with it.
    """
    line = _pick(rec, "represents cluster")
    if line:
        return line
    return f"cluster {rec.cluster}" if rec.cluster else "unclustered"


def _noise_note(rec: DesignRecord, spread: float | None) -> str:
    """Flag a predicted win that is smaller than the parent's own spread.

    The axes are probabilities that a design beats trastuzumab, not fold
    improvements, so this cannot be a fold comparison. What it can say — and
    what the lab needs — is that a near-coin-flip binding call is indistinct
    from the parent given an assay this noisy.
    """
    b = (rec.axes or {}).get("binding")
    if b is None:
        return "binding unscored"
    if spread and 0.4 <= b <= 0.6:
        return f"inside the noise (parent spans {spread:.1f}x over 8 replicates)"
    if b < 0.4:
        return "predicted worse than parent on affinity"
    return ""


def rows(shortlist: list[DesignRecord], spread: float | None) -> list[dict[str, Any]]:
    out = []
    for i, rec in enumerate(shortlist, start=1):
        rank = rec.rank if (rec.rank and rec.selected) else i
        seq = (rec.sequence or "").replace(" ", "")
        out.append({
            "rank": i,
            "priority": _priority(i),
            "design_id": rec.design_id,
            "track": rec.track or "unassigned",
            "format": (rec.format or "?").upper(),
            "length": len(seq),
            "cdrh3": rec.cdrh3 or "—",
            "identity": rec.cdrh3_identity_to_tras,
            "joint": rec.joint_score,
            "why": _why(rec),
            "hypothesis": _hypothesis(rec),
            "kill": rec.kill_criterion or "none recorded",
            "caveat": _noise_note(rec, spread),
            "stub": bool(rec.is_stub),
            "sequence": seq,
            "_rank_field": rank,
        })
    return out


# ---------------------------------------------------------------- markdown


def render_markdown(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    config: dict[str, Any] | None = None,
) -> str:
    config = config or {}
    bar = _bar()
    shortlist = build_shortlist(records, selected)
    table = rows(shortlist, bar["fold_spread"])
    blockers = readiness(records, shortlist)

    L: list[str] = []
    L.append("# Order sheet — Team 13 · FourWells")
    L.append("")
    meta = [
        f"**Target** {config.get('target', '—')}",
        f"**Reference** {config.get('reference', 'trastuzumab')}",
        f"**Run** `{config.get('run_id', '—')}`",
        f"**Commit** `{str(config.get('git_sha', '—'))[:12]}`",
    ]
    L.append(" · ".join(meta))
    L.append("")

    if blockers:
        L.append("> ## ⛔ NOT READY TO ORDER")
        L.append(">")
        for b in blockers:
            L.append(f"> - {b}")
        L.append(">")
        L.append("> Nothing on this sheet should be synthesised while any line above stands.")
        L.append("")

    if bar["geometric_mean_nM"] is not None:
        L.append(
            f"**The bar:** trastuzumab binds HER2 at **{bar['geometric_mean_nM']:.4f} nM** "
            f"(geometric mean of {bar['n']} SPR replicates). Those replicates span "
            f"**{bar['fold_spread']:.2f}x**, so a design predicted to beat the parent by "
            "less than that has not been shown to beat anything. KD is log-distributed; "
            "do not compare single rows."
        )
    else:
        L.append("**The bar:** reference measurements unavailable — affinity claims unquantified.")
    L.append("")
    L.append(
        f"**Priority:** ranks 1–{GUARANTEED_WELLS} are the guaranteed wells. "
        f"Ranks {GUARANTEED_WELLS + 1}–{SUBMISSION_CAP} are reserves, made only if we "
        "place (16/12/8 for 1st/2nd/3rd) or a judge nominates one (+2). A reserve is a "
        "contingency, not a queue position."
    )
    L.append("")

    L.append("| # | Priority | Design | Track | Fmt | aa | CDRH3 | Id→parent | Joint |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in table:
        ident = "—" if r["identity"] is None else f"{r['identity']:.2f}"
        joint = "—" if r["joint"] is None else f"{r['joint']:.3f}"
        flag = " ⚠️" if r["stub"] else ""
        L.append(
            f"| {r['rank']} | {'**LAB**' if r['priority'] == 'LAB' else 'reserve'} | "
            f"`{r['design_id']}`{flag} | {r['track']} | {r['format']} | {r['length']} | "
            f"`{r['cdrh3']}` | {ident} | {joint} |"
        )
    L.append("")

    L.append("## Why each one, and when to call it a failure")
    L.append("")
    for r in table:
        L.append(f"**{r['rank']}. `{r['design_id']}`** — {r['why']}")
        L.append(f"  - **Tests:** {r['hypothesis']}")
        if r["caveat"]:
            L.append(f"  - ⚠️ {r['caveat']}")
        L.append(f"  - **Kill criterion:** {r['kill']}")
        L.append("")

    L.append("## Sequences")
    L.append("")
    L.append("Chains separated by `/`. Lengths above are the total across chains, "
             f"against the abguard ceiling of 250 aa.")
    L.append("")
    for r in table:
        L.append(f"- **{r['rank']} `{r['design_id']}`** ({r['format']}, {r['length']} aa)")
        L.append(f"  ```")
        L.append(f"  {r['sequence']}")
        L.append(f"  ```")
    L.append("")

    return "\n".join(L)


# ---------------------------------------------------------------- html


_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       margin: 0; padding: 28px 32px; color: #111; background: #fff; max-width: 1100px; }
h1 { font-size: 19px; margin: 0 0 2px; letter-spacing: -0.2px; }
h2 { font-size: 14px; margin: 22px 0 8px; text-transform: uppercase;
     letter-spacing: 0.06em; color: #555; border-bottom: 1px solid #e4e4e7; padding-bottom: 4px; }
.meta { color: #666; font-size: 12px; margin-bottom: 14px; }
.bar { background: #f6f7f9; border-left: 3px solid #52525b; padding: 9px 12px;
       margin: 12px 0; font-size: 12.5px; }
.blocked { background: #fff1f0; border: 1px solid #ffccc7; border-left: 3px solid #cf1322;
           padding: 11px 14px; margin: 12px 0; }
.blocked h3 { margin: 0 0 6px; font-size: 13px; color: #a8071a; text-transform: uppercase;
              letter-spacing: 0.05em; }
.blocked ul { margin: 0; padding-left: 18px; }
.blocked li { margin: 3px 0; font-size: 12.5px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; margin: 8px 0 4px; }
th { text-align: left; font-weight: 600; color: #555; border-bottom: 1.5px solid #d4d4d8;
     padding: 5px 7px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
td { border-bottom: 1px solid #f0f0f2; padding: 5px 7px; vertical-align: top; }
tr.lab td { background: #fafafa; font-weight: 500; }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px; }
.tag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px;
       font-weight: 600; letter-spacing: 0.04em; }
.tag.lab { background: #111; color: #fff; }
.tag.res { background: #e4e4e7; color: #52525b; }
.stub { color: #cf1322; font-weight: 600; }
.why { margin: 0 0 12px; }
.why .id { font-weight: 600; }
.why .kill { color: #555; font-size: 12px; }
.why .caveat { color: #ad4e00; font-size: 12px; }
.seq { background: #fafafa; border: 1px solid #f0f0f2; padding: 6px 8px; margin: 3px 0 10px;
       word-break: break-all; font-family: ui-monospace, Menlo, monospace; font-size: 11px; }
@media print {
  body { padding: 0; font-size: 10.5px; max-width: none; }
  h2 { margin: 12px 0 5px; }
  .seq { font-size: 9px; }
  tr { page-break-inside: avoid; }
}
"""


def _h(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def render_html(
    records: list[DesignRecord],
    selected: list[DesignRecord],
    config: dict[str, Any] | None = None,
) -> str:
    config = config or {}
    bar = _bar()
    shortlist = build_shortlist(records, selected)
    table = rows(shortlist, bar["fold_spread"])
    blockers = readiness(records, shortlist)

    P: list[str] = []
    P.append("<!DOCTYPE html>")
    P.append('<html lang="en"><head><meta charset="utf-8">')
    P.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    P.append("<title>Order sheet — Team 13 · FourWells</title>")
    P.append(f"<style>{_CSS}</style></head><body>")

    P.append("<h1>Order sheet — Team 13 · FourWells</h1>")
    P.append(
        '<div class="meta">'
        f"Target {_h(config.get('target', '—'))} · "
        f"Reference {_h(config.get('reference', 'trastuzumab'))} · "
        f"Run <span class=\"mono\">{_h(config.get('run_id', '—'))}</span> · "
        f"Commit <span class=\"mono\">{_h(str(config.get('git_sha', '—'))[:12])}</span>"
        "</div>"
    )

    if blockers:
        P.append('<div class="blocked"><h3>⛔ Not ready to order</h3><ul>')
        for b in blockers:
            P.append(f"<li>{_h(b)}</li>")
        P.append("</ul><div style=\"margin-top:7px;font-size:12.5px\">Nothing on this sheet "
                 "should be synthesised while any line above stands.</div></div>")

    if bar["geometric_mean_nM"] is not None:
        P.append(
            '<div class="bar"><strong>The bar:</strong> trastuzumab binds HER2 at '
            f"<strong>{bar['geometric_mean_nM']:.4f} nM</strong> (geometric mean of "
            f"{bar['n']} SPR replicates). Those replicates span "
            f"<strong>{bar['fold_spread']:.2f}×</strong>, so a design predicted to beat the "
            "parent by less than that has not been shown to beat anything. "
            "K<sub>D</sub> is log-distributed; do not compare single rows.</div>"
        )
    P.append(
        f'<div class="bar"><strong>Priority:</strong> ranks 1–{GUARANTEED_WELLS} are the '
        f"guaranteed wells. Ranks {GUARANTEED_WELLS + 1}–{SUBMISSION_CAP} are reserves, made "
        "only if we place (16/12/8) or a judge nominates one (+2). A reserve is a "
        "contingency, not a queue position.</div>"
    )

    P.append("<h2>The order</h2><table><thead><tr>")
    for col in ("#", "Priority", "Design", "Track", "Fmt", "aa", "CDRH3", "Id→parent", "Joint"):
        P.append(f"<th>{_h(col)}</th>")
    P.append("</tr></thead><tbody>")
    for r in table:
        ident = "—" if r["identity"] is None else f"{r['identity']:.2f}"
        joint = "—" if r["joint"] is None else f"{r['joint']:.3f}"
        tag = ('<span class="tag lab">LAB</span>' if r["priority"] == "LAB"
               else '<span class="tag res">reserve</span>')
        stub = ' <span class="stub">STUB</span>' if r["stub"] else ""
        P.append(
            f'<tr class="{"lab" if r["priority"] == "LAB" else ""}">'
            f"<td>{r['rank']}</td><td>{tag}</td>"
            f"<td><span class=\"mono\">{_h(r['design_id'])}</span>{stub}</td>"
            f"<td>{_h(r['track'])}</td><td>{_h(r['format'])}</td><td>{r['length']}</td>"
            f"<td><span class=\"mono\">{_h(r['cdrh3'])}</span></td>"
            f"<td>{ident}</td><td>{joint}</td></tr>"
        )
    P.append("</tbody></table>")

    P.append("<h2>Why each one, and when to call it a failure</h2>")
    for r in table:
        P.append('<div class="why">')
        P.append(f'<span class="id">{r["rank"]}. <span class="mono">{_h(r["design_id"])}</span></span> — {_h(r["why"])}')
        P.append(f'<div class="kill"><strong>Tests:</strong> {_h(r["hypothesis"])}</div>')
        if r["caveat"]:
            P.append(f'<div class="caveat">⚠️ {_h(r["caveat"])}</div>')
        P.append(f'<div class="kill"><strong>Kill criterion:</strong> {_h(r["kill"])}</div>')
        P.append("</div>")

    P.append("<h2>Sequences</h2>")
    P.append('<div class="meta">Lengths are the total across chains, against the abguard '
             "ceiling of 250 aa.</div>")
    for r in table:
        P.append(f'<div><strong>{r["rank"]} <span class="mono">{_h(r["design_id"])}</span></strong> '
                 f'({_h(r["format"])}, {r["length"]} aa)</div>')
        P.append(f'<div class="seq">{_h(r["sequence"])}</div>')

    P.append("</body></html>")
    return "\n".join(P)


# ---------------------------------------------------------------- entry point


def write_outputs(
    rundir: Path,
    records: list[DesignRecord],
    selected: list[DesignRecord],
    config: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    md = rundir / "order-sheet.md"
    htm = rundir / "order-sheet.html"
    md.write_text(render_markdown(records, selected, config))
    htm.write_text(render_html(records, selected, config))
    return md, htm


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="fourwells.ordersheet",
        description="Render the one-page order sheet from a run directory",
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

    md, htm = write_outputs(a.rundir, records, selected, config)
    print(f"wrote {md}")
    print(f"wrote {htm}")

    blockers = readiness(records, build_shortlist(records, selected))
    if blockers:
        print(f"\n⛔ NOT READY TO ORDER — {len(blockers)} blocker(s):")
        for b in blockers:
            print(f"   - {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
