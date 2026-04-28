"""Speech-to-text engine with mic capture, Silero VAD, and faster-whisper."""

import asyncio
import logging
import threading
import time
from pathlib import Path

from olmec.events import STTResultEvent, bus

logger = logging.getLogger(__name__)

# Audio capture settings
SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1
DTYPE = "float32"

# VAD settings
VAD_SILENCE_THRESHOLD_SEC = 1.0  # Stop after this much silence
HARD_TIMEOUT_SEC = 8.0  # Max recording time
VAD_WINDOW_MS = 512  # VAD processes in 512ms windows for silero


class STTEngine:
    """Captures mic audio, detects speech end via VAD, transcribes with Whisper."""

    def __init__(self):
        self._whisper_model = None
        self._vad_model = None
        self._recording = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._record_thread: threading.Thread | None = None

    async def start(self) -> None:
        """Load models (lazy — first use may take a moment)."""
        self._loop = asyncio.get_running_loop()
        logger.info("STT engine ready (models load on first use)")

    async def stop(self) -> None:
        self._recording = False
        logger.info("STT engine stopped")

    def _ensure_whisper(self):
        """Lazy-load Whisper model."""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            logger.info("Loading Whisper model (tiny.en)...")
            self._whisper_model = WhisperModel(
                "tiny.en",
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper model loaded")

    def _ensure_vad(self):
        """Lazy-load Silero VAD model."""
        if self._vad_model is None:
            from silero_vad import load_silero_vad
            logger.info("Loading Silero VAD model...")
            self._vad_model = load_silero_vad()
            logger.info("Silero VAD model loaded")

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _check_local_mic(self) -> bool:
        """Check if local mic capture is possible (deps + hardware)."""
        try:
            import sounddevice as sd  # noqa: F401
            import faster_whisper  # noqa: F401
            import silero_vad  # noqa: F401
            devices = sd.query_devices()
            has_input = any(d['max_input_channels'] > 0 for d in devices) if devices else False
            if not has_input:
                return False
            return True
        except (ImportError, Exception):
            return False

    def _check_whisper(self) -> bool:
        """Check if Whisper is available (for transcribing browser audio)."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    async def start_listening(self) -> None:
        """Begin recording from the local microphone if available.
        Even if local mic is unavailable, the listening state is broadcast
        so browsers can capture audio via getUserMedia instead."""
        if not self._check_local_mic():
            logger.info("No local mic — waiting for browser audio")
            return
        if self._recording:
            logger.warning("Already recording")
            return
        self._recording = True
        self._record_thread = threading.Thread(target=self._record_and_transcribe, daemon=True)
        self._record_thread.start()

    async def stop_listening(self) -> None:
        """Manually stop recording."""
        self._recording = False

    async def transcribe_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> None:
        """Transcribe raw PCM audio bytes (from browser mic). Runs Whisper in a thread."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._transcribe_audio_bytes, audio_bytes, sample_rate)

    def _transcribe_audio_bytes(self, audio_bytes: bytes, sample_rate: int) -> None:
        """Transcribe raw audio bytes. Runs in a thread."""
        import numpy as np

        try:
            self._ensure_whisper()
        except Exception:
            logger.exception("Failed to load Whisper model")
            return

        # Convert bytes to float32 numpy array
        audio = np.frombuffer(audio_bytes, dtype=np.float32)

        if len(audio) == 0:
            logger.info("Empty audio received")
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    bus.publish(STTResultEvent(text="", confidence=0.0)),
                    self._loop,
                )
            return

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            from scipy.signal import resample
            num_samples = int(len(audio) * 16000 / sample_rate)
            audio = resample(audio, num_samples).astype(np.float32)

        duration = len(audio) / 16000
        logger.info(f"Received {duration:.1f}s of browser audio, transcribing...")

        try:
            segments, info = self._whisper_model.transcribe(
                audio,
                language="en",
                beam_size=1,
                vad_filter=True,  # Let Whisper filter silence from browser audio
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            confidence = 1.0 - (info.language_probability if hasattr(info, 'language_probability') else 0.0)
            logger.info(f"Browser STT: '{text}' (confidence: {confidence:.2f})")
        except Exception:
            logger.exception("Whisper transcription failed")
            text = ""
            confidence = 0.0

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                bus.publish(STTResultEvent(text=text, confidence=confidence)),
                self._loop,
            )

    def _record_and_transcribe(self) -> None:
        """Record audio, detect end of speech, transcribe. Runs in a thread."""
        import numpy as np
        import sounddevice as sd
        import torch

        self._ensure_vad()
        self._ensure_whisper()

        audio_chunks: list[np.ndarray] = []
        speech_detected = False
        silence_start: float | None = None
        record_start = time.monotonic()

        # VAD needs 512-sample chunks at 16kHz
        vad_chunk_size = 512

        # Determine the mic's native sample rate (some mics don't support 16kHz)
        from olmec.audio.devices import find_device_by_name
        from olmec.config import settings
        input_device = find_device_by_name(settings.audio_input_device, "input")
        device_info = sd.query_devices(input_device, kind="input") if input_device is not None else sd.query_devices(kind="input")
        native_rate = int(device_info.get("default_samplerate", 16000))
        if native_rate != SAMPLE_RATE:
            logger.info(f"Mic native rate is {native_rate}Hz, will resample to {SAMPLE_RATE}Hz")
            # Use a chunk size that gives ~32ms at the native rate
            capture_chunk_size = int(native_rate * 0.032)
        else:
            capture_chunk_size = vad_chunk_size

        logger.info("Listening...")

        try:
            stream = sd.InputStream(
                samplerate=native_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=capture_chunk_size,
                device=input_device,
            )
            stream.start()

            # Buffer for accumulating samples for VAD (which needs 512 samples at 16kHz)
            vad_buffer = np.zeros(0, dtype=np.float32)

            while self._recording:
                elapsed = time.monotonic() - record_start

                # Hard timeout
                if elapsed > HARD_TIMEOUT_SEC:
                    logger.info("Hard timeout reached")
                    break

                # Read audio chunk at native rate
                data, overflowed = stream.read(capture_chunk_size)
                if overflowed:
                    logger.warning("Audio buffer overflow")

                chunk_native = data.squeeze()
                audio_chunks.append(chunk_native.copy())

                # Resample to 16kHz for VAD if needed
                if native_rate != SAMPLE_RATE:
                    from scipy.signal import resample_poly
                    chunk_16k = resample_poly(chunk_native, SAMPLE_RATE, native_rate).astype(np.float32)
                else:
                    chunk_16k = chunk_native

                # Accumulate into VAD buffer and process 512-sample chunks
                vad_buffer = np.concatenate([vad_buffer, chunk_16k])
                stop_recording = False
                while len(vad_buffer) >= vad_chunk_size:
                    chunk = vad_buffer[:vad_chunk_size]
                    vad_buffer = vad_buffer[vad_chunk_size:]

                    # Run VAD on this chunk
                    chunk_tensor = torch.from_numpy(chunk)
                    speech_prob = self._vad_model(chunk_tensor, SAMPLE_RATE).item()

                    if speech_prob > 0.5:
                        speech_detected = True
                        silence_start = None
                    elif speech_detected:
                        # Speech was detected before, now silence
                        if silence_start is None:
                            silence_start = time.monotonic()
                        elif time.monotonic() - silence_start > VAD_SILENCE_THRESHOLD_SEC:
                            logger.info("Silence detected — stopping")
                            stop_recording = True
                            break

                if stop_recording:
                    break

            stream.stop()
            stream.close()

        except Exception:
            logger.exception("Error during recording")
            self._recording = False
            return

        self._recording = False

        if not speech_detected or len(audio_chunks) == 0:
            logger.info("No speech detected")
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    bus.publish(STTResultEvent(text="", confidence=0.0)),
                    self._loop,
                )
            return

        # Concatenate audio
        audio = np.concatenate(audio_chunks)
        # Resample to 16kHz for Whisper if needed
        if native_rate != SAMPLE_RATE:
            from scipy.signal import resample_poly
            audio = resample_poly(audio, SAMPLE_RATE, native_rate).astype(np.float32)
        duration = len(audio) / SAMPLE_RATE
        logger.info(f"Captured {duration:.1f}s of audio, transcribing...")

        # Transcribe with Whisper
        try:
            segments, info = self._whisper_model.transcribe(
                audio,
                language="en",
                beam_size=1,  # Faster, good enough for short answers
                vad_filter=False,  # We already did VAD
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            confidence = 1.0 - (info.language_probability if hasattr(info, 'language_probability') else 0.0)
            logger.info(f"Transcription: '{text}' (confidence: {confidence:.2f})")
        except Exception:
            logger.exception("Whisper transcription failed")
            text = ""
            confidence = 0.0

        # Publish result
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                bus.publish(STTResultEvent(text=text, confidence=confidence)),
                self._loop,
            )


# Singleton
stt_engine = STTEngine()
