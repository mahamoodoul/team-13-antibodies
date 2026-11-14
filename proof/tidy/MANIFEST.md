# Tidy datasets — manifest

Built 2026-11-14 by `proof/prepare_datasets.py` from `/home/hackathon/data`.
Owner: Mahamodul (proof lane). Consumers: Rizve (gates, predictors), Ansarul (fixtures).

## Files

| File | Rows | What it is |
| --- | --- | --- |
| `facs_variants.csv` | 524,346 | All CDRH3 variants, FACS class, distance to parent |
| `facs_train.csv` | 283,608 | edit_distance <= 7 — fit here |
| `facs_test.csv` | 240,738 | edit_distance > 7 — **held out** |
| `spr_designs.csv` | 768 | Optimisation designs, all outcomes |
| `spr_measured.csv` | 190 | Fitted KD only — **blind validation** |
| `iptm_pairs.csv` | 24,550 | Long-form ipTM, 3 models |
| `fixtures/*.csv` | <=2,000 each | Samples for fast iteration (seed 13) |

The three `facs_*.csv` files total ~260 MB and are **not committed**; rerun this
script to rebuild them from the source zip. Everything else here is in git, because
the VM is wiped at the end of the day.

## The held-out split

Split axis: **edit distance to the trastuzumab CDRH3** (`WGGDGFYAMD`), at **7**.
Not random. Our submissions must clear <70% CDRH3 identity to trastuzumab, so every
design we ship sits in the distant regime. Training on near-neighbours and testing on
distant variants is the only split that measures the extrapolation we actually need.

- train 283,608 rows · test 240,738 rows · 46% held out
- shared CDRH3 between the two sides: **0** (no leakage)

| Class | All | Train | Test | Train % | Test % |
| --- | --- | --- | --- | --- | --- |
| low | 162,186 | 66,277 | 95,909 | 23% | 40% |
| medium | 190,011 | 101,966 | 88,045 | 36% | 37% |
| high | 172,149 | 115,365 | 56,784 | 41% | 24% |

**Class balance is not preserved, and that is the point.** High binders fall from
41% of train to 24% of test, low binders rise from 23% to 40%:
more mutations means worse binding. Two consequences, both of which must be
respected or the headline number is meaningless:

1. Raw accuracy is not comparable across the two sides. Report per-class metrics, or
   balanced accuracy, or ranking metrics — never a single accuracy figure.
2. A classifier that always predicts "low" already scores 40% on the test set.
   That is the baseline to beat, not 33%.

Edit-distance distribution: 1:50, 2:600, 3:1,490, 4:6,392, 5:28,510, 6:86,438, 7:160,128, 8:150,838, 9:70,161, 10:19,739

## SPR validation set

190 of 768 designs carry a fitted KD. Range 0.0234389–13863.2 nM, median 66.0271 nM.
Outcomes: quantified_binding 190, no_reportable_kd 460, inconclusive 104, not_reported 14
CDRH3 lengths: {9: 20, 10: 740, 16: 8} — the 9-mers and 16-mers are not
comparable to the 10-mer FACS set; filter to length 10 before scoring against it.

Same assay the judges use. Rank these blind; never fit on them.

## ipTM pairs — read this before using them

Cross-pairing matrices: 91 VHH x 91 antigen. Diagonal = cognate (known binders),
off-diagonal = **shuffled** non-binding pairs. Shuffled pairs are computational,
**not SPR-measured**. The separate SPR table has only 29 rows.

| Model | Cognate | Non-cognate | Cognate >=0.7 | Non-cognate >=0.7 |
| --- | --- | --- | --- | --- |
| af3 | 91 | 8,137 | 43 (47%) | 246 (3%) |
| boltz2 | 91 | 8,190 | 90 (99%) | 7,723 (94%) |
| chai1 | 89 | 7,952 | 7 (8%) | 17 (0%) |

A single 0.7 cutoff means three different things across these models. Pick any
cutoff from the curve per model — see `calibrate_iptm.py` — never from a round number.

## Provenance

- FACS variants and SPR designs: Chinery et al., trastuzumab CDRH3 deep mutational scan.
- ipTM matrices and SPR table: Smorodina et al., *Structural Plausibility Without Binding
  Specificity*, bioRxiv 2026, doi 10.64898/2026.03.02.709004.
- The SPR table was extracted from the paper's supplementary PDF and is not in the Zenodo
  archives. The authors state: "N/A denotes no reportable affinity fit, NOT confirmed
  non-binding." Do not relabel those rows as measured true negatives.
