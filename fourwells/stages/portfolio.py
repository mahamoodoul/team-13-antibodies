"""Portfolio selection — OWNER: Rizve. Layer 3, and the 40%.

Four of our designs are guaranteed a well. This file decides which four, and
the reasoning it writes into each record is the thing a judge will ask about.

THE OBJECTIVE IS NOT A RANKED LIST. A design counts as S-tier only if it beats
trastuzumab on binding, epitope competition *and* thermostability, and the team
with the most S-tier designs wins. So what we maximise is the expected number
of designs that win on three axes at once:

    joint = P(binding) * P(epitope) * P(stability)

A product, not a weighted sum, and the difference is the entire point. A design
at (0.95, 0.95, 0.05) is excellent on two axes and hopeless on the third: a
weighted sum ranks it near the top, the product puts it near the bottom, and
the product is right, because that design cannot be S-tier. A weighted sum is
how a team spends four wells on four molecules that each win one axis and
collects nothing.

THEN: ALLOCATE ACROSS CLUSTERS, NOT DOWN THE LIST. Four variants of one parent
share a failure mode. If the parent is wrong — wrong loop, wrong binding mode,
wrong framework — all four die together and we learn one thing from four wells.
We cluster by parent, by CDRH3 and by predicted binding mode, then spend one
slot per cluster. Four slots, four distinct hypotheses, four independent shots.
That costs us some expected value on paper and buys uncorrelated failure, which
is the right trade when the sample size is four.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import features
from ..align import identity
from ..schema import AXES, DesignRecord
from .gates import SUBMITTABLE_DISTANCE

# CDRH3 identity at or above this puts two designs in the same cluster: they
# are variations on one loop hypothesis, not two.
CLUSTER_IDENTITY = 0.80

STUB_RATIONALE = (
    "STUB SELECTION — ordered by design_id among gate-passing records. "
    "No axis prediction informed this choice."
)


def joint_score(rec: DesignRecord) -> float | None:
    """Expected-S-tier probability. None while any axis is unscored.

    Deliberately returns None rather than treating a missing axis as 0.5 or
    dropping it from the product: a design scored on two axes is not
    comparable to one scored on three, and quietly making it comparable is how
    an unscored design wins a slot it did not earn.
    """
    vals = [rec.axes.get(a) for a in AXES]
    if any(v is None for v in vals):
        return None
    score = 1.0
    for v in vals:
        score *= float(v)
    return score


def is_borderline(rec: DesignRecord) -> bool:
    """Passes the novelty filter as measured, but sits where the wording and
    the observed behaviour disagree — exactly 2 substitutions from a provided
    sequence. Not a rejection; a tie-break against.

    It costs us nothing to prefer a design that is unambiguously submittable
    when one is available at a similar score, and it costs a whole well if the
    organisers read the rule the strict way.
    """
    return bool(((rec.gates.checks or {}).get("novelty") or {}).get("borderline"))


def weakest_axis(rec: DesignRecord) -> tuple[str, float] | None:
    vals = [(a, rec.axes.get(a)) for a in AXES if rec.axes.get(a) is not None]
    return min(vals, key=lambda kv: kv[1]) if vals else None


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


@dataclass
class Cluster:
    cid: str
    members: list[DesignRecord] = field(default_factory=list)
    hypothesis: str = ""

    @property
    def best(self) -> DesignRecord | None:
        """The representative of this hypothesis.

        Borderline designs sort last at equal score, so a cluster that holds an
        unambiguously submittable design sends that one to the lab.
        """
        scored = [m for m in self.members if m.joint_score is not None]
        if scored:
            return max(
                scored,
                key=lambda r: (round(r.joint_score, 4), not is_borderline(r), r.design_id),
            )
        return min(self.members, key=lambda r: (is_borderline(r), r.design_id)) if self.members else None

    @property
    def best_score(self) -> float:
        b = self.best
        return b.joint_score if b and b.joint_score is not None else -1.0


def _binding_mode(rec: DesignRecord) -> str:
    """Coarse binding-mode key: track, format, and whether the epitope axis is
    evidenced or merely inferred. Two designs that differ here fail for
    different reasons, which is exactly what we are trying to spread across."""
    ev = (rec.axis_evidence or {}).get("epitope") or {}
    return f"{rec.track or 'unassigned'}/{rec.format or '?'}/{ev.get('basis', 'none')}"


def cluster(records: list[DesignRecord]) -> list[Cluster]:
    """Single-linkage on CDRH3 identity, partitioned first by parent and mode.

    Single-linkage because the question is "does this design share a failure
    mode with one already in the basket", and sharing it with any member is
    enough. n is small after gating, so the O(n^2) comparison is free.
    """
    buckets: dict[str, list[DesignRecord]] = {}
    for rec in records:
        key = f"{rec.parent or 'none'}|{_binding_mode(rec)}"
        buckets.setdefault(key, []).append(rec)

    clusters: list[Cluster] = []
    for key, group in sorted(buckets.items()):
        loops: list[list[DesignRecord]] = []
        for rec in sorted(group, key=lambda r: r.design_id):
            loop = features.clean(rec.cdrh3)
            placed = False
            for bucket in loops:
                if any(
                    identity(loop, features.clean(m.cdrh3)) >= CLUSTER_IDENTITY
                    for m in bucket
                ):
                    bucket.append(rec)
                    placed = True
                    break
            if not placed:
                loops.append([rec])
        for bucket in loops:
            cid = f"c{len(clusters) + 1}"
            rep = bucket[0]
            parent = rep.parent or "unknown parent"
            clusters.append(
                Cluster(
                    cid=cid,
                    members=bucket,
                    hypothesis=(
                        f"{rep.track or 'unassigned'} track, {parent} scaffold, "
                        f"CDRH3 family {features.clean(rep.cdrh3)[:14] or '?'} "
                        f"({len(bucket)} design{'s' if len(bucket) != 1 else ''})"
                    ),
                )
            )
    for c in clusters:
        for m in c.members:
            m.cluster = c.cid
    return clusters


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def _near_duplicate(a: DesignRecord, b: DesignRecord) -> bool:
    """True when two picks are the same loop hypothesis.

    Cluster ids are assigned per parent and binding mode, so two 90%-identical
    loops whose epitope basis differs (one folded, one inferred) land in
    different clusters. They are still one bet: if the change that separates
    them does not matter, both fail together. Wells are checked against this
    identity directly rather than trusting the cluster id.
    """
    la, lb = features.clean(a.cdrh3), features.clean(b.cdrh3)
    return bool(la and lb) and identity(la, lb) >= CLUSTER_IDENTITY


def allocate(clusters: list[Cluster], budget: int) -> tuple[list[DesignRecord], list[str]]:
    """One slot per cluster, best cluster first, then round-robin for leftovers.

    Returns (picks, notes). The notes say out loud when we had to put two
    designs in one cluster, because that is a real reduction in how many
    independent hypotheses we are testing and it should never be invisible.
    """
    notes: list[str] = []
    ordered = sorted(clusters, key=lambda c: (-c.best_score, c.cid))
    picks: list[DesignRecord] = []
    taken: dict[str, int] = {}
    skipped: list[str] = []

    # Pass 1: the best design from each distinct cluster. A pick that is a near
    # copy of one already in the basket is skipped even if its cluster id
    # differs -- the cluster id is a prediction, the loop identity is a fact.
    for c in ordered:
        if len(picks) >= budget:
            break
        b = c.best
        if b is None:
            continue
        if any(_near_duplicate(b, p) for p in picks):
            skipped.append(b.design_id)
            continue
        picks.append(b)
        taken[c.cid] = 1

    if skipped:
        notes.append(
            f"{len(skipped)} near-identical loop(s) skipped as separate "
            f"hypotheses despite a separate cluster id: {', '.join(skipped)}. "
            f"At >={CLUSTER_IDENTITY:.0%} CDRH3 identity they are one bet."
        )

    if len(picks) < budget:
        if len(ordered) < budget:
            notes.append(
                f"only {len(ordered)} distinct cluster(s) survived gating for {budget} "
                "slots — the shortlist tests fewer independent hypotheses than it has "
                "wells, so some picks share a failure mode. Ask Ruhit for more diverse "
                "candidates before accepting this."
            )
        # Pass 2: deepen the strongest clusters, in score order. Similarity is
        # allowed here only because the alternative is an empty well.
        pool = []
        for c in ordered:
            for m in sorted(
                c.members,
                key=lambda r: (-(r.joint_score if r.joint_score is not None else -1), r.design_id),
            ):
                if m not in picks:
                    pool.append((c.cid, m))
        pool.sort(
            key=lambda t: (
                -(round(t[1].joint_score, 4) if t[1].joint_score is not None else -1),
                is_borderline(t[1]),
                t[1].design_id,
            )
        )
        for cid, m in pool:
            if len(picks) >= budget:
                break
            picks.append(m)
            taken[cid] = taken.get(cid, 0) + 1

    for cid, n in taken.items():
        if n > 1:
            notes.append(f"cluster {cid} holds {n} of our {budget} slots — correlated bet")

    return picks[:budget], notes


# ---------------------------------------------------------------------------
# The dossier
# ---------------------------------------------------------------------------


def _kill_criterion(rec: DesignRecord) -> str:
    """The measurement that would prove this design wrong.

    Stated per design and per its own weakest axis, because "it might not bind"
    is not a kill criterion — it is a shrug. A kill criterion names the assay,
    the direction and the consequence.
    """
    weak = weakest_axis(rec)
    if weak is None:
        return "UNSET — no axis scored, so nothing about this design is falsifiable yet"
    axis, val = weak
    if axis == "epitope":
        if (rec.track or "") == "de_novo":
            return (
                "Fails if it loses the competitive-binding assay against trastuzumab: "
                "a de novo binder off the domain IV epitope cannot be S-tier at any affinity. "
                f"Predicted P(competes) {val:.2f} — this is the axis we expect to lose on."
            )
        return (
            "Fails if competitive binding shows it no longer displaces trastuzumab, "
            f"i.e. the CDR changes moved the paratope off the epitope (P {val:.2f})."
        )
    if axis == "binding":
        return (
            f"Fails if SPR K_D comes back above trastuzumab's (predicted P {val:.2f}). "
            "This is the expected failure: the <70% CDRH3 rule forced us to change an "
            "affinity-matured loop, and that is more likely to cost affinity than add it."
        )
    return (
        f"Fails if the thermal melt is at or below trastuzumab's T_m (predicted P {val:.2f}) — "
        "which would mean the framework and loop changes cost more stability than they bought."
    )


def _write_dossier(rec: DesignRecord, cluster_obj: Cluster | None, rank: int, budget: int) -> None:
    ev = rec.axis_evidence or {}
    lines: list[str] = []

    js = rec.joint_score
    if js is not None:
        lines.append(
            f"Joint P(S-tier) {js:.3f} = binding {rec.axes['binding']:.2f} x "
            f"epitope {rec.axes['epitope']:.2f} x stability {rec.axes['stability']:.2f}, "
            "each against a trastuzumab baseline of 0.50 on every axis."
        )
    for axis in AXES:
        reason = (ev.get(axis) or {}).get("reason")
        if reason:
            lines.append(f"{axis.capitalize()}: {reason}")

    if cluster_obj is not None:
        others = len(cluster_obj.members) - 1
        lines.append(
            f"Represents cluster {cluster_obj.cid} — {cluster_obj.hypothesis}"
            + (
                f". Chosen over {others} sibling{'s' if others != 1 else ''} sharing this "
                "hypothesis, so a failure here costs us one idea, not the shortlist."
                if others
                else ". A hypothesis no other design in the shortlist tests."
            )
        )

    strongest = max(
        ((a, rec.axes[a]) for a in AXES if rec.axes.get(a) is not None),
        key=lambda kv: kv[1],
        default=None,
    )
    if strongest:
        lines.append(
            f"On the list because its strongest axis is {strongest[0]} ({strongest[1]:.2f}) "
            f"and it clears every entry gate."
        )

    if is_borderline(rec):
        lines.append(
            "Novelty borderline: exactly 2 substitutions from the nearest provided "
            "sequence. It passes the filter as Ruhit measured it, but the project "
            "wording reads as 'more than 2', so this pick is contingent on that "
            "reading. Confirm with an Apheris mentor before submitting."
        )

    conf = (ev.get("confidence_policy") or {})
    if conf and not conf.get("calibrated", True):
        lines.append(
            "Structure confidence contributed nothing positive to this score: the cutoff "
            "is not yet calibrated against shuffled non-cognate pairs (computational, not "
            "SPR-measured), so high confidence is ignored by policy rather than trusted."
        )

    rec.rationale = lines
    rec.kill_criterion = _kill_criterion(rec)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit(records: list[DesignRecord], budget: int = 4) -> dict:
    """Facts about the shortlist that someone has to look at before 18:00.

    Exposed as a function rather than printed from here so Mahamoodoul's report
    renderer and Ansarul's CLI can both read it without this stage deciding how
    it is displayed.
    """
    picked = sorted([r for r in records if r.selected], key=lambda r: r.rank or 999)
    tracks: dict[str, int] = {}
    for r in picked:
        tracks[r.track or "unassigned"] = tracks.get(r.track or "unassigned", 0) + 1

    unverified_abguard = [
        r.design_id
        for r in picked
        if ((r.gates.checks or {}).get("abguard") or {}).get("status") != "pass"
    ]

    # The novelty-distance reading is a judgment call, not a measurement, so the
    # output has to state which one this shortlist obeys and prove it obeys it.
    # Ruhit's gate (SUBMITTABLE_DISTANCE) is what enforces the strict reading and
    # it is the right place for it — this is the check that it worked, derived
    # from the records rather than from the constant. Reading the constant would
    # only restate the intent; a judge is entitled to see the outcome. It is also
    # the one thing that still catches a lenient verdict carried in from a future
    # generation export, which is exactly how the first three attempts at this
    # filter silently did nothing.
    # Checked against each pick's MEASURED distance, not against is_borderline().
    # Under Ruhit's gate a distance-2 design fails outright and is never flagged
    # borderline, so is_borderline() is now always False on a real run and a
    # check built on it would pass vacuously — which is the same shape of mistake
    # as the tiebreaker that started this.
    too_close: list[str] = []
    undecided: list[str] = []
    for r in picked:
        nov = (r.gates.checks or {}).get("novelty") or {}
        d = nov.get("min_substitutions_from_any_provided")
        if d is None:
            undecided.append(r.design_id)
        elif int(d) < SUBMITTABLE_DISTANCE and not nov.get("min_substitutions_is_capped_at"):
            # A capped value means "at least this", so it cannot be too close.
            too_close.append(f"{r.design_id} (d={d})")

    # The designs the strict reading cost us, counted for the pitch rather than
    # inferred on stage: at distance 2, and failing nothing else.
    priced_out = [
        r
        for r in records
        if not r.is_baseline
        and not r.gates.passed
        and ((r.gates.checks or {}).get("novelty") or {}).get(
            "min_substitutions_from_any_provided"
        )
        == 2
        and len(r.gates.failed_rules) == 1
        and "novelty" in r.gates.failed_rules[0]
    ]

    out: dict = {
        "n_selected": len(picked),
        "budget": budget,
        "clusters_represented": sorted({r.cluster for r in picked if r.cluster}),
        "tracks": tracks,
        "joint_scores": {r.design_id: r.joint_score for r in picked},
        "submittable_distance": SUBMITTABLE_DISTANCE,
        "novelty_distance_verified": not too_close and not undecided,
        "picks_too_close": too_close,
        "picks_without_measured_distance": undecided,
        "designs_priced_out_by_strict_reading": len(priced_out),
        "submission_ready": (
            not unverified_abguard
            and len(picked) == budget
            and not too_close
            and not undecided
        ),
    }

    blockers: list[str] = []
    if too_close:
        blockers.append(
            f"{len(too_close)} pick(s) are closer than {SUBMITTABLE_DISTANCE} "
            f"substitutions to a provided sequence ({', '.join(too_close)}). The team "
            "took the strict reading of 'more than 2' at 12:43, so either the gate is "
            "not enforcing it or a lenient verdict was carried in from the generation "
            "export — which is how the first three attempts at this filter silently "
            "did nothing. Do not submit this shortlist."
        )
    if undecided:
        blockers.append(
            f"{len(undecided)} pick(s) have no measured distance to the provided set "
            f"({', '.join(undecided)}). Unmeasured is not the same as far enough, and "
            "a design nobody can place cannot go in the ranked list."
        )
    if unverified_abguard:
        blockers.append(
            f"{len(unverified_abguard)} of the shortlist have no abguard pass "
            f"({', '.join(unverified_abguard)}). The hard rule is that every design in "
            "the ranked list went through abguard — run this on the VM before submitting."
        )
    if len(picked) < budget:
        blockers.append(f"only {len(picked)} designs selected for {budget} wells")
    if len(tracks) == 1 and picked:
        only = next(iter(tracks))
        blockers.append(
            f"all {len(picked)} picks are in the {only} track. That is defensible — "
            "epitope competition is near-free there — but it must be a decision we "
            "made, not one we discovered. Confirm it is deliberate."
        )
    if any(r.joint_score is None for r in picked):
        blockers.append("some picks have an unscored axis, so the ranking is not fully evidence-based")

    out["blockers"] = blockers
    return out


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------


def run(records: list[DesignRecord], budget: int = 4, **kwargs) -> list[DesignRecord]:
    for rec in records:
        rec.joint_score = joint_score(rec)
        rec.selected = False
        rec.rank = None

    eligible = [r for r in records if r.gates.passed and not r.is_baseline]
    clusters = cluster(eligible)
    by_cid = {c.cid: c for c in clusters}

    scored = [r for r in eligible if r.joint_score is not None]
    if scored:
        picks, notes = allocate(clusters, budget)
        stub = False
    else:
        # Nothing is scored yet: keep the pipeline producing a complete result,
        # but every record says the choice carries no scientific meaning.
        picks = sorted(eligible, key=lambda r: r.design_id)[:budget]
        notes = []
        stub = True

    for i, rec in enumerate(picks, start=1):
        rec.selected = True
        rec.rank = i
        if stub:
            rec.rationale = [STUB_RATIONALE]
            rec.kill_criterion = "UNSET — no hypothesis behind this pick yet"
        else:
            _write_dossier(rec, by_cid.get(rec.cluster or ""), i, budget)
        rec.note("portfolio", f"selected rank {i}/{budget}")

    report = audit(records, budget)
    for note in notes + report["blockers"]:
        for rec in picks:
            rec.note("portfolio", f"audit: {note}")
            break  # once per run, not once per design

    return records
