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
        ],
        "potentiometers": [
            {
                "pin":      26,
                "min":      0,
                "max":      255,
                "step":     1,            # optional, default 1
                "key_up":   "scrollup",   # optional
                "key_down": "scrolldown", # optional
                "label":    "Brightness"  # optional, display only
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
        # Maps pygame key constant → (pin, type)  type in {"button", "toggle", "pot_up", "pot_down"}
        self._key_to_pin: dict = {}
        # Rotary encoder scroll wheel entries: direction → [(clk_pin, dt_pin, _)]
        self._scroll_map: dict = {"scrollup": [], "scrolldown": []}
        # Potentiometer scroll wheel entries: direction → [pin, ...]
        self._scroll_pots: dict = {"scrollup": [], "scrolldown": []}

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

        for pot in cfg.get("potentiometers", []):
            pin = pot["pin"]
            min_val = float(pot.get("min", 0))
            max_val = float(pot.get("max", 100))
            step = float(pot.get("step", 1))
            gpio_shim._init_pot(pin, min_val, max_val, step)

            up_key_name = pot.get("key_up", "")
            dn_key_name = pot.get("key_down", "")

            if up_key_name:
                up_key = _resolve_key(up_key_name)
                if up_key == "scrollup":
                    self._scroll_pots["scrollup"].append(pin)
                elif up_key is not None:
                    self._key_to_pin[up_key] = (pin, "pot_up")

            if dn_key_name:
                dn_key = _resolve_key(dn_key_name)
                if dn_key == "scrolldown":
                    self._scroll_pots["scrolldown"].append(pin)
                elif dn_key is not None:
                    self._key_to_pin[dn_key] = (pin, "pot_down")

            Logger.info(f"gpio: potentiometer pin={pin} min={min_val} max={max_val} step={step}")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self._handle_keydown(event.key)
        elif event.type == pygame.KEYUP:
            self._handle_keyup(event.key)
        elif event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                for clk, dt, _ in self._scroll_map["scrollup"]:
                    self._fire_rotary(clk, dt, "cw")
                for pin in self._scroll_pots["scrollup"]:
                    self._step_pot(pin, +1)
            elif event.y < 0:
                for clk, dt, _ in self._scroll_map["scrolldown"]:
                    self._fire_rotary(clk, dt, "ccw")
                for pin in self._scroll_pots["scrolldown"]:
                    self._step_pot(pin, -1)

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
        elif entry[1] == "pot_up":
            self._step_pot(entry[0], +1)
        elif entry[1] == "pot_down":
            self._step_pot(entry[0], -1)

    def _handle_keyup(self, key_const):
        entry = self._key_to_pin.get(key_const)
        if entry is None:
            return
        if entry[1] == "button":
            gpio_shim._trigger_pin(entry[0], gpio_shim.LOW)

    def _step_pot(self, pin: int, direction: int):
        """Advance a potentiometer by one step in the given direction (+1 or -1)."""
        cfg = gpio_shim._pot_configs.get(pin, {"min": 0.0, "max": 100.0, "step": 1.0})
        current = gpio_shim._get_pot(pin)
        gpio_shim._set_pot(pin, current + direction * cfg["step"])

    def _fire_rotary(self, clk_pin: int, dt_pin: int, direction: str):
        """Simulate rotary encoder pulse sequence."""
        gpio_shim._update_encoder(clk_pin, dt_pin, direction)
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
