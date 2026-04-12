# Olmec

Interactive Olmec head sculpture for Bay to Breakers 2026 — a Legends of the Hidden Temple group costume.

A Raspberry Pi-powered talking head that asks trivia questions to passersby, judges their answers, and awards jello shots. Features AI-generated voice (ElevenLabs), pulsing red LED eyes synced to speech, speech-to-text answer recognition, and a phone-based operator UI.

## Quick Start

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (with speech-to-text support)
uv sync --extra stt

# Seed the question database
uv run python pipeline/seed_db.py

# Run the server
uv run uvicorn olmec.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open:
- **Olmec (combined UI):** http://localhost:8000/olmec/ — digital twin + slide-out operator controls
- **Operator UI (phone):** http://localhost:8000/ui/ — standalone controls for phone use at the festival
- **API Status:** http://localhost:8000/api/status

## Architecture

```
Phone / Browser ──WebSocket──▶ FastAPI Server
                                 ├── State Machine (WANDERING / QUIZ modes)
                                 ├── Event Bus (async pub/sub)
                                 ├── Audio Engine (real-time amplitude extraction)
                                 ├── LED Driver (GPIO on Pi, mock on Mac)
                                 ├── STT Engine (faster-whisper + Silero VAD)
                                 ├── Question DB (SQLite)
                                 └── Answer Judge (fuzzy matching)
```

### Modes

- **WANDERING** — Olmec calls out to the crowd as a barker while being carried around
- **QUIZ** — Interactive trivia: Olmec asks → person answers → STT transcribes → auto-judge → Olmec responds

### Deployment Modes

1. **Local Dev (macOS)** — Everything runs on localhost, LEDs mocked, audio plays in browser
2. **Pi Field Mode** — Pi creates WiFi hotspot, works fully offline, audio through physical speaker + LEDs
3. **Cloud Demo** — Deployed to Fly.io, browser mic capture via getUserMedia, HTTPS

## Project Structure

```
src/olmec/            # Python backend
  main.py             # FastAPI app + lifecycle
  config.py           # Settings via env vars, platform detection
  events.py           # Async event bus
  state_machine.py    # WANDERING + QUIZ state management
  audio/engine.py     # Playback with real-time amplitude extraction
  led/driver.py       # LED abstraction (Pi GPIO / mock)
  stt/engine.py       # Mic capture + Silero VAD + faster-whisper
  stt/judge.py        # Fuzzy answer matching
  questions/db.py     # SQLite question database
  api/ws.py           # WebSocket hub (operator commands, amplitude, STT)
  api/routes.py       # REST API endpoints

ui/
  combined/           # Olmec face + slide-out operator panel (primary UI)
  operator/           # Standalone phone operator UI
  twin/               # Standalone digital twin

pipeline/
  generate_audio.py   # ElevenLabs TTS batch generation from YAML
  apply_effects.py    # Audio effects (reverb) via pedalboard
  seed_db.py          # Load YAML content into SQLite

data/
  content/            # YAML source files (questions, responses, wandering, canned)
  audio/              # Generated WAV clips organized by voice
```

## Configuration

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Key settings:
- `OLMEC_MODE` — `local`, `pi`, or `cloud`
- `OLMEC_VOICE` — Active voice directory name (e.g., `olmec-v1-fx` for reverb version)
- `ELEVENLABS_API_KEY` — For audio generation pipeline
- `ELEVENLABS_VOICE_ID` — Your cloned Olmec voice ID

## Content Pipeline

All text content lives in `data/content/*.yaml` (source of truth). Audio clips are generated artifacts.

```bash
# Generate audio clips for all content using ElevenLabs
uv run python pipeline/generate_audio.py

# Only generate missing clips
uv run python pipeline/generate_audio.py --category questions

# Preview what would be generated
uv run python pipeline/generate_audio.py --dry-run

# Apply reverb effects (creates olmec-v1-fx/ from olmec-v1/)
uv run python pipeline/apply_effects.py

# Seed the question database
uv run python pipeline/seed_db.py
```

## Cloud Deployment (Fly.io)

```bash
fly launch --no-deploy
fly secrets set OLMEC_PASSWORD=your-password  # optional
fly deploy --remote-only
```

See [docs/deployment.md](docs/deployment.md) for details.

## Hardware

- Raspberry Pi 5 (4GB)
- USB-C PD power bank (20,000mAh+)
- Portable speaker (3.5mm)
- USB directional microphone
- 2x 1W high-power red LEDs + constant-current driver (CAT4101 or MOSFET)
- USB WiFi dongle (for internet via phone hotspot)
- Foam sculpture
