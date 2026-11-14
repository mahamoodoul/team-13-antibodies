"""Fit the binding axis on the FACS-labelled CDRH3 variants — OWNER: Rizve.

This replaces the hand-set binding prior in `stages/score.py` with a model
fitted on real labels for this exact parent against this exact target. The
prior could only ever penalise change; these data contain variants measured to
bind BETTER than trastuzumab, so a fit can credit a specific aggressive change
that the prior is structurally unable to reward.

    python3 -m fourwells.fit_binding --train proof/tidy/fixtures/facs_train_sample.csv \\
        --test proof/tidy/fixtures/facs_test_sample.csv --spr proof/tidy/spr_measured.csv

Writes data/models/binding_cdrh3.json, which `score.load_binding_model()` picks
up on the next run with no code change.

WHY A POSITION-SPECIFIC LINEAR MODEL and not something fancier. Three reasons,
in order of how much they matter:

1. It is the right shape for the data. Every variant row is a 10-mer at fixed
   framework, so the design matrix is one-hot(position, residue) — 200 columns,
   no alignment, no feature engineering to argue about.
2. It is interpretable per position, which is what the dossier needs. "Position
   7 tolerates M but not P" is a sentence a judge can check; a tree ensemble's
   feature importance is not.
3. It runs on the standard library in seconds. The repo has no numpy by
   deliberate choice — `make demo` must work on a judge's laptop offline — and
   a dependency on the critical path for a 200-parameter fit is a bad trade.

Fitted by full-batch gradient descent with L2, fixed iterations, no randomness
anywhere: same input gives the same model, which is the reproducibility the
execution score is actually asking about.

HONEST LIMITS, stated here because they belong in the pitch:
- The model only speaks the parent's loop length. A design with an indel in
  CDRH3 has positions the model never saw; those contribute nothing and the
  record says so rather than quietly scoring short.
- FACS affinity classes are a coarser readout than the SPR the lab will run.
  The fit ranks; it does not predict a K_D.
- Trained on single-target data, so it transfers to nothing else. The ranking
  LAYER is target-agnostic; this particular axis is not, and conflating those
  two claims would be overselling.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"
MODEL_FILE = MODEL_DIR / "binding_cdrh3.json"

AA = "ACDEFGHIKLMNPQRSTVWY"
# "high" is the class we want to rank up. Binary rather than ordinal because
# the decision we are making is binary — does this design go in a well — and a
# three-class fit would spend capacity separating low from medium, which we do
# not care about.
POSITIVE_CLASS = "high"

L2 = 1e-3
ITERATIONS = 400
LEARNING_RATE = 0.5


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def read_variants(path: Path, loop_col: str = "cdrh3", label_col: str = "binding_class"):
    rows = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            loop = (row.get(loop_col) or "").strip().upper()
            label = (row.get(label_col) or "").strip().lower()
            if loop and label:
                rows.append((loop, 1 if label == POSITIVE_CLASS else 0))
    return rows


def read_spr(path: Path):
    """The 190 SPR-measured designs: (loop, kd_nM). Blind validation."""
    out = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            loop = (row.get("cdrh3") or "").strip().upper()
            raw = (row.get("kd_nM") or "").strip()
            if not loop or not raw:
                continue
            try:
                out.append((loop, float(raw)))
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------


def _index(loop_len: int) -> dict[tuple[int, str], int]:
    return {(i, aa): i * len(AA) + k for i in range(loop_len) for k, aa in enumerate(AA)}


def fit(rows, loop_len: int, iterations: int = ITERATIONS, lr: float = LEARNING_RATE, l2: float = L2):
    """Logistic regression on one-hot(position, residue). Deterministic."""
    idx = _index(loop_len)
    n_feat = loop_len * len(AA)
    w = [0.0] * n_feat
    b = 0.0
    usable = [(loop, y) for loop, y in rows if len(loop) == loop_len]
    n = len(usable)
    if not n:
        raise SystemExit(f"no training rows of length {loop_len}")

    # Pre-resolve feature indices once; the inner loop is 10 lookups per row.
    encoded = [([idx[(i, aa)] for i, aa in enumerate(loop) if (i, aa) in idx], y) for loop, y in usable]

    for _ in range(iterations):
        gw = [0.0] * n_feat
        gb = 0.0
        for feats, y in encoded:
            z = b
            for j in feats:
                z += w[j]
            p = 1.0 / (1.0 + math.exp(-z)) if -40 < z < 40 else (0.0 if z <= -40 else 1.0)
            d = p - y
            gb += d
            for j in feats:
                gw[j] += d
        b -= lr * gb / n
        for j in range(n_feat):
            w[j] -= lr * (gw[j] / n + l2 * w[j])

    return w, b, idx, n


def score_loop(loop: str, w, b: float, idx) -> float:
    z = b
    for i, aa in enumerate(loop):
        j = idx.get((i, aa))
        if j is not None:
            z += w[j]
    return z


# ---------------------------------------------------------------------------
# Evaluation — ranking metrics only, for the reason the manifest gives
# ---------------------------------------------------------------------------


def auc(scores_labels) -> float:
    """Rank-based AUC. Class balance differs between train and test by design,
    so a single accuracy figure would be meaningless and this is not."""
    pos = [s for s, y in scores_labels if y == 1]
    neg = [s for s, y in scores_labels if y == 0]
    if not pos or not neg:
        return float("nan")
    ordered = sorted(scores_labels, key=lambda t: t[0])
    ranks: dict[int, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg
        i = j + 1
    rank_sum = sum(ranks[k] for k, (_, y) in enumerate(ordered) if y == 1)
    return (rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def enrichment(spr, w, b, idx, baseline_kd: float) -> dict:
    """The number that matters: hit rate in our top 4 against the base rate.

    A hit is a design whose measured K_D beats trastuzumab's. Top 4 is reported
    first because four wells is the decision we are actually making — top 10
    and top 25 are context, not the claim.
    """
    scored = sorted(((score_loop(loop, w, b, idx), loop, kd) for loop, kd in spr), key=lambda t: -t[0])
    hits = [1 if kd < baseline_kd else 0 for _, _, kd in scored]
    total_hits = sum(hits)
    base_rate = total_hits / len(hits) if hits else 0.0

    out: dict = {
        "n_designs": len(scored),
        "n_beating_baseline": total_hits,
        "base_rate": round(base_rate, 4),
        "baseline_kd_nM": baseline_kd,
    }
    for k in (4, 10, 25):
        if len(scored) >= k:
            rate = sum(hits[:k]) / k
            out[f"top{k}"] = {
                "hits": sum(hits[:k]),
                "rate": round(rate, 4),
                "enrichment_vs_base": round(rate / base_rate, 2) if base_rate else None,
            }
    out["top4_designs"] = [
        {"cdrh3": loop, "model_score": round(s, 4), "kd_nM": kd, "beats_baseline": kd < baseline_kd}
        for s, loop, kd in scored[:4]
    ]
    # Name a case we got wrong: the best measured design we ranked worst.
    true_best = min(scored, key=lambda t: t[2])
    rank_of_best = [i for i, (_, loop, _) in enumerate(scored, 1) if loop == true_best[1]][0]
    out["worst_miss"] = {
        "cdrh3": true_best[1],
        "kd_nM": true_best[2],
        "our_rank": rank_of_best,
        "of": len(scored),
        "note": "the strongest measured binder and where our ranking put it",
    }
    return out


def spearman(xs, ys) -> float:
    """Rank correlation, ties averaged. The statistic that decides whether this
    model is allowed into the pipeline at all."""

    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (c - my) for a, c in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((c - my) ** 2 for c in ry))
    return num / den if den else 0.0


def transfer_check(spr, w, b, idx, parent: str) -> dict:
    """Does the fit transfer from FACS classes to measured K_D, on designs we
    are actually allowed to submit?

    This gate exists because the answer turned out to be no, and a model with
    a good held-out AUC on its own label would otherwise have walked straight
    into the ranker. A high AUC against FACS class is not evidence of anything
    about SPR K_D; this is the check that says so in numbers.

    Sign convention: lower K_D is better, so a model that ranks binding
    correctly has a NEGATIVE correlation with log K_D. A positive value means
    the model is actively ranking good binders down.
    """
    legal = [(l, kd) for l, kd in spr if l != parent and _identity(l, parent) < 0.70]
    scored = [(score_loop(l, w, b, idx), math.log(kd)) for l, kd in legal]
    rho_legal = spearman([s for s, _ in scored], [k for _, k in scored])

    allrows = [(l, kd) for l, kd in spr if l != parent]
    rho_all = spearman(
        [score_loop(l, w, b, idx) for l, _ in allrows], [math.log(kd) for _, kd in allrows]
    )

    ok = rho_legal < -0.10
    return {
        "n_submittable": len(legal),
        "spearman_vs_logkd_submittable": round(rho_legal, 4),
        "spearman_vs_logkd_all": round(rho_all, 4),
        "sign_convention": "negative is correct (high score should mean low K_D)",
        "passes": ok,
        "verdict": (
            f"TRANSFERS — rho {rho_legal:+.3f} on the submittable subset"
            if ok
            else f"DOES NOT TRANSFER — rho {rho_legal:+.3f} on the submittable subset. "
            "A good FACS AUC did not survive contact with measured K_D. This model is "
            "NOT written to data/models/ and the hand-set prior stays in the ranker."
        ),
    }


def _identity(a: str, b: str) -> float:
    n = max(len(a), len(b))
    return sum(1 for x, y in zip(a, b) if x == y) / n if n else 0.0


def leakage_check(train_rows, spr) -> dict:
    """Are any SPR validation loops in the training set? Report it, loudly."""
    train_loops = {loop for loop, _ in train_rows}
    spr_loops = {loop for loop, _ in spr}
    shared = train_loops & spr_loops
    return {
        "n_train_loops": len(train_loops),
        "n_spr_loops": len(spr_loops),
        "shared": len(shared),
        "examples": sorted(shared)[:5],
        "verdict": (
            "CLEAN — no SPR validation loop appears in training"
            if not shared
            else f"LEAKAGE — {len(shared)} SPR loops are in the training set; "
            "the enrichment number below is inflated and must not be quoted"
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fourwells.fit_binding", description=__doc__)
    ap.add_argument("--train", type=Path, default=Path("proof/tidy/fixtures/facs_train_sample.csv"))
    ap.add_argument("--test", type=Path, default=Path("proof/tidy/fixtures/facs_test_sample.csv"))
    ap.add_argument("--spr", type=Path, default=Path("proof/tidy/spr_measured.csv"))
    ap.add_argument("--parent-cdrh3", default=None, help="default: from the reference file")
    ap.add_argument("--baseline-kd", type=float, default=None, help="default: from the reference file")
    ap.add_argument("--iterations", type=int, default=ITERATIONS)
    ap.add_argument("--out", type=Path, default=MODEL_FILE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="write the model even if it fails the transfer check")
    args = ap.parse_args(argv)

    from .targets import REFERENCE_DIR

    ref_blob = json.loads((REFERENCE_DIR / "trastuzumab.json").read_text())
    parent = args.parent_cdrh3 or ref_blob["cdrs_kabat"]["cdr_h3"]
    baseline_kd = args.baseline_kd or (ref_blob.get("baseline_measurements") or {}).get("kd_nM")
    loop_len = len(parent)

    train = read_variants(args.train)
    print(f"train  {len(train):>7} rows from {args.train}")
    print(f"       class balance {dict(Counter(y for _, y in train))} (1 = {POSITIVE_CLASS})")

    w, b, idx, n_used = fit(train, loop_len, iterations=args.iterations)
    print(f"fit    {loop_len * len(AA)} weights on {n_used} rows of length {loop_len}, "
          f"{args.iterations} iterations")

    report: dict = {"train_rows": n_used, "parent_cdrh3": parent, "loop_length": loop_len}

    train_auc = auc([(score_loop(l, w, b, idx), y) for l, y in train if len(l) == loop_len])
    report["train_auc"] = round(train_auc, 4)
    print(f"       train AUC {train_auc:.4f}")

    if args.test.exists():
        test = read_variants(args.test)
        test_auc = auc([(score_loop(l, w, b, idx), y) for l, y in test if len(l) == loop_len])
        report["test_auc"] = round(test_auc, 4)
        report["test_rows"] = len(test)
        print(f"       held-out AUC {test_auc:.4f}  ({len(test)} rows, split by edit distance)")

    if args.spr.exists() and baseline_kd:
        spr = read_spr(args.spr)
        report["leakage"] = leakage_check(train, spr)
        print(f"\nleakage: {report['leakage']['verdict']}")
        report["enrichment"] = enrichment(spr, w, b, idx, baseline_kd)
        e = report["enrichment"]
        print(f"\nenrichment on {e['n_designs']} SPR-measured designs "
              f"(baseline K_D {baseline_kd} nM)")
        print(f"  base rate        {e['base_rate']:.1%}  ({e['n_beating_baseline']} beat it)")
        for k in (4, 10, 25):
            key = f"top{k}"
            if key in e:
                print(f"  our top {k:<2}      {e[key]['rate']:.1%}  "
                      f"({e[key]['hits']}/{k}, {e[key]['enrichment_vs_base']}x base)")
        wm = e["worst_miss"]
        print(f"  worst miss       {wm['cdrh3']} at {wm['kd_nM']} nM ranked "
              f"{wm['our_rank']}/{wm['of']}")

        report["transfer"] = transfer_check(spr, w, b, idx, parent)
        print(f"\ntransfer: {report['transfer']['verdict']}")

    model = {
        "kind": "pssm",
        "intercept": round(b, 6),
        "weights": {
            str(i): {aa: round(w[idx[(i, aa)]], 6) for aa in AA} for i in range(loop_len)
        },
        "fit_note": (
            f"logistic on one-hot(position, residue), L2={L2}, {args.iterations} full-batch "
            f"iterations, deterministic. Positive class = FACS '{POSITIVE_CLASS}'. "
            f"Only speaks {loop_len}-mers; other lengths score missing positions as 0."
        ),
        "heldout": report,
    }

    if args.dry_run:
        print("\n(dry run — model not written)")
        return 0

    # A model that failed blind validation does not get to become the ranker.
    # This is the guard that a good held-out AUC on the training label would
    # otherwise have walked straight past.
    transfer = report.get("transfer")
    if transfer and not transfer["passes"] and not args.force:
        print(
            f"\nREFUSING to write {args.out}: the model does not transfer to measured K_D.\n"
            "The hand-set prior in stages/score.py stays in the ranker. Pass --force to\n"
            "override, and if you do, say so on the slide."
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
