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

## What the 3D panel shows

We have no folds for these designs — the generated complexes are on the VM. What we do
have is the experimental structure of the molecule they are all variants of: **1N8Z**,
trastuzumab Fab bound to HER2 at 2.52 Å, committed as `viz/scaffold/1N8Z.pdb`.

So the panel draws the real parent complex and marks this design's differences on it:

| colour | what it is |
| --- | --- |
| red | CDRH3 positions **this design changes** |
| teal | the rest of trastuzumab's CDRH3 (chain B, residues 99–108) |
| orange | the HER2 epitope trastuzumab binds (chain C, 557-561 / 570-573 / 593-603) |
| grey | HER2 domain IV |

**This is not the design's structure, and the page says so under every view.** No coordinate
is predicted or invented; every atom comes from the deposited model. For an optimisation-track
design — this scaffold with a redesigned loop — it is the honest picture: it shows exactly
which residues change and how close they sit to the epitope. A design whose CDRH3 differs in
length is not mapped at all, because an indel shifts the register and a position-by-position
comparison would be meaningless; the note says so instead.

Mapping checks, all verified against the file rather than assumed: CDRH3 `WGGDGFYAMD` is
chain B 99–108 with no insertion codes; epitope spans 557-561, 570-573 and 593-603 are all
present in chain C; and 581-590 is **absent** from 1N8Z, exactly as
`data/reference/trastuzumab.json` warns ("8PWH only — a loop not resolved in earlier
structures").

## A real fold replaces it

The page prefers `viz/structures/<design_id>.cif` over the scaffold wherever one exists, so
dropping real folds in upgrades every view with no code change. Either:

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

The score panels work with no network. Only the 3D viewer needs its one library (3Dmol.js)
from a CDN, and it degrades to a message if that is unavailable. It also needs WebGL, and
says so plainly where there is none rather than reporting a missing structure.
