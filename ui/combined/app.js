// Olmec Combined UI — Twin + Operator controls

let ws = null;
let state = {};
let audioFiles = {};
let currentQuestion = null;
let isListening = false;

// Twin state
let currentAmplitude = 0;
let targetAmplitude = 0;
let currentState = '--';

const canvas = document.getElementById('olmec-canvas');
const ctx = canvas.getContext('2d');

// --- Panel Toggle ---

let panelOpen = false;

function togglePanel() {
    panelOpen = !panelOpen;
    const panel = document.getElementById('operator-panel');
    const btn = document.getElementById('panel-toggle');
    if (panelOpen) {
        panel.className = 'panel-visible';
        document.body.classList.add('panel-open');
        btn.textContent = 'CLOSE';
    } else {
        panel.className = 'panel-hidden';
        document.body.classList.remove('panel-open');
        btn.textContent = 'CONTROLS';
    }
}

// --- WebSocket ---

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        document.getElementById('connection-status').className = 'status connected';
        document.getElementById('connection-status').textContent = 'Connected';
        document.getElementById('debug-connection').className = 'connected';
        document.getElementById('debug-connection').textContent = 'Connected';
        loadAudioFiles();
    };

    ws.onclose = () => {
        document.getElementById('connection-status').className = 'status disconnected';
        document.getElementById('connection-status').textContent = 'Disconnected';
        document.getElementById('debug-connection').className = 'disconnected';
        document.getElementById('debug-connection').textContent = 'Disconnected';
        setTimeout(connect, 2000);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };
}

function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    }
}

// --- Message handling ---

function handleMessage(msg) {
    if (msg.type === 'amplitude') {
        targetAmplitude = msg.data.rms;
        document.getElementById('debug-amplitude').textContent = msg.data.rms.toFixed(4);
        document.getElementById('amplitude-fill').style.width = (msg.data.rms * 100) + '%';

    } else if (msg.type === 'state') {
        state = msg.data;
        currentState = msg.data.display_state;
        document.getElementById('debug-state').textContent = currentState;
        updateOperatorUI();
        if (msg.data.quiz_state === 'asking') {
            document.getElementById('debug-judge').textContent = '--';
            document.getElementById('debug-judge').className = '';
            document.getElementById('debug-expected').textContent = '';
            document.getElementById('debug-stt').textContent = '--';
        }

    } else if (msg.type === 'volume') {
        document.getElementById('volume-slider').value = Math.round(msg.data.volume * 100);
        document.getElementById('volume-value').textContent = Math.round(msg.data.volume * 100);

    } else if (msg.type === 'question') {
        currentQuestion = msg.data;
        updateQuestionDisplay();

    } else if (msg.type === 'listening') {
        isListening = msg.data.active;
        updateListenButton();
        document.getElementById('debug-listening').textContent = isListening ? 'LISTENING' : 'Off';
        document.getElementById('debug-listening').className = isListening ? 'listening-active' : '';

    } else if (msg.type === 'stt') {
        isListening = false;
        updateListenButton();
        document.getElementById('debug-listening').textContent = 'Off';
        document.getElementById('debug-listening').className = '';
        const el = document.getElementById('stt-result');
        if (msg.data.text) {
            el.innerHTML = `Heard: <span class="transcription">"${msg.data.text}"</span>`;
            document.getElementById('debug-stt').textContent = `"${msg.data.text}"`;
        } else {
            el.innerHTML = '<span style="color:#666">No speech detected</span>';
            document.getElementById('debug-stt').textContent = '(no speech)';
        }

    } else if (msg.type === 'auto_judge') {
        const result = msg.data.correct ? 'CORRECT' : 'INCORRECT';
        const conf = Math.round(msg.data.confidence * 100);
        // Operator panel
        const el = document.getElementById('auto-judge-result');
        if (msg.data.correct) {
            el.innerHTML = `<span class="correct">AUTO: CORRECT</span> (${conf}% match)`;
        } else {
            el.innerHTML = `<span class="incorrect">AUTO: INCORRECT</span> — expected "${msg.data.expected}"`;
        }
        // Debug panel
        document.getElementById('debug-stt').textContent = `"${msg.data.transcription}" → ${result} (${conf}%)`;
        document.getElementById('debug-judge').textContent = `${result} — ${conf}% confidence`;
        document.getElementById('debug-judge').className = msg.data.correct ? 'judge-correct' : 'judge-incorrect';
        document.getElementById('debug-expected').textContent = msg.data.correct ? '' : `Expected: ${msg.data.expected}`;

    } else if (msg.type === 'play_audio') {
        if (msg.data.url) {
            playAudio(msg.data.url);
        }
    }
}

// --- Operator UI updates ---

function updateOperatorUI() {
    document.getElementById('state-display').textContent = state.display_state || '--';
    document.getElementById('btn-wandering').classList.toggle('active', state.mode === 'wandering');
    document.getElementById('btn-quiz').classList.toggle('active', state.mode === 'quiz');
    document.getElementById('quiz-controls').style.display = state.mode === 'quiz' ? 'block' : 'none';
    document.getElementById('wandering-controls').style.display = state.mode === 'wandering' ? 'block' : 'none';

    const quizState = state.quiz_state;
    document.getElementById('btn-next-question').disabled = quizState !== 'idle';
    document.getElementById('btn-correct').disabled = quizState !== 'listening' && quizState !== 'judging';
    document.getElementById('btn-incorrect').disabled = quizState !== 'listening' && quizState !== 'judging';
    document.getElementById('btn-listen').disabled = quizState !== 'listening' && quizState !== 'judging';

    if (quizState === 'idle') {
        currentQuestion = null;
        updateQuestionDisplay();
        document.getElementById('stt-result').innerHTML = '';
        document.getElementById('auto-judge-result').innerHTML = '';
    }

    document.getElementById('difficulty-slider').value = state.difficulty || 3;
    document.getElementById('difficulty-value').textContent = state.difficulty || 3;
    document.getElementById('jello-toggle').checked = state.jello_shots_available;
    document.getElementById('llm-mode').value = state.llm_mode || 'offline';
}

function updateQuestionDisplay() {
    const el = document.getElementById('question-info');
    if (currentQuestion) {
        el.innerHTML = `
            <div class="question-text">${currentQuestion.question_text}</div>
            <div class="question-answer">Answer: ${currentQuestion.answer}</div>
            <div class="question-meta">${currentQuestion.category} · Difficulty ${currentQuestion.difficulty}</div>
        `;
    } else {
        el.innerHTML = '';
    }
}

function updateListenButton() {
    const btn = document.getElementById('btn-listen');
    if (isListening) {
        btn.textContent = 'LISTENING...';
        btn.classList.add('listening');
    } else {
        btn.textContent = 'LISTEN';
        btn.classList.remove('listening');
    }
}

// --- Commands ---

function setMode(mode) { send({ command: 'set_mode', mode }); }
function nextQuestion() { send({ command: 'next_question' }); }
function judgeCorrect() { send({ command: 'judge_correct' }); }
function judgeIncorrect() { send({ command: 'judge_incorrect' }); }

function toggleListen() {
    if (isListening) {
        send({ command: 'stop_listening' });
        isListening = false;
    } else {
        send({ command: 'start_listening' });
        isListening = true;
        document.getElementById('stt-result').innerHTML = '';
        document.getElementById('auto-judge-result').innerHTML = '';
    }
    updateListenButton();
}

function playRandomWandering() { send({ command: 'play_wandering' }); }

function setVolume(value) {
    document.getElementById('volume-value').textContent = value;
    send({ command: 'set_volume', volume: parseInt(value) / 100 });
}

function setDifficulty(value) {
    document.getElementById('difficulty-value').textContent = value;
    send({ command: 'set_difficulty', difficulty: parseInt(value) });
}

function setJelloShots(available) { send({ command: 'set_jello_shots', available }); }
function setLLMMode(mode) { send({ command: 'set_llm_mode', llm_mode: mode }); }

// --- Audio file loading ---

async function loadAudioFiles() {
    try {
        const resp = await fetch('/api/audio/list');
        const data = await resp.json();
        audioFiles = data.files || {};
        populateClipGrids();
    } catch (e) {
        console.error('Failed to load audio files:', e);
    }
}

function populateClipGrids() {
    const wanderingGrid = document.getElementById('wandering-clips');
    wanderingGrid.innerHTML = '';
    (audioFiles.wandering || []).forEach(file => {
        const btn = document.createElement('button');
        btn.className = 'clip-btn';
        btn.textContent = file.split('/').pop().replace('.wav', '').replace(/_/g, ' ');
        btn.onclick = () => send({ command: 'play_wandering', audio_path: file });
        wanderingGrid.appendChild(btn);
    });

    const cannedGrid = document.getElementById('canned-clips');
    cannedGrid.innerHTML = '';
    (audioFiles.canned || []).forEach(file => {
        const btn = document.createElement('button');
        btn.className = 'clip-btn';
        btn.textContent = file.split('/').pop().replace('.wav', '').replace(/_/g, ' ');
        btn.onclick = () => send({ command: 'play_canned', audio_path: file });
        cannedGrid.appendChild(btn);
    });
}

// --- Olmec Face Drawing ---

function drawFace() {
    const w = canvas.width;
    const h = canvas.height;
    currentAmplitude += (targetAmplitude - currentAmplitude) * 0.3;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h * 0.42;

    // Head outline
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx - 160, cy - 180);
    ctx.quadraticCurveTo(cx, cy - 220, cx + 160, cy - 180);
    ctx.quadraticCurveTo(cx + 200, cy, cx + 170, cy + 140);
    ctx.quadraticCurveTo(cx, cy + 180, cx - 170, cy + 140);
    ctx.quadraticCurveTo(cx - 200, cy, cx - 160, cy - 180);
    ctx.closePath();
    ctx.fillStyle = '#3a3529';
    ctx.fill();
    ctx.strokeStyle = '#2a2519';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.restore();

    // Headdress
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
    ctx.beginPath();
    ctx.ellipse(cx - 12, cy + 25, 8, 5, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 12, cy + 25, 8, 5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#2a2015';
    ctx.fill();
    ctx.restore();

    // Eyes
    const eyeY = cy - 50;
    const eyeSpacing = 70;
    drawEye(cx - eyeSpacing, eyeY, currentAmplitude);
    drawEye(cx + eyeSpacing, eyeY, currentAmplitude);

    // Mouth
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

    // Chin
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

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x, y, eyeWidth + 5, eyeHeight + 5, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#1a1510';
    ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(x, y, eyeWidth, eyeHeight, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#1a1510';
    ctx.fill();
    ctx.restore();

    if (glow > 0.01) {
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, eyeWidth * 2);
        const alpha = glow * 0.5;
        gradient.addColorStop(0, `rgba(255, 50, 20, ${alpha})`);
        gradient.addColorStop(0.5, `rgba(255, 20, 0, ${alpha * 0.3})`);
        gradient.addColorStop(1, 'rgba(255, 0, 0, 0)');
        ctx.save();
        ctx.fillStyle = gradient;
        ctx.fillRect(x - eyeWidth * 2, y - eyeWidth * 2, eyeWidth * 4, eyeWidth * 4);
        ctx.restore();

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
    const a = new Audio();
    a.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
    a.play().then(() => { audioUnlocked = true; }).catch(() => {});
}

document.addEventListener('click', unlockAudio, { once: true });
document.addEventListener('touchstart', unlockAudio, { once: true });

function playAudio(url) {
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
