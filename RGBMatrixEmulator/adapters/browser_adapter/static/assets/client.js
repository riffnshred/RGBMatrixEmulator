(function () {
    const WS_RETRY_DELAY  = 2000;
    const FPS_DEFAULT     = 60;
    const FPS_UPDATE_RATE = 300;
    const GPIO_POLL_MS    = 100;

    const BTN_LABELS = ["UP/LEFT", "DOWN/RIGHT", "A"];

    const img       = document.getElementById("liveImg");
    const fpsText   = document.getElementById("fps");
    const fpsTarget = parseInt(document.getElementById("targetFps").value) || FPS_DEFAULT;

    let startTime;
    let nFrames = 0;
    let fps = 0;

    // ── WebSocket status indicator ────────────────────────────────────

    const wsStatusEl = document.getElementById("wsStatus");

    function setWsStatus(state) {
        if (!wsStatusEl) return;
        wsStatusEl.className = `wsStatus wsStatus--${state}`;
        wsStatusEl.title = { connecting: "Connecting…", open: "Connected", closed: "Disconnected" }[state] || "";
    }

    setWsStatus("connecting");
    let socket = generateSocket();

    // ── Controls panel ────────────────────────────────────────────────

    const gpioConfig = (typeof GPIO_CONFIG !== "undefined") ? GPIO_CONFIG : {};
    const hasControls = (gpioConfig.buttons  && gpioConfig.buttons.length) ||
                        (gpioConfig.rgb_leds && gpioConfig.rgb_leds.length);

    if (hasControls) {
        buildControlsPanel();
        pollGpio();
    }

    function buildControlsPanel() {
        const content = document.getElementById("controlsContent");

        // 3 rounded-square buttons: UP/LEFT, DOWN/RIGHT, A
        const buttons = gpioConfig.buttons || [];
        for (let i = 0; i < Math.min(3, buttons.length); i++) {
            const btn = buttons[i];
            const wrap = el("div", "hardBtnWrap");
            const cap  = el("div", "hardBtnCap");
            cap.id = `led_pin_${btn.pin}`;

            cap.addEventListener("mousedown",   () => trigger({type:"button", pin:btn.pin, value:1}));
            cap.addEventListener("mouseup",     () => trigger({type:"button", pin:btn.pin, value:0}));
            cap.addEventListener("mouseleave",  () => trigger({type:"button", pin:btn.pin, value:0}));
            cap.addEventListener("touchstart",  (e) => { e.preventDefault(); trigger({type:"button", pin:btn.pin, value:1}); });
            cap.addEventListener("touchend",    () => trigger({type:"button", pin:btn.pin, value:0}));

            const lbl = el("div", "hardBtnLabel");
            lbl.textContent = BTN_LABELS[i];

            wrap.appendChild(cap);
            wrap.appendChild(lbl);
            content.appendChild(wrap);
        }

        // Neopixel — narrow rounded rectangle, driven by rgb_leds[0]
        const rgbLeds = gpioConfig.rgb_leds || [];
        if (rgbLeds.length > 0) {
            const led  = rgbLeds[0];
            const wrap = el("div", "neopixelWrap");
            const rect = el("div", "neopixelRect");
            rect.id = `rgb_pin_${led.pin}`;

            const lbl = el("div", "hardBtnLabel");
            lbl.textContent = led.label || "NEOPIXEL";

            wrap.appendChild(rect);
            wrap.appendChild(lbl);
            content.appendChild(wrap);
        }
    }

    // ── GPIO trigger ──────────────────────────────────────────────────

    function trigger(body) {
        fetch("/gpio/trigger", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
        }).catch(() => {});
    }

    // ── GPIO poll ─────────────────────────────────────────────────────

    function pollGpio() {
        fetch("/gpio")
            .then(r => r.json())
            .then(data => {
                // Update button cap state
                for (const [pin, state] of Object.entries(data.pins)) {
                    const led = document.getElementById(`led_pin_${pin}`);
                    if (led) led.classList.toggle("on", state === 1);
                }

                // Update neopixel rect color
                for (const [pin, rgb] of Object.entries(data.rgb || {})) {
                    const rect = document.getElementById(`rgb_pin_${pin}`);
                    if (rect) {
                        const [r, g, b] = rgb;
                        const isOn = r > 0 || g > 0 || b > 0;
                        rect.style.background = isOn
                            ? `linear-gradient(180deg, rgb(${Math.min(255,r+60)},${Math.min(255,g+60)},${Math.min(255,b+60)}) 0%, rgb(${r},${g},${b}) 100%)`
                            : "";
                        rect.style.boxShadow = isOn
                            ? `0 0 12px rgba(${r},${g},${b},0.7), 0 0 24px rgba(${r},${g},${b},0.3)`
                            : "";
                        rect.style.borderColor = isOn
                            ? `rgba(${Math.min(255,r+40)},${Math.min(255,g+40)},${Math.min(255,b+40)},0.6)`
                            : "";
                        rect.classList.toggle("on", isOn);
                    }
                }
            })
            .catch(() => {})
            .finally(() => { setTimeout(pollGpio, GPIO_POLL_MS); });
    }

    // ── Helpers ───────────────────────────────────────────────────────

    function el(tag, cls) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        return e;
    }

    // ── WebSocket image stream ────────────────────────────────────────

    function generateSocket() {
        let path = location.pathname;

        if (path.endsWith("index.html")) {
            path = path.substring(0, path.length - "index.html".length);
        }

        if (!path.endsWith("/")) {
            path = path + "/";
        }

        const wsProtocol = (location.protocol === "https:") ? "wss://" : "ws://";
        const ws = new WebSocket(wsProtocol + location.host + path + "websocket");

        ws.binaryType = 'arraybuffer';

        ws.onopen = function () {
            console.log("RGBME WebSocket connection established!");
            startTime = performance.now();
            setWsStatus("open");
        };

        ws.onclose = function () {
            console.warn(`RGBME WebSocket connection lost. Retrying in ${WS_RETRY_DELAY / 1000}s.`);
            setWsStatus("closed");
            setTimeout(function () {
                setWsStatus("connecting");
                socket = generateSocket();
            }, WS_RETRY_DELAY);
        };

        ws.onerror = function () {
            ws.close();
        };

        ws.onmessage = function (evt) {
            nFrames++;

            const arrayBuffer = evt.data;
            const blob = new Blob([new Uint8Array(arrayBuffer)], { type: "image/jpeg" });
            const old_img = img.src.slice();
            img.src = window.URL.createObjectURL(blob);
            window.URL.revokeObjectURL(old_img);

            if (fpsText) {
                const endTime = performance.now();
                const deltaT = endTime - startTime;

                if (deltaT > FPS_UPDATE_RATE) {
                    fps = (nFrames / (deltaT / 1000)).toFixed(2);
                    fpsText.textContent = fps;
                    startTime = endTime;
                    nFrames = 0;
                }
            }
        };

        return ws;
    }

    console.log(`TARGET FPS: ${fpsTarget}`);

    // ── Theme toggle ──────────────────────────────────────────────────

    (function initTheme() {
        const root        = document.documentElement;
        const toggleBtn   = document.getElementById("themeToggle");
        const STORAGE_KEY = "rgbme-theme";

        function resolveTheme() {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved === "light" || saved === "dark") return saved;
            if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) return "light";
            return "dark";
        }

        function applyTheme(theme) {
            root.dataset.theme = theme;
            if (toggleBtn) toggleBtn.title = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
        }

        applyTheme(resolveTheme());

        if (toggleBtn) {
            toggleBtn.addEventListener("click", () => {
                const next = root.dataset.theme === "light" ? "dark" : "light";
                applyTheme(next);
                localStorage.setItem(STORAGE_KEY, next);
            });
        }

        if (window.matchMedia) {
            window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", (e) => {
                if (!localStorage.getItem(STORAGE_KEY)) {
                    applyTheme(e.matches ? "light" : "dark");
                }
            });
        }
    })();

})();
