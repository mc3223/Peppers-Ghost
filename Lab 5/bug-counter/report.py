"""
Bug counter, the morning reveal: count the night, then have Qwen say it in three
friendly sentences.

    python report.py                  # runs count.py first if the counts are older than the night
    python report.py --model qwen3:0.6b

The counting is done by count.py, never by the model: Part D showed a 0.8B model
invents facts, and Part E showed it turns a jittery log into "14 people". Qwen
only gets the finished numbers and is asked to put them into words. The facts line
is printed first, so the report can be checked against it, and a night with no
catches gets a plain sentence without asking the model at all.

Writes morning_report.txt.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--model", default="qwen3.5:0.8b")
args = parser.parse_args()

if not os.path.exists("count_result.json") or os.path.getmtime("count_result.json") < os.path.getmtime("capture_log.jsonl"):
    print("counting the night...", flush=True)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "count.py"), "--step", "6"], check=True, stdout=subprocess.DEVNULL)
night = json.load(open("count_result.json"))

start, end = night["start"][11:16], night["end"][11:16]
arrivals = ", ".join(c["arrived"] for c in night["catches"])
facts = (f"Watched {start}-{end}. Caught {night['caught']}" + (f" (at {arrivals})" if arrivals else "") +
         f". Already in the trap at bedtime: {night['already_in_trap']}."
         f" Lamp off: {night['lamp_off_minutes']} min."         # visits are left out: unverified, mostly dawn flicker
         f" Daylight from {night['daylight_from'] or 'never'}.")
print(facts)

if night["caught"] == 0:
    report = f"Quiet night: the trap watched from {start} to {end} and caught no flies."
    if night["lamp_off_minutes"]:
        report += f" The light was off for {night['lamp_off_minutes']} minutes, so it may have missed some."
else:
    prompt = f"""You are a fruit fly trap on a kitchen counter, reporting on last night. These are the facts,
counted by a camera; they are complete and correct:

{facts}

Write a three-sentence morning report for a sleepy person. Say how many flies were caught and when.
Use only these facts. Do not add flies, times or events that are not listed."""
    t = time.time()
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": args.model, "prompt": prompt, "think": False, "stream": False,
        "options": {"temperature": 0.3, "num_predict": 120},
    }, timeout=600)
    r.raise_for_status()
    report = r.json()["response"].strip()
    print(f"[{args.model}, {time.time() - t:.1f} s]")

print("\n" + report)
with open("morning_report.txt", "w") as f:
    f.write(facts + "\n\n" + report + "\n")
