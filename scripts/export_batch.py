#!/usr/bin/env python3
"""Export one Foundry design run into the batch format the pipeline replays.

Reads a run directory produced by scripts/design_batch.sh (plus refold-prepare /
fold / refold-score if those ran) and writes one JSON object per design:

  design_id, vh, vl, cdrh3, generator, track, format, seed,
  novelty {...}, design_metrics {...}, refold {...}

Sequences come from the generated CIFs, so every design is exported whether or
not it was selected for refolding. Novelty is checked against every CDRH3 in the
provided data, which is the actual challenge filter.

Usage:
  python3 -I scripts/export_batch.py runs/optA --weight her2-novel-2026-11-09 \
      --seed 1 --out runs/optA/designs.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

# Run with python3 -I, which keeps the script's directory off sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from epitope_contacts import contacts as _epitope_contacts  # noqa: E402

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}

CDRH3_PREFIX = "YYCSR"
CDRH3_SUFFIX = "YWGQGT"
PARENT_CDRH3 = "WGGDGFYAMD"
UNIVERSE = Path.home() / "data" / "tidy" / "provided_cdrh3_universe.txt"
# The committed fallback, so novelty can be recomputed off the VM. The VM is
# wiped tonight and this script outlives it.
UNIVERSE_COMMITTED = (
    Path(__file__).resolve().parent.parent
    / "data" / "reference" / "provided_cdrh3_universe.txt.gz"
)

# How far we resolve the distance to the nearest provided sequence. 3, not 2,
# because 2 is the single value where the rule's wording ("more than 2 point
# mutations from any provided antibody") and its measured behaviour (rejects
# only at <= 1) disagree. Capping at 2 made every passing design report exactly
# "2", so generation could not steer towards the unambiguous band and the whole
# shortlist sat on an unsettled reading. Matches gates.novelty_from_universe.
NOVELTY_CAP = 3

# Keep the per-design metrics that say something about the design, and drop the
# ~70 config columns that just echo the run settings.
WANTED_METRICS = {
    "hotspot_obedience.hotspot_obedience": "hotspot_obedience",
    "clash_metrics.frac_atoms_clashing_1p5A": "clash_fraction",
    "interchain_interactions.hbond_atom_pair_count_coi": "interface_hbond_pairs",
    "interchain_interactions.saltbridge_residue_pair_count_coi": "interface_saltbridges",
    "interchain_interactions.hydrophobic_atom_pair_count_coi": "interface_hydrophobic_pairs",
    "interchain_interactions.pistack_residue_pair_count_coi": "interface_pistack",
    "sequence_adherence.sequence_adherence": "sequence_adherence",
    "sequence_adherence.n_violations": "sequence_violations",
    "amino_acid_composition.n_generated_unknown_residues": "unknown_residues",
    "bond_length_metrics.bond_length.frac_unreasonable": "bond_length_unreasonable",
}

WANTED_REFOLD = {
    "model": "model", "min_ipae": "min_ipae", "iptm": "iptm", "ptm": "ptm",
    "binder_plddt": "binder_plddt", "plddt": "plddt", "binder_ptm": "binder_ptm",
    "backbone_rmsd": "backbone_rmsd", "pass": "pass", "pass_note": "pass_note",
}


def parse_cif_chains(path: Path) -> dict[str, str]:
    """Return {chain_id: one-letter sequence} from an mmCIF atom_site loop."""
    cols: list[str] = []
    in_loop = False
    seen: dict[str, dict] = {}
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("_atom_site."):
                cols.append(s.split(".", 1)[1].split()[0])
                in_loop = True
                continue
            if in_loop and (s.startswith("ATOM") or s.startswith("HETATM")):
                parts = s.split()
                if len(parts) < len(cols):
                    continue
                rec = dict(zip(cols, parts))
                chain = rec.get("auth_asym_id") or rec.get("label_asym_id")
                resnum = rec.get("auth_seq_id") or rec.get("label_seq_id")
                comp = (rec.get("label_comp_id") or rec.get("auth_comp_id") or "").upper()
                if chain is None or resnum is None or not comp:
                    continue
                seen.setdefault(chain, {})
                # keyed by residue number so each residue is counted once
                if resnum not in seen[chain]:
                    seen[chain][resnum] = comp
            elif in_loop and s.startswith("#"):
                in_loop = False
    out = {}
    for chain, residues in seen.items():
        ordered = sorted(residues.items(), key=lambda kv: int(kv[0]) if kv[0].lstrip("-").isdigit() else 0)
        out[chain] = "".join(THREE_TO_ONE.get(c, "X") for _, c in ordered)
    return out


def extract_cdrh3(vh: str) -> str | None:
    """Pull the designed loop out of a VH by its conserved flanks.

    The loop sits between the conserved cysteine motif and the FR4 tryptophan:

        trastuzumab   ...AV-YYC-SR-[WGGDGFYAMD]-Y-WGQGT-LVTVSS
        adalimumab fw ...AV-YYC-AK-[EKRISFAGNSYPTYAMD]-Y-WGQGT-LVTVSS

    Anchoring on the literal "YYCSR" broke on 30 of 100 designs whose framework
    reads YYCAK rather than YYCAR -- that position borders the designed region, so
    it is not framework we can assume. Anchoring on YYC plus two residues, and on
    the terminal WGQGT from the right, locates the loop in all of them.

    Returns None rather than guessing if either flank is missing, so a design we
    cannot parse is dropped loudly instead of scored on the wrong loop.
    """
    if not vh:
        return None
    i = vh.find("YYC")
    if i < 0:
        return None
    start = i + 3 + 2  # YYC, then the two residues before the loop
    j = vh.rfind("YWGQGT")
    if j < 0:
        j = vh.rfind("WGQGT")
    if j <= start:
        return None
    return vh[start:j]


def load_universe() -> set[str]:
    """Every provided CDRH3, from the VM copy or the committed gzip."""
    if UNIVERSE.exists():
        text = UNIVERSE.read_text()
    elif UNIVERSE_COMMITTED.exists():
        import gzip

        with gzip.open(UNIVERSE_COMMITTED, "rt") as fh:
            text = fh.read()
    else:
        print(
            f"WARNING: no provided-CDRH3 universe ({UNIVERSE} or "
            f"{UNIVERSE_COMMITTED}) — novelty not checked",
            file=sys.stderr,
        )
        return set()
    return {l.strip().upper() for l in text.splitlines() if l.strip()}


AA_ALPHABET = "ACDEFGHIKLMNPQRSTVWY"


def min_substitutions_capped(
    loop: str, universe: set[str], cap: int = NOVELTY_CAP
) -> int | None:
    """How far `loop` is from the nearest provided sequence, capped at `cap`.

    Returns 0 (the loop is in the provided data), 1 (a single substitution from a
    provided sequence), 2 (exactly two — passes the filter as measured, but the
    wording reads as "more than 2", so it is the ambiguous band), or `cap`
    meaning "`cap` or more" — unambiguously clear of the rule either way.

    Enumerating the loop's own substitution neighbourhood and doing set lookups
    is exact, and far cheaper than scanning 525,063 rows per design: ~190
    lookups for distance 1 and ~16k for distance 2 on a 10-mer.

    This is the authoritative number generation ships. It must agree with
    gates.novelty_from_universe, which recomputes it for a judge's own run.
    """
    if not universe:
        return None
    loop = loop.upper()
    if loop in universe:
        return 0

    n = len(loop)
    for i in range(n):
        orig = loop[i]
        for aa in AA_ALPHABET:
            if aa == orig:
                continue
            if loop[:i] + aa + loop[i + 1 :] in universe:
                return 1

    if cap >= 2:
        for i in range(n):
            oi = loop[i]
            for ai in AA_ALPHABET:
                if ai == oi:
                    continue
                first = loop[:i] + ai + loop[i + 1 :]
                for j in range(i + 1, n):
                    oj = first[j]
                    for aj in AA_ALPHABET:
                        if aj == oj:
                            continue
                        if first[:j] + aj + first[j + 1 :] in universe:
                            return 2

    return cap


def novelty_block(cdrh3: str, muts: int | None, universe: set[str]) -> dict:
    """The novelty verdict generation ships for one design.

    `borderline` is the field the portfolio step needs: a design at exactly 2
    substitutions passes the filter as the tool measures it, but fails the
    project text's "more than 2" wording. Those two readings disagree only at
    2, so flagging that one value is what lets selection prefer designs that
    are submittable under either reading.
    """
    nov = {
        "cdrh3_length": len(cdrh3),
        "mutations_from_parent": muts,
        "identity_to_parent": (
            round(1 - muts / len(cdrh3), 4) if muts is not None else None
        ),
    }
    if not universe:
        return nov

    mh = min_substitutions_capped(cdrh3, universe, NOVELTY_CAP)
    nov["min_substitutions_from_any_provided"] = mh
    if mh is not None and mh >= NOVELTY_CAP:
        nov["min_substitutions_is_capped_at"] = NOVELTY_CAP
    nov["in_provided_data"] = (mh == 0)
    # The filter as measured: >= 2 differences from every provided sequence,
    # and at least 4 of 10 changed from the parent (the strict <70% reading).
    nov["passes_novelty"] = bool(mh is not None and mh >= 2)
    nov["passes_identity_ceiling"] = bool(muts is not None and muts >= 4)
    nov["passes_challenge_filter"] = bool(
        nov["passes_novelty"] and nov["passes_identity_ceiling"]
    )
    # Submittable under the strict wording too, not just as measured.
    nov["borderline"] = bool(mh == 2)
    nov["passes_novelty_strict"] = bool(mh is not None and mh >= 3)
    return nov


def read_metrics(run: Path) -> dict[str, dict]:
    path = run / "design" / "generation" / "inference_metrics" / "per_example_metrics.csv"
    if not path.exists():
        return {}
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            ex = row.get("example_id")
            if not ex:
                continue
            d = {}
            for src, dst in WANTED_METRICS.items():
                v = row.get(src)
                if v in (None, ""):
                    continue
                try:
                    f = float(v)
                    d[dst] = int(f) if f.is_integer() else round(f, 5)
                except ValueError:
                    d[dst] = v
            out[ex] = d
    return out


def read_refold(run: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for scored in sorted(run.glob("scored-*")):
        path = scored / "refold_metrics.csv"
        if not path.exists():
            continue
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                qid = row.get("query_id")
                if not qid:
                    continue
                d = {}
                for src, dst in WANTED_REFOLD.items():
                    v = row.get(src)
                    if v in (None, ""):
                        continue
                    try:
                        f = float(v)
                        d[dst] = int(f) if f.is_integer() else round(f, 5)
                    except ValueError:
                        d[dst] = v
                out[qid] = d
    return out


def normalise_model(dir_name: str) -> str:
    """Fold output directories carry suffixes (protenix-close, boltz2-close)."""
    n = dir_name.lower()
    for key in ("protenix-v2", "protenix-v1", "of3ob", "of3p2", "mol1-base", "boltz2", "boltz1",
                "esmfold2", "protenix"):
        if n.startswith(key):
            return "protenix-v2" if key == "protenix" else key
    return dir_name


def fold_dirs(run: Path):
    for d in sorted(run.iterdir()):
        if not d.is_dir():
            continue
        if d.name in ("design", "prepared") or d.name.startswith("scored-"):
            continue
        yield d


def per_model_scores(run: Path, example_id: str) -> dict[str, dict]:
    """ipTM / pTM / pLDDT per folding model, straight from each model's scores.json.

    refold-score only runs for the model we scored against, but every fold writes
    its own scores. Reading them directly is what makes a per-model comparison
    possible -- and the per-model baseline is the only way those numbers mean
    anything, since the same parent scores 0.960 under Boltz-2 and 0.676 under
    Protenix v2.
    """
    out: dict[str, dict] = {}
    for d in fold_dirs(run):
        hits = sorted(d.glob(f"{example_id}/*/*_scores.json"))
        if not hits:
            continue
        try:
            blob = json.loads(hits[0].read_text())
        except (OSError, ValueError):
            continue
        model = normalise_model(d.name)
        entry = {
            "model": model,
            "iptm": blob.get("interface_predicted_tm_score"),
            "ptm": blob.get("predicted_tm_score"),
            "plddt": blob.get("average_predicted_local_distance_difference_test"),
            "ranking_score": blob.get("model_ranking_score"),
        }
        out[model] = {k: v for k, v in entry.items() if v is not None}
    return out


def refold_contacts(run: Path, example_id: str) -> dict[str, dict]:
    """Epitope contacts from every refolded model of one design, keyed by model.

    score.py caps the epitope axis without structural evidence and says the
    contacts should come from the refold. Validated against the parent: the
    baseline refold recovers 557-561, 570-573 and 593-603, which is the annotated
    trastuzumab epitope, so the method and the annotation agree.
    """
    out: dict[str, dict] = {}
    for model_dir in fold_dirs(run):
        name = model_dir.name
        hits = sorted(model_dir.glob(f"{example_id}/*/*_model.cif"))
        if not hits:
            continue
        try:
            res = _epitope_contacts(hits[0])
        except (OSError, ValueError):
            continue
        if res.get("contacts"):
            out[normalise_model(name)] = res
    return out


def recompute_novelty(paths: list[Path]) -> int:
    """Re-derive the novelty block for already-exported batches, in place.

    The run directories live on the VM and the VM is wiped tonight, but the
    novelty verdict only needs the CDRH3 and the committed universe — both of
    which are in the repo. So raising the cap does not require regenerating.
    """
    universe = load_universe()
    if not universe:
        raise SystemExit("cannot recompute novelty without the provided universe")
    # The rule is a substitution count, so it is only defined between loops of
    # equal length. A de novo 17-19mer cannot sit N substitutions from a 10mer
    # at any N, and the de novo export records that as null with a basis note
    # rather than a number. Recomputing those would replace a deliberate "does
    # not apply" with a vacuous "3".
    provided_lengths = {len(s) for s in universe}
    changed_files = 0
    for path in paths:
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        moved = 0
        skipped = 0
        for row in rows:
            cdrh3 = row.get("cdrh3")
            if not cdrh3:
                continue
            if len(cdrh3) not in provided_lengths:
                skipped += 1
                continue
            old = row.get("novelty") or {}
            before = old.get("min_substitutions_from_any_provided")
            muts = old.get("mutations_from_parent")
            if muts is None and len(cdrh3) == len(PARENT_CDRH3):
                muts = sum(1 for a, b in zip(cdrh3, PARENT_CDRH3) if a != b)
            new = novelty_block(cdrh3, muts, universe)
            # Keep anything the original block carried that we do not derive,
            # e.g. the de novo export's basis note for non-10-mer loops.
            for k, v in old.items():
                new.setdefault(k, v)
            new.pop("min_substitutions_is_capped_at_2", None)
            row["novelty"] = new
            if new.get("min_substitutions_from_any_provided") != before:
                moved += 1
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        unamb = sum(
            1 for r in rows if (r.get("novelty") or {}).get("passes_novelty_strict")
        )
        border = sum(1 for r in rows if (r.get("novelty") or {}).get("borderline"))
        note = (
            f", {skipped} left alone (CDRH3 length the rule is not defined on)"
            if skipped else ""
        )
        print(
            f"{path.name}: {len(rows)} designs, {moved} distances resolved further, "
            f"{unamb} unambiguous (>=3), {border} borderline (exactly 2){note}"
        )
        changed_files += 1
    return changed_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path, nargs="?")
    ap.add_argument("--weight")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--prefix", default=None, help="design_id prefix (default: run dir name)")
    ap.add_argument("--track", default="optimisation")
    ap.add_argument("--format", dest="fmt", default="scfv")
    ap.add_argument("--skip-novelty", action="store_true")
    ap.add_argument(
        "--recompute-novelty",
        type=Path,
        nargs="+",
        metavar="JSONL",
        help="re-derive novelty in place for exported batches; no run dir needed",
    )
    args = ap.parse_args()

    if args.recompute_novelty:
        recompute_novelty(args.recompute_novelty)
        return

    for required in ("run", "weight", "seed", "out"):
        if getattr(args, required) is None:
            ap.error(f"--{required} is required when exporting a run")

    run = args.run
    prefix = args.prefix or run.name
    samples = run / "design" / "generation" / "inference_samples"
    if not samples.is_dir():
        raise SystemExit(f"no designs found under {samples}")

    universe = set() if args.skip_novelty else load_universe()
    metrics = read_metrics(run)
    refold = read_refold(run)

    cifs = sorted(samples.glob("*/*_generated.cif"))
    rows = []
    skipped = []
    for cif in cifs:
        example_id = cif.parent.name
        chains = parse_cif_chains(cif)
        vh = chains.get("B", "")
        vl = chains.get("A", "")
        cdrh3 = extract_cdrh3(vh) if vh else None
        if not vh or not cdrh3:
            skipped.append((example_id, "could not parse VH or locate CDRH3"))
            continue
        muts = (
            sum(1 for a, b in zip(cdrh3, PARENT_CDRH3) if a != b)
            if len(cdrh3) == len(PARENT_CDRH3) else None
        )
        row = {
            "design_id": f"{prefix}-{example_id}",
            "batch": prefix,
            "example_id": example_id,
            "vh": vh,
            "vl": vl,
            "cdrh3": cdrh3,
            "generator": f"rfd4-proteina:{args.weight}",
            "track": args.track,
            "format": args.fmt,
            "seed": args.seed,
            "parent": "trastuzumab",
        }
        row["novelty"] = novelty_block(cdrh3, muts, universe)
        if example_id in metrics:
            row["design_metrics"] = metrics[example_id]
        if example_id in refold:
            row["refold"] = refold[example_id]
        pms = per_model_scores(run, example_id)
        if pms:
            row["refold_by_model"] = pms
        ec = refold_contacts(run, example_id)
        if ec:
            row["epitope_contacts_by_model"] = ec
            # One consumable list, from the model that PASSES THE EPITOPE CONTROL.
            #
            # This order used to be ("protenix-v2", "of3ob", "boltz2") on the
            # grounds that Protenix is the model whose confidence we trust --
            # true, and documented in generation.md section 3, but it is a
            # statement about ipTM and it does not transfer to where a model
            # puts the two molecules. Those are different questions and they
            # have different answers.
            #
            # Measured on trastuzumab's own refold, whose epitope is known from
            # 1N8Z, scored against the annotated contact regions:
            #
            #   boltz2       precision 0.74  recall 0.70  all three regions
            #   protenix-v2  precision 0.47  recall 0.35  misses 557-561 AND
            #                                            570-573 entirely
            #
            # So the axis was reading contacts from the model that cannot find
            # the epitope on the one molecule where the answer is known, and
            # the spread Protenix gave across designs was its own placement
            # error. Rerun the control any time with
            # scripts/epitope_control.py -- it reads committed data only.
            pref = next((m for m in ("boltz2", "of3ob", "protenix-v2") if m in ec), sorted(ec)[0])
            row["epitope_contacts"] = ec[pref]["contacts"]
            row["epitope_contacts_source"] = pref
        rows.append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    # ---- summary, so the log says what we actually got ----
    n = len(rows)
    print(f"exported {n} designs -> {args.out}")
    if skipped:
        print(f"skipped {len(skipped)}:")
        for ex, why in skipped[:5]:
            print(f"  {ex}: {why}")
    if not n:
        return
    uniq = len({r["cdrh3"] for r in rows})
    print(f"distinct CDRH3: {uniq}/{n} ({100*uniq/n:.0f}%)")
    with_refold = sum(1 for r in rows if "refold" in r)
    print(f"refolded: {with_refold}/{n}")
    with_ec = sum(1 for r in rows if r.get("epitope_contacts"))
    if with_ec:
        print(f"with epitope contacts from the refolded complex: {with_ec}/{n}")
    if universe:
        known = sum(1 for r in rows if r["novelty"].get("in_provided_data"))
        nov_ok = sum(1 for r in rows if r["novelty"].get("passes_novelty"))
        id_ok = sum(1 for r in rows if r["novelty"].get("passes_identity_ceiling"))
        both = sum(1 for r in rows if r["novelty"].get("passes_challenge_filter"))
        print(f"already in the provided data (known): {known}/{n} ({100*known/n:.0f}%)")
        print(f"passes novelty (>=2 from all provided): {nov_ok}/{n} ({100*nov_ok/n:.0f}%)")
        print(f"passes identity ceiling (>=4 from parent): {id_ok}/{n} ({100*id_ok/n:.0f}%)")
        print(f"PASSES THE CHALLENGE FILTER: {both}/{n} ({100*both/n:.0f}%)")
        muts = [r["novelty"]["mutations_from_parent"] for r in rows
                if r["novelty"].get("mutations_from_parent") is not None]
        if muts:
            hist = {}
            for m in muts:
                hist[m] = hist.get(m, 0) + 1
            print(f"substitutions from parent: {dict(sorted(hist.items()))}")


if __name__ == "__main__":
    main()
