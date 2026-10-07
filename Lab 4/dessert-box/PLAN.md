# Hand-Crank Dessert Box: Setup Plan

A music box for the Feast Automata theme. You turn the crank (rotary encoder) and a melody plays at the speed you crank. While it plays, the servo turns 3D-printed gears so a figure on top spins. When the song ends, the lid opens to reveal a treat. Before cranking, the crank knob switches songs; after, it resets the box.

The code is already written ([`dessert_box.py`](dessert_box.py)). This plan walks through the hardware, one piece at a time. Every step can be tested on its own, and the script skips anything that isn't plugged in yet.

---

## How it works

```
 crank (rotary encoder) ──► Pi ──► speaker: next note when the crank passes it
          │                  ├──► servo ch 0 ──► gears ──► spinning figure (follows song progress)
     knob press = reset      ├──► lid: opens at the end of the song (servo ch 1, or a latch on the gears)
                             └──► OLED: song name + progress bar
```

- **Crank → song.** Every `TICKS_PER_BEAT` encoder clicks is one beat. Crank faster and the song speeds up; stop and it pauses. Cranking backward does nothing, like a real music box.
- **Songs.** [`songs.py`](songs.py) holds the melodies. Press the knob before cranking to switch between them.
- **Song → servo.** The servo angle follows song progress: 0° at the start, 180° at the end. Gears turn that 180° into more rotation for the figure (see step 4).
- **End → lid.** When the last note plays, the lid opens.

---

## Parts

| Part | Connects to | Notes |
|---|---|---|
| Raspberry Pi | power | |
| SparkFun Servo pHAT | Pi header | Needs its own USB-C power for the servo. Don't power servos from the Pi. |
| 9g servo | Servo pHAT channel 0 | Drives the gears |
| Second 9g servo (optional) | Servo pHAT channel 1 | Only if the lid gets its own servo |
| Adafruit rotary encoder (soldered) | Qwiic | The crank |
| Qwiic OLED 128×32 | Qwiic | Optional status screen |
| USB speaker | Pi USB | |
| 3D-printed gears + figure | | See step 4 |
| Cardboard box with hinged lid | | Low-fi housing for Part D |

All Qwiic parts chain together: Pi → encoder → OLED, in any order.

---

## Step 1: Get the code onto the Pi

The Pi's `~/Interactive-Lab-Hub` folder is a copy of your partner's repo, so put this folder somewhere else to avoid mixing up your files and theirs. From your Mac:

```bash
scp -r "Lab 4/dessert-box" pi@10.56.130.46:~/dessert-box
```

Then on the Pi, use the Lab 4 environment that's already set up:

```bash
cd ~/dessert-box
source ~/Interactive-Lab-Hub/Lab\ 4/.venv/bin/activate
```

(Once your partner merges this into their repo, you can run it from `~/Interactive-Lab-Hub/Lab 4/dessert-box` instead.)

## Step 2: Try it without hardware

On your Mac (or the Pi), the simulate mode uses the keyboard as the crank:

```bash
python dessert_box.py --simulate
```

Hold any key to crank, `r` to press the knob (switch songs / reset), `q` to quit. You should hear the music-box notes. This is a good way to tune the song and `TICKS_PER_BEAT` before anything is built.

## Step 3: Bring up each part

Do these in order. After each one, run `python dessert_box.py` and check that the warning for that part goes away.

1. **Rotary encoder.** Solder it if it isn't yet, plug it in with Qwiic, and run `python ~/Interactive-Lab-Hub/Lab\ 4/encoder_test.py`. Turning it should print positions. The box script needs at least the encoder to start.
2. **Speaker.** Plug it into USB, then check it shows up with `aplay -l` (look for a USB card, not just `vc4hdmi`). If notes play out of the wrong output, set the speaker as the default in the Pi's audio settings.
3. **Servo pHAT + servo.** Stack the pHAT on the Pi, plug in its own USB-C power, and connect the servo to channel 0. Run `python ~/Interactive-Lab-Hub/Lab\ 4/pi_servo_hat_test.py`. The servo should sweep.
4. **OLED (optional).** Plug in with Qwiic. For text on the screen, install Pillow once: `pip install pillow`. Without it, the screen shows only the progress bar.

To check what the Pi can see on the Qwiic chain:

```bash
python -c "import board; i=board.I2C(); i.try_lock(); print([hex(a) for a in i.scan()])"
```

Expected addresses: encoder `0x36`, Servo pHAT `0x40`, OLED `0x3c` (or `0x3d`).

## Step 4: Design the gears

The servo only swings 180°, so the gear ratio decides how far the figure turns over one song:

| Servo gear : figure gear | Ratio | Figure turns per song |
|---|---|---|
| 24 : 24 | 1:1 | ½ turn |
| 36 : 18 | 2:1 | 1 turn |
| 48 : 16 | 3:1 | 1½ turns |
| 48 : 12 | 4:1 | 2 turns |

Rule of thumb: figure turns = ratio ÷ 2.

- Keep the gears and figure light. A 9g servo is weak, and higher ratios make it work harder.
- Use the same tooth size (module) on both gears so they mesh. The [Gear Template Generator](https://woodgears.ca/gear_cutting/template.html) from the lab readme can help.
- Mount the servo gear with the servo horn screw. Give the figure gear a fixed axle (a dowel or screw through the box top).

**Lid options:**

- **A. Second servo (simplest).** A servo on channel 1 pushes the lid open. Set `LID_CH = 1` in the script.
- **B. Latch on the gears (one servo).** Put a peg on the figure gear that knocks a latch free at the end of the turn, and let the lid fall or spring open. No code change needed; leave `LID_CH = None`.

## Step 5: Build the housing

Cardboard first, as the lab asks for low-fi prototypes in Part D:

- The crank (encoder) sticks out the side, like a real music box handle. A cardboard or printed handle on the encoder knob makes cranking feel right.
- The figure and gears sit on top, visible.
- The treat goes in a compartment under the lid.
- The OLED sits on the front.
- The Pi, Servo pHAT, and cables go in the bottom, with a hole for the power cables.

## Step 6: Tune the settings

All the settings are at the top of [`dessert_box.py`](dessert_box.py):

| Setting | What it does | What to change |
|---|---|---|
| `TICKS_PER_BEAT` | Cranking needed per beat | Lower if the song takes too long to crank through |
| `FIGURE_START` / `FIGURE_END` | Servo angle range over the song | Shrink if the servo buzzes or hits something at the ends |
| `SERVO_PULSE_MS` | Pulse widths for 0° and 180° | If the servo only moves about 90° when it should move 180°, try `(0.5, 2.5)` |
| `LID_CH`, `LID_CLOSED`, `LID_OPEN` | Lid servo channel and angles | Set to match your lid |

The songs themselves live in [`songs.py`](songs.py), as `(note, beats)` lists. The top of that file explains how to read note names, note lengths, rests, and key signatures off sheet music. **Le Festin** has an empty slot there, ready for its notes; until it has them, the box skips it.

## Step 7: Document for the lab

What the lab readme asks for, and where it comes from:

- **Part D:** 5 sketches of different physical arrangements, the questions they raise, which one you picked and why, and photos/video of the cardboard prototype.
- **Part E:** the code (this folder), video of it working, an interaction diagram (the "How it works" sketch above is a start), and a written reflection.
- **Part F:** "looks like" (housing), "works like" (cranking → music, gears, lid), "acts like" (someone cranking to get their dessert).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Rotary encoder not found at 0x36` | Check the Qwiic cable at both ends; run the I2C scan from step 3 |
| No sound | `aplay -l` should list the USB speaker; check the volume with `alsamixer` |
| Servo jitters or the Pi restarts | The Servo pHAT needs its own USB-C power |
| Servo moves only about half as far as expected | Widen `SERVO_PULSE_MS` (step 6) |
| OLED shows only a bar, no text | `pip install pillow` |
