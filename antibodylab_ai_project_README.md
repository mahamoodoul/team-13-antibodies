# AntibodyLab AI

## AI-guided Trastuzumab Optimization for HER2

**Mission:** Design and evaluate improved antibody candidates against
HER2, using trastuzumab as the reference. The scientific
design-and-evaluation engine is the main product. The dashboard is a
supporting workspace for inspecting every experiment and decision.

------------------------------------------------------------------------

## 1. The main problem

The Oslo AI Antibodies Hackathon asks teams to improve **trastuzumab**,
an antibody that binds to **HER2**.

Each design is evaluated against the trastuzumab baseline on three
properties:

1.  **Binding affinity:** bind HER2 as strongly as, or more strongly
    than, trastuzumab.
2.  **Epitope preservation:** preserve the same HER2 binding region
    recognized by trastuzumab.
3.  **Thermostability:** improve stability at higher temperatures.

The experimental tiers are:

  Tier           Properties improved against trastuzumab
  -------------- -----------------------------------------
  S-tier         All 3
  A-tier         2 of 3
  B-tier         1 of 3
  Unsuccessful   0 of 3

Improving all three is the strongest outcome. Computational predictions
are not experimental proof; the final properties are checked later in
the laboratory.

## 2. What we are building

### Scientific engine --- the priority

-   Inspect and use organizer-provided experimental and computational
    data.
-   Generate candidates using Apheris RFD4-Proteina.
-   Validate format, sequence, novelty, and hard rules using `abguard`.
-   Predict structures using available Apheris Foundry models.
-   Evaluate binding, epitope preservation, and thermostability
    separately.
-   Rank eligible candidates using evidence, uncertainty, and sequence
    diversity.
-   Export up to 20 ranked designs with explanations and provenance.

### Visual workspace --- supports the science

-   Show pipeline and model-run status.
-   Preserve every iteration.
-   Inspect sequences, structures, validation, and predictions.
-   Compare candidates and iterations.
-   Explain why candidates were kept, rejected, or shortlisted.
-   Export ranked designs and supporting evidence.

The pipeline must run independently of the browser. Closing the
dashboard must not stop a model job.

------------------------------------------------------------------------

## 3. Scientific workflow

``` text
Trastuzumab reference + HER2 target + organizer data
                         |
                         v
                  Data inspection
                         |
                         v
                 Choose design track
                  /             \
                 v               v
           Optimization       De novo
           HER2 CDRH3          Novel HER2
           redesign            CDRH3 design
                  \             /
                   v           v
                  RFD4-Proteina
                         |
                         v
                Candidate sequences
                         |
                         v
                      abguard
                    /         \
                 Reject       Eligible
                                |
                                v
                       Refold preparation
                                |
                                v
                    Structure prediction
                OpenFold3 / Boltz-2 / others
                                |
                                v
                   Evidence for three goals
                   /          |          \
                  v           v           v
              Binding      Epitope     Stability
              evidence    evidence     evidence
                   \          |          /
                    v         v         v
                 Multi-objective ranking
                         |
                         v
              Diverse shortlist (up to 20)
                         |
                         v
                 Laboratory validation
```

### 3.1 Establish the baseline

Before generating designs:

-   Identify the provided trastuzumab sequence and HER2 reference
    structure.
-   Record antibody format and chain information.
-   Identify the trastuzumab--HER2 reference interface.
-   Record available baseline measurements.
-   Keep reference files immutable and record checksums.

Every candidate is compared with the same reference.

### 3.2 Design tracks

The official `abguard` tool classifies each submitted design. The team
must not manually override the track.

**Optimization:** Modify an existing antibody while retaining useful
properties. The guide provides HER2-specific RFD4-Proteina weights for
redesigning trastuzumab CDRH3.

**De novo:** Generate a more novel antibody design intended to preserve
the original HER2 epitope. The guide provides a HER2-novel model for
generating mostly new CDRH3 loops.

Keep the two strategies as separately labelled branches. A design that
fails its track's checks is rejected, not moved to the other track.

### 3.3 Candidate generation

Use the documented RFD4-Proteina `design` task and the model weights
installed on the hackathon VM.

  -----------------------------------------------------------------------
  Model weights                       Intended use in the guide
  ----------------------------------- -----------------------------------
  `release-2026-10-19`                General protein/miniprotein design

  `antibody-2026-10-30`               Antibody design or CDR redesign on
                                      a fixed framework

  `her2-2026-11-07`                   HER2-focused trastuzumab CDRH3
                                      redesign

  `her2-novel-2026-11-09`             Mostly novel CDRH3 loops with
                                      predicted HER2 fit
  -----------------------------------------------------------------------

For `her2-2026-11-07`, the guide describes `--sequence-tsr-k 2` as
balanced and `--sequence-tsr-k 1` as exploratory. Confirm exact syntax
in the installed tutorial before running.

The guide reports a trade-off between known-binder recovery and novelty
for model settings. Treat those figures as prior benchmark observations,
not guarantees for new candidates. Generate a small pilot batch first,
inspect it, then scale up.

RFD4-Proteina tasks described by the organizers:

-   `design`
-   `refold-prepare`
-   `refold-score`
-   `finetune`

First establish a working pipeline with provided weights. Fine-tuning is
optional and should not be attempted without a clear evaluation plan and
enough time.

### 3.4 Validate candidates

Run every generated design through the organizer-provided `abguard` CLI.

The guide describes shared checks:

-   Format must be VHH, scFv, or Fab.
-   Total length at most 250 amino acids.
-   No unpaired cysteines.
-   Antibody numbering confidence at least 0.1.
-   Type-aware sequence identity comparison.

Track-specific checks described in the guide:

-   **De novo:** under 70% sequence identity to known antibodies and at
    least two CDRH3 mutations away from trastuzumab.
-   **Optimization:** under 70% CDRH3 identity to trastuzumab and
    strictly more than two point mutations from any provided antibody.

`abguard` extracts the antibody sequence, strips tags/linkers as
described in the guide, compares sequences by antibody type, and assigns
the track. A failed design is rejected, not reclassified.

Save the exact CLI output and failure reason for every candidate. Never
silently discard failures.

### 3.5 Predict structures

For eligible candidates:

1.  Run documented RFD4-Proteina `refold-prepare`.
2.  Predict the antibody--HER2 complex using an available co-folding
    model.
3.  Save model name/version, inputs, parameters, logs, and output
    structures.
4.  Run `refold-score` where applicable.
5.  Keep raw output files.

Models listed in the guide:

  Model                            Template support
  -------------------------------- ------------------
  OpenFold3 / OpenBind preview 2   Yes
  Protenix v2 / v1                 Yes
  Boltz-2                          Yes
  Boltz-1                          No
  Mol-1 base                       Yes
  ESMFold2                         No

For the HER2 exercise, the guide says the `refold-score` pass column
remains empty; rank using `min_ipae`, `iptm`, and `binder_plddt`.
Confirm this against the installed tutorial and actual outputs. A
template-supported model can provide a fairer binder-complex check than
an unguided target fold. No single structural metric proves experimental
binding.

### 3.6 Evaluate the three objectives separately

Do not hide all evidence inside one score.

**Objective 1 --- HER2 binding**

Collect evidence from relevant experimental data and candidate--HER2
complex predictions. Record `min_ipae`, `iptm`, `binder_plddt`, and
other documented interface metrics where available.

The guide reports 454 SPR-confirmed true-negative pairs, of which 21 had
AlphaFold3 ipTM at or above 0.7. High structure confidence alone can
therefore produce false positives. Use negative data to assess and
calibrate confidence filters.

Label predicted binding scores as predictions, not measured affinity or
probability of success.

**Objective 2 --- Epitope preservation**

Compare each predicted candidate--HER2 complex with the
trastuzumab--HER2 reference. Record whether the predicted interaction is
on the same HER2 region, the structural/interface comparison used,
deviations from the reference, and model uncertainty.

This is computational evidence only. Experimental confirmation is a
competitive binding assay against trastuzumab.

**Objective 3 --- Thermostability**

Treat thermostability as its own objective.

-   Inspect installed tools and documentation for a supported stability
    predictor.
-   If available, record predictor, version, output, and limitations.
-   Do not use pLDDT, ipTM, or general structure confidence as a
    substitute for thermostability.
-   If no suitable predictor is available, mark the computational result
    as `unknown`.

The final experimental thermostability measurement is performed directly
by the laboratory.

**Additional developability evidence**

The guide recommends considering Aggrescan 3D, SoluProt, NetSolP, and
ProteinMPNN with soluble weights because expression success may improve
when candidates are screened with these tools. Treat these as
expression/developability indicators, not direct measurements of
thermostability or HER2 affinity. Use them only if available and
documented on the VM.

------------------------------------------------------------------------

## 4. Data strategy

Read the bucket's `README.md` before processing files. It is the source
of truth for exact file names, schemas, and table definitions.

  --------------------------------------------------------------------------------------------
  Dataset                                      Contents                Intended use
  -------------------------------------------- ----------------------- -----------------------
  `her2-trastuzumab/`                          Trastuzumab CDRH3 FACS  Study sequence changes
                                               classes and SPR-related and experimental
                                               data                    binding evidence

  `zenodo-18390239-ab-ag-complexes/`           About 1.8M AI-predicted Explore
                                               antibody--antigen       cognate/non-cognate
                                               complexes               prediction behavior

  `sigma2-ab-ag-champloo/`                     Per-sample ipTM, pLDDT, Analyze prediction
                                               PAE and confidence data confidence and
                                                                       calibrate filters

  `sigma2-ab-ag-champloo/spr-supplementary/`   SPR measurements for a  Connect predictions to
                                               subset of pairs         measurements

  `zenodo-10831512-trastuzumab-ngs/`           Ready-made              Consistent FACS model
                                               train/validation/test   evaluation
                                               splits                  
  --------------------------------------------------------------------------------------------

The PDF describes:

-   524,346 trastuzumab CDRH3 variants, with up to 10 mutated positions,
    measured by FACS in three affinity classes.
-   Around 700 optimization designs from the same study, with 190 having
    measurable SPR affinity.
-   454 VHH--antigen true-negative pairs with no measurable SPR binding;
    21 have AlphaFold3 ipTM at or above 0.7.
-   Two non-cognate interactions with binary off-target labels.
-   15 cognate VHH--antigen affinity data points, all sub-micromolar.
-   About 1.8M predicted structures from 106 cognate and 11,342
    non-cognate pairings, predicted by AlphaFold3, Boltz-2, and Chai-1
    with 50 samples per pairing.

The Slack data announcement describes SPR affinities for 768 variants,
while the PDF separately describes around 700 optimization designs and
190 with measurable SPR. Inspect the actual README and tables to
understand the exact cohorts and definitions; do not assume these counts
refer to the same subset.

### Data-use rules

-   Use provided train/validation/test splits for FACS data.
-   Keep test data out of model fitting and threshold tuning.
-   Keep FACS classes distinct from SPR measurements; they are different
    assay outputs.
-   Do not treat AI-generated structures as experimental binding labels.
-   Use true-negative pairs to test how often high structural-confidence
    scores occur for non-binders.
-   Two non-cognate labels are too few to train a reliable general
    off-target classifier.
-   Fifteen cognate affinity points are too few to justify a complex
    affinity model by themselves.
-   Record dataset version, source, split, and preprocessing for every
    analysis.

Start with data inspection and baseline evaluation. Do not train a large
model simply because the data is available.

------------------------------------------------------------------------

## 5. Ranking and selection

### 5.1 Eligibility is a hard gate

A candidate must pass `abguard` before it can be considered for
submission. Eligibility is not a ranking bonus. A failed candidate
cannot be rescued by a high predicted score.

### 5.2 Candidate evidence table

Keep one record per candidate with:

  -----------------------------------------------------------------------
  Field                               Description
  ----------------------------------- -----------------------------------
  Candidate ID                        Permanent unique identifier

  Track                               Track assigned by `abguard`

  Sequence/format                     Amino-acid sequence and antibody
                                      format

  Generator                           RFD4-Proteina weights and version

  Validation                          `abguard` result and log

  Binding evidence                    Model metrics and/or relevant
                                      experimental evidence

  Epitope evidence                    Comparison with trastuzumab--HER2
                                      reference

  Stability evidence                  Supported predictor output or
                                      `unknown`

  Developability                      Optional expression/solubility
                                      indicators

  Uncertainty                         Missing evidence, model
                                      disagreement, limitations

  Diversity                           Similarity to other shortlisted
                                      candidates

  Decision                            Keep/reject/shortlist and
                                      explanation
  -----------------------------------------------------------------------

### 5.3 Ranking method

Use transparent multi-objective ranking instead of one unexplained
weighted score:

1.  Remove candidates failing hard eligibility checks.
2.  Keep optimization and de novo tracks correctly classified.
3.  Compare binding, epitope, and stability evidence separately.
4.  Identify candidates that are not dominated across available
    objectives.
5.  Consider uncertainty and disagreement between prediction models.
6.  Prefer a diverse shortlist rather than near-duplicate sequences.
7.  Record a human-readable reason for each final selection.

A Pareto-front approach can show trade-offs. It cannot create missing
evidence or prove experimental superiority. Do not invent a
thermostability score if no supported predictor is available.

### 5.4 Iteration policy

Each iteration should answer a documented question:

-   Does a different documented RFD4-Proteina setting produce more
    eligible designs?
-   Does a candidate retain a predicted interaction near the reference
    epitope?
-   Do independent structure-prediction models agree?
-   Does a new batch add useful sequence diversity?
-   Are high-confidence predictions incorrectly accepted by
    negative-control analysis?

Do not repeatedly optimize only the model's highest score; this can
exploit weaknesses in the prediction model.

Stop when the time/compute budget is reached or further iterations no
longer provide useful new candidates or evidence.

------------------------------------------------------------------------

## 6. Visual workspace

The dashboard is an inspection and decision interface for the scientific
engine.

### Overview

Show project/target, current run status, iteration count, candidates
generated, `abguard` pass/fail totals, prediction status, shortlisted
candidates, and recent errors. Clearly label demo data versus real
results.

### Iteration explorer

Every iteration is immutable and selectable. Display:

-   Iteration ID, parent iteration, timestamp, and status.
-   Design track, model weights, parameters, and random seed.
-   Candidate counts and validation outcomes.
-   Prediction jobs, failures, and elapsed time.
-   Candidate rankings and decision notes.

Allow comparison of any two iterations.

### Candidate detail

Display sequence, format, generator model/version, parameters, `abguard`
result, structure files, prediction metrics, separate evidence for all
three objectives, uncertainty, and selection/rejection rationale.

### 3D viewer

Use a browser-based molecular viewer to load saved structures, show HER2
and the candidate antibody, toggle chains, highlight CDR regions when
residue mapping is available, compare against the trastuzumab reference,
and rotate/zoom.

A visually plausible structure does not prove binding.

### Comparison and final selection

Provide candidate and iteration comparisons, plots for available
objective metrics, sequence diversity, a ranked list of up to 20
designs, and export of sequences, metadata, validation evidence,
predictions, and selection rationale.

------------------------------------------------------------------------

## 7. Technical architecture

``` text
React + TypeScript dashboard
             |
             v
        FastAPI backend
             |
       Run manager
             |
      Pipeline orchestrator
             |
   +---------+----------+----------------+
   |                    |                |
   v                    v                v
RFD4-Proteina        abguard        Structure models
   |                    |          OpenFold3/Boltz/etc.
   +--------------------+----------------+
                        |
                        v
              Evaluation and ranking
                        |
             +----------+----------+
             |                     |
             v                     v
       SQLite/Postgres       Artifact storage
       run metadata          FASTA/PDB/JSON/logs
             |                     |
             +----------+----------+
                        |
                        v
                    Dashboard
```

### Recommended stack

  -----------------------------------------------------------------------
  Layer                               Technology
  ----------------------------------- -----------------------------------
  Frontend                            React + TypeScript

  3D visualization                    Three.js / React Three Fiber or
                                      suitable molecular viewer

  Charts                              Recharts

  Backend                             Python + FastAPI

  Orchestration                       Python process/job manager

  Metadata database                   SQLite for a small hackathon
                                      implementation; PostgreSQL if
                                      needed

  Artifacts                           VM filesystem, organized by
                                      project/iteration/candidate

  Model execution                     Existing Apheris Foundry Docker
                                      images

  Logging                             Structured JSON
  -----------------------------------------------------------------------

Keep model execution independent of the frontend. Add a job queue only
if needed for concurrent or long-running jobs.

------------------------------------------------------------------------

## 8. Repository structure

``` text
antibodylab-ai/
├── README.md
├── config/settings.yaml
├── data/README.md
├── docs/
│   ├── scientific-method.md
│   ├── data-dictionary.md
│   └── model-usage.md
├── backend/
│   ├── app.py
│   ├── pipeline.py
│   ├── generator.py
│   ├── validator.py
│   ├── refold.py
│   ├── predictor.py
│   ├── evaluator.py
│   ├── ranker.py
│   └── storage.py
├── frontend/
├── artifacts/<project-id>/<iteration-id>/<candidate-id>/
├── results/
│   ├── candidate_scores.csv
│   └── final_ranked_designs.csv
└── tests/
    ├── test_validation.py
    ├── test_ranking.py
    └── test_iteration_storage.py
```

Keep large organizer data and generated structures out of Git. Store
paths and checksums in metadata.

------------------------------------------------------------------------

## 9. Reproducibility

Every run must save:

-   Original input references and checksums.
-   Candidate sequence and format.
-   Design track.
-   Generator model, weights, version, parameters, and random seed.
-   `abguard` command/version/output.
-   Structure model/version and parameters.
-   Raw prediction outputs and structure artifacts.
-   Metric names, values, units, and sources.
-   Ranking method/version.
-   Selection/rejection reason.
-   Start/end time, status, and error logs.

Never overwrite a previous iteration. A new attempt creates a new
iteration record. Every final candidate must be traceable to its inputs
and model runs.

------------------------------------------------------------------------

## 10. Hackathon VM setup

The organizers provide a Nebius VM with an NVIDIA H100 GPU, 16 vCPUs,
200 GB RAM, 500 GB disk, and Ubuntu 24.04 LTS.

Apheris Foundry models are already available as Docker images. The VM
does not have Foundry Hub; follow the VM-specific instructions.

### Download data

``` bash
aws s3 sync \
  s3://apheris-oslo-hackathon/data/ \
  hackathon-data/
```

### Download RFD4-Proteina documentation

``` bash
aws s3 sync \
  s3://apheris-oslo-hackathon/rfd4-proteina/docs/ \
  ~/rfd4
```

Read the VM instructions first:

``` bash
cat ~/rfd4/18-vm.md
```

Then open `~/rfd4/Tutorial.html` using an available browser or file
viewer.

Other provided resources:

-   `foundry.md` --- Foundry usage through UI, CLI, and agents.
-   `18-vm.md` --- running models on the hackathon VM.
-   `Tutorial.html` --- model examples.
-   `abguard` --- candidate validity checks.
-   RCSB MCP --- access to known protein structures.
-   Read-only credentials for the hackathon S3 bucket.

Use `foundry-toolkit module list` as documented by the organizers to
inspect available modules. Verify exact commands and options from
installed documentation; do not guess.

------------------------------------------------------------------------

## 11. Implementation phases

### Phase 1 --- Understand resources

1.  Read the data `README.md`.
2.  Inspect train/validation/test splits.
3.  Read `18-vm.md` and `Tutorial.html`.
4.  List installed model images and commands.
5.  Identify trastuzumab and HER2 reference files.
6.  Run one documented example.

**Deliverable:** Verified inventory of data, models, commands, and
reference inputs.

### Phase 2 --- Prove one scientific run

1.  Generate a small pilot batch using a documented RFD4-Proteina model.
2.  Save sequences and generation parameters.
3.  Run `abguard`.
4.  Prepare refold inputs for eligible designs.
5.  Run one documented structure-prediction model.
6.  Save raw outputs and metrics.
7.  Produce a candidate evidence table.

**Deliverable:** At least one candidate traced through generation,
validation, prediction, and saved results.

### Phase 3 --- Build evaluation

1.  Inspect FACS and SPR data separately.
2.  Evaluate structural confidence on true-negative pairs.
3.  Implement reference-epitope comparison.
4.  Check whether a supported thermostability predictor is available.
5.  Add uncertainty and missing-evidence reporting.
6.  Implement transparent multi-objective ranking and diversity
    selection.

**Deliverable:** Reproducible candidate evaluation report.

### Phase 4 --- Run design iterations

1.  Run the optimization branch.
2.  Run a de novo branch if time and model support allow.
3.  Compare model settings and novelty.
4.  Track candidate quality and model disagreement.
5.  Keep the best eligible and diverse candidates.

**Deliverable:** Traceable shortlist with reasons.

### Phase 5 --- Build the visual workspace

Prioritize iteration list/status, candidate table/detail, validation and
prediction evidence, candidate comparison, and finally the 3D viewer if
time permits.

**Deliverable:** Dashboard displaying actual pipeline outputs, not
fabricated demo values.

### Phase 6 --- Final submission and pitch

1.  Run `abguard` on every proposed design.
2.  Confirm track classification and eligibility.
3.  Prepare a ranked list of up to 20 designs.
4.  Export sequences and supporting evidence.
5.  Prepare a reproducible GitHub repository.
6.  Explain scientific reasoning, limitations, intended user, and path
    to real validation.

------------------------------------------------------------------------

## 12. Definition of done

-   A documented end-to-end workflow runs on the supplied target.
-   Candidate generation uses provided RFD4-Proteina models.
-   Every candidate is checked with `abguard`.
-   Eligible candidates pass through the documented structure-prediction
    workflow.
-   Binding, epitope, and thermostability evidence are reported
    separately.
-   Missing or uncertain evidence is clearly marked.
-   Ranking is reproducible and explained.
-   Every iteration and candidate can be inspected later.
-   The dashboard displays actual saved results.
-   Up to 20 designs can be exported with sequences and provenance.

## 13. Scientific limitations

-   High ipTM or another model confidence score is not proof of binding.
-   Predicted structures do not replace SPR or competitive binding
    experiments.
-   Structure confidence does not establish thermostability.
-   AI-generated structures are not experimental ground truth.
-   Small measured datasets must not be presented as sufficient to train
    a general-purpose affinity model.
-   Do not hide model disagreement or missing evidence.
-   Do not claim a candidate is experimentally improved before
    laboratory validation.
-   Follow the exact `abguard` eligibility checks and official
    submission instructions.

The guide says Adaptyv will perform cell-free expression, measure HER2
binding by SPR, test epitope preservation by competitive binding against
trastuzumab, and directly measure thermostability.

The pitch is judged on judgment (40%), execution (20%), user fit (20%),
and path to value (20%). Explain not only what the models produced, but
why the team trusts---or does not trust---the evidence behind each
selected design.

------------------------------------------------------------------------

## 14. Core principle

**Optimize the antibody first. Build the dashboard to make the
optimization process visible and trustworthy.**

A beautiful interface cannot compensate for weak scientific evidence. A
sophisticated model cannot compensate for an irreproducible workflow.
AntibodyLab AI combines a careful antibody design-and-evaluation engine
with a clear record of every decision.
