# plant_clock_light.py
# Raspberry Pi 5 + Adafruit Mini PiTFT 1.14" ST7789
# + APDS9960 Light Sensor
#
# Button A (GPIO23) = PAUSE
# Button B (GPIO24) = RESUME
#
# Light controls Growth Clock speed:
# Dark light   -> minimum 1x
# Normal light -> around 10x
# Strong light -> maximum 100x
#
# Landscape display: 240 x 135

import time
import digitalio
import board

from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
import adafruit_apds9960.apds9960


# ---------------------------
# SPI + Display configuration
# ---------------------------

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
# APDS9960 Light Sensor
# ---------------------------

i2c = board.I2C()

sensor = adafruit_apds9960.apds9960.APDS9960(i2c)

sensor.enable_color = True


# ---------------------------
# Screen configuration
# ---------------------------

WIDTH = 240
HEIGHT = 135

image = Image.new("RGB", (WIDTH, HEIGHT), "black")
draw = ImageDraw.Draw(image)


# ---------------------------
# Fonts
# ---------------------------

try:
    title_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        16
    )

    clock_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        28
    )

    status_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        13
    )

    small_font = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        10
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

paused = False

# Start at normal 10x speed
growth_speed = 10.0

last_time = time.monotonic()


# ---------------------------
# Light variables
# ---------------------------

# Current Clear value
clear_value = 0

# Smoothed Clear value
smoothed_clear = None

# Sensor reading interval
last_sensor_read = 0.0
SENSOR_INTERVAL = 0.20


# ---------------------------
# Button states
# ---------------------------

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
# Convert light to speed
# ---------------------------

def light_to_speed(clear):

    # Calibration based on the actual sensor test:
    #
    # Very dark:
    # Clear around 187
    # -> 1x speed
    #
    # Normal/moderate light:
    # Clear around 5000
    # -> 10x speed
    #
    # Strong light:
    # Clear around 40000
    # -> 100x speed

    DARK_CLEAR = 200
    NORMAL_CLEAR = 5000
    BRIGHT_CLEAR = 40000

    MIN_SPEED = 1.0
    NORMAL_SPEED = 10.0
    MAX_SPEED = 100.0


    # Very dark
    if clear <= DARK_CLEAR:
        return MIN_SPEED


    # Dark -> normal
    elif clear <= NORMAL_CLEAR:

        ratio = (
            (clear - DARK_CLEAR)
            / (NORMAL_CLEAR - DARK_CLEAR)
        )

        speed = MIN_SPEED + ratio * (
            NORMAL_SPEED - MIN_SPEED
        )

        return speed


    # Normal -> bright
    elif clear < BRIGHT_CLEAR:

        ratio = (
            (clear - NORMAL_CLEAR)
            / (BRIGHT_CLEAR - NORMAL_CLEAR)
        )

        speed = NORMAL_SPEED + ratio * (
            MAX_SPEED - NORMAL_SPEED
        )

        return speed


    # Very bright
    else:
        return MAX_SPEED


# ---------------------------
# Send landscape image
# to physical display
# ---------------------------

def show_image():

    rotated_image = image.rotate(90, expand=True)

    display.image(rotated_image)


# ---------------------------
# Draw the screen
# ---------------------------

def draw_screen():

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
        ((WIDTH - title_width) // 2, 3),
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
        ((WIDTH - clock_width) // 2, 27),
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
        ((WIDTH - status_width) // 2, 61),
        status,
        font=status_font,
        fill="white"
    )


    # -----------------------
    # Light + Speed
    # -----------------------

    sensor_text = (
        f"Light: {clear_value}   "
        f"Speed: {growth_speed:.1f}x"
    )

    sensor_box = draw.textbbox(
        (0, 0),
        sensor_text,
        font=small_font
    )

    sensor_width = sensor_box[2] - sensor_box[0]

    draw.text(
        ((WIDTH - sensor_width) // 2, 83),
        sensor_text,
        font=small_font,
        fill="white"
    )


    # -----------------------
    # Button information
    # -----------------------

    draw.text(
        (10, 112),
        "A: PAUSE",
        font=small_font,
        fill="white"
    )

    draw.text(
        (160, 112),
        "B: RESUME",
        font=small_font,
        fill="white"
    )


    show_image()


# ---------------------------
# Main loop
# ---------------------------

print("Light-Controlled Growth Clock Started")
print("Button A (GPIO23): PAUSE")
print("Button B (GPIO24): RESUME")
print("Dark -> 1x")
print("Normal -> around 10x")
print("Bright -> up to 100x")
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
        # Read light sensor
        # -------------------

        if current_time - last_sensor_read >= SENSOR_INTERVAL:

            r, g, b, c = sensor.color_data

            clear_value = c

            # Smooth the sensor reading.
            # This prevents small light fluctuations
            # from changing the speed too quickly.

            if smoothed_clear is None:
                smoothed_clear = float(c)

            else:
                smoothed_clear = (
                    0.8 * smoothed_clear
                    + 0.2 * c
                )

            growth_speed = light_to_speed(
                smoothed_clear
            )

            last_sensor_read = current_time

            print(
                f"Clear: {c:5d} | "
                f"Speed: {growth_speed:6.1f}x"
            )


        # -------------------
        # Read buttons
        # -------------------

        current_A = buttonA.value
        current_B = buttonB.value


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


        previous_A = current_A
        previous_B = current_B


        # -------------------
        # Update Growth Clock
        # -------------------

        if not paused:

            growth_time += (
                delta_time * growth_speed
            )


        # -------------------
        # Update screen
        # -------------------

        draw_screen()

        time.sleep(0.05)


# ---------------------------
# Exit
# ---------------------------

except KeyboardInterrupt:

    print("\nLight-Controlled Growth Clock stopped.")

    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill="black"
    )

    show_image()
