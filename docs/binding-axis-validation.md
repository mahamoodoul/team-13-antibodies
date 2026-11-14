# The binding axis: we fitted it, validated it blind, and it failed

Owner: Rizve (ranking engine). Written 2026-11-14, before the 16:00 freeze.
Reproduce: `python3 -m fourwells.fit_binding --dry-run`

**Short version.** We fitted the obvious model — a position-specific logistic on
the FACS-labelled CDRH3 variants — and it reached a held-out AUC of **0.873**
against its own label. Then we ranked the 190 SPR-measured designs with it and
it scored **0 of 4, 0 of 10 and 0 of 25**, with the correlation pointing the
wrong way. It is not in the pipeline. `fit_binding.py` refuses to write a model
that fails this check, so the hand-set prior is still what ranks binding.

> **UPDATE 14:50 — read the last section.** The finding below is about the
> *additive* model and it stands. A different fitted model, the CDRH3
> transformer, passes the same blind check (rho −0.393, AUC 0.663/0.729) and now
> ranks the binding column. The prior is now the fallback for unseen loops.

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

---

## UPDATE 14:50 — a different fitted model passes the same check

The finding above is about the **additive** model (a position-specific logistic,
one weight per position/residue). It is correct and it stands. But it is not the
only fitted model we have, and it should not have closed the question.

The CDRH3 **transformer** in `~/ansarul` was also trained on the FACS labels,
and it was ranked against the same blind SPR rows. Run it yourself:

```bash
cd ~/ansarul && ./.venv/bin/python -I validate_spr.py
```

| Model | rho vs log K_D (n=152 unseen) | AUC K_D<10 nM | AUC K_D<1 nM | Top-10 under 10 nM |
| --- | --- | --- | --- | --- |
| additive PSSM | −0.149 (p=0.07) | 0.579 | 0.496 | 1/10 |
| **CDRH3 transformer** | **−0.393 (p=6e−7)** | **0.663** | **0.729** | **6/10** |

Base rate among the 152: 29/152 under 10 nM. The transformer's sign is correct,
the correlation is significant, and it finds 6 of the top 10 tight binders
against a 1.9-in-10 base rate. It also survives the distance confound the doc
above warns about: Spearman with substitutions-from-parent controlled is
**−0.276**, so it is not just counting mutations.

This does not overturn the caution above — binding is still weak evidence at our
designs' distance, and the ~1% submittable base rate still governs what to
expect from four wells. What changes is only this: the pipeline's binding column
no longer has to be a prior that can only penalise change. It is now the
transformer, serialised as `data/models/binding_cdrh3.json` (`kind:
"cdrh3_table"`) by `~/ansarul/export_transformer_table.py`, with the checkpoint
sha256 in the file. A loop the table has never seen — an unseen target, a
non-10-mer de novo loop — falls back to the prior deliberately; the additive PSSM
is **not** used as that fallback, because it is the model that failed the check.

The distance-binned caveat travels in the file's `heldout` block: the scorer is
0.875 at 3 substitutions from training, 0.666 at 4, 0.504 at 5. The column ranks;
it is not a K_D.
