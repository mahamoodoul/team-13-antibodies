"""Evidence-based ranking. Raw metrics retain their units; missing is never zero.

This workflow deliberately does not interpret a heuristic as a probability or
multiply dependent model outputs into a probability of laboratory success.
"""
from __future__ import annotations

import math
from .align import identity
from .schema import AXES

RANKING_VERSION = "pareto-evidence-v2"


def objective(raw, axis=None):
    if not isinstance(raw, dict):
        return {"status": "unknown", "reason": "No supported evidence supplied"}
    if axis == "stability" and any(x in str(raw.get("method", "")).lower()
                                   for x in ("plddt", "iptm", "pae", "soluprot", "netsolp", "aggrescan")):
        return {"status": "unknown", "reason": "Confidence/developability is not thermostability"}
    required = ("method", "version", "unit", "source", "direction", "kind")
    if any(not isinstance(raw.get(k), str) or not raw[k].strip() for k in required) or raw.get("direction") not in ("min", "max"):
        return {"status": "unknown", "reason": "Evidence needs method, version, unit, source, kind and direction"}
    if raw["kind"] not in ("prediction", "measurement"):
        return {"status": "unknown", "reason": "Evidence kind must be prediction or measurement"}
    value = raw.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return {"status": "unknown", "reason": "Evidence value must be a finite number"}
    ref = raw.get("reference_value")
    if ref is not None and (isinstance(ref, bool) or not isinstance(ref, (int, float)) or not math.isfinite(ref)):
        return {"status": "unknown", "reason": "Invalid baseline measurement"}
    return {**raw, "status": "available", "beats_reference": None if ref is None else
            (value < ref if raw["direction"] == "min" else value > ref)}


def comparable(a, b):
    # A different assay, model, version or unit is a different objective scale.
    return all(a.get(k) == b.get(k) for k in ("method", "version", "unit", "direction", "kind"))


def dominates(a, b):
    av = {k: v for k, v in a["objectives"].items() if v["status"] == "available"}
    bv = {k: v for k, v in b["objectives"].items() if v["status"] == "available"}
    if not av or av.keys() != bv.keys() or any(not comparable(av[k], bv[k]) for k in av):
        return False
    deltas = [(av[k]["value"] - bv[k]["value"]) * (1 if av[k]["direction"] == "max" else -1) for k in av]
    return all(d >= 0 for d in deltas) and any(d > 0 for d in deltas)


def rank_candidates(candidates, cap=20):
    """Pareto layers then farthest-first diversity, with an ID tie break.

    Only officially validated, non-demo designs enter the shortlist. Candidates
    with no usable objectives remain visible but are not ranked for export.
    Different evidence coverage never silently dominates missing objectives.
    """
    pool = []
    for c in candidates:
        c.update(rank=None, pareto_front=None, selected=False)
        c["uncertainty"] = [f"{a}: {c['objectives'][a].get('reason', 'unknown')}"
                            for a in AXES if c["objectives"][a]["status"] != "available"]
        c["uncertainty"] += ["Predictions require laboratory validation"]
        if c["eligible"] and any(v["status"] == "available" for v in c["objectives"].values()):
            pool.append(c)
        else:
            c["decision"] = "rejected" if c["validation"]["status"] == "fail" else "needs_evidence"
            c["rationale"] = list(c["validation"].get("failed_rules", [])) or [
                "Official validation and at least one supported objective are required for ranking"]
    # Compute the partial order once. Re-testing every pair for every front
    # makes a long chain of dominated candidates unnecessarily cubic.
    successors = {c["design_id"]: [] for c in pool}
    predecessors = {c["design_id"]: 0 for c in pool}
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            winner, loser = (a, b) if dominates(a, b) else ((b, a) if dominates(b, a) else (None, None))
            if winner is not None:
                successors[winner["design_id"]].append(loser["design_id"])
                predecessors[loser["design_id"]] += 1
    ranked = []
    distances = {}
    limit = max(0, min(cap, 20))

    def distance(c, p):
        field = "cdrh3" if c["cdrh3"] and p["cdrh3"] else "sequence"
        pair = tuple(sorted((c[field], p[field])))
        if pair not in distances:
            distances[pair] = 1 - identity(*pair)
        return distances[pair]

    front = 0
    while pool:
        front += 1
        layer = [c for c in pool if predecessors[c["design_id"]] == 0]
        completed_layer = list(layer)
        # Coverage is an explicit tie break within a non-dominated front.
        while layer:
            def key(c):
                # Diversity affects the submission shortlist, not hundreds of
                # reserves. Cache pairs and stop aligning once the cap is met.
                diversity = min((distance(c, p) for p in ranked), default=1) if len(ranked) < limit else 0
                coverage = sum(v["status"] == "available" for v in c["objectives"].values())
                return (-coverage, -diversity, c["design_id"])
            c = min(layer, key=key)
            layer.remove(c)
            pool.remove(c)
            c["pareto_front"] = front
            c["rank"] = len(ranked) + 1
            c["selected"] = c["rank"] <= limit
            c["decision"] = "shortlist" if c["selected"] else "reserve"
            c["rationale"] = [f"Pareto front {front}; " + (
                "coverage then sequence diversity break shortlist ties" if c["selected"] else
                "reserve ordered by coverage and ID after shortlist cap"),
                              "Unknown objectives remain unknown; no experimental tier assigned"]
            ranked.append(c)
        for c in completed_layer:
            for ident in successors[c["design_id"]]:
                predecessors[ident] -= 1
    return candidates


def sequence_diversity(candidates):
    """Compare matched sequence scopes; never align one loop to a whole construct."""
    pairs = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            loops = bool(a.get("cdrh3") and b.get("cdrh3"))
            field = "cdrh3" if loops else "sequence"
            pairs.append({"a": a["design_id"], "b": b["design_id"],
                          "scope": "CDRH3" if loops else "full construct",
                          "identity": round(identity(a[field], b[field]), 4)})
    return pairs
