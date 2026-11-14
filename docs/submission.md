# Phase 7 — the submission

## The thing this fixes

The portfolio stage answers *"which four designs take the four guaranteed lab
wells."* That is not the same question as *"what do we submit,"* and until now
the repo only answered the first one. `results/order_sheet.csv` had four rows.

The organisers take **a ranked list of up to 20**:

| | wells |
| --- | --- |
| every team | 4 |
| 1st place | +16 |
| 2nd place | +12 |
| 3rd place | +8 |
| each of 6 judges may nominate | +2 |

So a list that stops at four forfeits every slot we win on the day. We had 205
eligible designs and were sending four of them.

## What it produces

```sh
make submission      # full pipeline, writes results/ including the four below
make ranked          # rebuild just the ranked list, no model re-run
python3 -m fourwells.cli submission results/
```

| File | What it is |
| --- | --- |
| `final_ranked_designs.csv` | **the submission** — up to 20, ranked, with axes, evidence basis, rationale and kill criterion |
| `candidate_scores.csv` | every candidate in the pool and why it did or did not make the list |
| `final_sequences.fasta` | sequences as ordered, rank and priority in the header |
| `submission.json` | machine-readable, full evidence, readiness and blockers |

`order_sheet.csv` is unchanged and still holds the four that take the
guaranteed wells. The two are different documents on purpose.

## Three decisions worth defending

**The four keep their portfolio order at the top.** That order is a joint
allocation across clusters, not a sort. Re-ranking them here by score would
silently discard the diversity decision the portfolio stage made. There is a
test that pins this: give pick 4 the best score in the pool and it must still
rank fourth.

**Ranks 5–20 fill round-robin across clusters, not straight down the score.**
Sixteen slots filled by score alone would be sixteen variants of whichever
CDRH3 family happens to score well — one hypothesis tested sixteen times.
Each cluster contributes its best before any contributes a second. On the
current pool that yields **18 distinct clusters and 20 distinct CDRH3 loops**
across the 20 submitted.

**Nothing is fabricated to fill a column.** A design with an unscored axis
exports an empty cell, never a zero, and a design with no joint score is not
placed in the list at all — you cannot rank what you have not scored. Stub
records and gate failures are excluded and say so in `candidate_scores.csv`.

## Readiness

`submission.json` carries `submission_ready` and a list of blockers,
recomputed from the records on every render rather than read from a stored
audit — a blocker that only lives in a stale file is a blocker that quietly
disappears.

Current blockers on `results/`:

1. **Every design is optimisation track.** The two tracks are judged
   independently, so the de novo entry is currently empty.

That one open item is deliberate rather than unresolved. The de novo track is
not reachable with the RFD4 antibody weights we were given — even at maximum
CDR length, identity to a known antibody is 0.779–0.823 against a 0.70 ceiling
([generation.md](generation.md#5-the-de-novo-track-is-not-reachable-with-these-weights)).
The exporter reports it honestly instead of papering over it.

The earlier "no abguard pass" blocker is cleared. abguard has since been run on
the VM (`abguard 0.1.0 / immunum 2.0.0`), and all 20 designs carry a recorded
pass; the 8 designs it rejected are excluded from the pool and recorded in
`data/reference/abguard_verdicts.json`.

## Current submission at a glance

20 of 20 slots filled, from 197 eligible of 401 generated. All 20 score the
epitope axis from measured structure rather than the paratope-conservation
prior. All 401 candidates are accounted for in `candidate_scores.csv`:

| | n |
| --- | --- |
| submitted | 20 |
| eligible, ranked below the top 20 | 177 |
| failed entry gates | 203 |
| reference molecule | 1 |
