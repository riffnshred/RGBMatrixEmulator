import io, json, os, webbrowser
from pathlib import Path

import numpy as np

from RGBMatrixEmulator.adapters.base import BaseAdapter
from RGBMatrixEmulator.internal.pixel_style import PixelStyle
from RGBMatrixEmulator.adapters.browser_adapter.server import Server
from RGBMatrixEmulator.logger import Logger


class BrowserAdapter(BaseAdapter):
    SUPPORTED_PIXEL_STYLES = [
        PixelStyle.SQUARE,
        PixelStyle.CIRCLE,
        PixelStyle.REAL,
    ]
    IMAGE_FORMATS = {"bmp": "BMP", "jpeg": "JPEG", "png": "PNG", "webp": "WebP"}

    def __init__(self, width, height, options):
        super().__init__(width, height, options)
        self.__server = None
        self.image = None
        self.image_ready = False
        self.default_image_format = "JPEG"

        # Producer/consumer split: draw_to_screen (user thread) stashes the latest
        # pixel buffer; the Tornado periodic on the IO loop encodes and broadcasts
        # at most once per target_fps tick.
        self._latest_pixels = None
        self._frame_seq = 0
        self._last_encoded_seq = -1
        self._last_encoded_pixels = None

        image_format = options.browser.image_format
        if image_format.lower() in self.IMAGE_FORMATS:
            self.image_format = self.IMAGE_FORMATS[image_format.lower()]
        else:
            Logger.warning(
                "Invalid browser image format '{}', falling back to '{}'".format(
                    image_format, self.default_image_format
                )
            )
            self.image_format = self.IMAGE_FORMATS.get(
                self.default_image_format.lower()
            )

        # Default icon path is browser adapter assets
        self.default_icon_path = str(
            (Path(__file__).parent / "static" / "assets" / "icon.ico").resolve()
        )
        self._set_icon_path()

        self.gpio_config = self.__load_gpio_config()
        self.gpio_config_json = json.dumps(self.gpio_config)

    def __load_gpio_config(self) -> dict:
        from RGBMatrixEmulator.internal.emulator_config import RGBMatrixEmulatorConfig
        cfg = RGBMatrixEmulatorConfig.DEFAULT_CONFIG.get("gpio", {})
        if os.path.exists(RGBMatrixEmulatorConfig.CONFIG_PATH):
            try:
                with open(RGBMatrixEmulatorConfig.CONFIG_PATH) as f:
                    cfg = json.load(f).get("gpio", cfg)
            except Exception:
                pass
        return cfg

    def load_emulator_window(self):
        if self.loaded:
            return

        Logger.info(self.emulator_title)

        self.__server = Server(self)
        self.__server.run()

        self.loaded = True

        self.__open_browser()

    def draw_to_screen(self, pixels):
        # Hot path on the user's render thread: just snapshot the buffer.
        # Encoding happens on the IO loop, capped at target_fps.
        self._latest_pixels = np.ascontiguousarray(pixels).copy()
        self._frame_seq += 1

    def encode_for_broadcast(self):
        """Encode the latest pixel snapshot if it's new. Runs on the Tornado IO loop.

        Returns True when self.image was refreshed and should be broadcast.
        """
        if self._frame_seq == self._last_encoded_seq:
            return False

        pixels = self._latest_pixels
        if pixels is None:
            return False

        if self._last_encoded_pixels is not None and np.array_equal(
            pixels, self._last_encoded_pixels
        ):
            self._last_encoded_seq = self._frame_seq
            return False

        image = self._get_masked_image(pixels)
        with io.BytesIO() as bytesIO:
            image.save(
                bytesIO,
                self.image_format,
                quality=self.options.browser.quality,
            )
            self.image = bytesIO.getvalue()

        self._last_encoded_pixels = pixels
        self._last_encoded_seq = self._frame_seq
        self.image_ready = True
        return True

    def __open_browser(self):
        if self.options.browser.open_immediately:
            try:
                uri = f"http://localhost:{self.options.browser.port}"
                Logger.info(
                    f"Browser adapter configured to open immediately, opening new window/tab to {uri}"
                )
                webbrowser.open(uri)
            except Exception as e:
                Logger.exception("Failed to open a browser window")
                Logger.exception(e)
