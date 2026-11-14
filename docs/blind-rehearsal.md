# The blind rehearsal

OWNER: Mahamoodoul. plan.md:337 — *"Pick two targets for the blind rehearsal; do not
tell Ansarul what they are until 16:00."*

The execution score rewards a pipeline that runs on a target it has not seen. This is
the test of that claim, and it is deliberately run by someone who did not write the
pipeline, on targets the pipeline was never tuned against.

## The targets

| Accession | Protein | Why this one |
| --- | --- | --- |
| `Q9NZQ7` | PD-L1 (CD274), 290 aa | A real, heavily-antibodied checkpoint target with no committed reference, no epitope annotation and no parent antibody in this repo. The realistic unseen-target case. |
| `P01375` | TNF, 233 aa | A trimeric cytokine, structurally nothing like a receptor ectodomain. Tests the opposite failure mode from PD-L1. |
| `examples/unseen_target.fasta` | Serum albumin | The decoy. Nobody designs a therapeutic binder against it here, so the pass condition is a *graceful refusal*, not a shortlist. |

Both accessions are cached under `cache/`, so the rehearsal reproduces offline on any
laptop with no network and no GPU:

```sh
make blind
```

## Pass conditions

The rehearsal is not asking "are the designs good" — on an unseen target there is no
baseline to be good against. It asks four things:

1. The run completes and writes a report, an order sheet and its records.
2. The target resolves and carries its sequence.
3. Nothing is claimed that was not computed — no epitope evidence invented for a
   target with no annotated epitope.
4. The order sheet refuses to look submission-ready.

## What it found — 2026-11-14

Runs complete, records are written, the cache serves offline, and the order sheet
blocks correctly. Two real findings, both worth saying out loud rather than fixing
quietly:

**1. The reference antibody does not follow the target.** `resolve_target` retargets,
but `resolve_reference_ab` defaults to trastuzumab independently of it. So a run against
PD-L1 produces *trastuzumab* CDRH3 variants, labelled `optimisation track, trastuzumab
scaffold`, against an antigen trastuzumab does not bind. The pipeline is target-aware in
its gates and target-blind in its generation.

This matters for the pitch. Slide 7 in [plan.md](plan.md#the-pitch) claims the ranking
layer is *"generation-agnostic, retargets to any antigen."* The ranking layer genuinely
is — gates, axes and portfolio all read from the record, not from HER2. **Generation is
not**, and the claim should be made about the ranking layer only.

**2. Epitope evidence is correctly absent, not invented.** PD-L1 resolves with
`epitope_residues: []`, and the epitope axis declines to score rather than guessing.
That is the behaviour we wanted and it is worth showing: it is the same mechanism that
caps a de novo design with no evidence it reaches HER2 domain IV.

## Handover protocol

The accessions above were chosen before any run and are recorded here rather than
passed verbally, so there is no question afterwards about whether they were picked to
flatter the result. Hand this file to Ansarul at 16:00, not before.
