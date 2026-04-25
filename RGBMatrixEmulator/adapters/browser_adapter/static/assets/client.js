(function () {
    const WS_RETRY_DELAY  = 2000;
    const FPS_DEFAULT     = 60;
    const FPS_UPDATE_RATE = 300;
    const GPIO_POLL_MS    = 100;
    const DRAG_STEP       = 5;   // px of vertical drag per encoder tick
    const KNOB_CX         = 45;
    const KNOB_CY         = 45;

    const img       = document.getElementById("liveImg");
    const fpsText   = document.getElementById("fps");
    const fpsTarget = parseInt(document.getElementById("targetFps").value) || FPS_DEFAULT;

    let startTime;
    let nFrames = 0;
    let fps = 0;
    let activeDrag    = null; // { enc, svg, startY, accum }
    let activePotDrag = null; // { pot, svg, min, max, step, startY, value, accum }

    const svgNS = "http://www.w3.org/2000/svg";
    function svgEl(tag) { return document.createElementNS(svgNS, tag); }

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
    const hasControls = (gpioConfig.buttons  && gpioConfig.buttons.length)  ||
                        (gpioConfig.toggles  && gpioConfig.toggles.length)  ||
                        (gpioConfig.rotary_encoders && gpioConfig.rotary_encoders.length) ||
                        (gpioConfig.potentiometers && gpioConfig.potentiometers.length);

    if (hasControls) {
        buildControlsPanel();
        if (gpioConfig.rotary_encoders && gpioConfig.rotary_encoders.length) {
            setupKnobDrag();
        }
        if (gpioConfig.potentiometers && gpioConfig.potentiometers.length) {
            setupPotDrag();
        }
        pollGpio();
    }

    function buildControlsPanel() {
        const content = document.getElementById("controlsContent");

        // Buttons — hold to keep HIGH, release to go LOW
        if (gpioConfig.buttons && gpioConfig.buttons.length) {
            content.appendChild(sectionLabel("BUTTONS"));
            for (const btn of gpioConfig.buttons) {
                const row = el("div", "gpioButton interactive");
                const btnCap = el("div", "btnCap");
                btnCap.id = `led_pin_${btn.pin}`;
                const lbl = el("div", "lbl");
                lbl.textContent = btn.label || `pin ${btn.pin}`;
                row.appendChild(btnCap);
                row.appendChild(lbl);
                if (btn.key) {
                    const keyHint = el("span", "keyHint");
                    keyHint.textContent = `[${btn.key}]`;
                    row.appendChild(keyHint);
                }
                row.addEventListener("mousedown",   () => trigger({type:"button", pin:btn.pin, value:1}));
                row.addEventListener("mouseup",     () => trigger({type:"button", pin:btn.pin, value:0}));
                row.addEventListener("mouseleave",  () => trigger({type:"button", pin:btn.pin, value:0}));
                row.addEventListener("touchstart",  (e) => { e.preventDefault(); trigger({type:"button", pin:btn.pin, value:1}); });
                row.addEventListener("touchend",    () => trigger({type:"button", pin:btn.pin, value:0}));
                content.appendChild(row);
            }
        }

        // Toggles — click to flip; uses horizontal pill (toggleTrack / toggleThumb)
        if (gpioConfig.toggles && gpioConfig.toggles.length) {
            content.appendChild(sectionLabel("TOGGLES"));
            for (const tog of gpioConfig.toggles) {
                const row = el("div", "gpioToggle interactive");
                const toggleTrack = el("div", "toggleTrack");
                toggleTrack.id = `led_pin_${tog.pin}`;
                const toggleThumb = el("div", "toggleThumb");
                toggleTrack.appendChild(toggleThumb);
                const lbl = el("div", "lbl");
                lbl.textContent = tog.label || `pin ${tog.pin}`;
                row.appendChild(toggleTrack);
                row.appendChild(lbl);
                if (tog.key) {
                    const keyHint = el("span", "keyHint");
                    keyHint.textContent = `[${tog.key}]`;
                    row.appendChild(keyHint);
                }
                row.addEventListener("click", () => trigger({type:"toggle", pin:tog.pin}));
                content.appendChild(row);
            }
        }

        // Rotary encoders — guitar knob with drag + scroll
        if (gpioConfig.rotary_encoders && gpioConfig.rotary_encoders.length) {
            const encLabel = gpioConfig.rotary_encoders.length > 1 ? "ENCODERS" : "ENCODER";
            content.appendChild(sectionLabel(encLabel));

            for (const enc of gpioConfig.rotary_encoders) {
                const wrap = el("div", "gpioEncoder");

                // ── Modern flat-ring encoder ──────────────────────────
                const svg = svgEl("svg");
                svg.setAttribute("width", "90");
                svg.setAttribute("height", "90");
                svg.setAttribute("viewBox", "0 0 90 90");
                svg.classList.add("encoderDial");
                svg.id = `dial_${enc.clk_pin}_${enc.dt_pin}`;
                svg.style.cursor = "grab";
                svg.title = "Drag up/down or scroll to turn";

                // Background track (full 360° circle)
                {
                    const ba = svgEl("circle");
                    ba.setAttribute("cx", KNOB_CX); ba.setAttribute("cy", KNOB_CY);
                    ba.setAttribute("r", "36");
                    ba.setAttribute("class", "ringTrack");
                    ba.setAttribute("stroke-width", "5");
                    svg.appendChild(ba);
                }

                // Value arc (amber, fills from 12-o'clock clockwise)
                {
                    const va = svgEl("path");
                    va.setAttribute("fill", "none");
                    va.setAttribute("class", "ringArcEnc");
                    va.setAttribute("stroke-width", "5");
                    va.setAttribute("stroke-linecap", "round");
                    va.id = `arc_${enc.clk_pin}_${enc.dt_pin}`;
                    svg.appendChild(va);
                }

                // Scale ticks — 12 around the full circle, major at cardinals
                for (let i = 0; i < 12; i++) {
                    const angleDeg = i * 30;
                    const angleRad = (angleDeg - 90) * Math.PI / 180;
                    const isMajor  = (i % 3 === 0);
                    const [r1, r2] = isMajor ? [39, 44] : [40, 43];
                    const tick = svgEl("line");
                    tick.setAttribute("x1", KNOB_CX + r1 * Math.cos(angleRad));
                    tick.setAttribute("y1", KNOB_CY + r1 * Math.sin(angleRad));
                    tick.setAttribute("x2", KNOB_CX + r2 * Math.cos(angleRad));
                    tick.setAttribute("y2", KNOB_CY + r2 * Math.sin(angleRad));
                    tick.setAttribute("class", isMajor ? "ringTickMajor" : "ringTick");
                    tick.setAttribute("stroke-width", isMajor ? "1.5" : "1");
                    svg.appendChild(tick);
                }

                // Center fill
                {
                    const cc = svgEl("circle");
                    cc.setAttribute("cx", KNOB_CX); cc.setAttribute("cy", KNOB_CY);
                    cc.setAttribute("r", "28");
                    cc.setAttribute("class", "ringCenter");
                    svg.appendChild(cc);
                }

                // Value label inside ring
                {
                    const vt = svgEl("text");
                    vt.setAttribute("x", KNOB_CX); vt.setAttribute("y", KNOB_CY);
                    vt.setAttribute("text-anchor", "middle");
                    vt.setAttribute("dominant-baseline", "central");
                    vt.setAttribute("class", "ringValueText");
                    vt.id = `encval_${enc.clk_pin}_${enc.dt_pin}`;
                    vt.textContent = "0";
                    svg.appendChild(vt);
                }

                // Rotating indicator group
                const knobGroup = svgEl("g");
                knobGroup.id = `knob_${enc.clk_pin}_${enc.dt_pin}`;
                {
                    const dot = svgEl("circle");
                    dot.setAttribute("cx", KNOB_CX); dot.setAttribute("cy", KNOB_CY - 32);
                    dot.setAttribute("r", "3");
                    dot.setAttribute("class", "ringIndicatorEnc");
                    knobGroup.appendChild(dot);
                }
                svg.appendChild(knobGroup);

                // Mouse drag events (per-knob mousedown; global move/up in setupKnobDrag)
                svg.addEventListener("mousedown", (e) => {
                    e.preventDefault();
                    activeDrag = { enc, svg, startY: e.clientY, accum: 0 };
                    svg.style.cursor = "grabbing";
                    document.body.style.userSelect = "none";
                });

                // Touch drag events (handled per-element for better multi-knob support)
                svg.addEventListener("touchstart", (e) => {
                    e.preventDefault();
                    const t = e.touches[0];
                    activeDrag = { enc, svg, startY: t.clientY, accum: 0 };
                }, { passive: false });

                svg.addEventListener("touchmove", (e) => {
                    e.preventDefault();
                    if (!activeDrag) return;
                    const t = e.touches[0];
                    const dy = t.clientY - activeDrag.startY;
                    activeDrag.startY = t.clientY;
                    activeDrag.accum += dy;
                    flushDragAccum();
                }, { passive: false });

                svg.addEventListener("touchend", () => {
                    if (activeDrag && activeDrag.svg === svg) {
                        activeDrag.svg.style.cursor = "grab";
                        activeDrag = null;
                    }
                });

                // Scroll wheel
                svg.addEventListener("wheel", (e) => {
                    e.preventDefault();
                    const dir = e.deltaY < 0 ? "cw" : "ccw";
                    trigger({type:"encoder", clk_pin:enc.clk_pin, dt_pin:enc.dt_pin, direction:dir});
                }, { passive: false });

                wrap.appendChild(svg);

                // ◀ value ▶ row
                const dialRow = el("div", "encoderDialRow");
                const btnCCW = el("button", "encBtn");
                btnCCW.textContent = "◀";
                btnCCW.title = "Counter-clockwise";
                btnCCW.addEventListener("click", () => trigger({type:"encoder", clk_pin:enc.clk_pin, dt_pin:enc.dt_pin, direction:"ccw"}));

                const btnCW = el("button", "encBtn");
                btnCW.textContent = "▶";
                btnCW.title = "Clockwise";
                btnCW.addEventListener("click", () => trigger({type:"encoder", clk_pin:enc.clk_pin, dt_pin:enc.dt_pin, direction:"cw"}));

                dialRow.appendChild(btnCCW);
                dialRow.appendChild(btnCW);
                wrap.appendChild(dialRow);

                // CLK / DT indicators
                const pinsDiv = el("div", "encoderPins");
                for (const [label, pin] of [["CLK", enc.clk_pin], ["DT", enc.dt_pin]]) {
                    const pinRow = el("div", "encoderPin");
                    const led = el("div", "led");
                    led.id = `led_pin_${pin}`;
                    const lbl = el("div", "lbl");
                    lbl.textContent = `${label} ${pin}`;
                    pinRow.appendChild(led);
                    pinRow.appendChild(lbl);
                    pinsDiv.appendChild(pinRow);
                }
                wrap.appendChild(pinsDiv);

                // Optional shaft button
                if (enc.sw_pin != null) {
                    const divider = el("div", "encoderDivider");
                    wrap.appendChild(divider);
                    const swLabel = el("div", "encoderSwLabel");
                    swLabel.textContent = "PUSH";
                    wrap.appendChild(swLabel);

                    const swRow = el("div", "gpioButton interactive");
                    const swCap = el("div", "btnCap");
                    swCap.id = `led_pin_${enc.sw_pin}`;
                    const swLbl = el("div", "lbl");
                    swLbl.textContent = `SW pin ${enc.sw_pin}`;
                    swRow.appendChild(swCap);
                    swRow.appendChild(swLbl);
                    if (enc.key_sw) {
                        const swKeyHint = el("span", "keyHint");
                        swKeyHint.textContent = `[${enc.key_sw}]`;
                        swRow.appendChild(swKeyHint);
                    }
                    swRow.addEventListener("mousedown",  () => trigger({type:"button", pin:enc.sw_pin, value:1}));
                    swRow.addEventListener("mouseup",    () => trigger({type:"button", pin:enc.sw_pin, value:0}));
                    swRow.addEventListener("mouseleave", () => trigger({type:"button", pin:enc.sw_pin, value:0}));
                    wrap.appendChild(swRow);
                }

                content.appendChild(wrap);
            }
        }

        // Potentiometers — knob with drag + scroll
        if (gpioConfig.potentiometers && gpioConfig.potentiometers.length) {
            const potLabel = gpioConfig.potentiometers.length > 1 ? "POTENTIOMETERS" : "POTENTIOMETER";
            content.appendChild(sectionLabel(potLabel));

            for (const pot of gpioConfig.potentiometers) {
                const min  = parseFloat(pot.min  ?? 0);
                const max  = parseFloat(pot.max  ?? 100);
                const step = parseFloat(pot.step ?? 1);

                const wrap = el("div", "gpioPot");

                // ── Modern flat-ring potentiometer ────────────────────
                const svg = svgEl("svg");
                svg.setAttribute("width",   "90");
                svg.setAttribute("height",  "90");
                svg.setAttribute("viewBox", "0 0 90 90");
                svg.classList.add("potDial");
                svg.id            = `pot_dial_${pot.pin}`;
                svg.style.cursor  = "grab";
                svg.title         = "Drag up/down or scroll to adjust";
                svg.dataset.value = String(min);
                svg.dataset.min   = String(min);
                svg.dataset.max   = String(max);
                svg.dataset.step  = String(step);
                svg.dataset.pin   = String(pot.pin);

                // Background track (300°, 7-o'clock to 5-o'clock)
                {
                    const ba = svgEl("path");
                    ba.setAttribute("fill", "none");
                    ba.setAttribute("class", "ringTrack");
                    ba.setAttribute("stroke-width", "5");
                    ba.setAttribute("stroke-linecap", "round");
                    ba.setAttribute("d", describeArc(KNOB_CX, KNOB_CY, 36, 210, 510));
                    svg.appendChild(ba);
                }

                // Value arc (teal)
                {
                    const va = svgEl("path");
                    va.setAttribute("fill", "none");
                    va.setAttribute("class", "ringArcPot");
                    va.setAttribute("stroke-width", "5");
                    va.setAttribute("stroke-linecap", "round");
                    va.id = `pot_arc_${pot.pin}`;
                    svg.appendChild(va);
                }

                // Scale ticks
                for (let i = 0; i <= 10; i++) {
                    const angleDeg = 210 + i * 30;
                    const angleRad = (angleDeg - 90) * Math.PI / 180;
                    const isMajor  = (i === 0 || i === 5 || i === 10);
                    const [r1, r2] = isMajor ? [39, 44] : [40, 43];
                    const tick = svgEl("line");
                    tick.setAttribute("x1", KNOB_CX + r1 * Math.cos(angleRad));
                    tick.setAttribute("y1", KNOB_CY + r1 * Math.sin(angleRad));
                    tick.setAttribute("x2", KNOB_CX + r2 * Math.cos(angleRad));
                    tick.setAttribute("y2", KNOB_CY + r2 * Math.sin(angleRad));
                    tick.setAttribute("class", isMajor ? "ringTickMajor" : "ringTick");
                    tick.setAttribute("stroke-width", isMajor ? "1.5" : "1");
                    svg.appendChild(tick);
                }

                // Center fill
                {
                    const cc = svgEl("circle");
                    cc.setAttribute("cx", KNOB_CX); cc.setAttribute("cy", KNOB_CY);
                    cc.setAttribute("r", "28");
                    cc.setAttribute("class", "ringCenter");
                    svg.appendChild(cc);
                }

                // Value label inside ring
                {
                    const vt = svgEl("text");
                    vt.setAttribute("x", KNOB_CX); vt.setAttribute("y", KNOB_CY);
                    vt.setAttribute("text-anchor", "middle");
                    vt.setAttribute("dominant-baseline", "central");
                    vt.setAttribute("class", "ringValueText ringValueTextPot");
                    vt.id = `pot_val_${pot.pin}`;
                    vt.textContent = String(min);
                    svg.appendChild(vt);
                }

                // Rotating indicator group
                const knobGroup = svgEl("g");
                knobGroup.id = `pot_knob_${pot.pin}`;
                {
                    const dot = svgEl("circle");
                    dot.setAttribute("cx", KNOB_CX); dot.setAttribute("cy", KNOB_CY - 32);
                    dot.setAttribute("r", "3");
                    dot.setAttribute("class", "ringIndicatorPot");
                    knobGroup.appendChild(dot);
                }
                svg.appendChild(knobGroup);
                updatePotKnob(pot.pin, min, min, max, step);

                svg.addEventListener("mousedown", (e) => {
                    e.preventDefault();
                    activePotDrag = { pot, svg, min, max, step, startY: e.clientY, value: parseFloat(svg.dataset.value), accum: 0 };
                    svg.style.cursor = "grabbing";
                    document.body.style.userSelect = "none";
                });

                svg.addEventListener("touchstart", (e) => {
                    e.preventDefault();
                    const t = e.touches[0];
                    activePotDrag = { pot, svg, min, max, step, startY: t.clientY, value: parseFloat(svg.dataset.value), accum: 0 };
                }, { passive: false });

                svg.addEventListener("touchmove", (e) => {
                    e.preventDefault();
                    if (!activePotDrag || activePotDrag.svg !== svg) return;
                    const t = e.touches[0];
                    activePotDrag.accum += t.clientY - activePotDrag.startY;
                    activePotDrag.startY = t.clientY;
                    flushPotDragAccum();
                }, { passive: false });

                svg.addEventListener("touchend", () => {
                    if (activePotDrag && activePotDrag.svg === svg) {
                        activePotDrag.svg.style.cursor = "grab";
                        activePotDrag = null;
                    }
                });

                svg.addEventListener("wheel", (e) => {
                    e.preventDefault();
                    const cur = parseFloat(svg.dataset.value);
                    const nv  = e.deltaY < 0 ? Math.min(max, cur + step) : Math.max(min, cur - step);
                    updatePotKnob(pot.pin, nv, min, max, step);
                    trigger({type:"pot", pin:pot.pin, value:nv});
                }, { passive: false });

                wrap.appendChild(svg);

                const lbl = el("div", "potLabel");
                lbl.textContent = pot.label || `pin ${pot.pin}`;
                wrap.appendChild(lbl);

                const rangeRow = el("div", "potRangeRow");
                const minLbl = el("span", "potRangeLabel"); minLbl.textContent = min;
                const maxLbl = el("span", "potRangeLabel"); maxLbl.textContent = max;
                rangeRow.appendChild(minLbl);
                rangeRow.appendChild(maxLbl);
                wrap.appendChild(rangeRow);

                content.appendChild(wrap);
            }
        }
    }

    // ── Knob drag (global mouse handlers, set up once) ────────────────

    function flushDragAccum() {
        if (!activeDrag) return;
        while (activeDrag.accum >= DRAG_STEP) {
            trigger({type:"encoder", clk_pin:activeDrag.enc.clk_pin, dt_pin:activeDrag.enc.dt_pin, direction:"ccw"});
            activeDrag.accum -= DRAG_STEP;
        }
        while (activeDrag.accum <= -DRAG_STEP) {
            trigger({type:"encoder", clk_pin:activeDrag.enc.clk_pin, dt_pin:activeDrag.enc.dt_pin, direction:"cw"});
            activeDrag.accum += DRAG_STEP;
        }
    }

    function setupKnobDrag() {
        document.addEventListener("mousemove", (e) => {
            if (!activeDrag) return;
            activeDrag.accum += e.clientY - activeDrag.startY;
            activeDrag.startY = e.clientY;
            flushDragAccum();
        });

        document.addEventListener("mouseup", () => {
            if (!activeDrag) return;
            activeDrag.svg.style.cursor = "grab";
            document.body.style.userSelect = "";
            activeDrag = null;
        });
    }

    // ── Pot knob drag (global mouse handlers, set up once) ───────────

    function setupPotDrag() {
        document.addEventListener("mousemove", (e) => {
            if (!activePotDrag) return;
            activePotDrag.accum += e.clientY - activePotDrag.startY;
            activePotDrag.startY = e.clientY;
            flushPotDragAccum();
        });
        document.addEventListener("mouseup", () => {
            if (!activePotDrag) return;
            activePotDrag.svg.style.cursor = "grab";
            document.body.style.userSelect = "";
            activePotDrag = null;
        });
    }

    function flushPotDragAccum() {
        if (!activePotDrag) return;
        const { min, max, step } = activePotDrag;
        while (activePotDrag.accum >= DRAG_STEP) {
            activePotDrag.value = Math.max(min, +(activePotDrag.value - step).toFixed(10));
            activePotDrag.accum -= DRAG_STEP;
            updatePotKnob(activePotDrag.pot.pin, activePotDrag.value, min, max, step);
            trigger({type:"pot", pin:activePotDrag.pot.pin, value:activePotDrag.value});
        }
        while (activePotDrag.accum <= -DRAG_STEP) {
            activePotDrag.value = Math.min(max, +(activePotDrag.value + step).toFixed(10));
            activePotDrag.accum += DRAG_STEP;
            updatePotKnob(activePotDrag.pot.pin, activePotDrag.value, min, max, step);
            trigger({type:"pot", pin:activePotDrag.pot.pin, value:activePotDrag.value});
        }
    }

    function updatePotKnob(pin, value, min, max, step) {
        const fraction  = (max === min) ? 0 : (value - min) / (max - min);
        const knobGroup = document.getElementById(`pot_knob_${pin}`);
        const arc       = document.getElementById(`pot_arc_${pin}`);
        const valSpan   = document.getElementById(`pot_val_${pin}`);
        const dialSvg   = document.getElementById(`pot_dial_${pin}`);

        if (knobGroup) knobGroup.setAttribute("transform", `rotate(${210 + fraction * 300}, ${KNOB_CX}, ${KNOB_CY})`);
        if (arc) {
            const span = fraction * 300;
            arc.setAttribute("d", span > 0 ? describeArc(KNOB_CX, KNOB_CY, 36, 210, 210 + span) : "");
        }
        if (valSpan) {
            const s = step ?? (dialSvg ? parseFloat(dialSvg.dataset.step) : 1);
            const decimals = String(s).includes(".") ? String(s).split(".")[1].length : 0;
            valSpan.textContent = typeof value === "number" ? value.toFixed(decimals) : String(value);
        }
        if (dialSvg) dialSvg.dataset.value = String(value);
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
                // Update all pin LEDs
                for (const [pin, state] of Object.entries(data.pins)) {
                    const led = document.getElementById(`led_pin_${pin}`);
                    if (led) led.classList.toggle("on", state === 1);
                }
                // Update encoder knob rotation and value arc
                for (const [key, val] of Object.entries(data.encoders)) {
                    const [clk, dt] = key.split("_");
                    const knobGroup = document.getElementById(`knob_${clk}_${dt}`);
                    const arc       = document.getElementById(`arc_${clk}_${dt}`);
                    const valDiv    = document.getElementById(`encval_${clk}_${dt}`);
                    if (knobGroup) {
                        const angleDeg = (val * 15 % 360 + 360) % 360;
                        knobGroup.setAttribute("transform", `rotate(${angleDeg}, ${KNOB_CX}, ${KNOB_CY})`);
                    }
                    if (arc) {
                        // Map value into full 360° arc starting at 12-o'clock
                        const arcSpan = ((val * 15 % 360) + 360) % 360;
                        arc.setAttribute("d", arcSpan > 0 ? describeArc(KNOB_CX, KNOB_CY, 36, 0, arcSpan) : "");
                    }
                    if (valDiv) valDiv.textContent = String(val);
                }
                // Update potentiometer knobs
                for (const [pin, val] of Object.entries(data.pots || {})) {
                    const dialSvg = document.getElementById(`pot_dial_${pin}`);
                    if (dialSvg) {
                        updatePotKnob(
                            parseInt(pin), val,
                            parseFloat(dialSvg.dataset.min),
                            parseFloat(dialSvg.dataset.max),
                            parseFloat(dialSvg.dataset.step)
                        );
                    }
                }
            })
            .catch(() => {})
            .finally(() => { setTimeout(pollGpio, GPIO_POLL_MS); });
    }

    // Returns an SVG arc path; 0° = 12-o'clock, clockwise sweep
    function describeArc(cx, cy, r, startDeg, endDeg) {
        const toRad = d => (d - 90) * Math.PI / 180;
        const x1 = cx + r * Math.cos(toRad(startDeg));
        const y1 = cy + r * Math.sin(toRad(startDeg));
        const x2 = cx + r * Math.cos(toRad(endDeg));
        const y2 = cy + r * Math.sin(toRad(endDeg));
        const large = Math.abs(endDeg - startDeg) > 180 ? 1 : 0;
        return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
    }

    // ── Helpers ───────────────────────────────────────────────────────

    function el(tag, cls) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        return e;
    }

    function sectionLabel(text) {
        const d = el("div", "sectionLabel");
        d.textContent = text;
        return d;
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

        // Determine initial theme: saved preference > system preference > dark
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

        // Sync with system changes when no manual preference is saved
        if (window.matchMedia) {
            window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", (e) => {
                if (!localStorage.getItem(STORAGE_KEY)) {
                    applyTheme(e.matches ? "light" : "dark");
                }
            });
        }
    })();

})();
