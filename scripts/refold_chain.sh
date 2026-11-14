#!/usr/bin/env bash
# Post-design chain: refold-prepare -> export -> challenge filter -> fold -> score -> export.
# The filter runs BEFORE folding so GPU is spent only on submittable designs.
#   OUT=runs/optA WEIGHT=her2-novel-2026-11-09 SEED=1 MODEL=boltz2 MAXFOLD=25 \
#     bash scripts/refold_chain.sh
set -euo pipefail
Q=quay.io/apheris/oslo-hackathon
OUT=${OUT:?set OUT to the run dir}
WEIGHT=${WEIGHT:-her2-novel-2026-11-09}
SEED=${SEED:-1}
MODEL=${MODEL:-boltz2}
MAXFOLD=${MAXFOLD:-25}
PREPTOP=${PREPTOP:-100}
RFD=$Q:apheris-rfd4-proteina-v0.3.0-$WEIGHT
run=(docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)"
     -e HOME=/tmp -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work)

echo "### 1. refold-prepare (top $PREPTOP)"
rm -rf "$OUT/prepared"
"${run[@]}" "$RFD" module-run refold-prepare \
  --input "$OUT/design" --output "$OUT/prepared" --top-n "$PREPTOP"

echo "### 2. export designs (pre-refold)"
python3 -I scripts/export_batch.py "$OUT" --weight "$WEIGHT" --seed "$SEED" \
  --out "$OUT/designs.jsonl" --prefix "$(basename "$OUT")"

echo "### 3. challenge filter, before spending GPU"
python3 -I scripts/filter_queries.py "$OUT/designs.jsonl" \
  "$OUT/prepared/holo/queries.json" "$OUT/prepared/holo/queries.filtered.json" \
  --max "$MAXFOLD"
cp "$OUT/prepared/holo/queries.json" "$OUT/prepared/holo/queries.all.json"
cp "$OUT/prepared/holo/queries.filtered.json" "$OUT/prepared/holo/queries.json"

echo "### 4. fold with $MODEL"
MODEL=$MODEL IN="$OUT/prepared" OUT="$OUT/$MODEL" bash scripts/fold.sh

echo "### 5. refold-score"
rm -rf "$OUT/scored-$MODEL"
"${run[@]}" "$RFD" module-run refold-score \
  --input "$OUT/design" --output "$OUT/scored-$MODEL" \
  --predictions "$OUT/$MODEL" --model "$MODEL"

echo "### 6. export designs (with refold)"
python3 -I scripts/export_batch.py "$OUT" --weight "$WEIGHT" --seed "$SEED" \
  --out "$OUT/designs.jsonl" --prefix "$(basename "$OUT")"
echo "CHAIN_DONE $(date -u +%FT%TZ)"
