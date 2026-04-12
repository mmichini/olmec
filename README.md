# Olmec

Interactive Olmec head sculpture for Bay to Breakers 2026 — a Legends of the Hidden Temple group costume.

A Raspberry Pi-powered talking head that asks trivia questions to passersby, judges their answers, and awards jello shots. Features AI-generated voice (ElevenLabs), pulsing red LED eyes synced to speech, and a phone-based operator UI.

## Quick Start

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run the server
uv run uvicorn olmec.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open:
- **Operator UI:** http://localhost:8000/operator/
- **Digital Twin:** http://localhost:8000/twin/
- **API Status:** http://localhost:8000/api/status

## Architecture

```
Phone (WiFi) ──WebSocket──▶ FastAPI Server
                              ├── State Machine (WANDERING / QUIZ modes)
                              ├── Event Bus (async pub/sub)
                              ├── Audio Engine (real-time amplitude extraction)
                              ├── LED Driver (GPIO on Pi, mock on Mac)
                              ├── STT Engine (faster-whisper, offline)
                              ├── Question DB (SQLite)
                              └── LLM (local llama.cpp / Claude API)
```

### Modes

- **WANDERING** — Olmec calls out to the crowd as a barker while being carried around
- **QUIZ** — Interactive trivia: Olmec asks a question → person answers → Olmec judges

### Deployment Modes

1. **Local Dev (macOS)** — Everything runs on localhost, LEDs mocked via digital twin
2. **Pi Field Mode** — Pi creates WiFi hotspot, works fully offline
3. **Cloud Demo** — Deployed to a VPS for remote group collaboration

## Project Structure

```
src/olmec/          # Python backend
  main.py           # FastAPI app
  config.py         # Settings via env vars
  events.py         # Async event bus
  state_machine.py  # WANDERING + QUIZ state management
  audio/engine.py   # Playback with real-time amplitude
  led/driver.py     # LED abstraction (Pi GPIO / mock)
  api/              # REST + WebSocket endpoints
ui/
  operator/         # Phone control UI
  twin/             # Digital twin (animated Olmec face)
pipeline/           # Content generation scripts
data/
  content/          # YAML source files (questions, responses, etc.)
  audio/            # Generated WAV clips (per voice)
```

## Configuration

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Key settings:
- `OLMEC_MODE` — `local`, `pi`, or `cloud`
- `OLMEC_VOICE` — Active voice directory name
- `ELEVENLABS_API_KEY` — For audio generation
- `ANTHROPIC_API_KEY` — For question extraction + cloud LLM

## Content Pipeline

All text content lives in `data/content/*.yaml` (source of truth). Audio clips are generated artifacts.

```bash
# Generate audio clips for all content using ElevenLabs
uv run python pipeline/generate_audio.py --voice olmec-v1 --regenerate-all

# Seed the database
uv run python pipeline/seed_db.py
```

See [docs/content-pipeline.md](docs/content-pipeline.md) for details.

## Hardware

- Raspberry Pi 5 (4GB)
- USB-C PD power bank (20,000mAh+)
- Portable speaker (3.5mm)
- USB directional microphone
- 2x 1W high-power red LEDs + constant-current driver
- Foam sculpture

See [hardware/bom.md](hardware/bom.md) for the full bill of materials.
