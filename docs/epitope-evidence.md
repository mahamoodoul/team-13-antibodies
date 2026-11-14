# Epitope evidence — where trastuzumab actually touches HER2

OWNER: Mahamoodoul. plan.md:341 — one contact list, shared by Rizve's epitope predictor
and Ruhit's hotspot conditioning, so the two stages cannot drift apart.

This file is the citation layer for `her2.contact_regions` in
[data/reference/trastuzumab.json](../data/reference/trastuzumab.json). The numbers live
there because the code reads them; the reasons live here because the pitch needs them.

## The claim, and what supports it

**Trastuzumab binds domain IV of the HER2 extracellular region, at the juxtamembrane
end.** According to PubMed, this is established by the original co-crystal structure of
the HER2 extracellular region with the trastuzumab (Herceptin) Fab at 2.5 Å, which
states plainly that "Herceptin binds to the juxtamembrane region of HER2, identifying
this site as a target for anticancer therapies" — Cho et al., *Nature* 2003,
[DOI](https://doi.org/10.1038/nature01392) (PMID 12610629). That structure is PDB
**1N8Z**, the first of the two our contact regions are derived from.

Two further results matter for *why we score an epitope axis at all*, rather than
treating any HER2 binder as equivalent:

- Binders to HER2 subdomain I and subdomain IV are functionally different, not
  interchangeable: bispecific DARPins spanning subdomain I and subdomain IV produce a
  much stronger cytotoxic effect on BT474 than trastuzumab does, by preventing
  signaling-competent dimerisation — Jost et al., *Structure* 2013,
  [DOI](https://doi.org/10.1016/j.str.2013.08.020) (PMID 24095059).
- A high-affinity HER2 binder can sit on a conformational epitope *distant* from the
  trastuzumab and pertuzumab sites and still bind at K_D = 22 pM — Eigenbrot et al.,
  *PNAS* 2010, [DOI](https://doi.org/10.1073/pnas.1005025107) (PMID 20696930).

That second one is the load-bearing citation for our whole epitope axis. **Affinity does
not imply epitope.** A design can bind HER2 beautifully and bind it somewhere
trastuzumab never touched, which scores zero on the lab's competitive-binding assay. It
is the published reason the axis exists and the reason a de novo design with no evidence
of domain IV contact is capped rather than guessed — see
[score.py:335-380](../fourwells/stages/score.py#L335-L380).

For the broader structural picture across ErbB-targeting antibodies, Schmitz & Ferguson,
*Exp Cell Res* 2009, [DOI](https://doi.org/10.1016/j.yexcr.2008.10.008) (PMID 18992239)
reviews five Fab–ErbB co-crystal structures and their distinct inhibition mechanisms.

## What the literature supports, and what it does not

Stated precisely, because the pitch should not overclaim and a judge may well know this
literature better than we do:

| Claim | Status |
| --- | --- |
| Trastuzumab's epitope is domain IV, juxtamembrane | **Published**, Cho 2003 |
| Epitope identity, not just affinity, changes function | **Published**, Jost 2013 / Eigenbrot 2010 |
| The specific residue ranges 557-561, 570-573, 593-603 | **Our own contact analysis** of 1N8Z, cross-checked against 8PWH |
| The 581-590 loop | **8PWH only** — not resolved in the earlier structure |

The residue-level ranges are *ours*, computed from the cited structures. The papers
establish the domain and the principle; they do not hand us a contact list. Saying so is
cheaper than being caught rounding it up.

## How this list is consumed

One list, three consumers, no second copy:

- `resolve_target` loads it into `Target.epitope_residues`
  ([targets.py](../fourwells/targets.py))
- the epitope axis scores paratope conservation and domain IV overlap against it
  ([score.py:369](../fourwells/stages/score.py#L369))
- generation conditions de novo designs on it

A target with no annotated epitope — every blind-rehearsal target, see
[blind-rehearsal.md](blind-rehearsal.md) — resolves with `epitope_residues: []` and the
axis declines to score rather than inventing one.

## On AMASS

plan.md:341 assigns this task to AMASS, which is paid for ($100, expires 14 Dec 2026)
and carries its own prize for best use. The work above was done with PubMed instead,
because the AMASS key could not be reached from the environment this was written in —
`TEAM-13-SETUP.md:77` says it lives in `amass.env`, and that file is not present in the
repo. **Outstanding:** create `amass.env` from the key in the team vault, re-run this
search through AMASS so the provenance is theirs, and post the team intro in
`#amass-scientific-intelligence`. A draft of that post is in
[amass-intro-draft.md](amass-intro-draft.md).
