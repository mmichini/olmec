"""LED driver abstraction. WS2812B addressable strip on Pi, mock on macOS."""

import logging
from abc import ABC, abstractmethod

from olmec.config import settings
from olmec.events import AmplitudeEvent, bus

logger = logging.getLogger(__name__)

# Default eye color — classic red
DEFAULT_COLOR: tuple[int, int, int] = (255, 0, 0)


class LEDDriver(ABC):
    """Abstract LED driver.

    Tracks an overall color, brightness, and per-eye colors.
    Subclasses implement `_apply()` to push the state to the physical LEDs.
    """

    def __init__(self):
        self._color: tuple[int, int, int] = DEFAULT_COLOR
        self._brightness: float = 0.0
        self._eye_colors: list[tuple[int, int, int]] = [DEFAULT_COLOR, DEFAULT_COLOR]
        # When True, amplitude events are ignored — for manual LED testing
        self._test_mode: bool = False

    @abstractmethod
    async def _apply(self) -> None:
        """Push the current color/brightness/eye state to the physical LEDs."""
        ...

    async def set_brightness(self, brightness: float) -> None:
        """Set overall brightness (0.0 to 1.0). Driven by audio amplitude."""
        self._brightness = max(0.0, min(1.0, brightness))
        await self._apply()

    async def set_color(self, color: tuple[int, int, int]) -> None:
        """Set all LEDs to a single color."""
        self._color = color
        self._eye_colors = [color, color]
        await self._apply()

    async def set_eye_color(self, eye: int, color: tuple[int, int, int]) -> None:
        """Set just one eye's color (eye=0 or eye=1)."""
        if 0 <= eye < len(self._eye_colors):
            self._eye_colors[eye] = color
            await self._apply()

    async def clear(self) -> None:
        """Turn all LEDs off."""
        self._brightness = 0.0
        await self._apply()

    async def start(self) -> None:
        """Register for amplitude events."""
        bus.subscribe(AmplitudeEvent, self._on_amplitude)
        logger.info(f"{self.__class__.__name__} started")

    async def stop(self) -> None:
        """Clean up."""
        bus.unsubscribe(AmplitudeEvent, self._on_amplitude)
        await self.clear()
        logger.info(f"{self.__class__.__name__} stopped")

    async def _on_amplitude(self, event: AmplitudeEvent) -> None:
        if self._test_mode:
            return
        await self.set_brightness(event.rms)

    @property
    def is_test_mode(self) -> bool:
        return self._test_mode

    def set_test_mode(self, enabled: bool) -> None:
        """Toggle test mode (when enabled, ignores amplitude events)."""
        self._test_mode = enabled

    @property
    def state(self) -> dict:
        """Current driver state — for the test UI."""
        return {
            "test_mode": self._test_mode,
            "brightness": round(self._brightness, 3),
            "eye_colors": [list(c) for c in self._eye_colors],
        }


class MockLEDDriver(LEDDriver):
    """Mock LED driver for macOS development. Logs brightness changes."""

    def __init__(self):
        super().__init__()
        self._callback = None

    async def _apply(self) -> None:
        if self._callback:
            await self._callback(self._brightness)

    def on_brightness_change(self, callback):
        """Register a callback for brightness changes (used by digital twin)."""
        self._callback = callback


class NeoPixelLEDDriver(LEDDriver):
    """Raspberry Pi LED driver using WS2812B addressable strip via SPI.

    Layout: 80 LEDs total, daisy-chained.
      - LEDs  0-39: eye 0 (rows 1-2)
      - LEDs 40-79: eye 1 (rows 1-2)

    Wiring: data line on GPIO 10 (SPI0 MOSI, physical pin 19) through a
    330Ω resistor to the strip's DI pad. 5V power from a separate buck
    converter — NOT the Pi's 5V rail. Common ground.
    """

    NUM_PIXELS = 80
    EYE0_RANGE = range(0, 40)
    EYE1_RANGE = range(40, 80)
    MAX_HARDWARE_BRIGHTNESS = 0.6  # safety cap to limit current draw

    def __init__(self):
        super().__init__()
        self._pixels = None
        self._refresh_task = None

    async def start(self) -> None:
        try:
            import board
            import neopixel_spi as neopixel
            spi = board.SPI()
            self._pixels = neopixel.NeoPixel_SPI(
                spi,
                self.NUM_PIXELS,
                pixel_order=neopixel.GRB,
                brightness=self.MAX_HARDWARE_BRIGHTNESS,
                auto_write=False,
            )
            logger.info(f"NeoPixel SPI initialized ({self.NUM_PIXELS} LEDs)")
        except Exception:
            logger.exception("NeoPixel SPI init failed — falling back to mock")
            return
        await super().start()
        # Start the keep-alive refresh task to prevent pixel drift
        import asyncio
        self._refresh_task = asyncio.create_task(self._keepalive_loop())

    async def _keepalive_loop(self) -> None:
        """Periodically re-send the current state so pixels don't drift from noise."""
        import asyncio
        while self._pixels is not None:
            try:
                await asyncio.sleep(0.1)  # 10 Hz
                if self._pixels is not None:
                    await self._apply()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Keep-alive refresh error")

    async def _apply(self) -> None:
        if not self._pixels:
            return
        # Scale color by current brightness (smoother than using strip brightness)
        eye0 = _scale(self._eye_colors[0], self._brightness)
        eye1 = _scale(self._eye_colors[1], self._brightness)
        for i in self.EYE0_RANGE:
            self._pixels[i] = eye0
        for i in self.EYE1_RANGE:
            self._pixels[i] = eye1
        self._pixels.show()

    async def stop(self) -> None:
        # Cancel keep-alive first so it doesn't try to draw to a closed strip
        task = getattr(self, "_refresh_task", None)
        if task:
            task.cancel()
            try:
                await task
            except (Exception, BaseException):
                pass
        await super().stop()
        if self._pixels:
            self._pixels.fill((0, 0, 0))
            self._pixels.show()
            self._pixels = None


def _scale(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """Scale an RGB color by a 0.0-1.0 brightness factor."""
    return (
        int(color[0] * factor),
        int(color[1] * factor),
        int(color[2] * factor),
    )


def create_led_driver() -> LEDDriver:
    """Factory: returns the appropriate LED driver for the current platform."""
    if settings.is_pi:
        return NeoPixelLEDDriver()
    return MockLEDDriver()
