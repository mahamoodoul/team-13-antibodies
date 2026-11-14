# The plan — FourWells

> **Four of our designs are guaranteed a well. Which four do we send?**

How we're spending the day and who owns what. The challenge rules, datasets and model
inventory are in **[brief.md](brief.md)** — this is strategy and task lists, not a restatement.

Living version (editable, comment-able):
[claude.ai/artifact/2zfcViTnYM43ghkNazvGcF](https://claude.ai/artifact/2zfcViTnYM43ghkNazvGcF)

---

## The call

The target is HER2, the benchmark molecule is trastuzumab, and **only four of our designs
are guaranteed a well**. Generation is handed to us: Apheris Foundry serves RFD4-Proteina
with a checkpoint fine-tuned for this challenge. What is not handed to us is the choice of
which designs go to the lab — and each team ranks its own designs. That ranking is the
deliverable.

Three reasons selection is the whole game here:

1. **The budget is brutally small.** 64 of the 100 lab slots are simply 4 per team × 16
   teams. Extra slots are earned by placing on the day (12/8/4 for 1st/2nd/3rd) or being
   picked by a judge. Four bets is a portfolio problem, not a top-N sort.
2. **S-tier needs all three axes at once.** A design counts as S-tier only if it beats
   trastuzumab on binding, epitope competition *and* thermostability. The team with the most
   S-tier designs wins. So we are maximising the expected count of designs that win on three
   axes simultaneously — which is emphatically not the same as ranking by predicted affinity.
3. **Generation is commoditised today.** Every team gets the same HER2-fine-tuned model in
   Foundry. Everyone will have thousands of candidates by mid-afternoon. Nobody wins on
   candidate count.

### The strategic read most teams will miss

This is the reasoning to put on a slide, because it is where the 40% judgment score lives.

- **In the optimisation track, epitope competition is nearly free.** A trastuzumab variant
  binds where trastuzumab binds. So S-tier there effectively reduces to two axes — binding
  and thermostability.
- **In the de novo track, epitope is the axis that kills you.** A novel binder that hits HER2
  anywhere other than the trastuzumab epitope cannot compete with trastuzumab, so it can
  never be S-tier no matter how tightly it binds. Trastuzumab binds domain IV of the HER2
  extracellular region — so every de novo design must be epitope-targeted at domain IV by
  construction, not by luck.
- **Pick the beatable axis.** Trastuzumab is a heavily optimised therapeutic antibody;
  beating its affinity is genuinely hard. Beating its thermostability is more tractable. A
  design clearly better on stability and merely non-inferior on binding is a cheap A-tier;
  chasing affinity alone risks zero.

The field's own data supports the emphasis. In Adaptyv's EGFR competition the winning entry
optimised an existing therapeutic lead rather than designing from scratch, and the best
optimised binder reached 1.21 nM against 82 nM for the best de novo design
([lessons paper](https://www.biorxiv.org/content/10.1101/2025.04.17.648362.full.pdf),
[Cradle write-up](https://www.cradle.bio/adaptyv2)).

So: generate with Foundry, select with our own engine, and justify all four.

---

## Two scoring systems, running in parallel

They reward different things. The jury rubric decides placement, and placement buys extra
lab slots. The lab results decide the Apheris track prizes, and arrive after the event.

| Category | Weight | What we must hand them |
| --- | --- | --- |
| Judgment | 40% | A per-design dossier with explicit reasons, a stated kill criterion, and evidence our ranking beats random on real measured data |
| Execution | 20% | One command, pinned deps, fixed seeds, runs offline in under 10 minutes |
| User fit | 20% | A named user, the decision they face, the artefact they hand their CRO |
| Path to value | 20% | Where the ranking layer goes after today — it is generation-agnostic and retargets |

Two consequences worth internalising:

- **A beautiful pipeline with no evidence it works scores badly.** Most teams will show
  architecture. We show an enrichment number on data where the answer is already known.
- **Nobody gets points for the number of models we wired up.** A judge asking "why these
  four?" must get a crisp answer, not a tour of our dependency graph.

---

## Architecture

```
  two tracks ──▶ Apheris Foundry ──▶ trastuzumab baseline
                 RFD4-Proteina,       (same path, every batch)
                 HER2 checkpoint
                 Design → Refold → Score
                        │
                        ▼
                  abguard + entry gates          a failed gate
                  identity, ≥2 muts,             never reaches
                  cysteines, length              the lab
                        │
                        ▼
      ┌─────────────────────────────────────────────────┐
      │  Predict the three axes the lab measures,        │
      │  each against trastuzumab                        │
      │                                                  │
      │  Binding · SPR    Epitope · domain IV   Stability│
      │  hardest to beat  kills de novo      most beatable│
      └─────────────────────────────────────────────────┘
                        │
                        ▼
      ┌─────────────────────────────────────────────────┐
      │  Portfolio: four slots, four distinct hypotheses │
      │  S-tier needs all three at once → rank on the    │
      │  joint score, never four variants of one parent  │
      └─────────────────────────────────────────────────┘
```

Foundry supplies candidates, gates remove anything the lab would reject on sight, and the
three predictors feed one portfolio decision. Trastuzumab runs through the identical path so
every score has a reference. The ranking layer is generation-agnostic — if Foundry access
fails we swap the first box and the rest still stands.

---

## Who owns what

Four people, four non-overlapping surfaces. The rule that keeps this from deadlocking:
**agree the JSON schema between stages in the first 20 minutes, then never block on each
other.** Everyone writes against the schema with fake data until the real stage lands.

| Role | Owner | Surface | Must not touch |
| --- | --- | --- | --- |
| A — Spine | | CLI, orchestration, repo, caching, the demo run | Scoring logic |
| B — Ranking engine | | Gates, three axis predictors, portfolio step | Orchestration |
| C — Generation | | Foundry, the shared H100, refold-and-score metrics | The critical path |
| D — Proof and pitch | | Provided datasets, validation, report, pitch | Core pipeline code |

The contract between stages — settle this before anyone writes real code:

```json
{
  "design_id": "d001",
  "sequence": "QVQLVQSGAEVKKPGASVKVSCKAS...",
  "track": "optimisation",
  "format": "scfv",
  "parent": "trastuzumab",
  "cdrh3_identity_to_tras": 0.63,
  "gates": {"passed": true, "failed_rules": []},
  "axes": {"binding": 0.41, "epitope": 0.92, "stability": 0.78},
  "joint_score": 0.29,
  "cluster": "c3",
  "rationale": ["CDRH3 redesigned to 63% identity, clears the 70% ceiling",
                "paratope contacts at domain IV retained"],
  "kill_criterion": "loses trastuzumab competition in the epitope assay"
}
```

Every stage reads a list of these and returns the list enriched. Any axis may be `null` while
its predictor is still being built — that is the normal state before 14:00, not an error.

Two roles are tempting to skip and must not be. D is not "the person who makes slides": they
own the 40% category and the proof. A is not "the person who does glue": they own the thing
the judges will actually run.

---

## The day

```
10:00  12:00                    16:00        18:00
  │      ┊                        ┊            │
  ├──────┊────────────────────────┊────────────┤
  │      ┊                        ┊            │
A │ schema ─ stubbed e2e ─ integrate ─ FREEZE ─ rehearse ─ SUBMIT
C │ foundry ─ datasets ─ baseline ─ opt batch ─ de novo ─ final
B │ gates ───── three axis predictors ──────── pick the four
D │ datasets ── ground truth ── enrichment result ── report + deck
       ┊                        ┊
   stubbed                   code
   end to end                freeze
```

The two dashed lines are the only deadlines that cannot move.

**12:00 — stubbed end to end.** Dummy data flowing through every stage, start to finish. Not
working, not accurate, just connected. Four developers who skip this and integrate at 16:00
is the single most common way a hackathon team ends the day with nothing to show.

**16:00 — code freeze.** Everything after is selection, report, rehearsal. No refactors, no
new dependencies, no clever idea at 17:15.

| Checkpoint | Question |
| --- | --- |
| 10:00 | Schema agreed? Who is blocked on access? |
| 12:00 | Does a dummy design flow end to end? If no, cut scope now |
| 14:00 | Real candidates scored? Is the proof experiment running? |
| 16:00 | Freeze. What are our four designs and why those four? |
| 17:00 | Rehearse the pitch out loud, twice, timed |

**If you are reading this late in the day**, cut in this order: drop the de novo track and
submit four optimisation designs, drop CLI generality and hard-code HER2, drop the report
renderer and hand-write the four dossiers. Never cut the trastuzumab baseline, the entry
gates, or the pitch.

---

# Task lists by person

## Dev A — the spine

You own the thing the judges type a command into. Success metric: an unseen target runs
clean, offline, in under ten minutes.

- [ ] Agree the design-record schema with B, C and D — 20 minutes, then it is frozen
- [ ] `fourwells run --target <uniprot|fasta|pdb> --budget 4 --out results/` as the single entry point
- [ ] Target resolver: UniProt ID, raw sequence or structure file, plus an optional reference
      antibody to beat. HER2 and trastuzumab are default arguments, never hard-coded
- [ ] Stage runner with per-stage timeboxes; the no-network path is the default
- [ ] Disk cache for every Foundry call and fetch, keyed by sequence hash, committed
- [ ] **Stub every stage first and get an end-to-end run producing dummy output by 12:00** —
      the most important deadline of the day
- [ ] Pinned `requirements.txt`, fixed seeds everywhere, `--seed` flag
- [ ] `make demo` that runs a bundled example end to end with no arguments
- [ ] Rehearse the blind run on two targets picked by Dev D that you have not seen

Two things to resist. Do not let the pipeline grow a stage that only works on your laptop.
And do not refactor after 16:00 — freeze and make the demo bulletproof.

## Dev B — the ranking engine

You own what decides which four designs go to the lab. Build it to predict the three axes the
lab actually measures — not generic developability metrics, and not affinity alone.

### Layer 1: gates and expression screen (first hour, non-negotiable)

Wrap `abguard` so nothing enters the ranking without a clean pass, and record the rejection
reason. Then add the expression screen, because a design that does not express scores nothing
on all three axes.

- [ ] `abguard` wrapper returning a named reason per rejection; report the reason
      distribution, which tells Dev C whether generation is drifting
- [ ] Expression pre-screen: Aggrescan 3D, SoluProt, NetSolP, ProteinMPNN soluble weights —
      [the brief](brief.md#submission-rules) names these as what lifted Adaptyv's earlier rounds
- [ ] Our own copy of the cheap checks so we fail fast before calling anything hosted: length,
      unpaired cysteines, natural residues, CDRH3 identity to trastuzumab, distance from the
      provided antibodies

### Layer 2: one predictor per lab axis

Three scores, each in 0–1, each meaning "probability this beats trastuzumab on that axis",
each with a one-line human-readable reason. **Always score trastuzumab itself through the
identical pipeline and show it as the baseline row** — that single habit makes every other
number interpretable.

- [ ] **Binding.** Fit on the 524K FACS-labelled CDRH3 variants — same target, same parent,
      already labelled. A gradient-boosted model over sequence features trains in minutes on
      CPU and is defensible; reach for a language model only if that lands early. Use
      folding-model confidence as a *feature*, never as the score.
- [ ] **Epitope retention.** For optimisation designs, paratope conservation — which
      trastuzumab contact residues survive. For de novo, check the predicted complex actually
      contacts the trastuzumab epitope on HER2 domain IV. Anything binding elsewhere is capped
      at A-tier and must be ranked accordingly.
- [ ] **Thermostability.** The most beatable axis, so give it real effort. From sequence and
      structure: framework germline reversion count, hydrophobic patch area, net charge and pI
      distance from 7, disulfide integrity, loop length relative to germline, packing quality
      from the refolded structure. JapanFold's AF2-IG is antibody-specific and already paid
      for — worth a look if Dev C has it working.
- [ ] **Calibrate the structure-confidence cutoff on the 454 true negatives**, not on a
      remembered threshold. 21 of them score ipTM ≥ 0.7 while being measured not to bind.

### Layer 3: the portfolio step — this is the 40%

Do **not** sort by a weighted sum. The objective is the expected number of designs that beat
trastuzumab on all three axes.

- [ ] Score the joint objective — roughly `P(binding) × P(epitope) × P(stability)` per design,
      which punishes a design excellent on two axes and hopeless on the third, exactly as the
      S-tier rule does
- [ ] Cluster by parent, by CDRH3 and by predicted binding mode, then **allocate the four
      slots across clusters, not down the ranked list**. Four variants of one parent share a
      failure mode; if the parent is wrong, all four die together
- [ ] Check which track each of the four lands in — `abguard` assigns it by identity, we do not
      choose. If all four land in one track, that should be a decision we made, not an accident
      we discovered
- [ ] Emit per design: the three predicted axes, the trastuzumab baseline for each, the reason
      it survived, the cluster it represents, and an explicit kill criterion

That last bullet is literally what "clear reasoning behind the molecules chosen" means. Write
the reason strings as if a judge will read one aloud, because one will.

## Dev C — generation and compute

You own candidate supply and the shared box. Setup is in the [README](../README.md); model
inventory is in [brief.md](brief.md#models). The good news: no CUDA wrangling. Foundry runs on
the VM, Nebius serves 34 hosted models needing no GPU, and JapanFold is paid for.

The constraint that shapes your whole day: **one H100 shared by four people, and first model
calls can queue 15 minutes.** Start long jobs early, never submit the same job twice, stay in
your own folder on the shared home.

- [ ] **By 10:30** — on the box, keys loaded, one trivial hosted job returned through
      `forge.py`. If access is blocked, find an Apheris mentor at once; Egor Marin and Leonardo
      Castorina are both here and both are judges
- [ ] **By 11:00** — provided datasets unpacked and handed to Dev B. The 524K variant set and
      the 454 true negatives are what Dev B is blocked on, so these come before anything you
      generate
- [ ] **By 11:30** — trastuzumab itself run through the full Design → Refold → Score path as
      our baseline. Everything we later claim is relative to that row
- [ ] **By 13:00** — first real batch, optimisation track. The <70% CDRH3 identity rule forces
      substantial diversification, so generate boldly rather than conservatively
- [ ] **By 14:30** — de novo batch, epitope-conditioned on HER2 domain IV using trastuzumab
      contact residues as hotspots. A de novo design that binds elsewhere cannot be S-tier
- [ ] **By 16:00** — final batch scored, metrics exported into our schema, handed to Dev B.
      Then stop generating and help rehearse

Four rules:

1. **Refold is the signal, not the design confidence.** A folding model given only the sequence
   must recover the designed complex. A design whose refold diverges from its intended complex
   is a bad bet however good its design score looked. Export that agreement explicitly — Dev B
   needs it as a feature.
2. **Carry the trastuzumab baseline through every batch.** Without it no score means anything.
3. **Commit results to `results/` and run ids to `nebius-runs/` as you go.** The VM dies
   Saturday night, and a number we cannot trace to a run is a number we cannot defend on stage.
4. **Diversity beats volume.** Dev B's gates will cut most of it, and the portfolio step needs
   genuinely distinct hypotheses. Thousands of near-duplicates of one parent are worth less
   than forty spread across four ideas.

If Foundry access fails entirely, fall back to CDR point-mutation sampling on trastuzumab plus
any hosted folding model, and the pitch says we built the ranking layer generation-agnostic —
which is true, and a better story than a broken dependency.

## Dev D — proof and pitch

You own the largest scoring category and the only artefact the judges are guaranteed to see.
This is the highest-leverage seat on the team, not the support role.

### Morning (10:00–12:00)

- [ ] Unpack the provided datasets as soon as Dev C has them and read
      [brief.md](brief.md#data-we-were-given) properly. The 524K labelled variants, the 190
      SPR-measured designs and the 454 true negatives are the three that matter
- [ ] Get each into a tidy CSV and hand them to Dev B as fixtures — Dev B is blocked on these
- [ ] Design the held-out split yourself — split by mutation count, not at random, so the test
      set is not a near-neighbour of training. Getting this wrong invalidates the headline number
- [ ] Pick two targets for the blind rehearsal; do not tell Dev A what they are until 16:00

### Midday (12:00–14:00)

- [ ] Epitope evidence: which HER2 domain IV residues trastuzumab actually contacts, so Dev B's
      epitope predictor and Dev C's hotspot conditioning use the same list. AMASS is paid for
      and the mentors will recognise it
- [ ] Cache everything to disk

### Afternoon (14:00–17:00)

- [ ] Run Dev B's ranker over the held-out SPR designs and the true negatives, and produce the
      enrichment result — see below, this is the centrepiece
- [ ] Report renderer: ranked table, per-design dossier, reasons, kill criteria. Markdown plus
      a single self-contained HTML file
- [ ] A one-page order sheet: sequence, track, format, rationale, priority
- [ ] Draft the pitch; rehearse twice out loud before 18:00

One discipline point: you will be tempted to help debug. Do not. If the proof and the pitch are
not done, a working pipeline scores badly anyway.

---

# Reference

## The proof: show the ranker works

The single thing most likely to win the day, and it is pure software work. Every team will show
a pipeline. Almost none will show evidence their ranking beats picking at random — and we have
been handed the data to prove it.

### We do not need outside data

[brief.md](brief.md#data-we-were-given) lists what we have. Three pieces matter:

| Dataset | Why it is decisive |
| --- | --- |
| 524,346 trastuzumab CDRH3 variants, FACS, 3 affinity classes | Same target, same parent, labelled. A training set for a sequence → affinity model, not just a novelty reference |
| ~700 optimisation designs, 190 SPR-measured | Held-out validation with the *same assay the judges will use*. This is our enrichment number |
| 454 VHH–antigen true negatives, 21 with AF3 ipTM ≥ 0.7 | Measured **not** to bind. The only way to calibrate a structure-confidence cutoff before trusting it |

### The slide that wins the judgment category

Those 21 true negatives scoring ipTM ≥ 0.7 are the most valuable rows in the whole challenge.
They are direct, measured proof that **high structure confidence does not mean binding** —
exactly the mistake the rest of the field makes, and exactly what our ranker is built to avoid.

1. Fit the binding predictor on the 524K FACS-labelled variants. Hold out a clean slice by
   mutation count so the test set is not a near-neighbour of training.
2. Rank the 190 SPR-measured optimisation designs blind. Report hit rate in our top 4, top 10,
   top 25 against the hit rate of the full 190. **Top 4 is the number that matters** — it is the
   decision we are actually making.
3. Run the ranker over the 454 true negatives. Show what fraction of the ipTM ≥ 0.7 decoys our
   joint score correctly rejects where a structure-confidence filter alone would have accepted them.
4. Set the structure-confidence cutoff *from that curve*, not from a round number someone
   remembered.

Step 3 is the headline. "A confidence filter would have ordered these 21; we rejected N of them,
and here is why" is a concrete, measured claim about judgment — which is 40% of the score.

### Reporting it honestly

- State enrichment as one number a judge can repeat: "our top 4 held 3× the binder rate of the pool"
- Report the three axes separately, since our whole thesis is that collapsing them into affinity
  is the error
- Name one case the ranker got **wrong**, with the reason. A team that names its own failure mode
  reads as credible; one showing only wins reads as overfitted

If enrichment comes out flat, **report it anyway** and spend the slide on why. A team that ran the
experiment and reported a null result demonstrates more judgment than one that never checked.

The 1.8M predicted complexes are a tempting rabbit hole. Touch them only if everything else is
done — they are a modelling project, not a one-day one.

## What the entry criteria imply

Exact rules are in [brief.md](brief.md#submission-rules). Four implications worth acting on:

- **The track is decided for us, by identity to known antibodies.** We do not pick it. So "how do
  we split our four between tracks" is the wrong question — the right one is how far from
  trastuzumab each design sits, because that distance is what assigns it. A design near the 70%
  line could land either side; know which before you rank it.
- **The <70% CDRH3 identity rule in the optimisation track is a floor on how much we must change,
  not a ceiling.** This inverts the usual instinct. A conservative two-point CDRH3 mutant is
  rejected for being too similar to trastuzumab. Roughly a third of CDRH3 has to differ — which
  makes thermostability a live risk in the optimisation track rather than the free pass it would
  otherwise be.
- **A design has to express to be measured at all.** A non-expressing design scores nothing on all
  three axes, so expression screening is not optional polish.
- **`abguard` fails silently if you skip the filters.** Treat a clean pass as a precondition for a
  design entering the ranking at all, not as a final check at 17:50.

### The objective that falls out of the tier rule

Maximise the **expected number of S-tier designs among our four**, which is not the same as ranking
by predicted affinity. It rewards two things a weighted sum destroys: designs whose three predicted
axes are *jointly* good — excellent on two axes and hopeless on the third scores zero S-tier — and
designs whose failure modes are *uncorrelated* with each other.

## The pitch

Submission closes 18:00, presentations start 18:05. Build for about five minutes. Seven slides,
one idea each.

| # | Slide | The line to actually say |
| --- | --- | --- |
| 1 | The question | "Four of our designs are guaranteed a well. Trastuzumab is the thing to beat. Which four do we send?" Then stop for a beat. |
| 2 | Why it is hard | S-tier means beating trastuzumab on binding, epitope and thermostability at once. Everyone here will have thousands of candidates by three o'clock. Nobody wins on candidate count — the prize is decided by a ranking. |
| 3 | What we built | The pipeline diagram, 20 seconds. Foundry generates, we gate, predict three axes, allocate four slots. |
| 4 | How we decide | Epitope is free in optimisation and fatal in de novo, so every de novo design is conditioned on domain IV. Stability is the beatable axis. We rank on the joint probability, not a weighted sum, and never spend four slots on four variants of one parent. |
| 5 | **The proof** | The enrichment result, and the 21 ipTM-confident non-binders we rejected. This is the slide that wins or loses. Include the case we got wrong. |
| 6 | Our four | Show them. Each one's hypothesis, its three predicted axes against the trastuzumab baseline, its kill criterion. The most concrete thing any team will put on screen. |
| 7 | What is next | What the lab results would tell us, what we would change, and why the ranking layer outlives this challenge — generation-agnostic, retargets to any antigen. |

Five things to get right in delivery:

- **Lead with the decision, not the architecture.** Every other team will open with their stack.
- **Always show the trastuzumab baseline row.** It makes every number mean something and is the
  cheapest credibility in the room.
- **Say what you deliberately did not do.** "We did not try to out-model Foundry in seven hours"
  is a judgment statement, and judgment is 40%.
- **Name your failure mode before a judge finds it.** You will be asked how you know this works —
  slide 5 is the answer, so get there fast.
- **Have the output pre-rendered.** Do not live-run anything at 18:05 on venue wifi.

The line for "is this real biology?": we are not claiming a better generative model — we are
claiming that with four wells the ranking *is* the science, that it is measurable on the data we
were given, and that we measured it.

Worth making on slide 7: placing on the day earns 12, 8 or 4 extra lab slots on top of the
guaranteed four. A good pitch is not separate from the lab result — it buys more shots at it.

## Risks and kill switches

| Risk | Owner | Kill switch | Decide by |
| --- | --- | --- | --- |
| Foundry access blocked or slow | C | CDR point-mutation sampling on trastuzumab; escalate to an Apheris mentor at once | 10:30 |
| A dependency will not install | B | Simplest working fallback; never block on a package | 30 min after first attempt |
| Datasets messier than expected | D | Binary binder/non-binder labels are enough for an enrichment story | 12:00 |
| Enrichment comes out flat | D | Report the null result honestly; pivot slide 5 to what it taught us | 16:00 |
| Pipeline not end-to-end by midday | A | Cut generation to point-mutation sampling; the selection layer is the product | 12:00 |
| Chasing affinity alone, ignoring stability | all | Anyone may call it; S-tier needs all three | always |
| A submitted design fails an entry gate | A | Run the gate checker over the final four twice, by two different people | 16:00 |
| VM or venue network dies | A | Everything cached and committed as we go, slides exported to PDF | 17:00 |

The two failure modes most likely to actually sink us:

1. **Nothing runs end to end until 16:00.** The classic four-developer hackathon death. The
   mitigation is the stubbed end-to-end run by 12:00. Protect that deadline over everything else.
2. **Four people building four disconnected pieces.** Mitigated by freezing the schema in the
   first 20 minutes and by the 14:00 integration checkpoint where everything merges whether or
   not it is finished.

## Mentors — go in with one specific question

Mentoring is the cheapest score improvement available and most teams under-use it. Several of
these people are also judges, and each of six judges picks two extra designs for the lab — so a
good conversation is worth actual lab slots.

| Mentor | Affiliation | Ask them |
| --- | --- | --- |
| Victor Greiff | UiO, IMPRINT | Whether our three-axis predictors match what actually separates a good HER2 binder from a bad one |
| Leonardo Castorina | Apheris | Sanity-check the selection logic; what separates an S-tier design from an A-tier one in practice |
| Egor Marin | Apheris | Foundry itself: which checkpoint, which folding model to score with |
| Daria Balashova | Nebius | Compute setup, fast — go early if anything is stalling |
| Arseniy Sokolov | Nebius | Same |

## 18:00 submission checklist

- [ ] **Our four designs submitted and ranked**, every entry gate re-checked by a second person
- [ ] A dossier per design: hypothesis, three predicted axes against the trastuzumab baseline,
      kill criterion
- [ ] Repo README complete, validation result in the first screen
- [ ] Pitch deck submitted before 18:00, exported to PDF locally as backup
- [ ] Example output committed so the repo demonstrates itself without being run
- [ ] Output pre-rendered for the pitch — nothing live at 18:05
- [ ] All four names on the repo and the deck

---

**Sources.** [Event page](https://oslo-ai-antibodies-hackathon.vercel.app/) ·
[Adaptyv EGFR round 1 data](https://github.com/adaptyvbio/egfr_competition_1) ·
[Crowdsourced protein design lessons](https://www.biorxiv.org/content/10.1101/2025.04.17.648362.full.pdf) ·
[Adaptyv on choosing design methods](https://adaptyvbio.substack.com/p/protein-optimization-102-lessons) ·
[Cradle on optimising a lead](https://www.cradle.bio/adaptyv2) ·
[Germinal preprint](https://www.biorxiv.org/content/10.1101/2025.09.19.677421.full.pdf)
