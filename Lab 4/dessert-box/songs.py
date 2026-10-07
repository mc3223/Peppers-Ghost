"""Songs for the dessert box.

Each song is a list of (note, beats). Before cranking, press the crank knob
to switch songs; songs with no notes yet are skipped.

How to write notes
------------------
Note names: letter + octave, e.g. "C5". Middle C is C4. On a treble staff, the
bottom line is E4 and the top line is F5.
Sharps and flats: "F#5", "Bb4", "Eb5".
Rests: ("rest", beats).

Beats (counting a quarter note as 1 beat):
    whole note      4        dotted half      3
    half note       2        dotted quarter   1.5
    quarter note    1        dotted eighth    0.75
    eighth note     0.5      triplet eighth   1/3
    sixteenth note  0.25
    Tied notes: add the lengths together and write one note.
    Repeats and 1st/2nd endings: write the notes out in the order they're played.

Key signature: the flats or sharps at the start of each line apply to every
note on that line or space unless a natural sign cancels them. For example,
three flats (Bb, Eb, Ab) mean every B, E and A is played flat, in every octave.

"transpose" shifts the whole song in semitones. Music boxes sound high and
bell-like, so +12 (one octave up) often sounds more like a real one.
Tempo doesn't matter: the crank sets the speed.
"""

LE_FESTIN = [
    # Fill in from your sheet music, e.g. ("Eb5", 1), ("rest", 1), ...
]

FRERE_JACQUES = [
    ("C5", 1), ("D5", 1), ("E5", 1), ("C5", 1),
    ("C5", 1), ("D5", 1), ("E5", 1), ("C5", 1),
    ("E5", 1), ("F5", 1), ("G5", 2),
    ("E5", 1), ("F5", 1), ("G5", 2),
    ("G5", 0.5), ("A5", 0.5), ("G5", 0.5), ("F5", 0.5), ("E5", 1), ("C5", 1),
    ("G5", 0.5), ("A5", 0.5), ("G5", 0.5), ("F5", 0.5), ("E5", 1), ("C5", 1),
    ("C5", 1), ("G4", 1), ("C5", 2),
    ("C5", 1), ("G4", 1), ("C5", 2),
]

TWINKLE = [
    ("C5", 1), ("C5", 1), ("G5", 1), ("G5", 1), ("A5", 1), ("A5", 1), ("G5", 2),
    ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 1), ("D5", 1), ("C5", 2),
    ("G5", 1), ("G5", 1), ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 2),
    ("G5", 1), ("G5", 1), ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 2),
    ("C5", 1), ("C5", 1), ("G5", 1), ("G5", 1), ("A5", 1), ("A5", 1), ("G5", 2),
    ("F5", 1), ("F5", 1), ("E5", 1), ("E5", 1), ("D5", 1), ("D5", 1), ("C5", 2),
]

# The first song with notes is the one the box starts on.
SONGS = [
    {"name": "Le Festin", "notes": LE_FESTIN, "transpose": 0},
    {"name": "Frere Jacques", "notes": FRERE_JACQUES, "transpose": 0},
    {"name": "Twinkle Twinkle", "notes": TWINKLE, "transpose": 0},
]
