# FourWells — shortlist

*2026-11-14 14:02 · 4 designs for 4 lab slots · chosen from 205 eligible of 401 generated*

Every axis is scored against trastuzumab at 0.50. S-tier requires beating the
baseline on all three at once, so the joint score is a product, not a mean: a
design that is excellent on two axes and hopeless on the third is not a candidate.

## The four

| # | design | track | CDRH3 | subs | binding | epitope | stability | joint |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `optA-her2_cdrh3_21` | optimisation | `WKSSYYYYFD` | 7 | 0.31 ▼ | 0.46 ▼ | 0.60 ▲ | 0.085 |
| 2 | `optB-her2_cdrh3_10` | optimisation | `YPGRYFYTYD` | 6 | 0.25 ▼ | 0.54 ▲ | 0.61 ▲ | 0.084 |
| 3 | `optB-her2_cdrh3_85` | optimisation | `WYQYGYYAYE` | 6 | 0.25 ▼ | 0.50 ≈ | 0.56 ▲ | 0.070 |
| 4 | `optA-her2_cdrh3_71` | optimisation | `WRSTTDYYFD` | 7 | 0.24 ▼ | 0.50 ≈ | 0.57 ▲ | 0.067 |

## Dossiers

### 1. `optA-her2_cdrh3_21`

**Hypothesis.** Joint P(S-tier) 0.085 = binding 0.31 x epitope 0.46 x stability 0.60, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-novel-2026-11-09` |
| CDRH3 | `WKSSYYYYFD` (7 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.085 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.31 ▼ — 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +30%
- **epitope** 0.46 ▼ — predicted complex covers 65% of the annotated domain IV epitope
- **stability** 0.60 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.30 < 0.70 · 7 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +30%
- Epitope: predicted complex covers 65% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09
- Represents cluster c119 — optimisation track, trastuzumab scaffold, CDRH3 family WKSSYYYYFD (2 designs). Chosen over 1 sibling sharing this hypothesis, so a failure here costs us one idea, not the shortlist.
- On the list because its strongest axis is stability (0.60) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.31). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWKSSYYYYFDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 2. `optB-her2_cdrh3_10`

**Hypothesis.** Joint P(S-tier) 0.084 = binding 0.25 x epitope 0.54 x stability 0.61, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `YPGRYFYTYD` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.084 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.25 ▼ — 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +20%
- **epitope** 0.54 ▲ — predicted complex covers 75% of the annotated domain IV epitope
- **stability** 0.61 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +20%
- Epitope: predicted complex covers 75% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09
- Represents cluster c135 — optimisation track, trastuzumab scaffold, CDRH3 family YPGRYFYTYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.61) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.25). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRYPGRYFYTYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 3. `optB-her2_cdrh3_85`

**Hypothesis.** Joint P(S-tier) 0.070 = binding 0.25 x epitope 0.50 x stability 0.56, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WYQYGYYAYE` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.070 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.25 ▼ — 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +0%, aromatics +30%
- **epitope** 0.50 ≈ — predicted complex covers 70% of the annotated domain IV epitope
- **stability** 0.56 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.6 vs 8.1; dominant terms pi_distance +0.15, loop_glycine +0.05

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +0%, aromatics +30%
- Epitope: predicted complex covers 70% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.6 vs 8.1; dominant terms pi_distance +0.15, loop_glycine +0.05
- Represents cluster c147 — optimisation track, trastuzumab scaffold, CDRH3 family WYQYGYYAYE (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.56) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.25). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWYQYGYYAYEYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 4. `optA-her2_cdrh3_71`

**Hypothesis.** Joint P(S-tier) 0.067 = binding 0.24 x epitope 0.50 x stability 0.57, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-novel-2026-11-09` |
| CDRH3 | `WRSTTDYYFD` (7 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.067 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.24 ▼ — 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +10%
- **epitope** 0.50 ≈ — predicted complex covers 70% of the annotated domain IV epitope
- **stability** 0.57 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.16, loop_glycine +0.07

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.30 < 0.70 · 7 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 7 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +10%
- Epitope: predicted complex covers 70% of the annotated domain IV epitope
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.16, loop_glycine +0.07
- Represents cluster c130 — optimisation track, trastuzumab scaffold, CDRH3 family WRSTTDYYFD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.57) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against shuffled non-cognate pairs (computational, not SPR-measured), so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.24). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWRSTTDYYFDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

## What would change our mind

The ranker is a prediction, and the parts of it that are not yet evidence are
marked as such rather than dressed up. Where an axis reads `—`, no predictor has
run; where structure confidence contributed nothing, it was withheld by policy
because the model's baseline left no headroom, not because the design scored badly.
