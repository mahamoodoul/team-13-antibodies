# Shortlist visualiser

Two views of the same run: the **scored pool** (which designs the ranker saw, where the four
picks sit, what got rejected and why) and the **structure** of whichever design is selected.

```bash
python3 -I viz/build_data.py        # regenerate viz/designs.json from the pipeline
python3 -m http.server -d viz 8000  # then open http://localhost:8000
```

Serve it rather than opening `index.html` directly — browsers block `fetch` of a sibling file
over `file://`, so the data and any structure file will not load. The page says so if you do.

## What it shows

The scatter is **CDRH3 substitutions from trastuzumab** against **joint P(S-tier)**, which is
`P(binding) × P(epitope) × P(stability)`. Two things are worth reading off it:

- The dashed line at 4 substitutions is the `<70%` CDRH3 identity floor. Everything to its left
  is unsubmittable however well it scores, which is why the ranker never picks there.
- Rejected designs are plotted too, faintly. The pool thins out sharply to the right: that is
  the affinity cliff in `docs/binding-axis-validation.md`, visible as geometry.

Each axis bar has a tick at 0.50. That is trastuzumab, and it is exact — every axis is a
logistic over feature deltas against the reference, so the parent lands on 0.500 by
construction. A bar past the tick is a design we predict beats it on that axis.

## Structures are not committed

The generated complexes live on the VM and are not in the repo. The page looks for
`viz/structures/<design_id>.cif` and otherwise tells you how to fetch one. Either:

```bash
# pull the refolded complexes for the shortlist
scp -i ~/.ssh/team-13 'hackathon@<vm>:~/ruhit/gen/runs/*/scored-*/<design_id>*.cif' viz/structures/
```

or drag a `.cif`/`.pdb` onto the viewer, which needs no server and no VM. `1N8Z` (trastuzumab
Fab + HER2 ECD) is a useful reference to drop in while the design folds are still running.

`viz/structures/` is gitignored — structures are bulk and re-fetchable, same rule as `data/`.

## Keeping it honest

`designs.json` is generated, never hand-edited: the page recomputes nothing, so it cannot drift
from the ranker. If the page and `fourwells` disagree, the JSON is stale — rerun `build_data.py`.
The 3D viewer loads real files only; it will not draw a model we have not folded.

The score panels work with no network. Only the 3D viewer needs its one library (3Dmol.js) from
a CDN, and it degrades to a message if that is unavailable.
