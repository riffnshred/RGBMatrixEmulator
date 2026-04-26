# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
# Install dependencies (including dev group)
uv sync --group dev

# Install with optional pi5 support
uv sync --extra pi5

# Run a sample script
cd samples && uv run python runtext.py

# Run all tests
uv run python -m unittest discover -s test

# Run a single test method
uv run python -m unittest test.test_sample.TestSampleRunMatchesReference

# Lint (black; excludes samples/)
uv run black .

# Generate a fresh emulator config
rgbme config
```

## Architecture Overview

**RGBMatrixEmulator** is a drop-in emulator for the `rpi-rgb-led-matrix` Python bindings. Code that imports from `rgbmatrix` can swap to `from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions` and run on a PC.

### Request/Render Flow

```
User script
  → RGBMatrix  (emulation/matrix.py)   — mirrors rpi-rgb-led-matrix API
  → Canvas     (emulation/canvas.py)   — holds a NumPy H×W×3 pixel array
  → BaseAdapter subclass               — converts pixels to a display
```

`RGBMatrix.SwapOnVSync()` calls `canvas.draw_to_screen()`, which delegates to whichever adapter is active. Adapters are **singletons** (`BaseAdapter.INSTANCE`); `Canvas` always calls `get_instance()`.

### Configuration

`emulator_config.json` is looked up in the **current working directory** at startup. `RGBMatrixEmulatorConfig` (internal/emulator_config.py) loads it and dynamically sets attributes; nested dicts become `ChildConfig` objects. If the file is absent, a default is written on first run. Config is consumed once during `RGBMatrixOptions` construction; adapters read `options.*` and `options.browser.*` / `options.pi5.*` for adapter-specific settings.

### Adapter System

`adapters/__init__.py` defines the `ADAPTERS` registry (name → module path + class name + fallback flag). `AdapterLoader` (internal/adapter_loader.py) resolves the requested adapter and falls back through the registry if `allow_adapter_fallback` is true and the adapter fails to import.

All adapters extend `BaseAdapter` and must implement:
- `load_emulator_window()` — called once when `Canvas` is first created
- `draw_to_screen(pixels)` — called every `SwapOnVSync`

Pixel masking (square / circle / real-glow) is implemented in `BaseAdapter` using PIL composite masks. `_get_masked_image(pixels)` is the entry point adapters call before drawing.

### Browser Adapter (default)

The browser adapter (adapters/browser_adapter/) runs a **Tornado web server** in a daemon thread. The server serves an HTML/JS client over a WebSocket that receives JPEG/PNG frames via `PeriodicCallback`. Routes: `/` (main), `/websocket` (frame stream), `/image` (single-shot), `/gpio` (GET — returns `{pins, encoders, pots, rgb}` JSON), `/gpio/trigger` (POST — drive pins from the browser UI). The server is itself a singleton (`Server.__Singleton`).

The browser client renders an interactive controls panel alongside the matrix display. Layout is controlled by `browser.controls_layout` in `emulator_config.json` (`"horizontal"` or `"vertical"`). The panel reflects live GPIO state and lets the user click buttons/toggles, turn encoders, and drag potentiometer sliders.

`/gpio/trigger` body shapes:

```json
{"type": "button",  "pin": 17, "value": 1}
{"type": "toggle",  "pin": 22}
{"type": "encoder", "clk_pin": 23, "dt_pin": 24, "direction": "cw"}
{"type": "pot",     "pin": 26, "value": 75.0}
```

### GPIO Shim + Input Mapping

`emulation/gpio_shim.py` is a module-level drop-in for `RPi.GPIO`, maintaining pin state, callbacks, rotary encoder positions, potentiometer values, and RGB LED colors in plain dicts. It is imported as:

```python
try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO
```

**Module-level state dicts:**

| Dict | Key | Value |
|---|---|---|
| `_pin_states` | pin int | HIGH/LOW |
| `_callbacks` | pin int | list of (edge, callback) |
| `_encoder_values` | (clk_pin, dt_pin) | int tick count |
| `_pot_configs` | pin int | `{min, max, step}` |
| `_pot_values` | pin int | float |
| `_rgb_states` | pin int | (r, g, b) |

**Extended API (beyond standard RPi.GPIO):**

- `GPIO.set_rgb(pin, r, g, b)` — set an RGB LED pin to a color; also callable via `GPIO.output(pin, (r, g, b))`
- `GPIO._get_pot(pin)` — read current potentiometer float value
- `GPIO._set_pot(pin, value)` — set potentiometer value (clamped, fires callbacks)
- `GPIO._init_pot(pin, min, max, step)` — register a potentiometer (called automatically by `InputMap`)

The `"gpio"` section of `emulator_config.json` supports five input/output types:

```json
"gpio": {
    "buttons":         [{"key": "space", "pin": 17}],
    "toggles":         [{"key": "t", "pin": 22}],
    "rotary_encoders": [{"key_cw": "scrollup", "key_ccw": "scrolldown",
                         "clk_pin": 23, "dt_pin": 24,
                         "sw_pin": 25, "key_sw": "r"}],
    "potentiometers":  [{"pin": 26, "min": 0, "max": 100, "step": 2,
                         "key_up": "up", "key_down": "down", "label": "Brightness"}],
    "rgb_leds":        [{"pin": 28, "label": "Status"}],
    "indicators":      [{"pin": 29, "label": "Paused", "color": "red"}]
}
```

`potentiometers` are input pins driven by keyboard/scroll; values read via `GPIO._get_pot(pin)`. `rgb_leds` and `indicators` are output-only — the user script writes to them via `GPIO.set_rgb()` / `GPIO.output()`; they appear in both the pygame and browser controls panels.

Indicator `color` accepts: `green`, `red`, `yellow`, `blue`, `orange`, `white`, `cyan`, `purple`.

`emulation/input_map.py` (`InputMap`) translates pygame keyboard/scroll-wheel events into `gpio_shim._trigger_pin()` / `gpio_shim._set_pot()` calls; the pygame adapter calls `InputMap.handle_event()` each frame. The browser adapter exposes the same pin-driving capability via `GpioTriggerHandler` (POST `/gpio/trigger`). `adapters/controls_panel.py` (`ControlsPanel`) draws a live GPIO state sidebar inside the pygame window — it reads `gpio_shim` directly on every frame, rendering buttons, toggles, encoders, potentiometer sliders, RGB LEDs, and indicators.

### Pixel Styles

`internal/pixel_style.py` defines `PixelStyle` (SQUARE, CIRCLE, REAL). Each adapter declares `SUPPORTED_PIXEL_STYLES`; unsupported styles fall back to `DEFAULT` at config load time.

### Graphics Module

`graphics/__init__.py` provides the drawing API mirroring `rgbmatrix.graphics`: `DrawText(canvas, font, x, y, color, text)`, `DrawLine(canvas, x1, y1, x2, y2, color)`, `DrawCircle(canvas, x, y, r, color)`. All drawing functions accept only `Color` instances (not raw tuples). `Font` wraps BDF fonts via `bdfparser`. These are re-exported from `RGBMatrixEmulator` top-level.

### Adding a New Adapter

1. Implement `BaseAdapter` (`load_emulator_window` + `draw_to_screen`), setting `SUPPORTED_PIXEL_STYLES`.
2. Register it in `adapters/__init__.py` `ADAPTERS` dict with `path`, `class`, and `fallback` keys.
3. Call `self._get_masked_image(pixels)` inside `draw_to_screen` before rendering to apply the active pixel style.

### Testing

Tests live in `test/` and use `unittest`. `test_sample.py` runs sample scripts against reference PNG screenshots using the `raw` adapter (no display window). The `raw` adapter is not in the fallback chain (`"fallback": False`), so tests must explicitly configure it via `test/test_config.json`. Failed comparisons write diff images to `test/result/`.

To regenerate reference screenshots after changing rendering behavior:

```sh
cd test && uv run python reference.py
```

### GPIO Sample Scripts

`samples/` includes several GPIO demo scripts that also serve as usage references:

| Script | Demonstrates |
|---|---|
| `gpio-all-controls.py` | All input/output types together (button, toggle, encoder, two pots, RGB LED, indicator) |
| `gpio-brightness-control.py` | Potentiometer controlling display brightness |
| `gpio-button-counter.py` | Button with event callback |
| `gpio-color-picker.py` | Rotary encoder cycling hue |
| `gpio-pot-color.py` | Potentiometer controlling color |

Each script includes the required `emulator_config.json` `"gpio"` snippet in its docstring.
