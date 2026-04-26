(function () {
    const WS_RETRY_DELAY  = 2000;
    const FPS_DEFAULT     = 60;
    const FPS_UPDATE_RATE = 300;
    const GPIO_POLL_MS    = 50;

    const canvas    = document.getElementById("liveImg");
    const ctx       = canvas.getContext("2d", { alpha: false });
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

    const INDICATOR_COLORS = {
        green:  "#3fb950", red:    "#f85149", yellow: "#f0e68c",
        blue:   "#58a6ff", orange: "#f0883e", white:  "#e6edf3",
        cyan:   "#39d353", purple: "#bc8cff"
    };

    const gpioConfig = (typeof GPIO_CONFIG !== "undefined") ? GPIO_CONFIG : {};
    const hasControls = (gpioConfig.buttons          && gpioConfig.buttons.length)          ||
                        (gpioConfig.rgb_leds         && gpioConfig.rgb_leds.length)         ||
                        (gpioConfig.toggles          && gpioConfig.toggles.length)          ||
                        (gpioConfig.rotary_encoders  && gpioConfig.rotary_encoders.length)  ||
                        (gpioConfig.potentiometers   && gpioConfig.potentiometers.length)   ||
                        (gpioConfig.indicators       && gpioConfig.indicators.length);

    if (hasControls) {
        buildControlsPanel();
        pollGpio();
    }

    function buildControlsPanel() {
        const content = document.getElementById("controlsContent");

        const buttons = gpioConfig.buttons || [];
        for (let i = 0; i < buttons.length; i++) {
            const btn = buttons[i];
            const wrap = el("div", "hardBtnWrap");
            const cap  = el("div", "hardBtnCap");
            cap.id = `led_pin_${btn.pin}`;

            cap.addEventListener("mousedown",   () => trigger({type:"button", pin:btn.pin, value:0}));
            cap.addEventListener("mouseup",     () => trigger({type:"button", pin:btn.pin, value:1}));
            cap.addEventListener("mouseleave",  () => trigger({type:"button", pin:btn.pin, value:1}));
            cap.addEventListener("touchstart",  (e) => { e.preventDefault(); trigger({type:"button", pin:btn.pin, value:0}); });
            cap.addEventListener("touchend",    () => trigger({type:"button", pin:btn.pin, value:1}));

            const lbl = el("div", "hardBtnLabel");
            lbl.textContent = btn.key || `BTN ${i + 1}`;

            wrap.appendChild(cap);
            wrap.appendChild(lbl);
            content.appendChild(wrap);
        }

        const toggles = gpioConfig.toggles || [];
        for (let i = 0; i < toggles.length; i++) {
            const tog = toggles[i];
            const wrap   = el("div", "toggleWrap");
            const sw     = el("div", "toggleSwitch");
            const thumb  = el("div", "toggleThumb");
            sw.id = `toggle_pin_${tog.pin}`;

            sw.appendChild(thumb);

            sw.addEventListener("click", () => trigger({type: "toggle", pin: tog.pin}));

            const lbl = el("div", "hardBtnLabel");
            lbl.textContent = tog.key || `SW ${i + 1}`;

            wrap.appendChild(sw);
            wrap.appendChild(lbl);
            content.appendChild(wrap);
        }

        const encoders = gpioConfig.rotary_encoders || [];
        for (let i = 0; i < encoders.length; i++) {
            const enc = encoders[i];
            const wrap  = el("div", "encoderWrap");
            const outer = el("div", "encoderDialOuter");
            outer.id = `encoder_${enc.clk_pin}_${enc.dt_pin}`;

            const inner = el("div", "encoderDialInner");
            outer.appendChild(inner);

            const svg = makeSvg(64, 64);
            svg.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;";
            const pointer = document.createElementNS("http://www.w3.org/2000/svg", "line");
            pointer.setAttribute("x1", "32");
            pointer.setAttribute("y1", "32");
            pointer.setAttribute("x2", "32");
            pointer.setAttribute("y2", "8");
            pointer.setAttribute("stroke", "rgba(255,255,255,0.75)");
            pointer.setAttribute("stroke-width", "2");
            pointer.setAttribute("stroke-linecap", "round");
            svg.appendChild(pointer);
            outer.appendChild(svg);

            const cap = el("div", "encoderDialCap");
            cap.id = `encoder_cap_${enc.sw_pin}`;
            outer.appendChild(cap);

            if (enc.sw_pin != null) {
                cap.addEventListener("mousedown",  (e) => { e.stopPropagation(); trigger({type:"button", pin:enc.sw_pin, value:0}); });
                cap.addEventListener("mouseup",    (e) => { e.stopPropagation(); trigger({type:"button", pin:enc.sw_pin, value:1}); });
                cap.addEventListener("mouseleave", (e) => { e.stopPropagation(); trigger({type:"button", pin:enc.sw_pin, value:1}); });
                cap.style.cursor = "pointer";
            }

            outer.addEventListener("wheel", (e) => {
                e.preventDefault();
                const dir = e.deltaY < 0 ? "cw" : "ccw";
                trigger({type:"encoder", clk_pin:enc.clk_pin, dt_pin:enc.dt_pin, direction:dir});
            }, {passive: false});

            let dragStartX = null;
            let dragAccum  = 0;
            outer.addEventListener("mousedown", (e) => {
                if (e.target === cap) return;
                dragStartX = e.clientX;
                dragAccum  = 0;
            });
            document.addEventListener("mousemove", (e) => {
                if (dragStartX === null) return;
                const dx = e.clientX - dragStartX;
                dragAccum += dx;
                dragStartX = e.clientX;
                while (dragAccum >= 8) {
                    trigger({type:"encoder", clk_pin:enc.clk_pin, dt_pin:enc.dt_pin, direction:"cw"});
                    dragAccum -= 8;
                }
                while (dragAccum <= -8) {
                    trigger({type:"encoder", clk_pin:enc.clk_pin, dt_pin:enc.dt_pin, direction:"ccw"});
                    dragAccum += 8;
                }
            });
            document.addEventListener("mouseup", () => { dragStartX = null; });

            const valLbl = el("div", "encoderValueLabel");
            valLbl.id = `encoder_val_${enc.clk_pin}_${enc.dt_pin}`;
            valLbl.textContent = "0";

            const nameLbl = el("div", "hardBtnLabel");
            nameLbl.textContent = enc.key_cw ? `${enc.key_cw}/${enc.key_ccw}` : `ENC ${i + 1}`;

            wrap.appendChild(outer);
            wrap.appendChild(valLbl);
            wrap.appendChild(nameLbl);
            content.appendChild(wrap);
        }

        const pots = gpioConfig.potentiometers || [];
        for (let i = 0; i < pots.length; i++) {
            const pot = pots[i];
            const wrap  = el("div", "potWrap");
            const outer = el("div", "potDialOuter");
            outer.id = `pot_dial_${pot.pin}`;

            const inner = el("div", "potDialInner");
            outer.appendChild(inner);

            const svg = makeSvg(64, 64);
            svg.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;";
            svg.id = `pot_svg_${pot.pin}`;

            const arcTrack = document.createElementNS("http://www.w3.org/2000/svg", "path");
            arcTrack.setAttribute("fill", "none");
            arcTrack.setAttribute("stroke", "rgba(255,255,255,0.10)");
            arcTrack.setAttribute("stroke-width", "3");
            arcTrack.setAttribute("stroke-linecap", "round");
            arcTrack.setAttribute("d", describeArc(32, 32, 26, 225, 495));
            svg.appendChild(arcTrack);

            const arcFill = document.createElementNS("http://www.w3.org/2000/svg", "path");
            arcFill.setAttribute("fill", "none");
            arcFill.setAttribute("stroke", "#58a6ff");
            arcFill.setAttribute("stroke-width", "3");
            arcFill.setAttribute("stroke-linecap", "round");
            arcFill.id = `pot_arc_${pot.pin}`;
            svg.appendChild(arcFill);

            const pointer = document.createElementNS("http://www.w3.org/2000/svg", "line");
            pointer.setAttribute("stroke", "rgba(255,255,255,0.75)");
            pointer.setAttribute("stroke-width", "2");
            pointer.setAttribute("stroke-linecap", "round");
            pointer.id = `pot_ptr_${pot.pin}`;
            svg.appendChild(pointer);

            outer.appendChild(svg);

            const cap = el("div", "potDialCap");
            outer.appendChild(cap);

            outer.addEventListener("wheel", (e) => {
                e.preventDefault();
                const current = parseFloat(outer.dataset.value || pot.min);
                const step    = pot.step || 1;
                const next    = Math.min(pot.max, Math.max(pot.min, current + (e.deltaY < 0 ? step : -step)));
                trigger({type:"pot", pin:pot.pin, value:next});
            }, {passive: false});

            let potDragY    = null;
            let potDragBase = null;
            outer.addEventListener("mousedown", (e) => {
                potDragY    = e.clientY;
                potDragBase = parseFloat(outer.dataset.value || pot.min);
            });
            document.addEventListener("mousemove", (e) => {
                if (potDragY === null) return;
                const dy    = potDragY - e.clientY;
                const range = pot.max - pot.min;
                const delta = (dy / 120) * range;
                const next  = Math.min(pot.max, Math.max(pot.min, potDragBase + delta));
                trigger({type:"pot", pin:pot.pin, value:next});
            });
            document.addEventListener("mouseup", () => { potDragY = null; });

            const valLbl = el("div", "potValueLabel");
            valLbl.id = `pot_val_${pot.pin}`;
            valLbl.textContent = String(pot.min);

            const nameLbl = el("div", "hardBtnLabel");
            nameLbl.textContent = pot.label || `POT ${i + 1}`;

            wrap.appendChild(outer);
            wrap.appendChild(valLbl);
            wrap.appendChild(nameLbl);
            content.appendChild(wrap);
        }

        const rgbLeds = gpioConfig.rgb_leds || [];
        for (let j = 0; j < rgbLeds.length; j++) {
            const led  = rgbLeds[j];
            const wrap = el("div", "neopixelWrap");
            const rect = el("div", "neopixelRect");
            rect.id = `rgb_pin_${led.pin}`;

            const lbl = el("div", "hardBtnLabel");
            lbl.textContent = led.label || "NEOPIXEL";

            wrap.appendChild(rect);
            wrap.appendChild(lbl);
            content.appendChild(wrap);
        }

        const indicators = gpioConfig.indicators || [];
        for (let i = 0; i < indicators.length; i++) {
            const ind  = indicators[i];
            const wrap = el("div", "indicatorWrap");
            const dot  = el("div", "indicatorDot");
            dot.id = `indicator_pin_${ind.pin}`;
            dot.dataset.color = ind.color || "green";

            const lbl = el("div", "hardBtnLabel");
            lbl.textContent = ind.label || `IND ${i + 1}`;

            wrap.appendChild(dot);
            wrap.appendChild(lbl);
            content.appendChild(wrap);
        }
    }

    function makeSvg(w, h) {
        const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        s.setAttribute("width", w);
        s.setAttribute("height", h);
        s.setAttribute("viewBox", `0 0 ${w} ${h}`);
        return s;
    }

    function polarToXY(cx, cy, r, angleDeg) {
        const rad = (angleDeg - 90) * Math.PI / 180;
        return {x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad)};
    }

    function describeArc(cx, cy, r, startDeg, endDeg) {
        const s   = polarToXY(cx, cy, r, startDeg);
        const e   = polarToXY(cx, cy, r, endDeg);
        const lg  = (endDeg - startDeg + 360) % 360 > 180 ? 1 : 0;
        return `M ${s.x} ${s.y} A ${r} ${r} 0 ${lg} 1 ${e.x} ${e.y}`;
    }

    function describeArcFill(cx, cy, r, startDeg, endDeg) {
        if (Math.abs(endDeg - startDeg) < 0.5) return "";
        const sweepDeg = (endDeg - startDeg + 360) % 360;
        const s   = polarToXY(cx, cy, r, startDeg);
        const e   = polarToXY(cx, cy, r, endDeg);
        const lg  = sweepDeg > 180 ? 1 : 0;
        return `M ${s.x} ${s.y} A ${r} ${r} 0 ${lg} 1 ${e.x} ${e.y}`;
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
                for (const [pin, state] of Object.entries(data.pins)) {
                    const led = document.getElementById(`led_pin_${pin}`);
                    if (led) led.classList.toggle("on", state === 0);

                    const tog = document.getElementById(`toggle_pin_${pin}`);
                    if (tog) tog.classList.toggle("on", state === 1);

                    const ind = document.getElementById(`indicator_pin_${pin}`);
                    if (ind) {
                        const isOn = state === 1;
                        const hex  = INDICATOR_COLORS[ind.dataset.color] || INDICATOR_COLORS.green;
                        ind.classList.toggle("on", isOn);
                        if (isOn) {
                            ind.style.background  = hex;
                            ind.style.boxShadow   = `0 0 8px ${hex}, 0 0 16px ${hex}80`;
                            ind.style.borderColor = "transparent";
                        } else {
                            ind.style.background  = "";
                            ind.style.boxShadow   = "";
                            ind.style.borderColor = "";
                        }
                    }

                    const encCap = document.getElementById(`encoder_cap_${pin}`);
                    if (encCap) encCap.classList.toggle("on", state === 0);
                }

                for (const [key, ticks] of Object.entries(data.encoders || {})) {
                    const outer   = document.getElementById(`encoder_${key}`);
                    const valLbl  = document.getElementById(`encoder_val_${key}`);
                    if (outer) {
                        const deg = ((ticks % 24) * 15 + 360) % 360;
                        const svg = outer.querySelector("svg");
                        if (svg) {
                            const line = svg.querySelector("line");
                            if (line) {
                                const rad  = (deg - 90) * Math.PI / 180;
                                const x2   = 32 + 20 * Math.cos(rad);
                                const y2   = 32 + 20 * Math.sin(rad);
                                line.setAttribute("x2", x2.toFixed(2));
                                line.setAttribute("y2", y2.toFixed(2));
                            }
                        }
                    }
                    if (valLbl) valLbl.textContent = String(ticks);
                }

                for (const [pin, value] of Object.entries(data.pots || {})) {
                    const outer  = document.getElementById(`pot_dial_${pin}`);
                    const valLbl = document.getElementById(`pot_val_${pin}`);
                    const arc    = document.getElementById(`pot_arc_${pin}`);
                    const ptr    = document.getElementById(`pot_ptr_${pin}`);

                    if (outer) outer.dataset.value = value;
                    if (valLbl) valLbl.textContent = Number(value).toFixed(1);

                    if (arc || ptr) {
                        const potCfg = (gpioConfig.potentiometers || []).find(p => String(p.pin) === String(pin));
                        if (potCfg) {
                            const min   = potCfg.min;
                            const max   = potCfg.max;
                            const t     = max > min ? (value - min) / (max - min) : 0;
                            const start = 225;
                            const total = 270;
                            const deg   = start + t * total;

                            if (arc) {
                                const d = t > 0.001 ? describeArcFill(32, 32, 26, start, deg) : "";
                                arc.setAttribute("d", d);
                            }

                            if (ptr) {
                                const rad = (deg - 90) * Math.PI / 180;
                                const x2  = 32 + 20 * Math.cos(rad);
                                const y2  = 32 + 20 * Math.sin(rad);
                                ptr.setAttribute("x1", "32");
                                ptr.setAttribute("y1", "32");
                                ptr.setAttribute("x2", x2.toFixed(2));
                                ptr.setAttribute("y2", y2.toFixed(2));
                            }
                        }
                    }
                }

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

            const blob = new Blob([evt.data], { type: "image/jpeg" });
            createImageBitmap(blob).then((bitmap) => {
                if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
                    canvas.width  = bitmap.width;
                    canvas.height = bitmap.height;
                }
                ctx.drawImage(bitmap, 0, 0);
                bitmap.close();
            }).catch(() => {});

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
