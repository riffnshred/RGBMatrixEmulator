#!/usr/bin/env python
"""
GPIO Color Picker
-----------------
Rotary encoder (clk=23, dt=24) cycles through hue.
Encoder push-button (sw=25) resets hue to 0.

emulator_config.json gpio section:
    "gpio": {
        "buttons": [{"key": "r", "pin": 25}],
        "rotary_encoders": [
            {
                "key_cw":  "scrollup",
                "key_ccw": "scrolldown",
                "clk_pin": 23,
                "dt_pin":  24,
                "sw_pin":  25,
                "key_sw":  "r"
            }
        ]
    }
"""
import sys
import os
import colorsys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from samplebase import SampleBase

try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO

CLK_PIN = 23
DT_PIN  = 24
SW_PIN  = 25

_hue = 0.0          # 0.0 – 1.0
_last_clk = None


def _on_rotate(channel):
    global _hue, _last_clk
    clk = GPIO.input(CLK_PIN)
    dt  = GPIO.input(DT_PIN)
    if clk == GPIO.HIGH and _last_clk == GPIO.LOW:
        step = 0.02 if dt == GPIO.HIGH else -0.02
        _hue = (_hue + step) % 1.0
    _last_clk = clk


def _on_reset(channel):
    global _hue
    _hue = 0.0


class GpioColorPicker(SampleBase):
    def run(self):
        global _last_clk

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(CLK_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(DT_PIN,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(SW_PIN,  GPIO.IN, pull_up_down=GPIO.PUD_UP)

        _last_clk = GPIO.input(CLK_PIN)

        GPIO.add_event_detect(CLK_PIN, GPIO.BOTH,    callback=_on_rotate)
        GPIO.add_event_detect(SW_PIN,  GPIO.FALLING, callback=_on_reset, bouncetime=200)

        canvas = self.matrix.CreateFrameCanvas()
        w = self.matrix.width
        h = self.matrix.height

        try:
            prev_hue = -1.0
            while True:
                current_hue = _hue
                if abs(current_hue - prev_hue) > 0.005 or prev_hue < 0:
                    prev_hue = current_hue
                    r, g, b = colorsys.hsv_to_rgb(current_hue, 1.0, 1.0)
                    ir, ig, ib = int(r * 255), int(g * 255), int(b * 255)

                    canvas.Clear()
                    # Fill half the display with the selected colour
                    for y in range(h // 2):
                        for x in range(w):
                            canvas.SetPixel(x, y, ir, ig, ib)

                    # Hue bar across the bottom half
                    for x in range(w):
                        hr, hg, hb = colorsys.hsv_to_rgb(x / w, 1.0, 1.0)
                        for y in range(h // 2, h):
                            canvas.SetPixel(x, y, int(hr * 255), int(hg * 255), int(hb * 255))

                    # Cursor on the hue bar
                    cx = int(current_hue * w) % w
                    for y in range(h // 2, h):
                        canvas.SetPixel(cx, y, 255, 255, 255)

                    canvas = self.matrix.SwapOnVSync(canvas)
        finally:
            GPIO.cleanup([CLK_PIN, DT_PIN, SW_PIN])


if __name__ == "__main__":
    sample = GpioColorPicker()
    if not sample.process():
        sample.print_help()
