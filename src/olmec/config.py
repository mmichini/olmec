"""Application configuration via environment variables."""

import sys
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


def _detect_platform() -> Literal["pi", "mac", "linux"]:
    """Detect whether we're running on a Raspberry Pi, macOS, or other Linux."""
    if sys.platform == "darwin":
        return "mac"
    if sys.platform == "linux":
        try:
            model = Path("/proc/device-tree/model").read_text()
            if "Raspberry Pi" in model:
                return "pi"
        except FileNotFoundError:
            pass
        return "linux"
    return "linux"


class Settings(BaseSettings):
    model_config = {"env_prefix": "OLMEC_", "env_file": ".env", "extra": "ignore"}

    # Deployment
    mode: Literal["local", "pi", "cloud"] = "local"
    password: str = "changeme"

    # Audio
    voice: str = "olmec-v1"
    # Audio device selection — match by substring of device name (case insensitive)
    # Use `python -c "import sounddevice; print(sounddevice.query_devices())"` to list devices
    audio_input_device: str = ""   # e.g. "USB" to match a USB mic
    audio_output_device: str = ""  # e.g. "USB" to match a USB speaker

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Detected at runtime
    platform: Literal["pi", "mac", "linux"] = "mac"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.platform = _detect_platform()

    @property
    def data_dir(self) -> Path:
        return Path(__file__).parent.parent.parent / "data"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio" / self.voice

    @property
    def content_dir(self) -> Path:
        return self.data_dir / "content"

    @property
    def is_pi(self) -> bool:
        return self.platform == "pi"


settings = Settings()
