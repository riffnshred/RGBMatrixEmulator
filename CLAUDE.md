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

The browser adapter (adapters/browser_adapter/) runs a **Tornado web server** in a daemon thread. The server serves an HTML/JS client over a WebSocket that receives JPEG/PNG frames via `PeriodicCallback`. Routes: `/` (main), `/websocket` (frame stream), `/image` (single-shot), `/gpio` (GET — pin/encoder state), `/gpio/trigger` (POST — drive pins from the browser UI). The server is itself a singleton (`Server.__Singleton`).

### GPIO Shim + Input Mapping

`emulation/gpio_shim.py` is a module-level drop-in for `RPi.GPIO`, maintaining pin state, callbacks, and rotary encoder positions in plain dicts. It is imported as:

```python
try:
    import RPi.GPIO as GPIO
except ImportError:
    from RGBMatrixEmulator.emulation import gpio_shim as GPIO
```

The `"gpio"` section of `emulator_config.json` configures buttons, toggles, and rotary encoders:

```json
"gpio": {
    "buttons":          [{"key": "r", "pin": 25}],
    "toggles":          [{"key": "t", "pin": 22}],
    "rotary_encoders":  [{"key_cw": "scrollup", "key_ccw": "scrolldown",
                          "clk_pin": 23, "dt_pin": 24,
                          "sw_pin": 25, "key_sw": "r"}]
}
```

`emulation/input_map.py` (`InputMap`) translates pygame keyboard/scroll-wheel events into `gpio_shim._trigger_pin()` calls; the pygame adapter calls `InputMap.handle_event()` each frame. The browser adapter exposes the same pin-driving capability via `GpioTriggerHandler` (POST `/gpio/trigger`). `adapters/controls_panel.py` (`ControlsPanel`) draws a live GPIO state sidebar inside the pygame window — it reads `gpio_shim` directly on every frame.

### Pixel Styles

`internal/pixel_style.py` defines `PixelStyle` (SQUARE, CIRCLE, REAL). Each adapter declares `SUPPORTED_PIXEL_STYLES`; unsupported styles fall back to `DEFAULT` at config load time.

### Testing

Tests live in `test/` and use `unittest`. `test_sample.py` runs sample scripts against reference PNG screenshots using the `raw` adapter (no display window). The `raw` adapter is not in the fallback chain (`"fallback": False`), so tests must explicitly configure it via `test/test_config.json`. Failed comparisons write diff images to `test/result/`.
