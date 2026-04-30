from RGBMatrixEmulator.internal.emulator_config import RGBMatrixEmulatorConfig


def visible_dims(options) -> tuple[int, int]:
    """Return (visible_width, visible_height) after applying pixel_mapper transforms."""
    cols = options.cols
    rows = options.rows
    chain = options.chain_length
    parallel = options.parallel
    mapper = getattr(options, "pixel_mapper_config", "") or ""

    w = cols * chain
    h = rows * parallel
    for part in mapper.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, param = part.partition(":")
        name = name.strip().lower()
        param = param.strip()
        if name == "rotate":
            angle = (int(param) + 360) % 360 if param else 0
            if angle % 180 != 0:
                w, h = h, w
        elif name == "u-mapper":
            w, h = (w // 64) * 32, 2 * h
        elif name == "v-mapper":
            w, h = w * parallel // chain, h * chain // parallel
        elif name == "stacktorow":
            w, h = w * parallel, h // parallel
        elif name == "remap":
            dims = param.split("|")[0].split(",")
            w, h = int(dims[0]), int(dims[1])
    return w, h


class RGBMatrixOptions:
    def __init__(self) -> None:
        self.hardware_mapping = "EMULATED"
        self.rows = 32
        self.cols = 32
        self.chain_length = 1
        self.parallel = 1
        self.row_address_type = 0
        self.multiplexing = 0
        self.pwm_bits = 0
        self.brightness = 100
        self.pwm_lsb_nanoseconds = 130
        self.led_rgb_sequence = "RGB-EMULATED"
        self.show_refresh_rate = 0
        self.gpio_slowdown = None
        self.disable_hardware_pulsing = False

        emulator_config = RGBMatrixEmulatorConfig()

        self.display_adapter = emulator_config.display_adapter
        self.pixel_style = emulator_config.pixel_style
        self.pixel_glow = emulator_config.pixel_glow
        self.pixel_size = emulator_config.pixel_size
        self.pixel_outline = emulator_config.DEFAULT_CONFIG["pixel_outline"]
        self.pixel_outline = emulator_config.pixel_outline

        # Browser Adapter
        self.browser = emulator_config.browser
        self.emulator_title = emulator_config.emulator_title
        self.icon_path = emulator_config.icon_path

        # Pi5 Adapter
        self.pi5 = emulator_config.pi5

    def window_size(self) -> tuple[int, int]:
        w, h = visible_dims(self)
        return (w * self.pixel_size, h * self.pixel_size)

    def window_size_str(self, pixel_text: str = "") -> str:
        width, height = self.window_size()

        return f"{width} x {height} {pixel_text}"
