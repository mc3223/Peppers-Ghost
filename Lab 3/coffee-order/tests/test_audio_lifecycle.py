"""Fake audio streams check ownership/timing without claiming a hardware test."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coffee_order import PiSpeech


class DummyJournal:
    turn = 0
    path = Path("unused")

    def emit(self, *args, **kwargs):
        pass


class Chunk:
    def reshape(self, *_):
        return [0.1] * 512


class AudioLifecycleTests(unittest.TestCase):
    def make_speech(self, scenario):
        speech = PiSpeech.__new__(PiSpeech)
        speech.cfg = {"input_device": None, "reply_timeout": .05,
                      "max_utterance": .05 if scenario == "long" else 20,
                      "save_audio": False}
        speech.journal = DummyJournal()
        speech.window = 512
        speech.vad_config = object()
        speech.recording = False
        state = {"open": False, "reads": 0, "processed": False, "asr": False}
        case = self

        class Stream:
            def __enter__(self):
                state["open"] = True
                return self

            def read(self, _):
                state["reads"] += 1
                return Chunk(), scenario == "overflow"

            def __exit__(self, *args):
                state["open"] = False

        class VAD:
            front = SimpleNamespace(samples=[0.1] * 1024)

            def accept_waveform(self, _):
                pass

            def is_speech_detected(self):
                return scenario in {"ok", "long"}

            def empty(self):
                return not (scenario == "ok" and state["reads"] >= 2)

            def pop(self):
                pass

        def transcribe(*args, **kwargs):
            case.assertFalse(state["open"])
            case.assertFalse(speech.recording)
            case.assertTrue(state["processed"])
            state["asr"] = True
            return iter([SimpleNamespace(text=" Latte ")]), None

        speech.sd = SimpleNamespace(InputStream=lambda **_: Stream())
        speech.sherpa = SimpleNamespace(VoiceActivityDetector=lambda *a, **k: VAD())
        speech.np = SimpleNamespace(array=lambda data, **_: data, float32=float)
        speech.recognizer = SimpleNamespace(transcribe=transcribe)

        def processing():
            self.assertFalse(state["open"])
            self.assertFalse(speech.recording)
            state["processed"] = True

        def listening():
            self.assertTrue(state["open"])
            self.assertTrue(speech.recording)

        return speech, state, processing, listening

    def test_input_closed_before_asr_and_review(self):
        speech, state, processing, listening = self.make_speech("ok")
        result = speech.listen(processing, listening)
        self.assertEqual((result.status, result.text), ("ok", "Latte"))
        self.assertTrue(state["asr"])
        self.assertFalse(state["open"])
        self.assertFalse(speech.recording)

    def test_failure_paths_close_input_and_do_not_transcribe(self):
        for scenario, status in [("silent", "timeout"), ("overflow", "overflow"), ("long", "too_long")]:
            with self.subTest(scenario=scenario):
                speech, state, processing, listening = self.make_speech(scenario)
                result = speech.listen(processing, listening)
                self.assertEqual(result.status, status)
                self.assertFalse(state["open"])
                self.assertFalse(speech.recording)
                self.assertFalse(state["asr"])

    def test_playback_forbidden_while_recording(self):
        speech = PiSpeech.__new__(PiSpeech)
        speech.recording = True
        with self.assertRaises(RuntimeError):
            speech.say("This must not play.")


if __name__ == "__main__":
    unittest.main()
