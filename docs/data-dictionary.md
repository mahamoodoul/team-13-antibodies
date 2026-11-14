# Local data dictionary

Inspected with `python3 proof/audit_datasets.py --data data/source`.

| Source | Observed contents | Use |
| --- | --- | --- |
| her2-trastuzumab/tz_her2_facs_3classes_524346.csv.zip | 524,346 variants; FACS low/medium/high classes; CDRH3 and edit distance | Sequence research; assay classes are not SPR KD |
| her2-trastuzumab/trastuzumab_her2_spr_all_768.csv | 768 rows; 190 fitted KD rows including parent replicates | Blind affinity validation; distinguish no reportable fit from measured nonbinding |
| zenodo-18390239-ab-ag-complexes/iptm_confidence_scores.zip | AF3/Boltz2/Chai1 cross-pairing matrices; shuffled off-diagonal pairs | Confidence behavior; not SPR-labelled true negatives |
| reference/trastuzumab.json | VH/VL, baseline KD replicates and documented HER2 contact regions | Immutable per-iteration reference snapshot |

The organizer bucket README, official clonotype splits, sigma2 SPR supplement,
actual complex PDBs and most of the described large archives are absent locally.
Do not substitute the edit-distance split for the official benchmark. Existing
`proof/tidy/` outputs are derived historical analyses, not newly measured data.

Regenerate a source file/size/SHA-256 inventory:

```bash
python3 -m fourwells.experiments inventory
python3 proof/audit_datasets.py --data data/source
```

Experiment records live under `artifacts/antibodylab/<iteration-id>/`:
`spec.json`, `reference.json`, `provenance.json`, `evidence.json`, input snapshots,
`events.jsonl`, raw `logs/`, saved `structures/`, exports and `manifest.json`.
`metadata.sqlite3` stores ID, parent (in spec), status, timestamps, errors and worker
PID. UTC timestamps are displayed in the browser's local timezone.
