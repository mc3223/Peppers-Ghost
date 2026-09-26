#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOICES_DIR="$SCRIPT_DIR/../voices"
OUT="$SCRIPT_DIR/number_answer.wav"

# Ask the question aloud.
python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "How many pets do you have? Please say a number." \
  | aplay -r 22050 -f S16_LE -t raw -

# Record the answer using the independent USB microphone.
echo "Speak now! Recording for 5 seconds..."
arecord -D plughw:4,0 -d 5 -f S16_LE -c 1 -r 16000 "$OUT"

# Show what the speech recognizer heard.
python3 "$SCRIPT_DIR/transcribe.py" "$OUT" --model tiny.en
