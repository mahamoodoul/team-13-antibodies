"""Durable, browser-independent scientific experiments and audited tool adapters.

    python3 -m fourwells.experiments inventory
    python3 -m fourwells.experiments start --mode demo --question 'Test the workflow'
    python3 -m fourwells.experiments start --mode import --input candidates.jsonl --question 'Pilot'

Real model execution requires a local, documented adapter profile, not guessed
Foundry CLI flags. See docs/model-usage.md for the file protocol.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .evidence import RANKING_VERSION, objective, rank_candidates, sequence_diversity
from .schema import AXES, DesignRecord
from .stages import gates, generate
from .targets import ReferenceAntibody, resolve_target

ROOT = Path(__file__).resolve().parents[1]
STATES = {"queued", "running", "complete", "failed", "blocked", "interrupted"}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.replace(p)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.base = self.root / "artifacts" / "antibodylab"
        self.base.mkdir(parents=True, exist_ok=True)
        self.db = self.base / "metadata.sqlite3"
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS iterations (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, updated TEXT NOT NULL,
                status TEXT NOT NULL, spec TEXT NOT NULL, error TEXT, pid INTEGER)""")

    def connect(self):
        db = sqlite3.connect(self.db, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def directory(self, ident):
        # Do not expose arbitrary paths through API identifiers.
        if not isinstance(ident, str) or len(ident) > 64 or not ident or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in ident):
            raise ValueError("Invalid iteration ID")
        return self.base / ident

    def create(self, spec):
        spec = validate_spec(spec)
        if spec.get("parent") and not self.get(spec["parent"]):
            raise ValueError("Parent iteration does not exist")
        ident = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        folder = self.directory(ident)
        folder.mkdir(exist_ok=False)
        (folder / "logs").mkdir()
        write_json(folder / "spec.json", spec)
        stamp = now()
        with self.connect() as db:
            db.execute("INSERT INTO iterations VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (ident, stamp, stamp, "queued", json.dumps(spec), None, None))
        return ident

    def update(self, ident, status, error=None, pid=None):
        if status not in STATES:
            raise ValueError("Invalid job status")
        with self.connect() as db:
            db.execute("UPDATE iterations SET status=?, updated=?, error=?, pid=COALESCE(?,pid) WHERE id=?",
                       (status, now(), error, pid, ident))

    def get(self, ident):
        self.directory(ident)
        with self.connect() as db:
            row = db.execute("SELECT * FROM iterations WHERE id=?", (ident,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["spec"] = json.loads(d["spec"])
        if d["status"] in ("queued", "running") and d["pid"]:
            try:
                os.kill(d["pid"], 0)
            except ProcessLookupError:
                # A final worker commit may race this read; never replace a
                # completed result with a stale interruption observation.
                message = "Worker exited before recording completion; start a new iteration"
                with self.connect() as db:
                    changed = db.execute("UPDATE iterations SET status='interrupted',updated=?,error=? "
                                         "WHERE id=? AND status IN ('queued','running') AND pid=?",
                                         (now(), message, ident, d["pid"])).rowcount
                if not changed:
                    return self.get(ident)
                d.update(status="interrupted", error=message)
            except PermissionError:
                pass
        result = self.directory(ident) / "evidence.json"
        if result.exists():
            d["result"] = json.loads(result.read_text())
        partial = self.directory(ident) / "partial-evidence.json"
        if not result.exists() and partial.exists():
            d["partial_result"] = json.loads(partial.read_text())
        d["events"] = []
        event_file = self.directory(ident) / "events.jsonl"
        if event_file.exists():
            for line in event_file.read_text().splitlines():
                try:
                    d["events"].append(json.loads(line))
                except ValueError:
                    continue
        return d

    def list(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM iterations ORDER BY created DESC")]
        return [self.get(i) for i in ids]

    def event(self, ident, stage, status, **kwargs):
        with (self.directory(ident) / "events.jsonl").open("a") as f:
            f.write(json.dumps({"at": now(), "stage": stage, "status": status, **kwargs}) + "\n")


def validate_spec(spec):
    if not isinstance(spec, dict):
        raise ValueError("Experiment must be an object")
    d = {k: spec[k] for k in ("mode", "question", "seed", "candidates", "cap", "parent", "input", "profile") if k in spec}
    d.setdefault("mode", "demo")
    if d["mode"] not in ("demo", "import", "live"):
        raise ValueError("mode must be demo, import or live")
    if not isinstance(d.get("question"), str) or not d["question"].strip() or len(d["question"]) > 2000:
        raise ValueError("Document an iteration question (1–2000 characters)")
    for k, default, low, high in (("seed", 0, 0, 2147483647), ("candidates", 24, 1, 1000), ("cap", 20, 1, 20)):
        v = d.get(k, default)
        if type(v) is not int or not low <= v <= high:
            raise ValueError(f"{k} must be an integer between {low} and {high}")
        d[k] = v
    if d["mode"] == "import" and not isinstance(d.get("input"), str):
        raise ValueError("Import requires a JSONL input path")
    if d["mode"] == "live" and not isinstance(d.get("profile"), str):
        raise ValueError("Live execution requires a documented adapter profile")
    return d


def start(root, spec):
    """Detach the worker from both the HTTP request and server process."""
    store = Store(root)
    ident = store.create(spec)
    with (store.directory(ident) / "logs" / "worker.log").open("ab") as log:
        try:
            proc = subprocess.Popen([sys.executable, "-m", "fourwells.experiments", "--root", str(store.root),
                                     "worker", ident], cwd=ROOT, stdout=log, stderr=log,
                                    start_new_session=True)
            with store.connect() as db:
                db.execute("UPDATE iterations SET pid=? WHERE id=? AND status='queued'", (proc.pid, ident))
            # Reap children while this process lives; the worker remains
            # independent if the web server exits.
            threading.Thread(target=proc.wait, daemon=True).start()
        except OSError as exc:
            store.update(ident, "failed", str(exc))
            raise
    return store.get(ident)


class Unavailable(RuntimeError):
    pass


def adapter(profile, stage, folder, values, store, ident, allow_failure=False):
    step = profile.get("stages", {}).get(stage)
    if not isinstance(step, dict) or not step.get("argv") or not step.get("version"):
        raise Unavailable(f"No documented {stage} adapter/version configured")
    if not isinstance(step["argv"], list) or not all(isinstance(x, str) for x in step["argv"]):
        raise ValueError("Adapter argv must be a list of strings; shell commands are not accepted")
    argv = [x.format_map(values) for x in step["argv"]]
    name = stage + ("-" + values["design_id"] if "design_id" in values else "")
    logs = folder / "logs"
    write_json(logs / (name + ".command.json"), {"argv": argv, "version": step["version"], "started": now()})
    store.event(ident, stage, "running", candidate=values.get("design_id"))
    began = time.monotonic()
    with (logs / (name + ".stdout")).open("wb") as out, (logs / (name + ".stderr")).open("wb") as err:
        proc = subprocess.run(argv, cwd=store.root, stdout=out, stderr=err,
                              timeout=min(int(step.get("timeout", 3600)), 86400), check=False)
    store.event(ident, stage, "complete" if proc.returncode == 0 else "failed",
                returncode=proc.returncode, seconds=round(time.monotonic() - began, 3))
    if proc.returncode and not allow_failure:
        raise RuntimeError(f"{stage} exited {proc.returncode}; inspect {name}.stderr")
    return {"command": argv, "version": step["version"], "stdout": f"logs/{name}.stdout",
            "stderr": f"logs/{name}.stderr", "returncode": proc.returncode}


def copy_artifact(root, folder, path, name):
    source = Path(path)
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    # The protocol accepts scientific structures, never arbitrary private files.
    source.relative_to(root.resolve())
    if source.suffix.lower() != ".pdb" or not source.is_file() or source.stat().st_size > 30_000_000:
        raise ValueError("Structure must be a project-local PDB file below 30 MB")
    target = folder / "structures" / name
    target.parent.mkdir(exist_ok=True)
    shutil.copy2(source, target)
    return str(target.relative_to(folder))


def evaluate_row(row, ref, folder, root, profile, store, ident, demo=False):
    design_id = row.get("design_id")
    if not isinstance(design_id, str) or not design_id or len(design_id) > 64 or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in design_id):
        raise ValueError("Candidate IDs must contain 1–64 letters, numbers, hyphens or underscores")
    if design_id == "trastuzumab":
        raise ValueError("The reference is not a candidate")
    seq = row.get("sequence") or row.get("vh") or ""
    if row.get("vl") and not row.get("sequence"):
        raise ValueError("Supply the final construct in sequence; do not infer a linker from VH/VL")
    if not isinstance(seq, str):
        raise ValueError("Candidate sequence must be text")
    seq = "".join(seq.split()).upper()
    cdrh3 = row.get("cdrh3")
    if cdrh3 is not None:
        if not isinstance(cdrh3, str):
            raise ValueError("CDRH3 must be a sequence string")
        cdrh3 = "".join(cdrh3.split()).upper()
        if cdrh3 and cdrh3 not in seq:
            raise ValueError(f"{design_id}: supplied CDRH3 is absent from the construct")
    rec = DesignRecord(design_id, seq, track=row.get("track"), format=row.get("format"),
                       cdrh3=cdrh3, generator=row.get("generator"))
    gates.check(rec, ref, use_abguard=False)
    validation = {"status": "not_run", "track": None, "failed_rules": [],
                  "local_screen": rec.gates.checks, "local_failures": rec.gates.failed_rules}
    # Local track checks are diagnostics. Only abguard may assign a track.
    if profile and not demo:
        cp = folder / (design_id + ".input.json")
        vp = folder / (design_id + ".validation.json")
        write_json(cp, {"design_id": design_id, "sequence": rec.sequence, "format": rec.format,
                        "requested_track": rec.track})
        provenance = adapter(profile, "validation", folder,
                             {"workspace": str(folder), "input": str(cp), "output": str(vp),
                              "design_id": design_id}, store, ident, allow_failure=True)
        raw = json.loads(vp.read_text()) if vp.exists() else {
            "passed": False, "failed_rules": ["Validator produced no structured verdict; inspect raw logs"]}
        passed = raw.get("passed") is True and provenance["returncode"] == 0
        assigned = raw.get("track")
        confidence = raw.get("numbering_confidence")
        valid = assigned in ("optimisation", "de_novo") and type(confidence) in (int, float) and math.isfinite(confidence) and 0.1 <= confidence <= 1
        # No failed design is rescued by assigning a different branch.
        branch_ok = row.get("track") in (None, assigned)
        validation.update(status="pass" if passed and valid and branch_ok else "fail",
                          track=assigned, raw=raw, provenance=provenance,
                          failed_rules=list(raw.get("failed_rules") or []))
        if not valid:
            validation["failed_rules"].append("Official track or numbering confidence missing/invalid")
        if provenance["returncode"]:
            validation["failed_rules"].append(f"Validator exited {provenance['returncode']}; inspect raw logs")
        if not branch_ok:
            validation["failed_rules"].append("Assigned track differs from design branch; candidate rejected")
        # Format, alphabet, length, cysteine failures still cannot be rescued.
        cheap_failed = []
        gates.cheap_checks(rec, cheap_failed, {})
        validation["failed_rules"].extend(cheap_failed)
        if validation["failed_rules"]:
            validation["status"] = "fail"
    if demo:
        validation["status"] = "demo_only"
    ev = row.get("evidence") or row.get("axis_evidence", {}).get("objectives", {})
    objectives = {a: objective(ev.get(a), a) for a in AXES}
    structures = []
    for i, s in enumerate(row.get("structures", [])):
        path = copy_artifact(root, folder, s["path"], f"{design_id}-{i}.pdb")
        structures.append({**s, "path": path, "sha256": sha256(folder / path)})
    return {"design_id": design_id, "sequence": rec.sequence, "format": rec.format,
            "track": validation["track"], "requested_track": row.get("track"),
            "generator": row.get("generator"), "generation": row.get("generation", {}),
            "cdrh3": rec.cdrh3, "stub": demo or bool(row.get("is_stub")),
            "eligible": validation["status"] == "pass" and not demo and not row.get("is_stub", False),
            "validation": validation, "objectives": objectives, "structures": structures,
            "predictions": row.get("predictions", [row["refold"]] if row.get("refold") else []),
            "developability": row.get("developability", rec.gates.checks.get("developability")),
            "limitations": row.get("limitations", []), "model_disagreement": row.get("model_disagreement", [])}


def work(root, ident):
    store = Store(root)
    job = store.get(ident)
    if not job or job["status"] != "queued":
        raise ValueError("Only a queued iteration may run; create a new iteration for retries")
    # Atomically claim: two workers must never run the same model job.
    with store.connect() as db:
        claimed = db.execute("UPDATE iterations SET status='running',pid=?,updated=? WHERE id=? AND status='queued'",
                             (os.getpid(), now(), ident)).rowcount
    if not claimed:
        raise ValueError("Iteration already claimed")
    spec, folder = job["spec"], store.directory(ident)
    try:
        store.event(ident, "inputs", "running")
        refpath = ROOT / "data/reference/trastuzumab.json"
        shutil.copy2(refpath, folder / "reference.json")
        reference = json.loads((folder / "reference.json").read_text())
        ref = ReferenceAntibody(name="trastuzumab", vh=reference.get("vh", {}).get("sequence"),
                               vl=reference.get("vl", {}).get("sequence"),
                               cdrh3=reference.get("cdrs_kabat", {}).get("cdr_h3"), meta=reference)
        from .runner import git_sha
        write_json(folder / "provenance.json", {"started": now(), "git_sha": git_sha(),
                   "python": sys.version, "ranking_version": RANKING_VERSION,
                   "reference_sha256": sha256(folder / "reference.json"),
                   "target": "HER2 P04626", "reference": ref.name,
                   "resources": resource_status(store.root),
                   "baseline_measurements": ref.meta.get("baseline_measurements", {})})
        profile = None
        if spec.get("profile"):
            pp = Path(spec["profile"])
            if not pp.is_absolute():
                pp = store.root / pp
            profile = json.loads(pp.read_text())
            documentation = Path(profile.get("documentation", ""))
            if not documentation.is_absolute():
                documentation = store.root / documentation
            if not documentation.is_file() or profile.get("verified_against_installed_docs") is not True:
                raise Unavailable("Adapter requires existing documentation and verified_against_installed_docs=true")
            shutil.copy2(pp, folder / "profile.json")
            shutil.copy2(documentation, folder / "adapter-documentation.txt")
        if spec["mode"] == "demo":
            records = generate.run(resolve_target(None), ref, n=spec["candidates"], seed=spec["seed"])
            rows = [r.to_dict() for r in records if not r.is_baseline]
            write_json(folder / "demo-input.json", rows)
        else:
            source = folder / "candidates.jsonl"
            if spec["mode"] == "import":
                src = Path(spec["input"])
                if not src.is_absolute():
                    src = store.root / src
                if src.stat().st_size > 20_000_000:
                    raise ValueError("Pilot import limit is 20 MB")
                shutil.copy2(src, source)
            else:
                adapter(profile, "design", folder,
                        {"workspace": str(folder), "output": str(source), "seed": str(spec["seed"]),
                         "candidates": str(spec["candidates"])}, store, ident)
            rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        if not rows or len(rows) > 1000:
            raise ValueError("An iteration must contain 1–1000 candidates")
        if any(not isinstance(r, dict) for r in rows):
            raise ValueError("Each candidate record must be a JSON object")
        ids = [r.get("design_id") for r in rows]
        if any(not isinstance(i, str) for i in ids):
            raise ValueError("Every candidate needs a string design_id")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate candidate IDs; no candidates were discarded")
        store.event(ident, "inputs", "complete", candidates=len(rows))
        candidates = []
        for r in rows:
            c = evaluate_row(r, ref, folder, store.root, profile, store, ident,
                             demo=spec["mode"] == "demo")
            candidates.append(c)
            write_json(folder / "partial-evidence.json", {"candidates": candidates})
        if spec["mode"] == "live":
            eligible = [c for c in candidates if c["eligible"]]
            write_json(folder / "eligible.json", eligible)
            if eligible:
                vals = {"workspace": str(folder), "input": str(folder / "eligible.json"),
                        "output": str(folder / "predictions.json")}
                for stage in ("refold_prepare", "predict", "refold_score"):
                    adapter(profile, stage, folder, vals, store, ident)
                predictions = json.loads((folder / "predictions.json").read_text())
                if not isinstance(predictions, dict):
                    raise ValueError("predictions.json must be keyed by candidate ID")
                missing = [c["design_id"] for c in eligible if c["design_id"] not in predictions]
                if missing:
                    raise ValueError("Prediction results missing eligible candidates: " + ", ".join(missing))
                for c in candidates:
                    if not c["eligible"]:
                        continue
                    p = predictions.get(c["design_id"], {})
                    c["predictions"] = p.get("predictions", [])
                    c["model_disagreement"] = p.get("model_disagreement", c["model_disagreement"])
                    c["limitations"] += p.get("limitations", [])
                    c["developability"] = p.get("developability", c["developability"])
                    for i, s in enumerate(p.get("structures", [])):
                        path = copy_artifact(store.root, folder, s["path"], f"{c['design_id']}-pred-{i}.pdb")
                        c["structures"].append({**s, "path": path, "sha256": sha256(folder / path)})
                    for a in AXES:
                        if a in p.get("evidence", {}):
                            c["objectives"][a] = objective(p["evidence"][a], a)
        # Optional structural comparison uses explicitly supplied chain mapping.
        from .structures import compare_interface
        for c, row in zip(candidates, rows):
            interface = row.get("interface")
            if interface and c["structures"]:
                rp = copy_artifact(store.root, folder, interface["reference"], c["design_id"] + "-reference.pdb")
                ev = compare_interface(folder / c["structures"][0]["path"], folder / rp,
                                       interface["target_chains"], interface["binder_chains"],
                                       interface["reference_target_chains"], interface["reference_binder_chains"])
                c["objectives"]["epitope"] = objective(ev)
                c["reference_structure"] = rp
        store.event(ident, "ranking", "running")
        rank_candidates(candidates, spec["cap"])
        picked = [c for c in candidates if c["selected"]]
        diversity = sequence_diversity(picked)
        result = {"iteration_id": ident, "mode": spec["mode"], "question": spec["question"],
                  "ranking_version": RANKING_VERSION, "reference_sha256": sha256(folder / "reference.json"),
                  "diversity": diversity,
                  "candidates": candidates, "counts": {"generated": len(candidates),
                      "eligible": sum(c["eligible"] for c in candidates),
                      "shortlisted": sum(c["selected"] for c in candidates),
                      "failed": sum(c["validation"]["status"] == "fail" for c in candidates)},
                  "limitations": ["No experimental improvement or probability of success is inferred",
                                   "Unknown evidence is not imputed; only official passes can be exported"]}
        write_json(folder / "evidence.json", result)
        write_exports(folder, candidates)
        store.event(ident, "ranking", "complete", shortlisted=result["counts"]["shortlisted"])
        provenance = json.loads((folder / "provenance.json").read_text())
        provenance["completed"] = now()
        write_json(folder / "provenance.json", provenance)
        # Recompute after finalizing timestamps, keeping every manifest hash valid.
        write_json(folder / "manifest.json", [
            {"path": str(p.relative_to(folder)), "bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(folder.rglob("*")) if p.is_file() and p.name not in ("manifest.json", "events.jsonl", "worker.log")])
        store.update(ident, "complete")
    except Exception as exc:
        # Keep partial candidates and exact tool output when an external stage fails.
        if "candidates" in locals():
            try:
                write_json(folder / "partial-evidence.json", {"candidates": candidates})
            except (ValueError, TypeError, OSError):
                # Invalid/nonfinite imported metadata may itself be the cause.
                # The copied original input and last valid snapshot survive.
                pass
        status = "blocked" if isinstance(exc, Unavailable) else "failed"
        store.event(ident, "pipeline", status, error=f"{type(exc).__name__}: {exc}")
        store.update(ident, status, f"{type(exc).__name__}: {exc}")


def write_exports(folder, candidates):
    def csv_text(rows):
        s = io.StringIO()
        fields = ["rank", "design_id", "track", "format", "sequence", "eligible", "pareto_front",
                  *AXES, "rationale", "uncertainty"]
        w = csv.DictWriter(s, fieldnames=fields)
        w.writeheader()
        for c in rows:
            row = {k: c.get(k) for k in fields if k not in AXES}
            for k in ("rationale", "uncertainty"):
                row[k] = " | ".join(row[k] or [])
            row.update({a: json.dumps(c["objectives"][a], sort_keys=True) for a in AXES})
            # CSV exports must not evaluate imported IDs/metadata as formulas.
            w.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k, v in row.items()})
        return s.getvalue()
    ordered = sorted(candidates, key=lambda c: (c["rank"] or 100000, c["design_id"]))
    selected = [c for c in ordered if c["selected"] and c["eligible"] and not c["stub"]][:20]
    (folder / "candidate_scores.csv").write_text(csv_text(ordered))
    (folder / "final_ranked_designs.csv").write_text(csv_text(selected))
    (folder / "final_sequences.fasta").write_text("".join(f">{c['design_id']} track={c['track']}\n{c['sequence']}\n" for c in selected))


def export_bundle(root, ident):
    store = Store(root)
    d = store.get(ident)
    if not d or d["status"] != "complete":
        raise ValueError("Only completed iterations can be exported")
    folder = store.directory(ident)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob("*"):
            if p.is_file() and p.name != "worker.log":
                z.write(p, str(p.relative_to(folder)))
    return output.getvalue()


def inventory(root):
    root = Path(root)
    sources = []
    for folder in (root / "data/source", root / "data/reference"):
        if folder.exists():
            for p in sorted(folder.rglob("*")):
                if p.is_file() and not p.name.startswith("."):
                    sources.append({"path": str(p.relative_to(root)), "bytes": p.stat().st_size,
                                    "sha256": sha256(p)})
    readmes = [p["path"] for p in sources if Path(p["path"]).name.lower() == "readme.md"]
    return {"at": now(), "tools": {k: shutil.which(k) for k in ("python3", "docker", "abguard", "foundry-toolkit")},
            "files": sources, "organizer_readmes": readmes,
            "limitations": ["Tool executable presence does not verify Docker images, GPU or model availability",
                            "Organizer bucket README, VM instructions and tutorial must be supplied before live commands",
                            "No supported thermostability predictor is configured",
                            "Provided clonotype splits are absent locally; edit-distance split is exploratory, not the official evaluation"]}


def resource_status(root):
    """Cheap discovery for the dashboard; never launches or certifies a model."""
    root = Path(root)
    return {
        "tools": {name: bool(shutil.which(name)) for name in ("docker", "abguard", "foundry-toolkit")},
        "organizer_readme": any(p.is_file() for p in (
            root / "data/source/README.md", root / "hackathon-data/README.md")),
        "vm_instructions": (Path.home() / "rfd4/18-vm.md").is_file(),
        "model_tutorial": (Path.home() / "rfd4/Tutorial.html").is_file(),
        "note": "Executable presence does not verify GPU, images or model support. Live runs require a verified CLI adapter profile; no thermostability predictor is bundled."
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    sub.add_parser("list")
    s = sub.add_parser("start")
    s.add_argument("--mode", choices=("demo", "import", "live"), default="demo")
    s.add_argument("--question", required=True)
    s.add_argument("--input")
    s.add_argument("--profile")
    s.add_argument("--parent")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--candidates", type=int, default=24)
    s.add_argument("--cap", type=int, default=20)
    sub.add_parser("worker").add_argument("ident")
    a = p.parse_args(argv)
    if a.command == "inventory":
        print(json.dumps(inventory(a.root), indent=2))
    elif a.command == "list":
        print(json.dumps(Store(a.root).list(), indent=2))
    elif a.command == "worker":
        work(a.root, a.ident)
    else:
        spec = {k: v for k, v in vars(a).items() if k not in ("root", "command") and v is not None}
        print(json.dumps(start(a.root, spec), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
