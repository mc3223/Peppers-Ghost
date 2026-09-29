#!/usr/bin/env python3
"""Lab 3 Part 2: speech input, PiTFT feedback, A accepts / B retries.

Hardware imports are deliberately deferred so --simulate and unit tests can run
on an ordinary computer. No speech is committed before an A confirmation.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
import time
import unicodedata
import uuid
import wave

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
DRINKS = ("Latte", "Cappuccino", "Mocha")
TEMPERATURES = ("Hot", "Iced")
SIZES = ("Small", "Medium", "Large")
DEFAULTS = {
    "voice": "../voices/en_US-lessac-medium.onnx",
    "vad_model": "../models/silero_vad.onnx",
    "asr_model": "tiny.en",
    "compute_type": "int8",
    "input_device": None,
    "output_device": None,
    "min_silence": 0.8,
    "min_speech": 0.15,
    "reply_timeout": 5.0,
    "max_utterance": 20.0,
    "audio_settle": 0.25,
    "save_audio": False,
    "run_dir": "runs",
}
RATE = 16000


@dataclass(frozen=True)
class Meaning:
    kind: str
    value: str = ""
    note: str = ""

    @property
    def label(self):
        if self.kind == "choice":
            return "Choice: " + self.value
        if self.kind == "change":
            return "Edit: " + self.value
        if self.kind == "price":
            return "Price question"
        return "Needs clarification"


def normalize(text):
    text = unicodedata.normalize("NFKC", text).lower().replace("\u2019", "'")
    text = re.sub(r"\bthat's\b", "that is", text)
    text = re.sub(r"\bit's\b", "it is", text)
    text = re.sub(r"\bdon't\b", "do not", text)
    text = re.sub(r"\bisn't\b", "is not", text)
    text = re.sub(r"\bcan't\b", "cannot", text)
    return re.sub(r"[^a-z0-9' ]", " ", text)


def corrected_clause(text):
    # Only an explicit correction marker lets us prefer a later option.
    return re.split(r"\b(?:actually|instead|sorry|i mean|rather)\b", text)[-1]


def alternatives(text, choices):
    matches = []
    for value, pattern in choices.items():
        for match in re.finditer(pattern, text):
            prefix = text[:match.start()].split()
            # Conservative: "not a large", "do not want hot", etc. are not
            # positive selections. Ambiguous language should be repeated.
            if any(w in {"no", "not", "never", "without"} for w in prefix[-4:]):
                continue
            matches.append(value)
    return set(matches)


CHOICES = {
    "drink": {"Latte": r"\blatte\b", "Cappuccino": r"\bcappuccino\b",
              "Mocha": r"\bmocha\b"},
    "temperature": {"Hot": r"\bhot\b", "Iced": r"\b(?:iced|ice|cold)\b"},
    "size": {"Small": r"\bsmall\b", "Medium": r"\bmedium\b", "Large": r"\blarge\b"},
    "edit": {"drink": r"\b(?:drink|coffee|beverage|latte|cappuccino|mocha)\b",
             "temperature": r"\b(?:temperature|hot|iced|ice|cold)\b",
             "size": r"\b(?:size|small|medium|large)\b"},
}


def interpret(step, heard):
    text = normalize(heard)
    if not text.strip():
        return Meaning("invalid", note="Please say that again.")
    if re.search(r"\b(?:price|prices|cost|costs|how much)\b", text):
        return Meaning("price")
    text = corrected_clause(text)
    if re.search(r"\b(?:or|either|maybe)\b", text):
        return Meaning("invalid", note="Please choose one definite answer.")
    if step in {"drink", "temperature", "size"}:
        if re.search(r"\b(?:two|three|four|five|six|several|multiple|both|[2-9])\b", text):
            return Meaning("invalid", note="Please order one drink at a time.")
    if step == "confirm":
        if re.search(r"\b(?:change|different|make it|switch|edit)\b", text):
            change_text = re.split(r"\b(?:change|different|make it|switch|edit)\b", text, maxsplit=1)[-1]
            fields = alternatives(change_text, CHOICES["edit"])
            return Meaning("change", next(iter(fields)) if len(fields) == 1 else "")
        negative = bool(re.search(r"\b(?:no|nope|wrong|incorrect|not)\b", text))
        positive = bool(re.search(r"\b(?:yes|yeah|yep|correct|right|okay|ok|sure)\b", text))
        if re.search(r"\bnot (?:quite )?(?:correct|right|okay|ok)\b", text):
            # The adjective inside "not correct" is not an affirmative.
            remainder = re.sub(r"\bnot (?:quite )?(?:correct|right|okay|ok)\b", "", text)
            positive = bool(re.search(r"\b(?:yes|yeah|yep|correct|right|okay|ok|sure)\b", remainder))
        if negative and not positive:
            return Meaning("choice", "No")
        if positive and not negative:
            return Meaning("choice", "Yes")
        return Meaning("invalid", note="Please say yes or no, or ask to change your order.")
    found = alternatives(text, CHOICES[step])
    if len(found) == 1:
        return Meaning("choice", next(iter(found)))
    if len(found) > 1:
        return Meaning("invalid", note="I heard more than one option. Please choose one.")
    return Meaning("invalid")


@dataclass
class OrderFlow:
    step: str = "drink"
    order: dict = field(default_factory=dict)
    editing: bool = False
    completed: bool = False

    def summary(self):
        if all(k in self.order for k in ("drink", "temperature", "size")):
            return f"One {self.order['size'].lower()} {self.order['temperature'].lower()} {self.order['drink'].lower()}"
        return " / ".join(self.order.values()) or "No selection yet"

    def options(self):
        return {
            "drink": list(DRINKS),
            "temperature": list(TEMPERATURES),
            "size": list(SIZES),
            "confirm": [self.summary(), "Yes / No"],
            "edit": ["Drink", "Temperature", "Size"],
        }[self.step]

    def prompt(self, welcome=False):
        return {
            "drink": ("Welcome! " if welcome else "") +
                     "We have Latte, Cappuccino, and Mocha. Which would you like?",
            "temperature": "Would you like it hot or iced?",
            "size": "What size would you like: small, medium, or large?",
            "confirm": self.summary() + ". Is that correct?",
            "edit": "What would you like to change: the drink, temperature, or size?",
        }[self.step]

    def accept(self, meaning):
        """Called ONLY after A. Returns a clarification, or empty on advancement."""
        if meaning.kind == "price":
            return "Prices are not included in this prototype. " + self.prompt()
        if meaning.kind == "invalid":
            return (meaning.note + " " if meaning.note else "") + self.prompt()
        if self.step == "confirm":
            if meaning.kind == "change":
                self.editing = True
                self.step = meaning.value or "edit"
            elif meaning.value == "Yes":
                self.completed = True
            else:
                self.step = "edit"
                self.editing = True
            return ""
        if self.step == "edit":
            self.step = meaning.value
            self.editing = True
            return ""
        self.order[self.step] = meaning.value
        if self.editing:
            self.step = "confirm"
            self.editing = False
        else:
            self.step = {"drink": "temperature", "temperature": "size", "size": "confirm"}[self.step]
        return ""


class ButtonGate:
    """Release-to-arm + debounce. Simultaneous buttons disarm the gate."""
    def __init__(self, debounce=0.06):
        self.debounce = debounce
        self.last = None
        self.since = 0.0
        self.armed = False

    def update(self, a_pressed, b_pressed, now):
        state = (a_pressed, b_pressed)
        if state != self.last:
            self.last, self.since = state, now
            if state == (True, True):
                self.armed = False
            return None
        if now - self.since < self.debounce:
            return None
        if state == (False, False):
            self.armed = True
        elif self.armed and state in {(True, False), (False, True)}:
            self.armed = False
            return "A" if state[0] else "B"
        return None


class TurnClock:
    """No-answer timeout applies before speech only, not to thinking pauses."""
    def __init__(self, reply_timeout, max_utterance):
        self.reply_timeout = reply_timeout
        self.max_utterance = max_utterance
        self.elapsed = 0.0
        self.speech_start = None

    def advance(self, seconds, speech_detected):
        self.elapsed += seconds
        if speech_detected and self.speech_start is None:
            self.speech_start = self.elapsed
        if self.speech_start is None:
            return "timeout" if self.elapsed >= self.reply_timeout else None
        return "too_long" if self.elapsed - self.speech_start >= self.max_utterance else None


class Journal:
    def __init__(self, root):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.path = root / stamp
        self.path.mkdir(parents=True)
        self.file = (self.path / "events.jsonl").open("a", encoding="utf-8")
        self.started = time.monotonic()
        self.turn = 0

    def emit(self, event, **data):
        record = {"time": datetime.now(timezone.utc).isoformat(),
                  "elapsed_s": round(time.monotonic() - self.started, 3),
                  "event": event, **data}
        self.file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.file.flush()
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def close(self):
        self.file.close()


class TerminalUI:
    def show(self, status, body, candidate="", footer=""):
        print(f"\n[{status}]\n" + "\n".join(body))
        if candidate:
            print(candidate)
        if footer:
            print(footer)

    def review(self, heard, meaning):
        self.show("Check answer", [heard], meaning.label, "A: Confirm / B: Retry")
        while True:
            button = input("Operator [A/B]: ").strip().upper()
            if button in {"A", "B"}:
                return button

    def close(self):
        pass


class PiUI:
    """Same SPI pins, offsets and 90-degree rotation as Lab 2 plant_clock.py."""
    def __init__(self):
        import board
        import digitalio
        from PIL import Image, ImageDraw, ImageFont
        import adafruit_rgb_display.st7789 as st7789

        self.Image, self.ImageDraw = Image, ImageDraw
        self.pins = []
        self.spi = None
        self.backlight = None
        self.closed = False
        try:
            def pin(number):
                item = digitalio.DigitalInOut(number)
                self.pins.append(item)
                return item
            cs, dc = pin(board.D5), pin(board.D25)
            self.spi = board.SPI()
            self.display = st7789.ST7789(
                self.spi, cs=cs, dc=dc, rst=None, baudrate=64000000,
                width=135, height=240, x_offset=53, y_offset=40)
            self.backlight = pin(board.D22)
            self.backlight.switch_to_output(value=True)
            self.a, self.b = pin(board.D23), pin(board.D24)
            self.a.switch_to_input(pull=digitalio.Pull.UP)
            self.b.switch_to_input(pull=digitalio.Pull.UP)
            fonts = Path("/usr/share/fonts/truetype/dejavu")
            self.font = ImageFont.truetype(str(fonts / "DejaVuSans.ttf"), 14)
            self.small = ImageFont.truetype(str(fonts / "DejaVuSans.ttf"), 11)
            self.title = ImageFont.truetype(str(fonts / "DejaVuSans-Bold.ttf"), 17)
            self.canvas = Image.new("RGB", (240, 135), "black")
            self.draw = ImageDraw.Draw(self.canvas)
        except BaseException:
            self.close()
            raise

    def wrap(self, text, font, width=226):
        lines, line = [], ""
        for word in text.split():
            proposal = (line + " " + word).strip()
            if self.draw.textlength(proposal, font=font) <= width:
                line = proposal
                continue
            if line:
                lines.append(line)
            line = ""
            for char in word:
                if self.draw.textlength(line + char, font=font) > width:
                    lines.append(line)
                    line = ""
                line += char
        if line:
            lines.append(line)
        return lines or [""]

    def pages(self, body):
        lines = [line for text in body for line in self.wrap(str(text), self.font)]
        return [lines[i:i + 3] for i in range(0, len(lines), 3)] or [[]]

    def show(self, status, body, candidate="", footer="", page=0):
        pages = self.pages(body)
        current = page % len(pages)
        self.draw.rectangle((0, 0, 239, 134), fill="black")
        color = {"Listening": "#66dd99", "Processing": "#ffcc66",
                 "Speaking": "#88bbff"}.get(status, "white")
        self.draw.text((7, 2), status, font=self.title, fill=color)
        self.draw.line((6, 26, 233, 26), fill="#444444")
        for index, line in enumerate(pages[current]):
            self.draw.text((7, 31 + index * 19), line, font=self.font, fill="white")
        if len(pages) > 1:
            self.draw.text((200, 86), f"{current+1}/{len(pages)}", font=self.small, fill="#999999")
        self.draw.text((7, 99), candidate, font=self.small, fill="#ffcc66")
        self.draw.text((7, 117), footer, font=self.small, fill="#88bbff")
        self.display.image(self.canvas.rotate(90, expand=True))

    def review(self, heard, meaning):
        gate = ButtonGate()
        start = time.monotonic()
        previous_page = None
        while True:
            now = time.monotonic()
            page = int((now - start) / 2.5) % len(self.pages([heard]))
            if page != previous_page:
                self.show("Check answer", [heard], meaning.label,
                          "A: Confirm   B: Retry", page=page)
                previous_page = page
            result = gate.update(not self.a.value, not self.b.value, now)
            if result:
                return result
            time.sleep(0.01)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.backlight is not None:
            try:
                self.backlight.value = False
            except Exception:
                pass
        for pin in reversed(self.pins):
            try:
                pin.deinit()
            except Exception:
                pass
        if self.spi is not None:
            try:
                self.spi.deinit()
            except Exception:
                pass


@dataclass
class Heard:
    status: str
    text: str = ""


class SimulatedSpeech:
    """No hardware/model dependencies; input supplies the ASR transcript."""
    def say(self, text, playing=None):
        if playing:
            playing()
        print("Piper would say:", text)

    def listen(self, processing, listening=None):
        if listening:
            listening()
        text = input("Customer transcript (:silence / :fail / :long): ").strip()
        if text == ":silence":
            return Heard("timeout")
        if text == ":long":
            return Heard("too_long")
        processing()
        return Heard("empty") if text in {"", ":fail"} else Heard("ok", text)

    def close(self):
        pass


class PiSpeech:
    def __init__(self, config, journal):
        import numpy as np
        import sherpa_onnx
        import sounddevice as sd
        from faster_whisper import WhisperModel
        from piper import PiperVoice
        self.np, self.sherpa, self.sd = np, sherpa_onnx, sd
        self.cfg, self.journal = config, journal
        self.recording = False
        self.cache = {}
        sd.check_input_settings(device=config["input_device"], channels=1,
                                dtype="float32", samplerate=RATE)
        print("Loading tiny.en / Piper / VAD; the first ASR download may take a while.", flush=True)
        self.recognizer = WhisperModel(config["asr_model"], device="cpu",
                                      compute_type=config["compute_type"])
        self.voice = PiperVoice.load(str(config["voice"]))
        self.vad_config = sherpa_onnx.VadModelConfig()
        self.vad_config.silero_vad.model = str(config["vad_model"])
        self.vad_config.silero_vad.min_silence_duration = config["min_silence"]
        self.vad_config.silero_vad.min_speech_duration = config["min_speech"]
        # Do not let the VAD auto-split a long turn into an accepted answer.
        self.vad_config.silero_vad.max_speech_duration = config["max_utterance"] + 2.0
        self.vad_config.sample_rate = RATE
        self.window = self.vad_config.silero_vad.window_size

    def say(self, text, playing=None):
        if self.recording:
            raise RuntimeError("Internal error: playback attempted with microphone open.")
        if text not in self.cache:
            chunks = []
            rate = None
            for chunk in self.voice.synthesize(text):
                rate = chunk.sample_rate
                chunks.append(self.np.frombuffer(chunk.audio_int16_bytes, dtype=self.np.int16).copy())
            if not chunks:
                raise RuntimeError("Piper produced no audio.")
            self.cache[text] = (self.np.concatenate(chunks), rate)
        audio, rate = self.cache[text]
        if playing:
            playing()
        self.sd.play(audio, samplerate=rate, device=self.cfg["output_device"], blocking=True)
        time.sleep(self.cfg["audio_settle"])

    def listen(self, processing, listening=None):
        # A fresh detector ensures no old speech remains after B, timeout or TTS.
        vad = self.sherpa.VoiceActivityDetector(self.vad_config, buffer_size_in_seconds=60)
        timer = TurnClock(self.cfg["reply_timeout"], self.cfg["max_utterance"])
        utterance = None
        self.recording = True
        try:
            with self.sd.InputStream(
                device=self.cfg["input_device"], samplerate=RATE, channels=1,
                dtype="float32", blocksize=self.window) as stream:
                if listening:
                    listening()
                while True:
                    chunk, overflow = stream.read(self.window)
                    if overflow:
                        # Never silently accept a potentially clipped answer.
                        return Heard("overflow")
                    vad.accept_waveform(chunk.reshape(-1))
                    status = timer.advance(self.window / RATE, vad.is_speech_detected())
                    if status == "too_long":
                        return Heard(status)
                    if not vad.empty():
                        utterance = self.np.array(vad.front.samples, dtype=self.np.float32)
                        vad.pop()
                        break
                    if status == "timeout":
                        return Heard(status)
        finally:
            self.recording = False
        # InputStream has been CLOSED before processing, review or playback.
        processing()
        self.journal.turn += 1
        audio_name = None
        if self.cfg["save_audio"]:
            audio_name = f"answer-{self.journal.turn:03d}.wav"
            pcm = (self.np.clip(utterance, -1, 1) * 32767).astype("<i2")
            with wave.open(str(self.journal.path / audio_name), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(pcm.tobytes())
        started = time.monotonic()
        segments, _ = self.recognizer.transcribe(
            utterance, language="en", beam_size=1, temperature=0.0,
            condition_on_previous_text=False, vad_filter=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        self.journal.emit("transcription", text=text, audio=audio_name,
                          speech_s=round(len(utterance)/RATE, 3),
                          asr_s=round(time.monotonic()-started, 3))
        return Heard("ok", text) if text else Heard("empty")

    def close(self):
        self.sd.stop()


class Application:
    def __init__(self, ui, speech, journal):
        self.ui, self.speech, self.journal = ui, speech, journal
        self.flow = OrderFlow()

    def say(self, text):
        self.journal.emit("prompt", step=self.flow.step, text=text)
        self.ui.show("Processing", self.flow.options())
        self.speech.say(text, lambda: self.ui.show("Speaking", self.flow.options()))

    def run(self):
        prompt = self.flow.prompt(welcome=True)
        while not self.flow.completed:
            self.say(prompt)
            def listening():
                self.ui.show("Listening", self.flow.options())
                self.journal.emit("listening", step=self.flow.step)
            heard = self.speech.listen(
                lambda: self.ui.show("Processing", self.flow.options()), listening)
            if heard.status != "ok":
                self.journal.emit("retry", step=self.flow.step, reason=heard.status)
                prompt = {
                    "timeout": "Would you like more time?",
                    "too_long": "Please give a shorter answer.",
                    "empty": "Please say that again.",
                    "overflow": "I missed part of that. Please say that again.",
                }[heard.status]
                continue
            meaning = interpret(self.flow.step, heard.text)
            self.journal.emit("review", step=self.flow.step,
                              transcript=heard.text, candidate=asdict(meaning))
            button = self.ui.review(heard.text, meaning)
            self.journal.emit("button", button=button, step=self.flow.step)
            if button == "B":
                prompt = "Please say that again."
                continue
            clarification = self.flow.accept(meaning)
            self.journal.emit("accepted", transcript=heard.text,
                              candidate=asdict(meaning), order=dict(self.flow.order),
                              next_step=self.flow.step, completed=self.flow.completed)
            prompt = clarification or self.flow.prompt()
        self.say("Thank you! Please pay at the counter.")
        self.ui.show("Order confirmed", [self.flow.summary(), "Pay at the counter."],
                     footer="Demo complete - no payment taken")
        self.journal.emit("completed", order=dict(self.flow.order),
                          payment_processed=False, order_sent=False)


def load_config(path):
    config = dict(DEFAULTS)
    if path:
        with path.open(encoding="utf-8-sig") as file:
            overrides = json.load(file)
        if not isinstance(overrides, dict):
            raise ValueError("Config must be a JSON object.")
        extra = set(overrides) - set(DEFAULTS)
        if extra:
            raise ValueError("Unknown config keys: " + ", ".join(sorted(extra)))
        config.update(overrides)
    for key in ("min_silence", "min_speech", "reply_timeout", "max_utterance", "audio_settle"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be a positive finite number.")
    if config["max_utterance"] > 45:
        raise ValueError("max_utterance must be <= 45 seconds.")
    if config["min_speech"] >= config["reply_timeout"]:
        raise ValueError("min_speech must be shorter than reply_timeout.")
    if config["min_silence"] >= config["max_utterance"]:
        raise ValueError("min_silence must be shorter than max_utterance.")
    if not isinstance(config["save_audio"], bool):
        raise ValueError("save_audio must be true or false.")
    for key in ("voice", "vad_model", "run_dir"):
        value = Path(config[key]).expanduser()
        config[key] = (HERE / value).resolve() if not value.is_absolute() else value
    return config


def device_arg(value):
    return int(value) if value.isdigit() else value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path,
                        default=HERE / "config.json" if (HERE / "config.json").exists() else None)
    parser.add_argument("--simulate", action="store_true", help="text-only test; no hardware imports")
    parser.add_argument("--list-devices", action="store_true", help="list PortAudio device IDs/names")
    parser.add_argument("--input-device", type=device_arg)
    parser.add_argument("--output-device", type=device_arg)
    parser.add_argument("--save-audio", action="store_true", help="also save utterance WAVs locally")
    parser.add_argument("--check", action="store_true", help="check imports, models and audio settings; no GPIO access")
    args = parser.parse_args(argv)
    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        print("These are PortAudio IDs, not the ALSA card numbers shown by arecord -l.")
        return 0
    cfg = load_config(args.config)
    for key in ("input_device", "output_device"):
        if getattr(args, key) is not None:
            cfg[key] = getattr(args, key)
    if args.save_audio:
        cfg["save_audio"] = True
    if not args.simulate:
        for key in ("voice", "vad_model"):
            if not cfg[key].is_file():
                raise FileNotFoundError(f"{key} missing: {cfg[key]}. Run bash setup_coffee.sh.")
        if not Path(str(cfg["voice"]) + ".json").is_file():
            raise FileNotFoundError("Piper voice .onnx.json is missing. Run bash setup_coffee.sh.")
    if args.check:
        import board
        import digitalio
        import adafruit_rgb_display.st7789
        import PIL
        import sounddevice as sd
        import sherpa_onnx
        import faster_whisper
        import piper
        sd.check_input_settings(device=cfg["input_device"], channels=1,
                                dtype="float32", samplerate=RATE)
        with Path(str(cfg["voice"]) + ".json").open() as file:
            voice_rate = json.load(file)["audio"]["sample_rate"]
        sd.check_output_settings(device=cfg["output_device"], channels=1,
                                 dtype="int16", samplerate=voice_rate)
        print("Imports, model paths and audio formats OK. Screen/buttons still need a real run.")
        return 0
    journal = Journal(cfg["run_dir"])
    ui = speech = None
    try:
        journal.emit("started", simulation=args.simulate, save_audio=cfg["save_audio"])
        ui = TerminalUI() if args.simulate else PiUI()
        ui.show("Loading", ["Speech models...", "Please wait"])
        speech = SimulatedSpeech() if args.simulate else PiSpeech(cfg, journal)
        Application(ui, speech, journal).run()
        if not args.simulate:
            print("Demo complete. Screen stays on until Ctrl+C. Restart for another customer.")
            while True:
                time.sleep(0.2)
        return 0
    except (KeyboardInterrupt, EOFError):
        journal.emit("stopped", reason="operator")
        return 0
    except Exception as exc:
        journal.emit("error", message=str(exc))
        if ui:
            ui.show("Error", ["See terminal details.", "Fix issue and restart."])
        raise
    finally:
        try:
            if speech:
                speech.close()
        finally:
            try:
                if ui:
                    ui.close()
            finally:
                journal.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"\nUnable to continue: {error}", file=sys.stderr)
        print("Check README.md troubleshooting. No order was sent and no payment was taken.",
              file=sys.stderr)
        raise SystemExit(1)
