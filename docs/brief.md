# The brief

Reference for team-13. [Setup is in the README](../README.md) — this is everything else.

Source: organisers' task description, 6 Nov 2026 ·
[hackathon site](https://oslo-ai-antibodies-hackathon.vercel.app)

## The task

Improve **trastuzumab** (anti-HER2), either by point mutations (*optimisation*) or by
designing a new antibody that keeps the original epitope (*de novo*). Adaptyv expresses
the designs cell-free and measures:

| Property | Measured by |
| --- | --- |
| Binding to HER2 | SPR |
| Epitope preservation | competitive binding vs trastuzumab |
| Thermostability | direct measurement |

Tiers are counted per design against the measured trastuzumab baseline: **S** beats all
three, **A** two, **B** one. Teams rank by S-tier count first, then A, then B — so two
S-tier designs beat ten B-tier ones.

## Submission rules

`abguard` checks every design before submission. **A design that fails is rejected, never
moved to the other track.** The track is decided for you, by identity to known antibodies.

Shared, every design:

- format is VHH, scFv or Fab
- ≤250 aa total (combined for VH + VL)
- no unpaired cysteines
- immunum numbering confidence ≥0.1

| Track | Entry condition | Extra requirement |
| --- | --- | --- |
| De novo | <70% identity to any known antibody | ≥2 CDRH3 mutations from trastuzumab |
| Optimisation | everything else | <70% CDRH3 identity to trastuzumab **and** >2 point mutations from any provided antibody |

A design has to express to be measured at all. Adaptyv's earlier rounds improved once
teams pre-screened with **Aggrescan 3D, SoluProt, NetSolP** and **ProteinMPNN soluble
weights** — cheap, worth running before ranking.

## Data we were given

| Dataset | Size | Modality |
| --- | --- | --- |
| Trastuzumab CDRH3 variants vs HER2 | 524,346 variants, ≤10 mutated positions | FACS, 3 affinity classes |
| Optimisation designs, same study | ~700, 190 measured | SPR |
| VHH–antigen true negatives | 454 pairs (21 with AF3 ipTM ≥0.7) | SPR, no measurable binding |
| Cognate VHH–antigen affinities | 15 | SPR, all sub-µM |
| Non-cognate interactions | 2 | binary off-target label |
| Predicted complexes | 1.8M structures, AF3 + Boltz-2 + Chai-1 | computational |

The true negatives are the valuable ones — pairs measured *not* to bind, including 21 that
score ipTM ≥0.7. They are the only way to calibrate a structure-confidence cutoff before
trusting it to rank our designs.

Published sets: Chinery et al. (CDRH3 variants) and Smorodina et al. (complexes), both on Zenodo.

## Models

### On the VM — Apheris Foundry

Structure prediction, all same inputs/outputs so they are swappable:
OpenFold3, Protenix v2/v1, Boltz-2, Boltz-1, Mol-1, ESMFold2.
All take a template except Boltz-1 and ESMFold2.

RFD4-Proteina design weights, measured on the trastuzumab CDRH3 task:

| Weight | Known binders | Passes novelty | Interface err | Use for |
| --- | --- | --- | --- | --- |
| `antibody-2026-10-30` | 0% | 100% | 8.2 Å | any CDR, fixed framework |
| `her2-2026-11-07` balanced (`--sequence-tsr-k 2`) | 21% | 6% | 9.1 Å | CDRH3, leans on measured binders |
| `her2-2026-11-07` exploratory (`-k 1`) | 0.3% | 74% | 9.1 Å | CDRH3, more varied loops |
| `her2-novel-2026-11-09` | 4% | 86% | **6.8 Å** | CDRH3, best confident fit |

The `her2-*` weights only redesign CDRH3; use `antibody-2026-10-30` for other CDRs.
**A known binder fails the novelty filter**, so filter before ranking.

Pipeline: `design` → `refold-prepare` → fold with a template-taking model → `refold-score`.
Avoid ESMFold2 for binders — it folds the target unguided, which flatters the result.
The pass column is empty for this exercise, so rank on `min_ipae`, `iptm`, `binder_plddt`.
Worked example: `rfd4-proteina/docs/Tutorial.html` in the data bucket.

### Nebius — 34 models with tested input formats

`boltz2` (~80s) · `nanobodybuilder2` (~2m) · `abodybuilder3` (~2m) · `antifold` (~110s) ·
`stab-ddg` (~12m, ddG for point mutations — our thermostability axis) · `proteinmpnn` (~100s) ·
`rfd4-proteina` (~5m) · `esm2-650m` (~4m) · `openfold3` · `rfdiffusion` · MD engines.

### JapanFold — the three nothing else gives us

**RoseTTAFold3**, **OpenDDE** (antibody–antigen complexes) and **AF2-IG** (scores a binder
you already designed — slots into our ranking step). Plus BoltzGen, RFdiffusion3, PXDesign,
Mol-1, ESMC, SaProt. $0.26/processor-hour, no charge for queueing or failed runs.

## Scoring

**Pitch, today:** 40% judgment (reasoning behind the molecules) · 20% execution
(reproducible pipeline in this repo) · 20% user fit · 20% path to value.

Placing buys wet-lab slots — every team gets 4 designs tested, 1st 16, 2nd 12, 3rd 8,
and each of 6 judges nominates a favourite for +2. We submit a ranked list of up to 20.

**Prizes:** €3000 split evenly across the two tracks (€800 / €500 / €200 each), plus $500
best pitch. AMASS separately awards a free month for best use of their platform.
