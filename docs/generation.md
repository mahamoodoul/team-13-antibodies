# Generation: what we made, and what it taught us

Everything in `data/generated/` came from Apheris Foundry on the hackathon VM. This is the
record of how, with the yields measured rather than quoted, so any number in the pitch can be
traced back to a run. The VM is wiped Saturday night; this file and the committed batches are
what survive.

Owner: Ruhit. Pipeline stage: `fourwells/stages/generate.py`. VM scripts: `scripts/`.

## The batches

All four ran RFD4-Proteina on one H100, as Docker images already on the VM. Provenance for
each is committed beside it as `*.provenance.json` — weight, seed, replicate count, image
digest, start time.

| batch | weight | designs | distinct CDRH3 | submittable | 4-5 subs | refolded |
| --- | --- | --- | --- | --- | --- | --- |
| `optA` | `her2-novel-2026-11-09` | 100 | 97% | 90 | 5 | 43 |
| `optB` | `her2-2026-11-07`, `sequenceTsrK=1` | 100 | 100% | 73 | **24** | 20 |
| `multicdr` | `antibody-2026-10-30` | 100 | 94% | **99** | 0 | — |
| `denovo` | `antibody-2026-10-30` | 100 | — | see below | — | — |

"Submittable" means it passes the real challenge filter: CDRH3 differing at 2+ positions from
every one of the 525,063 provided CDRH3s, **and** at least 4 of 10 positions changed from the
parent. "4-5 subs" counts submittable designs closest to the parent loop.

Our yields match the Apheris published figures closely, which is a useful check that the
generators behaved as documented rather than that we got lucky:

| | published | measured |
| --- | --- | --- |
| her2-novel, passes filter | 86% | 90% |
| her2-novel, distinct | 90% | 97% |
| exploratory, passes filter | 74% | 73% |
| exploratory, distinct | 100% | 100% |

Reproduce any batch from `~/ruhit/gen`:

```bash
WEIGHT=her2-novel-2026-11-09 N=100 SEED=1 OUT=runs/optA bash scripts/design_batch.sh
OUT=runs/optA WEIGHT=her2-novel-2026-11-09 SEED=1 MODEL=boltz2 MAXFOLD=25 \
  bash scripts/refold_chain.sh
```

100 designs took 11.5 minutes with `--compile true`, against the documented ~30 s per design.

## Five things we measured that changed what we did

### 1. The challenge filter belongs in front of the GPU, not after it

`refold-prepare` ranks by its own structural criteria — hotspot obedience, interface H-bonds,
clashes — and knows nothing about the novelty rule. On the first 4-design test it selected a
design with only 3 CDRH3 substitutions, which cannot be submitted, so half the refold budget
went on a design we could never send. Folding is the expensive step.

`scripts/filter_queries.py` now runs the real filter before folding. On the 100-design batch it
dropped 10, including two whose CDRH3 is *already in the provided screen verbatim*
(`WGPPGFYAFD`, `WGSTGFYAFD`) and six sitting within one substitution of a screened variant.

### 2. The novelty rule and the affinity cliff pull against each other

Rizve measured median K_D degrading monotonically with distance from the parent loop — 0.18 nM
near-parent to 160 nM below 40% identity — so among designs that clear the gate we want the
*least* changed. But the 524,346-variant FACS screen densely samples exactly the near-parent
space, so the least-changed designs are the most likely to land within one substitution of
something already screened.

This is not theoretical. Three of the first four shortlisted designs would have been rejected
by abguard on that rule, because the ranker correctly preferred 4-substitution designs and
4-substitution designs are where the collisions are. Each collided with a real provided
sequence at a single position:

```WGYSGFYTYD  vs provided WGGSGFYTYD
WTGRGFYSFD  vs provided WAGRGFYSFD
WGSSSFYAFD  vs provided WGSSDFYAFD```

The target is not "fewest substitutions" but **fewest substitutions that still clear novelty
against all 525,063**. That band is narrow, and `her2-2026-11-07` with `sequenceTsrK=1`
populates it far better than `her2-novel` does — 24 submittable designs at 4-5 substitutions
against 5 — even though `her2-novel` has the higher overall pass rate.

`data/reference/provided_cdrh3_universe.txt.gz` holds all 525,063 sequences, 1.4 MB gzipped, so
the check runs offline in a judge's own run. Testing it by generating a loop's 190
single-substitution neighbours and doing set lookups is exact and about 3000x faster than
scanning the table per design; the full 300-design check takes well under a second.

### 3. The baseline row is what makes any of the numbers mean something

Trastuzumab is folded through the identical path as every design — same model, same 1N8Z
template, same seed, same flags — and emitted as an ordinary record, not a special case.

Then we did it with a second model, which is where it got interesting:

| | ipTM | pTM | binder pLDDT | designs above baseline |
| --- | --- | --- | --- | --- |
| Boltz-2 | 0.960 | 0.969 | 98.39 | **0 of 25** |
| Protenix v2 | 0.676 | 0.784 | 93.12 | **8 of 18** |

Boltz-2 puts a clinical antibody, with a crystal structure of this exact complex, 0.04 from the
ceiling. That leaves the metric no headroom: across 25 refolded designs not one exceeded it and
all were compressed into 0.813-0.932. Protenix puts the same binder at 0.676 and the designs
land either side of it, 0.638-0.713.

Same designs, same pipeline. One model produces a usable ranking signal and the other produces
a saturated one — and the only reason we know is that the baseline went through the identical
path. **Compare a design only against the baseline for its own folding model.** Records carry
`axis_evidence["refold_by_model"]` for exactly this.

This agrees with the independent calibration data. On the Smorodina matrices, across ~8,100
VHH-antigen pairs measured *not* to bind, Boltz-2 gives 94.3% of them ipTM ≥ 0.7 (median 0.88,
against 0.91 for real pairs). AF3 gives 3.0% (median 0.18 against 0.50). Boltz-2's interface
confidence barely separates binders from non-binders, so it is a feature and never the binding
score.

### 4. A pattern we reported and then withdrew

We briefly claimed that designs far from the parent fold more confidently, which would have put
refold confidence in tension with the affinity cliff. It does not survive contact with data:

```Spearman(substitutions from parent, ipTM)
  Boltz-2      n=43   +0.044
  Protenix v2  n=18   +0.348, over 3 substitution values, group means 0.652 / 0.669 / 0.675```

The original claim rested on one design at the bottom of a 25-row table. Refold confidence
simply does not track distance from the parent, which is the simpler and better outcome: there
is no contradiction to explain, and the cliff stands unopposed.

It is recorded here because a team that reports only the patterns that held is not showing its
working.

### 5. The de novo track is not reachable with these weights

We tried properly: HER2 domain IV as the target, a separate antibody framework, all six CDRs
designed at maximum length, and the four trastuzumab-epitope atoms as conditioning hotspots so
a de novo binder would compete where trastuzumab binds.

It cannot clear the entry rule. Measured over the batch, maximum identity to a known antibody
is **0.779 to 0.823**, against a ceiling of 0.70.

The reason is structural rather than a tuning problem. RFD4's antibody model keeps the
framework fixed by design and only builds CDRs, and the retained framework is about 80% of the
sequence. No choice of CDR length closes a 10-point gap — we generated at maximum CDR length
specifically to find out.

So "how do we split our four between the two tracks" was the wrong question for us: with these
weights every design we can make is an optimisation design. The batch is kept as a fourth
hypothesis on a different framework, labelled for what it is, with the measured identities
attached — not as a de novo entry it cannot be.

`scripts/export_denovo.py` measures this with global Needleman-Wunsch identity over VH, VL and
the concatenated pair, against both the framework donor and trastuzumab, with the worst case
driving the verdict since we do not know which abguard uses. Validated on known pairs:
self-identity 1.0, VH against VL 0.289, and a VH with CDRH3 replaced by ten alanines 0.925,
which is 111/120 exactly.

## Portfolio note

All four current picks come from `optB` and are CDRH3-only redesigns, so they share one
generator's failure mode — if that loop family is wrong, all four die together, which is the
thing the plan explicitly warns against. `multicdr` and `denovo` exist to give the portfolio
step genuinely uncorrelated options:

- `multicdr` changes CDRH1 and CDRH2 as well as CDRH3, in all 100 designs, so it moves contacts
  trastuzumab makes through the other two loops. Honest caveat: the affinity cliff was measured
  on CDRH3 variants, so it does not extrapolate here — these sit outside the domain of that
  measurement. That is a real unknown and also precisely why the failure mode is uncorrelated.
- `denovo` keeps a different framework entirely.

The choice between them belongs to the portfolio step, not to generation.

## Two things still unresolved

- **`abguard` was never installed on the VM.** Every novelty and identity number here is
  computed against our reading of the rules, not against the authority. The reading is
  conservative where it is ambiguous.
- **The identity threshold is ambiguous.** `docs/brief.md` says "<70% CDRH3 identity", under
  which 7/10 matches fails and 4 of 10 positions must differ. The Apheris tutorial says "at most
  70% ... at least 3 of 10 changed", under which 3 suffice. We require 4, which satisfies both
  readings and costs about 8 designs of yield. Designs with exactly 3 substitutions are recorded
  with their count so the decision can be revisited if the stricter reading turns out to be
  wrong.

## Reading a design record

```json
{
  "design_id": "optB-her2_cdrh3_82",
  "cdrh3": "WGTGYFYYYD",
  "generator": "rfd4-proteina:her2-2026-11-07",
  "novelty": {
    "mutations_from_parent": 5,
    "min_substitutions_from_any_provided": 2,
    "passes_challenge_filter": true
  },
  "design_metrics": {"hotspot_obedience": 1, "clash_fraction": 0.0015,
                     "interface_hbond_pairs": 19},
  "refold": {"model": "boltz2", "iptm": 0.9, "min_ipae": 0.37, "binder_plddt": 96.8}
}
```

`min_substitutions_from_any_provided` is capped at 2, because the filter only asks whether a
design differs at 2 or more positions and the exact distance beyond that is not needed.

Sequences are parsed from the generated CIFs and verified byte for byte against the tool's own
`binder_sequence` output, so the records are not a reinterpretation of the structures.
