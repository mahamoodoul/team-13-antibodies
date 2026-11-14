# FourWells — shortlist

*2026-11-14 12:26 · 4 designs for 4 lab slots · chosen from 261 eligible of 401 generated*

Every axis is scored against trastuzumab at 0.50. S-tier requires beating the
baseline on all three at once, so the joint score is a product, not a mean: a
design that is excellent on two axes and hopeless on the third is not a candidate.

## The four

| # | design | track | CDRH3 | subs | binding | epitope | stability | joint |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `optB-her2_cdrh3_10` | optimisation | `YPGRYFYTYD` | 6 | 0.27 ▼ | 0.37 ▼ | 0.61 ▲ | 0.061 |
| 2 | `optB-her2_cdrh3_62` | optimisation | `WWDGSFYSYD` | 6 | 0.31 ▼ | 0.37 ▼ | 0.51 ≈ | 0.060 |
| 3 | `optB-her2_cdrh3_85` | optimisation | `WYQYGYYAYE` | 6 | 0.28 ▼ | 0.37 ▼ | 0.56 ▲ | 0.058 |
| 4 | `optB-her2_cdrh3_7` | optimisation | `WGNRGVYRYD` | 5 | 0.23 ▼ | 0.39 ▼ | 0.62 ▲ | 0.058 |

> **Concentration warning.** All 4 picks come from `her2-2026-11-07`. They share a generator and a scaffold, so they share a failure mode — if that family is wrong, all of them fail together.

## Dossiers

### 1. `optB-her2_cdrh3_10`

**Hypothesis.** Joint P(S-tier) 0.061 = binding 0.27 x epitope 0.37 x stability 0.61, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `YPGRYFYTYD` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.061 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.27 ▼ — 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +20%
- **epitope** 0.37 ▼ — optimisation-track variant retaining 83% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.61 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +20%
- Epitope: optimisation-track variant retaining 83% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.0 vs 8.1; dominant terms pi_distance +0.26, abs_net_charge +0.09
- Represents cluster c96 — optimisation track, trastuzumab scaffold, CDRH3 family YPGRYFYTYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.61) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.27). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRYPGRYFYTYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 2. `optB-her2_cdrh3_62`

**Hypothesis.** Joint P(S-tier) 0.060 = binding 0.31 x epitope 0.37 x stability 0.51, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WWDGSFYSYD` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.060 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.31 ▼ — 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +20%
- **epitope** 0.37 ▼ — optimisation-track variant retaining 83% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.51 ≈ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.1 vs 8.1; dominant terms loop_glycine +0.05, pi_distance -0.00

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard NOT RUN  
novelty: pass — ≥2 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +20%
- Epitope: optimisation-track variant retaining 83% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.1 vs 8.1; dominant terms loop_glycine +0.05, pi_distance -0.00
- Represents cluster c125 — optimisation track, trastuzumab scaffold, CDRH3 family WWDGSFYSYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.51) and it clears every entry gate.
- Novelty borderline: exactly 2 substitutions from the nearest provided sequence. It passes the filter as Ruhit measured it, but the project wording reads as 'more than 2', so this pick is contingent on that reading. Confirm with an Apheris mentor before submitting.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.31). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWWDGSFYSYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 3. `optB-her2_cdrh3_85`

**Hypothesis.** Joint P(S-tier) 0.058 = binding 0.28 x epitope 0.37 x stability 0.56, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WYQYGYYAYE` (6 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.058 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.28 ▼ — 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +0%, aromatics +30%
- **epitope** 0.37 ▼ — optimisation-track variant retaining 83% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.56 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.6 vs 8.1; dominant terms pi_distance +0.15, loop_glycine +0.05

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.40 < 0.70 · 6 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 6 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +0%, aromatics +30%
- Epitope: optimisation-track variant retaining 83% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.6 vs 8.1; dominant terms pi_distance +0.15, loop_glycine +0.05
- Represents cluster c137 — optimisation track, trastuzumab scaffold, CDRH3 family WYQYGYYAYE (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.56) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.28). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWYQYGYYAYEYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 4. `optB-her2_cdrh3_7`

**Hypothesis.** Joint P(S-tier) 0.058 = binding 0.23 x epitope 0.39 x stability 0.62, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WGNRGVYRYD` (5 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.058 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.23 ▼ — 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +0%
- **epitope** 0.39 ▼ — optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.62 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.3 vs 8.1; dominant terms pi_distance +0.35, abs_net_charge +0.14

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.50 < 0.70 · 5 substitutions · abguard NOT RUN  
novelty: pass — ≥3 (capped) substitutions from any of the 525,063 provided · recomputed locally from the committed universe

**Why this one.**

- Binding: 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +0%
- Epitope: optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.3 vs 8.1; dominant terms pi_distance +0.35, abs_net_charge +0.14
- Represents cluster c130 — optimisation track, trastuzumab scaffold, CDRH3 family WGNRGVYRYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.62) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.23). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGNRGVYRYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

## What would change our mind

The ranker is a prediction, and the parts of it that are not yet evidence are
marked as such rather than dressed up. Where an axis reads `—`, no predictor has
run; where structure confidence contributed nothing, it was withheld by policy
because the model's baseline left no headroom, not because the design scored badly.
