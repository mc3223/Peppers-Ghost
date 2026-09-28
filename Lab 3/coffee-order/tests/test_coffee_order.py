"""Run with python -m unittest discover -s tests -v (no Pi needed)."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import tempfile
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coffee_order import (
    Application, ButtonGate, Heard, Meaning, OrderFlow, TurnClock,
    interpret, load_config,
)


class ParserTests(unittest.TestCase):
    def test_three_drinks(self):
        for drink in ("Latte", "Cappuccino", "Mocha"):
            self.assertEqual(interpret("drink", f"I would like a {drink}.").value, drink)

    def test_explicit_correction(self):
        self.assertEqual(interpret("size", "Medium... actually, large.").value, "Large")
        self.assertEqual(interpret("temperature", "Hot, I mean iced.").value, "Iced")
        self.assertEqual(interpret("drink", "Latte, actually cappuccino.").value, "Cappuccino")

    def test_ambiguous_or_negated_choices(self):
        for step, text in [
            ("size", "Small or medium"), ("size", "not large"),
            ("temperature", "not hot"), ("drink", "Latte and Mocha"),
            ("drink", "Tea please"), ("drink", "Two lattes"), ("drink", "Latte or tea"),
            ("size", "Latte"), ("confirm", "yes no"), ("confirm", ""),
        ]:
            with self.subTest(text=text):
                self.assertEqual(interpret(step, text).kind, "invalid")

    def test_yes_and_no(self):
        for text in ("yes", "yes that's correct", "correct", "that is right"):
            self.assertEqual(interpret("confirm", text).value, "Yes")
        for text in ("no", "nope", "that is not correct", "that's not right", "incorrect"):
            self.assertEqual(interpret("confirm", text).value, "No")

    def test_change_request(self):
        meaning = interpret("confirm", "No, change the size.")
        self.assertEqual((meaning.kind, meaning.value), ("change", "size"))

    def test_price_question_is_not_an_order(self):
        self.assertEqual(interpret("drink", "How much is a latte?").kind, "price")
        self.assertEqual(interpret("size", "What is the price?").kind, "price")


class FlowTests(unittest.TestCase):
    def complete_to_review(self):
        flow = OrderFlow()
        for answer in ("Latte", "Iced", "Large"):
            flow.accept(interpret(flow.step, answer))
        return flow

    def test_main_flow_has_no_add_item_or_price(self):
        flow = self.complete_to_review()
        self.assertEqual(flow.step, "confirm")
        self.assertEqual(flow.summary(), "One large iced latte")
        self.assertNotIn("price", flow.prompt().lower())
        flow.accept(interpret("confirm", "yes"))
        self.assertTrue(flow.completed)

    def test_no_opens_edit_then_returns_to_confirmation(self):
        flow = self.complete_to_review()
        flow.accept(interpret("confirm", "no"))
        self.assertEqual(flow.step, "edit")
        flow.accept(interpret("edit", "size"))
        self.assertEqual(flow.step, "size")
        flow.accept(interpret("size", "Small"))
        self.assertEqual(flow.step, "confirm")
        self.assertEqual(flow.order, {"drink": "Latte", "temperature": "Iced", "size": "Small"})

    def test_direct_change_preserves_other_fields(self):
        flow = self.complete_to_review()
        flow.accept(interpret("confirm", "change the temperature"))
        flow.accept(interpret("temperature", "hot"))
        self.assertEqual(flow.step, "confirm")
        self.assertEqual(flow.order["temperature"], "Hot")
        self.assertEqual(flow.order["size"], "Large")

    def test_invalid_and_price_do_not_advance(self):
        flow = OrderFlow()
        for text in ("Tea", "Latte or Mocha", "How much?"):
            before = deepcopy(flow)
            self.assertTrue(flow.accept(interpret(flow.step, text)))
            self.assertEqual(flow, before)


class GateTests(unittest.TestCase):
    def test_press_at_entry_is_ignored_until_release(self):
        gate = ButtonGate()
        self.assertIsNone(gate.update(True, False, 0))
        self.assertIsNone(gate.update(True, False, .2))
        gate.update(False, False, .3)
        gate.update(False, False, .4)
        gate.update(True, False, .5)
        self.assertEqual(gate.update(True, False, .6), "A")
        self.assertIsNone(gate.update(True, False, .8))

    def test_bounce_and_both_buttons(self):
        gate = ButtonGate()
        gate.update(False, False, 0)
        gate.update(False, False, .1)
        gate.update(True, False, .2)
        gate.update(False, False, .22)
        self.assertIsNone(gate.update(False, False, .23))
        gate.update(True, True, .4)
        self.assertIsNone(gate.update(True, True, .5))
        gate.update(False, True, .6)
        self.assertIsNone(gate.update(False, True, .7))
        gate.update(False, False, .8)
        gate.update(False, False, .9)
        gate.update(False, True, 1.0)
        self.assertEqual(gate.update(False, True, 1.1), "B")


class TimingTests(unittest.TestCase):
    def test_initial_silence_times_out(self):
        clock = TurnClock(5, 20)
        self.assertIsNone(clock.advance(4.9, False))
        self.assertEqual(clock.advance(.2, False), "timeout")

    def test_speech_start_cancels_initial_reply_timer(self):
        clock = TurnClock(5, 20)
        clock.advance(4.8, False)
        self.assertIsNone(clock.advance(.1, True))
        self.assertIsNone(clock.advance(3, False))

    def test_long_speech_rejected(self):
        clock = TurnClock(5, 20)
        clock.advance(.1, True)
        self.assertEqual(clock.advance(20.1, True), "too_long")


class FakeJournal:
    def __init__(self):
        self.events = []

    def emit(self, event, **data):
        self.events.append((event, deepcopy(data)))


class FakeUI:
    def __init__(self, buttons):
        self.buttons = iter(buttons)
        self.screens = []
        self.reviews = []

    def show(self, *args, **kwargs):
        self.screens.append((args, kwargs))

    def review(self, heard, meaning):
        self.reviews.append((heard, meaning))
        return next(self.buttons)


class FakeSpeech:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.prompts = []

    def say(self, text, playing=None):
        if playing:
            playing()
        self.prompts.append(text)

    def listen(self, processing, listening=None):
        if listening:
            listening()
        processing()
        answer = next(self.answers)
        return answer if isinstance(answer, Heard) else Heard("ok", answer)


class ApplicationTests(unittest.TestCase):
    def run_flow(self, answers, buttons):
        speech, ui, journal = FakeSpeech(answers), FakeUI(buttons), FakeJournal()
        app = Application(ui, speech, journal)
        app.run()
        return app, speech, ui, journal

    def test_b_discards_current_candidate_without_losing_prior_order(self):
        app, speech, ui, journal = self.run_flow(
            ["Latte", "Hot", "Iced", "Large", "Yes"], ["A", "B", "A", "A", "A"])
        self.assertEqual(app.flow.order, {"drink": "Latte", "temperature": "Iced", "size": "Large"})
        accepted = [data for name, data in journal.events if name == "accepted"]
        self.assertFalse(any(x["order"].get("temperature") == "Hot" for x in accepted))
        self.assertEqual(len(ui.reviews), 5)
        self.assertIn("Please say that again.", speech.prompts)

    def test_silence_failure_and_unsupported_answer_never_advance(self):
        app, speech, ui, journal = self.run_flow(
            [Heard("timeout"), Heard("empty"), "Tea", "Mocha", "Hot", "Medium", "Yes"],
            ["A", "A", "A", "A", "A"])
        self.assertTrue(app.flow.completed)
        self.assertEqual(app.flow.order["drink"], "Mocha")
        self.assertIn("Would you like more time?", speech.prompts)
        # No operator button is consumed for silence or failed ASR.
        self.assertEqual(len(ui.reviews), 5)

    def test_customer_no_is_not_operator_b(self):
        app, speech, ui, journal = self.run_flow(
            ["Latte", "Hot", "Large", "No", "Size", "Small", "Yes"], ["A"] * 7)
        self.assertEqual(app.flow.order["size"], "Small")
        self.assertEqual(journal.events[-1][0], "completed")
        self.assertFalse(journal.events[-1][1]["payment_processed"])
        self.assertFalse(journal.events[-1][1]["order_sent"])

    def test_prices_are_not_included(self):
        app, speech, ui, journal = self.run_flow(
            ["How much?", "Cappuccino", "Hot", "Small", "Yes"], ["A"] * 5)
        self.assertEqual(app.flow.order["drink"], "Cappuccino")
        self.assertTrue(any("Prices are not included" in p for p in speech.prompts))
        self.assertFalse(any("anything else" in p.lower() for p in speech.prompts))

    def test_acceptance_is_required_even_for_customer_yes(self):
        app, speech, ui, journal = self.run_flow(
            ["Mocha", "Iced", "Small", "Yes", "No", "size", "Large", "Yes"],
            ["A", "A", "A", "B", "A", "A", "A", "A"])
        self.assertEqual(app.flow.order["size"], "Large")


class ConfigTests(unittest.TestCase):
    def test_invalid_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for value in (-1, 0, True, "0.8"):
                path.write_text(json.dumps({"min_silence": value}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_unknown_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"input_devce": 3}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
