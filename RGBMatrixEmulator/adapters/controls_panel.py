"""
Draws a live hardware-controls sidebar inside the pygame window.

Reads pin state directly from gpio_shim on every frame so it always reflects
the current emulated state without extra wiring.
"""

import math
import pygame
from RGBMatrixEmulator.emulation import gpio_shim

# Palette
_BG         = (18, 18, 18)
_DIVIDER    = (45, 45, 45)
_TEXT       = (210, 210, 210)
_LABEL      = (110, 110, 110)
_BTN_OFF    = (55, 55, 55)
_BTN_ON     = (30, 210, 90)
_TOG_OFF    = (55, 55, 55)
_TOG_ON     = (30, 140, 230)
_ENC_BG     = (45, 45, 45)
_ENC_NEEDLE = (230, 150, 20)
_ENC_RIM    = (85, 85, 85)
_POT_FILL   = (230, 150, 20)
_POT_TRACK  = (55, 55, 55)

_PAD = 10


class ControlsPanel:
    def __init__(self, gpio_config: dict, width: int, height: int):
        self.width = width
        self.height = height
        self.buttons = gpio_config.get("buttons", [])
        self.toggles = gpio_config.get("toggles", [])
        self.encoders = gpio_config.get("rotary_encoders", [])
        self.potentiometers = gpio_config.get("potentiometers", [])
        self._font_h = None   # header
        self._font_m = None   # medium
        self._font_s = None   # small

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface, x: int):
        """Draw the panel at horizontal offset *x*."""
        self._ensure_fonts()

        # Background + left border
        pygame.draw.rect(surface, _BG, (x, 0, self.width, self.height))
        pygame.draw.line(surface, _DIVIDER, (x, 0), (x, self.height))

        y = _PAD
        y = self._draw_title(surface, x, y)
        y = self._draw_buttons(surface, x, y)
        y = self._draw_toggles(surface, x, y)
        y = self._draw_encoders(surface, x, y)
        self._draw_potentiometers(surface, x, y)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _draw_title(self, surface, x, y):
        t = self._font_h.render("CONTROLS", True, _TEXT)
        surface.blit(t, (x + (self.width - t.get_width()) // 2, y))
        y += t.get_height() + 4
        pygame.draw.line(surface, _DIVIDER, (x + _PAD, y), (x + self.width - _PAD, y))
        return y + 6

    def _draw_buttons(self, surface, x, y):
        if not self.buttons:
            return y
        y = self._section_label(surface, x, y, "BUTTONS")
        for btn in self.buttons:
            pin = btn["pin"]
            key = btn.get("key", "?")
            on = gpio_shim.input(pin) == gpio_shim.HIGH
            color = _BTN_ON if on else _BTN_OFF
            r = 9
            cx = x + _PAD + r
            cy = y + r
            pygame.draw.circle(surface, color, (cx, cy), r)
            if on:
                pygame.draw.circle(surface, (180, 255, 180), (cx, cy), r, 1)
            lbl = self._font_m.render(f"[{key}] pin {pin}", True, _TEXT)
            surface.blit(lbl, (cx + r + 5, cy - lbl.get_height() // 2))
            y += r * 2 + 7
        return y + 4

    def _draw_toggles(self, surface, x, y):
        if not self.toggles:
            return y
        y = self._section_label(surface, x, y, "TOGGLES")
        for tog in self.toggles:
            pin = tog["pin"]
            key = tog.get("key", "?")
            on = gpio_shim.input(pin) == gpio_shim.HIGH
            color = _TOG_ON if on else _TOG_OFF
            tw, th = 22, 12
            tx = x + _PAD
            ty = y
            pygame.draw.rect(surface, color, (tx, ty, tw, th), border_radius=4)
            lbl = self._font_m.render(f"[{key}] pin {pin}", True, _TEXT)
            surface.blit(lbl, (tx + tw + 5, ty + th // 2 - lbl.get_height() // 2))
            y += th + 9
        return y + 4

    def _draw_encoders(self, surface, x, y):
        for enc in self.encoders:
            clk = enc["clk_pin"]
            dt  = enc["dt_pin"]
            key_cw  = enc.get("key_cw", "scrollup")
            key_ccw = enc.get("key_ccw", "scrolldown")

            y = self._section_label(surface, x, y, "ENCODER")

            # Dial
            dial_r  = 30
            dial_cx = x + self.width // 2
            dial_cy = y + dial_r + 2
            val = gpio_shim._encoder_values.get((clk, dt), 0)

            pygame.draw.circle(surface, _ENC_BG, (dial_cx, dial_cy), dial_r)
            pygame.draw.circle(surface, _ENC_RIM, (dial_cx, dial_cy), dial_r, 2)

            # Needle: 15° per tick, 0° at top
            angle_deg = (val * 15) % 360
            angle_rad = math.radians(angle_deg - 90)
            nx = dial_cx + int((dial_r - 7) * math.cos(angle_rad))
            ny = dial_cy + int((dial_r - 7) * math.sin(angle_rad))
            pygame.draw.line(surface, _ENC_NEEDLE, (dial_cx, dial_cy), (nx, ny), 3)
            pygame.draw.circle(surface, _ENC_NEEDLE, (dial_cx, dial_cy), 4)

            # Tick value centred below dial
            val_t = self._font_m.render(str(val), True, _ENC_NEEDLE)
            surface.blit(val_t, (dial_cx - val_t.get_width() // 2, dial_cy + dial_r + 3))

            y = dial_cy + dial_r + val_t.get_height() + 8

            # CLK / DT pin indicators
            for pin_label, pin_num in [("CLK", clk), ("DT", dt)]:
                on = gpio_shim.input(pin_num) == gpio_shim.HIGH
                color = _BTN_ON if on else _BTN_OFF
                r = 6
                px = x + _PAD + r
                py = y + r
                pygame.draw.circle(surface, color, (px, py), r)
                t = self._font_s.render(f"{pin_label} {pin_num}", True, _TEXT)
                surface.blit(t, (px + r + 4, py - t.get_height() // 2))
                y += r * 2 + 5

            # Key hint
            hint = self._font_s.render(f"↑{key_cw}  ↓{key_ccw}", True, _LABEL)
            surface.blit(hint, (x + (self.width - hint.get_width()) // 2, y + 2))
            y += hint.get_height() + 6

            # Optional shaft button
            sw_pin = enc.get("sw_pin")
            key_sw = enc.get("key_sw")
            if sw_pin is not None:
                on = gpio_shim.input(sw_pin) == gpio_shim.HIGH
                color = _BTN_ON if on else _BTN_OFF
                r = 9
                scx = x + _PAD + r
                scy = y + r
                pygame.draw.circle(surface, color, (scx, scy), r)
                if key_sw:
                    t = self._font_m.render(f"SW [{key_sw}] pin {sw_pin}", True, _TEXT)
                    surface.blit(t, (scx + r + 5, scy - t.get_height() // 2))
                y += r * 2 + 8

            y += 4

        return y

    def _draw_potentiometers(self, surface, x, y):
        if not self.potentiometers:
            return y
        for pot in self.potentiometers:
            pin = pot["pin"]
            min_val = float(pot.get("min", 0))
            max_val = float(pot.get("max", 100))
            label = pot.get("label", f"pin {pin}")
            value = gpio_shim._get_pot(pin)

            y = self._section_label(surface, x, y, "POT")

            lbl = self._font_m.render(label, True, _TEXT)
            surface.blit(lbl, (x + _PAD, y))
            y += lbl.get_height() + 4

            track_w = self.width - 2 * _PAD
            track_h = 8
            tx, ty = x + _PAD, y
            pygame.draw.rect(surface, _POT_TRACK, (tx, ty, track_w, track_h), border_radius=3)

            ratio = (value - min_val) / (max_val - min_val) if max_val > min_val else 0
            fill_w = int(track_w * ratio)
            if fill_w > 0:
                pygame.draw.rect(surface, _POT_FILL, (tx, ty, fill_w, track_h), border_radius=3)

            # Thumb indicator
            thumb_x = tx + fill_w
            pygame.draw.circle(surface, _POT_FILL, (thumb_x, ty + track_h // 2), 5)

            y += track_h + 4
            val_t = self._font_s.render(f"{value:.1f} / {max_val:.0f}", True, _ENC_NEEDLE)
            surface.blit(val_t, (x + _PAD, y))
            y += val_t.get_height() + 8

        return y

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _section_label(self, surface, x, y, text):
        t = self._font_s.render(text, True, _LABEL)
        surface.blit(t, (x + _PAD, y))
        return y + t.get_height() + 4

    def _ensure_fonts(self):
        if self._font_h is None:
            pygame.font.init()
            self._font_h = pygame.font.SysFont("monospace", 13, bold=True)
            self._font_m = pygame.font.SysFont("monospace", 11)
            self._font_s = pygame.font.SysFont("monospace", 9)
