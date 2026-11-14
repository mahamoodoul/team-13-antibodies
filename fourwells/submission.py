"""Phase 7 — final submission. The ranked list we actually send.

The portfolio stage answers "which four designs take the four guaranteed lab
wells". That is a different question from "what do we submit", and conflating
them is how a team forfeits most of what it won:

    every team gets 4 wells. Placing buys 16 / 12 / 8 for 1st / 2nd / 3rd,
    and each of 6 judges may nominate a favourite for +2.

So a list that stops at four throws away every slot we might win on the day.
The organisers take **a ranked list of up to 20**, and this module builds it.

Three decisions, each one a way the list could be wrong:

  - **The four keep their portfolio order and sit at the top.** That order is a
    joint allocation across clusters, not a sort, so re-sorting it here would
    silently discard the diversity decision the portfolio stage made.
  - **Ranks 5-20 are filled round-robin across clusters, not straight down the
    score.** Sixteen slots filled by score alone would be sixteen variants of
    whichever CDRH3 family happens to score well, which tests one hypothesis
    sixteen times. Each cluster contributes its best before any contributes a
    second.
  - **Nothing is fabricated to fill a column.** A design with an unscored axis
    exports an empty cell, never a zero. Missing evidence is the thing the
    scoring rubric asks us to record, not to paper over.

Outputs, named as the project spec names them:

    results/final_ranked_designs.csv   the submission: up to 20, ranked
    results/candidate_scores.csv       every candidate, with why it did or
                                       did not make the list
    results/final_sequences.fasta      sequences as ordered
    results/submission.json            machine-readable, full evidence

Usage:

    python3 -m fourwells.submission results/
    make submission
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .report import construct_of
from .schema import AXES, DesignRecord, read_jsonl

# The organisers take a ranked list of up to this many designs.
SUBMISSION_CAP = 20

# Guaranteed wells. Everything past this is contingent on placing or on a judge
# nomination, which is why rank and priority are different columns.
GUARANTEED_WELLS = 4

# A blocker that is not an oversight must be recorded, not deleted. This file
# holds decisions the team made on purpose; `readiness()` suppresses the
# matching blocker only when the decision says why, and the payload carries the
# decision so a judge can see it was a choice.
DECISION_FILE = (
    Path(__file__).resolve().parent.parent
    / "data" / "reference" / "submission_decisions.json"
)


def load_decisions(path: Path | None = None) -> list[dict]:
    p = path or DECISION_FILE
    if not p.exists():
        return []
    try:
        blob = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    decisions = blob.get("decisions", []) if isinstance(blob, dict) else []
    return [d for d in decisions if isinstance(d, dict)]


# --------------------------------------------------------------------------- #
# building the list
# --------------------------------------------------------------------------- #


def _eligible(records: list[DesignRecord]) -> list[DesignRecord]:
    """Everything that could legitimately be submitted.

    Deliberately strict about `joint_score is not None`: an unranked design
    cannot be placed in a *ranked* list, and guessing a position for it would
    be inventing the one thing the list is supposed to communicate.
    """
    return [
        r for r in records
        if r.gates.passed
        and not r.is_baseline
        and not r.is_stub
        and r.joint_score is not None
    ]


def _round_robin_by_cluster(pool: list[DesignRecord]) -> list[DesignRecord]:
    """Best of each cluster, then second-best of each, and so on.

    Within a pass, clusters are visited by the score of the design they are
    contributing, so a strong cluster still ranks above a weak one — it just
    cannot take two slots before every other hypothesis has taken one.
    """
    by_cluster: dict[str, list[DesignRecord]] = {}
    for r in pool:
        by_cluster.setdefault(r.cluster or f"_solo_{r.design_id}", []).append(r)
    for members in by_cluster.values():
        members.sort(key=lambda r: (-(r.joint_score or 0), r.design_id))

    out: list[DesignRecord] = []
    depth = 0
    while True:
        tier = [m[depth] for m in by_cluster.values() if len(m) > depth]
        if not tier:
            return out
        tier.sort(key=lambda r: (-(r.joint_score or 0), r.design_id))
        out.extend(tier)
        depth += 1


def _unique_constructs(ordered: list[DesignRecord],
                       cap: int) -> list[DesignRecord]:
    """The list may not spend two slots on the same molecule.

    Two design ids can carry byte-identical constructs (the generator emitted
    the same heavy/light pair twice under different seeds). The organisers rank
    molecules, not ids, so a duplicate is a wasted slot and a claim of breadth
    we do not have. The first occurrence wins; later ones are dropped and the
    list is refilled from further down so the cap is still met when the pool
    allows it.
    """
    out: list[DesignRecord] = []
    seen: set[str] = set()
    for r in ordered:
        seq, _, _ = construct_of(r)
        if seq in seen:
            continue
        seen.add(seq)
        out.append(r)
        if len(out) >= cap:
            break
    return out


def build_ranked_list(
    records: list[DesignRecord],
    selected: list[DesignRecord] | None = None,
    cap: int = SUBMISSION_CAP,
) -> list[DesignRecord]:
    """The submission: the portfolio's picks, then the rest, up to `cap`."""
    if selected is None:
        selected = sorted(
            [r for r in records if r.selected], key=lambda r: r.rank or 999
        )
    picked_ids = {r.design_id for r in selected}
    rest = [r for r in _eligible(records) if r.design_id not in picked_ids]
    ordered = (list(selected) + _round_robin_by_cluster(rest))
    return _unique_constructs(ordered, cap)


def priority_of(position: int) -> str:
    return "lab" if position <= GUARANTEED_WELLS else "reserve"


# --------------------------------------------------------------------------- #
# readiness
# --------------------------------------------------------------------------- #


def readiness(records: list[DesignRecord], ranked: list[DesignRecord],
              decisions: list[dict] | None = None) -> list[str]:
    """What stands between this list and being sendable.

    Recomputed from the records every time rather than read from a stored
    audit, because this runs long after the audit was written and a blocker
    that only lives in a stale file is a blocker that quietly disappears.

    `decisions` are deliberate choices recorded in
    data/reference/submission_decisions.json. A decision can clear exactly the
    blocker it names, and only when it carries a reason; it can never clear an
    evidence blocker such as a design with no abguard pass.
    """
    decisions = decisions or []
    decided_kinds = {
        d.get("kind") for d in decisions if str(d.get("reason", "")).strip()
    }
    out: list[str] = []

    if not ranked:
        out.append("the ranked list is empty — no design passed every gate with a score")
        return out

    unseen = [
        r.design_id for r in ranked
        if ((r.gates.checks or {}).get("abguard") or {}).get("status") != "pass"
    ]
    if unseen:
        out.append(
            f"{len(unseen)} of {len(ranked)} have no abguard pass. abguard assigns the "
            "track and is the organisers' authority; it is not installed on the VM, so "
            "this cannot be cleared locally. Put it to a mentor before submitting."
        )

    stubs = [r.design_id for r in records if r.is_stub]
    if stubs:
        out.append(
            f"{len(stubs)} stub records exist in this run and were excluded from the "
            "list. They are not designs; confirm the pool is the real one."
        )

    tracks = {r.track for r in ranked if r.track}
    if len(tracks) == 1 and "single_track" not in decided_kinds:
        out.append(
            f"every design is {next(iter(tracks))} — the two tracks are judged "
            "independently, so the other track is an empty entry."
        )

    if len(ranked) < SUBMISSION_CAP:
        out.append(
            f"{len(ranked)} of {SUBMISSION_CAP} slots filled — "
            f"{SUBMISSION_CAP - len(ranked)} submission slots left empty."
        )

    unscored = [
        r.design_id for r in ranked
        if any(r.axes.get(a) is None for a in AXES)
    ]
    if unscored:
        out.append(
            f"{len(unscored)} have at least one unscored axis, so their rank rests on "
            "partial evidence: " + ", ".join(unscored[:5])
        )

    return out


# --------------------------------------------------------------------------- #
# exports
# --------------------------------------------------------------------------- #


def _cell(v: Any) -> str:
    """A number, or an empty cell. Never a zero standing in for 'unknown'."""
    return "" if v is None else f"{v:.4f}" if isinstance(v, float) else str(v)


def _csv_safe(s: str) -> str:
    """Stop a spreadsheet evaluating an exported id or sequence as a formula."""
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def _epitope_basis(rec: DesignRecord) -> str:
    ev = (rec.axis_evidence or {}).get("epitope") or {}
    return str(ev.get("basis", "none"))


def write_ranked_csv(ranked: list[DesignRecord], path: Path) -> None:
    with open(path, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow([
            "rank", "priority", "design_id", "track", "format", "length_aa",
            "cdrh3", "substitutions_from_parent", "binding", "epitope",
            "epitope_basis", "stability", "joint_score", "cluster",
            "abguard_status", "sequence", "rationale", "kill_criterion",
        ])
        for i, r in enumerate(ranked, start=1):
            seq, length, _ = construct_of(r)
            wr.writerow([
                i,
                priority_of(i),
                _csv_safe(r.design_id),
                r.track or "",
                r.format or "",
                length,
                r.cdrh3 or "",
                _cell(r.cdrh3_mutations_from_tras),
                _cell(r.axes.get("binding")),
                _cell(r.axes.get("epitope")),
                _epitope_basis(r),
                _cell(r.axes.get("stability")),
                _cell(r.joint_score),
                r.cluster or "",
                ((r.gates.checks or {}).get("abguard") or {}).get("status", "NOT RUN"),
                _csv_safe(seq),
                " | ".join(r.rationale),
                r.kill_criterion or "",
            ])


def write_candidate_scores(records: list[DesignRecord], ranked: list[DesignRecord], path: Path) -> None:
    """Every candidate, and why it is or is not in the submission.

    This is the "validate every candidate" half of Phase 7. A judge asking
    "what did you throw away, and why" should not have to take our word for the
    funnel — the rejected rows carry their own named reasons.
    """
    ranks = {r.design_id: i for i, r in enumerate(ranked, start=1)}
    with open(path, "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow([
            "design_id", "track", "generator", "gates_passed", "failed_rules",
            "is_stub", "binding", "epitope", "stability", "joint_score",
            "cluster", "submitted", "submission_rank", "excluded_because",
        ])
        for r in sorted(records, key=lambda r: (-(r.joint_score or -1), r.design_id)):
            rank = ranks.get(r.design_id)
            if rank:
                why = ""
            elif r.is_baseline:
                why = "reference molecule, not a candidate"
            elif r.is_stub:
                why = "stub record, not a design"
            elif not r.gates.passed:
                why = "failed entry gates"
            elif r.joint_score is None:
                why = "unscored — cannot be placed in a ranked list"
            else:
                why = f"eligible, ranked below the top {SUBMISSION_CAP}"
            wr.writerow([
                _csv_safe(r.design_id), r.track or "", r.generator or "",
                "yes" if r.gates.passed else "no",
                "; ".join(r.gates.failed_rules),
                "yes" if r.is_stub else "no",
                _cell(r.axes.get("binding")), _cell(r.axes.get("epitope")),
                _cell(r.axes.get("stability")), _cell(r.joint_score),
                r.cluster or "", "yes" if rank else "no", rank or "", why,
            ])


def write_fasta(ranked: list[DesignRecord], path: Path) -> None:
    lines = []
    for i, r in enumerate(ranked, start=1):
        seq, length, basis = construct_of(r)
        lines.append(
            f">{r.design_id} rank={i} priority={priority_of(i)} "
            f"track={r.track or 'unassigned'} format={r.format or '?'} "
            f"length={length} basis={basis}"
        )
        for j in range(0, len(seq), 60):
            lines.append(seq[j:j + 60])
    path.write_text("\n".join(lines) + "\n")


def write_json(
    records: list[DesignRecord],
    ranked: list[DesignRecord],
    path: Path,
    meta: dict | None = None,
    decisions: list[dict] | None = None,
) -> dict:
    decisions = load_decisions() if decisions is None else decisions
    blockers = readiness(records, ranked, decisions)
    payload = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "submission_cap": SUBMISSION_CAP,
        "guaranteed_wells": GUARANTEED_WELLS,
        "submitted": len(ranked),
        "pool": {
            "generated": len(records),
            "eligible": len(_eligible(records)),
            "gate_failures": sum(1 for r in records if not r.gates.passed),
        },
        "submission_ready": not blockers,
        "blockers": blockers,
        "decisions": decisions,
        "designs": [],
        **(meta or {}),
    }
    for i, r in enumerate(ranked, start=1):
        seq, length, basis = construct_of(r)
        payload["designs"].append({
            "rank": i,
            "priority": priority_of(i),
            "design_id": r.design_id,
            "track": r.track,
            "format": r.format,
            "generator": r.generator,
            "cdrh3": r.cdrh3,
            "substitutions_from_parent": r.cdrh3_mutations_from_tras,
            "construct": {"sequence": seq, "length": length, "basis": basis},
            "axes": {a: r.axes.get(a) for a in AXES},
            "axis_evidence": r.axis_evidence,
            "joint_score": r.joint_score,
            "cluster": r.cluster,
            "gates": {
                "passed": r.gates.passed,
                "abguard": ((r.gates.checks or {}).get("abguard") or {}).get("status", "NOT RUN"),
            },
            "rationale": r.rationale,
            "kill_criterion": r.kill_criterion,
        })
    path.write_text(json.dumps(payload, indent=2))
    return payload


def write_all(
    records: list[DesignRecord],
    out_dir: Path,
    selected: list[DesignRecord] | None = None,
    meta: dict | None = None,
    decisions: list[dict] | None = None,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ranked = build_ranked_list(records, selected)

    paths = {
        "ranked_csv": out_dir / "final_ranked_designs.csv",
        "candidate_scores": out_dir / "candidate_scores.csv",
        "fasta": out_dir / "final_sequences.fasta",
        "json": out_dir / "submission.json",
    }
    write_ranked_csv(ranked, paths["ranked_csv"])
    write_candidate_scores(records, ranked, paths["candidate_scores"])
    write_fasta(ranked, paths["fasta"])
    write_json(records, ranked, paths["json"], meta, decisions)
    return paths


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="fourwells.submission",
        description="Build the ranked submission (up to 20) from a run directory",
    )
    ap.add_argument("rundir", type=Path, help="a directory holding designs.jsonl")
    a = ap.parse_args(argv)

    designs = a.rundir / "designs.jsonl"
    if not designs.exists():
        print(f"no designs.jsonl in {a.rundir}")
        return 1

    records = read_jsonl(designs)
    sel_path = a.rundir / "selected.jsonl"
    selected = read_jsonl(sel_path) if sel_path.exists() else None

    decisions = load_decisions()
    paths = write_all(records, a.rundir, selected, decisions=decisions)
    ranked = build_ranked_list(records, selected)
    blockers = readiness(records, ranked, decisions)

    print(f"\n  submission  {len(ranked)} of {SUBMISSION_CAP} ranked "
          f"({GUARANTEED_WELLS} lab · {max(0, len(ranked) - GUARANTEED_WELLS)} reserve)")
    print(f"  pool        {len(_eligible(records))} eligible of {len(records)} generated")
    for k, p in paths.items():
        print(f"  {k:18s} {p}")

    if blockers:
        print(f"\n  NOT SUBMISSION READY — {len(blockers)} blocker(s):")
        for b in blockers:
            print(f"    - {b}")
    else:
        print("\n  submission ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
