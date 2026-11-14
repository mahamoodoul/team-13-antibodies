# The minimal system

What we have to build, reduced to the smallest thing that can win. Strategy and task
lists are in [docs/plan.md](docs/plan.md); the rules and datasets are in
[docs/brief.md](docs/brief.md). This is the system design, and its job is to say **no**
to work that does not change the submission.

## 1. The only artefact that must exist at 18:00

> A ranked list of up to 20 eligible designs, each with its reasons, reproducible by one
> command on a laptop with no network.

Four of those twenty are guaranteed a well. Everything in this document is justified by
that sentence or it is cut.

Scoring is 40% judgment · 20% execution · 20% user fit · 20% path to value. Note what
that means: **the reasoning is worth twice the pipeline.** A system that produces a
defensible ranking with a thin pipeline beats a beautiful pipeline with an
unexplained ranking.

## 2. What the system is

It already exists. [`fourwells/`](fourwells/) is the spine: a stdlib-only CLI, a frozen
record schema, four stages, offline by default.

```
fourwells run --budget 4 --candidates 24 --out results/
```

```
candidates ──▶ gates ──▶ three axis scores ──▶ portfolio ──▶ ranked JSONL + report
   (any         hard      binding · epitope      pick 4        up to 20, with
   source)      filters   · stability            of N          reasons per design
```

Four rules hold the design together:

1. **One record type, frozen.** [`fourwells/schema.py`](fourwells/schema.py) is the
   contract between all four lanes. Every stage takes a list of records and returns the
   list enriched. Any axis may be `null` while its predictor is unfinished — that is the
   normal state before 14:00, not an error.
2. **Generation is swappable.** Foundry supplies candidates; the ranking layer never
   knows that. If Foundry access dies we replace the first box and the rest stands.
3. **The reference runs the same path.** Trastuzumab goes through gates and scoring with
   every batch, so every number has a zero point. Each axis is a probability that the
   design beats the reference, which makes the reference score exactly 0.500 by
   construction.
4. **Offline by default.** `--online` is opt-in. The demo must run while the VM is dead
   and the conference wifi is gone, because tonight both will be true.

## 3. The UI, and what was cut from it

There **is** a dashboard — [`report.html`](fourwells/report.py), generated per run. It
sorts, filters, opens a dossier per design, and compares designs side by side. What was
cut is the *toolchain*, not the interactivity, and an earlier draft of this section got
that distinction wrong by cutting both.

| Cut | Why |
| --- | --- |
| React + TypeScript | A build toolchain is a liability on a judge's laptop, not a demo. Vanilla JS against a JSON blob in the page gives the same interactions with no install and no `node_modules`. |
| FastAPI backend | Nothing needs a server. The pipeline is a batch job that writes files, and the page reads data embedded in itself. |
| SQLite / PostgreSQL | Peak scale is ~24 candidates against 768 measured designs. JSONL on disk is greppable, diffable in git, and has no migration step. |
| Three.js structure viewer | **Decided, not deferred.** A judge asks why we picked these four, not to rotate a cartoon. It would also need a structure file per design that the pipeline does not produce. Do not re-propose this. |
| Live run-status UI | The run takes seconds and prints to stdout. |

What the page does, chosen because each answers a question a judge actually asks:

- **Sort by any axis** — "what if you'd ranked on stability instead?" is answered by
  clicking the column rather than by arguing.
- **Filter** by track, predicted tier, lab-slots-only, or free text.
- **A dossier per design** — axes with a tick at the 0.500 baseline, rationale, kill
  criterion, sequence, gate verdict.
- **Side-by-side comparison** — shift-click rows, or one button for the four lab slots.
  It bolds the per-axis winner and counts distinct clusters, which is the portfolio
  argument made visible: *four distinct clusters, so their failure modes are
  uncorrelated.*

The constraint that survives all of it: **no network at runtime**. No CDN, no web font,
no `fetch`, no external reference of any kind — asserted in tests, and the behaviour is
driven in headless Chrome by `tests/test_report.py` so that a sort which silently does
nothing cannot pass for one that works.

### The second UI: the call log

[`report.html`](fourwells/report.py) is for the judges. [`logs/index.html`](fourwells/logview.py)
is for us, and it answers a question the design records cannot.

```
make logs      # write logs/index.html
make watch     # live on 127.0.0.1:8765, re-read on every refresh
```

`designs.jsonl` records what we *decided*, not what we *asked*. When a run produces
nothing, the question is always: did the call fail, was it blocked by offline mode, or
did it return something we then discarded? That is unanswerable from the records, and it
has already cost us time. So every expensive call is recorded as one JSON line with its
request, its response, its duration, and one of four statuses — `ok`, `cache_hit`,
`offline_blocked`, `error`.

`Cache.memo` is the hook, because it is already the choke point every expensive call goes
through; `abguard` and the Foundry pipeline are instrumented directly, and each pipeline
stage is logged as a unit of work so the log alone answers "where did the time go".

The UI shows totals and latency percentiles, a per-provider breakdown ordered by time
spent, and the full log with filters by status, provider and run, plus a slow-only
(≥ p95) toggle. Clicking a row shows the request and the response it got back.

Two rules it has to keep, because a log that leaks or kills the run is worse than none:

- **Credentials are redacted at the write boundary**, not only in the recording helper.
  The first render of this UI printed an API key, because the entry had been written
  through `write()` and redaction lived one level up.
- **Logging can never be the reason a run dies.** An unwritable log directory disables
  logging and the run continues. That was also a real bug: the constructor used to raise.

`logs/` is gitignored. Credentials are stripped and bodies truncated, but it still holds
what we sent and what came back, and this repo is public.

## 4. State on disk

No database. One directory per run, never overwritten:

```
results/<run-id>/
  config.json       target, reference, seed, budget, git SHA, stage timings, warnings
  designs.jsonl     every candidate, every stage's output, failures included
  selected.jsonl    the designs taking the guaranteed lab slots
  report.md         the ranked submission and the dossiers, for the repo
  report.html       the same, self-contained and offline — the thing we show
```

`<run-id>` is a timestamp plus an 8-char hash of the inputs, so successive runs never
overwrite each other and two runs with identical inputs are obvious at a glance.
`--run-id` pins it when you want to diff two runs byte for byte. The cache is
content-addressed and shared across runs, so it sits outside the run directory.

Rejected candidates stay in `designs.jsonl` with their failure reasons. A pipeline that
silently drops its failures cannot be audited, and "what did you throw away?" is a
question a judge will actually ask.

The report is a *view* of the JSONL, never the record of truth: if rendering raises, the
run still saves its records and warns, and `fourwells report <rundir>` re-renders from
disk without touching a model. That matters at 17:00, when wording changes should cost
nothing and risk nothing.

Re-running with the same seed and inputs reproduces `designs.jsonl`, `selected.jsonl`
and `report.md` byte for byte — verified, not asserted. That is the 20% execution score,
and it holds because the cache is keyed on content rather than on time.

## 5. The ranking, which is the actual product

The objective is **not** a sorted list of predicted affinities. Tiers are counted per
design against the *measured* trastuzumab baseline: **S** beats all three axes, **A**
two, **B** one. Teams rank by S count first, then A, then B — two S-tier designs beat ten
B-tier ones. So what we maximise first is the expected number of designs that win on
three axes at once:

```
joint = P(binding) · P(epitope) · P(stability)
```

Two things that objective rewards and a weighted sum destroys: designs whose axes are
*jointly* good — excellent on two and hopeless on the third scores zero — and four
designs whose **failure modes are uncorrelated**. Four variants of one parent is one bet
placed four times.

The A-then-B tiebreak has a consequence worth building in, not just noting. Among designs
with little chance of S, prefer the ones most likely to take **two** axes over the ones
with a single spectacular axis — a lexicographic tiebreak on expected tier, not a second
sort by affinity. Concretely, the fourth slot should rarely go to the next-highest
`joint`; it should go to whichever design most changes the *distribution* of outcomes
across our four.

Three constraints on how evidence may be used, all three measured today, all three in
[`proof/`](proof/):

- **Never collapse the three axes into one opaque number.** Show each axis, its
  provenance, and whether it is predicted or measured. The whole thesis is that
  collapsing to affinity is the field's mistake.
- **Do not rank on a FACS-trained sequence model.** It reaches AUC 0.879 on held-out
  FACS data and 0.508 — chance — on the submittable SPR-measured designs; plain CDRH3
  identity to trastuzumab scores 0.750 on the same designs. See
  [`proof/tidy/enrichment.md`](proof/tidy/enrichment.md). The FACS set is an
  expression and tolerability prior, not the binding axis.
- **Do not gate on structure confidence.** A single ipTM cutoff means three different
  things across AF3, Boltz-2 and Chai-1; at 0.70 Boltz-2 admits 94% of shuffled
  non-binders and Chai-1 discards 92% of known binders. See
  [`proof/tidy/iptm_calibration.md`](proof/tidy/iptm_calibration.md). Confidence is a
  tie-breaker, never a filter.

And one reporting rule: **quote affinity against the assay's resolution.** Trastuzumab is
measured eight times in the provided SPR file, spanning 6.2× in KD. Any predicted
improvement smaller than that is inside the noise, and the order sheet says so next to
the number.

## 6. Gates are a precondition, not a final check

`abguard` rejects a failing design outright — it is never moved to the other track, and
the track is decided for us by identity to known antibodies. So gates run *before*
scoring, and a design that fails one never enters the ranking.

Shared, every design: format is VHH, scFv or Fab · ≤250 aa total (VH + VL combined) · no
unpaired cysteines · immunum numbering confidence ≥0.1.

| Track | Entry condition | Extra requirement |
| --- | --- | --- |
| De novo | <70% identity to **any known antibody** | ≥2 CDRH3 mutations from trastuzumab |
| Optimisation | everything else | <70% CDRH3 identity to trastuzumab **and** >2 point mutations from any provided antibody |

We do not choose the track — identity to known antibodies chooses it for us. So the useful
question is never "how do we split four between tracks", it is how far from trastuzumab
each design sits, because that distance is what assigns it. A design near the 70% line
could land either side, and we need to know which before we rank it.

The counterintuitive one, worth stating because it inverts the usual instinct: the <70%
identity rule is a **floor on how much we must change**, not a ceiling. A conservative
two-point CDRH3 mutant is rejected for being too *similar*. Roughly a third of CDRH3 has
to differ, which makes thermostability a live risk in the optimisation track rather than
the free pass it looks like.

A design also has to express to be measured at all. A non-expressing design scores
nothing on all three axes, so the expression screen is not polish.

## 7. Build order

Each phase ends with something demonstrable. Stop at any phase boundary and we still have
a submission. Status as of this revision:

**Phase 1 — a run that completes. ✅** `fourwells run` goes end to end and
[`examples/example-run/`](examples/example-run/) holds a committed run. This is the
safety net: if every model falls over, the command still produces a ranked list we can
defend.

**Phase 2 — real gates, real candidates. ✅** [`stages/gates.py`](fourwells/stages/gates.py)
runs the real filters, with [`align.py`](fourwells/align.py) added because identity was
previously only computed when two CDRH3 loops were the same length — an indel skipped the
<70% check entirely, and RFD4 changes loop length routinely, so that was the common case
rather than an edge one. [`stages/generate.py`](fourwells/stages/generate.py) replays
committed Foundry batches with the baseline row on the same path.

**Phase 3 — the three axes. ✅** [`stages/score.py`](fourwells/stages/score.py) returns a
probability per axis against the reference, with a one-line reason each.
[`fit_binding.py`](fourwells/fit_binding.py) fits the binding axis on the FACS labels —
and then rejects it on blind validation, which is the section 5 constraint arrived at
independently from the data rather than imposed from this document.
[`calibrate.py`](fourwells/calibrate.py) is wired into `score.py` via
`confidence_policy`, and currently reports *uncalibrated* — so structure confidence is
ignored by policy rather than trusted, which is the correct default and visible in the
run output.

One wording bug to fix there before the demo: the rationale strings in
[`score.py`](fourwells/stages/score.py#L32) and
[`portfolio.py`](fourwells/stages/portfolio.py#L289) still say "the 454 measured
non-binders". Those pairs are **shuffled and computational**, not SPR measurements — see
[`proof/audit_datasets.py`](proof/audit_datasets.py). Printing "measured" to a judge is
exactly the predicted-versus-measured confusion this system exists to avoid, and it is
in our own output. Rizve's files, so flagged rather than edited here.

**Phase 4 — portfolio and report. ✅** [`stages/portfolio.py`](fourwells/stages/portfolio.py)
implements the joint objective. [`report.py`](fourwells/report.py) renders `report.md` and
a self-contained interactive `report.html` — sort, filter, dossiers and side-by-side
comparison in vanilla JS, with zero external references so it opens from a `file://` URL
on a dead network.
[`runner.py`](fourwells/runner.py) writes the run directory and `config.json` with the git
SHA. `make report` re-renders the newest run.

One thing the renderer fixed rather than inherited: the portfolio stage marks the four
designs that take the *guaranteed* slots, but the organisers accept a ranked list of up to
**20**, and placing on the day buys 16/12/8 more slots plus a judge's nomination. A list
that stopped at four would discard every slot we might win, so
[`build_shortlist`](fourwells/report.py) keeps the four at the top in the portfolio's
order and fills the rest by joint score.

## 8. Done

Verified by running it, not by reading the code. `make demo && make unit` checks all of
the ticked boxes; 70 tests, offline, under a second.

- [x] One documented command runs end to end, offline — `make demo`
- [x] Same seed, same inputs → identical `designs.jsonl`, `selected.jsonl`, `report.md`
- [x] Every design traces to its source, config and git SHA — `config.json`
- [x] Three axes reported separately, each with a readable reason and its provenance
- [x] Predicted and measured values are never shown without a label, and nothing in the
      report calls a computational decoy "measured"
- [x] Stub-sourced records are flagged as a warning in the run output, not hidden
- [x] Rejections retained with their exact failure reasons, tallied by rule in the report
- [x] Ranked ≤20 exported, with the lab slots flagged and a reason for each
- [x] Report opens offline — zero external references, no network calls at runtime
- [x] The dashboard's sorting, filtering and comparison verified in a real browser
- [x] Cases the ranker gets **wrong**, named with the reason, above the reproduce section
- [ ] `abguard` verdicts recorded — the gate calls it, needs a run on the VM to confirm

That last box is not humility, it is scoring. A team that names its own failure mode
reads as credible; one showing only wins reads as overfitted. We have a null result on
the obvious approach and we are going to lead with it.

## The limit to state out loud

The lab measures binding by SPR, epitope preservation by competitive binding, and
thermostability directly. **None of that is available to us today.** Every number this
system produces is a prediction, and the system's job is to make four bets that are
worth a well — not to claim it already knows the answer. Any view that shows a predicted
value next to a measured one must label which is which.
