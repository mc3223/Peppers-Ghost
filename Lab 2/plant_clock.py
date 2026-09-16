# growth_clock.py
# Raspberry Pi 5 + Adafruit Mini PiTFT 1.14" ST7789
#
# Button A (GPIO23) = PAUSE
# Button B (GPIO24) = RESUME

import time
import digitalio
import board

from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789


# ---------------------------
# SPI + Display configuration
# ---------------------------

# Keep the same pin configuration as screen_test.py
cs_pin = digitalio.DigitalInOut(board.D5)      # GPIO5
dc_pin = digitalio.DigitalInOut(board.D25)     # GPIO25
reset_pin = None

BAUDRATE = 64000000

spi = board.SPI()

display = st7789.ST7789(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)


# ---------------------------
# Backlight + Buttons
# ---------------------------

backlight = digitalio.DigitalInOut(board.D22)  # GPIO22
backlight.switch_to_output(value=True)

# Button A = PAUSE
buttonA = digitalio.DigitalInOut(board.D23)    # GPIO23
buttonA.switch_to_input(pull=digitalio.Pull.UP)

# Button B = RESUME
buttonB = digitalio.DigitalInOut(board.D24)    # GPIO24
buttonB.switch_to_input(pull=digitalio.Pull.UP)


# ---------------------------
# Screen configuration
# ---------------------------

# The screen is used in landscape orientation
WIDTH = 135
HEIGHT = 240

image = Image.new("RGB", (WIDTH, HEIGHT), "black")
draw = ImageDraw.Draw(image)


# ---------------------------
# Fonts
# ---------------------------

try:
    title_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        18
    )

    clock_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        32
    )

    status_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        16
    )

    small_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        11
    )

except OSError:
    title_font = ImageFont.load_default()
    clock_font = ImageFont.load_default()
    status_font = ImageFont.load_default()
    small_font = ImageFont.load_default()


# ---------------------------
# Growth Clock variables
# ---------------------------

growth_time = 0.0

# False = clock running
# True = clock paused
paused = False

# Normal speed
# Later the light sensor can change this value
growth_speed = 1.0

last_time = time.monotonic()


# ---------------------------
# Button states
# ---------------------------

# Used to detect a new button press
previous_A = True
previous_B = True


# ---------------------------
# Format time
# ---------------------------

def format_time(seconds):

    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ---------------------------
# Draw the screen
# ---------------------------

def draw_screen():

    # Clear previous frame
    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill="black"
    )

    # -----------------------
    # Title
    # -----------------------

    title = "GROWTH CLOCK"

    title_box = draw.textbbox(
        (0, 0),
        title,
        font=title_font
    )

    title_width = title_box[2] - title_box[0]

    draw.text(
        ((WIDTH - title_width) // 2, 5),
        title,
        font=title_font,
        fill="white"
    )


    # -----------------------
    # Clock
    # -----------------------

    clock_text = format_time(growth_time)

    clock_box = draw.textbbox(
        (0, 0),
        clock_text,
        font=clock_font
    )

    clock_width = clock_box[2] - clock_box[0]

    draw.text(
        ((WIDTH - clock_width) // 2, 35),
        clock_text,
        font=clock_font,
        fill="white"
    )


    # -----------------------
    # Status
    # -----------------------

    if paused:
        status = "PAUSED"
    else:
        status = "GROWING"

    status_box = draw.textbbox(
        (0, 0),
        status,
        font=status_font
    )

    status_width = status_box[2] - status_box[0]

    draw.text(
        ((WIDTH - status_width) // 2, 78),
        status,
        font=status_font,
        fill="white"
    )


    # -----------------------
    # Button information
    # -----------------------

    draw.text(
        (10, 110),
        "A: PAUSE",
        font=small_font,
        fill="white"
    )

    draw.text(
        (155, 110),
        "B: RESUME",
        font=small_font,
        fill="white"
    )


    # -----------------------
    # Send image to PiTFT
    # -----------------------

    display.image(image)


# ---------------------------
# Main loop
# ---------------------------

print("Growth Clock Started")
print("Button A (GPIO23): PAUSE")
print("Button B (GPIO24): RESUME")
print("Press Ctrl+C to stop the program.")

try:

    while True:

        # -------------------
        # Calculate real time
        # -------------------

        current_time = time.monotonic()

        delta_time = current_time - last_time

        last_time = current_time


        # -------------------
        # Read buttons
        # -------------------

        current_A = buttonA.value
        current_B = buttonB.value

        # Buttons are active LOW:
        #
        # True  = not pressed
        # False = pressed


        # -------------------
        # Button A -> PAUSE
        # -------------------

        if previous_A and not current_A:

            paused = True

            print("PAUSED")


        # -------------------
        # Button B -> RESUME
        # -------------------

        if previous_B and not current_B:

            paused = False

            print("RESUMED")


        # Remember button states
        previous_A = current_A
        previous_B = current_B


        # -------------------
        # Update Growth Clock
        # -------------------

        if not paused:

            growth_time += delta_time * growth_speed


        # -------------------
        # Update screen
        # -------------------

        draw_screen()


        # Small delay
        time.sleep(0.05)


# ---------------------------
# Exit
# ---------------------------

except KeyboardInterrupt:

    print("\nGrowth Clock stopped.")

    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill="black"
    )

    display.image(image)
