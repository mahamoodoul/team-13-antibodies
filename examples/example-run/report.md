# FourWells — shortlist

*2026-11-14 12:11 · 4 designs for 4 lab slots · chosen from 261 eligible of 301 generated*

Every axis is scored against trastuzumab at 0.50. S-tier requires beating the
baseline on all three at once, so the joint score is a product, not a mean: a
design that is excellent on two axes and hopeless on the third is not a candidate.

## The four

| # | design | track | CDRH3 | subs | binding | epitope | stability | joint |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `optB-her2_cdrh3_82` | optimisation | `WGTGYFYYYD` | 5 | 0.33 ▼ | 0.39 ▼ | 0.55 ▲ | 0.073 |
| 2 | `optB-her2_cdrh3_4` | optimisation | `WGNFGFYDFT` | 5 | 0.32 ▼ | 0.39 ▼ | 0.56 ▲ | 0.071 |
| 3 | `optB-her2_cdrh3_11` | optimisation | `WGGYGFRMYG` | 5 | 0.26 ▼ | 0.39 ▼ | 0.61 ▲ | 0.063 |
| 4 | `optB-her2_cdrh3_70` | optimisation | `WGGGGIYVYD` | 4 | 0.28 ▼ | 0.42 ▼ | 0.55 ▲ | 0.062 |

> **Concentration warning.** All 4 picks come from `her2-2026-11-07`. They share a generator and a scaffold, so they share a failure mode — if that family is wrong, all of them fail together.

## Dossiers

### 1. `optB-her2_cdrh3_82`

**Hypothesis.** Joint P(S-tier) 0.073 = binding 0.33 x epitope 0.39 x stability 0.55, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WGTGYFYYYD` (5 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.073 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.33 ▼ — 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +30%
- **epitope** 0.39 ▼ — optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.55 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.6 vs 8.1; dominant terms pi_distance +0.15, abs_net_charge +0.04

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.50 < 0.70 · 5 substitutions · abguard NOT RUN  
novelty: pass — ≥2 (capped) substitutions from any of the 525,063 provided · generation export

**Why this one.**

- Binding: 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +20%, aromatics +30%
- Epitope: optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.6 vs 8.1; dominant terms pi_distance +0.15, abs_net_charge +0.04
- Represents cluster c154 — optimisation track, trastuzumab scaffold, CDRH3 family WGTGYFYYYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.55) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.33). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGTGYFYYYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 2. `optB-her2_cdrh3_4`

**Hypothesis.** Joint P(S-tier) 0.071 = binding 0.32 x epitope 0.39 x stability 0.56, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WGNFGFYDFT` (5 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.071 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.32 ▼ — 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +0%, aromatics +20%
- **epitope** 0.39 ▼ — optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.56 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, abs_net_charge +0.04

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.50 < 0.70 · 5 substitutions · abguard NOT RUN  
novelty: pass — ≥2 (capped) substitutions from any of the 525,063 provided · generation export

**Why this one.**

- Binding: 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +0%, aromatics +20%
- Epitope: optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.17, abs_net_charge +0.04
- Represents cluster c119 — optimisation track, trastuzumab scaffold, CDRH3 family WGNFGFYDFT (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.56) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.32). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGNFGFYDFTYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 3. `optB-her2_cdrh3_11`

**Hypothesis.** Joint P(S-tier) 0.063 = binding 0.26 x epitope 0.39 x stability 0.61, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WGGYGFRMYG` (5 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.063 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.26 ▼ — 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +10%
- **epitope** 0.39 ▼ — optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.61 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.3 vs 8.1; dominant terms pi_distance +0.35, abs_net_charge +0.14

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.50 < 0.70 · 5 substitutions · abguard NOT RUN  
novelty: pass — ≥2 (capped) substitutions from any of the 525,063 provided · generation export

**Why this one.**

- Binding: 5 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +10%
- Epitope: optimisation-track variant retaining 86% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 9.3 vs 8.1; dominant terms pi_distance +0.35, abs_net_charge +0.14
- Represents cluster c98 — optimisation track, trastuzumab scaffold, CDRH3 family WGGYGFRMYG (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.61) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.26). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGYGFRMYGYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

### 4. `optB-her2_cdrh3_70`

**Hypothesis.** Joint P(S-tier) 0.062 = binding 0.28 x epitope 0.42 x stability 0.55, each against a trastuzumab baseline of 0.50 on every axis.

| | |
| --- | --- |
| track / format | optimisation / scfv |
| generator | `rfd4-proteina:her2-2026-11-07` |
| CDRH3 | `WGGGGIYVYD` (4 substitutions from parent) |
| construct | 242 aa, VH-linker-VL |
| joint P(S-tier) | 0.062 |

**Axes, against the trastuzumab baseline of 0.50.**

- **binding** 0.28 ▼ — 4 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +0%
- **epitope** 0.42 ▼ — optimisation-track variant retaining 89% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- **stability** 0.55 ▲ — 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.16, abs_net_charge +0.04

**Entry gates.** length 242 aa (construct) ≤ 250 · CDRH3 identity 0.60 < 0.70 · 4 substitutions · abguard NOT RUN  
novelty: pass — ≥2 (capped) substitutions from any of the 525,063 provided · generation export

**Why this one.**

- Binding: 4 of 10 CDRH3 positions changed against an affinity-matured parent; paratope-residue content +10%, aromatics +0%
- Epitope: optimisation-track variant retaining 89% of trastuzumab's CDR paratope — it binds where trastuzumab binds, so this axis is close to free
- Stability: 0 framework substitutions, hydrophobic-patch burden +0.00 and pI 8.7 vs 8.1; dominant terms pi_distance +0.16, abs_net_charge +0.04
- Represents cluster c144 — optimisation track, trastuzumab scaffold, CDRH3 family WGGGGIYVYD (1 design). A hypothesis no other design in the shortlist tests.
- On the list because its strongest axis is stability (0.55) and it clears every entry gate.
- Structure confidence contributed nothing positive to this score: the cutoff is not yet calibrated against the 454 measured non-binders, so high confidence is ignored by policy rather than trusted.

**Kill criterion.** Fails if SPR K_D comes back above trastuzumab's (predicted P 0.28). This is the expected failure: the <70% CDRH3 rule forced us to change an affinity-matured loop, and that is more likely to cost affinity than add it.

**Sequence as ordered.**

```
EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRY
ADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGGGIYVYDYWGQGTLVTVSS
GGGGSGGGGSGGGGSDIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPK
LLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVE
IK
```

## What would change our mind

The ranker is a prediction, and the parts of it that are not yet evidence are
marked as such rather than dressed up. Where an axis reads `—`, no predictor has
run; where structure confidence contributed nothing, it was withheld by policy
because the model's baseline left no headroom, not because the design scored badly.
