#!/usr/bin/env python
"""
GPIO Brightness Control
-----------------------
A bouncing ball animation whose brightness is controlled by a rotary encoder.
A toggle switch (pin 22) pauses / resumes the animation.

emulator_config.json gpio section:
    "gpio": {
        "toggles": [{"key": "p", "pin": 22}],
        "rotary_encoders": [
            {
                "key_cw":  "scrollup",
                "key_ccw": "scrolldown",
                "clk_pin": 23,
                "dt_pin":  24
            }
        ]
    }
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from samplebase import SampleBase

try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO

CLK_PIN    = 23
DT_PIN     = 24
PAUSE_PIN  = 22

_brightness = 80     # 1–100
_last_clk   = None


def _on_rotate(channel):
    global _brightness, _last_clk
    clk = GPIO.input(CLK_PIN)
    dt  = GPIO.input(DT_PIN)
    if clk == GPIO.HIGH and _last_clk == GPIO.LOW:
        delta = 5 if dt == GPIO.HIGH else -5
        _brightness = max(1, min(100, _brightness + delta))
    _last_clk = clk


class GpioBrightnessControl(SampleBase):
    def run(self):
        global _last_clk

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(CLK_PIN,   GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(DT_PIN,    GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PAUSE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        _last_clk = GPIO.input(CLK_PIN)
        GPIO.add_event_detect(CLK_PIN, GPIO.BOTH, callback=_on_rotate)

        canvas = self.matrix.CreateFrameCanvas()
        w = self.matrix.width
        h = self.matrix.height

        # Ball state
        bx, by = float(w // 2), float(h // 2)
        vx, vy = 0.6, 0.4
        radius = 3

        try:
            prev_brightness = -1
            while True:
                paused = GPIO.input(PAUSE_PIN) == GPIO.HIGH

                if not paused:
                    bx += vx
                    by += vy
                    if bx - radius < 0:
                        bx = radius
                        vx = abs(vx)
                    elif bx + radius >= w:
                        bx = w - 1 - radius
                        vx = -abs(vx)
                    if by - radius < 0:
                        by = radius
                        vy = abs(vy)
                    elif by + radius >= h:
                        by = h - 1 - radius
                        vy = -abs(vy)

                bright = _brightness
                if bright != prev_brightness:
                    self.matrix.brightness = bright
                    prev_brightness = bright

                scale = bright / 100.0
                canvas.Clear()

                # Draw ball
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        if dx * dx + dy * dy <= radius * radius:
                            px, py = int(bx) + dx, int(by) + dy
                            if 0 <= px < w and 0 <= py < h:
                                canvas.SetPixel(px, py,
                                    int(255 * scale),
                                    int(100 * scale),
                                    int(30 * scale))

                # Brightness bar on bottom row
                bar_w = int((bright / 100.0) * w)
                for x in range(bar_w):
                    canvas.SetPixel(x, h - 1,
                        int(50 * scale),
                        int(200 * scale),
                        int(255 * scale))

                # Pause indicator: top-left corner dot
                if paused:
                    canvas.SetPixel(0, 0, 255, 50, 50)
                    canvas.SetPixel(1, 0, 255, 50, 50)
                    canvas.SetPixel(0, 1, 255, 50, 50)
                    canvas.SetPixel(1, 1, 255, 50, 50)

                canvas = self.matrix.SwapOnVSync(canvas)
                time.sleep(0.016)
        finally:
            GPIO.cleanup([CLK_PIN, DT_PIN, PAUSE_PIN])


if __name__ == "__main__":
    sample = GpioBrightnessControl()
    if not sample.process():
        sample.print_help()
