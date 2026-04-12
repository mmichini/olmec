"""WebSocket hub for operator UI and digital twin communication."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from olmec.config import settings
from olmec.events import AmplitudeEvent, PlayAudioEvent, STTResultEvent, StateChangeEvent, bus
from olmec.questions.db import question_db, resolve_audio_path
from olmec.state_machine import Mode, QuizState, state_machine
from olmec.stt.engine import stt_engine
from olmec.stt.judge import check_answer

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for operator and twin clients."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        # Send current state on connect
        await self._send(websocket, {
            "type": "state",
            "data": state_machine.to_dict(),
        })
        logger.info(f"WebSocket connected ({len(self._connections)} total)")

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.info(f"WebSocket disconnected ({len(self._connections)} total)")

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        disconnected = []
        for ws in self._connections:
            try:
                await self._send(ws, message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._connections.remove(ws)

    async def _send(self, ws: WebSocket, message: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(message))


manager = ConnectionManager()


async def setup_ws_events() -> None:
    """Subscribe to events and broadcast to WebSocket clients."""

    async def on_amplitude(event: AmplitudeEvent) -> None:
        await manager.broadcast({
            "type": "amplitude",
            "data": {"rms": round(event.rms, 4), "peak": round(event.peak, 4)},
        })

    async def on_state_change(event: StateChangeEvent) -> None:
        await manager.broadcast({
            "type": "state",
            "data": state_machine.to_dict(),
        })

        # Auto-start listening when entering LISTENING state
        if event.new_state == "quiz:listening":
            await stt_engine.start_listening()
            await manager.broadcast({"type": "listening", "data": {"active": True}})

    async def on_play_audio(event: PlayAudioEvent) -> None:
        """Broadcast audio URL so browser clients can play it too."""
        # Convert filesystem path to a URL path the browser can fetch
        audio_base = settings.data_dir / "audio"
        try:
            rel = Path(event.file_path).relative_to(audio_base)
            url = f"/audio/{rel}"
        except ValueError:
            url = None
        await manager.broadcast({
            "type": "play_audio",
            "data": {"url": url, "category": event.category},
        })

    async def on_stt_result(event: STTResultEvent) -> None:
        """Handle STT transcription result — broadcast and auto-judge."""
        await manager.broadcast({
            "type": "stt",
            "data": {"text": event.text, "confidence": round(event.confidence, 2)},
        })

        # Auto-judge if we're in listening/judging state and have a current question
        if (
            state_machine.state.mode == Mode.QUIZ
            and state_machine.state.quiz_state in (QuizState.LISTENING, QuizState.JUDGING)
            and state_machine.state.current_question_answer
            and event.text
        ):
            # Get the question's accepted answers from the DB
            question = question_db.get_question(state_machine.state.current_question_id)
            if question:
                is_correct, confidence = check_answer(event.text, question.accept)
                logger.info(
                    f"Auto-judge: '{event.text}' vs accepted={question.accept} "
                    f"-> correct={is_correct} (confidence={confidence:.2f})"
                )

                # Broadcast the judgment for the UI
                await manager.broadcast({
                    "type": "auto_judge",
                    "data": {
                        "correct": is_correct,
                        "confidence": round(confidence, 2),
                        "transcription": event.text,
                        "expected": question.answer,
                    },
                })

                # Auto-trigger the response:
                # - Correct: only if confidence is high (we're sure they got it right)
                # - Incorrect: always auto-trigger (they didn't match any accepted answer)
                if is_correct and confidence >= 0.8:
                    await handle_ws_message({"command": "judge_correct"})
                elif not is_correct:
                    await handle_ws_message({"command": "judge_incorrect"})

    bus.subscribe(AmplitudeEvent, on_amplitude)
    bus.subscribe(StateChangeEvent, on_state_change)
    bus.subscribe(PlayAudioEvent, on_play_audio)
    bus.subscribe(STTResultEvent, on_stt_result)


def _resolve_audio_path(relative_path: str) -> str:
    """Resolve a relative audio path (from UI) to an absolute filesystem path."""
    # The UI sends paths like "wandering/step_right_up.wav"
    # Resolve to the active voice directory
    resolved = settings.audio_dir / relative_path
    return str(resolved)


async def handle_ws_message(data: dict[str, Any]) -> None:
    """Process an incoming WebSocket command from the operator UI."""
    cmd = data.get("command")

    if cmd == "set_mode":
        mode = Mode(data["mode"])
        await state_machine.set_mode(mode)

    elif cmd == "next_question":
        # Pick a random question from the DB, filtered by difficulty
        difficulty = state_machine.state.difficulty
        question = question_db.get_random_question(max_difficulty=difficulty)
        if not question:
            logger.warning("No questions available for difficulty <= %d", difficulty)
            return
        audio_path = resolve_audio_path(question.id, "questions")
        if not audio_path:
            logger.warning("No audio file for question %s", question.id)
            return
        await state_machine.ask_question(
            audio_path=audio_path,
            question_id=question.id,
            answer=question.answer,
        )
        # Send question info to clients so they can display it
        await manager.broadcast({
            "type": "question",
            "data": {
                "id": question.id,
                "question_text": question.question_text,
                "answer": question.answer,
                "category": question.category,
                "difficulty": question.difficulty,
            },
        })

    elif cmd == "judge_correct":
        # Pick a correct response clip from the DB
        jello = state_machine.state.jello_shots_available
        category = "correct" if jello else "correct_no_jello"
        clip = question_db.get_random_clip(category)
        if not clip:
            # Fallback to regular correct if no jello-specific clips
            clip = question_db.get_random_clip("correct")
        if clip:
            audio_path = resolve_audio_path(clip.id, "responses", clip.takes)
            if audio_path:
                # Record stats
                if state_machine.state.current_question_id:
                    question_db.record_asked(state_machine.state.current_question_id, correct=True)
                await state_machine.judge_correct(audio_path=audio_path)

    elif cmd == "judge_incorrect":
        clip = question_db.get_random_clip("incorrect")
        if clip:
            audio_path = resolve_audio_path(clip.id, "responses", clip.takes)
            if audio_path:
                if state_machine.state.current_question_id:
                    question_db.record_asked(state_machine.state.current_question_id, correct=False)
                # Try to find a reveal clip for this question
                reveal_path = resolve_audio_path(
                    f"reveal_{state_machine.state.current_question_id}", "reveals"
                ) if state_machine.state.current_question_id else None
                await state_machine.judge_incorrect(
                    audio_path=audio_path,
                    reveal_audio_path=reveal_path or None,
                )

    elif cmd == "play_wandering":
        if "audio_path" in data:
            # Specific clip requested from soundboard
            await state_machine.play_wandering_clip(audio_path=_resolve_audio_path(data["audio_path"]))
        else:
            # Pick random wandering clip from DB
            clip = question_db.get_random_clip("wandering")
            if clip:
                audio_path = resolve_audio_path(clip.id, "wandering", clip.takes)
                if audio_path:
                    await state_machine.play_wandering_clip(audio_path=audio_path)

    elif cmd == "play_canned":
        if "audio_path" in data:
            await state_machine.play_canned(audio_path=_resolve_audio_path(data["audio_path"]))
        else:
            clip = question_db.get_random_clip("canned")
            if clip:
                audio_path = resolve_audio_path(clip.id, "canned", clip.takes)
                if audio_path:
                    await state_machine.play_canned(audio_path=audio_path)

    elif cmd == "start_listening":
        # Try local mic first, fall back to waiting for browser audio
        if stt_engine._check_deps():
            await stt_engine.start_listening()
        # Either way, broadcast listening state so browser knows to capture mic
        await manager.broadcast({"type": "listening", "data": {"active": True}})

    elif cmd == "stop_listening":
        await stt_engine.stop_listening()
        await manager.broadcast({"type": "listening", "data": {"active": False}})

    elif cmd == "browser_audio":
        # Receive audio from browser mic (base64-encoded float32 PCM)
        import base64
        audio_bytes = base64.b64decode(data["audio"])
        sample_rate = data.get("sample_rate", 16000)
        await stt_engine.transcribe_bytes(audio_bytes, sample_rate)

    elif cmd == "set_volume":
        from olmec.audio.engine import audio_engine
        audio_engine.volume = float(data["volume"])
        await manager.broadcast({"type": "volume", "data": {"volume": audio_engine.volume}})

    elif cmd == "set_difficulty":
        state_machine.state.difficulty = int(data["difficulty"])
        await manager.broadcast({"type": "state", "data": state_machine.to_dict()})

    elif cmd == "set_jello_shots":
        state_machine.state.jello_shots_available = bool(data["available"])
        await manager.broadcast({"type": "state", "data": state_machine.to_dict()})

    elif cmd == "set_llm_mode":
        state_machine.state.llm_mode = data["llm_mode"]
        await manager.broadcast({"type": "state", "data": state_machine.to_dict()})

    else:
        logger.warning(f"Unknown WebSocket command: {cmd}")
