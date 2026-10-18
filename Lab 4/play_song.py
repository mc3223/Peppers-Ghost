import math
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path

BPM = 120
TRANSPOSE = 0       # Set to 12 to raise the melody by one octave.
VOLUME = 0.25       # Range: 0.0 to 1.0
SAMPLE_RATE = 44100

LE_FESTIN = [
    ("Bb3", 0.5),
    ("G4", 1), ("F4", 1), ("Eb4", 1),
    ("G4", 1), ("F4", 1.5), ("Eb4", 0.5),
    ("G4", 1), ("F4", 1), ("Eb4", 1),
    ("Bb3", 2), ("Bb3", 1),
    ("Bb4", 1), ("F4", 1), ("Eb4", 1),
    ("Bb4", 1), ("D4", 1.5), ("D4", 0.5),
    ("Bb4", 1), ("F4", 1.5), ("D4", 0.5),
    ("Eb4", 2), ("F4", 0.5), ("Bb4", 0.5),
    ("G4", 1), ("F4", 1), ("Eb4", 1),
    ("G4", 1), ("F4", 1.5), ("A4", 0.5),
    ("Bb4", 1), ("G4", 1), ("Bb4", 1),
    ("C5", 2), ("rest", 1),
    ("Bb4", 1), ("F4", 1), ("Eb4", 1),
    ("Bb3", 1), ("D4", 1.5), ("C5", 0.5),
    ("D5", 1), ("D5", 1), ("Bb4", 0.5),
    ("C5", 2.5), ("rest", 0.5), ("G4", 0.5),
    ("A4", 1), ("Eb4", 1.5), ("C4", 0.5),
    ("D4", 2), ("G4", 0.75), ("G4", 0.25),
    ("Eb4", 3),
]


def note_frequency(note):
    """Convert a note name to its frequency in Hz."""
    semitones = {
        "C": 0, "D": 2, "E": 4, "F": 5,
        "G": 7, "A": 9, "B": 11,
    }

    pitch = semitones[note[0]]
    octave_start = 1

    if note[1:2] == "#":
        pitch += 1
        octave_start = 2
    elif note[1:2] == "b":
        pitch -= 1
        octave_start = 2

    octave = int(note[octave_start:])
    midi_note = (octave + 1) * 12 + pitch + TRANSPOSE

    return 440.0 * 2 ** ((midi_note - 69) / 12)


def create_wav(filename):
    """Generate a mono WAV file with a simple plucked tone."""
    with wave.open(str(filename), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)

        for note, beats in LE_FESTIN:
            duration = beats * 60.0 / BPM
            count = round(duration * SAMPLE_RATE)
            samples = array("h", [0]) * count

            if note != "rest":
                frequency = note_frequency(note)
                fade_samples = max(
                    1, min(int(0.005 * SAMPLE_RATE), count // 2)
                )

                for i in range(count):
                    t = i / SAMPLE_RATE

                    # Fade note boundaries to reduce clicks.
                    envelope = min(
                        1.0,
                        i / fade_samples,
                        (count - 1 - i) / fade_samples,
                    )

                    # Add decay and harmonics for a plucked sound.
                    envelope *= math.exp(-2.8 * t)
                    phase = 2 * math.pi * frequency * t
                    tone = (
                        math.sin(phase)
                        + 0.22 * math.sin(2 * phase)
                        + 0.08 * math.sin(3 * phase)
                    ) / 1.3

                    samples[i] = round(
                        32767 * VOLUME * envelope * tone
                    )

            if sys.byteorder != "little":
                samples.byteswap()

            wav.writeframes(samples.tobytes())


def play_loop(filename, player):
    """Stream repeated audio through one persistent aplay process."""
    with wave.open(str(filename), "rb") as wav:
        audio_data = wav.readframes(wav.getnframes())

    process = subprocess.Popen(
        [
            player,
            "-q",
            "-t", "raw",
            "-f", "S16_LE",
            "-r", str(SAMPLE_RATE),
            "-c", "1",
        ],
        stdin=subprocess.PIPE,
        bufsize=0,
    )

    try:
        while True:
            # Handle partial pipe writes without losing audio data.
            remaining = memoryview(audio_data)
            while remaining:
                written = process.stdin.write(remaining)
                if not written:
                    raise BrokenPipeError("Audio playback stopped.")
                remaining = remaining[written:]
    finally:
        # Stop playback immediately, including any buffered audio.
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        process.stdin.close()


def main():
    player = shutil.which("aplay")
    if player is None:
        print("aplay was not found. Install it with:")
        print("sudo apt install alsa-utils")
        return

    filename = Path(__file__).resolve().with_name("le_festin.wav")

    print("Generating melody...")
    create_wav(filename)

    print("Playing on repeat. Press Ctrl+C to stop.")
    try:
        play_loop(filename, player)
    except BrokenPipeError:
        print("Playback failed. Check your speaker and audio output settings.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPlayback stopped.")
