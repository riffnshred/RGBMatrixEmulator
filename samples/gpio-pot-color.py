#!/usr/bin/env python
"""
GPIO Potentiometer Color Control
---------------------------------
Two potentiometers control the hue and brightness of the display in real time.

Unlike a rotary encoder (which fires edge callbacks), a potentiometer is read
by polling GPIO._get_pot(pin) directly inside the main loop.

emulator_config.json gpio section:
    "gpio": {
        "potentiometers": [
            {
                "pin": 26, "min": 0, "max": 360, "step": 5,
                "key_up": "scrollup", "key_down": "scrolldown",
                "label": "Hue"
            },
            {
                "pin": 27, "min": 0, "max": 100, "step": 2,
                "key_up": "up", "key_down": "down",
                "label": "Brightness"
            }
        ]
    }
"""
import sys
import os
import colorsys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from samplebase import SampleBase

try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO

HUE_PIN    = 26   # 0 – 360  (scroll wheel)
BRIGHT_PIN = 27   # 0 – 100  (up / down arrows)


class GpioPotColor(SampleBase):
    def run(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(HUE_PIN,    GPIO.IN)
        GPIO.setup(BRIGHT_PIN, GPIO.IN)

        canvas = self.matrix.CreateFrameCanvas()
        w = self.matrix.width
        h = self.matrix.height

        # Reserve bottom two rows for the hue bar and brightness bar
        display_h = h - 2

        prev_hue    = -1.0
        prev_bright = -1.0

        try:
            while True:
                # Read both pots — no callback needed, just poll the value
                hue_deg = GPIO._get_pot(HUE_PIN)
                bright  = GPIO._get_pot(BRIGHT_PIN)

                hue = hue_deg / 360.0
                val = bright  / 100.0

                if abs(hue - prev_hue) < 0.002 and abs(bright - prev_bright) < 0.5:
                    time.sleep(0.016)
                    continue

                prev_hue    = hue
                prev_bright = bright

                canvas.Clear()

                # ── Main colour fill ────────────────────────────────────
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, val)
                ir, ig, ib = int(r * 255), int(g * 255), int(b * 255)
                for y in range(display_h):
                    for x in range(w):
                        canvas.SetPixel(x, y, ir, ig, ib)

                # ── Hue rainbow bar (second-to-last row) ────────────────
                bar_y = h - 2
                for x in range(w):
                    hr, hg, hb = colorsys.hsv_to_rgb(x / w, 1.0, 1.0)
                    canvas.SetPixel(x, bar_y, int(hr * 255), int(hg * 255), int(hb * 255))

                # Hue cursor: white tick on the rainbow bar
                cursor_x = int(hue * w) % w
                canvas.SetPixel(cursor_x, bar_y, 255, 255, 255)

                # ── Brightness bar (last row) ───────────────────────────
                bar_y = h - 1
                bar_w = int((bright / 100.0) * w)
                for x in range(w):
                    if x < bar_w:
                        canvas.SetPixel(x, bar_y, 220, 220, 220)
                    else:
                        canvas.SetPixel(x, bar_y, 30, 30, 30)

                canvas = self.matrix.SwapOnVSync(canvas)
                time.sleep(0.016)

        finally:
            GPIO.cleanup([HUE_PIN, BRIGHT_PIN])


if __name__ == "__main__":
    sample = GpioPotColor()
    if not sample.process():
        sample.print_help()
