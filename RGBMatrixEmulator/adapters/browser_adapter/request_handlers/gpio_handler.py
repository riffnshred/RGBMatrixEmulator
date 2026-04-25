import json
from RGBMatrixEmulator.adapters.browser_adapter.request_handlers.base import NoCacheRequestHandler
from RGBMatrixEmulator.emulation import gpio_shim


class GpioHandler(NoCacheRequestHandler):
    """GET /gpio — returns current pin states and encoder values as JSON."""

    def get(self):
        pins = {str(k): v for k, v in gpio_shim._pin_states.items()}
        encoders = {
            f"{clk}_{dt}": val
            for (clk, dt), val in gpio_shim._encoder_values.items()
        }
        pots = {str(k): v for k, v in gpio_shim._pot_values.items()}
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"pins": pins, "encoders": encoders, "pots": pots}))


class GpioTriggerHandler(NoCacheRequestHandler):
    """POST /gpio/trigger — drive a pin or encoder from the browser UI.

    Body shapes:
      {"type": "button",  "pin": 17, "value": 1}          set pin HIGH or LOW
      {"type": "toggle",  "pin": 22}                       flip current state
      {"type": "encoder", "clk_pin": 23, "dt_pin": 24, "direction": "cw"|"ccw"}
    """

    def post(self):
        try:
            body = json.loads(self.request.body)
        except Exception:
            self.set_status(400)
            return

        t = body.get("type")

        if t == "button":
            pin = body["pin"]
            value = int(body["value"])
            gpio_shim._trigger_pin(pin, value)

        elif t == "toggle":
            pin = body["pin"]
            current = gpio_shim.input(pin)
            gpio_shim._trigger_pin(pin, gpio_shim.LOW if current == gpio_shim.HIGH else gpio_shim.HIGH)

        elif t == "encoder":
            clk = body["clk_pin"]
            dt  = body["dt_pin"]
            direction = body.get("direction", "cw")
            gpio_shim._update_encoder(clk, dt, direction)
            if direction == "cw":
                gpio_shim._trigger_pin(clk, gpio_shim.HIGH)
                gpio_shim._trigger_pin(dt,  gpio_shim.HIGH)
                gpio_shim._trigger_pin(clk, gpio_shim.LOW)
                gpio_shim._trigger_pin(dt,  gpio_shim.LOW)
            else:
                gpio_shim._trigger_pin(dt,  gpio_shim.HIGH)
                gpio_shim._trigger_pin(clk, gpio_shim.HIGH)
                gpio_shim._trigger_pin(dt,  gpio_shim.LOW)
                gpio_shim._trigger_pin(clk, gpio_shim.LOW)

        elif t == "pot":
            pin = body["pin"]
            value = float(body["value"])
            gpio_shim._set_pot(pin, value)

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps({"ok": True}))
