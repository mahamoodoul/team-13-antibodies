# Blind rehearsal — SEALED UNTIL 16:00

Two targets neither Ansarul nor Mahamodul has seen. Picked by Rizve at 13:03 on
14 November, at Ansarul's request, so the "runs on a target it has not seen"
claim is tested by someone who did not choose the target.

**Do not open `targets.sealed.b64` before 16:00.** The whole value of the
exercise is that the person running it has not seen the input. It is base64 and
not encryption — it is sealed against a glance and a `git diff`, not against
you. Honour system.

## Opening it at 16:00

```bash
python3 -I -c "import base64,json,sys;print(json.dumps(json.loads(base64.b64decode(open(sys.argv[1]).read())),indent=2))" \
  examples/blind-rehearsal/targets.sealed.b64
```

Each entry carries the UniProt accession, the full FASTA, the sequence length,
and the exact command to run. Both sequences were fetched from the UniProt REST
API on 14 November, so they are the real entries and not reconstructions.

## What the rehearsal is for

Not "does it crash". It does not crash — that was checked before sealing, on
both targets, via both the FASTA path and the bare-accession path. The question
is whether the four designs it returns mean anything on a target the generator
was not built for.

## Known failure mode, deliberately not sealed

Rizve verified the run before sealing and hit this, so it is written down here
rather than discovered on stage. Re-verified on `main` after Ruhit's strict
distance gate landed (`506bdef`), on both targets, unchanged:

**On an unseen target the pipeline completes but falls back to the STUB
generator, and the four picks are identical on both of these targets — same
ids, same joint scores to three decimals.** The gate and portfolio layers are
target-agnostic and work correctly; `generate` is HER2-specific, so there is
nothing target-derived in the candidates, and the axes are therefore scoring
stubs rather than designs. The run reports this itself (`N/25 records came from
the STUB generator — these are not designs`), which is the honest behaviour, but
it means the blind run currently demonstrates *portability of the ranking
engine*, not portability of the whole pipeline.

That distinction is the answer to give a judge who runs it, and it is defensible
— the ranking engine is the part we built and the part that is 40% of the score.
Claiming more than that would not survive the five minutes it takes to check.

The targets stay sealed anyway: the input being cold is what makes the timing
and the operator experience a real test.
