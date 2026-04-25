"""
Translates pygame keyboard/scroll events into gpio_shim pin triggers.

Reads the "gpio" section of emulator_config.json and builds lookup tables
for buttons, toggle switches, and rotary encoders.

Config shape:
    {
        "buttons": [{"key": "1", "pin": 17}, ...],
        "toggles": [{"key": "t", "pin": 22}, ...],
        "rotary_encoders": [
            {
                "key_cw":  "scrollup",    # or a keyboard key name
                "key_ccw": "scrolldown",
                "clk_pin": 23,
                "dt_pin":  24,
                "sw_pin":  25,            # optional
                "key_sw":  "r"            # optional
            }
        ]
    }

Supported key names for "key_cw" / "key_ccw":
    "scrollup", "scrolldown"  — mouse wheel
    Any pygame key name without the "K_" prefix, e.g. "space", "return", "1"
"""

import pygame
from RGBMatrixEmulator.emulation import gpio_shim
from RGBMatrixEmulator.logger import Logger


def _resolve_key(name: str):
    """Return a pygame key constant or the sentinel strings 'scrollup'/'scrolldown'."""
    low = name.lower()
    if low in ("scrollup", "scrolldown"):
        return low
    # Try direct attribute lookup: K_1, K_space, K_return, etc.
    attr = "K_" + low
    if hasattr(pygame, attr):
        return getattr(pygame, attr)
    # Fallback: pygame.key.key_code (requires pygame init, safe after display)
    try:
        return pygame.key.key_code(low)
    except Exception:
        Logger.warning(f"gpio input_map: unknown key '{name}', mapping ignored.")
        return None


class InputMap:
    def __init__(self, gpio_config):
        # Maps pygame key constant → (pin, type)  type in {"button", "toggle"}
        self._key_to_pin: dict = {}
        # Maps scroll direction sentinel → (clk_pin, dt_pin, direction)
        self._scroll_map: dict = {"scrollup": [], "scrolldown": []}

        self._build(gpio_config)

    def _build(self, cfg):
        for entry in cfg.get("buttons", []):
            key = _resolve_key(entry["key"])
            if key is not None:
                self._key_to_pin[key] = (entry["pin"], "button")
                Logger.info(f"gpio: key '{entry['key']}' → button pin {entry['pin']}")

        for entry in cfg.get("toggles", []):
            key = _resolve_key(entry["key"])
            if key is not None:
                self._key_to_pin[key] = (entry["pin"], "toggle")
                Logger.info(f"gpio: key '{entry['key']}' → toggle pin {entry['pin']}")

        for enc in cfg.get("rotary_encoders", []):
            clk = enc["clk_pin"]
            dt = enc["dt_pin"]

            cw_key = _resolve_key(enc.get("key_cw", "scrollup"))
            ccw_key = _resolve_key(enc.get("key_ccw", "scrolldown"))

            if cw_key == "scrollup":
                self._scroll_map["scrollup"].append((clk, dt, "cw"))
            elif cw_key is not None:
                self._key_to_pin[cw_key] = (clk, dt, "rotary_cw")

            if ccw_key == "scrolldown":
                self._scroll_map["scrolldown"].append((clk, dt, "ccw"))
            elif ccw_key is not None:
                self._key_to_pin[ccw_key] = (clk, dt, "rotary_ccw")

            # Optional push-button on the encoder shaft
            sw_pin = enc.get("sw_pin")
            key_sw = enc.get("key_sw")
            if sw_pin is not None and key_sw is not None:
                key = _resolve_key(key_sw)
                if key is not None:
                    self._key_to_pin[key] = (sw_pin, "button")
                    Logger.info(f"gpio: key '{key_sw}' → rotary switch pin {sw_pin}")

            Logger.info(
                f"gpio: rotary encoder clk={clk} dt={dt} "
                f"cw='{enc.get('key_cw')}' ccw='{enc.get('key_ccw')}'"
            )

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self._handle_keydown(event.key)
        elif event.type == pygame.KEYUP:
            self._handle_keyup(event.key)
        elif event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                for clk, dt, _ in self._scroll_map["scrollup"]:
                    self._fire_rotary(clk, dt, "cw")
            elif event.y < 0:
                for clk, dt, _ in self._scroll_map["scrolldown"]:
                    self._fire_rotary(clk, dt, "ccw")

    def _handle_keydown(self, key_const):
        entry = self._key_to_pin.get(key_const)
        if entry is None:
            return
        if entry[1] == "button":
            gpio_shim._trigger_pin(entry[0], gpio_shim.HIGH)
        elif entry[1] == "toggle":
            current = gpio_shim.input(entry[0])
            gpio_shim._trigger_pin(entry[0], gpio_shim.LOW if current == gpio_shim.HIGH else gpio_shim.HIGH)
        elif entry[1] == "rotary_cw":
            self._fire_rotary(entry[0], entry[1], "cw")
        elif entry[1] == "rotary_ccw":
            self._fire_rotary(entry[0], entry[1], "ccw")

    def _handle_keyup(self, key_const):
        entry = self._key_to_pin.get(key_const)
        if entry is None:
            return
        if entry[1] == "button":
            gpio_shim._trigger_pin(entry[0], gpio_shim.LOW)

    def _fire_rotary(self, clk_pin: int, dt_pin: int, direction: str):
        """Simulate rotary encoder pulse sequence."""
        if direction == "cw":
            # CW: CLK rises first, then DT
            gpio_shim._trigger_pin(clk_pin, gpio_shim.HIGH)
            gpio_shim._trigger_pin(dt_pin, gpio_shim.HIGH)
            gpio_shim._trigger_pin(clk_pin, gpio_shim.LOW)
            gpio_shim._trigger_pin(dt_pin, gpio_shim.LOW)
        else:
            # CCW: DT rises first, then CLK
            gpio_shim._trigger_pin(dt_pin, gpio_shim.HIGH)
            gpio_shim._trigger_pin(clk_pin, gpio_shim.HIGH)
            gpio_shim._trigger_pin(dt_pin, gpio_shim.LOW)
            gpio_shim._trigger_pin(clk_pin, gpio_shim.LOW)
