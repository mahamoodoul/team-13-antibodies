# Calibrating a structure-confidence cutoff

91 cognate VHH-antigen pairs (known binders) vs ~8,100 **shuffled** pairs per model.
Shuffled pairs are computational non-binders from the Champloo benchmark, not
measurements. Source: Smorodina et al., bioRxiv 2026, doi 10.64898/2026.03.02.709004.

## How well does ipTM separate binders from shuffled pairs at all?

| Model | AUC | Cognate median | Shuffled median | Verdict |
| --- | --- | --- | --- | --- |
| af3 | **0.754** | 0.50 | 0.18 | weak |
| boltz2 | **0.645** | 0.91 | 0.88 | near-useless |
| chai1 | **0.568** | 0.21 | 0.19 | near-useless |

## What the round number (0.7) actually does

| Model | Cognate kept | Shuffled passed | Precision |
| --- | --- | --- | --- |
| af3 | 43/91 (47%) | 246/8,137 (3%) | 0.149 |
| boltz2 | 90/91 (99%) | 7,723/8,190 (94%) | 0.011 |
| chai1 | 7/89 (8%) | 17/7,952 (0%) | 0.292 |

The same number means three different things. This is the finding.

## Recommended cutoff per model

Two defensible rules: maximise Youden's J, or hold shuffled pass-through at <=5%.

| Model | Best J cutoff | Cognate kept | Shuffled passed | Cutoff at <=5% shuffled | Cognate kept there |
| --- | --- | --- | --- | --- | --- |
| af3 | **0.69** | 44/91 (48%) | 260 (3.2%) | 0.57 | 45/91 (49%) |
| boltz2 | **0.93** | 38/91 (42%) | 1,569 (19.2%) | 0.95 | 16/91 (18%) |
| chai1 | **0.49** | 14/89 (16%) | 176 (2.2%) | 0.39 | 15/89 (17%) |

## What to do with this

1. **Gate on af3 ipTM only.** It is the one model here that separates
   binders from shuffled pairs at all (AUC 0.754), and even that is weak.
   Its best cutoff, 0.69, sits within noise of the round
   0.70 — so 0.70 is defensible for af3, but now we can say *why*,
   and we know its price: it keeps only 48% of known binders.
2. **Do not gate on boltz2 ipTM.** AUC 0.645; at 0.70 it admits 94% of shuffled pairs (7,723 of 8,190) - it rejects almost nothing.
3. **Do not gate on chai1 ipTM.** AUC 0.568; at 0.70 it discards 92% of *known binders* (keeps 7/89) - its whole distribution sits below 0.70, so the cutoff is on the wrong scale.
4. **Treat confidence as a weak prior, never a hard gate.** At the best cutoff
   available anywhere here, 3.2% of shuffled pairs still clear it
   while 52% of real binders are thrown away.
   Rank on the joint score; use confidence to break ties, not to exclude.

## Honest limits

- Shuffled pairs are computational non-binders, not SPR measurements. They are a
  model of non-binding, and the curve inherits that assumption.
- 91 cognate pairs is a small positive set; the cutoffs carry real uncertainty.
- This is VHH-antigen data, not trastuzumab-HER2. It calibrates how much to trust
  a confidence score in general, not HER2 binding specifically.
- The measured counterexample is stronger than any of this: 8w90_a binds CD4 at
  7.41 nM with AF3 ipTM 0.12. One confirmed binder a confidence filter throws away.
