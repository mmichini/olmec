// Olmec Operator UI

let ws = null;
let state = {};
let audioFiles = {};
let currentQuestion = null;
let isListening = false;

// --- WebSocket ---

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        document.getElementById('connection-status').className = 'status connected';
        document.getElementById('connection-status').textContent = 'Connected';
        loadAudioFiles();
    };

    ws.onclose = () => {
        document.getElementById('connection-status').className = 'status disconnected';
        document.getElementById('connection-status').textContent = 'Disconnected';
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
    if (msg.type === 'state') {
        state = msg.data;
        updateUI();
    } else if (msg.type === 'volume') {
        document.getElementById('volume-slider').value = Math.round(msg.data.volume * 100);
        document.getElementById('volume-value').textContent = Math.round(msg.data.volume * 100);
    } else if (msg.type === 'question') {
        currentQuestion = msg.data;
        updateQuestionDisplay();
    } else if (msg.type === 'listening') {
        isListening = msg.data.active;
        updateListenButton();
    } else if (msg.type === 'stt') {
        const el = document.getElementById('stt-result');
        if (msg.data.text) {
            el.innerHTML = `Heard: <span class="transcription">"${msg.data.text}"</span>`;
        } else {
            el.innerHTML = '<span style="color:#666">No speech detected</span>';
        }
        isListening = false;
        updateListenButton();
    } else if (msg.type === 'auto_judge') {
        const el = document.getElementById('auto-judge-result');
        if (msg.data.correct) {
            el.innerHTML = `<span class="correct">AUTO: CORRECT</span> (${Math.round(msg.data.confidence * 100)}% match)`;
        } else {
            el.innerHTML = `<span class="incorrect">AUTO: INCORRECT</span> — expected "${msg.data.expected}"`;
        }
    }
}

function updateUI() {
    // State display
    document.getElementById('state-display').textContent = state.display_state || '--';

    // Mode buttons
    document.getElementById('btn-wandering').classList.toggle('active', state.mode === 'wandering');
    document.getElementById('btn-quiz').classList.toggle('active', state.mode === 'quiz');

    // Show/hide panels
    document.getElementById('quiz-controls').style.display = state.mode === 'quiz' ? 'block' : 'none';
    document.getElementById('wandering-controls').style.display = state.mode === 'wandering' ? 'block' : 'none';

    // Quiz button states
    const quizState = state.quiz_state;
    document.getElementById('btn-next-question').disabled = quizState !== 'idle';
    document.getElementById('btn-correct').disabled = quizState !== 'listening' && quizState !== 'judging';
    document.getElementById('btn-incorrect').disabled = quizState !== 'listening' && quizState !== 'judging';

    // Clear question display when returning to idle
    if (quizState === 'idle') {
        currentQuestion = null;
        updateQuestionDisplay();
        document.getElementById('stt-result').innerHTML = '';
        document.getElementById('auto-judge-result').innerHTML = '';
    }

    // Listen button: enabled during listening/judging states
    document.getElementById('btn-listen').disabled = quizState !== 'listening' && quizState !== 'judging';

    // Difficulty
    document.getElementById('difficulty-slider').value = state.difficulty || 3;
    document.getElementById('difficulty-value').textContent = state.difficulty || 3;

    // Jello shots
    document.getElementById('jello-toggle').checked = state.jello_shots_available;

    // LLM mode
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

// --- Commands ---

function setMode(mode) {
    send({ command: 'set_mode', mode: mode });
}

function nextQuestion() {
    // Server picks from DB based on current difficulty
    send({ command: 'next_question' });
}

function judgeCorrect() {
    // Server picks correct response clip from DB
    send({ command: 'judge_correct' });
}

function judgeIncorrect() {
    // Server picks incorrect response clip from DB
    send({ command: 'judge_incorrect' });
}

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

function playRandomWandering() {
    // Server picks random wandering clip from DB
    send({ command: 'play_wandering' });
}

function setVolume(value) {
    document.getElementById('volume-value').textContent = value;
    send({ command: 'set_volume', volume: parseInt(value) / 100 });
}

function setDifficulty(value) {
    document.getElementById('difficulty-value').textContent = value;
    send({ command: 'set_difficulty', difficulty: parseInt(value) });
}

function setJelloShots(available) {
    send({ command: 'set_jello_shots', available: available });
}

function setLLMMode(mode) {
    send({ command: 'set_llm_mode', llm_mode: mode });
}

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
    // Wandering clips
    const wanderingGrid = document.getElementById('wandering-clips');
    wanderingGrid.innerHTML = '';
    (audioFiles.wandering || []).forEach(file => {
        const btn = document.createElement('button');
        btn.className = 'clip-btn';
        const name = file.split('/').pop().replace('.wav', '').replace(/_/g, ' ');
        btn.textContent = name;
        btn.onclick = () => send({
            command: 'play_wandering',
            audio_path: file,
        });
        wanderingGrid.appendChild(btn);
    });

    // Canned clips
    const cannedGrid = document.getElementById('canned-clips');
    cannedGrid.innerHTML = '';
    (audioFiles.canned || []).forEach(file => {
        const btn = document.createElement('button');
        btn.className = 'clip-btn';
        const name = file.split('/').pop().replace('.wav', '').replace(/_/g, ' ');
        btn.textContent = name;
        btn.onclick = () => send({
            command: 'play_canned',
            audio_path: file,
        });
        cannedGrid.appendChild(btn);
    });
}

// --- Init ---
connect();
