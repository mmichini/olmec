// Olmec Digital Twin — Canvas-based animated face

const canvas = document.getElementById('olmec-canvas');
const ctx = canvas.getContext('2d');

let currentAmplitude = 0;
let targetAmplitude = 0;
let currentState = '--';
let isListening = false;
let lastJudge = null;  // { correct, confidence, transcription, expected }
let ws = null;

// --- WebSocket ---

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        document.getElementById('debug-connection').className = 'connected';
        document.getElementById('debug-connection').textContent = 'Connected';
    };

    ws.onclose = () => {
        document.getElementById('debug-connection').className = 'disconnected';
        document.getElementById('debug-connection').textContent = 'Disconnected';
        setTimeout(connect, 2000);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'amplitude') {
            targetAmplitude = msg.data.rms;
            document.getElementById('debug-amplitude').textContent = msg.data.rms.toFixed(4);
            document.getElementById('amplitude-fill').style.width = (msg.data.rms * 100) + '%';
        } else if (msg.type === 'listening') {
            isListening = msg.data.active;
            document.getElementById('debug-listening').textContent = isListening ? 'LISTENING' : 'Off';
            document.getElementById('debug-listening').className = isListening ? 'listening-active' : '';
        } else if (msg.type === 'stt') {
            isListening = false;
            document.getElementById('debug-listening').textContent = 'Off';
            document.getElementById('debug-listening').className = '';
            document.getElementById('debug-stt').textContent = msg.data.text
                ? `"${msg.data.text}"`
                : '(no speech)';
        } else if (msg.type === 'auto_judge') {
            lastJudge = msg.data;
            const result = msg.data.correct ? 'CORRECT' : 'INCORRECT';
            const conf = Math.round(msg.data.confidence * 100);
            document.getElementById('debug-stt').textContent =
                `"${msg.data.transcription}" → ${result} (${conf}%)`;
            document.getElementById('debug-judge').textContent =
                `${result} — ${conf}% confidence`;
            document.getElementById('debug-judge').className =
                msg.data.correct ? 'judge-correct' : 'judge-incorrect';
            if (!msg.data.correct) {
                document.getElementById('debug-expected').textContent =
                    `Expected: ${msg.data.expected}`;
            } else {
                document.getElementById('debug-expected').textContent = '';
            }
        } else if (msg.type === 'state') {
            currentState = msg.data.display_state;
            document.getElementById('debug-state').textContent = currentState;
            // Clear info when a new question starts (not on idle)
            if (msg.data.quiz_state === 'asking') {
                lastJudge = null;
                document.getElementById('debug-judge').textContent = '--';
                document.getElementById('debug-judge').className = '';
                document.getElementById('debug-expected').textContent = '';
                document.getElementById('debug-stt').textContent = '--';
            }
        } else if (msg.type === 'play_audio') {
            // Only play in browser if server tells us to (e.g., not on Pi)
            if (msg.data.url && msg.data.play_in_browser !== false) {
                playAudio(msg.data.url);
            }
        }
    };
}

// --- Olmec Face Drawing ---

function drawFace() {
    const w = canvas.width;
    const h = canvas.height;

    // Smooth amplitude
    currentAmplitude += (targetAmplitude - currentAmplitude) * 0.3;

    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, w, h);

    // Head shape — stone-like Olmec head
    const cx = w / 2;
    const cy = h * 0.42;

    // Head outline
    ctx.save();
    ctx.beginPath();
    // Rounded trapezoidal head shape
    ctx.moveTo(cx - 160, cy - 180);  // top left
    ctx.quadraticCurveTo(cx, cy - 220, cx + 160, cy - 180);  // top
    ctx.quadraticCurveTo(cx + 200, cy, cx + 170, cy + 140);  // right
    ctx.quadraticCurveTo(cx, cy + 180, cx - 170, cy + 140);  // bottom
    ctx.quadraticCurveTo(cx - 200, cy, cx - 160, cy - 180);  // left
    ctx.closePath();
    ctx.fillStyle = '#3a3529';
    ctx.fill();
    ctx.strokeStyle = '#2a2519';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.restore();

    // Headdress / helmet
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx - 180, cy - 120);
    ctx.quadraticCurveTo(cx, cy - 240, cx + 180, cy - 120);
    ctx.strokeStyle = '#4a4535';
    ctx.lineWidth = 8;
    ctx.stroke();
    ctx.restore();

    // Nose
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx - 20, cy - 20);
    ctx.lineTo(cx, cy + 30);
    ctx.lineTo(cx + 20, cy - 20);
    ctx.strokeStyle = '#2a2519';
    ctx.lineWidth = 3;
    ctx.stroke();
    // Nostrils
    ctx.beginPath();
    ctx.ellipse(cx - 12, cy + 25, 8, 5, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 12, cy + 25, 8, 5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#2a2015';
    ctx.fill();
    ctx.restore();

    // Eyes — THE MAIN EVENT
    const eyeY = cy - 50;
    const eyeSpacing = 70;
    const eyeGlow = currentAmplitude;

    drawEye(cx - eyeSpacing, eyeY, eyeGlow);
    drawEye(cx + eyeSpacing, eyeY, eyeGlow);

    // Mouth — slight open based on amplitude
    const mouthOpen = currentAmplitude * 15;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx - 50, cy + 70);
    ctx.quadraticCurveTo(cx, cy + 70 + mouthOpen + 5, cx + 50, cy + 70);
    if (mouthOpen > 2) {
        ctx.quadraticCurveTo(cx, cy + 70 + mouthOpen + 15, cx - 50, cy + 70);
        ctx.fillStyle = '#1a1510';
        ctx.fill();
    }
    ctx.strokeStyle = '#2a2519';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.restore();

    // Chin line
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx - 80, cy + 100);
    ctx.quadraticCurveTo(cx, cy + 130, cx + 80, cy + 100);
    ctx.strokeStyle = '#2a2519';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();

    // Status text
    ctx.save();
    ctx.fillStyle = '#444';
    ctx.font = '14px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText(currentState.toUpperCase(), cx, h - 20);
    ctx.restore();

    requestAnimationFrame(drawFace);
}

function drawEye(x, y, glow) {
    const eyeWidth = 35;
    const eyeHeight = 20;

    // Eye socket shadow
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x, y, eyeWidth + 5, eyeHeight + 5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#1a1510';
    ctx.fill();
    ctx.restore();

    // Eye shape
    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x, y, eyeWidth, eyeHeight, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#1a1510';
    ctx.fill();
    ctx.restore();

    // Red glow
    if (glow > 0.01) {
        // Outer glow
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, eyeWidth * 2);
        const alpha = glow * 0.5;
        gradient.addColorStop(0, `rgba(255, 50, 20, ${alpha})`);
        gradient.addColorStop(0.5, `rgba(255, 20, 0, ${alpha * 0.3})`);
        gradient.addColorStop(1, 'rgba(255, 0, 0, 0)');
        ctx.save();
        ctx.fillStyle = gradient;
        ctx.fillRect(x - eyeWidth * 2, y - eyeWidth * 2, eyeWidth * 4, eyeWidth * 4);
        ctx.restore();

        // Inner eye glow
        ctx.save();
        ctx.beginPath();
        ctx.ellipse(x, y, eyeWidth - 2, eyeHeight - 2, 0, 0, Math.PI * 2);
        const innerGradient = ctx.createRadialGradient(x, y, 0, x, y, eyeWidth);
        innerGradient.addColorStop(0, `rgba(255, 80, 30, ${glow})`);
        innerGradient.addColorStop(0.7, `rgba(200, 20, 0, ${glow * 0.6})`);
        innerGradient.addColorStop(1, `rgba(100, 0, 0, ${glow * 0.2})`);
        ctx.fillStyle = innerGradient;
        ctx.fill();
        ctx.restore();

        // Bright center
        ctx.save();
        ctx.beginPath();
        ctx.ellipse(x, y, 8, 5, 0, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 200, 150, ${glow * 0.8})`;
        ctx.fill();
        ctx.restore();
    }
}

// --- Audio playback ---
let audioUnlocked = false;
let currentAudio = null;

function unlockAudio() {
    if (audioUnlocked) return;
    // Play a silent buffer to unlock audio context
    const a = new Audio();
    a.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    a.play().then(() => { audioUnlocked = true; }).catch(() => {});
}

// Unlock audio on first user interaction
document.addEventListener('click', unlockAudio, { once: true });
document.addEventListener('touchstart', unlockAudio, { once: true });

function playAudio(url) {
    console.log('Playing audio:', url);
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
    currentAudio = new Audio(url);
    currentAudio.play().then(() => {
        document.getElementById('audio-unlock-prompt').style.display = 'none';
    }).catch(e => {
        console.warn('Audio play blocked — click the page first:', e);
        document.getElementById('audio-unlock-prompt').style.display = 'block';
    });
}

// --- Init ---
connect();
drawFace();
