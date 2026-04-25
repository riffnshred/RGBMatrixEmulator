"""
Drop-in replacement for RPi.GPIO when running under RGBMatrixEmulator.

Usage in app code:
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        from RGBMatrixEmulator.emulation import gpio_shim as GPIO
"""

# Mode constants
BCM = 11
BOARD = 10

# Direction constants
IN = 1
OUT = 0

# Level constants
HIGH = 1
LOW = 0

# Edge constants
RISING = 31
FALLING = 32
BOTH = 33

# Pull constants
PUD_OFF = 20
PUD_UP = 22
PUD_DOWN = 21

# Module-level state
_pin_states: dict = {}
_pin_modes: dict = {}
_pull: dict = {}
# Maps pin -> list of (edge, callback)
_callbacks: dict = {}
# Tracks pins that have been triggered (for event_detected())
_event_flags: dict = {}

_mode = None


def setmode(mode):
    global _mode
    _mode = mode


def getmode():
    return _mode


def setup(channel, direction, pull_up_down=PUD_OFF, initial=None):
    channels = channel if isinstance(channel, (list, tuple)) else [channel]
    for ch in channels:
        _pin_modes[ch] = direction
        _pull[ch] = pull_up_down
        if initial is not None:
            _pin_states[ch] = initial
        elif pull_up_down == PUD_UP:
            _pin_states[ch] = HIGH
        else:
            _pin_states[ch] = LOW
        if ch not in _callbacks:
            _callbacks[ch] = []
        _event_flags[ch] = False


def input(channel):
    return _pin_states.get(channel, LOW)


def output(channel, value):
    channels = channel if isinstance(channel, (list, tuple)) else [channel]
    values = value if isinstance(value, (list, tuple)) else [value] * len(channels)
    for ch, val in zip(channels, values):
        _trigger_pin(ch, val)


def add_event_detect(channel, edge, callback=None, bouncetime=None):
    if channel not in _callbacks:
        _callbacks[channel] = []
    if callback is not None:
        _callbacks[channel].append((edge, callback))


def add_event_callback(channel, callback):
    if channel not in _callbacks:
        _callbacks[channel] = []
    # Inherit the edge from the first registered detect, default BOTH
    edge = BOTH
    if _callbacks[channel]:
        edge = _callbacks[channel][0][0]
    _callbacks[channel].append((edge, callback))


def remove_event_detect(channel):
    _callbacks[channel] = []
    _event_flags[channel] = False


def event_detected(channel):
    triggered = _event_flags.get(channel, False)
    _event_flags[channel] = False
    return triggered


def cleanup(channel_list=None):
    if channel_list is None:
        _pin_states.clear()
        _pin_modes.clear()
        _pull.clear()
        _callbacks.clear()
        _event_flags.clear()
    else:
        channels = channel_list if isinstance(channel_list, (list, tuple)) else [channel_list]
        for ch in channels:
            _pin_states.pop(ch, None)
            _pin_modes.pop(ch, None)
            _pull.pop(ch, None)
            _callbacks.pop(ch, None)
            _event_flags.pop(ch, None)


def _trigger_pin(pin: int, value: int):
    """Internal: set pin state and fire matching edge callbacks. Called by InputMap."""
    previous = _pin_states.get(pin, LOW)
    _pin_states[pin] = value

    if previous == value:
        return

    rising = value == HIGH
    _event_flags[pin] = True

    for edge, cb in _callbacks.get(pin, []):
        if edge == BOTH:
            cb(pin)
        elif edge == RISING and rising:
            cb(pin)
        elif edge == FALLING and not rising:
            cb(pin)
