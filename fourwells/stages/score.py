"""Axis prediction — OWNER: Rizve.

STUB. Returns None for every axis, which is the honest answer before the
predictors exist and is explicitly a valid state in the schema. The runner
reports how many axes are still unscored rather than treating it as failure.

Three predictors go here, one per axis the lab measures, each relative to
trastuzumab so 0.5 means "indistinguishable from the baseline":

  binding    fit on the 524k FACS-labelled CDRH3 variants; hold out by mutation
             count so the test set is not a near-neighbour of training
  epitope    domain IV contact retention (residues in the target's epitope
             list). Near-free in the optimisation track; the axis that kills
             de novo designs
  stability  the most beatable axis — trastuzumab's affinity is already
             heavily optimised, its thermostability less so

Do not let a structure-confidence number become the binding score on its own.
The 454 true negatives include 21 with AF3 ipTM >= 0.7 that were measured not
to bind; rejecting those is the proof slide.
"""

from __future__ import annotations

from ..schema import AXES, DesignRecord
from ..targets import ReferenceAntibody, Target


def run(
    records: list[DesignRecord],
    target: Target,
    ref: ReferenceAntibody,
    cache=None,
    **kwargs,
) -> list[DesignRecord]:
    for rec in records:
        for axis in AXES:
            rec.axes.setdefault(axis, None)
        rec.axis_evidence.setdefault(
            "status", "no predictor wired yet — axes intentionally null"
        )
        rec.note("score", "stub: axes left null")
    return records
