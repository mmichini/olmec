"""FastAPI application factory and entry point."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from olmec.api.routes import router as api_router
from olmec.api.ws import handle_ws_message, manager, setup_ws_events
from olmec.audio.engine import audio_engine
from olmec.config import settings
from olmec.led.driver import create_led_driver
from olmec.questions.db import question_db
from olmec.state_machine import state_machine
from olmec.stt.engine import stt_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Resolve paths relative to the package
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_UI_DIR = _PROJECT_ROOT / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info(f"Starting Olmec (platform={settings.platform}, mode={settings.mode})")

    # Start subsystems
    question_db.open()
    led_driver = create_led_driver()
    await audio_engine.start()
    await led_driver.start()
    await state_machine.start()
    await stt_engine.start()
    await setup_ws_events()

    # Store LED driver on app for access
    app.state.led_driver = led_driver

    logger.info("Olmec is ready")
    yield

    # Shutdown
    await stt_engine.stop()
    await state_machine.stop()
    await led_driver.stop()
    await audio_engine.stop()
    question_db.close()
    logger.info("Olmec shut down")


app = FastAPI(title="Olmec", lifespan=lifespan)

# API routes
app.include_router(api_router)


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await handle_ws_message(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Serve static UI files
if _UI_DIR.exists():
    # Combined UI (Olmec face + operator panel toggle)
    combined_dir = _UI_DIR / "combined"
    if combined_dir.exists():
        app.mount("/olmec", StaticFiles(directory=str(combined_dir), html=True), name="combined")

    # Standalone operator UI (for phone use at the festival)
    operator_dir = _UI_DIR / "operator"
    if operator_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(operator_dir), html=True), name="operator")

    # Standalone twin (legacy)
    twin_dir = _UI_DIR / "twin"
    if twin_dir.exists():
        app.mount("/twin", StaticFiles(directory=str(twin_dir), html=True), name="twin")

# Serve audio files
_AUDIO_DIR = settings.data_dir / "audio"
if _AUDIO_DIR.exists():
    app.mount("/audio", StaticFiles(directory=str(_AUDIO_DIR)), name="audio")


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/olmec/")


def cli():
    """Entry point for `olmec` command."""
    import uvicorn
    uvicorn.run(
        "olmec.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.mode == "local",
    )


if __name__ == "__main__":
    cli()
