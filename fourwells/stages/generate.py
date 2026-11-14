"""Generation — OWNER: Ruhit.

Candidates come from Apheris Foundry: RFD4-Proteina redesigns trastuzumab's CDRH3
against HER2 domain IV, a folding model refolds the result, and refold-score says
whether the folding model agrees with the design.

That pipeline needs an H100 and 15 GB of Docker images, so it does not run on a
judge's laptop. This stage therefore has three paths, in order of preference:

1. **replay** (the default) — read batches committed under `data/generated/`. These
   are real Foundry designs with their real refold metrics, exported from the VM by
   `scripts/export_batch.py`. Offline, deterministic, under a second.
2. **live** — run Foundry over Docker, for use on the VM. `live=True`.
3. **stub** — random CDRH3 substitutions, only if no batch is committed and Docker
   is unavailable. Every record is flagged `is_stub=True` so nothing downstream can
   mistake it for a design.

The baseline travels the identical path. `trastuzumab` is emitted as an ordinary
record carrying its own refold metrics, so every axis has a reference row — one
per folding model, because the scores are not comparable across models.

Generation is deliberately thin: it supplies candidates and the evidence, and
makes no ranking decisions. Those belong to the gate and scoring stages.

What each record carries, and which stage reads it:

    axes evidence             read by        what it is
    novelty                   gates          the challenge filter against all
                                             525,063 provided CDRH3s
    confidence                score          an ipTM-scale number, ONLY from a
                                             model whose baseline leaves headroom
                                             (see CONFIDENCE_MODEL_PREFERENCE)
    epitope_contacts          score          HER2 residues within 4.5 A of the
                                             binder in the refolded complex
    refold, refold_by_model   score/report   raw per-model fold metrics
    construct                 report         the orderable VH-(G4S)3-VL scFv

Three of those exist because the stage was computing them and nothing was reading
them: the key the consumer expects and the key the producer wrote did not match.
If you add evidence here, grep for the key in the stage meant to consume it before
assuming it arrived.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

from ..schema import DesignRecord
from ..targets import ReferenceAntibody, Target

AA = "ACDEFGHIKLMNPQRSTVWY"

BATCH_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "generated"

# The CDRH3 sits between these two framework anchors in the trastuzumab VH:
#   ...LRAEDTAV-YYCSR-[WGGDGFYAMD]-YWGQGT-LVTVSS
# Only the loop between them is designed, so this recovers it whatever its length.
CDRH3_PREFIX = "YYCSR"
CDRH3_SUFFIX = "YWGQGT"

# The stub spans the novelty boundary (>=4 of 10 positions changed) so the gate
# stage sees both passing and failing records on its very first run.
_MUTATION_COUNTS = [1, 2, 4, 5, 6, 7]


# --------------------------------------------------------------------------- #
# sequence helpers
# --------------------------------------------------------------------------- #

def extract_cdrh3(vh: str) -> str | None:
    """Pull the designed loop out of a full VH by its flanking framework.

    Returns None rather than guessing if either anchor is missing, so a design we
    cannot parse is dropped loudly instead of scored on a wrong loop.
    """
    if not vh:
        return None
    i = vh.find(CDRH3_PREFIX)
    if i < 0:
        return None
    start = i + len(CDRH3_PREFIX)
    # rfind: the suffix is terminal framework, so the last match is the real one
    # even in the unlikely case that the designed loop contains it too.
    j = vh.rfind(CDRH3_SUFFIX)
    if j <= start:
        return None
    return vh[start:j]


def hamming(a: str, b: str) -> int | None:
    """Substitutions between two equal-length loops; None if lengths differ."""
    if a is None or b is None or len(a) != len(b):
        return None
    return sum(1 for x, y in zip(a, b) if x != y)


def _identity(a: str, b: str) -> float | None:
    d = hamming(a, b)
    if d is None:
        return None
    return round(1.0 - d / len(a), 4)


# A design has to be expressed to be measured at all, and abguard checks the
# combined VH+VL length against 250. The parent pair is 227 aa, so a standard
# (G4S)3 linker leaves 242 -- inside the limit with room to spare. Emitting the
# construct here means the order sheet quotes a sequence someone can actually
# synthesise, rather than two chains and an assumption.
SCFV_LINKER = "GGGGS" * 3
ABGUARD_LENGTH_LIMIT = 250


def _scfv_construct(vh: str, vl: str) -> dict:
    """The submittable scFv, VH-(G4S)3-VL, with its length check."""
    seq = f"{vh}{SCFV_LINKER}{vl}"
    return {
        "format": "scfv",
        "orientation": "VH-linker-VL",
        "linker": SCFV_LINKER,
        "sequence": seq,
        "length": len(seq),
        "vh_plus_vl_length": len(vh) + len(vl),
        "abguard_length_limit": ABGUARD_LENGTH_LIMIT,
        "length_ok": len(vh) + len(vl) <= ABGUARD_LENGTH_LIMIT,
        "_note": (
            "abguard's 250 aa limit is stated as combined VH + VL, so the check is "
            "on vh_plus_vl_length. If it is enforced on the whole construct the "
            "linker counts too; both numbers are here so either reading is covered."
        ),
    }


def _splice(vh: str, old_loop: str, new_loop: str) -> str:
    """Put a new loop into a VH between the framework anchors."""
    i = vh.find(CDRH3_PREFIX)
    j = vh.rfind(CDRH3_SUFFIX)
    if i < 0 or j <= i:
        return vh.replace(old_loop, new_loop) if old_loop in vh else vh + new_loop
    return vh[: i + len(CDRH3_PREFIX)] + new_loop + vh[j:]


# --------------------------------------------------------------------------- #
# path 1: replay committed Foundry batches
# --------------------------------------------------------------------------- #

# Folding models whose interface confidence is worth feeding to the binding axis,
# best first. Boltz-2 is deliberately absent: measured on ~8,100 VHH-antigen pairs
# that do NOT bind, it gives 94.3% of them ipTM >= 0.7 (median 0.88 against 0.91
# for real pairs), and it scores trastuzumab itself 0.960 -- 0.04 from the ceiling,
# so every design clamps to "no contribution" and the number ranks nothing.
# Protenix v2 puts the same parent at 0.676 and designs land either side of it, so
# calibrate.adjustment() can actually discriminate on that scale.
CONFIDENCE_MODEL_PREFERENCE = ("protenix-v2", "of3ob", "of3p2", "protenix-v1", "mol1-base")


def _confidence_for_scoring(row: dict, refold: dict) -> dict:
    """The structure-confidence number the binding axis should see, if any.

    calibrate.adjustment() expects an ipTM-scale value against a cutoff. Handing
    it a saturated metric is worse than handing it nothing, so we only populate
    `iptm` from a model whose baseline leaves headroom, and record the rest as
    context rather than as the signal.
    """
    by_model = row.get("refold_by_model") or {}
    if not by_model and refold.get("model"):
        by_model = {refold["model"]: refold}

    chosen = next((m for m in CONFIDENCE_MODEL_PREFERENCE if m in by_model), None)
    out: dict = {
        "_models_present": sorted(by_model),
        "_iptm_by_model": {
            m: v.get("iptm") for m, v in sorted(by_model.items()) if v.get("iptm") is not None
        },
    }
    if refold.get("min_ipae") is not None:
        out["min_ipae"] = refold["min_ipae"]
        out["min_ipae_model"] = refold.get("model")
    if refold.get("binder_plddt") is not None:
        out["binder_plddt"] = refold["binder_plddt"]

    if chosen and by_model[chosen].get("iptm") is not None:
        out["iptm"] = by_model[chosen]["iptm"]
        out["iptm_model"] = chosen
        out["_why"] = (
            f"ipTM taken from {chosen}, not Boltz-2. Boltz-2 scores the parent 0.960 "
            "and 94.3% of measured non-binders above 0.7, so on that scale every "
            "design clamps to no contribution."
        )
    else:
        out["_why"] = (
            "no ipTM offered to the binding axis: the only refold we have is from a "
            "model whose baseline is saturated (parent 0.960), so the number cannot "
            "discriminate. min_ipae and binder_plddt are recorded as context."
        )
    return out


def _batch_files(batch_dir: Path) -> list[Path]:
    if not batch_dir.is_dir():
        return []
    return sorted(p for p in batch_dir.glob("*.jsonl") if p.is_file())


# Every committed batch was generated against HER2. Replaying them for a different
# target would hand back anti-HER2 antibodies with a dossier asserting they bind
# where trastuzumab binds -- confidently wrong, and the blind run on an unseen
# target is exactly what the execution score checks.
DEFAULT_BATCH_TARGET_ALIASES = ("p04626", "her2", "erbb2")


def _batch_targets(path: Path) -> set[str]:
    """Which targets a batch file may be replayed for, from its provenance."""
    prov = path.with_suffix("").with_suffix(".provenance.json")
    if not prov.exists():
        prov = path.parent / (path.stem + ".provenance.json")
    aliases: set[str] = set()
    if prov.exists():
        try:
            blob = json.loads(prov.read_text())
        except (OSError, ValueError):
            blob = {}
        for key in ("target", "target_aliases"):
            val = blob.get(key)
            if isinstance(val, str):
                aliases.add(val.strip().lower())
            elif isinstance(val, (list, tuple)):
                aliases.update(str(v).strip().lower() for v in val)
    if not aliases:
        aliases.update(DEFAULT_BATCH_TARGET_ALIASES)
    return {a for a in aliases if a}


def _target_matches(target: Target, aliases: set[str]) -> bool:
    ident = (getattr(target, "identifier", "") or "").strip().lower()
    if ident and ident in aliases:
        return True
    meta = getattr(target, "meta", None) or {}
    for key in ("uniprot", "name", "gene"):
        v = str(meta.get(key, "")).strip().lower()
        if v and v in aliases:
            return True
    return False


def _record_from_row(row: dict, ref: ReferenceAntibody) -> DesignRecord | None:
    """Turn one exported Foundry design into a DesignRecord."""
    vh = (row.get("vh") or row.get("binder_sequence") or "").strip().upper()
    cdrh3 = (row.get("cdrh3") or extract_cdrh3(vh) or "").strip().upper() or None
    if not vh or not cdrh3:
        return None

    parent_loop = ref.cdrh3
    muts = hamming(cdrh3, parent_loop)

    rec = DesignRecord(
        design_id=row["design_id"],
        sequence=vh,
        track=row.get("track", "optimisation"),
        format=row.get("format", "scfv"),
        parent=row.get("parent", ref.name),
        generator=row.get("generator"),
        cdrh3=cdrh3,
        cdrh3_identity_to_tras=_identity(cdrh3, parent_loop),
        cdrh3_mutations_from_tras=muts,
    )

    # Refold evidence. This is the generator's honest signal about its own output:
    # whether a folding model, given only the sequence, recovers the designed
    # complex. The scoring stage uses it as a FEATURE, never as the score --
    # Boltz-2 ipTM in particular barely separates real binders from shuffled
    # non-binding pairs (94.3% of known non-binders clear 0.7), so a high ipTM
    # here means much less than it looks like.
    refold = row.get("refold") or {}
    if refold:
        rec.axis_evidence["refold"] = refold
        conf = _confidence_for_scoring(row, refold)
        if conf:
            rec.axis_evidence["confidence"] = conf

    # Structural epitope evidence, read off the refolded complex. score.py caps
    # the epitope axis without this and asks for it by name.
    if row.get("epitope_contacts"):
        rec.axis_evidence["epitope_contacts"] = row["epitope_contacts"]
        rec.axis_evidence["epitope_contacts_meta"] = {
            "source_model": row.get("epitope_contacts_source"),
            "cutoff_angstrom": 4.5,
            "_validated": (
                "The same method on the parent's own refold recovers 557-561, "
                "570-573 and 593-603 -- the annotated trastuzumab epitope -- so "
                "the measurement and the annotation agree."
            ),
        }
        if row.get("epitope_contacts_by_model"):
            rec.axis_evidence["epitope_contacts_by_model"] = row["epitope_contacts_by_model"]

    design_metrics = row.get("design_metrics") or {}
    if design_metrics:
        rec.axis_evidence["design"] = design_metrics

    # The challenge filter as computed against all 525,063 provided CDRH3s. The
    # gate stage owns the decision; this is the evidence it needs, and it is also
    # what makes `n` pick eligible designs rather than arbitrary ones.
    novelty = row.get("novelty") or {}
    if novelty:
        rec.axis_evidence["novelty"] = novelty
        if novelty.get("identity_to_parent") is not None:
            rec.cdrh3_identity_to_tras = novelty["identity_to_parent"]

    if row.get("vl"):
        rec.axis_evidence["vl"] = row["vl"]
        rec.axis_evidence["construct"] = _scfv_construct(vh, row["vl"])

    src = row.get("batch") or "foundry"
    if muts is None:
        rec.note("generate", f"{src}: CDRH3 {cdrh3} ({len(cdrh3)} aa), length differs from parent")
    else:
        rec.note("generate", f"{src}: CDRH3 {cdrh3}, {muts} substitutions from the parent loop")
    if refold:
        bits = ", ".join(
            f"{k}={v}" for k, v in refold.items() if k in ("model", "min_ipae", "iptm", "binder_plddt")
        )
        if bits:
            rec.note("generate", f"refold {bits}")
    return rec


def _replay(
    batch_dir: Path, ref: ReferenceAntibody, target: Target | None = None
) -> tuple[list[DesignRecord], list[str]]:
    records: list[DesignRecord] = []
    sources: list[str] = []
    seen: set[str] = set()
    for path in _batch_files(batch_dir):
        if target is not None and not _target_matches(target, _batch_targets(path)):
            sources.append(f"{path.name} (skipped: generated against another target)")
            continue
        n_before = len(records)
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = _record_from_row(json.loads(line), ref)
            if rec is None or rec.design_id in seen:
                continue
            seen.add(rec.design_id)
            records.append(rec)
        if len(records) > n_before:
            sources.append(f"{path.name} ({len(records) - n_before})")
    return records, sources


# --------------------------------------------------------------------------- #
# path 2: live Foundry over Docker (VM only)
# --------------------------------------------------------------------------- #

def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _live(
    n: int, seed: int, weight: str, work_dir: Path, tsr_k: str | None = None
) -> list[dict]:
    """Run design -> refold-prepare -> fold -> refold-score, then export rows.

    Returns exported rows in the same shape as a committed batch, so the replay
    path and the live path produce identical records.
    """
    script = work_dir / "scripts" / "run_pipeline.sh"
    if not script.exists():
        raise FileNotFoundError(
            f"{script} not found. The live path runs on the hackathon VM, where "
            "~/ruhit/gen holds the Foundry scripts. Use the committed batches "
            "instead (the default), or pass work_dir."
        )
    env_bits = [f"WEIGHT={weight}", f"N={n}", f"SEED={seed}"]
    if tsr_k:
        env_bits.append(f"TSRK={tsr_k}")
    out = work_dir / "runs" / f"live-{weight}-s{seed}"
    env_bits.append(f"OUT=runs/live-{weight}-s{seed}")
    subprocess.run(
        ["env", *env_bits, "bash", str(script), "all"],
        cwd=work_dir, check=True,
    )
    export = out / "designs.jsonl"
    if not export.exists():
        raise RuntimeError(f"live run finished but {export} is missing")
    return [json.loads(l) for l in export.read_text().splitlines() if l.strip()]


# --------------------------------------------------------------------------- #
# path 3: stub
# --------------------------------------------------------------------------- #

def _mutate(seq: str, n: int, rng: random.Random) -> str:
    positions = rng.sample(range(len(seq)), min(n, len(seq)))
    out = list(seq)
    for p in positions:
        out[p] = rng.choice([a for a in AA if a != out[p]])
    return "".join(out)


def _stub_candidates(n: int, ref: ReferenceAntibody, rng: random.Random) -> list[DesignRecord]:
    parent_cdrh3 = ref.cdrh3 or "WGGDGFYAMD"
    vh = ref.vh or ""
    records = []
    for i in range(n):
        muts = _MUTATION_COUNTS[i % len(_MUTATION_COUNTS)]
        cdrh3 = _mutate(parent_cdrh3, muts, rng)
        seq = _splice(vh, parent_cdrh3, cdrh3) if vh else cdrh3
        rec = DesignRecord(
            design_id=f"stub-{i:03d}",
            sequence=seq or cdrh3,
            track="optimisation",
            format="scfv",
            parent=ref.name,
            generator="STUB:cdrh3-random-mutation",
            cdrh3=cdrh3,
            cdrh3_identity_to_tras=_identity(cdrh3, parent_cdrh3),
            cdrh3_mutations_from_tras=hamming(cdrh3, parent_cdrh3),
            is_stub=True,
        )
        rec.note("generate", f"stub: {muts} random CDRH3 substitutions, NOT a design")
        records.append(rec)
    return records


# --------------------------------------------------------------------------- #
# the baseline row
# --------------------------------------------------------------------------- #

def _baseline(ref: ReferenceAntibody, batch_dir: Path) -> DesignRecord | None:
    """Trastuzumab as an ordinary record, with its real refold metrics if we have them.

    Do not special-case this downstream. Its whole purpose is to travel the
    identical path so that every number has a reference.
    """
    if not ref.vh:
        return None
    rec = DesignRecord(
        design_id="trastuzumab",
        sequence=ref.vh,
        track="optimisation",
        format="scfv",
        parent=ref.name,
        generator="reference",
        cdrh3=ref.cdrh3,
        cdrh3_identity_to_tras=1.0,
        cdrh3_mutations_from_tras=0,
    )
    # One baseline per folding model. Confidence scores are NOT comparable across
    # models: the same complex, same template, same seed scores ipTM 0.960 under
    # Boltz-2 and 0.676 under Protenix v2. Boltz-2 puts this known binder 0.04
    # from the ceiling, so nothing can beat it and the metric ranks nothing --
    # across 25 refolded designs none exceeded it. Protenix leaves room in both
    # directions. So a design is only ever "above baseline" with respect to a
    # named model, and every consumer needs the whole set.
    baselines: dict[str, dict] = {}
    for path in sorted(batch_dir.glob("baseline*.json")):
        try:
            blob = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        refold = blob.get("refold") or {}
        model = refold.get("model") or path.stem.replace("baseline-", "") or "unknown"
        if refold:
            baselines[model] = refold
        for k in ("measured_kd_nM", "measured_kd_median_nM"):
            if blob.get(k) is not None:
                rec.axis_evidence.setdefault("measured", {})[k] = blob[k]

    if baselines:
        rec.axis_evidence["refold_by_model"] = baselines
        # Keep the single-model key for anything already reading it.
        primary = "boltz2" if "boltz2" in baselines else sorted(baselines)[0]
        rec.axis_evidence["refold"] = baselines[primary]
        bits = ", ".join(
            f"{m} iptm={v.get('iptm')}" for m, v in sorted(baselines.items())
        )
        rec.note("generate", f"baseline refolded through the identical path: {bits}")
        if len(baselines) > 1:
            rec.note(
                "generate",
                "compare a design only against the baseline for its own folding model",
            )
    else:
        rec.note(
            "generate",
            "reference baseline, same path as every design (no refold metrics committed yet)",
        )
    if ref.vl:
        rec.axis_evidence["vl"] = ref.vl
    return rec


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def run(
    target: Target,
    ref: ReferenceAntibody,
    n: int = 24,
    seed: int = 0,
    cache=None,
    **kwargs,
) -> list[DesignRecord]:
    """Return candidate designs for `target`, to be scored against `ref`.

    kwargs:
      live      run Foundry over Docker instead of replaying (VM only)
      weight    RFD4-Proteina weight for the live path
      tsr_k     sequenceTsrK for the live path (1 most varied, 4 default)
      work_dir  where the Foundry scripts live, for the live path
      batch_dir override the committed batch directory
    """
    batch_dir = Path(kwargs.get("batch_dir") or BATCH_DIR)
    records: list[DesignRecord] = []
    how = "stub"

    if kwargs.get("live"):
        if not _docker_available():
            raise RuntimeError(
                "live=True but Docker is not available. Generation needs the "
                "hackathon VM; drop live= to replay the committed batches."
            )
        rows = _live(
            n=n,
            seed=seed,
            weight=kwargs.get("weight", "her2-novel-2026-11-09"),
            work_dir=Path(kwargs.get("work_dir", ".")),
            tsr_k=kwargs.get("tsr_k"),
        )
        records = [r for r in (_record_from_row(x, ref) for x in rows) if r]
        how = "live"
    else:
        records, sources = _replay(batch_dir, ref, target)
        if records:
            how = "replay"

    if not records:
        # Last resort. The pipeline must still run end to end for the judges even
        # with no batch committed and no GPU, but it has to be obvious that these
        # are not designs.
        records = _stub_candidates(n, ref, random.Random(seed))
        how = "stub"
        if how == "stub" and _batch_files(batch_dir):
            # Batches exist but none was generated against this target. Say so,
            # rather than replaying anti-HER2 designs for something else.
            for rec in records:
                rec.note(
                    "generate",
                    f"no committed batch was generated against {target.identifier!r} — "
                    "falling back to the stub rather than replaying designs made for "
                    "another target",
                )

    # Deterministic subset when more designs are committed than asked for.
    #
    # Any choice here is a selection, so make the least opinionated one that does
    # not waste the budget: designs that can actually be submitted come first.
    # That is an eligibility fact, not a ranking judgment -- a design failing the
    # challenge filter can never reach the lab, and the plan says to filter before
    # ranking. Ordering within each group is by design_id, so the pick is
    # reproducible on every machine and carries no quality bias that might look
    # like us pre-ranking ahead of the ranking stage.
    #
    # A few ineligible designs are kept at the tail on purpose, so the gate stage
    # still has material and its rejection-reason distribution stays informative.
    # Pass --candidates 100 to score the whole batch; scoring 100 takes under a
    # second, so there is little reason not to.
    if how != "stub" and n and len(records) > n:
        def eligible(rec) -> bool:
            return bool((rec.axis_evidence.get("novelty") or {}).get("passes_challenge_filter"))

        def batch_of(rec) -> str:
            return rec.design_id.split("-", 1)[0]

        # Spread the subset across batches, round-robin, instead of taking the
        # lexicographic head. Each batch is a different hypothesis, and sorting by
        # design_id alone handed every slot to whichever batch sorts first --
        # "multicdr" before "optA" -- so a default run saw one hypothesis and the
        # portfolio step had nothing to choose between.
        groups: dict[str, list] = {}
        for rec in sorted(records, key=lambda r: (not eligible(r), r.design_id)):
            groups.setdefault(batch_of(rec), []).append(rec)

        ordered: list[DesignRecord] = []
        while any(groups.values()) and len(ordered) < len(records):
            for key in sorted(groups):
                if groups[key]:
                    ordered.append(groups[key].pop(0))

        keep = [r for r in ordered if eligible(r)][: max(1, n - 1) if n > 1 else n]
        # Keep one ineligible design so the gate's rejection-reason report stays
        # informative rather than silently empty.
        rejected = [r for r in ordered if not eligible(r)][: n - len(keep)]
        records = keep + rejected

    for rec in records:
        rec.note("generate", f"source: {how}")

    baseline = _baseline(ref, batch_dir)
    if baseline is not None:
        baseline.note("generate", f"source: {how}")
        records.append(baseline)

    return records
