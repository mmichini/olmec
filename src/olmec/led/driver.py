"""LED driver abstraction. Uses GPIO PWM on Pi, mock on macOS."""

import logging
from abc import ABC, abstractmethod

from olmec.config import settings
from olmec.events import AmplitudeEvent, bus

logger = logging.getLogger(__name__)


class LEDDriver(ABC):
    """Abstract LED driver."""

    @abstractmethod
    async def set_brightness(self, brightness: float) -> None:
        """Set LED brightness (0.0 to 1.0)."""
        ...

    async def start(self) -> None:
        """Register for amplitude events."""
        bus.subscribe(AmplitudeEvent, self._on_amplitude)
        logger.info(f"{self.__class__.__name__} started")

    async def stop(self) -> None:
        """Clean up."""
        bus.unsubscribe(AmplitudeEvent, self._on_amplitude)
        await self.set_brightness(0.0)
        logger.info(f"{self.__class__.__name__} stopped")

    async def _on_amplitude(self, event: AmplitudeEvent) -> None:
        await self.set_brightness(event.rms)


class MockLEDDriver(LEDDriver):
    """Mock LED driver for macOS development. Logs brightness changes."""

    def __init__(self):
        self._brightness: float = 0.0
        self._callback = None

    async def set_brightness(self, brightness: float) -> None:
        self._brightness = max(0.0, min(1.0, brightness))
        if self._callback:
            await self._callback(self._brightness)

    def on_brightness_change(self, callback):
        """Register a callback for brightness changes (used by digital twin)."""
        self._callback = callback


class PiLEDDriver(LEDDriver):
    """Raspberry Pi LED driver using GPIO PWM."""

    def __init__(self, pin: int = 18):
        self._pin = pin
        self._pwm = None

    async def start(self) -> None:
        try:
            from gpiozero import PWMLED
            self._pwm = PWMLED(self._pin)
            logger.info(f"GPIO PWM LED initialized on pin {self._pin}")
        except ImportError:
            logger.error("gpiozero not available — falling back to mock")
            return
        await super().start()

    async def set_brightness(self, brightness: float) -> None:
        if self._pwm:
            self._pwm.value = max(0.0, min(1.0, brightness))

    async def stop(self) -> None:
        await super().stop()
        if self._pwm:
            self._pwm.close()


def create_led_driver() -> LEDDriver:
    """Factory: returns the appropriate LED driver for the current platform."""
    if settings.is_pi:
        return PiLEDDriver()
    return MockLEDDriver()
