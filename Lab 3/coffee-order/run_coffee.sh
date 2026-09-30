#!/usr/bin/env bash
# All options are forwarded to coffee_order.py.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(dirname -- "$SCRIPT_DIR")"
COFFEE_VENV="${COFFEE_VENV:-$LAB_DIR/.venv}"
PYTHON="$COFFEE_VENV/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment missing: $COFFEE_VENV" >&2
  echo "Run bash setup_coffee.sh first." >&2
  exit 1
fi

HARDWARE=1
for arg in "$@"; do
  case "$arg" in
    --simulate|--list-devices|--check|--help|-h) HARDWARE=0 ;;
  esac
done

if [[ "$HARDWARE" == "1" ]]; then
  if command -v systemctl >/dev/null && systemctl is-active --quiet piscreen.service; then
    echo "Lab 2's piscreen.service is using the display pins." >&2
    echo "Temporarily stop it: sudo systemctl stop piscreen.service" >&2
    echo "Then run this script again. Restore later: sudo systemctl start piscreen.service" >&2
    exit 1
  fi
  if [[ ! -e /dev/spidev0.0 && ! -e /dev/spidev0.1 ]]; then
    echo "SPI is not available. Enable SPI using sudo raspi-config, then reboot." >&2
    exit 1
  fi
  mkdir -p "$SCRIPT_DIR/runs"
  exec 9>"$SCRIPT_DIR/runs/coffee.lock"
  if ! flock -n 9; then
    echo "Another coffee-order instance is already running." >&2
    exit 1
  fi
fi

cd -- "$SCRIPT_DIR"
exec "$PYTHON" -u "$SCRIPT_DIR/coffee_order.py" "$@"
