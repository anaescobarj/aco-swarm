#!/usr/bin/env bash
# Ejecuta TODA la simulación sin Docker (útil para depurar). Requiere:
#   pip install numpy pillow matplotlib pybullet
# Uso:  ./run_local.sh            (los resultados quedan en ./out)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
export PYTHONPATH="$PWD" PYTHONUNBUFFERED=1
export AP_HOST=127.0.0.1 AP_PORT=${AP_PORT:-5000} OUT_DIR="$PWD/out" HTTP_PORT=${HTTP_PORT:-8080}
export EXIT_WHEN_DONE=1
mkdir -p out logs
pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

$PY ap/ap_relay.py > logs/ap.log 2>&1 & pids+=($!)
sleep 0.5
for n in 1 2 3; do
  NODE_ID=$n $PY node/node_esp32.py > logs/nodo$n.log 2>&1 & pids+=($!)
done
$PY twin/twin.py 2>&1 | tee logs/twin.log
echo "---- logs de nodos ----"; tail -n 4 logs/nodo*.log
