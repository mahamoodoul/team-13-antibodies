#!/usr/bin/env bash
# Fold the designs the RANKER selected, both models. Fresh output dirs because
# the folders refuse a non-empty --output; normalise_model() maps the -picks
# suffix back to the model name, same as the existing -close dirs.
set -euo pipefail
cd ~/ruhit/gen
H=runs/optB/prepared/holo
[ -f $H/queries.firstfold.json ] || cp $H/queries.json $H/queries.firstfold.json
cp $H/queries.picks.json $H/queries.json
for M in boltz2 protenix-v2; do
  echo "### folding ${M} $(date -u +%FT%TZ)"
  rm -rf runs/optB/$M-picks
  MODEL=$M IN=runs/optB/prepared OUT=runs/optB/$M-picks bash scripts/fold.sh
done
RFD=quay.io/apheris/oslo-hackathon:apheris-rfd4-proteina-v0.3.0-her2-2026-11-07
for M in boltz2 protenix-v2; do
  echo "### refold-score $M $(date -u +%FT%TZ)"
  rm -rf runs/optB/scored-$M-picks
  docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work "$RFD" module-run refold-score \
    --input runs/optB/design --output runs/optB/scored-$M-picks \
    --predictions runs/optB/$M-picks --model $M || echo "refold-score $M failed, continuing"
done
echo "### export $(date -u +%FT%TZ)"
python3 -I export_batch.py runs/optB --weight her2-2026-11-07 --seed 2 --prefix optB \
  --out runs/optB/designs.jsonl
echo "PICKS_FOLD_DONE $(date -u +%FT%TZ)"
