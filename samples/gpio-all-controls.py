#!/usr/bin/env python
"""
GPIO All Controls Demo
-----------------------
Demonstrates every GPIO input type in a single sample.

Controls
--------
  Button       (pin 17, key SPACE)        — cycle foreground colour (5 presets)
  Toggle       (pin 22, key t)            — pause / resume animation
  Rotary enc.  (clk=23, dt=24, scroll)    — change animation mode
  Encoder btn  (sw=25,  key r)            — reset animation mode to 0
  Pot 1        (pin 26, key up / down)    — overall brightness  (0 – 100 %)
  Pot 2        (pin 27, key right / left) — animation speed     (0 – 100 %)

Indicators
----------
  RGB LED      (pin 28)                   — mirrors current foreground colour
  Paused LED   (pin 29, red)              — lit when animation is paused

Required emulator_config.json "gpio" section:
    "gpio": {
        "buttons": [{"key": "space", "pin": 17}],
        "toggles": [{"key": "t",     "pin": 22}],
        "rotary_encoders": [
            {
                "key_cw":  "scrollup",
                "key_ccw": "scrolldown",
                "clk_pin": 23,
                "dt_pin":  24,
                "sw_pin":  25,
                "key_sw":  "r"
            }
        ],
        "potentiometers": [
            {"pin": 26, "min": 0, "max": 100, "step": 2,
             "key_up": "up",    "key_down": "down",  "label": "Brightness"},
            {"pin": 27, "min": 0, "max": 100, "step": 2,
             "key_up": "right", "key_down": "left",  "label": "Speed"}
        ],
        "rgb_leds": [
            {"pin": 28, "label": "Fg Color"}
        ],
        "indicators": [
            {"pin": 29, "label": "Paused", "color": "red"}
        ]
    }
"""
import sys
import os
import math
import random
import time
import colorsys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from samplebase import SampleBase

try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO

# ── Pin assignments ────────────────────────────────────────────────────────────
BUTTON_PIN  = 17   # momentary push-button
PAUSE_PIN   = 22   # toggle switch
CLK_PIN     = 23   # rotary encoder clock
DT_PIN      = 24   # rotary encoder data
SW_PIN      = 25   # rotary encoder push-button
BRIGHT_PIN  = 26   # potentiometer → brightness
SPEED_PIN   = 27   # potentiometer → animation speed
RGB_PIN     = 28   # RGB LED — mirrors current foreground colour
PAUSED_PIN  = 29   # indicator LED — lit when paused

# ── Animation modes ────────────────────────────────────────────────────────────
MODES     = ["plasma", "scan", "starfield"]
NUM_MODES = len(MODES)

# ── Foreground colour presets (hue, 0 – 1) ───────────────────────────────────
COLORS = [0.0, 0.33, 0.55, 0.75, 0.95]   # red, green, cyan, purple, pink

# ── Shared callback state ─────────────────────────────────────────────────────
_mode_index  = 0
_color_index = 0
_last_clk    = None


def _on_color_cycle(channel):
    """Button press: advance foreground colour preset."""
    global _color_index
    _color_index = (_color_index + 1) % len(COLORS)


def _on_mode_reset(channel):
    """Encoder button: reset animation mode to 0."""
    global _mode_index
    _mode_index = 0


def _on_rotate(channel):
    """Rotary encoder CLK edge: change animation mode."""
    global _mode_index, _last_clk
    clk = GPIO.input(CLK_PIN)
    dt  = GPIO.input(DT_PIN)
    if clk == GPIO.HIGH and _last_clk == GPIO.LOW:
        delta = 1 if dt == GPIO.HIGH else -1
        _mode_index = (_mode_index + delta) % NUM_MODES
    _last_clk = clk


class GpioAllControls(SampleBase):
    def run(self):
        global _last_clk

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(PAUSE_PIN,  GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(CLK_PIN,    GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(DT_PIN,     GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(SW_PIN,     GPIO.IN,  pull_up_down=GPIO.PUD_UP)
        GPIO.setup(BRIGHT_PIN, GPIO.IN)
        GPIO.setup(SPEED_PIN,  GPIO.IN)
        GPIO.setup(RGB_PIN,    GPIO.OUT)
        GPIO.setup(PAUSED_PIN, GPIO.OUT)

        _last_clk = GPIO.input(CLK_PIN)

        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING,  callback=_on_color_cycle, bouncetime=200)
        GPIO.add_event_detect(CLK_PIN,    GPIO.BOTH,    callback=_on_rotate)
        GPIO.add_event_detect(SW_PIN,     GPIO.FALLING, callback=_on_mode_reset,  bouncetime=200)

        canvas = self.matrix.CreateFrameCanvas()
        w = self.matrix.width
        h = self.matrix.height

        # Starfield: random positions + per-star phase for independent twinkle
        stars = [
            (random.randint(0, w - 1), random.randint(0, h - 1), random.uniform(0, math.tau))
            for _ in range(max(20, w * h // 60))
        ]

        t = 0.0

        try:
            while True:
                paused   = GPIO.input(PAUSE_PIN) == GPIO.HIGH
                bright   = GPIO._get_pot(BRIGHT_PIN) / 100.0   # 0.0 – 1.0
                speed    = GPIO._get_pot(SPEED_PIN)  / 100.0   # 0.0 – 1.0
                hue_base = COLORS[_mode_index % NUM_MODES]      # read once per frame
                fg_hue   = COLORS[_color_index]
                mode     = _mode_index

                # ── Output indicators ────────────────────────────────────
                fr, fg, fb = colorsys.hsv_to_rgb(fg_hue, 1.0, max(0.15, bright))
                GPIO.set_rgb(RGB_PIN, int(fr * 255), int(fg * 255), int(fb * 255))
                GPIO.output(PAUSED_PIN, GPIO.HIGH if paused else GPIO.LOW)

                if not paused:
                    t += 0.03 + speed * 0.12

                canvas.Clear()

                if mode == 0:
                    # ── Plasma: interference of three sine waves ─────────────
                    for y in range(h):
                        for x in range(w):
                            v = (math.sin(x / 4.0 + t) +
                                 math.sin(y / 4.0 + t * 0.7) +
                                 math.sin((x + y) / 6.0 + t * 1.3)) / 3.0
                            hue = (fg_hue + (v + 1.0) * 0.15) % 1.0
                            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, bright)
                            canvas.SetPixel(x, y, int(r * 255), int(g * 255), int(b * 255))

                elif mode == 1:
                    # ── Rainbow scan: vertical colour bands scrolling left ───
                    for x in range(w):
                        hue = (fg_hue + x / w + t * 0.08) % 1.0
                        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, bright)
                        ir, ig, ib = int(r * 255), int(g * 255), int(b * 255)
                        for y in range(h):
                            canvas.SetPixel(x, y, ir, ig, ib)

                elif mode == 2:
                    # ── Starfield: twinkling stars ───────────────────────────
                    for sx, sy, phase in stars:
                        flicker = (math.sin(t * 4.0 + phase) + 1.0) / 2.0
                        v = flicker * bright
                        r, g, b = colorsys.hsv_to_rgb(fg_hue, 0.25, v)
                        canvas.SetPixel(sx, sy, int(r * 255), int(g * 255), int(b * 255))

                # ── Status indicators ────────────────────────────────────────
                # Top-left 2×2: red when paused
                if paused:
                    pv = max(60, int(200 * bright))
                    for dy in range(2):
                        for dx in range(2):
                            canvas.SetPixel(dx, dy, pv, 0, 0)

                # Top-right column: brightness level bar (vertical, right edge)
                bar_h = int(bright * h)
                for y in range(h - 1, h - 1 - bar_h, -1):
                    if y >= 0:
                        canvas.SetPixel(w - 1, y, 0, 180, 80)

                canvas = self.matrix.SwapOnVSync(canvas)
                time.sleep(0.016)

        finally:
            GPIO.cleanup([BUTTON_PIN, PAUSE_PIN, CLK_PIN, DT_PIN, SW_PIN,
                          BRIGHT_PIN, SPEED_PIN, RGB_PIN, PAUSED_PIN])


if __name__ == "__main__":
    sample = GpioAllControls()
    if not sample.process():
        sample.print_help()
