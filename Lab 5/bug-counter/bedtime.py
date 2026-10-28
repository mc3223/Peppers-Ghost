"""
Bug counter, the hand-off before bed: hold a "quiet spider" over the trap and
the Pi starts the night shift.

    python bedtime.py              # wait for the spider, acknowledge, then run capture.py
    python bedtime.py --show       # same, with a camera window (VNC / Pi Connect) to practise the gesture
    python bedtime.py --no-capture # just the gesture and the acknowledgement, for testing

The quiet spider: an open hand held over the dish, all five fingers straight and
spread wide like legs, for a second and a half. The camera looks straight down,
so this is a rule over MediaPipe's 21 landmarks that works from above.

Acknowledgement: the Pi's green activity LED blinks three times slowly, then goes
dark for the night. Then the script waits for your hand to leave the frame and the
liquid to settle before the first frame, so your hand is never in the start-of-night
reference that count.py uses to tell "already in the trap" from "caught tonight".
"""
import argparse
import math
import os
import subprocess
import sys
import time

import cv2
import mediapipe as mp

parser = argparse.ArgumentParser()
parser.add_argument("--show", action="store_true", help="open a window with the landmarks")
parser.add_argument("--hold", type=float, default=1.5, help="seconds the spider must be held")
parser.add_argument("--settle", type=float, default=30, help="seconds with no hand before recording starts")
parser.add_argument("--no-capture", action="store_true", help="do not start capture.py afterwards")
args = parser.parse_args()

LED = "/sys/class/leds/ACT"


def led(path, value):
    """Write to the LED through sudo (the Pi's default user can sudo without a password)."""
    subprocess.run(["sudo", "tee", f"{LED}/{path}"], input=str(value).encode(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def acknowledge():
    print("quiet spider seen: watching tonight", flush=True)
    if not os.path.exists(LED):
        return
    led("trigger", "none")
    for _ in range(3):
        led("brightness", 1)
        time.sleep(0.6)
        led("brightness", 0)
        time.sleep(0.6)
    # Leave it dark: the device has gone to sleep. The LED's normal trigger comes back on the next boot.


def is_spider(lm):
    """Open hand, all five fingers straight and spread. lm is [[id, x, y], ...] for one hand."""
    p = {i: (x, y) for i, x, y in lm}
    d = lambda a, b: math.dist(p[a], p[b])
    palm = d(0, 9)                                       # wrist to middle knuckle: the hand's scale
    if palm < 20:
        return False
    straight = all(d(0, tip) > d(0, pip) * 1.15 for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)])
    thumb_out = d(4, 5) > 0.6 * palm                     # thumb away from the index knuckle
    spread = all(d(a, b) > 0.35 * palm for a, b in [(4, 8), (8, 12), (12, 16), (16, 20)])
    return straight and thumb_out and spread


cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
if not cap.isOpened():
    raise SystemExit("no webcam found: is it plugged in?")
hands = mp.solutions.hands.Hands(max_num_hands=1, model_complexity=0, min_detection_confidence=0.6)


def landmarks(img, draw=False):
    """[[id, x, y], ...] in pixels for the first hand, or [] (the same shape hand_pose.py uses)."""
    found = hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).multi_hand_landmarks
    if not found:
        return []
    if draw:
        mp.solutions.drawing_utils.draw_landmarks(img, found[0], mp.solutions.hands.HAND_CONNECTIONS)
    h, w = img.shape[:2]
    return [[i, int(p.x * w), int(p.y * h)] for i, p in enumerate(found[0].landmark)]


print("hold a quiet spider over the trap", flush=True)
held_since = None
while True:
    ok, img = cap.read()
    if not ok:
        continue
    lm = landmarks(img, draw=args.show)
    spider = bool(lm) and is_spider(lm)
    held_since = (held_since or time.time()) if spider else None    # the Part E lesson: no flicker
    if args.show:
        label = "quiet spider!" if spider else ("hand" if lm else "")
        cv2.putText(img, label, (20, 40), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 2)
        cv2.imshow("bedtime", img)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            raise SystemExit
    if held_since and time.time() - held_since >= args.hold:
        break

acknowledge()

# Wait for the hand to leave and the liquid to stop moving.
clear_since = time.time()
while time.time() - clear_since < args.settle:
    ok, img = cap.read()
    if ok:
        if landmarks(img):
            clear_since = time.time()
cap.release()
if args.show:
    cv2.destroyAllWindows()

if args.no_capture:
    print("(--no-capture: not starting the night shift)")
    raise SystemExit
print("night shift started", flush=True)
here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
os.execv(sys.executable, [sys.executable, "capture.py"])        # Ctrl-C in the morning stops it as before
