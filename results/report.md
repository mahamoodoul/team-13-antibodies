# FourWells — shortlist

*2026-11-14 13:20 · 4 designs for 4 lab slots · chosen from 14 eligible of 25 generated*

Every axis is scored against trastuzumab at 0.50. S-tier requires beating the
baseline on all three at once, so the joint score is a product, not a mean: a
design that is excellent on two axes and hopeless on the third is not a candidate.

## The four

| # | design | track | CDRH3 | subs | binding | epitope | stability | joint |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `optB-her2_cdrh3_10` | optimisation | `YPGRYFYTYD` | 6 | 0.23 ▼ | 0.29 ▼ | 0.61 ▲ | 0.041 |
| 2 | `optA-her2_cdrh3_14` | optimisation | `WHNLHEYYFD` | 7 | 0.11 ▼ | 0.35 ▼ | 0.52 ≈ | 0.020 |
| 3 | `optB-her2_cdrh3_0` | optimisation | `WAPMGGYAMY` | 5 | 0.11 ▼ | 0.26 ▼ | 0.60 ▲ | 0.017 |
| 4 | `multicdr-her2_multicdr_11` | optimisation | `SYGSASYYFD` | 7 | 0.15 ▼ | 0.18 ▼ | 0.59 ▲ | 0.016 |

## Dossiers

### 1. `optB-her2_cdrh3_10`

**Hypothesis.** Joint P(S-tier) 0.041 = binding 0.23 x epitope 0.29 x stability 0.61, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `YPGRYFYTYD` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.041 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.23 ▼ — 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +20%
- **epitope** 0.29 ▼ — predicted complex covers 75% of the annotated domain IV epitope
- **stability** 0.61 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +20%
- Epitope: predicted complex covers 75% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09
- Represents cluster c13 — optimisation track, trastuzumab scaffold, CDRH3 family YPGRYFYTYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.61) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.23). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRYPGRYFYTYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 2. `optA-her2_cdrh3_14`

**Hypothesis.** Joint P(S-tier) 0.020 = binding 0.11 x epitope 0.35 x stability 0.52, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-novel-2026-11-09` |
| CDRH3 | `WHNLHEYYFD` (7 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.020 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.11 ▼ — 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content -20%, aromatics +10%
- **epitope** 0.35 ▼ — optimisation-track variant retaining 80% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.52 ≈ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.1 vs 8.1; dominant terms loop_glycine +0.07, abs_net_charge +0.00

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.30 < 0.70 · 7 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content -20%, aromatics +10%
- Epitope: optimisation-track variant retaining 80% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.1 vs 8.1; dominant terms loop_glycine +0.07, abs_net_charge +0.00
- Represents cluster c9 — optimisation track, trastuzumab scaffold, CDRH3 family WHNLHEYYFD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.52) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.11). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWHNLHEYYFDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 3. `optB-her2_cdrh3_0`

**Hypothesis.** Joint P(S-tier) 0.017 = binding 0.11 x epitope 0.26 x stability 0.60, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WAPMGGYAMY` (5 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.017 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.11 ▼ — 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content -20%, aromatics +0%
- **epitope** 0.26 ▼ — predicted complex covers 70% of the annotated domain IV epitope
- **stability** 0.60 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.1 vs 8.1; dominant terms pi_distance +0.28, abs_net_charge +0.09

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.50 < 0.70 · 5 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content -20%, aromatics +0%
- Epitope: predicted complex covers 70% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.1 vs 8.1; dominant terms pi_distance +0.28, abs_net_charge +0.09
- Represents cluster c12 — optimisation track, trastuzumab scaffold, CDRH3 family WAPMGGYAMY (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.60) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.11). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWAPMGGYAMYYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 4. `multicdr-her2_multicdr_11`

**Hypothesis.** Joint P(S-tier) 0.016 = binding 0.15 x epitope 0.18 x stability 0.59, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:antibody-2026-10-30` |
| CDRH3 | `SYGSASYYFD` (7 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.016 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.15 ▼ — 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +10%
- **epitope** 0.18 ▼ — optimisation-track variant retaining 49% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.59 ▲ — 1 framework substitutions, hydrophobic-patch burden +0.24 and pI 4.9 vs 8.1; dominant terms pi_distance +0.51, framework_substitutions -0.11

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.30 < 0.70 · 7 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +10%
- Epitope: optimisation-track variant retaining 49% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 1 framework substitutions, hydrophobic-patch burden +0.24 and pI 4.9 vs 8.1; dominant terms pi_distance +0.51, framework_substitutions -0.11
- Represents cluster c1 — optimisation track, trastuzumab scaffold, CDRH3 family SYGSGSGYFD (2 designs). Chosen over 1 sibling sharing this hypothesis, so a failure here costs us one idea, not the shortlist.
- On the list because its strongest axis is stability (0.59) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.15). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGYTFTNYTINWVRQAPGKGLEWVASIYPGNGDTNY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRSYGSASYYFDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

## What would change our mind

The ranker is a prediction, and the parts of it that are not yet evidence are
marked as such rather than dressed up. Where an axis reads `—`, no predictor has
run; where structure confidence contributed nothing, it was withheld by policy
because the model's baseline left no headroom, not because the design scored badly.
