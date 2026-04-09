#!/bin/bash
set -euo pipefail

cd /app/

plantform="$(uname -m)"
PLANT_PATH=${PLANT_PATH:-/app/env}
plant="${PLANT_PATH}_${plantform}"

if [ -f /app/environment.sh ]; then
  source /app/environment.sh
fi

if [ -f "$plant/bin/activate" ]; then
  source "$plant/bin/activate"
fi

CONFIG_PATH=${CONFIG_PATH:-/app/config.yaml}
START_MODE=${START_MODE:-api}

case "$START_MODE" in
  api|worker|auth|all) ;;
  *)
    echo "Unsupported START_MODE: $START_MODE" >&2
    exit 1
    ;;
esac

exec python3 main.py -config "$CONFIG_PATH" --mode "$START_MODE"
