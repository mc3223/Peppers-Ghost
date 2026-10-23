# Observant Systems: Overnight Sensation

**Max Corkran**

For lab this week, we focus on creating interactive systems that can detect and respond to events or stimuli in the environment of the Pi, like the Boat Detector we mentioned in lecture. 
Your **observant device** could, for example, count items, find objects, recognize an event or continuously monitor a room.

This lab will help you think through the design of observant systems, particularly corner cases that the algorithms need to be aware of.

**New this year: the AI runs on the Pi.** Your Pi 5 can run an object detector ([YOLO](https://docs.ultralytics.com/)) and a small language model ([Qwen](https://ollama.com/library/qwen3.5) through [Ollama](https://ollama.com)) completely offline. In Part 1 you get both running and connect them: YOLO *sees*, Qwen *reasons* about what was seen. These models are slow, but they have all night. In Part 2 you use them to design a **night-time interaction**: what you tell the device before bed, what it does while you sleep, and what it shows you when you wake up.

**Collaborators and influences:** Claude (Anthropic's AI assistant, via Claude Code) helped set up the Pi, wrote the bug counter's capture and counting scripts with me, and drafted parts of this writeup from my results.

## Overview

**Part 1: the tools**

A) [Set up your Pi for on-device AI](#part-a)

B) [See: recognize people in real time with YOLO](#part-b)

C) [See more: hands and pose with MediaPipe](#part-c)

D) [Reason: run Qwen on the Pi with Ollama](#part-d)

E) [Connect: from YOLO readings to Qwen reasoning](#part-e)

**Part 2: Overnight Sensation**

F) [Read Part 2 and storyboard your night-time interaction](#part-f)

G) [Design the interaction before bed](#part-g)

H) [Incorporate the observant system during sleep](#part-h)

I) [Design the interaction when awake](#part-i)

The tools from earlier versions of this lab (MobileNet, Teachable Machine, Moondream, audio analysis, classic OpenCV) live in the [legacy folder](legacy/README.md). They are optional, but any of them can be the sensor in your Part 2 system.


## Prep for Part 1

Please check the instructions in [prep.md](prep.md) and complete them before lab. The installs in Part A take a while, so prep.md also tells you how to get a head start.

## The Report

This readme.md page in your own repository should be edited to include the work you have done. You can delete everything but the headers and the sections between the \*\*\***stars**\*\*\*. Write the answers to the questions under the starred sentences. Include any material that explains what you did in this lab hub folder, and link it in the readme.

---

# Part 1

## Part A. Set up your Pi for on-device AI

Everything from Part A is installed on a Pi 5 (8 GB): a Python venv with the requirements, YOLO26-nano exported to NCNN, and Ollama with both Qwen models.

```
NAME            ID              SIZE      MODIFIED
qwen3:0.6b      7df6b6e09427    522 MB    36 seconds ago
qwen3.5:0.8b    de63045f2975    1.3 GB    About a minute ago
```

(`ollama list`, saved in [part-a/ollama_list.txt](part-a/ollama_list.txt).)

YOLO on the test image found 4 people and the bus in 137 ms, and on my own snapshot found me at 0.92 confidence in 66 ms:

<img src="part-a/yolo_bus.jpg" width="300"> <img src="part-a/yolo_snap.jpg" width="400">

Setup notes for anyone else doing this:
* On aarch64, `pip install ultralytics` pulls the CUDA build of torch, which downloads several GB of NVIDIA libraries the Pi can't use. Installing the CPU wheels first (`--index-url https://download.pytorch.org/whl/cpu`) avoids it.
* Campus wifi gave the Pi ~100–200 KB/s, so Qwen alone would have taken hours. Downloading big wheels on my laptop and `scp`-ing them to the Pi was about 10x faster; the rest finished at home.
* Ollama's installer tried to pull the models before its own service had started; rerunning `ollama pull` fixed it.
* `yolo predict ... project=runs` still wrote to `runs/detect/runs/...` at the top of the repo with this version of ultralytics.


## Part B. See: recognize people in real time with YOLO

* [Person detection video](media/partB-person-detection.mp4)
* [All 80 classes (`--all`) video](media/partB-all-classes.mp4)

**People-only detection:** YOLO found me at 0.85 when my face and shoulders were in frame. More interesting was what it did *not* call a person: I held up a framed line drawing of a saxophonist and a drummer, two clearly human figures, and it reported 0 objects the whole time. A blurry hand on its own, on the other hand, came up as `person 0.52`. So "person" really means "photo-like body parts", not "anything shaped like a human", which is good for not counting posters and bad if a sleeve or hand is all that's in view.

**`--all`:** pointed at my desk, it got the obvious things right (the desk as `dining table 0.66`, a plate of food as `bowl 0.64`, my arm and sleeve as `person 0.86`) and invented the rest from the closest COCO class it knows: a white holder with red light bulbs became `cup 0.64`, a red bulb on its own became `apple 0.47`, and a pen became `knife 0.51`. The floor, plants and paperwork got nothing. It only knows 80 classes and will always pick one of them.

**`--conf 0.2` / `--conf 0.7`:** didn't make a visible difference in my setup, since the detections I got were mostly either clearly above 0.7 or not there at all.


## Part C. See more: hands and pose with MediaPipe

[Hand pose video](media/partC-hand-pose.mp4)

The hand tracker ran at 6–11 FPS. Pinch-to-volume followed the thumb–index distance (green dot), and Quiet Coyote was recognized reliably and dropped the volume to 0%. It held up even with my hand partly in front of my face. The Pi has no speaker, so the music played silently, but the on-screen meter shows the effect.

**How I'd use pose tracking:** my observant system watches a fruit fly trap (Part 2), so the camera isn't pointed at people at night. Where a hand gesture fits is the *hand-off*: a Quiet Coyote at the camera before bed as the "start watching tonight" signal, and the same gesture in the morning as "show me the report". It's a rule over 21 landmark points, the same way `interpret()` in Part E is a rule over YOLO's boxes, and it needs no button or microphone on the Pi.


## Part D. Reason: run Qwen on the Pi with Ollama

Full output in [part-d-qwen.txt](part-d-qwen.txt).

<details>
<summary>Questions, answers and timings</summary>

**1. "Tell me a bit about the history of Roosevelt Island."** (qwen3.5:0.8b, 32.6 s)
> Roosevelt Island is a historic island in Manhattan, originally built as a military fortification during World War II to protect the harbor from German submarines. It was later converted into an art museum and now serves as a popular tourist destination featuring the famous "Roosevelt Island Ferry," which connects New York City with Queens.

**Same question with qwen3:0.6b** (12.0 s)
> Roosevelt Island, located in the state of New York, was established in 1854 as a temporary refuge for the New York Immigration Board. It was a crucial location for immigrants seeking a stable home and became a significant hub for the community. Today, it remains a symbol of the resilience and diversity of the New York community.

**2. "What is in this photo?"** with `--image snap.jpg` (qwen3.5:0.8b, 119.5 s)
> A man with reddish-brown hair and a black hoodie is making a peace sign against a white ceiling with recessed lights.

**3. "How can I tell a fruit fly from a house fly, and what attracts fruit flies to a kitchen?"** (qwen3.5:0.8b, 14.4 s)
> 1. Fruit flies have long, thin bodies with six legs, while house flies are rounder with eight legs.
> 2. Fruit flies are attracted to sweet food like honey or nectar, whereas house flies seek out human waste for their larvae.
> 3. Fruit flies are often found near fruit and flowers, but house flies prefer warm, dry areas like kitchens.

</details>

**What I took from it:** neither model got a single checkable fact about Roosevelt Island right (Blackwell's Island, Welfare Island, renamed in 1973, Cornell Tech in 2017). The 0.8B model invented a WWII fort and an art museum; the 0.6B model was almost 3x faster and invented a different history. The fly answer is confidently wrong too (house flies have six legs, like every insect). The one good answer was the photo: an accurate description of what was actually in front of it, but it took two minutes.

So the small model is reasonable at describing data you hand it and unreliable at knowing things. That shaped Part 2: Qwen never decides whether there's a fly, it only puts the counter's numbers into words.


## Part E. Connect: from YOLO readings to Qwen reasoning

![The watch log and "asking Qwen..."](media/partE-qwen-answer.png)

Log: [part-e-watch_log.txt](part-e-watch_log.txt)

I was the only person in the room for the whole minute. The log has 24 lines anyway, and Qwen concluded there had been **14 distinct individuals**.

The log explains why. YOLO flickers: in under a second the reading goes `center/close` → `center/far` → `center/close`, it drops to `nobody` mid-sequence (10:21:42, 10:21:56), and twice it briefly saw `2 person(s)` (10:21:33, 10:21:35). Every flicker is a new line, and nothing in the interpreter says "the same person as before", only how many and where. From Qwen's side, two dozen lines about a person could easily mean a dozen people.

This is the README's point that the interpreter decides everything the model can know. Two fixes:
* **Debounce the interpreter:** only log a new reading once it has held for a couple of seconds, so flicker never reaches the log.
* **Ask questions the log can answer:** "how many times did the room go empty?" instead of "how many people?"

My Part 2 counter does the first one: a dark spot only counts as a fly once it has stayed for 10 minutes, and both nights' false alarms (shifting reflections) were exactly this kind of flicker.

---

# Lab 5 Part 2: Overnight Sensation

For Part 2, you will use the observant system from Part 1 to design a night-time interaction. On-device AI is slow, so let it work while you sleep. The person meets the device twice: **before bed**, when they hand the night over, and **when awake**, when the device gives something back. In between, the pipeline from Part E runs on its own.

Two flavors, pick one or mix them:

* **Sense all night.** The Pi watches, listens or measures from bedtime until morning and keeps a log.
* **Process all night.** You already have the data (a day of phone photos, a long recording) and the Pi needs hours to get through it.

Two house rules. Sample rather than stream: one look every 5 to 30 seconds is plenty, and it keeps the Pi cool. And keep everything on the Pi: tell the people you live with, point the camera at things rather than at beds, and delete the snapshots after the demo.

## Part F. 
### Read Part 2 and storyboard your night-time interaction

Storyboard a night-time interaction built on your observant system, in three panels:

1. **Before bed.** How does the person hand the night over, and how does the device acknowledge it?
2. **While asleep.** What does the device watch or work through?
3. **When awake.** What is the one thing the person learns, and in what medium?

Stuck? A kitchen that tells you who raided the fridge. A desk that reports whether you actually went to bed. A window that names the quietest hour. A plant that describes its night. Find something better.

Use storyboards and/or [Verplank diagrams](https://ccrma.stanford.edu/courses/250a-fall-2004/IDSketchbok.pdf).

\*\*\***Insert ideas, sketches, Verplank diagrams and storyboards for your night-time interaction here.**\*\*\*

## Prep for Part 2

1. Look at and give feedback on the Part F storyboards.
   **Put the feedback for your ideas here.**
2. [Update your Lab Hub](prep.md#get-the-latest-content) to get the latest content for Part 2.
3. Decide where the device will spend the night and who else lives there. Get their OK before the first run.
4. Revise your storyboard with the feedback and with what you learned in Part E about where the pipeline breaks.

\*\*\***Post your revised storyboard here.**\*\*\*

## Part G. 
### Design the interaction before

The hand-off: the person tells the device what to watch tonight, and the device acknowledges it. Keep it to a thirty-second ritual. A button or a touch (Lab 4), a spoken sentence (Lab 3), a wave or a Quiet Coyote at the camera (Part C). The acknowledgement can be a line on the display, a tone, or an LED that dims rather than lights up. At its simplest, the hand-off just sets the question that the morning will answer.

\*\*\***Describe the interaction before.**\*\*\*

## Part H. 
### Incorporate the observant system

The Part E pipeline becomes the night shift. `overnight.py` runs your `interpret()` from `yolo_to_qwen.py` every few seconds, people only unless you pass `--all`, and writes the readings to `night_log.jsonl`; the reasoning waits for the morning. Start it inside `tmux` so it keeps running after you close your laptop, and stop it with Ctrl-C in the morning:

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ tmux new -s night
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python overnight.py
```

Fake a night first: run it for thirty seconds while you walk around, stop it, and run `morning.py` from Part I. When that looks right, run a real night. If your storyboard needs a sensor rather than the camera, swap in the Lab 4 example code and log its reading the same way.

\*\*\***Screenshots or videos of the running system.**\*\*\*

## Part I. 
### Design the interaction after

The reveal. The night produced a log; the morning turns it into something a half-awake person can take in. `morning.py` is the smallest version: it asks Qwen for a three-sentence report.

```
(.venv) pi@raspberrypi:~/Interactive-Lab-Hub/Lab 5 $ python morning.py
```

Make it yours: show the report on the Mini PiTFT, read it aloud with Piper from Lab 3, plot the night as a timeline, or ask for JSON (`--json`, Part D) and move a servo. Whatever you pick, make sure it is honest about a night in which nothing happened.

## Final documentation

Document all the prototypes and iterations you have designed and worked on. The deliverables for this lab are writings, sketches, photos, and videos that show what your system:

* "Looks like": how the device sits in the room at night, and what it looks like at bedtime and in the morning.
* "Works like": the pipeline from detector to interpreter to log to reasoner, with a real night's data.
* "Acts like": how a person hands the night over and what they get back.

\*\*\***Include a short video of the whole system**\*\*\*

As always, make sure you document contributions and ideas from others (and AI) explicitly in your writeup.

You are permitted (but not required) to work in groups and share a turn in; you are expected to make equal contribution on any group work you do, and N people's group project should look like N times the work of a single person's lab. Make sure the page for the group turn in is linked to your personal Interactive Lab Hub page.

## Deliverables & Submission for Lab 5

For submission, the readme.md page for this lab should be edited to include the work you have done:
* Upload any materials that explain what you did, including your code and night log, into your Lab 5 repository, and link them in your Lab 5 readme.md.
* Labs are due on Sundays, make sure to submit your Lab 5 readme.md to Canvas.

<details>
  <summary><strong>Submission Cleanup Reminder (Click to Expand)</strong></summary>

  **Before submitting your README.md:**
  - This readme.md file has a lot of extra text for guidance.
  - Remove all instructional text and example prompts from this file.
  - You may either delete these sections or use the toggle/hide feature in VS Code to collapse them for a cleaner look.
  - Your final submission should be neat, focused on your own work, and easy to read for grading.
</details>
