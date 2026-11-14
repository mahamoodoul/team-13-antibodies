"""Run the organisers' abguard over the pool and record a verdict per design.

    python3 -I scripts/abguard_verdicts.py --abguard /path/to/abguard

abguard exists only on the team VM, so this is run there. It writes
data/reference/abguard_verdicts.json, which the gate stage reads on any machine.
Commit that file: it is the evidence that the ranked designs went through abguard.

WHAT IT DOES. It builds the submission table abguard expects (sequence_id, kind,
heavy_sequence, light_sequence, design_description) from every design that clears
our own gates. An scFv is one polypeptide, so it goes in heavy_sequence with
light_sequence empty. It runs `abguard team-validate --drop` and takes the
verdict from what survives: a design is `pass` only if abguard wrote it back out.

A verdict is bound to the sha256 of the exact sequence abguard saw. The gate
refuses to apply it to a design whose sequence has changed, so an old pass can
never vouch for a different molecule.

The reason for a rejection is read from abguard's own log. Where the log gives
none, the record says so rather than inventing one.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fourwells.cache import Cache  # noqa: E402
from fourwells.report import construct_of  # noqa: E402
from fourwells.runner import run_pipeline  # noqa: E402
from fourwells.targets import resolve_reference_ab, resolve_target  # noqa: E402

OUT = ROOT / "data" / "reference" / "abguard_verdicts.json"
COLUMNS = ["sequence_id", "kind", "heavy_sequence", "light_sequence", "design_description"]
NOVELTY_LINE = re.compile(r"\[novelty\]\s+(?P<id>\S+?):\s+(?P<why>.+)$")


def sha(seq: str) -> str:
    return hashlib.sha256(seq.encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--abguard", required=True, help="path to the abguard executable")
    ap.add_argument("--candidates", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    result = run_pipeline(
        target=resolve_target(None),
        ref=resolve_reference_ab(None),
        budget=4,
        n_candidates=args.candidates,
        seed=args.seed,
        cache=Cache(offline=True),
    )
    pool = [r for r in result.records if r.gates.passed and not r.is_baseline]
    seqs = {r.design_id: construct_of(r)[0] for r in pool}

    with tempfile.TemporaryDirectory() as tmp:
        table, passed_csv, log = Path(tmp, "pool.csv"), Path(tmp, "pass.csv"), Path(tmp, "log.txt")
        with open(table, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            for r in pool:
                w.writerow([r.design_id, "scfv", seqs[r.design_id], "", f"{r.track} {r.cdrh3}"])

        proc = subprocess.run(
            [args.abguard, "team-validate", str(table), "--drop", "-o", str(passed_csv)],
            capture_output=True,
            text=True,
        )
        log.write_text(proc.stdout + proc.stderr)
        if not passed_csv.exists():
            print("abguard wrote no output; refusing to record verdicts", file=sys.stderr)
            print(proc.stdout + proc.stderr, file=sys.stderr)
            return 1
        with open(passed_csv, newline="") as fh:
            survivors = {row["sequence_id"] for row in csv.DictReader(fh)}
        reasons = {}
        for line in (proc.stdout + proc.stderr).splitlines():
            m = NOVELTY_LINE.search(line)
            if m:
                reasons[m["id"]] = "novelty: " + m["why"].strip()

    # Versions come from the environment abguard actually ran in, so the record
    # says what produced it rather than what we expected.
    py = Path(args.abguard).parent / "python"
    ver = subprocess.run(
        [str(py), "-c",
         "import importlib.metadata as m; print(m.version('abguard'), m.version('immunum'))"],
        capture_output=True, text=True,
    )
    abguard_v, immunum_v = (ver.stdout.split() + ["unknown", "unknown"])[:2]

    verdicts = {}
    for r in pool:
        ok = r.design_id in survivors
        verdicts[r.design_id] = {
            "sha256": sha(seqs[r.design_id]),
            "status": "pass" if ok else "fail",
            "reason": None
            if ok
            else reasons.get(r.design_id, "dropped by abguard; no reason in its log"),
        }

    blob = {
        "tool": f"abguard {abguard_v} / immunum {immunum_v}, team-validate --drop, bundled reference",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "table": {"kind": "scfv", "n_rows": len(pool), "n_pass": len(survivors)},
        "note": "A verdict applies only to a design whose construct sha256 matches.",
        "verdicts": verdicts,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(blob, indent=1, sort_keys=True) + "\n")
    print(f"{len(survivors)}/{len(pool)} pass abguard; wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
