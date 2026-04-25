#!/usr/bin/env python
"""
GPIO Button Counter
-------------------
Demonstrates a simple push-button wired to GPIO pin 17.
Each press increments a counter displayed on the matrix.

emulator_config.json gpio section:
    "gpio": {
        "buttons": [{"key": "space", "pin": 17}]
    }

On real hardware pin 17 is pulled up; pressing the button pulls it LOW (FALLING edge).
In the emulator the shim fires RISING on press, FALLING on release — we count RISING.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from samplebase import SampleBase

try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO

try:
    from rgbmatrix import graphics  # type: ignore[import]
except ImportError:
    from RGBMatrixEmulator import graphics


BUTTON_PIN = 17

_count = 0


def _on_press(channel):
    global _count
    _count += 1


class GpioButtonCounter(SampleBase):
    def run(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=_on_press, bouncetime=200)

        canvas = self.matrix.CreateFrameCanvas()
        font = graphics.Font()
        font.LoadFont(os.path.join(os.path.dirname(__file__), "fonts/7x13.bdf"))

        color_label = graphics.Color(180, 180, 180)
        color_value = graphics.Color(0, 220, 80)

        try:
            last = -1
            while True:
                if _count != last:
                    last = _count
                    canvas.Clear()
                    graphics.DrawText(canvas, font, 2, 12, color_label, "Presses:")
                    graphics.DrawText(canvas, font, 2, 26, color_value, str(_count))
                    canvas = self.matrix.SwapOnVSync(canvas)
        finally:
            GPIO.cleanup(BUTTON_PIN)


if __name__ == "__main__":
    sample = GpioButtonCounter()
    if not sample.process():
        sample.print_help()
