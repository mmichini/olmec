"""Olmec interaction state machine with WANDERING and QUIZ modes."""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum

from olmec.events import (
    AudioFinishedEvent,
    PlayAudioEvent,
    StateChangeEvent,
    bus,
)

logger = logging.getLogger(__name__)


class Mode(str, Enum):
    WANDERING = "wandering"
    QUIZ = "quiz"


class QuizState(str, Enum):
    IDLE = "idle"
    ASKING = "asking"
    LISTENING = "listening"
    JUDGING = "judging"
    RESPONDING = "responding"


class WanderingState(str, Enum):
    IDLE = "idle"
    SPEAKING = "speaking"


@dataclass
class OlmecState:
    """Current state of the Olmec."""
    mode: Mode = Mode.WANDERING
    quiz_state: QuizState = QuizState.IDLE
    wandering_state: WanderingState = WanderingState.IDLE
    current_question_id: str | None = None
    current_question_answer: str | None = None
    current_question_audio: str | None = None
    jello_shots_available: bool = True
    difficulty: int = 3  # 1-5
    llm_mode: str = "offline"  # "offline", "local", "cloud"

    @property
    def display_state(self) -> str:
        if self.mode == Mode.QUIZ:
            return f"quiz:{self.quiz_state.value}"
        return f"wandering:{self.wandering_state.value}"


class StateMachine:
    """Manages Olmec's interaction state."""

    def __init__(self):
        self.state = OlmecState()
        self._audio_finished_event = asyncio.Event()
        self._pending_reveal_path: str | None = None

    async def start(self) -> None:
        bus.subscribe(AudioFinishedEvent, self._on_audio_finished)
        logger.info("State machine started")

    async def stop(self) -> None:
        bus.unsubscribe(AudioFinishedEvent, self._on_audio_finished)
        logger.info("State machine stopped")

    async def _on_audio_finished(self, event: AudioFinishedEvent) -> None:
        self._audio_finished_event.set()

        if self.state.mode == Mode.QUIZ and self.state.quiz_state == QuizState.ASKING:
            # In offline mode, skip mic listening — go straight to JUDGING
            # so the operator can press CORRECT/INCORRECT manually
            if self.state.llm_mode == "offline":
                await self._transition_quiz(QuizState.JUDGING)
            else:
                await self._transition_quiz(QuizState.LISTENING)
        elif self.state.mode == Mode.QUIZ and self.state.quiz_state == QuizState.RESPONDING:
            # Check if there's a reveal clip to play after the incorrect response
            if self._pending_reveal_path:
                reveal_path = self._pending_reveal_path
                self._pending_reveal_path = None
                self._audio_finished_event.clear()
                await bus.publish(PlayAudioEvent(file_path=reveal_path, category="reveal"))
                # Stay in RESPONDING state — will transition to IDLE when reveal finishes
            else:
                await self._transition_quiz(QuizState.IDLE)
        elif self.state.mode == Mode.WANDERING and self.state.wandering_state == WanderingState.SPEAKING:
            await self._transition_wandering(WanderingState.IDLE)

    # --- Mode switching ---

    async def set_mode(self, mode: Mode) -> None:
        if self.state.mode == mode:
            return
        old = self.state.display_state
        self.state.mode = mode
        self.state.quiz_state = QuizState.IDLE
        self.state.wandering_state = WanderingState.IDLE
        await bus.publish(StateChangeEvent(old_state=old, new_state=self.state.display_state))
        logger.info(f"Mode changed to {mode.value}")

    # --- Quiz flow ---

    async def ask_question(self, audio_path: str, question_id: str, answer: str) -> None:
        """Start asking a question. Can interrupt any current state."""
        if self.state.mode != Mode.QUIZ:
            await self.set_mode(Mode.QUIZ)

        # Cancel any pending reveal (don't play it after interrupt)
        self._pending_reveal_path = None

        self.state.current_question_id = question_id
        self.state.current_question_answer = answer
        self.state.current_question_audio = audio_path
        self._audio_finished_event.clear()
        await self._transition_quiz(QuizState.ASKING)
        await bus.publish(PlayAudioEvent(file_path=audio_path, category="question"))

    async def repeat_question(self) -> None:
        """Replay the current question's audio."""
        if not self.state.current_question_audio:
            logger.warning("No current question to repeat")
            return
        # Cancel any pending reveal
        self._pending_reveal_path = None
        self._audio_finished_event.clear()
        await self._transition_quiz(QuizState.ASKING)
        await bus.publish(PlayAudioEvent(file_path=self.state.current_question_audio, category="question"))

    async def judge_correct(self, audio_path: str) -> None:
        """Operator or auto-judge says correct."""
        if self.state.quiz_state not in (QuizState.LISTENING, QuizState.JUDGING):
            return
        self._audio_finished_event.clear()
        await self._transition_quiz(QuizState.RESPONDING)
        await bus.publish(PlayAudioEvent(file_path=audio_path, category="response"))

    async def judge_incorrect(self, audio_path: str, reveal_audio_path: str | None = None) -> None:
        """Operator or auto-judge says incorrect. Optionally plays a reveal clip after."""
        if self.state.quiz_state not in (QuizState.LISTENING, QuizState.JUDGING):
            return
        self._pending_reveal_path = reveal_audio_path
        self._audio_finished_event.clear()
        await self._transition_quiz(QuizState.RESPONDING)
        await bus.publish(PlayAudioEvent(file_path=audio_path, category="response"))

    async def start_listening(self) -> None:
        """Manually trigger listening state (if auto-transition didn't fire)."""
        if self.state.quiz_state == QuizState.ASKING:
            await self._transition_quiz(QuizState.LISTENING)

    async def _transition_quiz(self, new_state: QuizState) -> None:
        old = self.state.display_state
        self.state.quiz_state = new_state
        await bus.publish(StateChangeEvent(old_state=old, new_state=self.state.display_state))
        logger.info(f"Quiz state: {new_state.value}")

    # --- Wandering flow ---

    async def play_wandering_clip(self, audio_path: str) -> None:
        """Play a wandering/barker clip."""
        if self.state.mode != Mode.WANDERING:
            await self.set_mode(Mode.WANDERING)
        if self.state.wandering_state == WanderingState.SPEAKING:
            return  # Already speaking

        self._audio_finished_event.clear()
        await self._transition_wandering(WanderingState.SPEAKING)
        await bus.publish(PlayAudioEvent(file_path=audio_path, category="wandering"))

    async def _transition_wandering(self, new_state: WanderingState) -> None:
        old = self.state.display_state
        self.state.wandering_state = new_state
        await bus.publish(StateChangeEvent(old_state=old, new_state=self.state.display_state))
        logger.info(f"Wandering state: {new_state.value}")

    # --- Canned clips (work in any mode) ---

    async def play_canned(self, audio_path: str) -> None:
        """Play a canned phrase (works in any mode/state)."""
        self._audio_finished_event.clear()
        await bus.publish(PlayAudioEvent(file_path=audio_path, category="canned"))

    def to_dict(self) -> dict:
        """Serialize current state for WebSocket clients."""
        return {
            "mode": self.state.mode.value,
            "quiz_state": self.state.quiz_state.value,
            "wandering_state": self.state.wandering_state.value,
            "display_state": self.state.display_state,
            "current_question_id": self.state.current_question_id,
            "jello_shots_available": self.state.jello_shots_available,
            "difficulty": self.state.difficulty,
            "llm_mode": self.state.llm_mode,
        }


# Singleton
state_machine = StateMachine()
