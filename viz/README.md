# Shortlist visualiser

Two pages, built from different things, and the difference matters:

| | built from | shows |
| --- | --- | --- |
| `results.html` | **`results/`, the committed submission** | what we are sending, and what the pool it came from looks like |
| `index.html` | a live pipeline run | the scored pool, each design's dossier, and the trastuzumab–HER2 complex in 3D |

```bash
make viz                            # rebuild results.html from results/ (runs in `make submission`)
open viz/results.html               # no server needed, the data is inlined

python3 -I viz/build_data.py        # regenerate viz/designs.json from the pipeline
python3 -m http.server -d viz 8000  # then open http://localhost:8000
```

Serve `index.html` rather than opening it directly — browsers block `fetch` of a sibling file
over `file://`, so the data and any structure file will not load. The page says so if you do.
`results.html` carries its data inside the file and opens straight from disk.

## results.html — the submission

One page over the run in `results/`: the four picks with their axes, CDRH3 alignment and
epitope footprint; every candidate on one logarithmic axis grouped by generator batch; what
each batch cost at the gates; a sortable table of all of them; and what the scores rest on,
including the pipeline's own submission blockers.

`build_results.py` rewrites only the block between the two `DATA` markers, so the page's code
is hand-written and its numbers never are. It recomputes nothing — it reads the same records
the ranker wrote, through `fourwells`' own helpers, so a number on the page and the same number
in `report.md` cannot disagree. `python3 -I viz/build_results.py --check` exits non-zero when
the page is stale, which is the thing to run if you suspect it has drifted.

The page states the sha256 of the `designs.jsonl` it was built from, in the header and again
in the footer, so you can tell at a glance which run you are looking at.

## index.html — the live pool

The scatter is **CDRH3 substitutions from trastuzumab** against **joint P(S-tier)**, which is
`P(binding) × P(epitope) × P(stability)`. Two things are worth reading off it:

- Two dashed lines mark the near-parent limits, both computed from the pipeline rather than
  typed in. The red line is the `<70%` CDRH3 identity floor. The amber line is the fewest
  substitutions any design clearing the strict distance-3 rule reaches in this pool. Left of a
  line, a design cannot pass that rule however well it scores.
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
