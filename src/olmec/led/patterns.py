"""LED animations / test patterns. Run on top of an LEDDriver."""

import asyncio
import colorsys
import logging
from typing import Awaitable, Callable

from olmec.led.driver import LEDDriver

logger = logging.getLogger(__name__)


class PatternRunner:
    """Runs an animation against an LEDDriver. Only one pattern at a time."""

    def __init__(self, driver: LEDDriver):
        self._driver = driver
        self._task: asyncio.Task | None = None

    async def start(self, name: str, **kwargs) -> bool:
        """Start a named pattern. Cancels any previous pattern. Returns True on success."""
        await self.stop()
        fn = PATTERNS.get(name)
        if not fn:
            logger.warning(f"Unknown pattern: {name}")
            return False
        self._driver.set_test_mode(True)
        self._task = asyncio.create_task(_safe_run(fn, self._driver, **kwargs))
        return True

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()


async def _safe_run(fn: Callable, driver: LEDDriver, **kwargs) -> None:
    try:
        await fn(driver, **kwargs)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Pattern crashed")


# --- Patterns ---

async def pulse(driver: LEDDriver, color: tuple = (255, 0, 0), period_s: float = 1.5) -> None:
    """Smooth brightness pulse 0 → 1 → 0."""
    await driver.set_color(color)
    import math
    t = 0.0
    while True:
        b = (math.sin(t) + 1) / 2  # 0 to 1
        await driver.set_brightness(b)
        t += 0.1
        await asyncio.sleep(period_s / 60)


async def alternate_eyes(driver: LEDDriver, color_a: tuple = (255, 0, 0), color_b: tuple = (0, 0, 255), period_s: float = 1.0) -> None:
    """Eyes alternate between two colors."""
    await driver.set_brightness(1.0)
    swap = False
    while True:
        if swap:
            await driver.set_eye_color(0, color_b)
            await driver.set_eye_color(1, color_a)
        else:
            await driver.set_eye_color(0, color_a)
            await driver.set_eye_color(1, color_b)
        swap = not swap
        await asyncio.sleep(period_s)


async def blink(driver: LEDDriver, color: tuple = (255, 0, 0), period_s: float = 0.4) -> None:
    """On/off blink."""
    await driver.set_color(color)
    on = True
    while True:
        await driver.set_brightness(1.0 if on else 0.0)
        on = not on
        await asyncio.sleep(period_s)


async def rainbow(driver: LEDDriver, period_s: float = 4.0) -> None:
    """Cycle hue across all LEDs together."""
    await driver.set_brightness(1.0)
    hue = 0.0
    while True:
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        await driver.set_color((int(r * 255), int(g * 255), int(b * 255)))
        hue = (hue + 0.01) % 1.0
        await asyncio.sleep(period_s / 100)


async def rainbow_eyes(driver: LEDDriver, period_s: float = 4.0) -> None:
    """Each eye cycles hue independently, offset by 180°."""
    await driver.set_brightness(1.0)
    hue = 0.0
    while True:
        for eye, offset in enumerate([0.0, 0.5]):
            h = (hue + offset) % 1.0
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            await driver.set_eye_color(eye, (int(r * 255), int(g * 255), int(b * 255)))
        hue = (hue + 0.01) % 1.0
        await asyncio.sleep(period_s / 100)


async def fade_in(driver: LEDDriver, color: tuple = (255, 0, 0), duration_s: float = 2.0) -> None:
    """Fade up from off to full once, then hold."""
    await driver.set_color(color)
    steps = 50
    for i in range(steps + 1):
        await driver.set_brightness(i / steps)
        await asyncio.sleep(duration_s / steps)
    # hold


async def heartbeat(driver: LEDDriver, color: tuple = (255, 0, 0)) -> None:
    """Two quick pulses, then pause — like a heartbeat."""
    await driver.set_color(color)
    while True:
        for _ in range(2):
            for b in (0.2, 0.6, 1.0, 0.6, 0.2):
                await driver.set_brightness(b)
                await asyncio.sleep(0.06)
            await driver.set_brightness(0.0)
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.6)


PATTERNS: dict[str, Callable[..., Awaitable[None]]] = {
    "pulse": pulse,
    "alternate_eyes": alternate_eyes,
    "blink": blink,
    "rainbow": rainbow,
    "rainbow_eyes": rainbow_eyes,
    "fade_in": fade_in,
    "heartbeat": heartbeat,
}
