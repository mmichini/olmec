"""Audio playback engine with real-time amplitude extraction for LED sync."""

import asyncio
import logging
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from olmec.config import settings
from olmec.events import (
    AmplitudeEvent,
    AudioFinishedEvent,
    PlayAudioEvent,
    StopAudioEvent,
    bus,
)

logger = logging.getLogger(__name__)

# Amplitude smoothing parameters
SMOOTHING_ALPHA = 0.3  # Exponential moving average factor
GAMMA = 0.6  # Perceptual brightness curve
FRAME_SIZE = 1024  # Samples per amplitude calculation (~23ms at 44.1kHz)


class AudioEngine:
    """Plays audio files and streams real-time amplitude data."""

    def __init__(self):
        self._playing = False
        self._stop_requested = False
        self._current_file: str | None = None
        self._volume: float = 1.0
        self._smoothed_rms: float = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._play_lock = threading.Lock()

    async def start(self) -> None:
        """Register event handlers and store the event loop."""
        self._loop = asyncio.get_running_loop()
        bus.subscribe(PlayAudioEvent, self._on_play)
        bus.subscribe(StopAudioEvent, self._on_stop)
        logger.info("Audio engine started")

    async def stop(self) -> None:
        """Clean up."""
        self._stop_requested = True
        bus.unsubscribe(PlayAudioEvent, self._on_play)
        bus.unsubscribe(StopAudioEvent, self._on_stop)
        logger.info("Audio engine stopped")

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))

    async def _on_play(self, event: PlayAudioEvent) -> None:
        """Handle play audio event."""
        if self._playing:
            await self._stop_playback()
        # Run blocking audio playback in a thread
        asyncio.get_running_loop().run_in_executor(None, self._play_file, event.file_path)

    async def _on_stop(self, event: StopAudioEvent) -> None:
        """Handle stop audio event."""
        await self._stop_playback()

    async def _stop_playback(self) -> None:
        """Stop current playback."""
        self._stop_requested = True
        sd.stop()

    def _play_file(self, file_path: str) -> None:
        """Play an audio file with real-time amplitude extraction. Runs in a thread.

        In local/cloud mode, audio playback is handled by the browser —
        we still extract amplitude for LED sync but skip speaker output.
        On Pi, we play through the physical speaker.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return

        play_speaker = settings.is_pi

        with self._play_lock:
            self._playing = True
            self._stop_requested = False
            self._current_file = file_path
            self._smoothed_rms = 0.0

            try:
                data, samplerate = sf.read(file_path, dtype="float32")

                # Convert stereo to mono if needed
                if data.ndim > 1:
                    data = data.mean(axis=1)

                # Apply volume
                data = data * self._volume

                # Play in chunks for real-time amplitude extraction
                stream = None
                if play_speaker:
                    stream = sd.OutputStream(
                        samplerate=samplerate,
                        channels=1,
                        dtype="float32",
                    )
                    stream.start()

                # Calculate chunk timing for non-speaker mode
                chunk_duration = FRAME_SIZE / samplerate

                offset = 0
                while offset < len(data) and not self._stop_requested:
                    chunk = data[offset : offset + FRAME_SIZE]
                    if len(chunk) == 0:
                        break

                    # Pad last chunk if needed
                    if len(chunk) < FRAME_SIZE:
                        chunk = np.pad(chunk, (0, FRAME_SIZE - len(chunk)))

                    if stream:
                        # Write to physical speaker
                        stream.write(chunk.reshape(-1, 1))
                    else:
                        # No speaker — sleep to match real-time playback rate
                        import time
                        time.sleep(chunk_duration)

                    # Calculate amplitude
                    rms = float(np.sqrt(np.mean(chunk**2)))
                    peak = float(np.max(np.abs(chunk)))

                    # Apply exponential smoothing
                    self._smoothed_rms = (
                        SMOOTHING_ALPHA * rms
                        + (1 - SMOOTHING_ALPHA) * self._smoothed_rms
                    )

                    # Apply gamma curve for perceptual brightness
                    brightness = self._smoothed_rms ** GAMMA

                    # Publish amplitude event from the event loop
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            bus.publish(AmplitudeEvent(rms=brightness, peak=peak)),
                            self._loop,
                        )

                    offset += FRAME_SIZE

                if stream:
                    stream.stop()
                    stream.close()

            except Exception:
                logger.exception(f"Error playing audio file: {file_path}")
            finally:
                self._playing = False
                self._current_file = None
                # Send zero amplitude to turn off LEDs
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        bus.publish(AmplitudeEvent(rms=0.0, peak=0.0)),
                        self._loop,
                    )
                    asyncio.run_coroutine_threadsafe(
                        bus.publish(AudioFinishedEvent(file_path=file_path)),
                        self._loop,
                    )


# Singleton
audio_engine = AudioEngine()
