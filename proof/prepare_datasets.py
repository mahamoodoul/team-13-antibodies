#!/usr/bin/env python3
"""Tidy the provided datasets into flat CSVs and build the held-out split.

Outputs (default --out ~/mahamodul/proof/tidy):

  facs_variants.csv        524,346 CDRH3 variants, FACS class, edit distance to parent
  facs_train.csv           edit_distance <= --split-at
  facs_test.csv            edit_distance >  --split-at      <- the held-out slice
  spr_designs.csv          768 optimisation designs, 190 with a fitted KD
  spr_measured.csv         the 190 measured designs only    <- blind validation set
  iptm_pairs.csv           long-form VHH x antigen ipTM, one row per pair per model
  fixtures/*.csv           2,000-row samples of each, for fast iteration
  MANIFEST.md              row counts, class balance, provenance, how the split was made

The split is by mutation count, not random: training sees CDRH3s close to the parent,
the test set sees distant ones. Our own designs must clear <70% CDRH3 identity to
trastuzumab, so they live in the distant regime. A random split would score far better
and mean nothing.

Usage: python3 prepare_datasets.py [--data DIR] [--out DIR] [--split-at 7]
"""

import argparse
import csv
import io
import random
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

PARENT_CDRH3 = "WGGDGFYAMD"  # trastuzumab, the 10-mer these datasets vary
FIXTURE_N = 2000
SEED = 13


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return path


def fixture(out, name, fieldnames, rows):
    rng = random.Random(SEED)
    sample = rows if len(rows) <= FIXTURE_N else rng.sample(rows, FIXTURE_N)
    write_csv(out / "fixtures" / name, fieldnames, sample)
    return len(sample)


def do_facs(data, out, split_at, log):
    zp = data / "her2-trastuzumab" / "tz_her2_facs_3classes_524346.csv.zip"
    rows = []
    with zipfile.ZipFile(zp) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "MACOSX" not in n)
        with z.open(name) as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, "utf-8")):
                c = r["cdrh3"]
                rows.append(
                    {
                        "cdrh3": c,
                        "binding_class": r["binding_class"],
                        "edit_distance": int(r["edit_distance"]),
                        "identity_to_parent": round(
                            sum(a == b for a, b in zip(c, PARENT_CDRH3)) / len(PARENT_CDRH3), 3
                        ),
                        "vh_sequence": r["vh_sequence"],
                        "vl_sequence": r["vl_sequence"],
                    }
                )

    fields = list(rows[0])
    write_csv(out / "facs_variants.csv", fields, rows)

    train = [r for r in rows if r["edit_distance"] <= split_at]
    test = [r for r in rows if r["edit_distance"] > split_at]
    write_csv(out / "facs_train.csv", fields, train)
    write_csv(out / "facs_test.csv", fields, test)
    fixture(out, "facs_train_sample.csv", fields, train)
    fixture(out, "facs_test_sample.csv", fields, test)

    # leakage check: a test CDRH3 must not appear in train
    overlap = len({r["cdrh3"] for r in train} & {r["cdrh3"] for r in test})

    log["facs"] = {
        "total": len(rows),
        "train": len(train),
        "test": len(test),
        "split_at": split_at,
        "overlap": overlap,
        "cls_all": Counter(r["binding_class"] for r in rows),
        "cls_train": Counter(r["binding_class"] for r in train),
        "cls_test": Counter(r["binding_class"] for r in test),
        "ed": Counter(r["edit_distance"] for r in rows),
    }
    return rows


def do_spr(data, out, log):
    p = data / "her2-trastuzumab" / "trastuzumab_her2_spr_all_768.csv"
    rows = []
    for r in csv.DictReader(p.open()):
        c = r["cdrh3"]
        kd = r["kd_nM"].strip()
        ident = (
            round(sum(a == b for a, b in zip(c, PARENT_CDRH3)) / len(PARENT_CDRH3), 3)
            if len(c) == len(PARENT_CDRH3)
            else ""
        )
        rows.append(
            {
                "cdrh3": c,
                "cdrh3_len": len(c),
                "identity_to_parent": ident,
                "binding_result": r["binding_result"],
                "kd_nM": kd,
                "measured": "yes" if kd else "no",
                "vh_sequence": r["vh_sequence"],
                "vl_sequence": r["vl_sequence"],
            }
        )
    fields = list(rows[0])
    write_csv(out / "spr_designs.csv", fields, rows)
    measured = [r for r in rows if r["measured"] == "yes"]
    write_csv(out / "spr_measured.csv", fields, measured)
    fixture(out, "spr_designs_sample.csv", fields, rows)

    kds = sorted(float(r["kd_nM"]) for r in measured)
    log["spr"] = {
        "total": len(rows),
        "measured": len(measured),
        "outcomes": Counter(r["binding_result"] for r in rows),
        "kd_min": kds[0],
        "kd_med": kds[len(kds) // 2],
        "kd_max": kds[-1],
        "lens": Counter(r["cdrh3_len"] for r in rows),
    }
    return rows


def do_iptm(data, out, log):
    zp = data / "zenodo-18390239-ab-ag-complexes" / "iptm_confidence_scores.zip"
    rows = []
    stats = defaultdict(lambda: {"cognate": [], "non_cognate": []})
    with zipfile.ZipFile(zp) as z:
        for model in ("af3", "boltz2", "chai1"):
            nm = f"iptm_confidence_scores/{model}_matrix_clean.csv"
            if nm not in z.namelist():
                continue
            with z.open(nm) as fh:
                tbl = list(csv.reader(io.TextIOWrapper(fh, "utf-8")))
            cols = tbl[0][1:]
            for line in tbl[1:]:
                ab, vals = line[0], line[1:]
                for ag, v in zip(cols, vals):
                    if not v.strip():
                        continue
                    x = float(v)
                    pair = "cognate" if ab == ag else "non_cognate"
                    rows.append(
                        {
                            "model": model,
                            "vhh_pdb": ab,
                            "antigen_pdb": ag,
                            "pair_type": pair,
                            "iptm": x,
                        }
                    )
                    stats[model][pair].append(x)
    fields = ["model", "vhh_pdb", "antigen_pdb", "pair_type", "iptm"]
    write_csv(out / "iptm_pairs.csv", fields, rows)
    fixture(out, "iptm_pairs_sample.csv", fields, rows)
    log["iptm"] = {m: {k: len(v) for k, v in d.items()} for m, d in stats.items()}
    log["iptm_raw"] = stats
    return rows


def manifest(out, log, data, split_at):
    f, s, ip = log["facs"], log["spr"], log["iptm_raw"]
    L = []
    A = L.append
    A("# Tidy datasets — manifest\n")
    A(f"Built {date.today().isoformat()} by `proof/prepare_datasets.py` from `{data}`.")
    A("Owner: Mahamodul (proof lane). Consumers: Rizve (gates, predictors), Ansarul (fixtures).\n")

    A("## Files\n")
    A("| File | Rows | What it is |")
    A("| --- | --- | --- |")
    A(f"| `facs_variants.csv` | {f['total']:,} | All CDRH3 variants, FACS class, distance to parent |")
    A(f"| `facs_train.csv` | {f['train']:,} | edit_distance <= {split_at} — fit here |")
    A(f"| `facs_test.csv` | {f['test']:,} | edit_distance > {split_at} — **held out** |")
    A(f"| `spr_designs.csv` | {s['total']:,} | Optimisation designs, all outcomes |")
    A(f"| `spr_measured.csv` | {s['measured']:,} | Fitted KD only — **blind validation** |")
    A(f"| `iptm_pairs.csv` | {sum(sum(v.values()) for v in log['iptm'].values()):,} | Long-form ipTM, 3 models |")
    A(f"| `fixtures/*.csv` | <={FIXTURE_N:,} each | Samples for fast iteration (seed {SEED}) |")
    A("\nThe three `facs_*.csv` files total ~260 MB and are **not committed**; rerun this")
    A("script to rebuild them from the source zip. Everything else here is in git, because")
    A("the VM is wiped at the end of the day.")

    A("\n## The held-out split\n")
    A(f"Split axis: **edit distance to the trastuzumab CDRH3** (`{PARENT_CDRH3}`), at **{split_at}**.")
    A("Not random. Our submissions must clear <70% CDRH3 identity to trastuzumab, so every")
    A("design we ship sits in the distant regime. Training on near-neighbours and testing on")
    A("distant variants is the only split that measures the extrapolation we actually need.\n")
    A(f"- train {f['train']:,} rows · test {f['test']:,} rows · "
      f"{100 * f['test'] / f['total']:.0f}% held out")
    A(f"- shared CDRH3 between the two sides: **{f['overlap']}** "
      f"({'no leakage' if f['overlap'] == 0 else 'LEAKAGE — investigate'})")
    A("")
    A("| Class | All | Train | Test | Train % | Test % |")
    A("| --- | --- | --- | --- | --- | --- |")
    for c in ("low", "medium", "high"):
        tr, te = f["cls_train"][c], f["cls_test"][c]
        A(f"| {c} | {f['cls_all'][c]:,} | {tr:,} | {te:,} | "
          f"{100 * tr / f['train']:.0f}% | {100 * te / f['test']:.0f}% |")
    hi_tr = 100 * f["cls_train"]["high"] / f["train"]
    hi_te = 100 * f["cls_test"]["high"] / f["test"]
    lo_tr = 100 * f["cls_train"]["low"] / f["train"]
    lo_te = 100 * f["cls_test"]["low"] / f["test"]
    A("")
    A(f"**Class balance is not preserved, and that is the point.** High binders fall from")
    A(f"{hi_tr:.0f}% of train to {hi_te:.0f}% of test, low binders rise from {lo_tr:.0f}% to "
      f"{lo_te:.0f}%:")
    A("more mutations means worse binding. Two consequences, both of which must be")
    A("respected or the headline number is meaningless:")
    A("")
    A("1. Raw accuracy is not comparable across the two sides. Report per-class metrics, or")
    A("   balanced accuracy, or ranking metrics — never a single accuracy figure.")
    A(f"2. A classifier that always predicts \"low\" already scores {lo_te:.0f}% on the test set.")
    A("   That is the baseline to beat, not 33%.")
    A("\nEdit-distance distribution: " + ", ".join(f"{k}:{v:,}" for k, v in sorted(f["ed"].items())))

    A("")
    A("**The organisers also ship ready-made splits** in `zenodo-10831512`, clustered by")
    A("clonotype, with a binary `label` equal to the \"high\" FACS class. Those are the")
    A("comparable numbers and the convention to adopt; this split is the harder")
    A("extrapolation test alongside them. See `split_reconciliation.md`.")
    A("\n## SPR validation set\n")
    A(f"{s['measured']} of {s['total']} designs carry a fitted KD. "
      f"Range {s['kd_min']:g}–{s['kd_max']:g} nM, median {s['kd_med']:g} nM.")
    A("Outcomes: " + ", ".join(f"{k} {v}" for k, v in s["outcomes"].items()))
    A(f"CDRH3 lengths: {dict(sorted(s['lens'].items()))} — the 9-mers and 16-mers are not")
    A("comparable to the 10-mer FACS set; filter to length 10 before scoring against it.\n")
    A("Same assay the judges use. Rank these blind; never fit on them.")

    A("\n## ipTM pairs — read this before using them\n")
    A("Cross-pairing matrices: 91 VHH x 91 antigen. Diagonal = cognate (known binders),")
    A("off-diagonal = **shuffled** non-binding pairs. Shuffled pairs are computational,")
    A("**not SPR-measured**. The separate SPR table has only 29 rows.\n")
    A("| Model | Cognate | Non-cognate | Cognate >=0.7 | Non-cognate >=0.7 |")
    A("| --- | --- | --- | --- | --- |")
    for m in ("af3", "boltz2", "chai1"):
        if m not in ip:
            continue
        cg, nc = ip[m]["cognate"], ip[m]["non_cognate"]
        cg7 = sum(x >= 0.7 for x in cg)
        nc7 = sum(x >= 0.7 for x in nc)
        A(f"| {m} | {len(cg)} | {len(nc):,} | {cg7} ({100 * cg7 / len(cg):.0f}%) | "
          f"{nc7:,} ({100 * nc7 / len(nc):.0f}%) |")
    A("\nA single 0.7 cutoff means three different things across these models. Pick any")
    A("cutoff from the curve per model — see `calibrate_iptm.py` — never from a round number.")

    A("\n## Provenance\n")
    A("- FACS variants and SPR designs: Chinery et al., trastuzumab CDRH3 deep mutational scan.")
    A("- ipTM matrices and SPR table: Smorodina et al., *Structural Plausibility Without Binding")
    A("  Specificity*, bioRxiv 2026, doi 10.64898/2026.03.02.709004.")
    A("- The SPR table was extracted from the paper's supplementary PDF and is not in the Zenodo")
    A("  archives. The authors state: \"N/A denotes no reportable affinity fit, NOT confirmed")
    A("  non-binding.\" Do not relabel those rows as measured true negatives.")

    p = out / "MANIFEST.md"
    p.write_text("\n".join(L) + "\n")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path.home() / "data")
    ap.add_argument("--out", type=Path, default=Path.home() / "mahamodul" / "proof" / "tidy")
    ap.add_argument("--split-at", type=int, default=7,
                    help="train on edit_distance <= N, hold out the rest")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    log = {}

    print("FACS variants ...", flush=True)
    do_facs(a.data, a.out, a.split_at, log)
    print(f"  train {log['facs']['train']:,} / test {log['facs']['test']:,} "
          f"(overlap {log['facs']['overlap']})")

    print("SPR designs ...", flush=True)
    do_spr(a.data, a.out, log)
    print(f"  {log['spr']['measured']} measured of {log['spr']['total']}")

    print("ipTM pairs ...", flush=True)
    do_iptm(a.data, a.out, log)
    for m, d in log["iptm"].items():
        print(f"  {m}: {d['cognate']} cognate, {d['non_cognate']:,} non-cognate")

    p = manifest(a.out, log, a.data, a.split_at)
    print(f"\nwrote {a.out}")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
