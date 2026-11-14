# Implementation status against antibodylab_ai_project_README.md

## Implemented and locally testable

- Browser-independent CLI orchestration with detached workers, SQLite job metadata,
  immutable iteration IDs, parent relationships, questions, parameters and seeds.
- Demo and real-record import paths; documented external adapter protocol for
  design, official validation, refold preparation, prediction and refold scoring.
- Strict export eligibility, explicit track mismatch rejection, raw validation logs,
  separate local diagnostic screening, and no demo designs in final exports.
- Independent objective records with method/version/unit/source, unknown evidence,
  raw prediction metrics, developability, limitations and disagreement metadata.
- Explicit PDB target-contact comparison, deterministic Pareto layers and diversity
  selection, up to 20 ranked designs, FASTA/CSV/JSON/raw-artifact ZIP exports.
- Scientific experiment list/detail, background status/events/errors, candidate
  inspection, working filters, comparison, raw objective plots grouped by compatible
  scales, pairwise sequence identity, and an offline chain-toggle C-alpha PDB viewer.
- Local tool/document availability in the dashboard, retained partial evidence on
  failures, and explicit missing-output failures for live model adapters.
- Source audit, input snapshots, reference checksums, artifact manifest and tests
  for missing evidence, failures, eligibility, immutable retries and job persistence.

## Requires supplied external resources; not claimed complete

- A real RFD4-Proteina pilot and documented model-specific wrappers on a supported
  GPU VM; verification against the installed Foundry tutorial and image versions.
- Official `abguard` execution on real candidates. No local installation is present.
- Real eligible candidates through co-folding and refold-score, actual complex PDBs,
  supported thermostability predictions, and independent model agreement evidence.
- Organizer bucket README, official clonotype splits and measured negative supplement;
  rigorous confidence calibration against genuinely measured non-binders.
- Experimental SPR, competitive-binding and thermal-melt validation.
- Fine-tuning (optional in the specification) and a demonstrated experimental improvement.

## Deliberate implementation choices / remaining UI limits

The recommended React/FastAPI stack is not required by the scientific data
contract. The working app retains standard-library Python and local JavaScript
so `make web` requires no downloads. SQLite and filesystem artifacts implement
the required metadata/storage architecture. Existing fourwells modules remain
in place rather than duplicating them under a `backend/` directory.

The viewer is a PDB C-alpha trace, not a full chemical surface/cartoon renderer;
mmCIF conversion and structural alignment are not included. References are shown
in independent frames, never falsely superimposed. Contact comparison assumes
matching HER2 residue numbering. Comparisons report evidence coverage and
sequence diversity without inventing absent objective values.
