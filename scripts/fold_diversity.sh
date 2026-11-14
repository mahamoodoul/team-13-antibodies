#!/usr/bin/env bash
# Fold the diversity batch. multicdr is the only uncorrelated hypothesis left
# (denovo is out on identity AND on construct length), and it is the one batch
# where the epitope axis actually discriminates -- 3 of the first 16 refolded
# designs do not contact the trastuzumab epitope at all. Picking a diversity
# slot from unfolded multicdr designs means picking blind on exactly the axis
# that batch is at risk on. So: all 95 submittable, in the ranker's own order.
set -euo pipefail
cd ~/ruhit/gen
H=runs/multicdr/prepared/holo
[ -f $H/queries.firstfold.json ] || cp $H/queries.json $H/queries.firstfold.json
cp $H/queries.diversity.json $H/queries.json
for M in boltz2 protenix-v2; do
  echo "### folding ${M} $(date -u +%FT%TZ)"
  rm -rf runs/multicdr/$M-div
  MODEL=$M IN=runs/multicdr/prepared OUT=runs/multicdr/$M-div bash scripts/fold.sh
done
RFD=quay.io/apheris/oslo-hackathon:apheris-rfd4-proteina-v0.3.0-antibody-2026-10-30
for M in boltz2 protenix-v2; do
  echo "### refold-score $M $(date -u +%FT%TZ)"
  rm -rf runs/multicdr/scored-$M-div
  docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work "$RFD" module-run refold-score \
    --input runs/multicdr/design --output runs/multicdr/scored-$M-div \
    --predictions runs/multicdr/$M-div --model $M || echo "refold-score $M failed, continuing"
done
echo "### export $(date -u +%FT%TZ)"
python3 -I scripts/export_batch.py runs/multicdr --weight antibody-2026-10-30 --seed 3 \
  --prefix multicdr --out runs/multicdr/designs.jsonl
echo "DIVERSITY_FOLD_DONE $(date -u +%FT%TZ)"
