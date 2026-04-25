import os
import sys

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

    def load_emulator_window(self):
        if self.loaded:
            return

        Logger.info(self.emulator_title)
        self.__surface = pygame.display.set_mode(self.options.window_size())
        pygame.init()

        self.__set_emulator_icon()
        pygame.display.set_caption(self.emulator_title)

        self.__init_input_map()
        self.loaded = True

    def __init_input_map(self):
        try:
            from RGBMatrixEmulator.internal.emulator_config import RGBMatrixEmulatorConfig
            from RGBMatrixEmulator.emulation.input_map import InputMap
            cfg = RGBMatrixEmulatorConfig.DEFAULT_CONFIG.get("gpio", {})
            # Prefer live config file values if already loaded
            import os, json
            if os.path.exists(RGBMatrixEmulatorConfig.CONFIG_PATH):
                with open(RGBMatrixEmulatorConfig.CONFIG_PATH) as f:
                    live = json.load(f)
                cfg = live.get("gpio", cfg)
            buttons = cfg.get("buttons", [])
            toggles = cfg.get("toggles", [])
            encoders = cfg.get("rotary_encoders", [])
            if buttons or toggles or encoders:
                self.__input_map = InputMap(cfg)
        except Exception as e:
            Logger.warning(f"gpio input_map could not be initialised: {e}")

    def draw_to_screen(self, pixels):
        image = self._get_masked_image(pixels)
        pygame_surface = pygame.image.fromstring(
            image.tobytes(), self.options.window_size(), "RGB"
        )
        self.__surface.blit(pygame_surface, (0, 0))

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
