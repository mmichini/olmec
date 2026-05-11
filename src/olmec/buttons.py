"""Physical GPIO button handling. Maps button presses to WebSocket commands."""

import asyncio
import logging

from olmec.config import settings

logger = logging.getLogger(__name__)


class ButtonHandler:
    """Manages a set of GPIO buttons that fire WS-equivalent commands."""

    def __init__(self, app):
        self._app = app
        self._buttons: list = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        if not settings.is_pi:
            logger.info("Not on Pi — skipping button setup")
            return

        try:
            from gpiozero import Button
        except ImportError:
            logger.warning("gpiozero not available — skipping buttons")
            return

        self._loop = asyncio.get_running_loop()

        # Map pin -> WS command payload
        button_map = [
            (settings.button_pin_next, {"command": "next_question"}, "Next Question"),
            (settings.button_pin_correct, {"command": "judge_correct"}, "Correct"),
            (settings.button_pin_incorrect, {"command": "judge_incorrect"}, "Incorrect"),
            (settings.button_pin_wandering, {"command": "play_wandering"}, "Say Something"),
        ]

        for pin, cmd_data, label in button_map:
            if pin <= 0:
                continue
            try:
                btn = Button(pin, pull_up=True, bounce_time=0.05)
                btn.when_pressed = lambda data=cmd_data, l=label: self._fire(data, l)
                self._buttons.append(btn)
                logger.info(f"Button on GPIO {pin}: {label}")
            except Exception:
                logger.exception(f"Failed to set up button on GPIO {pin}")

    def _fire(self, cmd_data: dict, label: str) -> None:
        """Called from gpiozero's thread when a button is pressed."""
        if not self._loop:
            return
        logger.info(f"Button pressed: {label}")
        from olmec.api.ws import handle_ws_message
        asyncio.run_coroutine_threadsafe(
            handle_ws_message(cmd_data, self._app),
            self._loop,
        )

    async def stop(self) -> None:
        for btn in self._buttons:
            try:
                btn.close()
            except Exception:
                pass
        self._buttons = []
