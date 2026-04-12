"""REST API routes."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from olmec.config import settings
from olmec.questions.db import question_db
from olmec.state_machine import state_machine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/status")
async def get_status():
    """Get current Olmec status."""
    return {
        "state": state_machine.to_dict(),
        "platform": settings.platform,
        "mode": settings.mode,
        "voice": settings.voice,
    }


@router.get("/audio/list")
async def list_audio():
    """List all available audio files for the current voice."""
    audio_dir = settings.audio_dir
    if not audio_dir.exists():
        return {"files": {}}

    files = {}
    for category_dir in audio_dir.iterdir():
        if category_dir.is_dir():
            category_files = sorted(
                str(f.relative_to(audio_dir))
                for f in category_dir.glob("*.wav")
            )
            files[category_dir.name] = category_files

    return {"files": files}


@router.get("/voices")
async def list_voices():
    """List available voice directories."""
    audio_base = settings.data_dir / "audio"
    if not audio_base.exists():
        return {"voices": [], "active": settings.voice}

    voices = [
        d.name for d in audio_base.iterdir()
        if d.is_dir() and d.name != "__pycache__"
    ]
    return {"voices": sorted(voices), "active": settings.voice}


@router.get("/questions")
async def list_questions():
    """List all questions in the database."""
    questions = question_db.get_all_questions()
    return {
        "questions": [
            {
                "id": q.id,
                "question_text": q.question_text,
                "answer": q.answer,
                "category": q.category,
                "difficulty": q.difficulty,
                "times_asked": q.times_asked,
                "times_correct": q.times_correct,
            }
            for q in questions
        ]
    }


@router.get("/questions/stats")
async def question_stats():
    """Get question usage statistics."""
    questions = question_db.get_all_questions()
    total_asked = sum(q.times_asked for q in questions)
    total_correct = sum(q.times_correct for q in questions)
    return {
        "total_questions": len(questions),
        "total_asked": total_asked,
        "total_correct": total_correct,
        "accuracy": round(total_correct / total_asked, 2) if total_asked > 0 else 0,
    }
