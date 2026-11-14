# Which split do we report?

The organisers ship ready-made HER2 splits. We had built our own. Both are valid and
they measure different things, so we report both — the provided one for comparability,
ours as the harder test that matches what we actually ship.

## The provided splits check out

| Check | clonotype_split | random_split |
| --- | --- | --- |
| Total rows | 524,346 | 524,346 |
| Unique CDRH3s | 524,346 | 524,346 |
| `label`==1 differs from class "high" | 0 rows | 0 rows |
| Sequences shared train↔test | 0 | 0 |
| Clonotype clusters shared train↔test | 0 | n/a |

Both reconstruct the full FACS set (524,346 rows), and `label` is exactly
the "high" FACS class — so the provided task is binary high-vs-rest, not 3-class.
**Use their label definition**, or our numbers will not be comparable to anyone else's.

## But neither asks a predictor to extrapolate

First, a threshold that does *not* separate anything, so nobody wastes time on it:
4+ mutated positions is the <70%-identity regime every design we ship sits in,
but 99.6% of the FACS set is already there. It is not a useful axis for splitting.

The axis that does differ is whether the test set reaches *beyond* the distances seen
in training. Edit-distance range and mean per part:

| Split | Train | Val | Test |
| --- | --- | --- | --- |
| clonotype_split | 2–10 (mean 7.4) | 1–10 (mean 7.3) | 2–10 (mean 7.2) |
| random_split | 1–10 (mean 7.3) | 1–10 (mean 7.3) | 1–10 (mean 7.3) |
| **ours (edit distance)** | 1–7 (mean 6.4) | — | 8–10 (mean 8.5) |

Both provided splits span the full 1–10 range on every side: a model is only ever asked
to interpolate, among distances it has already seen. Ours makes train and test
**disjoint** — train stops at 7, test starts at 8, 0 shared sequences — so it
measures the one thing the provided splits cannot, which is whether the ranker survives
a step past its training distribution.

Neither is better. Clonotype clustering kills similarity leakage, which our split does
not even attempt; our split probes extrapolation, which theirs does not. Hence both.

## Positive-class rate, which sets the baseline to beat

| Split | Train | Val | Test |
| --- | --- | --- | --- |
| clonotype_split | 32.8% | 32.8% | 32.8% |
| random_split | 32.8% | 32.8% | 32.8% |
| **ours (edit distance)** | 40.7% | — | 23.6% |

The provided splits are stratified, so the positive rate is flat and the majority-class
baseline is the same everywhere. Ours is not stratified by design: high binders get
rarer with distance, falling to 23.6% in the held-out slice. Quoting raw
accuracy across the two is meaningless; report AUC or balanced accuracy.

## What we do

1. **Headline number on `clonotype_split`.** It is the provided split, clustered to
   stop near-neighbour leakage, and comparable to every other team and to the
   published baselines that ship with it.
2. **Second number on our edit-distance split**, reported as the harder case: how the
   ranker holds up at the distance our own submissions sit at. Expect it to be worse.
   Showing both, with the drop named, reads as careful rather than lucky.
3. **Never report `random_split`** except as the leakage control that shows why the
   other two are needed.
4. **Adopt `label` = FACS class "high"** everywhere, so our numbers compare.

## Edit-distance distributions

**clonotype_split**

| Part | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | 0 | 226 | 596 | 2,982 | 17,258 | 59,392 | 115,589 | 107,389 | 49,399 | 14,213 |
| val | 50 | 343 | 750 | 2,069 | 3,919 | 10,993 | 22,387 | 25,174 | 11,867 | 1,099 |
| test | 0 | 31 | 144 | 1,341 | 7,333 | 16,053 | 22,152 | 18,275 | 8,895 | 4,427 |

**random_split**

| Part | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | 29 | 413 | 1,054 | 4,495 | 19,889 | 60,371 | 112,034 | 105,627 | 49,244 | 13,886 |
| val | 11 | 89 | 200 | 965 | 4,377 | 12,926 | 24,031 | 22,731 | 10,424 | 2,898 |
| test | 10 | 98 | 236 | 932 | 4,244 | 13,141 | 24,063 | 22,480 | 10,493 | 2,955 |

**ours (edit distance)**

| Part | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | 50 | 600 | 1,490 | 6,392 | 28,510 | 86,438 | 160,128 | 0 | 0 | 0 |
| test | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 150,838 | 70,161 | 19,739 |
