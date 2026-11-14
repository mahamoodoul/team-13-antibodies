# The binding axis: we fitted it, validated it blind, and it failed

Owner: Rizve (ranking engine). Written 2026-11-14, before the 16:00 freeze.
Reproduce: `python3 -m fourwells.fit_binding --dry-run`

**Short version.** We fitted the obvious model — a position-specific logistic on
the FACS-labelled CDRH3 variants — and it reached a held-out AUC of **0.873**
against its own label. Then we ranked the 190 SPR-measured designs with it and
it scored **0 of 4, 0 of 10 and 0 of 25**, with the correlation pointing the
wrong way. It is not in the pipeline. `fit_binding.py` refuses to write a model
that fails this check, so the hand-set prior is still what ranks binding.

This is slide 5. It is a stronger result than a working model would have been,
because it is a measured claim about judgment rather than another architecture
diagram.

---

## Three things the SPR data says

### 1. The 6.3% base rate is mostly measurement noise

The reference file states trastuzumab at K_D 0.152 nM and notes that 12 of the
190 measured designs beat it — a 6.3% base rate. The parent appears in that
file **eight times**:

| Parent replicate K_D (nM) |
| --- |
| 0.0285, 0.0379, 0.0792, 0.123, 0.146, 0.152, 0.165, 0.178 |

A 6.2x spread on the identical molecule, and the quoted baseline of 0.152 is
the *worst but one* of its own replicates. **Five of the twelve "winners" are
trastuzumab itself.** Excluding parent replicates the rate is 7 of 182 = 3.8%.

Consequence: "beats 0.152 nM" partly measures which replicate you drew. Any
enrichment number quoted against the 6.3% figure is quoted against noise, and a
judge who checks will find the eight replicates.

### 2. On designs we are allowed to submit, the rate is 0.76%

Our entry rules require CDRH3 identity to trastuzumab **under 70%**. Filtering
the measured set the same way we filter our own:

| Subset | n | beat baseline | rate |
| --- | --- | --- | --- |
| all rows | 190 | 12 | 6.3% |
| non-parent | 182 | 7 | 3.8% |
| **identity < 0.70 — submittable** | **131** | **1** | **0.76%** |

The single submittable design that beat the baseline is `WGGSGPYLFD` at 0.095 nM
(identity 0.6). Six others beat it and are **unsubmittable**, including the
strongest binder in the whole set, `WGSQGFYAYD` at 0.023 nM — which sits at
exactly 0.70 identity and so fails the gate.

### 3. Affinity falls off a cliff with distance from the parent

| CDRH3 identity to parent | n | median K_D |
| --- | --- | --- |
| 0.9 – 1.0 | 23 | **0.18 nM** |
| 0.7 – 0.9 | 33 | 15 nM |
| 0.6 – 0.7 | 34 | 61 nM |
| 0.5 – 0.6 | 32 | 93 nM |
| 0.4 – 0.5 | 29 | 93 nM |
| < 0.4 | 36 | 160 nM |

Monotone across ~900x. The <70% identity rule places every design we may submit
on the far side of that cliff, in the 60-160 nM regime, against a 0.15 nM parent.

---

## Why the fitted model failed

| Metric | Value |
| --- | --- |
| FACS train AUC | 0.905 |
| FACS held-out AUC (split by edit distance) | **0.873** |
| Spearman vs log K_D, all non-parent designs | +0.112 |
| Spearman vs log K_D, **submittable subset** | **+0.292** |
| Top-4 hit rate on the 190 | 0/4 |

Lower K_D is better, so a correct ranker shows a **negative** correlation. A
positive +0.29 means the model ranks good binders *down*. Its top four picks
measured 93, 47, 777 and 17.7 nM. It also ranks the parent's own loop 38th of
190, when the parent is among the best binders in the file.

The model learned FACS class honestly and FACS class does not carry SPR K_D
within this design set. More training rows will not fix a label mismatch, so
this is not a "rerun it on the full 283k" problem — though that rerun is still
worth doing on the VM to confirm.

For comparison, plain distance from the parent — which is what our hand-set
prior encodes — gets the sign right: Spearman **−0.41** across all non-parent
designs. Inside the submittable band it weakens to −0.23, which is honest but
thin.

---

## What this means for which four we send

1. **Do not spend wells chasing affinity.** The measured probability that a
   submittable design beats trastuzumab's K_D is about 1 in 131. Four wells
   aimed at that axis is an expected 0.03 S-tier designs.
2. **Use binding as a floor, not a ranking signal.** The useful question is not
   "will this beat 0.15 nM" but "will this stay off the 100 nM cliff". Distance
   from the parent predicts that at ρ = −0.41, and our prior already penalises
   it. Keep the penalty; stop reading the column as predicted affinity.
3. **The leverage is stability and epitope.** This is what the plan already
   argued from the EGFR literature — "pick the beatable axis" — and it is now
   measured on our own target rather than inferred.
4. **Sanity-check any S-tier claim.** S-tier needs binding too. If the honest
   binding probability for a submittable design is ~1%, then our realistic
   target is A-tier on stability plus non-inferior binding, and we should say
   so on stage rather than claim three axes we cannot support.

## Caveats, stated before someone asks

- Fitted on the committed 2,000-row fixture, not the full 283,608-row training
  split. Rerun on the VM: `--train proof/tidy/facs_train.csv`.
- One SPR validation loop also appears in the training fixture. The leakage
  check reports it; it inflates the fitted model's numbers, which failed anyway.
- FACS affinity class and SPR K_D are different assays. That difference is the
  finding, not a defect in Mahamoodoul's tidying — the split and the manifest
  are clean and the leakage check is built on them.
- 190 rows, and the 0.76% submittable rate rests on a single positive. The
  direction is solid; the precise number is not.
