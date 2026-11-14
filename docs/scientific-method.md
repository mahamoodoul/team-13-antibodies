# Scientific workflow

The scientific workflow is `python3 -m fourwells.experiments`. The older
`fourwells.cli run` remains a legacy heuristic demonstration. Its normalized
scores, product and preview tier are not calibrated probabilities or verified
thermostability predictions; do not submit its preview list.

An experiment records its question, parent, seed, input snapshot, immutable
reference snapshot, source revision, tool commands/versions, stdout/stderr,
UTC events, evidence, artifact checksums and ranking version. SQLite stores
job state; per-iteration files store scientific artifacts. Closing the browser
or stopping the HTTP server does not stop the detached worker. A failed job
preserves artifacts and partial evidence. Retry by creating a new child iteration;
completed iterations cannot be rerun or overwritten by the worker.

## Evidence and selection

Each objective is either `unknown`, or a finite raw value with method, version,
unit, direction, source, and kind (`prediction` or `measurement`). A reference
value is optional and must share the same method/units. There is no multiplication
into a success probability and no predicted experimental tier.

No thermostability predictor is configured on this laptop. Thermostability
therefore remains unknown unless supported predictor/measurement evidence is
supplied. ipTM, pLDDT, PAE, aggregation and solubility outputs are not thermal
stability evidence. Developability is stored separately.

A candidate is eligible only when the documented validation adapter runs,
returns exit zero and an explicit official pass, assigns an official track,
reports numbering confidence >= 0.1, and has no failures. A track mismatch with
the generation branch rejects the candidate; it is never rescued by changing
branches. Local sequence checks are diagnostics, not an official pass. Imported
`passed` flags alone have no authority. Demo sequences can never be eligible.

Non-dominated sorting uses raw metrics only when both designs have the same
available objectives, methods, versions, kinds and units. Missing objectives
cannot dominate present objectives. Within a front, evidence coverage then
global-alignment CDRH3 sequence diversity break ties; when either CDRH3 is absent,
both full constructs are compared. Candidate ID is the final deterministic tie
break. Diversity applies until the shortlist cap is reached; reserves use
coverage and ID within their Pareto front. Pairwise alignments are cached, and
the dominance graph is computed once. This policy is `pareto-evidence-v2`. It is an auditable
research heuristic, not a validated model of laboratory utility. No candidate
with zero supported objectives enters the ranked export. Up to 20 eligible
candidates are exported, even when thermostability is unknown; that uncertainty
is explicit in the CSV and evidence record.

## Epitope comparison

For project-local PDBs, explicit target and antibody chain mappings can compute
reference target-contact recall at a 5 Å heavy-atom cutoff. Target residue IDs
must match the reference numbering and must not overlap between target chains.
This is contact recovery, not an aligned RMSD,
competition probability or experimental epitope assay. Distinct numbering must
be reconciled before import. Multi-model PDB files use the first model and only
blank/A alternate locations. The viewer shows a C-alpha trace and explicitly
supplied CDR mappings. mmCIF conversion, antibody numbering, structural alignment,
and full molecular surface rendering are not implemented.

## Data evaluation

Use organizer clonotype train/validation/test splits for comparable model
assessment. Those splits are currently absent locally. The existing edit-distance
split is an exploratory extrapolation analysis only. Do not fit or tune thresholds
on the SPR cohort or a held-out FACS test split. FACS classes, SPR affinity,
AI structures, and shuffled non-cognate controls remain distinct evidence types.
The local confidence matrices do not establish SPR-measured negative labels.
