# ~/data/tidy — fixtures for the ranking engine

Unpacked and derived from the provided datasets by `~/ruhit/gen/scripts/build_fixtures.py`.
Rebuild any of it with `python3 -I scripts/build_fixtures.py` from `~/ruhit/gen`.

Everything here is read-only as far as generation is concerned — Rizve and Mahamoodoul own
what happens next. Four things below are not just unpacked data but results that change how
you should use it. They are flagged **READ THIS**.

## The files

| File | Rows | What it is |
| --- | --- | --- |
| `tz_her2_facs_3classes_524346.csv` | 524,346 | FACS binding classes for trastuzumab CDRH3 variants. `cdrh3`, `binding_class` (high/medium/low), `vh_sequence`, `vl_sequence`, `edit_distance`. The training set for a binding predictor. |
| `trastuzumab_her2_spr_all_768.csv` | 768 | SPR-measured designs. 190 rows have a `kd_nM`. The held-out validation set, same assay the judges' lab will use. |
| `provided_cdrh3_universe.txt` | 525,063 | Every unique CDRH3 in the two tables above, one per line. **This is the novelty gate reference set.** |
| `iptm_calibration.csv` | 24,550 | Long form of the Smorodina ipTM matrices: `model`, `vhh_pdb`, `antigen_pdb`, `iptm`, `is_cognate`. The structure-confidence calibration set. |
| `iptm_confidence_scores/` | 3 files | The original 91x91 matrices (af3, boltz2, chai1). Diagonal = cognate pairs, off-diagonal = shuffled non-binders. |
| `trastuzumab_parent.json` | — | The parent row, verified. VH 120 aa, VL 107 aa, 227 total, 8 measured KDs. |

Verified against the organisers' documentation on three independent counts: 525,063 unique
CDRH3s, 37 sequences shared between the two tables, and trastuzumab absent from the FACS
table. All three match the published description, so the files are intact.

## READ THIS 1 — Boltz-2 ipTM cannot tell a binder from a non-binder

Computed from `iptm_calibration.csv`, over 91 cognate pairs and ~8,100 shuffled pairs that
were measured **not** to bind:

| Model | cognate ipTM>=0.7 | shuffled ipTM>=0.7 | median cognate | median shuffled |
| --- | --- | --- | --- | --- |
| **Boltz-2** | 99% (90/91) | **94.3% (7723/8190)** | 0.91 | 0.88 |
| AF3 | 47% (43/91) | 3.0% (246/8137) | 0.50 | 0.18 |
| Chai-1 | 8% (7/89) | 0.2% (17/7952) | 0.21 | 0.19 |

Boltz-2 gives almost every pair a high ipTM whether or not it binds. A confidence filter at
0.7 would have accepted 7,723 known non-binders. **Do not use Boltz-2 ipTM as the binding
axis, and do not set a cutoff on it.** AF3 separates well but we have no AF3 on the VM.

This matters because our refolds use Boltz-2 (it is the templated model the tutorial wires
up). Use its output as a *feature* and rank on `min_ipae` within one model, as the Apheris
docs also advise. If you want a second opinion, Protenix v2 and OpenFold3 are available and
`scripts/fold.sh MODEL=protenix-v2` will run them — but scores are only comparable within one
model, so a new model needs its own baseline row.

Calibrate the cutoff from the curve in `iptm_calibration.csv`, per model. That is step 4 of
the proof in the plan, and the data for it is here.

## READ THIS 2 — the enrichment base rate is 3.3%, not 6.3%

Of the 190 `quantified_binding` rows in the SPR table, **8 are trastuzumab's own reference
rows**, not designs. The real pool is 182 genuine variant designs.

| Threshold | Designs beating it |
| --- | --- |
| median trastuzumab KD, 0.1345 nM | **6 / 182 = 3.3%** |
| a single reference row, 0.152 nM | 7 / 182 = 3.8% |
| trastuzumab's best, 0.0285 nM | 1 / 182 = 0.5% |

An earlier reading of 12/190 = 6.3% came from counting 5 trastuzumab rows that beat another
trastuzumab row as designs. Use 3.3% as the denominator of the enrichment claim — a judge who
recomputes it will find 182, not 190.

Also worth putting on the slide: median design KD is 79.5 nM against the parent's 0.13 nM, a
~590x gap. Affinity really is the hard axis.

## READ THIS 3 — the identity threshold is ambiguous, and it bites

Our two sources disagree:

- `docs/brief.md`: "<70% CDRH3 identity" — 7/10 matches is 70%, which is not under the
  ceiling, so **4 of 10 positions must differ**.
- Apheris `12-her2.md`: "at most 70% identical ... at least 3 of 10 positions changed" — so
  **3 differences suffice**.

This is not hypothetical. In the first 4-design test, one design had exactly 3 substitutions,
so it passes under one reading and fails under the other. Generation uses the strict `>=4`
rule, which satisfies both. `export_batch.py` records `mutations_from_parent` per design, so
you can find the borderline ones with `muts == 3` and decide deliberately.

Still unverified: whether abguard uses the same loop boundary at all. It numbers with immunum.
It was not installed on the VM as of 10:50.

## READ THIS 4 — the baseline row exists, and the designs "beat" it

`~/ruhit/gen/out/baseline.json` (committed as `data/generated/baseline.json`) holds
trastuzumab folded through the identical path — same model, same 1N8Z template, same seed,
same flags:

| Metric | trastuzumab | a design |
| --- | --- | --- |
| iptm | 0.960 | 0.965 |
| ptm | 0.969 | 0.972 |
| binder_plddt | 98.39 | 98.51 |

The design wins on all three, and that tells us nothing, for the reason in READ THIS 1. This
pairing — a real baseline row plus the calibration showing the metric is uninformative — is
the most concrete judgment claim we have. It belongs on the proof slide.

`binder_plddt` for the parent is computed from per-atom pLDDT over the binder chain, because
refold-score needs a design to compare a refold against and the parent has none. The method
reproduces refold-score's own `binder_plddt` exactly on designs that did go through it.

## Not unpacked

`zenodo-10831512-trastuzumab-ngs/data.zip` (2.4 GB, 4 GB unpacked) holds the authors'
ready-made clonotype splits of the FACS data — similar CDRH3s kept in the same split, which is
exactly the held-out design the plan asks for. Under
`data/affinity_data/her2/her2_aff_large/processed/remove_overlap/clonotype_split/0.7_0.15_0.15/`.
Worth unpacking if you would rather use their split than design one; say the word and I will.

`rmsd_between_replicas.zip` (543 MB) and the sigma2 per-replica archives are not needed for
ranking.
