"""
Bug counter, the morning after: go through the night's frames and count flies
caught in the trap.

    python count.py                    # every frame in capture_log.jsonl
    python count.py --step 6           # every 6th frame (30 s apart): faster, still catches catches
    python count.py --persist 20       # a spot must stay 20 min to count as caught

How it works:
  1. The liquid is the yellowest part of the first frame; everything else is ignored.
  2. In each frame, a black-hat filter finds small spots darker than their surroundings.
     It compares each pixel with its neighbourhood, so dawn brightening the whole dish
     does not look like a fly. Bright glare (the lamp's reflection) and a ring around
     it are skipped, since its edges look like dark spots.
  3. Spots are tracked by position. One that stays at least --persist minutes is a
     catch; one seen in two or more frames in a row that leaves sooner is a visit;
     a single-frame spot is noise. Spots already there in the first two minutes
     were floating at bedtime, and are reported as already_in_trap, not caught.

Writes count_result.json (catches, visits, light) and count_result.jpg (the last
frame with each catch circled and labelled with the time it arrived).
"""
import argparse
import datetime
import json
import statistics

import cv2
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--log", default="capture_log.jsonl")
parser.add_argument("--step", type=int, default=1, help="use every Nth frame")
parser.add_argument("--persist", type=float, default=10, help="minutes a spot must stay to count as caught")
parser.add_argument("--dark", type=int, default=20, help="how much darker than its surroundings a spot must be")
parser.add_argument("--min-area", type=int, default=30, help="smallest spot in pixels")
parser.add_argument("--max-area", type=int, default=1500, help="largest spot in pixels")
args = parser.parse_args()

rows = [json.loads(line) for line in open(args.log)]
for r in rows:
    r["t"] = datetime.datetime.fromisoformat(r["t"])
step_s = statistics.median((b["t"] - a["t"]).total_seconds() for a, b in zip(rows, rows[1:]))
# A track may miss a few looks: a fly that just landed struggles and blurs in and out.
max_gap = max(datetime.timedelta(seconds=step_s * args.step * 3), datetime.timedelta(minutes=3))

# 1. The liquid mask, from the first frame: the vinegar is yellower than the dish (Lab b*).
#    Colour balance and the lamp change from night to night, so Otsu picks the cutoff.
ref = cv2.imread(rows[0]["frame"])
yellow = cv2.GaussianBlur(cv2.cvtColor(ref, cv2.COLOR_BGR2LAB)[..., 2], (15, 15), 0)
_, liquid = cv2.threshold(yellow, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
liquid = cv2.morphologyEx(liquid, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
n, labels, stats, _ = cv2.connectedComponentsWithStats(liquid)
biggest = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
# A fly already floating at the edge is not amber and would bite a notch out of the
# liquid, hiding itself; the liquid is an oval, so fill out to its convex outline.
contours, _ = cv2.findContours((labels == biggest).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
mask = cv2.fillPoly(np.zeros_like(yellow), [cv2.convexHull(max(contours, key=cv2.contourArea))], 1)
mask = cv2.erode(mask, np.ones((11, 11), np.uint8))   # stay just off the rim; flies land near it

kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
glare_ring = np.ones((61, 61), np.uint8)


def spots(gray):
    """Small dark spots in the liquid, as (x, y, area)."""
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    glare = (gray > np.median(gray[mask > 0]) + 35).astype(np.uint8)
    usable = mask & (1 - cv2.dilate(glare, glare_ring))
    found = ((blackhat > args.dark) & (usable > 0)).astype(np.uint8)
    n, _, st, centers = cv2.connectedComponentsWithStats(found)
    return [(cx, cy, st[i, cv2.CC_STAT_AREA]) for i, (cx, cy) in enumerate(centers) if i
            and args.min_area <= st[i, cv2.CC_STAT_AREA] <= args.max_area]


# 2 + 3. Find spots in every frame and follow them.
tracks = []     # each: x, y, first, last, hits
for r in rows[::args.step]:
    gray = cv2.imread(r["frame"], cv2.IMREAD_GRAYSCALE)
    if gray is None:
        continue
    for x, y, _ in spots(gray):
        near = [k for k in tracks if r["t"] - k["last"] <= max_gap and abs(k["x"] - x) < 30 and abs(k["y"] - y) < 30]
        if near:
            k = near[0]
            k.update(x=x, y=y, last=r["t"], hits=k["hits"] + 1)     # floating flies drift slowly
        else:
            tracks.append({"x": x, "y": y, "first": r["t"], "last": r["t"], "hits": 1})

# Light: when was it dark (lamp off), when did daylight arrive?
night = statistics.median(r["brightness"] for r in rows[:round(600 / step_s)])     # the lamp alone, at bedtime
lamp_off = [r["t"] for r in rows if r["brightness"] < night * 0.5]
# Dawn: the next 5 minutes are brighter on average. Clouds make dawn flicker, and a
# lamp switched on for a moment is a blip, so neither single frames nor "bright
# for 10 minutes straight" work.
win = round(300 / step_s)
daylight = next((r["t"] for i, r in enumerate(rows)
                 if statistics.median(x["brightness"] for x in rows[i:i + win]) > night + 2), None)

# Daylight puts the window's reflection in the liquid, and its edges look like flies,
# so anything that first appears after daylight is reported as unsure, not caught.
# Spots there from the first couple of minutes were already floating at bedtime: not tonight's catch.
persist = datetime.timedelta(minutes=args.persist)
start_grace = rows[0]["t"] + datetime.timedelta(minutes=2)
lasting = [k for k in tracks if k["last"] - k["first"] >= persist]
already = [k for k in lasting if k["first"] <= start_grace]
lasting = [k for k in lasting if k["first"] > start_grace]
catches = [k for k in lasting if not daylight or k["first"] < daylight]
unsure = [k for k in lasting if daylight and k["first"] >= daylight]
visits = [k for k in tracks if k["last"] - k["first"] < persist and k["hits"] >= 2]

hhmm = lambda t: t.strftime("%H:%M")
result = {
    "start": rows[0]["t"].isoformat(timespec="minutes"),
    "end": rows[-1]["t"].isoformat(timespec="minutes"),
    "frames": len(rows),
    "already_in_trap": len(already),
    "caught": len(catches),
    "catches": [{"arrived": hhmm(k["first"]), "x": int(k["x"]), "y": int(k["y"])} for k in catches],
    "unsure_after_daylight": [{"appeared": hhmm(k["first"]), "x": int(k["x"]), "y": int(k["y"])} for k in unsure],
    "visits": len(visits),
    "visit_times": [hhmm(k["first"]) for k in visits],
    "lamp_off_minutes": round(len(lamp_off) * step_s / 60),
    "daylight_from": hhmm(daylight) if daylight else None,
}
json.dump(result, open("count_result.json", "w"), indent=2)

last = cv2.imread(rows[-1]["frame"])
for k in catches:
    c = (int(k["x"]), int(k["y"]))
    cv2.circle(last, c, 22, (0, 0, 255), 2)
    cv2.putText(last, hhmm(k["first"]), (c[0] + 26, c[1] + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
cv2.imwrite("count_result.jpg", last)

print(json.dumps(result, indent=2))
