#!/usr/bin/env bash
set -euo pipefail

# Find the downloaded voice model.
VOICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/voices"

# Ask for the name to use in the greeting.
read -r -p "Enter your name: " NAME

# Generate speech and play it through the speaker.
python3 -m piper \
  --model en_US-lessac-medium \
  --data-dir "$VOICES_DIR" \
  --output-raw \
  -- "Hello, ${NAME}! Welcome back. I hope you have a wonderful day." \
  | aplay -r 22050 -f S16_LE -t raw -
