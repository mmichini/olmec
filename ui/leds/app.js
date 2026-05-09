// LED Test UI

let ws = null;

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        document.getElementById('connection-status').className = 'status connected';
        document.getElementById('connection-status').textContent = 'Connected';
        // Request current state
        send({ command: 'led_state' });
    };

    ws.onclose = () => {
        document.getElementById('connection-status').className = 'status disconnected';
        document.getElementById('connection-status').textContent = 'Disconnected';
        setTimeout(connect, 2000);
    };

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'led_state') {
            updateStatus(msg.data);
        }
    };
}

function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
}

function updateStatus(state) {
    document.getElementById('status-test-mode').textContent = state.test_mode ? 'ON' : 'OFF';
    document.getElementById('status-brightness').textContent = (state.brightness * 100).toFixed(0) + '%';
    document.getElementById('status-pattern').textContent = state.pattern_running ? 'running' : '—';
    if (state.eye_colors && state.eye_colors.length === 2) {
        document.getElementById('status-eye0').style.background = rgbStr(state.eye_colors[0]);
        document.getElementById('status-eye1').style.background = rgbStr(state.eye_colors[1]);
    }
    document.getElementById('test-mode-toggle').checked = state.test_mode;
    document.getElementById('brightness-slider').value = Math.round(state.brightness * 100);
    document.getElementById('brightness-value').textContent = Math.round(state.brightness * 100);
}

function rgbStr(rgb) {
    return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

// --- Commands ---

function setTestMode(enabled) {
    send({ command: 'led_test_mode', enabled });
}

function setBrightness(percent) {
    document.getElementById('brightness-value').textContent = percent;
    send({ command: 'led_set_brightness', brightness: parseInt(percent) / 100 });
}

function setBrightnessQuick(percent) {
    document.getElementById('brightness-slider').value = percent;
    setBrightness(percent);
}

function setColor(rgb) {
    send({ command: 'led_set_color', color: rgb });
}

function setCustomColor() {
    const hex = document.getElementById('custom-color').value;
    setColor(hexToRgb(hex));
}

function setEye(eye, rgb) {
    send({ command: 'led_set_eye_color', eye, color: rgb });
}

function setEyeColor(eye, hex) {
    setEye(eye, hexToRgb(hex));
}

function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b];
}

function runPattern(name) {
    send({ command: 'led_pattern', name });
}

function stopPattern() {
    send({ command: 'led_pattern_stop' });
}

function clearAll() {
    send({ command: 'led_clear' });
}

// --- Init ---
connect();
