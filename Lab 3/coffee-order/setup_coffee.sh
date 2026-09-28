#!/usr/bin/env bash
# Run: bash setup_coffee.sh
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LAB_DIR="$(dirname -- "$SCRIPT_DIR")"
COFFEE_VENV="${COFFEE_VENV:-$LAB_DIR/.venv}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Run this installer on the Raspberry Pi, not on Windows." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential swig libportaudio2 alsa-utils \
  espeak-ng fonts-dejavu-core curl libopenblas0

if [[ ! -x "$COFFEE_VENV/bin/python" ]]; then
  python3 -m venv "$COFFEE_VENV"
fi
PYTHON="$COFFEE_VENV/bin/python"
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"

mkdir -p "$LAB_DIR/models" "$LAB_DIR/voices"
VAD="$LAB_DIR/models/silero_vad.onnx"
if [[ ! -s "$VAD" ]]; then
  curl --fail --location --retry 3 \
    https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx \
    --output "$VAD.part"
  mv -- "$VAD.part" "$VAD"
fi

VOICE="$LAB_DIR/voices/en_US-lessac-medium.onnx"
if [[ ! -s "$VOICE" || ! -s "$VOICE.json" ]]; then
  "$PYTHON" -m piper.download_voices en_US-lessac-medium --data-dir "$LAB_DIR/voices"
fi

"$PYTHON" -c 'from faster_whisper import WhisperModel; WhisperModel("tiny.en", device="cpu", compute_type="int8"); print("tiny.en ready")'

if [[ ! -e "$SCRIPT_DIR/config.json" ]]; then
  cp -- "$SCRIPT_DIR/config.example.json" "$SCRIPT_DIR/config.json"
fi
"$PYTHON" -m unittest discover -s "$SCRIPT_DIR/tests" -v
echo
echo "Setup complete. Next: bash run_coffee.sh --check"
echo "List audio devices: bash run_coffee.sh --list-devices"
echo "Then start: bash run_coffee.sh"
echo "If using a custom environment, keep COFFEE_VENV set when launching."
