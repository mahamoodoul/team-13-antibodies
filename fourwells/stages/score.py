"""Axis prediction — OWNER: Rizve. Layer 2.

Three predictors, one per property the lab actually measures, each returning a
number in [0, 1] meaning **"probability this design beats the reference on this
axis"**, each carrying a one-line reason a judge could read aloud.

The construction that makes every number interpretable: each axis is a logistic
over a weighted sum of feature *deltas against the reference molecule*. The
reference therefore scores exactly 0.500 on all three axes, by construction and
not by coincidence. "0.5 = indistinguishable from trastuzumab" is literally
true, so the baseline row is a real zero point rather than a decoration.

    score = 1 / (1 + exp(-sum(w_i * (f_i(design) - f_i(reference)))))

What each axis is worth fighting for, which is the team's strategic read and is
encoded in the weights below, not just written on a slide:

  binding    hardest to beat. Trastuzumab is a heavily affinity-matured
             therapeutic; the <70% CDRH3 identity rule forces us to change at
             least 4 of its 11 CDRH3 residues, and the expected effect of
             4 unselected changes to a matured loop is negative. The prior is
             therefore pessimistic in mutation count on purpose. Chasing this
             axis alone is how a team ends the day with zero S-tier designs.
  epitope    near-free in the optimisation track (a trastuzumab variant binds
             where trastuzumab binds) and fatal in de novo (a binder that hits
             HER2 anywhere else cannot out-compete trastuzumab, so it can never
             be S-tier however tightly it binds).
  stability  the most beatable axis, so it gets the most feature work.

ON STRUCTURE CONFIDENCE, which is the thing we are most trying not to get
wrong: ipTM/pLDDT enter as *features with modest weight*, never as the score,
and until the cutoff is calibrated against shuffled non-cognate pairs (computational negatives, not SPR-measured) a
high confidence is not allowed to RAISE a binding score at all — only a low one
may lower it. That asymmetry is the whole lesson of the shuffled non-cognate
pairs that still score ipTM >= 0.7: high confidence is not evidence of binding, while low
confidence is still weak evidence against it. See `fourwells.calibrate`.

A BIAS TO SAY OUT LOUD BEFORE A JUDGE FINDS IT: because the binding prior is
dominated by mutation count and substitution severity, it systematically
prefers designs sitting just under the 70% identity ceiling — the least-changed
loop that is still legal. That is a defensible position (minimum necessary
perturbation of a matured interface) but it is a *prior*, not a finding, and it
is exactly the bias the 524k fit exists to overturn: those data contain real
CDRH3 variants measured to bind better than the parent, so a fitted model can
credit a specific aggressive change that this prior can only penalise. Until
the fit lands, our binding column should be read as "how much are we
perturbing a molecule that already works", not as predicted affinity.

WHAT IS A PRIOR AND WHAT IS FITTED: every weight here is hand-set from
antibody-engineering direction-of-effect, not fitted, and `axis_evidence`
labels each axis `prior` or `fitted` so no one reads these as measurements. The
binding axis swaps itself for a model fitted on the 524k FACS-labelled CDRH3
variants the moment that file lands — same target, same parent, already
labelled. `load_binding_model()` is the seam; nothing else changes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .. import features
from ..align import align
from ..calibrate import confidence_policy
from ..schema import AXES, DesignRecord
from ..targets import REFERENCE_DIR, ReferenceAntibody, Target

MODEL_DIR = REFERENCE_DIR.parent / "models"
BINDING_MODEL_FILE = MODEL_DIR / "binding_cdrh3.json"

# --------------------------------------------------------------------------
# Weights. Hand-set priors: the SIGN of each is a direction-of-effect claim
# from antibody engineering, the MAGNITUDE is a judgement about relative
# importance. None of this is fitted. Keep them here so the whole scoring
# policy is one screen a mentor can argue with.
# --------------------------------------------------------------------------

W_BINDING = {
    # A matured loop changed at random gets worse. This term is why our
    # binding scores sit below 0.5 for aggressive redesigns, which is the
    # honest prior for a parent that is already a licensed therapeutic.
    "cdrh3_mutations": -0.14,
    # Aromatics and the Y/W/S/G/D/N/T/R set dominate antibody paratopes; their
    # enrichment is one of the most reproducible observations in the
    # structural literature, so losing them is a real penalty.
    "aromatic_frac": 2.6,
    "paratope_frac": 1.8,
    # A large side-chain volume swing at an interface position is disruptive
    # whatever it swaps to.
    "mean_volume_change": -0.015,
    # Loop length changes repack the whole interface.
    "cdrh3_len_delta_abs": -0.10,
    # Structure confidence, deliberately small, and clamped by the policy in
    # fourwells.calibrate so it cannot push a score up while uncalibrated.
    "confidence": 0.9,
    # Refold disagreement: a folding model given only the sequence must
    # recover the designed complex. If it does not, the design score was
    # describing a structure that does not exist.
    "refold_disagreement": -1.2,
}

W_STABILITY = {
    # Framework change is nearly all downside: trastuzumab's framework is a
    # humanised, heavily engineered scaffold and we are not improving it by
    # accident. CDR change is required by the rules and is scored elsewhere,
    # which is why framework and loops are separated in features.py.
    "framework_substitutions": -0.11,
    # Surface hydrophobic patches are the classic aggregation nucleus.
    "patch_burden": -0.30,
    # Distance of pI from neutral buffer: aggregation peaks at the pI, so
    # moving AWAY from formulation pH is a stability win.
    "pi_distance": 0.28,
    # Net charge magnitude keeps molecules apart in solution.
    "abs_net_charge": 0.045,
    # A longer CDRH3 costs conformational entropy and is a known Tm liability.
    "cdrh3_len_delta": -0.09,
    # Breaking the conserved intra-domain disulfide is not a small effect.
    "disulfide_broken": -2.0,
    # Proline rigidifies, glycine does the opposite.
    "loop_proline": 0.12,
    "loop_glycine": -0.08,
    # Packing quality from the refolded structure, when Ruhit exports it.
    "plddt": 0.025,
}

W_EPITOPE = {
    # Paratope retention is the whole axis in the optimisation track.
    "paratope_retention": 3.0,
    # Demonstrated contact with the target's annotated epitope residues is the
    # whole axis in de novo.
    "epitope_overlap": 3.5,
}

# A de novo design with no structural evidence of hitting the right epitope is
# not a coin flip, it is a long shot: HER2's ECD is large and domain IV is a
# small part of it. Capping rather than guessing is the point.
DE_NOVO_UNVERIFIED_EPITOPE = 0.10

# Trastuzumab's own refold (boltz2, data/generated/baseline.json), measured the
# same way as every design against the annotated 1N8Z epitope: 14 of 20 residues.
# No real molecule touches all of them, so the axis must score a design against
# the parent, not against 1.0. Rerun: scripts/epitope_control.py.
PARENT_EPITOPE_OVERLAP = 0.70


def _logistic(z: float) -> float:
    if z < -40:
        return 0.0
    if z > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def _frac(seq: str, alphabet) -> float:
    seq = features.clean(seq)
    return sum(1 for a in seq if a in alphabet) / len(seq) if seq else 0.0


def load_binding_model(path: Path | None = None) -> dict | None:
    """The 524k-fitted CDRH3 binding model, when Mahamoodoul has fitted it.

    Expected shape — a position-specific scoring matrix over the reference loop
    plus an intercept, which is what a gradient-boosted or logistic fit on
    FACS affinity classes reduces to for ranking purposes:

        {"kind": "pssm", "intercept": float,
         "weights": {"<0-based loop position>": {"<aa>": float}},
         "fit_note": "...", "heldout": {"split": "by mutation count", ...}}

    Hold the test set out BY MUTATION COUNT, not at random: a random split puts
    single-mutant near-neighbours of training rows in the test set and reports
    an enrichment number that will not survive contact with real designs.
    """
    path = path or BINDING_MODEL_FILE
    if not path.exists():
        return None
    return json.loads(path.read_text())


@dataclass
class ReferenceFeatures:
    """The reference molecule's features, computed once per run."""

    construct: str
    heavy: str
    cdrh3: str
    framework: str
    cdrs: dict
    dev: features.Developability
    dev_heavy: features.Developability | None = None
    fr4_offset: int = 0

    def dev_for(self, n_chains: int) -> tuple[features.Developability, str]:
        """The reference readout to compare a design of `n_chains` against.

        Like-for-like or the axis measures the wrong thing. Now that the
        reference VL is verified, the reference construct is a paired scFv —
        so comparing a single-chain design against it would charge that design
        for the absence of a light chain it was never supposed to have, and
        every VHH would read as destabilised. Chain count picks the comparator
        and `axis_evidence` records which one was used.
        """
        if n_chains < 2 and self.dev_heavy is not None:
            return self.dev_heavy, "reference heavy chain only (design is single-chain)"
        return self.dev, "full reference construct"

    @classmethod
    def build(cls, ref: ReferenceAntibody) -> ReferenceFeatures:
        vh = features.clean(ref.vh)
        vl = features.clean(ref.vl)
        construct = vh + ("GGGGSGGGGSGGGGS" + vl if vl else "")
        # The loop-boundary convention the reference is written in; see
        # features.detect_fr4_offset. Every CDR extraction below uses it so a
        # design's loops are cut the same way the reference's were.
        offset = features.detect_fr4_offset(vh, ref.cdrh3)
        return cls(
            construct=construct,
            heavy=vh,
            cdrh3=features.clean(ref.cdrh3) or (features.extract_cdrh3(vh, offset) or ""),
            framework=features.framework_of(vh, offset),
            cdrs=features.extract_cdrs(vh, offset),
            dev=features.developability(construct),
            dev_heavy=features.developability(vh),
            fr4_offset=offset,
        )


# --------------------------------------------------------------------------
# Axis 1 — binding
# --------------------------------------------------------------------------


def score_binding(
    rec: DesignRecord,
    rf: ReferenceFeatures,
    model: dict | None,
    policy,
    pool_median_ipae: float | None = None,
) -> tuple[float | None, dict, str]:
    cdrh3 = features.clean(rec.cdrh3)
    if not cdrh3 or not rf.cdrh3:
        return None, {"status": "no CDRH3 to score"}, "CDRH3 unavailable — axis left null"

    aln = align(cdrh3, rf.cdrh3)
    ev: dict = {"basis": "prior", "cdrh3": cdrh3, "reference_cdrh3": rf.cdrh3}

    if model and model.get("kind") == "pssm":
        # Fitted path: score the loop under the 524k model, and express it
        # relative to the reference loop's own score so 0.5 still means "ties
        # trastuzumab" and the axis keeps its meaning.
        z = float(model.get("intercept", 0.0))
        weights = model.get("weights", {})
        for i, aa in enumerate(cdrh3):
            z += float(weights.get(str(i), {}).get(aa, 0.0))
        z_ref = float(model.get("intercept", 0.0))
        for i, aa in enumerate(rf.cdrh3):
            z_ref += float(weights.get(str(i), {}).get(aa, 0.0))
        ev.update(
            basis="fitted:524k-facs",
            model_score=round(z, 4),
            reference_score=round(z_ref, 4),
            fit_note=model.get("fit_note"),
            heldout=model.get("heldout"),
        )
        score = _logistic(z - z_ref)
        reason = (
            f"CDRH3 scores {z - z_ref:+.2f} against trastuzumab's own loop under the "
            f"model fitted on 524k FACS-labelled variants of this exact parent"
        )
        return score, ev, reason

    # Prior path: direction-of-effect features on the loop.
    muts = aln.substitutions()
    len_delta = len(cdrh3) - len(rf.cdrh3)
    vol_change = 0.0
    n_sub = 0
    for x, y in zip(aln.a_aligned, aln.b_aligned):
        if x != y and x != "-" and y != "-":
            vol_change += abs(features.VOLUME.get(x, 140) - features.VOLUME.get(y, 140))
            n_sub += 1
    mean_vol = vol_change / n_sub if n_sub else 0.0

    f = {
        "cdrh3_mutations": muts,
        "aromatic_frac": _frac(cdrh3, features.AROMATIC) - _frac(rf.cdrh3, features.AROMATIC),
        "paratope_frac": _frac(cdrh3, features.PARATOPE_FAVOURED)
        - _frac(rf.cdrh3, features.PARATOPE_FAVOURED),
        "mean_volume_change": mean_vol,
        "cdrh3_len_delta_abs": abs(len_delta),
    }

    # Structure evidence, if Ruhit's refold metrics travelled with the record.
    #
    # The two metrics are NOT interchangeable and the baseline file is explicit
    # about why: min_ipae is refold-score comparing a design to its own refold,
    # so the parent has no design to compare against and structurally has no
    # min_ipae. ipTM/pTM/pLDDT do have a parent value. So:
    #
    #   ipTM      -> baseline-relative confidence, under the policy clamp
    #   min_ipae  -> design-to-design refold agreement, centred on the pool
    #
    # Centring min_ipae on the pool median rather than using it absolutely is
    # what keeps the baseline honest: a design must not be penalised against
    # the parent on a metric the parent cannot have. The baseline contributes 0
    # here, which is exactly the median design.
    conf = rec.axis_evidence.get("confidence") or {}
    raw_conf = conf.get("iptm")
    if raw_conf is not None:
        adj, conf_note = policy.adjustment(float(raw_conf))
        f["confidence"] = adj
        ev["confidence_input"] = {"metric": "iptm", "value": raw_conf}
        ev["confidence_note"] = conf_note
        if (conf.get("model") or "").startswith("boltz"):
            ev["confidence_model_caveat"] = (
                "Boltz-2: 94.3% of ~8,100 pairs measured NOT to bind score ipTM >= 0.7 "
                "(median 0.88) against 99% of cognate pairs (median 0.91). A design "
                "above the parent on ipTM has not been shown to bind better, which is "
                "why this enters as a clamped feature and never as the score."
            )

    disagree = conf.get("refold_disagreement")
    if conf.get("min_ipae") is not None and pool_median_ipae is not None:
        # Lower min_ipae is better agreement, so worse-than-median is positive
        # and gets penalised by W_BINDING["refold_disagreement"].
        f["refold_disagreement"] = float(conf["min_ipae"]) - pool_median_ipae
        ev["refold_agreement"] = {
            "min_ipae": conf["min_ipae"],
            "pool_median": round(pool_median_ipae, 4),
            "basis": "design-to-design within one model; the parent has no min_ipae",
        }
    elif disagree is not None:
        f["refold_disagreement"] = float(disagree)

    z = sum(W_BINDING[k] * v for k, v in f.items() if k in W_BINDING)
    ev["features"] = {k: round(v, 4) for k, v in f.items()}
    ev["z"] = round(z, 4)
    ev["weights"] = "W_BINDING in stages/score.py — hand-set prior, not fitted"
    ev["awaiting"] = "model fitted on the 524k FACS variants (data/models/binding_cdrh3.json)"

    score = _logistic(z)
    reason = (
        f"{muts} of {len(rf.cdrh3)} CDRH3 positions changed against an affinity-matured "
        f"parent{f' (loop {len_delta:+d} aa)' if len_delta else ''}; "
        f"paratope-residue content {f['paratope_frac']:+.0%}, aromatics {f['aromatic_frac']:+.0%}"
    )
    return score, ev, reason


# --------------------------------------------------------------------------
# Axis 2 — epitope retention
# --------------------------------------------------------------------------


def score_epitope(
    rec: DesignRecord, rf: ReferenceFeatures, target: Target
) -> tuple[float | None, dict, str]:
    """Does this design still compete with trastuzumab for ITS epitope?

    Two different questions depending on the track, which is the asymmetry most
    teams will miss:

      optimisation  a trastuzumab variant binds where trastuzumab binds, so
                    this reduces to paratope conservation and the axis is
                    nearly free. S-tier there is effectively a two-axis problem.
      de novo       the axis that kills you. Trastuzumab binds HER2 domain IV;
                    a novel binder that hits anywhere else cannot out-compete
                    it in the competition assay and can never be S-tier, no
                    matter how tightly it binds. We require structural evidence
                    of domain IV contact and cap the axis without it.
    """
    track = (rec.track or "").lower()
    ev: dict = {"basis": "prior", "track": track}

    contacts = rec.axis_evidence.get("epitope_contacts")
    if contacts:
        # Structural evidence present: measure overlap with the target's
        # annotated epitope. This path is track-agnostic — evidence beats
        # inference for optimisation designs too.
        annotated = set()
        for span in target.epitope_residues or []:
            if "-" in str(span):
                lo, hi = str(span).split("-")[:2]
                try:
                    annotated.update(range(int(lo), int(hi) + 1))
                except ValueError:
                    continue
            else:
                try:
                    annotated.add(int(span))
                except ValueError:
                    continue
        got = {int(c) for c in contacts if str(c).lstrip("-").isdigit()}
        overlap = len(got & annotated) / len(annotated) if annotated else 0.0
        ev.update(basis="structural", n_contacts=len(got), epitope_overlap=round(overlap, 3))
        if target.epitope_note:
            ev["numbering_caution"] = target.epitope_note
        # Matching the parent's measured overlap ties the reference (0.5), the
        # same value the parent gets on the prior path, so bases are comparable.
        score = _logistic(W_EPITOPE["epitope_overlap"] * (overlap - PARENT_EPITOPE_OVERLAP))
        return score, ev, f"predicted complex covers {overlap:.0%} of the annotated domain IV epitope"

    if track == "de_novo":
        ev.update(
            basis="capped",
            why="no predicted complex on this record — domain IV contact unverified",
            needs="epitope_contacts in axis_evidence, from Ruhit's refold of the complex",
        )
        return (
            DE_NOVO_UNVERIFIED_EPITOPE,
            ev,
            "de novo with no structural evidence it hits domain IV — capped, not guessed: "
            "a binder elsewhere on HER2 can never out-compete trastuzumab",
        )

    # Optimisation track, no structure: paratope conservation by alignment onto
    # the reference's CDR positions. The CDR loops ARE the paratope to a first
    # approximation; a contact-resolved paratope from 1N8Z would be better and
    # is Mahamoodoul's AMASS task, which lands in axis_evidence as above.
    retained = 0
    total = 0
    per_loop = {}
    design_cdrs = features.extract_cdrs(
        features.chains_of(rec.sequence)[0] if rec.sequence else "", rf.fr4_offset
    )
    for loop in ("h1", "h2", "h3"):
        ref_loop = features.clean(rf.cdrs.get(loop) or "")
        if loop == "h3":
            got_loop = features.clean(rec.cdrh3) or features.clean(design_cdrs.get(loop) or "")
        else:
            got_loop = features.clean(design_cdrs.get(loop) or "")
        if not ref_loop:
            continue
        if not got_loop:
            per_loop[loop] = None
            continue
        a = align(got_loop, ref_loop)
        kept = sum(1 for x, y in zip(a.a_aligned, a.b_aligned) if x == y and x != "-")
        retained += kept
        total += len(ref_loop)
        per_loop[loop] = round(kept / len(ref_loop), 3)

    if not total:
        return None, {"status": "no CDR loops resolved"}, "paratope unresolved — axis left null"

    retention = retained / total
    ev.update(
        paratope_retention=round(retention, 3),
        per_loop=per_loop,
        note="CDR-position conservation as a paratope proxy; a contact-resolved "
        "paratope from 1N8Z would replace this",
    )
    score = _logistic(W_EPITOPE["paratope_retention"] * (retention - 1.0))
    return score, ev, (
        f"optimisation-track variant retaining {retention:.0%} of trastuzumab's CDR paratope "
        "— it binds where trastuzumab binds, so this axis is close to free"
    )


# --------------------------------------------------------------------------
# Axis 3 — thermostability
# --------------------------------------------------------------------------


def score_stability(rec: DesignRecord, rf: ReferenceFeatures) -> tuple[float | None, dict, str]:
    """The most beatable axis, so it gets the most features.

    Trastuzumab's affinity is heavily optimised; its thermostability is not the
    thing it was optimised for. A design clearly better here and merely
    non-inferior on binding is a cheap A-tier, and A-tier beats the zero we get
    from chasing affinity alone.
    """
    seq = features.clean(rec.sequence)
    if not seq:
        return None, {"status": "no sequence"}, "no sequence — axis left null"

    chains = features.chains_of(seq)
    heavy = chains[0]
    dev = features.developability(seq)
    ref_dev, comparator = rf.dev_for(len(chains))
    fw = features.framework_of(heavy, rf.fr4_offset)
    cdrh3 = features.clean(rec.cdrh3) or ""

    fw_aln = align(fw, rf.framework) if rf.framework else None
    fw_subs = fw_aln.substitutions() if fw_aln else 0

    loops = "".join(v or "" for v in features.extract_cdrs(heavy, rf.fr4_offset).values())
    ref_loops = "".join(v or "" for v in rf.cdrs.values())

    def loop_frac(s: str, aa: str) -> float:
        return s.count(aa) / len(s) if s else 0.0

    f = {
        "framework_substitutions": fw_subs,
        "patch_burden": dev.patch_burden - ref_dev.patch_burden,
        "pi_distance": abs(dev.pi - 7.4) - abs(ref_dev.pi - 7.4),
        "abs_net_charge": abs(dev.net_charge) - abs(ref_dev.net_charge),
        "cdrh3_len_delta": len(cdrh3) - len(rf.cdrh3) if cdrh3 and rf.cdrh3 else 0,
        "disulfide_broken": 1.0 if dev.unpaired_cys_chains else 0.0,
        "loop_proline": (loop_frac(loops, "P") - loop_frac(ref_loops, "P")) * 10,
        "loop_glycine": (loop_frac(loops, "G") - loop_frac(ref_loops, "G")) * 10,
    }

    plddt = (rec.axis_evidence.get("confidence") or {}).get("binder_plddt")
    if plddt is not None:
        ref_plddt = (rec.axis_evidence.get("confidence") or {}).get("reference_binder_plddt")
        f["plddt"] = float(plddt) - float(ref_plddt) if ref_plddt is not None else 0.0

    z = sum(W_STABILITY[k] * v for k, v in f.items() if k in W_STABILITY)
    ev = {
        "basis": "prior",
        "features": {k: round(float(v), 4) for k, v in f.items()},
        "z": round(z, 4),
        "developability": dev.to_dict(),
        "compared_against": comparator,
        "weights": "W_STABILITY in stages/score.py — hand-set prior, not fitted",
        "germline_reversion": "NOT COMPUTED — needs a germline V-gene set. Framework "
        "deviation from the reference is the implemented proxy, which is the "
        "conservative direction (it penalises change without crediting reversion).",
        "awaiting": "AF2-IG packing quality (JapanFold, antibody-specific) if Ruhit gets it up",
    }

    drivers = sorted(
        ((k, W_STABILITY[k] * v) for k, v in f.items() if k in W_STABILITY and v),
        key=lambda kv: -abs(kv[1]),
    )[:2]
    driver_txt = ", ".join(f"{k} {c:+.2f}" for k, c in drivers) or "no deviation from baseline"
    return _logistic(z), ev, (
        f"{fw_subs} framework substitutions, hydrophobic-patch burden "
        f"{f['patch_burden']:+.2f} and pI {dev.pi:.1f} vs {ref_dev.pi:.1f}; "
        f"dominant terms {driver_txt}"
    )


# --------------------------------------------------------------------------
# Stage entry point
# --------------------------------------------------------------------------


def run(
    records: list[DesignRecord],
    target: Target,
    ref: ReferenceAntibody,
    cache=None,
    **kwargs,
) -> list[DesignRecord]:
    rf = ReferenceFeatures.build(ref)
    model = load_binding_model()
    policy = confidence_policy()

    # min_ipae is only meaningful design-to-design, so centre it on this pool.
    # Computed once per run, which keeps it deterministic for a fixed pool.
    ipaes = sorted(
        float((r.axis_evidence.get("confidence") or {})["min_ipae"])
        for r in records
        if (r.axis_evidence.get("confidence") or {}).get("min_ipae") is not None
    )
    pool_median_ipae = (
        (ipaes[len(ipaes) // 2] if len(ipaes) % 2 else
         (ipaes[len(ipaes) // 2 - 1] + ipaes[len(ipaes) // 2]) / 2)
        if ipaes else None
    )

    if not rf.cdrh3:
        for rec in records:
            rec.axis_evidence["status"] = "reference CDRH3 unset — no axis can be scored"
            rec.note("score", "skipped: no reference loop")
        return records

    for rec in records:
        # The reference travels the identical path. Its deltas are all zero, so
        # it lands on 0.500 on every axis without being special-cased — which
        # is exactly why 0.5 means "ties trastuzumab" everywhere else.
        b, b_ev, b_why = score_binding(rec, rf, model, policy, pool_median_ipae)
        e, e_ev, e_why = score_epitope(rec, rf, target)
        s, s_ev, s_why = score_stability(rec, rf)

        rec.axes["binding"] = None if b is None else round(b, 4)
        rec.axes["epitope"] = None if e is None else round(e, 4)
        rec.axes["stability"] = None if s is None else round(s, 4)

        rec.axis_evidence["binding"] = {**b_ev, "reason": b_why}
        rec.axis_evidence["epitope"] = {**e_ev, "reason": e_why}
        rec.axis_evidence["stability"] = {**s_ev, "reason": s_why}
        rec.axis_evidence["baseline"] = {a: 0.5 for a in AXES}
        rec.axis_evidence["interpretation"] = (
            "each axis is P(beats the reference); 0.5 ties it exactly"
        )
        rec.axis_evidence["confidence_policy"] = policy.describe()
        rec.axis_evidence.pop("status", None)

        scored = sum(1 for a in AXES if rec.axes.get(a) is not None)
        rec.note("score", f"{scored}/3 axes scored" + ("" if model else " (binding on prior)"))

    return records
