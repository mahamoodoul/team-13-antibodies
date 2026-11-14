# Model adapters and execution

No Foundry/abguard invocation is invented by the scientific workflow. The local
inventory finds neither `abguard` nor `foundry-toolkit`. The bucket README,
`18-vm.md`, `Tutorial.html`, real design batches and supported thermostability
predictor are absent. An end-to-end **real** model run therefore cannot be
claimed on this laptop. Docker executable presence alone says nothing about GPU
support or installed licensed images.

On the supplied VM, first obtain and read the organizer instructions. Confirm
weights, task syntax, inputs and output formats from installed documentation.
The pre-existing scripts in `scripts/` are historical VM recipes and need that
verification before execution; the scientific worker does not invoke them
automatically.

## Adapter protocol

Copy `config/model-profile.example.json` to a local profile. Supply the path to
the installed documentation and set `verified_against_installed_docs` only after
checking commands. Each stage specifies its exact `argv` (a list, no shell),
`version`, and optional `timeout` (seconds, capped at 24 hours). A wrapper translates
this project's file protocol to the verified native command. Merely setting the
verification flag does not install or validate a scientific model.

Substitutions allowed in argument strings:

| Stage | Placeholders and required output |
| --- | --- |
| design | `{workspace}`, `{output}`, `{seed}`, `{candidates}`; output JSONL candidates |
| validation | `{workspace}`, `{input}`, `{output}`, `{design_id}`; output official validation JSON |
| refold_prepare | `{workspace}`, `{input}`, `{output}`; read eligible.json, save preparation artifacts |
| predict | same; save model outputs and PDBs in workspace |
| refold_score | same; write predictions.json at `{output}` |

Use absolute executable paths or installed commands. Python wrapper scripts
must be passed to their interpreter, e.g. `["python3", "/vm/verified-wrapper.py",
"{input}", "{output}"]`. Literal braces in an argument must be doubled. Every
command and version, exact stdout/stderr and elapsed time are retained. Timeouts
and nonzero model exits fail the iteration; validation nonzero exits reject the
candidate and retain its logs. No failed validation is silently discarded.

Validation output must contain explicit `passed` (boolean), `track`
(`optimisation` or `de_novo`), `numbering_confidence`, and `failed_rules`.
The wrapper must return the official tool's verdict rather than implement its
own pass. Preserve the native tool output in stdout or artifacts. The platform
cannot independently certify a user-written wrapper's scientific correctness.

`predictions.json` is keyed by candidate ID. Each entry can contain `predictions`
(a list of per-model metrics with model/version/parameters), `structures`
(project-local `.pdb` paths and chain/CDR mapping metadata), and `evidence`
(objectives in the schema below). Every eligible candidate must have an entry;
missing IDs fail the iteration and retain partial evidence. Each entry may also
include `model_disagreement`, `limitations` (lists), and `developability`.
Model disagreement and limitations must remain
explicit; no averaging across differently scaled models is performed.

```bash
python3 -m fourwells.experiments start --mode live \
  --profile config/my-verified-vm-profile.json --seed 13 --candidates 8 \
  --question 'Does the documented balanced HER2 setting produce eligible designs?'
```

The worker validates before spending folding compute and sends only eligible
candidates to the refold stages. Jobs have unique workspace IDs and are never
implicitly resubmitted. Model execution occurs outside the HTTP process.

## Import saved candidates

```bash
python3 -m fourwells.experiments start --mode import \
  --input my-candidates.jsonl --question 'Inspect the pilot batch'
```

Without `--profile`, candidates remain unvalidated and cannot enter the final
submission. Add a verified profile with a validation stage to execute `abguard`.
Inputs may include supported existing experimental/predictor evidence; imported
claims retain their supplied provenance and are not independently certified.

Each line must have a unique safe `design_id`, final construct `sequence`, and
`format` (vhh/scfv/fab). Include generator/version/weights/parameters/seed in
`generator` and `generation`. The worker does not invent an scFv linker from
separate VH/VL sequences. `track` is a requested generation branch, not an
official assignment. Optional fields:

```json
{
  "evidence": {
    "binding": {
      "value": 1.2,
      "unit": "nM",
      "direction": "min",
      "kind": "measurement",
      "method": "SPR-protocol-id",
      "version": "1",
      "source": "lab-run-id",
      "reference_value": 0.0954
    }
  },
  "predictions": [],
  "structures": [{"path": "my-run/complex.pdb", "model": "record actual model", "cdr_regions": []}],
  "interface": {
    "reference": "my-run/reference.pdb",
    "target_chains": ["T"],
    "binder_chains": ["H", "L"],
    "reference_target_chains": ["T"],
    "reference_binder_chains": ["H", "L"]
  }
}
```

The numeric example illustrates the file format only; it is not new experimental
data. Supply actual measurements and matched assay baselines for your candidates.
Structures are copied into the iteration with checksums. They must be project-local
PDB files below 30 MB. Only saved structures are served by the viewer. ZIP exports
include raw evidence and logs; treat them as local scientific records.

`cdrh3`, when supplied, must be present in the construct. Sequence whitespace is
removed and letters are uppercased before validation and export. Local CDR
extraction is a diagnostic approximation; official numbering remains the tool's
responsibility. For contact comparison, all target chains must use unique,
reference-matched HER2 residue numbering; overlapping target IDs are rejected.
