# light_sensor_test.py
# APDS9960 Light Sensor Test
# Raspberry Pi 5

import time
import board
import adafruit_apds9960.apds9960

# Set up I2C
i2c = board.I2C()

# Create APDS9960 sensor
sensor = adafruit_apds9960.apds9960.APDS9960(i2c)

# Enable color/light sensor
sensor.enable_color = True

print("APDS9960 Light Sensor Test")
print("Press Ctrl+C to stop")

try:
    while True:
        # Read color/light data
        r, g, b, c = sensor.color_data

        print(
            f"Clear: {c:5d} | "
            f"Red: {r:5d} | "
            f"Green: {g:5d} | "
            f"Blue: {b:5d}"
        )

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nLight sensor test stopped.")
