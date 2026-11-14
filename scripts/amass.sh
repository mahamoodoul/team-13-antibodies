#!/usr/bin/env bash
# AMASS scientific-intelligence search. $100 credit, EXPIRES 14 Dec 2026 UTC.
#
# Reads AMASS_API_KEY from the environment -- never hardcode the key here, this
# repo is public. Load it first:
#
#   set -a && . ./amass.env && set +a
#
# Usage:  scripts/amass.sh <core> <query> [extra=param ...]
#
#   scripts/amass.sh biomedcore "trastuzumab epitope HER2 domain IV" limit=10
#   scripts/amass.sh biomedcore "affinity epitope independence antibody" minJournalQualityJufo=2
#   scripts/amass.sh trialcore  "HER2 breast cancer" phase=PHASE3 overallStatus=RECRUITING
#   scripts/amass.sh drugcore   "trastuzumab" drugType=ANTIBODY
#
# Cores: biomedcore (papers) · trialcore · drugcore · regulatorycore · genecore
#        patentcore (preview)
#
# Rate limit is 60 requests / 60 s per user+org; a 429 carries Retry-After.
# Raw JSON is written to artifacts/amass/ so a pitch claim can cite the exact
# response it came from, not a paraphrase of it.
set -euo pipefail

BASE="${AMASS_BASE_URL:-https://api.amass.tech/api/v1}"

if [[ -z "${AMASS_API_KEY:-}" ]]; then
  echo "AMASS_API_KEY is not set. Run: set -a && . ./amass.env && set +a" >&2
  exit 1
fi

if [[ $# -lt 2 ]]; then
  sed -n '2,24p' "$0" >&2
  exit 2
fi

core="$1"; query="$2"; shift 2

args=(--get --data-urlencode "query=${query}")
for kv in "$@"; do
  args+=(--data-urlencode "$kv")
done

outdir="$(cd "$(dirname "$0")/.." && pwd)/artifacts/amass"
mkdir -p "$outdir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
slug="$(printf '%s' "$query" | tr -cs 'A-Za-z0-9' '-' | cut -c1-48 | sed 's/-$//')"
out="${outdir}/${stamp}-${core}-${slug}.json"

code="$(curl -sS "${BASE}/cores/${core}/records" \
  -H "Authorization: Bearer ${AMASS_API_KEY}" \
  -H 'Accept: application/json' \
  "${args[@]}" \
  -o "$out" -w '%{http_code}')"

if [[ "$code" != "200" ]]; then
  echo "AMASS returned HTTP ${code}" >&2
  cat "$out" >&2
  exit 1
fi

echo "saved: ${out}" >&2
python3 - "$out" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
recs = d.get("data") or []
if isinstance(recs, dict):
    recs = recs.get("records") or recs.get("items") or [recs]
print(f"{len(recs)} record(s)\n")
for r in recs:
    if not isinstance(r, dict):
        print(r); continue
    title = r.get("title") or r.get("briefTitle") or r.get("name") or "(untitled)"
    year  = r.get("year") or r.get("publicationYear") or r.get("startDate") or ""
    ident = r.get("doi") or r.get("nctId") or r.get("amassId") or ""
    print(f"- {title}")
    if year or ident:
        print(f"    {year}  {ident}".rstrip())
PY
