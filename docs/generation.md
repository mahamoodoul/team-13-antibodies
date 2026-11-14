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
| `denovo` | `antibody-2026-10-30` | 100 | — | **0**, see §5 and §6 | — | — |

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

## Seven things we measured that changed what we did

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

### 6. The construct-length failure is the de novo batch, and no linker saves it

Flagged at 12:45 as "the entire `multicdr` batch is failing the length gate, all 100,
257–259 aa against the 250 limit", with the diversity hypothesis declared gone and the fix
handed to generation. The measurement is real and the arithmetic is right. It is the wrong
batch.

Run the gate over all 401 records and the failures sort cleanly:

| batch | failing | why |
| --- | --- | --- |
| `denovo` | **100 / 100** | `length 257-259 (construct) > 250` |
| `multicdr` | **1 / 100** | one design 1 substitution from a provided sequence |
| `optA` | 16 / 100 | novelty and identity ceiling |
| `optB` | 32 / 100 | novelty, identity ceiling, one unpaired cysteine |

`multicdr` is the *highest-yielding* batch we have, 99 of 100 through every gate. The
diversity hypothesis was never lost, and it needs no regeneration — it is available to the
portfolio step now.

The cause was also the reverse of the diagnosis. Redesigning three heavy CDRs did not grow
the VH: `multicdr` is VH 120 + VL 107 = 227, **shorter** than `optA` and `optB`, because the
loops were rebuilt at the parent's lengths. What grew is `denovo`, VH 129–131 + VL 113 =
242–244, and it grew for a reason recorded in §5 — we designed all six CDRs *at maximum
length* specifically to try to close the de novo identity gap.

That choice now has two measured costs and no benefit. It did not close the gap (identity
0.779–0.823 against a 0.70 ceiling) and it pushed the ordered construct over 250.

**The proposed fix cannot work, and the reason is worth knowing.** Dropping the linker from
(G4S)3 to (G4S)2 buys exactly 5 residues, which is not enough:

| linker | aa | construct | over 250 |
| --- | --- | --- | --- |
| `(G4S)3` | 15 | 257–259 | **100 / 100** |
| `(G4S)2` | 10 | 252–254 | **100 / 100** |
| `(G4S)1` | 5 | 247–249 | 0 / 100 |
| direct | 0 | 242–244 | 0 / 100 |

Only a 5-residue linker or direct ligation fits — and at those lengths the molecule is no
longer an scFv. The linker length that permits intramolecular VH–VL pairing is a measured
constant, not a free parameter:

- An scFv with a linker of **3–12 residues cannot fold into a functional Fv domain** and
  instead pairs with a second copy to form a bivalent diabody; below 3 it forms triabodies
  and tetramers ([Atwell 1999, PMID 10436086](https://pubmed.ncbi.nlm.nih.gov/10436086/);
  [review, PMID 12856620](https://pubmed.ncbi.nlm.nih.gov/12856620/)).
- Measured directly across a linker series: fragments with linkers **longer than 11 residues
  remained monomeric**, while 11, 6 and 2 formed multimers
  ([Alfthan 1995, PMID 8577701](https://pubmed.ncbi.nlm.nih.gov/8577701/)).
- On our own target: an **anti-ErbB2 (HER2) scFv was converted to a diabody precisely by
  shortening its linker from 15 to 5 aa** — "the shorter linker prevents intramolecular
  pairing of VH and VL" — and the resulting bivalent molecule showed dissociation rate
  constants up to **15-fold slower** than its parent scFv
  ([Nielsen 2000, PMID 11103810](https://pubmed.ncbi.nlm.nih.gov/11103810/)).

So (G4S)2 at 10 aa sits inside the diabody window and still does not fit; (G4S)1 at 5 aa fits
and is the canonical way to *build* a HER2 diabody. Either way it is a format change, not a
length trim — and the second one would hand Adaptyv a bivalent molecule in an SPR assay,
where that 15-fold slower off-rate is avidity from the format rather than affinity from the
design. We would be improving our own measured number by changing the molecule's valency.
That is the opposite of what we are trying to show.

`denovo` therefore stays what §5 already called it: a fourth hypothesis on a different
framework, labelled for what it is. It was unsubmittable as a de novo entry on identity, and
under the strict reading of the length rule it is unsubmittable as an optimisation entry too.

**One caveat, because the length rule is ambiguous exactly like the novelty rule.** The 250 aa
limit is stated as combined VH + VL. On that reading `denovo` passes at 242–244 and only the
linker pushes it over; the gate measures the whole construct, which is the strict reading, and
`_scfv_construct` records both numbers for every design. Our three optimisation batches clear
*both* readings — 227 on VH + VL, 242 on the construct, 8 aa of margin on the stricter one —
so nothing we would actually submit depends on which reading is right. Only `denovo` does, and
`denovo` is already out on identity.

### 7. Run the baseline through the epitope axis and it scores 0.134

§3's rule was "carry the trastuzumab baseline through every batch, because without it no score
means anything." We had been applying it to folding confidence. Applied to the epitope axis it
finds a 3.7x error, and the only reason it was invisible is that the parent had never been
measured on this axis at all — `baseline.json` carried refold confidence and no contacts.

Measured now, the same way as every design, against the annotated 1N8Z/8PWH epitope:

| | contacts | in epitope | precision | recall | regions touched |
| --- | --- | --- | --- | --- | --- |
| Boltz-2 | 19 | 14 | 0.74 | **0.70** | 557–561 ✓ · 570–573 ✓ · 593–603 ✓ |
| Protenix v2 | 15 | 7 | 0.47 | **0.35** | 557–561 ✗ · 570–573 ✗ · 593–603 ✓ |

**Protenix places trastuzumab off its own epitope**, missing two of the three crystallographic
contact regions outright. And `export_batch.py` was handing the axis Protenix's contacts — on
the §3 reasoning that Protenix is the model whose confidence we trust. That is true and it does
not transfer: where a model puts two molecules and how well its ipTM separates binders are
different questions. The spread Protenix gave across designs was its own placement error, so
ranking on it ranked designs by how far Protenix had drifted. The preference is now
`boltz2 → of3ob → protenix-v2`, with this measurement as the stated reason.

`scripts/epitope_control.py` reruns the whole control from committed data — no VM, no GPU.

**Then the axis itself.** Scored from the model that passes the control, the structural path
gives the parent **0.134**, against the 0.500 it gets on the prior path. The reference molecule
fails its own axis. Two compounding causes, both of which punish a design for having been
measured:

1. **Ten of the thirty "annotated" residues cannot be contacted by any fold we run.**
   `targets.py` takes all four `contact_regions`, including 581–590 — which is 8PWH-only,
   lower-confidence, and *absent from the folded input*: the yaml splits HER2 into chains
   C 489–580 and D 591–607 precisely because input validation rejects a numbering gap inside
   one chain. So overlap is capped at 20/30 = 0.667 for every design and for trastuzumab.
2. **The reference is overlap 1.0** — a molecule contacting all 30 residues, which does not
   exist. `score = logistic(3.5 x (overlap - 1.0))`.

| a design preserving the epitope exactly as well as the parent | scores |
| --- | --- |
| today — overlap /30, reference 1.0 | **0.134** |
| drop the unreachable 581–590 — overlap /20, reference 1.0 | 0.259 |
| and reference the parent's own measured overlap | **0.500** |

0.500 is the right answer and it is the same number the parent gets on the prior path, which is
what makes the two bases comparable. Today they are not: across the full pool the structural
basis spans 0.029–0.148 while the prior basis spans 0.071–0.500, so **the structural ceiling
sits below the prior mean.** Folding a design can only lower its rank. That is the real reason
no fold set of mine ever reached the top four — I fixed *which* designs we folded at 12:43 and
the fold budget still landed outside the shortlist, because the problem was never the
selection. It was that measured evidence is scored on a scale that cannot compete with
inferred evidence.

The fix belongs in `score.py`, which is Rizve's. What generation owes it is the calibration
point, and that is now committed: the parent's measured contacts, in both models, in
`baseline.json` and `baseline-protenix-v2.json`.

**And the axis does discriminate, once it is referenced properly.** It separates exactly where
it should — by what the generator redesigned:

| batch | n | median recall | sd | off-epitope |
| --- | --- | --- | --- | --- |
| `optA` CDRH3-only | 43 | 0.70 | 0.042 | 0 / 43 |
| `optB` CDRH3-only | 31 | 0.70 | 0.022 | 0 / 31 |
| `multicdr` three heavy CDRs | 16 | **0.45** | 0.150 | **3 / 16** |

CDRH3-only designs sit at the parent's own value with almost no spread: epitope preservation
really is close to free when one loop moves, which the plan argued from first principles and
this measures. Move CDRH1 and CDRH2 as well and it stops being free — `multicdr_20` contacts
the epitope not at all, with 5 contacts total.

So the axis is not a tie-break among trastuzumab variants. It is the check that catches a
design binding somewhere else, and it fires only where it should. With the parent as the
reference, `multicdr_20` scores 0.029 and an optB design scores 0.500 — which is the axis
working, not the axis being noisy.

**This is the price of the diversity slot, as a number.** §6 left `multicdr` as the only
uncorrelated hypothesis we have. It pays for that here: 3 of its 16 refolded designs do not
compete with trastuzumab for its epitope and can never be S-tier. The portfolio step should
take that trade knowingly — and it should pick from the 13 that do compete, which is a thing
it can only do if the axis is referenced to the parent rather than to a molecule that
contacts every residue.

## Portfolio note

All four current picks come from `optB` and are CDRH3-only redesigns, so they share one
generator's failure mode — if that loop family is wrong, all four die together, which is the
thing the plan explicitly warns against. `multicdr` and `denovo` exist to give the portfolio
step genuinely uncorrelated options:

- `multicdr` changes CDRH1 and CDRH2 as well as CDRH3, in all 100 designs, so it moves contacts
  trastuzumab makes through the other two loops. Honest caveat: the affinity cliff was measured
  on CDRH3 variants, so it does not extrapolate here — these sit outside the domain of that
  measurement. That is a real unknown and also precisely why the failure mode is uncorrelated.
- `denovo` keeps a different framework entirely — but it is **out**, on identity (§5) and
  again on construct length (§6). It is not an option the portfolio step can spend a slot on.

So after §6 there is exactly one uncorrelated hypothesis left, and it is `multicdr`: 99 of 100
through every gate, three heavy CDRs moved rather than one, 227 aa on VH + VL. If the four
picks are to stop being four variants of one loop family, that is the batch they have to come
from. The choice still belongs to the portfolio step, not to generation — but generation is no
longer supplying two alternatives, it is supplying one.

## Two things still unresolved

- **`abguard` was never installed on the VM.** Every novelty and identity number here is
  computed against our reading of the rules, not against the authority. The reading is
  conservative where it is ambiguous.
- **The epitope axis is mis-referenced, and the fix is in `score.py`.** §7 measures it: the
  parent scores 0.134 on the structural path against 0.500 on the prior path, so folding a
  design lowers its rank. The calibration point is committed; the two-line change is Rizve's.
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
