#!/usr/bin/env bash
# Generate CDRH3 designs with one RFD4-Proteina weight. Optimisation track.
#   WEIGHT=her2-novel-2026-11-09 N=100 SEED=1 TSRK= OUT=runs/optA bash scripts/design_batch.sh
set -euo pipefail
Q=quay.io/apheris/oslo-hackathon
WEIGHT=${WEIGHT:-her2-novel-2026-11-09}
N=${N:-100}; SEED=${SEED:-1}; OUT=${OUT:-runs/opt}; COMPILE=${COMPILE:-true}
RFD=$Q:apheris-rfd4-proteina-v0.3.0-$WEIGHT
extra=()
[ -n "${TSRK:-}" ] && extra+=(--sequence-tsr-k "$TSRK")
[ "$COMPILE" = "true" ] && extra+=(--compile true)
mkdir -p "$OUT"
cat > "$OUT/provenance.json" <<PROV
{"weight": "$WEIGHT", "num_replicates": $N, "seed": $SEED, "sequence_tsr_k": "${TSRK:-unset}",
 "compile": "$COMPILE", "recycle_strategy": "high/front_loaded",
 "input": "Data/12-her2/her2_cdrh3.yaml", "track": "optimisation",
 "started_utc": "$(date -u +%FT%TZ)", "image": "$RFD"}
PROV
docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work "$RFD" module-run design \
  --input Data/12-her2/her2_cdrh3.yaml --output "$OUT/design" \
  --num-replicates "$N" --seed "$SEED" --recycle-strategy high/front_loaded "${extra[@]}"
echo "DESIGN_DONE $(date -u +%FT%TZ)"
