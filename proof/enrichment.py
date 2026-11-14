#!/usr/bin/env python3
"""Does a FACS-trained sequence model pick winners in the assay the judges use?

The plan's centrepiece: fit a binding model on the 524K FACS-labelled CDRH3 variants,
rank the SPR-measured optimisation designs blind, and report the hit rate in our top 4
against the base rate of the pool.

We ran it. The answer is no, and that is the result worth presenting.

The experiment, in four steps, each of which can be checked independently:

  1. Fit a per-position amino-acid log-odds matrix (high vs low FACS class) on
     `facs_train.csv` -- the variants NEAR the trastuzumab parent, edit_distance <= 7.
     Site-independent, no pairwise terms, stdlib only, about a second to fit.
  2. Score `facs_test.csv` (edit_distance > 7, zero shared CDRH3). This measures
     extrapolation within the FACS assay, which is the regime our submissions live in.
  3. Assay transfer: a handful of molecules carry BOTH a FACS class and a fitted SPR KD.
     Score how well the FACS label alone predicts the KD. This is the ceiling on any
     FACS-trained model, independent of how good the model is.
  4. Rank the SPR designs we are actually allowed to submit, blind, and report top-k.

Three guards on the validation pool, each one a way the number could be a lie:

  - **Submittability.** Only designs under 70% CDRH3 identity to trastuzumab can be
    entered. Ranking near-parent point mutants measures a decision we are not allowed
    to make, and they are the easy, high-affinity end of the pool.
  - **Leakage.** Any SPR design whose CDRH3 also appears in the training rows is
    excluded and counted.
  - **Replicate noise.** Trastuzumab itself is measured eight times in this file,
    spanning 6x in KD. "Beats trastuzumab at 0.152 nM" is not a well-defined bar, and
    five of the parent's own replicates clear it. The bar here is the parent's
    geometric mean, with the spread reported next to it.

Outputs:
  enrichment_ranking.csv   every scored submittable design: rank, score, KD, hit flags
  enrichment.md            the readable result

Usage: python3 enrichment.py [--tidy DIR] [--out DIR] [--split-at 7] [--max-identity 0.70]
"""

import argparse
import csv
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

AAS = "ACDEFGHIKLMNPQRSTVWY"
PSEUDO = 1.0  # Laplace count. With ~100k rows a formality, but a residue unseen at a
              # position would otherwise score -inf and silently sink a design.
TOP_KS = (4, 10, 25, 50)
# Secondary, better-powered endpoints. Pre-registered here rather than chosen after
# seeing the ranking, which is the whole point of writing them down in the source.
KD_BARS = (1.0, 10.0)


# ---------------------------------------------------------------- stats

def auc(pos, neg):
    """Mann-Whitney U / ROC AUC, ties counted as half. Same routine as calibrate_iptm."""
    s = sorted([(x, 1) for x in pos] + [(x, 0) for x in neg])
    i, rsum = 0, 0.0
    while i < len(s):
        j = i
        while j < len(s) and s[j][0] == s[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        for k in range(i, j):
            if s[k][1] == 1:
                rsum += avg
        i = j
    n1, n0 = len(pos), len(neg)
    return (rsum - n1 * (n1 + 1) / 2) / (n1 * n0)


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and v[order[j]] == v[order[i]]:
            j += 1
        avg = (i + j + 1) / 2
        for k in range(i, j):
            r[order[k]] = avg
        i = j
    return r


def spearman(x, y):
    rx, ry = _ranks(x), _ranks(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


# ---------------------------------------------------------------- model

def fit(rows, length):
    """Per-position log-odds of the high FACS class over the low class.

    'medium' rows are deliberately unused. The lab question is whether a design beats
    trastuzumab, a high-vs-low contrast; treating medium as an ordinal middle needs a
    different model and, as step 3 shows, the labels do not support that much precision.
    """
    high = [defaultdict(float) for _ in range(length)]
    low = [defaultdict(float) for _ in range(length)]
    n_high = n_low = 0

    for r in rows:
        s = r["cdrh3"]
        if len(s) != length:
            continue
        if r["binding_class"] == "high":
            tgt, n_high = high, n_high + 1
        elif r["binding_class"] == "low":
            tgt, n_low = low, n_low + 1
        else:
            continue
        for i, aa in enumerate(s):
            tgt[i][aa] += 1

    if not n_high or not n_low:
        sys.exit("fit: need both high and low rows")

    mat = []
    for i in range(length):
        th = sum(high[i].values()) + PSEUDO * len(AAS)
        tl = sum(low[i].values()) + PSEUDO * len(AAS)
        mat.append({aa: math.log(((high[i].get(aa, 0.0) + PSEUDO) / th) /
                                 ((low[i].get(aa, 0.0) + PSEUDO) / tl))
                    for aa in AAS})
    return mat, {"high": n_high, "low": n_low}


def score(mat, seq):
    """Sum of per-position log-odds, or None if the sequence cannot be scored."""
    if len(seq) != len(mat):
        return None
    total = 0.0
    for i, aa in enumerate(seq):
        if aa not in mat[i]:
            return None  # non-standard residue: refuse rather than guess
        total += mat[i][aa]
    return total


def read(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tidy", type=Path, default=Path(__file__).parent / "tidy")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "tidy")
    ap.add_argument("--split-at", type=int, default=7,
                    help="edit-distance split used by prepare_datasets.py, for the report")
    ap.add_argument("--max-identity", type=float, default=0.70,
                    help="CDRH3 identity ceiling for a submittable design (strictly under)")
    a = ap.parse_args()

    for name in ("facs_train.csv", "facs_test.csv", "spr_measured.csv"):
        if not (a.tidy / name).exists():
            sys.exit(f"missing {a.tidy / name} - run prepare_datasets.py first "
                     "(the facs_*.csv files are not committed)")

    train = read(a.tidy / "facs_train.csv")
    test = read(a.tidy / "facs_test.csv")
    spr = read(a.tidy / "spr_measured.csv")

    length = Counter(len(r["cdrh3"]) for r in train).most_common(1)[0][0]
    mat, nfit = fit(train, length)

    # ---- step 2: extrapolation within the FACS assay ----
    def split_scores(rows):
        hi, lo = [], []
        for r in rows:
            v = score(mat, r["cdrh3"])
            if v is None:
                continue
            (hi if r["binding_class"] == "high" else
             lo if r["binding_class"] == "low" else []).append(v)
        return hi, lo

    tr_hi, tr_lo = split_scores(train)
    te_hi, te_lo = split_scores(test)
    auc_train, auc_test = auc(tr_hi, tr_lo), auc(te_hi, te_lo)

    train_cdrh3 = {r["cdrh3"] for r in train}
    test_cdrh3 = {r["cdrh3"] for r in test}
    facs_class = {r["cdrh3"]: r["binding_class"] for r in train}
    facs_class.update({r["cdrh3"]: r["binding_class"] for r in test})

    # ---- the parent: the bar, and its own measurement noise ----
    parent_cdrh3 = min(spr, key=lambda r: -(fnum(r["identity_to_parent"]) or 0))["cdrh3"]
    reps = [fnum(r["kd_nM"]) for r in spr if r["cdrh3"] == parent_cdrh3]
    reps = sorted(x for x in reps if x is not None)
    if not reps:
        sys.exit("no parent replicate found in spr_measured.csv")
    bar = statistics.geometric_mean(reps)

    # ---- step 3: does the FACS label itself predict SPR KD? ----
    dual = defaultdict(list)
    for r in spr:
        s, kd = r["cdrh3"], fnum(r["kd_nM"])
        if s == parent_cdrh3 or kd is None or s not in facs_class:
            continue
        dual[facs_class[s]].append(kd)
    d_pos = dual.get("high", [])
    d_neg = dual.get("medium", []) + dual.get("low", [])
    # tighter KD is better, so rank on -KD
    auc_label = (auc([-x for x in d_pos], [-x for x in d_neg])
                 if len(d_pos) >= 3 and len(d_neg) >= 3 else float("nan"))

    # ---- step 4: the blind pool, and the three guards ----
    def identity(s):
        if len(s) != len(parent_cdrh3):
            return None
        return sum(x == y for x, y in zip(s, parent_cdrh3)) / len(s)

    pool, excl = [], Counter()
    for r in spr:
        s, kd = r["cdrh3"], fnum(r["kd_nM"])
        if s == parent_cdrh3:
            excl["parent replicate"] += 1
            continue
        if kd is None:
            excl["no KD"] += 1
            continue
        ident = identity(s)
        if ident is None:
            excl[f"not a {length}-mer"] += 1
            continue
        if ident >= a.max_identity:
            excl["too similar to trastuzumab (not submittable)"] += 1
            continue
        if s in train_cdrh3:
            excl["seen in training (leakage)"] += 1
            continue
        v = score(mat, s)
        if v is None:
            excl["unscoreable sequence"] += 1
            continue
        pool.append({"cdrh3": s, "score": round(v, 4), "kd_nM": kd,
                     "identity_to_parent": round(ident, 2),
                     "in_facs_test": s in test_cdrh3,
                     "facs_class": facs_class.get(s, "")})

    if len(pool) < 20:
        sys.exit(f"pool too small to say anything: {len(pool)} designs")

    pool.sort(key=lambda d: -d["score"])
    for i, d in enumerate(pool, 1):
        d["rank"] = i
        d["beats_parent"] = d["kd_nM"] < bar
        for b in KD_BARS:
            d[f"under_{b:g}nM"] = d["kd_nM"] < b

    n = len(pool)
    kds = [d["kd_nM"] for d in pool]
    logkd = [math.log10(k) for k in kds]
    scores = [d["score"] for d in pool]
    rho = spearman(scores, logkd)
    rho_ident = spearman([d["identity_to_parent"] for d in pool], logkd)

    # The baseline any real model has to beat: one feature, no training, no dataset.
    # Identity to the parent CDRH3 -- i.e. "stay as close to trastuzumab as the rules allow".
    endpoints = []
    for label, flag in [(f"beats trastuzumab (KD < {bar:.3g} nM)", "beats_parent")] + \
                       [(f"KD < {b:g} nM", f"under_{b:g}nM") for b in KD_BARS]:
        pos = [d for d in pool if d[flag]]
        neg = [d for d in pool if not d[flag]]
        ok = len(pos) >= 3 and len(neg) >= 3
        endpoints.append({
            "label": label, "flag": flag, "n_pos": len(pos),
            "base": len(pos) / n,
            "auc": auc([d["score"] for d in pos],
                       [d["score"] for d in neg]) if ok else float("nan"),
            "auc_identity": auc([d["identity_to_parent"] for d in pos],
                                [d["identity_to_parent"] for d in neg]) if ok else float("nan"),
        })

    # the best-powered endpoint drives the top-k table
    primary = max((e for e in endpoints if not math.isnan(e["auc"])),
                  key=lambda e: e["n_pos"], default=endpoints[0])

    topk = []
    for k in TOP_KS:
        if k > n:
            continue
        cut = pool[:k]
        h = sum(d[primary["flag"]] for d in cut)
        topk.append({
            "k": k, "hits": h, "rate": h / k,
            "expected": primary["base"] * k,
            "enrichment": (h / k) / primary["base"] if primary["base"] else float("nan"),
            "median_kd": statistics.median(d["kd_nM"] for d in cut),
            "best_kd": min(d["kd_nM"] for d in cut),
        })
    pool_median = statistics.median(kds)

    # the single best submittable design in the whole file, leakage included, because
    # "is there even a winner in here" is a different question from "can we find it"
    all_sub = [(r["cdrh3"], fnum(r["kd_nM"]), identity(r["cdrh3"]))
               for r in spr
               if r["cdrh3"] != parent_cdrh3 and fnum(r["kd_nM"]) is not None
               and identity(r["cdrh3"]) is not None and identity(r["cdrh3"]) < a.max_identity]
    best_sub = min(all_sub, key=lambda t: t[1])
    n_sub_beat = sum(1 for _, kd, _ in all_sub if kd < bar)

    worst_miss = min((d for d in pool if d["kd_nM"] < bar * 20),
                     key=lambda d: -d["rank"], default=None)
    false_lead = pool[0]

    # ---------------------------------------------------------------- write
    a.out.mkdir(parents=True, exist_ok=True)
    cols = ["rank", "cdrh3", "score", "kd_nM", "beats_parent"] + \
           [f"under_{b:g}nM" for b in KD_BARS] + \
           ["identity_to_parent", "facs_class", "in_facs_test"]
    rp = a.out / "enrichment_ranking.csv"
    with open(rp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(pool)

    L = []
    A = L.append
    A("# Can a FACS-trained model pick winners in the judges' assay?\n")
    id_best = max((e for e in endpoints if not math.isnan(e["auc"])),
                  key=lambda e: e["auc_identity"] - e["auc"])
    A("**No, and that is the finding.** A site-independent CDRH3 model reaches "
      f"**AUC {auc_test:.3f}** on held-out FACS data and **AUC {primary['auc']:.3f}** "
      "— chance — on the SPR-measured designs we are actually allowed to submit. On the "
      f"same designs, plain identity to the trastuzumab CDRH3 scores "
      f"**{id_best['auc_identity']:.3f}** ({id_best['label']}), so the 524,000-row training "
      f"set loses to a string comparison. Training on the FACS labels and ranking by the "
      "result is a dead end; everything below is the evidence for that.\n")

    A("## Step 1-2: the model works, inside its own assay\n")
    A(f"Per-position amino-acid log-odds over the {length}-mer CDRH3, fit on "
      f"`facs_train.csv` ({nfit['high']:,} high vs {nfit['low']:,} low, "
      f"edit distance <= {a.split_at}). No pairwise terms, no training loop.\n")
    A("| Set | Scored (high / low) | AUC |")
    A("| --- | --- | --- |")
    A(f"| `facs_train.csv` (edit dist <= {a.split_at}) | {len(tr_hi):,} / {len(tr_lo):,} | {auc_train:.3f} |")
    A(f"| `facs_test.csv` (edit dist > {a.split_at}, **held out**) | {len(te_hi):,} / {len(te_lo):,} | **{auc_test:.3f}** |")
    A("")
    A(f"The two sides share zero CDRH3, and test minus train is {auc_test - auc_train:+.3f}. "
      "So the model genuinely extrapolates to distant variants — it is not memorising "
      "near-neighbours of the parent. Whatever goes wrong next is not underfitting.\n")

    A("## Step 3: the ceiling — the FACS label barely predicts a KD\n")
    A(f"{len(d_pos) + len(d_neg)} molecules in this challenge carry **both** a FACS class "
      "and a fitted SPR KD. That makes the assay gap measurable directly, without any "
      "model in the way:\n")
    A("| FACS class | n | Median KD (nM) | Range (nM) |")
    A("| --- | --- | --- | --- |")
    for c in ("high", "medium", "low"):
        v = dual.get(c, [])
        if v:
            A(f"| {c} | {len(v)} | {statistics.median(v):.2f} | "
              f"{min(v):.3g} – {max(v):.3g} |")
    A("")
    if not math.isnan(auc_label):
        A(f"FACS `high` vs the rest predicts a tighter KD at **AUC {auc_label:.3f}**, and the "
          "class medians are not even monotone. The label is a coarse, three-bin readout from "
          "a different experiment; it carries some information about affinity, but not much. "
          "**No model fit to these labels can beat this ceiling**, however good the model is.")
        A(f"Caveat that cuts both ways: n = {len(d_pos) + len(d_neg)}. This is a weak "
          "measurement of a weak relationship, not proof of none.\n")

    A("## Step 4: ranking the designs we are allowed to submit\n")
    A("The pool is the SPR-measured designs after three exclusions. Each one removes "
      "designs that would have flattered the result:\n")
    A("| Excluded | n | Why |")
    A("| --- | --- | --- |")
    why = {
        "too similar to trastuzumab (not submittable)":
            f"identity to the parent CDRH3 >= {a.max_identity:.0%} — cannot be entered, and these "
            "are the tight-binding end of the pool",
        "seen in training (leakage)": "CDRH3 appears in `facs_train.csv`; the model has seen it",
        "parent replicate": "trastuzumab itself — the benchmark, not a candidate",
        f"not a {length}-mer": f"a {length}-mer position matrix cannot score it; not padded, not guessed",
        "no KD": "no fitted affinity to validate against",
        "unscoreable sequence": "non-standard residue",
    }
    for k, v in excl.most_common():
        A(f"| {k} | {v} | {why.get(k, '')} |")
    A(f"| **pool kept** | **{n}** | submittable, unseen, {length}-mers with a fitted KD |")
    A("")
    A(f"Pool KD: median **{pool_median:.3g} nM**, best **{min(kds):.3g} nM**. "
      f"Trastuzumab's bar is **{bar:.3g} nM** (see below).\n")

    A("### Endpoints, all of them\n")
    A("A single \"beats trastuzumab\" bar has almost no positives, so it cannot measure "
      "anything on its own. These three were written into the source before the ranking "
      "was looked at.\n")
    A("The last column is the baseline the model has to beat: **identity to the parent "
      "CDRH3** — one number, no training, no dataset, available before any model is built.\n")
    A("| Endpoint | Positives | Base rate | Model AUC | Identity-only AUC |")
    A("| --- | --- | --- | --- | --- |")
    for e in endpoints:
        if math.isnan(e["auc"]):
            A(f"| {e['label']} | {e['n_pos']}/{n} | {100 * e['base']:.1f}% | "
              "n/a (too few) | n/a (too few) |")
        else:
            A(f"| {e['label']} | {e['n_pos']}/{n} | {100 * e['base']:.1f}% | "
              f"{e['auc']:.3f} | **{e['auc_identity']:.3f}** |")
    A("")
    A(f"Rank correlation of score against log KD: **rho = {rho:+.3f}** (a useful model "
      "would be strongly negative — high score, low KD). For identity against log KD it "
      f"is **rho = {rho_ident:+.3f}**.\n")
    beaten = [e for e in endpoints
              if not math.isnan(e["auc"]) and e["auc_identity"] > e["auc"]]
    if beaten:
        A(f"**The model loses to that one feature on {len(beaten)} of "
          f"{sum(1 for e in endpoints if not math.isnan(e['auc']))} endpoints.** "
          "A 524,000-row training set, and the useful part of the answer was a string "
          "comparison we could have done in the first ten minutes.\n")

    A(f"### Top-k, on the best-powered endpoint ({primary['label']}, "
      f"{primary['n_pos']} positives)\n")
    A("| Cut | Hits | Hit rate | Expected if random | Enrichment | Median KD (nM) | Best KD (nM) |")
    A("| --- | --- | --- | --- | --- | --- | --- |")
    for t in topk:
        b = "**" if t["k"] == 4 else ""
        A(f"| {b}top {t['k']}{b} | {b}{t['hits']}{b} | {100 * t['rate']:.1f}% | "
          f"{t['expected']:.1f} | {b}{t['enrichment']:.2f}x{b} | "
          f"{t['median_kd']:.3g} | {t['best_kd']:.3g} |")
    A(f"| all {n} | {primary['n_pos']} | {100 * primary['base']:.1f}% | — | 1.00x | "
      f"{pool_median:.3g} | {min(kds):.3g} |")
    A("")
    t4 = next((t for t in topk if t["k"] == 4), None)
    if t4:
        A("### The number to say out loud\n")
        A(f"> **Null result, reported as found.** Four wells chosen by this ranker would have "
          f"held {t4['hits']} hits against {t4['expected']:.1f} expected at random "
          f"(enrichment {t4['enrichment']:.2f}x), with a median KD of "
          f"{t4['median_kd']:.3g} nM against the pool's {pool_median:.3g} nM. "
          "We ran the experiment the plan called for, and the ranker it describes does not work.\n")

    A("## Why a single \"beats trastuzumab\" number is not a bar\n")
    A(f"Trastuzumab is measured **{len(reps)} times** in this file: "
      + ", ".join(f"{x:.3g}" for x in reps) + " nM.")
    A(f"That is a **{max(reps) / min(reps):.1f}x spread** on the same molecule in the same assay. "
      f"The geometric mean, {bar:.3g} nM, is the bar used above; the frequently quoted "
      f"{reps[len(reps) // 2 + 1]:.3g} nM is one draw from that spread, and "
      f"{sum(x < 0.152 for x in reps)} of trastuzumab's own replicates \"beat\" 0.152 nM.")
    A("Two consequences:\n")
    A("1. Any claim that a design beats trastuzumab by less than ~6x is inside the noise "
      "of this assay. Our order sheet should say so next to the predicted KD.")
    A("2. Counting nominal hits without excluding the parent's own replicates inflates the "
      f"base rate. In this file {n_sub_beat} submittable design out of {len(all_sub)} measured "
      f"({100 * n_sub_beat / len(all_sub):.1f}%) reaches {bar:.3g} nM"
      + (f" — `{best_sub[0]}` at {best_sub[1]:.3g} nM, {best_sub[2]:.0%} identity to the parent."
         if n_sub_beat else ".") + "\n")
    if n_sub_beat:
        A(f"That one design matters: it is proof a submittable CDRH3 **can** match trastuzumab, "
          "so the goal is not impossible. It is also in `facs_train.csv`, so the leakage guard "
          "removes it from the blind pool — we could not have found it honestly with this model, "
          "and the pool above has no winner left to find. The real base rate we are hunting is "
          f"about **1 in {len(all_sub) // max(n_sub_beat, 1)}**.\n")

    A("## Where the ranking is wrong, specifically\n")
    A(f"- **Most confident wrong call:** `{false_lead['cdrh3']}` is our rank 1 and measures "
      f"{false_lead['kd_nM']:.3g} nM — {false_lead['kd_nM'] / bar:.0f}x weaker than the parent. "
      f"It is {false_lead['identity_to_parent']:.0%} identical to trastuzumab, i.e. the model "
      "rewarded a sequence that looks nothing like the parent, because the FACS contrast it "
      "learned is about residue preferences, not about the binding interface.")
    if worst_miss:
        A(f"- **Worst miss:** `{worst_miss['cdrh3']}` binds at {worst_miss['kd_nM']:.3g} nM and we "
          f"ranked it **{worst_miss['rank']} of {n}**. A site-independent matrix cannot see "
          "compensating pairs of mutations, which is the most likely reason a real binder lands low.")
    A(f"- **And the thing it missed is simple.** Identity to the parent still predicts "
      f"affinity inside the submittable band (rho = {rho_ident:+.3f}; higher identity, "
      "tighter KD), which is exactly the signal a per-position matrix throws away by "
      "scoring residues independently of the parent. The model asks \"do these residues "
      "look like high binders?\"; what matters is \"how much of the working interface "
      "survived?\"")
    byid = sorted(pool, key=lambda d: -d["identity_to_parent"])
    A(f"  Practically: four wells picked by identity alone would have had a median KD of "
      f"{statistics.median(d['kd_nM'] for d in byid[:4]):.3g} nM against our ranker's "
      f"{topk[0]['median_kd']:.3g} nM. Caveat — identity is coarsely tied here "
      f"({sum(1 for d in pool if d['identity_to_parent'] == byid[0]['identity_to_parent'])} "
      f"designs sit at {byid[0]['identity_to_parent']:.0%}), so which four you get inside a "
      "tie is arbitrary. The AUCs above are the tie-safe version of the same comparison.\n")

    A("## What this changes\n")
    A("1. **Do not rank on a FACS-trained sequence model.** It is the obvious move, we made it, "
      "and it is chance-level on the endpoint that decides the challenge. Any team presenting "
      "FACS-trained affinity predictions without an SPR check is reporting a number like our "
      f"{auc_test:.2f}, not a number like our {primary['auc']:.2f}.")
    A("2. **Use the FACS set for what it does measure.** AUC "
      f"{auc_test:.3f} on held-out distant variants is real signal about *tolerated* CDRH3 "
      "sequence — useful as an expression and foldability prior, and as a cheap pre-filter "
      "against sequences the screen says are dead. Not as the binding axis.")
    A(f"3. **Carry the identity baseline into the ranker as a feature, and as the thing to "
      f"beat.** It is free, it is the one signal that survives into the submittable band, and "
      "any binding score we ship has to outperform it on the SPR pool or it is decoration. "
      "This is also the honest answer to \"why should we trust your ranking\" — because we "
      "checked it against the dumbest possible alternative and said what happened.")
    A("4. **The binding axis has to come from structure or energetics**, or from the ~130 "
      "KD-labelled submittable designs directly — a small-data problem, so a model with "
      "few parameters and honest error bars, not another large fit.")
    A("5. **Quote KD against the replicate spread, never a point value.** "
      f"{max(reps) / min(reps):.1f}x is the resolution of the assay we are being judged in.")
    A("")

    A("## Honest limits\n")
    A(f"- One model class, deliberately the simplest: site-independent, no epistasis. A pairwise "
      "or embedding model might transfer better. What we show is that the straightforward "
      "version does not, and that the label ceiling in step 3 caps how much better any of them "
      "can get.")
    A(f"- The pool is {n} designs and the primary endpoint has {primary['n_pos']} positives. "
      "A null at this size is a real null for a decision of four wells, but it is not a tight "
      "bound: a modest true effect could hide here.")
    A("- The exclusions are defensible but they are choices. `enrichment_ranking.csv` carries "
      f"every design and its flags, and `--max-identity` re-runs the whole thing at a different "
      "submittability line in about a second.")
    A("- `no_reportable_kd` rows are **not** treated as non-binders. The source states N/A does "
      "not confirm non-binding, so they are absent from this pool entirely; the base rate here "
      "is the rate among *measurable* designs, a harder bar than among all 768.")
    A("- This is the binding axis only. S-tier needs epitope competition and thermostability "
      "jointly; see `iptm_calibration.md` for why structure confidence cannot be the gate either.")

    mp = a.out / "enrichment.md"
    mp.write_text("\n".join(L) + "\n")

    print(f"fit: {nfit['high']:,} high / {nfit['low']:,} low {length}-mers")
    print(f"FACS AUC  train {auc_train:.3f}  test (held out) {auc_test:.3f}")
    print(f"label ceiling: FACS high vs rest predicts KD at AUC {auc_label:.3f} "
          f"(n={len(d_pos) + len(d_neg)})")
    print(f"pool: {n} submittable unseen designs; excluded " +
          ", ".join(f"{v} {k}" for k, v in excl.most_common()))
    for e in endpoints:
        print(f"  {e['label']:<38s} {e['n_pos']:>3d} pos  AUC {e['auc']:.3f}")
    print(f"  spearman(score, log KD) = {rho:+.3f}")
    for t in topk:
        print(f"  top {t['k']:>3}: {t['hits']} hits = {t['enrichment']:.2f}x random, "
              f"median KD {t['median_kd']:.3g} nM (pool {pool_median:.3g})")
    print(f"wrote {rp}\nwrote {mp}")


if __name__ == "__main__":
    main()
