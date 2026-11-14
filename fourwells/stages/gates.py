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

    if total > MAX_LENGTH:
        failed.append(f"length {total} > {MAX_LENGTH}")

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

    # Novelty distance against the provided set.
    if provided:
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
            f"provided-antibody set absent ({PROVIDED_AB_FILE.name}) — the "
            "novelty distance rules are UNCHECKED, not passed"
        )

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
        if provided and checks["min_mutations_from_provided"] <= MIN_POINT_MUTATIONS:
            failed.append(
                f"only {checks['min_mutations_from_provided']} point mutations from "
                f"{checks['nearest_provided']}, needs > {MIN_POINT_MUTATIONS}"
            )
    elif track == "de_novo":
        if muts < MIN_CDRH3_MUTATIONS:
            failed.append(f"{muts} CDRH3 mutations from reference, needs >= {MIN_CDRH3_MUTATIONS}")
        if provided and checks["max_identity_to_provided"] >= MAX_KNOWN_IDENTITY:
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


def abguard_check(rec: DesignRecord, failed: list[str], checks: dict, abguard: str = "abguard") -> None:
    """Run the organisers' checker. It is authoritative, including on track.

    Not on a laptop. When it is missing we record `NOT RUN` and the portfolio
    stage treats the shortlist as not submission-ready — the alternative, a
    design that reads as passed because the authority never saw it, is the
    failure mode the hard rule exists to prevent.
    """
    if shutil.which(abguard) is None:
        checks["abguard"] = {
            "status": "NOT RUN",
            "why": f"{abguard!r} not on PATH (it lives on the team VM)",
        }
        return

    payload = {
        "design_id": rec.design_id,
        "sequence": rec.sequence,
        "format": rec.format,
        "track": rec.track,
    }
    from .. import calllog

    log = calllog.active()
    try:
        with log.call("abguard", "check", stage="gates", request=payload,
                      design_id=rec.design_id) as slot:
            proc = subprocess.run(
                [abguard, "check", "--json", "-"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=120,
            )
            slot["response"] = {
                "returncode": proc.returncode,
                "stdout": proc.stdout[:2000],
                "stderr": proc.stderr[:2000],
            }
            if proc.returncode != 0:
                slot["status"] = calllog.ERROR
    except subprocess.TimeoutExpired:
        checks["abguard"] = {"status": "ERROR", "why": "timeout after 120s"}
        failed.append("abguard timed out")
        return
    except OSError as e:
        checks["abguard"] = {"status": "ERROR", "why": str(e)}
        failed.append(f"abguard could not be run: {e}")
        return

    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # A build that does not speak JSON: a zero exit is a pass, anything
        # else is a failure whose reason we still name from stderr.
        status = "pass" if proc.returncode == 0 else "fail"
        checks["abguard"] = {
            "status": status,
            "raw": (proc.stdout or proc.stderr).strip()[:300],
            "note": "non-JSON output; verdict taken from exit code",
        }
        if proc.returncode != 0:
            failed.append(f"abguard rejected: {proc.stderr.strip()[:120] or 'exit ' + str(proc.returncode)}")
        return

    checks["abguard"] = {"status": "pass" if out.get("passed", True) else "fail", "raw": out}

    # abguard assigns the track. We take its word over the generator's label.
    assigned = out.get("track")
    if assigned and assigned != rec.track:
        checks["abguard_reassigned_track"] = {"from": rec.track, "to": assigned}
        rec.note("gates", f"abguard reassigned track {rec.track} -> {assigned}")
        rec.track = assigned

    conf = out.get("numbering_confidence")
    if conf is not None:
        checks["numbering_confidence"] = conf
        if conf < MIN_NUMBERING_CONFIDENCE:
            failed.append(f"immunum numbering confidence {conf} < {MIN_NUMBERING_CONFIDENCE}")

    if not out.get("passed", True):
        for rule in out.get("failed_rules") or ["unspecified"]:
            failed.append(f"abguard: {rule}")


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
        dropped = [f for f in failed if "identity" in f or "mutation" in f]
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
