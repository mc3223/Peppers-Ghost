"""Hand-crank dessert box: a music box that opens to reveal a treat.

Turn the rotary encoder like a music-box crank. The melody plays at the speed
you crank, the servo turns the geared figure as the song progresses, and when
the song ends the lid opens. Press the encoder knob to reset.

Every piece of hardware is optional: anything that isn't plugged in is skipped
with a warning, so you can bring the box up one part at a time.

    python dessert_box.py              # on the Pi
    python dessert_box.py --simulate   # on a laptop: keys crank, no Pi needed
"""

import argparse
import math
import os
import select
import shutil
import struct
import subprocess
import sys
import time
import wave

# ---------------------------------------------------------------------------
# Settings to tune once the mechanism is built (see PLAN.md, step 6)
# ---------------------------------------------------------------------------

TICKS_PER_BEAT = 4        # encoder clicks per beat; lower = less cranking per song

FIGURE_CH = 0             # Servo pHAT channel that drives the gear train
FIGURE_START = 0          # servo angle at the start of the song
FIGURE_END = 180          # servo angle at the end of the song

LID_CH = None             # set to 1 if the lid has its own servo on channel 1
LID_CLOSED = 0
LID_OPEN = 90

# Pulse widths in ms for 0° and 180°. The library default (1.0, 2.0) only moves
# most 9g servos about 90°; widen toward (0.5, 2.5) to get the full 180°.
SERVO_PULSE_MS = (1.0, 2.0)

ENCODER_ADDR = 0x36
OLED_SIZE = (128, 32)

# Twinkle Twinkle Little Star as (note, beats). Swap in any melody here.
SONG_NAME = "Twinkle Twinkle"
SONG = [
    ("C5", 1), ("C5", 1), ("G5", 1), ("G5", 1), ("A5", 1), ("A5", 1), ("G5", 2),
    ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 1), ("D5", 1), ("C5", 2),
    ("G5", 1), ("G5", 1), ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 2),
    ("G5", 1), ("G5", 1), ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 2),
    ("C5", 1), ("C5", 1), ("G5", 1), ("G5", 1), ("A5", 1), ("A5", 1), ("G5", 2),
    ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 1), ("D5", 1), ("C5", 2),
]

SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
SAMPLE_RATE = 22050

# ---------------------------------------------------------------------------
# Sound: synthesize music-box notes once, then play them with aplay/afplay
# ---------------------------------------------------------------------------

NOTE_OFFSETS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_freq(name):
    """'C5' -> Hz. Supports sharps/flats like 'F#4' or 'Bb4'."""
    semitone = NOTE_OFFSETS[name[0]]
    rest = name[1:]
    if rest.startswith("#"):
        semitone, rest = semitone + 1, rest[1:]
    elif rest.startswith("b"):
        semitone, rest = semitone - 1, rest[1:]
    midi = 12 * (int(rest) + 1) + semitone
    return 440.0 * 2 ** ((midi - 69) / 12)


def write_note_wav(path, freq, seconds=1.4):
    """A plucked-tine tone: fast attack, long decay, quick-fading overtones."""
    frames = bytearray()
    for i in range(int(SAMPLE_RATE * seconds)):
        t = i / SAMPLE_RATE
        attack = min(1.0, t / 0.004)
        s = (math.sin(2 * math.pi * freq * t) * math.exp(-3.0 * t)
             + 0.35 * math.sin(2 * math.pi * 2 * freq * t) * math.exp(-7.0 * t)
             + 0.12 * math.sin(2 * math.pi * 5.4 * freq * t) * math.exp(-18.0 * t))
        frames += struct.pack("<h", int(0.45 * 32767 * attack * s / 1.47))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))


class Sound:
    def __init__(self, notes):
        self.player = shutil.which("aplay") or shutil.which("afplay")
        if not self.player:
            print("! No aplay/afplay found; notes will only be printed")
        os.makedirs(SOUND_DIR, exist_ok=True)
        self.paths = {}
        for name in sorted(set(notes)):
            path = os.path.join(SOUND_DIR, f"{name}.wav")
            if not os.path.exists(path):
                write_note_wav(path, note_freq(name))
            self.paths[name] = path
        self.procs = []

    def play(self, name):
        print(f"♪ {name}")
        if not self.player:
            return
        args = [self.player, "-q", self.paths[name]] if self.player.endswith("aplay") \
            else [self.player, self.paths[name]]
        self.procs = [p for p in self.procs if p.poll() is None]
        self.procs.append(subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL))

# ---------------------------------------------------------------------------
# Inputs: the encoder on the Pi, or the keyboard in --simulate
# ---------------------------------------------------------------------------


class EncoderCrank:
    def __init__(self):
        import board
        from adafruit_seesaw import seesaw, rotaryio, digitalio
        ss = seesaw.Seesaw(board.I2C(), addr=ENCODER_ADDR)
        ss.pin_mode(24, ss.INPUT_PULLUP)
        self.button = digitalio.DigitalIO(ss, 24)
        self.encoder = rotaryio.IncrementalEncoder(ss)
        self.last = -self.encoder.position
        self.held = False

    def read(self):
        """Returns (clicks turned since last read, True if the knob was just pressed)."""
        pos = -self.encoder.position  # negate so clockwise is positive
        delta, self.last = pos - self.last, pos
        pressed = not self.button.value
        clicked = pressed and not self.held
        self.held = pressed
        return delta, clicked


class KeyboardCrank:
    """Any key = one crank click, r = knob press (reset), q = quit."""

    def __init__(self):
        import termios
        import tty
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        print("Simulate: hold any key to crank, r = reset, q = quit")

    def read(self):
        delta, clicked = 0, False
        while select.select([sys.stdin], [], [], 0)[0]:
            ch = sys.stdin.read(1)
            if ch == "q":
                raise KeyboardInterrupt
            if ch == "r":
                clicked = True
            else:
                delta += 1
        return delta, clicked

    def close(self):
        import termios
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

# ---------------------------------------------------------------------------
# Outputs: servos and OLED (both fall back to printing)
# ---------------------------------------------------------------------------


class Servos:
    def __init__(self, simulate):
        self.hat = None
        self.angles = {}
        if simulate:
            return
        try:
            import pi_servo_hat
            hat = pi_servo_hat.PiServoHat()
            hat.restart()
            hat.set_pulse_time(*SERVO_PULSE_MS)
            self.hat = hat
        except Exception as e:
            print(f"! Servo pHAT not found ({e}); servo moves will be skipped")

    def move(self, channel, angle):
        angle = int(max(0, min(180, angle)))
        if self.angles.get(channel) == angle:
            return
        self.angles[channel] = angle
        if self.hat:
            self.hat.move_servo_position(channel, angle, 180)

    def ease(self, channel, target, seconds=1.0):
        start = self.angles.get(channel, target)
        steps = max(1, abs(target - start))
        for i in range(1, steps + 1):
            self.move(channel, start + (target - start) * i / steps)
            time.sleep(seconds / steps)


class Display:
    def __init__(self, simulate):
        self.oled = None
        self.font = None
        if simulate:
            return
        try:
            import board
            import adafruit_ssd1306
            self.oled = adafruit_ssd1306.SSD1306_I2C(*OLED_SIZE, board.I2C())
        except Exception as e:
            print(f"! OLED not found ({e}); status will be printed")
            return
        try:
            from PIL import Image, ImageDraw, ImageFont
            self.Image, self.ImageDraw = Image, ImageDraw
            self.font = ImageFont.load_default()
        except ImportError:
            print("! Pillow not installed; OLED will show the progress bar only")
        self.last = None

    def show(self, title, progress):
        """Title on the top line, progress bar (0..1) along the bottom."""
        if not self.oled:
            return
        state = (title, int(progress * 100))
        if state == self.last:
            return
        self.last = state
        w, h = OLED_SIZE
        bar = int((w - 4) * progress)
        if self.font:
            img = self.Image.new("1", OLED_SIZE)
            d = self.ImageDraw.Draw(img)
            d.text((0, 0), title, font=self.font, fill=1)
            d.rectangle((0, h - 10, w - 1, h - 1), outline=1)
            d.rectangle((2, h - 8, 2 + bar, h - 3), fill=1)
            self.oled.image(img)
        else:
            self.oled.fill(0)
            self.oled.rect(0, h - 10, w, 10, 1)
            self.oled.fill_rect(2, h - 8, bar, 6, 1)
        self.oled.show()

# ---------------------------------------------------------------------------
# The music box
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--simulate", action="store_true",
                        help="use the keyboard as the crank; skip all Pi hardware")
    args = parser.parse_args()

    onsets, beat = [], 0
    for name, beats in SONG:
        onsets.append((beat, name))
        beat += beats
    total_beats = beat

    sound = Sound([name for name, _ in SONG])
    servos = Servos(args.simulate)
    display = Display(args.simulate)
    if args.simulate:
        crank = KeyboardCrank()
    else:
        try:
            crank = EncoderCrank()
        except Exception as e:
            sys.exit(f"Rotary encoder not found at {hex(ENCODER_ADDR)} ({e}). "
                     "Plug it in, or try --simulate.")

    def reset():
        print("Reset: closing lid, rewinding figure")
        if LID_CH is not None:
            servos.ease(LID_CH, LID_CLOSED, 0.8)
        servos.ease(FIGURE_CH, FIGURE_START, 1.5)
        display.show("Crank me!", 0)
        return 0, 0  # (ticks, index of next note)

    ticks, next_note = reset()
    done = False
    try:
        while True:
            delta, clicked = crank.read()
            if clicked:
                ticks, next_note = reset()
                done = False
            # Like a real music box, cranking backwards does nothing.
            if delta > 0 and not done:
                ticks += delta
                pos = ticks / TICKS_PER_BEAT
                while next_note < len(onsets) and onsets[next_note][0] <= pos:
                    sound.play(onsets[next_note][1])
                    next_note += 1
                progress = min(1.0, pos / total_beats)
                servos.move(FIGURE_CH, FIGURE_START + (FIGURE_END - FIGURE_START) * progress)
                display.show(SONG_NAME, progress)
                if pos >= total_beats:
                    done = True
                    print("Song finished: opening lid")
                    time.sleep(1.0)  # let the last note ring
                    if LID_CH is not None:
                        servos.ease(LID_CH, LID_OPEN, 0.8)
                    display.show("Enjoy! Press knob", 1.0)
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nBye")
    finally:
        if isinstance(crank, KeyboardCrank):
            crank.close()


if __name__ == "__main__":
    main()
