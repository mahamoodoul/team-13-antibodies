# FourWells — shortlist

*2026-11-14 14:47 · 4 designs for 4 lab slots · chosen from 197 eligible of 401 generated*

Every axis is scored against trastuzumab at 0.50. S-tier requires beating the
baseline on all three at once, so the joint score is a product, not a mean: a
design that is excellent on two axes and hopeless on the third is not a candidate.

## The four

| # | design | track | CDRH3 | subs | binding | epitope | stability | joint |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `optA-her2_cdrh3_93` | optimisation | `STAAVGYAMD` | 6 | 0.34 ▼ | 0.50 ≈ | 0.56 ▲ | 0.096 |
| 2 | `optB-her2_cdrh3_41` | optimisation | `YEQPGVMAMT` | 7 | 0.29 ▼ | 0.50 ≈ | 0.54 ▲ | 0.078 |
| 3 | `optA-her2_cdrh3_84` | optimisation | `SAPPPAFAFD` | 8 | 0.26 ▼ | 0.46 ▼ | 0.60 ▲ | 0.071 |
| 4 | `optB-her2_cdrh3_55` | optimisation | `YGSRGLHEYD` | 7 | 0.11 ▼ | 0.50 ≈ | 0.56 ▲ | 0.031 |

## Dossiers

### 1. `optA-her2_cdrh3_93`

**Hypothesis.** Joint P(S-tier) 0.096 = binding 0.34 x epitope 0.50 x stability 0.56, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-novel-2026-11-09` |
| CDRH3 | `STAAVGYAMD` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.096 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.34 ▼ — CDRH3 scores -0.66 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- **epitope** 0.50 ≈ — predicted complex covers 70% of the annotated domain IV epitope
- **stability** 0.56 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, loop_glycine +0.05

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard pass  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: CDRH3 scores -0.66 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- Epitope: predicted complex covers 70% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, loop_glycine +0.05
- Represents cluster c40 — optimisation track, trastuzumab scaffold, CDRH3 family SNSDYGYAMD (8 designs). Chosen over 7 siblings sharing this hypothesis, so a failure here costs us one idea, not the shortlist.
- On the list because its strongest axis is stability (0.56) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.34). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRSTAAVGYAMDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 2. `optB-her2_cdrh3_41`

**Hypothesis.** Joint P(S-tier) 0.078 = binding 0.29 x epitope 0.50 x stability 0.54, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `YEQPGVMAMT` (7 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.078 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.29 ▼ — CDRH3 scores -0.89 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- **epitope** 0.50 ≈ — predicted complex covers 70% of the annotated domain IV epitope
- **stability** 0.54 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.50 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, patch_burden -0.15

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.30 < 0.70 · 7 substitutions · abguard pass  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: CDRH3 scores -0.89 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- Epitope: predicted complex covers 70% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.50 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, patch_burden -0.15
- Represents cluster c118 — optimisation track, trastuzumab scaffold, CDRH3 family YEQPGVMAMT (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.54) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.29). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRYEQPGVMAMTYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 3. `optA-her2_cdrh3_84`

**Hypothesis.** Joint P(S-tier) 0.071 = binding 0.26 x epitope 0.46 x stability 0.60, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-novel-2026-11-09` |
| CDRH3 | `SAPPPAFAFD` (8 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.071 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.26 ▼ — CDRH3 scores -1.05 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- **epitope** 0.46 ▼ — predicted complex covers 65% of the annotated domain IV epitope
- **stability** 0.60 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, loop_proline +0.10

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.20 < 0.70 · 8 substitutions · abguard pass  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: CDRH3 scores -1.05 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- Epitope: predicted complex covers 65% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, loop_proline +0.10
- Represents cluster c103 — optimisation track, trastuzumab scaffold, CDRH3 family SAPPPAFAFD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.60) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.26). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRSAPPPAFAFDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 4. `optB-her2_cdrh3_55`

**Hypothesis.** Joint P(S-tier) 0.031 = binding 0.11 x epitope 0.50 x stability 0.56, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `YGSRGLHEYD` (7 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.031 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.11 ▼ — CDRH3 scores -2.07 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- **epitope** 0.50 ≈ — predicted complex covers 70% of the annotated domain IV epitope
- **stability** 0.56 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.16, abs_net_charge +0.05

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.30 < 0.70 · 7 substitutions · abguard pass  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: CDRH3 scores -2.07 (log-odds) against trastuzumab's own loop under the CDRH3 transformer fitted on the 524k FACS-labelled variants
- Epitope: predicted complex covers 70% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.16, abs_net_charge +0.05
- Represents cluster c124 — optimisation track, trastuzumab scaffold, CDRH3 family YGSRGLHEYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.56) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.11). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRYGSRGLHEYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

## What would change our mind

The ranker is a prediction, and the parts of it that are not yet evidence are
marked as such rather than dressed up. Where an axis reads `—`, no predictor has
run; where structure confidence contributed nothing, it was withheld by policy
because the model's baseline left no headroom, not because the design scored badly.
