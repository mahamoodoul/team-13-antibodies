# Can a FACS-trained model pick winners in the judges' assay?

**No, and that is the finding.** A site-independent CDRH3 model reaches **AUC 0.879** on held-out FACS data and **AUC 0.508** — chance — on the SPR-measured designs we are actually allowed to submit. On the same designs, plain identity to the trastuzumab CDRH3 scores **0.750** (KD < 1 nM), so the 524,000-row training set loses to a string comparison. Training on the FACS labels and ranking by the result is a dead end; everything below is the evidence for that.

## Step 1-2: the model works, inside its own assay

Per-position amino-acid log-odds over the 10-mer CDRH3, fit on `facs_train.csv` (115,365 high vs 66,277 low, edit distance <= 7). No pairwise terms, no training loop.

| Set | Scored (high / low) | AUC |
| --- | --- | --- |
| `facs_train.csv` (edit dist <= 7) | 115,365 / 66,277 | 0.888 |
| `facs_test.csv` (edit dist > 7, **held out**) | 56,784 / 95,909 | **0.879** |

The two sides share zero CDRH3, and test minus train is -0.008. So the model genuinely extrapolates to distant variants — it is not memorising near-neighbours of the parent. Whatever goes wrong next is not underfitting.

## Step 3: the ceiling — the FACS label barely predicts a KD

27 molecules in this challenge carry **both** a FACS class and a fitted SPR KD. That makes the assay gap measurable directly, without any model in the way:

| FACS class | n | Median KD (nM) | Range (nM) |
| --- | --- | --- | --- |
| high | 16 | 7.20 | 0.09 – 174 |
| medium | 6 | 4.20 | 0.471 – 139 |
| low | 5 | 15.37 | 0.443 – 94 |

FACS `high` vs the rest predicts a tighter KD at **AUC 0.608**, and the class medians are not even monotone. The label is a coarse, three-bin readout from a different experiment; it carries some information about affinity, but not much. **No model fit to these labels can beat this ceiling**, however good the model is.
Caveat that cuts both ways: n = 27. This is a weak measurement of a weak relationship, not proof of none.

## Step 4: ranking the designs we are allowed to submit

The pool is the SPR-measured designs after three exclusions. Each one removes designs that would have flattered the result:

| Excluded | n | Why |
| --- | --- | --- |
| too similar to trastuzumab (not submittable) | 48 | identity to the parent CDRH3 >= 70% — cannot be entered, and these are the tight-binding end of the pool |
| seen in training (leakage) | 17 | CDRH3 appears in `facs_train.csv`; the model has seen it |
| parent replicate | 8 | trastuzumab itself — the benchmark, not a candidate |
| not a 10-mer | 3 | a 10-mer position matrix cannot score it; not padded, not guessed |
| **pool kept** | **114** | submittable, unseen, 10-mers with a fitted KD |

Pool KD: median **138 nM**, best **0.185 nM**. Trastuzumab's bar is **0.0954 nM** (see below).

### Endpoints, all of them

A single "beats trastuzumab" bar has almost no positives, so it cannot measure anything on its own. These three were written into the source before the ranking was looked at.

The last column is the baseline the model has to beat: **identity to the parent CDRH3** — one number, no training, no dataset, available before any model is built.

| Endpoint | Positives | Base rate | Model AUC | Identity-only AUC |
| --- | --- | --- | --- | --- |
| beats trastuzumab (KD < 0.0954 nM) | 0/114 | 0.0% | n/a (too few) | n/a (too few) |
| KD < 1 nM | 6/114 | 5.3% | 0.480 | **0.750** |
| KD < 10 nM | 10/114 | 8.8% | 0.508 | **0.610** |

Rank correlation of score against log KD: **rho = -0.058** (a useful model would be strongly negative — high score, low KD). For identity against log KD it is **rho = -0.243**.

**The model loses to that one feature on 2 of 2 endpoints.** A 524,000-row training set, and the useful part of the answer was a string comparison we could have done in the first ten minutes.

### Top-k, on the best-powered endpoint (KD < 10 nM, 10 positives)

| Cut | Hits | Hit rate | Expected if random | Enrichment | Median KD (nM) | Best KD (nM) |
| --- | --- | --- | --- | --- | --- | --- |
| **top 4** | **0** | 0.0% | 0.4 | **0.00x** | 102 | 17.7 |
| top 10 | 0 | 0.0% | 0.9 | 0.00x | 102 | 17.7 |
| top 25 | 2 | 8.0% | 2.2 | 0.91x | 124 | 0.368 |
| top 50 | 5 | 10.0% | 4.4 | 1.14x | 112 | 0.368 |
| all 114 | 10 | 8.8% | — | 1.00x | 138 | 0.185 |

### The number to say out loud

> **Null result, reported as found.** Four wells chosen by this ranker would have held 0 hits against 0.4 expected at random (enrichment 0.00x), with a median KD of 102 nM against the pool's 138 nM. We ran the experiment the plan called for, and the ranker it describes does not work.

## Why a single "beats trastuzumab" number is not a bar

Trastuzumab is measured **8 times** in this file: 0.0285, 0.0379, 0.0792, 0.123, 0.146, 0.152, 0.165, 0.178 nM.
That is a **6.2x spread** on the same molecule in the same assay. The geometric mean, 0.0954 nM, is the bar used above; the frequently quoted 0.152 nM is one draw from that spread, and 5 of trastuzumab's own replicates "beat" 0.152 nM.
Two consequences:

1. Any claim that a design beats trastuzumab by less than ~6x is inside the noise of this assay. Our order sheet should say so next to the predicted KD.
2. Counting nominal hits without excluding the parent's own replicates inflates the base rate. In this file 1 submittable design out of 131 measured (0.8%) reaches 0.0954 nM — `WGGSGPYLFD` at 0.095 nM, 60% identity to the parent.

That one design matters: it is proof a submittable CDRH3 **can** match trastuzumab, so the goal is not impossible. It is also in `facs_train.csv`, so the leakage guard removes it from the blind pool — we could not have found it honestly with this model, and the pool above has no winner left to find. The real base rate we are hunting is about **1 in 131**.

## Where the ranking is wrong, specifically

- **Most confident wrong call:** `YNAGMYVYTG` is our rank 1 and measures 124 nM — 1300x weaker than the parent. It is 0% identical to trastuzumab, i.e. the model rewarded a sequence that looks nothing like the parent, because the FACS contrast it learned is about residue preferences, not about the binding interface.
- **Worst miss:** `WKGYGSYVHD` binds at 0.723 nM and we ranked it **112 of 114**. A site-independent matrix cannot see compensating pairs of mutations, which is the most likely reason a real binder lands low.
- **And the thing it missed is simple.** Identity to the parent still predicts affinity inside the submittable band (rho = -0.243; higher identity, tighter KD), which is exactly the signal a per-position matrix throws away by scoring residues independently of the parent. The model asks "do these residues look like high binders?"; what matters is "how much of the working interface survived?"
  Practically: four wells picked by identity alone would have had a median KD of 60.7 nM against our ranker's 102 nM. Caveat — identity is coarsely tied here (32 designs sit at 60%), so which four you get inside a tie is arbitrary. The AUCs above are the tie-safe version of the same comparison.

## What this changes

1. **Do not rank on a FACS-trained sequence model.** It is the obvious move, we made it, and it is chance-level on the endpoint that decides the challenge. Any team presenting FACS-trained affinity predictions without an SPR check is reporting a number like our 0.88, not a number like our 0.51.
2. **Use the FACS set for what it does measure.** AUC 0.879 on held-out distant variants is real signal about *tolerated* CDRH3 sequence — useful as an expression and foldability prior, and as a cheap pre-filter against sequences the screen says are dead. Not as the binding axis.
3. **Carry the identity baseline into the ranker as a feature, and as the thing to beat.** It is free, it is the one signal that survives into the submittable band, and any binding score we ship has to outperform it on the SPR pool or it is decoration. This is also the honest answer to "why should we trust your ranking" — because we checked it against the dumbest possible alternative and said what happened.
4. **The binding axis has to come from structure or energetics**, or from the ~130 KD-labelled submittable designs directly — a small-data problem, so a model with few parameters and honest error bars, not another large fit.
5. **Quote KD against the replicate spread, never a point value.** 6.2x is the resolution of the assay we are being judged in.

## Honest limits

- One model class, deliberately the simplest: site-independent, no epistasis. A pairwise or embedding model might transfer better. What we show is that the straightforward version does not, and that the label ceiling in step 3 caps how much better any of them can get.
- The pool is 114 designs and the primary endpoint has 10 positives. A null at this size is a real null for a decision of four wells, but it is not a tight bound: a modest true effect could hide here.
- The exclusions are defensible but they are choices. `enrichment_ranking.csv` carries every design and its flags, and `--max-identity` re-runs the whole thing at a different submittability line in about a second.
- `no_reportable_kd` rows are **not** treated as non-binders. The source states N/A does not confirm non-binding, so they are absent from this pool entirely; the base rate here is the rate among *measurable* designs, a harder bar than among all 768.
- This is the binding axis only. S-tier needs epitope competition and thermostability jointly; see `iptm_calibration.md` for why structure confidence cannot be the gate either.
