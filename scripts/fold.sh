#!/usr/bin/env bash
# Fold a prepared holo/queries.json with one folding model, identical flags for every batch.
#   MODEL=boltz2 IN=runs/baseline OUT=runs/baseline/boltz2 bash scripts/fold.sh
set -euo pipefail
Q=quay.io/apheris/oslo-hackathon
MODEL=${MODEL:-boltz2}
case "$MODEL" in
  boltz2)      IMG=$Q:apheris-boltz-v1.3.0-boltz2 ;;
  protenix-v2) IMG=$Q:apheris-protenix-v1.3.0-v2 ;;
  of3ob)       IMG=$Q:apheris-openfold3-v1.3.0-of3ob ;;
  *) echo "unknown MODEL $MODEL"; exit 1 ;;
esac
IN=${IN:?set IN to the prepared dir}; OUT=${OUT:?set OUT}
CMD=$(docker inspect -f "{{join .Config.Cmd \" \"}}" "$IMG")
docker run --rm --gpus all --shm-size 16g --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /etc/passwd:/etc/passwd:ro -v "$PWD:/work" -w /work "$IMG" $CMD predict \
  --input "$IN/holo/queries.json" --output "$OUT" \
  --template-paths "$IN/holo/template.cif" --write-detailed-scores true \
  --num-diffusion-samples 1 --seeds 42 --query-failures skip
echo "FOLD_DONE $MODEL $(date -u +%FT%TZ)"
