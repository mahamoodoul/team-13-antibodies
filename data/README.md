# Project data

`reference/` contains the committed trastuzumab reference; the worker snapshots
and hashes it for every scientific iteration. `generated/` is the historical
Foundry replay location; currently only baseline refold metrics are available,
so an offline candidate demo is explicitly synthetic.

`source/` contains local organizer archives and is gitignored. Its authoritative
bucket README is missing; obtain it before adding new processing assumptions.
See [the data dictionary](../docs/data-dictionary.md) and the existing analysis
scripts in `proof/`. Keep train/validation/test identities and preprocessing
recorded; never tune on SPR or held-out test labels.

Large structures and new job outputs go in gitignored `artifacts/`, not Git.
