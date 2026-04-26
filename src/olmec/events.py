"""In-process async event bus for decoupled communication between subsystems."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class Event:
    """Base event class."""
    pass


@dataclass
class PlayAudioEvent(Event):
    """Request to play an audio file."""
    file_path: str
    category: str = ""  # e.g., "question", "response", "wandering"


@dataclass
class StopAudioEvent(Event):
    """Request to stop current audio playback."""
    pass


@dataclass
class AmplitudeEvent(Event):
    """Real-time amplitude data from audio playback."""
    rms: float = 0.0  # 0.0 to 1.0
    peak: float = 0.0  # 0.0 to 1.0


@dataclass
class AudioFinishedEvent(Event):
    """Audio playback completed."""
    file_path: str = ""


@dataclass
class StateChangeEvent(Event):
    """State machine transition."""
    old_state: str = ""
    new_state: str = ""


@dataclass
class STTResultEvent(Event):
    """Speech-to-text transcription result."""
    text: str = ""
    confidence: float = 0.0


@dataclass
class JudgmentEvent(Event):
    """Answer judgment result."""
    correct: bool = False
    expected: str = ""
    received: str = ""


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Simple async pub/sub event bus."""

    def __init__(self):
        self._handlers: dict[type[Event], list[EventHandler]] = {}

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(type(event), [])
        await asyncio.gather(*(h(event) for h in handlers), return_exceptions=True)


# Global event bus instance
bus = EventBus()
