"""Entry gates and the expression pre-screen — OWNER: Rizve. Layer 1.

Nothing enters the ranking without coming through here, and every rejection
carries a named reason. The reason distribution is an output in its own right:
a spike in one rule means generation has drifted, and Ruhit can retune rather
than keep producing candidates we throw away.

Three tiers, in cost order, and the order matters because we only have one
H100 and one afternoon:

  cheap_checks()     pure python, microseconds, no network. Length, chain-aware
                     cysteine parity, residue alphabet, format.
  track_checks()     the entry arithmetic: CDRH3 identity and point-mutation
                     distance, under a real alignment.
  abguard_check()    the organisers' tool. The authority, and the only thing
                     that actually assigns the track. Called last, and only on
                     designs that survived the two free tiers.

WHAT CHANGED FROM THE FIRST VERSION, because it decided submissions:
identity used to be computed only when the design's CDRH3 was the same length
as trastuzumab's, and returned None otherwise. A None skipped the ceiling check
completely, so any design with an insertion or deletion in CDRH3 passed the
<70% rule without being measured against it. RFD4 changes loop length freely.
That is now a real Needleman-Wunsch alignment in `fourwells.align` and there is
no path through this file that leaves the identity rule unevaluated.

The gate that is NOT satisfied locally: abguard is on the team VM, not on a
laptop. When it has not run, `checks["abguard"]["status"]` says so and the
portfolio stage refuses to call the shortlist submission-ready. A clean pass
here is a precondition for entering the ranking, not a final check at 17:50.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from .. import features
from ..align import align
from ..schema import DesignRecord
from ..targets import REFERENCE_DIR, ReferenceAntibody

MAX_LENGTH = 250
MAX_CDRH3_IDENTITY = 0.70  # strictly under, optimisation track
MAX_KNOWN_IDENTITY = 0.70  # strictly under, de novo track
MIN_POINT_MUTATIONS = 2  # strictly more than, optimisation track
MIN_CDRH3_MUTATIONS = 2  # at least this many, de novo track
MIN_NUMBERING_CONFIDENCE = 0.1

VALID_FORMATS = ("vhh", "scfv", "fab")

# Provided antibodies the novelty rules are measured against. Not in the repo
# yet — Ruhit unpacks them from the challenge bundle. Until then the distance
# rules report `unchecked` rather than a reassuring number, because a design
# that quietly skipped a novelty rule is the one that gets rejected at
# submission.
PROVIDED_AB_FILE = REFERENCE_DIR / "provided_antibodies.json"

# Every unique CDRH3 in the provided data, gzipped. This is the set the
# challenge novelty rule is actually measured against, and it IS committed, so
# the rule runs on a laptop with no VM and no network.
UNIVERSE_FILE = REFERENCE_DIR / "provided_cdrh3_universe.txt.gz"
AA_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"

_UNIVERSE: set[str] | None = None


def load_universe(path: Path | None = None) -> set[str]:
    """The 525k provided CDRH3s, loaded once and held."""
    global _UNIVERSE
    if _UNIVERSE is not None:
        return _UNIVERSE
    path = path or UNIVERSE_FILE
    if not path.exists():
        _UNIVERSE = set()
        return _UNIVERSE
    import gzip

    with gzip.open(path, "rt") as fh:
        _UNIVERSE = {line.strip().upper() for line in fh if line.strip()}
    return _UNIVERSE


def _carried_novelty(rec: DesignRecord, checks: dict) -> dict:
    """Normalise a novelty verdict from wherever the generator put it.

    Generation exports booleans under `axis_evidence["novelty"]`; this stage
    speaks in `verdict`. Translating here rather than asking either side to
    change means neither lane has to touch the other's file mid-afternoon.
    """
    raw = (
        (checks.get("novelty") or {})
        or ((rec.gates.checks or {}).get("novelty") or {})
        or ((rec.axis_evidence or {}).get("novelty") or {})
    )
    if not raw:
        return {}
    out = dict(raw)
    if "verdict" not in out:
        # Read passes_novelty, NOT passes_challenge_filter. The latter is a
        # composite of novelty AND the identity ceiling, so a design rejected
        # purely for sitting at 3 substitutions from the parent was being
        # reported as a novelty failure with a novelty reason attached. The
        # design was still correctly rejected — the identity rule catches it two
        # branches down — but the rejection-reason distribution is what tells
        # Ruhit whether generation is drifting, and it was blaming the wrong rule.
        passes = out.get("passes_novelty")
        if passes is None:
            passes = out.get("passes_challenge_filter")
        if passes is True:
            out["verdict"] = "pass"
        elif passes is False:
            out["verdict"] = "fail"
            if out.get("in_provided_data"):
                out.setdefault("reason", "CDRH3 appears verbatim in the provided data")
            else:
                n = out.get("min_substitutions_from_any_provided")
                out.setdefault(
                    "reason", f"only {n} substitution(s) from a provided sequence"
                )
        else:
            out["verdict"] = "undecidable"
            out.setdefault("reason", "generator reported no novelty verdict")
    return out


def _is_capped(nov: dict) -> bool:
    """Whether a novelty block's distance is a ceiling rather than a value."""
    return bool(
        nov.get("min_substitutions_is_capped_at_2")
        or nov.get("min_substitutions_is_capped_at")
    )


# The smallest distance from a provided sequence we will SUBMIT, as opposed to
# the smallest the filter appears to accept. These differ at exactly 2, and the
# gap is the whole shortlist.
#
# Ruhit's measured behaviour of the real filter: rejects only at <= 1. The
# wording -- "more than 2 point mutations from any provided antibody" -- plainly
# reads as 3. No mentor settled it in three hours. Ansarul and Rizve both called
# it strict at 12:43 on the asymmetry: the lenient reading gains ~2% of joint
# score, and if it is wrong it costs the entire submission, after the pitch.
#
# Set to 2 and re-run to go back; a distance-2 design keeps its exact measured
# distance in the record either way, so nothing needs regenerating.
#
# NOTE FOR RIZVE, whose file this is: this is the two-line change you described
# to Ansarul as "it just needs to become a hard filter rather than a
# preference". Revert if you want it done differently -- the measurement and
# the decision are not mine, only the wiring.
SUBMITTABLE_DISTANCE = 3


def novelty_from_universe(
    cdrh3: str, universe: set[str] | None = None, max_distance: int = 3
) -> dict:
    """Exact distance to the nearest provided sequence, capped at `max_distance`.

    The rule rejects a loop that is in the provided data or within a single
    substitution of something in it. Enumerating a 10-mer's own substitution
    neighbourhood and doing set lookups is exact and far cheaper than scanning
    525k rows per design.

    WHY THE CAP IS 3 AND NOT 2, which decided our whole shortlist. The
    generation export caps at 2, so every design that passes reports exactly
    "2", and all four of our picks came back at 2. But 2 is the one value where
    the rule's wording ("more than 2 point mutations from any provided
    antibody") and its measured behaviour (rejects only at <= 1) disagree. With
    a cap of 2 we could not tell a design that is genuinely at 2 from one at 5,
    so we could not prefer the unambiguous ones — the whole shortlist sat on an
    unsettled reading. Going one step further costs ~16k set lookups per design
    (the 2-neighbourhood) and removes the ambiguity for most of the pool.
    """
    universe = load_universe() if universe is None else universe
    if not universe:
        return {}

    cdrh3 = cdrh3.upper()
    base = {
        "in_provided_data": False,
        "source": "recomputed locally from the committed universe",
    }

    if cdrh3 in universe:
        return {
            **base,
            "verdict": "fail",
            "in_provided_data": True,
            "min_substitutions_from_any_provided": 0,
            "reason": "CDRH3 appears verbatim in the provided data",
        }

    n = len(cdrh3)
    # Distance 1.
    for i in range(n):
        orig = cdrh3[i]
        for aa in AA_ALPHABET:
            if aa == orig:
                continue
            if cdrh3[:i] + aa + cdrh3[i + 1 :] in universe:
                return {
                    **base,
                    "verdict": "fail",
                    "min_substitutions_from_any_provided": 1,
                    "reason": "one substitution from a provided sequence",
                }

    if max_distance >= 2:
        # Distance 2. ~16k lookups for a 10-mer.
        for i in range(n):
            oi = cdrh3[i]
            for ai in AA_ALPHABET:
                if ai == oi:
                    continue
                first = cdrh3[:i] + ai + cdrh3[i + 1 :]
                for j in range(i + 1, n):
                    oj = first[j]
                    for aj in AA_ALPHABET:
                        if aj == oj:
                            continue
                        if first[:j] + aj + first[j + 1 :] in universe:
                            lenient = 2 >= SUBMITTABLE_DISTANCE
                            return {
                                **base,
                                "verdict": "pass" if lenient else "fail",
                                "min_substitutions_from_any_provided": 2,
                                "borderline": lenient,
                                "reason": (
                                    "exactly 2 substitutions from a provided sequence — "
                                    "passes the filter as Ruhit measured it, but the "
                                    "project wording reads as 'more than 2'. We submit "
                                    f"only at >= {SUBMITTABLE_DISTANCE}: the lenient "
                                    "reading is worth ~2% of joint score and, if wrong, "
                                    "the whole submission"
                                ),
                            }

    return {
        **base,
        "verdict": "pass",
        "min_substitutions_from_any_provided": max_distance,
        "min_substitutions_is_capped_at": max_distance,
        "borderline": False,
        "reason": f"at least {max_distance} substitutions from every provided sequence",
    }


def load_provided_antibodies(path: Path | None = None) -> list[dict]:
    """[{name, sequence}, ...] or [] when the bundle has not landed."""
    path = path or PROVIDED_AB_FILE
    if not path.exists():
        return []
    blob = json.loads(path.read_text())
    if isinstance(blob, dict):
        blob = blob.get("antibodies", [])
    out = []
    for item in blob:
        if isinstance(item, str):
            out.append({"name": f"provided_{len(out)}", "sequence": item})
        elif item.get("sequence"):
            out.append({"name": item.get("name", f"provided_{len(out)}"), "sequence": item["sequence"]})
    return out


# ---------------------------------------------------------------------------
# Tier 1 — free, local
# ---------------------------------------------------------------------------


def cheap_checks(rec: DesignRecord, failed: list[str], checks: dict) -> None:
    seq = features.clean(rec.sequence)
    chains = features.chains_of(seq)
    total = sum(len(c) for c in chains)

    checks["length"] = total
    checks["n_chains"] = len(chains)

    if not seq:
        failed.append("empty sequence")
        return

    bad = sorted(set(seq) - features.NATURAL_AA)
    if bad:
        failed.append(f"non-natural residues: {''.join(bad)}")

    # The limit applies to the molecule we actually order, not to whichever
    # chain happens to sit in rec.sequence. Generation records the assembled
    # scFv under axis_evidence["construct"]; measuring rec.sequence instead
    # reads 120 aa for a 242 aa construct and turns an 8 aa margin into an
    # apparent 130 aa one. RFD4 varies loop length freely, so that margin is
    # the thing most likely to move.
    construct = (rec.axis_evidence or {}).get("construct") or {}
    measured, basis = total, "sequence"
    if isinstance(construct, dict):
        candidates = [
            v for v in (construct.get("length"), construct.get("vh_plus_vl_length"))
            if isinstance(v, int)
        ]
        if candidates:
            # Worst case of the two readings: abguard states the limit as
            # combined VH + VL, and whether the linker counts is unconfirmed.
            measured = max(candidates + [total])
            basis = "construct"
            checks["construct_length"] = construct.get("length")
            checks["vh_plus_vl_length"] = construct.get("vh_plus_vl_length")
    checks["length_measured"] = measured
    checks["length_basis"] = basis

    if measured > MAX_LENGTH:
        failed.append(f"length {measured} ({basis}) > {MAX_LENGTH}")

    # Per chain, not per construct: two chains each carrying one free cysteine
    # sum to an even count and would read as paired if checked in one go.
    checks["cysteines"] = seq.count("C")
    odd = [i for i, c in enumerate(chains) if features.unpaired_cysteines(c)]
    if odd:
        failed.append(f"unpaired cysteine in chain(s) {odd}")

    fmt = (rec.format or "").lower()
    if fmt not in VALID_FORMATS:
        failed.append(f"format {fmt or 'unset'!r} not one of {VALID_FORMATS}")


# ---------------------------------------------------------------------------
# Tier 2 — the entry arithmetic
# ---------------------------------------------------------------------------


def track_checks(
    rec: DesignRecord,
    ref: ReferenceAntibody,
    provided: list[dict],
    failed: list[str],
    checks: dict,
) -> None:
    """CDRH3 identity and novelty distance, under a real alignment.

    The track is assigned by abguard from identity; we do not choose it. So
    both tracks' arithmetic is computed for every design regardless of what the
    generator labelled it, and a design sitting near the 70% line is flagged
    because it could land on either side of a rule it then has to satisfy.
    """
    seq = features.clean(rec.sequence)
    chains = features.chains_of(seq)
    heavy = chains[0] if chains else seq

    # Which loop-boundary convention the reference is written in. Read off the
    # reference, not assumed: the datasets use a 10-mer where strict Kabat
    # reads 11, and under the wrong convention the parent scores 10/11 against
    # itself and every identity number here shifts with it.
    fr4_offset = features.detect_fr4_offset(ref.vh, ref.cdrh3)
    checks["fr4_offset"] = fr4_offset

    cdrh3 = features.clean(rec.cdrh3) or features.extract_cdrh3(heavy, fr4_offset)
    if cdrh3:
        rec.cdrh3 = cdrh3
    checks["cdrh3"] = cdrh3

    if not ref.cdrh3:
        checks["cdrh3_identity"] = None
        checks["cdrh3_note"] = "reference CDRH3 unset — identity rule cannot run"
        failed.append("reference CDRH3 unset, identity rule unevaluated")
        return

    if not cdrh3:
        # Do not pass a design whose CDRH3 we cannot find. The rule is phrased
        # in CDRH3 terms; an unlocatable loop is an unevaluated rule, and an
        # unevaluated rule is a rejection until immunum says otherwise.
        checks["cdrh3_identity"] = None
        checks["cdrh3_note"] = "anchors not found — defer to immunum/abguard"
        failed.append("CDRH3 not locatable from sequence anchors")
        return

    aln = align(cdrh3, ref.cdrh3)
    ident = aln.identity()
    muts = aln.substitutions()
    rec.cdrh3_identity_to_tras = round(ident, 4)
    rec.cdrh3_mutations_from_tras = muts
    checks["cdrh3_identity"] = round(ident, 4)
    checks["cdrh3_mutations"] = muts
    checks["cdrh3_alignment"] = f"{aln.a_aligned} / {aln.b_aligned}"
    checks["cdrh3_length_delta"] = len(cdrh3) - len(ref.cdrh3)

    # Novelty distance against the provided set. A verdict carried in from the
    # generation export wins: it was computed against all 525,063 provided
    # CDRH3s on the VM, which is the actual rule. Failing that we recompute it
    # here from the committed universe, so a judge's own run is checked too.
    carried = _carried_novelty(rec, checks)
    if not carried and cdrh3:
        carried = novelty_from_universe(cdrh3)
    elif carried and cdrh3 and carried.get("verdict") == "pass" and _is_capped(carried):
        # The carried verdict passes, but its distance is capped at 2 and 2 is
        # exactly the value where the rule's wording and its measured behaviour
        # disagree. Resolve it locally so the portfolio step can prefer designs
        # that are unambiguously submittable. Without this every passing design
        # reports "2" and the whole shortlist rests on an unsettled reading.
        refined = novelty_from_universe(cdrh3)
        if refined:
            carried = {
                **carried,
                **refined,
                "carried_distance_was_capped_at": carried.get(
                    "min_substitutions_from_any_provided"
                ),
            }
    if carried:
        # Enforce the submission threshold on whatever distance we ended up
        # with, carried or recomputed. This has to live here rather than in
        # either source: the carried export verdict wins above, and it was
        # computed against the export's own threshold of 2, so a distance-2
        # design arrived already stamped `passes_novelty: True` and never met
        # SUBMITTABLE_DISTANCE at all. That is why making the recompute strict
        # changed nothing -- the recompute only runs on capped records.
        #
        # A capped distance equals its cap and means "at least that", so the
        # one comparison is correct for both: an exact 2 fails, and a 3 capped
        # at 3 passes because the true distance can only be larger.
        _d = carried.get("min_substitutions_from_any_provided")
        if (
            carried.get("verdict") == "pass"
            and isinstance(_d, int)
            and _d < SUBMITTABLE_DISTANCE
        ):
            carried = {
                **carried,
                "verdict": "fail",
                "borderline": False,
                "submittable_distance": SUBMITTABLE_DISTANCE,
                "reason": (
                    f"{_d} substitutions from the nearest provided sequence. It "
                    "passes the filter as Ruhit measured it (rejects only at <= 1), "
                    "but the project wording reads as 'more than 2' and we submit "
                    f"only at >= {SUBMITTABLE_DISTANCE} — the lenient reading is "
                    "worth ~2% of joint score and, if wrong, the whole submission"
                ),
            }
        checks["novelty"] = carried
        verdict = carried.get("verdict")
        if verdict == "fail":
            failed.append(f"novelty: {carried.get('reason', 'failed the provided-sequence rule')}")
        elif verdict == "undecidable":
            # Fail closed. One lost slot in a shortlist of twenty costs less
            # than one submission the organisers throw out.
            failed.append(f"novelty undecidable: {carried.get('reason', 'see checks.novelty')}")
    elif provided:
        dists = [(align(heavy, features.clean(p["sequence"])), p["name"]) for p in provided]
        nearest_muts, nearest_name = min(
            ((a.substitutions(), n) for a, n in dists), key=lambda t: t[0]
        )
        worst_ident, worst_name = max(
            ((a.identity(), n) for a, n in dists), key=lambda t: t[0]
        )
        rec.identity_to_nearest_known = round(worst_ident, 4)
        checks["min_mutations_from_provided"] = nearest_muts
        checks["nearest_provided"] = nearest_name
        checks["max_identity_to_provided"] = round(worst_ident, 4)
        checks["most_similar_provided"] = worst_name
    else:
        checks["min_mutations_from_provided"] = None
        checks["max_identity_to_provided"] = None
        checks["provided_note"] = (
            f"provided-antibody set absent ({PROVIDED_AB_FILE.name}) and the "
            f"CDRH3 universe ({UNIVERSE_FILE.name}) unreadable — novelty "
            "UNCHECKED"
        )
        # Fail closed, the same policy as an undecidable carried verdict. This
        # branch used to write the note above and then say nothing, so every
        # design passed a rule that had never run.
        failed.append("novelty unchecked (no provided set and no universe)")

    track = (rec.track or "").lower()

    if track == "optimisation":
        # The inversion worth saying out loud: this is a floor on how much we
        # must change, not a ceiling. A conservative 1-2 point CDRH3 mutant is
        # rejected for being too close to trastuzumab. With an 11-residue loop,
        # at least 4 positions have to differ.
        if ident >= MAX_CDRH3_IDENTITY:
            need = int(len(ref.cdrh3) * (1 - MAX_CDRH3_IDENTITY)) + 1
            failed.append(
                f"CDRH3 identity {ident:.2f} >= {MAX_CDRH3_IDENTITY} "
                f"({muts} muts; needs >= {need} of {len(ref.cdrh3)})"
            )
        local_dist = checks.get("min_mutations_from_provided")
        if local_dist is not None and local_dist <= MIN_POINT_MUTATIONS:
            failed.append(
                f"only {checks['min_mutations_from_provided']} point mutations from "
                f"{checks['nearest_provided']}, needs > {MIN_POINT_MUTATIONS}"
            )
    elif track == "de_novo":
        if muts < MIN_CDRH3_MUTATIONS:
            failed.append(f"{muts} CDRH3 mutations from reference, needs >= {MIN_CDRH3_MUTATIONS}")
        local_ident = checks.get("max_identity_to_provided")
        if local_ident is not None and local_ident >= MAX_KNOWN_IDENTITY:
            failed.append(
                f"identity {checks['max_identity_to_provided']:.2f} to "
                f"{checks['most_similar_provided']} >= {MAX_KNOWN_IDENTITY} "
                "(a known binder fails novelty)"
            )
    else:
        checks["track_note"] = "track unset — abguard assigns it; both rules computed"

    if abs(ident - MAX_CDRH3_IDENTITY) < 0.05:
        checks["track_borderline"] = True


# ---------------------------------------------------------------------------
# Tier 3 — abguard, the authority
# ---------------------------------------------------------------------------


ABGUARD_VERDICTS_FILE = REFERENCE_DIR / "abguard_verdicts.json"
_VERDICTS: dict | None = None


def load_abguard_verdicts(path: Path | None = None) -> dict:
    """The recorded abguard verdicts, or {} if none have been recorded."""
    global _VERDICTS
    if path is None and _VERDICTS is not None:
        return _VERDICTS
    path = path or ABGUARD_VERDICTS_FILE
    blob = json.loads(path.read_text()) if path.exists() else {}
    if path == ABGUARD_VERDICTS_FILE:
        _VERDICTS = blob
    return blob


def _construct_sequence(rec: DesignRecord) -> str:
    """The molecule abguard was shown: the recorded construct, else the sequence.

    Same rule as report.construct_of, repeated here because report imports from
    the stages and the dependency must not run the other way.
    """
    c = (rec.axis_evidence or {}).get("construct")
    if isinstance(c, dict) and c.get("sequence"):
        return c["sequence"]
    return rec.sequence


def abguard_check(rec: DesignRecord, failed: list[str], checks: dict, **_) -> None:
    """Apply abguard's recorded verdict to this design. It is the authority.

    abguard exists only on the team VM, so it is run there by
    scripts/abguard_verdicts.py, which records one verdict per design in
    data/reference/abguard_verdicts.json. This reads that record.

    A verdict binds to the sha256 of the exact construct abguard saw. A design
    whose sequence has changed since, or that was never in the run, is `NOT RUN`
    and the portfolio stage treats the shortlist as not submission-ready. An old
    pass never vouches for a different molecule.

    (An earlier version shelled out to `abguard check --json -`. No such
    command exists; the real tool is `abguard team-validate`. That path never
    produced a verdict, and is gone rather than left to look like it works.)
    """
    import hashlib

    blob = load_abguard_verdicts()
    v = (blob.get("verdicts") or {}).get(rec.design_id)
    if not v:
        checks["abguard"] = {
            "status": "NOT RUN",
            "why": "no recorded verdict; run scripts/abguard_verdicts.py on the VM",
        }
        return

    seq = _construct_sequence(rec)
    if hashlib.sha256(seq.encode()).hexdigest() != v.get("sha256"):
        checks["abguard"] = {
            "status": "NOT RUN",
            "why": "sequence changed since abguard saw it; the recorded verdict does not apply",
        }
        return

    checks["abguard"] = {
        "status": v["status"],
        "tool": blob.get("tool"),
        "run_at": blob.get("run_at"),
        **({"reason": v["reason"]} if v.get("reason") else {}),
    }
    if v["status"] != "pass":
        failed.append(f"abguard: {v.get('reason') or 'rejected'}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def check(
    rec: DesignRecord,
    ref: ReferenceAntibody,
    provided: list[dict] | None = None,
    use_abguard: bool = True,
) -> DesignRecord:
    failed: list[str] = []
    checks: dict = {}
    provided = provided if provided is not None else load_provided_antibodies()

    cheap_checks(rec, failed, checks)
    track_checks(rec, ref, provided, failed, checks)

    # Expression screen. A design that does not express is measured on nothing
    # and scores nothing on all three axes, so it belongs in Layer 1 — but it
    # flags rather than fails, because these are sequence proxies and we have
    # no measured expression data for these constructs.
    dev = features.developability(rec.sequence)
    checks["developability"] = dev.to_dict()
    if dev.flags:
        checks["developability_flags"] = dev.flags

    # The reference molecule is a baseline row, not a submission. It fails the
    # novelty rules by construction — it *is* trastuzumab — so those are
    # dropped for it, while everything measurable is still reported. This runs
    # BEFORE the abguard decision: otherwise the baseline looks like it failed
    # a free gate and the skip reason recorded against it is a lie.
    if rec.is_baseline:
        # Novelty joins identity and mutation count here: trastuzumab's own
        # CDRH3 is necessarily verbatim in the provided data, so it fails the
        # novelty rule by construction. The baseline is a reference row rather
        # than a submission, and gating it out would leave every axis without
        # the reference it is scored against.
        dropped = [
            f for f in failed
            if "identity" in f or "mutation" in f or f.startswith("novelty")
        ]
        failed = [f for f in failed if f not in dropped]
        if dropped:
            checks["baseline_exempt_from"] = dropped

    # Only pay for the authority on designs that survived the free tiers.
    if use_abguard and not failed:
        abguard_check(rec, failed, checks)
    elif use_abguard:
        checks["abguard"] = {"status": "NOT RUN", "why": "already failed a free gate"}
    else:
        checks["abguard"] = {"status": "NOT RUN", "why": "disabled for this run"}

    rec.gates.passed = not failed
    rec.gates.failed_rules = failed
    rec.gates.checks = checks
    rec.note("gates", "pass" if not failed else f"fail: {'; '.join(failed)}")
    return rec


def run(
    records: list[DesignRecord],
    ref: ReferenceAntibody,
    use_abguard: bool = True,
    **kwargs,
) -> list[DesignRecord]:
    provided = load_provided_antibodies()
    return [check(r, ref, provided, use_abguard) for r in records]


def reason_distribution(records: list[DesignRecord]) -> Counter:
    """What is killing our designs — hand this to Ruhit.

    Keyed on the rule, not the formatted message, so counts aggregate across
    designs instead of fragmenting on the numbers embedded in each reason.
    """
    c: Counter = Counter()
    for r in records:
        if r.gates.passed:
            c["PASSED"] += 1
        for rule in r.gates.failed_rules:
            key = rule.split(":")[0].split("(")[0].strip()
            key = " ".join(key.split()[:4])
            c[key] += 1
    return c


def abguard_coverage(records: list[DesignRecord]) -> dict:
    """How many designs the authority actually saw. The hard rule is that every
    design in the ranked list went through abguard, so this is the number that
    says whether we are allowed to submit."""
    seen = Counter()
    for r in records:
        status = ((r.gates.checks or {}).get("abguard") or {}).get("status", "NOT RUN")
        seen[status] += 1
    return dict(seen)
