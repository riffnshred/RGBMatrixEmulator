import os
import sys
import json

# Try to suppress the pygame load warning if able.
try:
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
except Exception:
    pass

import pygame

from pygame.locals import QUIT, KEYDOWN, KEYUP, MOUSEWHEEL
from RGBMatrixEmulator.adapters.base import BaseAdapter
from RGBMatrixEmulator.internal.pixel_style import PixelStyle
from RGBMatrixEmulator.logger import Logger

_PANEL_WIDTH = 180


class PygameAdapter(BaseAdapter):
    SUPPORTED_PIXEL_STYLES = [
        PixelStyle.SQUARE,
        PixelStyle.CIRCLE,
        PixelStyle.REAL,
    ]

    def __init__(self, width, height, options):
        super().__init__(width, height, options)
        self.__surface = None
        self.__input_map = None
        self.__controls_panel = None

    def load_emulator_window(self):
        if self.loaded:
            return

        Logger.info(self.emulator_title)

        gpio_cfg = self.__load_gpio_config()
        self.__init_input_map(gpio_cfg)
        self.__init_controls_panel(gpio_cfg)

        matrix_w, matrix_h = self.options.window_size()
        panel_w = _PANEL_WIDTH if self.__controls_panel is not None else 0
        self.__matrix_w = matrix_w
        self.__surface = pygame.display.set_mode((matrix_w + panel_w, matrix_h))

        pygame.init()
        self.__set_emulator_icon()
        pygame.display.set_caption(self.emulator_title)

        self.loaded = True

    def __load_gpio_config(self) -> dict:
        from RGBMatrixEmulator.internal.emulator_config import RGBMatrixEmulatorConfig
        cfg = RGBMatrixEmulatorConfig.DEFAULT_CONFIG.get("gpio", {})
        if os.path.exists(RGBMatrixEmulatorConfig.CONFIG_PATH):
            try:
                with open(RGBMatrixEmulatorConfig.CONFIG_PATH) as f:
                    cfg = json.load(f).get("gpio", cfg)
            except Exception as e:
                Logger.warning(f"gpio config could not be read: {e}")
        return cfg

    def __init_input_map(self, cfg: dict):
        try:
            from RGBMatrixEmulator.emulation.input_map import InputMap
            has_controls = cfg.get("buttons") or cfg.get("toggles") or cfg.get("rotary_encoders")
            if has_controls:
                self.__input_map = InputMap(cfg)
        except Exception as e:
            Logger.warning(f"gpio input_map could not be initialised: {e}")

    def __init_controls_panel(self, cfg: dict):
        try:
            from RGBMatrixEmulator.adapters.controls_panel import ControlsPanel
            has_controls = cfg.get("buttons") or cfg.get("toggles") or cfg.get("rotary_encoders")
            if has_controls:
                _, matrix_h = self.options.window_size()
                self.__controls_panel = ControlsPanel(cfg, _PANEL_WIDTH, matrix_h)
        except Exception as e:
            Logger.warning(f"controls panel could not be initialised: {e}")

    def draw_to_screen(self, pixels):
        image = self._get_masked_image(pixels)
        pygame_surface = pygame.image.fromstring(
            image.tobytes(), self.options.window_size(), "RGB"
        )
        self.__surface.blit(pygame_surface, (0, 0))

        if self.__controls_panel is not None:
            self.__controls_panel.draw(self.__surface, self.__matrix_w)

        pygame.display.flip()

    def check_for_quit_event(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            elif self.__input_map is not None and event.type in (KEYDOWN, KEYUP, MOUSEWHEEL):
                self.__input_map.handle_event(event)

    def __set_emulator_icon(self):
        icon = pygame.image.load(self.icon_path)
        pygame.display.set_icon(icon)
