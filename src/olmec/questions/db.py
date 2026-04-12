"""SQLite database for questions and content metadata."""

import logging
import random
import sqlite3
from pathlib import Path

from olmec.config import settings
from olmec.questions.models import AudioClip, Question, QuestionWithAudio

logger = logging.getLogger(__name__)

DB_PATH = settings.data_dir / "questions.db"

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    question_text TEXT NOT NULL,
    answer TEXT NOT NULL,
    accept TEXT NOT NULL,  -- JSON list of accepted answers
    category TEXT DEFAULT '',
    difficulty INTEGER DEFAULT 3,
    times_asked INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audio_clips (
    id TEXT NOT NULL,
    text TEXT NOT NULL,
    category TEXT NOT NULL,  -- wandering, canned, correct, incorrect, correct_no_jello, question
    tags TEXT DEFAULT '[]',  -- JSON list
    takes INTEGER DEFAULT 1,
    PRIMARY KEY (id, category)
);
"""


class QuestionDB:
    """Synchronous SQLite database for questions and audio clip metadata."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or DB_PATH
        self._conn: sqlite3.Connection | None = None
        self._asked_ids: list[str] = []  # track recently asked to avoid repeats

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CREATE_TABLES)
        logger.info(f"Question DB opened: {self._db_path}")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Questions ---

    def get_question(self, question_id: str) -> Question | None:
        row = self._conn.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_question(row)

    def get_random_question(self, difficulty: int | None = None, max_difficulty: int | None = None) -> Question | None:
        """Get a random question, optionally filtered by difficulty.
        Avoids repeating recently asked questions.
        """
        query = "SELECT * FROM questions WHERE 1=1"
        params = []

        if difficulty is not None:
            query += " AND difficulty = ?"
            params.append(difficulty)
        elif max_difficulty is not None:
            query += " AND difficulty <= ?"
            params.append(max_difficulty)

        # Exclude recently asked (keep last N out of rotation)
        if self._asked_ids:
            placeholders = ",".join("?" * len(self._asked_ids))
            query += f" AND id NOT IN ({placeholders})"
            params.extend(self._asked_ids)

        rows = self._conn.execute(query, params).fetchall()
        if not rows:
            # If all questions exhausted, reset history and try again
            self._asked_ids.clear()
            rows = self._conn.execute(
                query.split(" AND id NOT IN")[0], params[:1] if difficulty or max_difficulty else []
            ).fetchall()

        if not rows:
            return None

        row = random.choice(rows)
        question = self._row_to_question(row)
        self._asked_ids.append(question.id)
        # Keep history to half the total question count
        total = self._conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        max_history = max(1, total // 2)
        if len(self._asked_ids) > max_history:
            self._asked_ids = self._asked_ids[-max_history:]

        return question

    def record_asked(self, question_id: str, correct: bool) -> None:
        """Record that a question was asked and whether it was answered correctly."""
        if correct:
            self._conn.execute(
                "UPDATE questions SET times_asked = times_asked + 1, times_correct = times_correct + 1 WHERE id = ?",
                (question_id,),
            )
        else:
            self._conn.execute(
                "UPDATE questions SET times_asked = times_asked + 1 WHERE id = ?",
                (question_id,),
            )
        self._conn.commit()

    def get_all_questions(self) -> list[Question]:
        rows = self._conn.execute("SELECT * FROM questions ORDER BY category, difficulty").fetchall()
        return [self._row_to_question(row) for row in rows]

    # --- Audio clips ---

    def get_random_clip(self, category: str) -> AudioClip | None:
        """Get a random audio clip from a category."""
        rows = self._conn.execute(
            "SELECT * FROM audio_clips WHERE category = ?", (category,)
        ).fetchall()
        if not rows:
            return None
        row = random.choice(rows)
        return self._row_to_clip(row)

    def get_all_clips(self, category: str) -> list[AudioClip]:
        rows = self._conn.execute(
            "SELECT * FROM audio_clips WHERE category = ?", (category,)
        ).fetchall()
        return [self._row_to_clip(row) for row in rows]

    # --- Seeding ---

    def upsert_question(self, q: Question) -> None:
        import json
        self._conn.execute(
            """INSERT OR REPLACE INTO questions (id, question_text, answer, accept, category, difficulty, times_asked, times_correct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (q.id, q.question_text, q.answer, json.dumps(q.accept), q.category, q.difficulty, q.times_asked, q.times_correct),
        )
        self._conn.commit()

    def upsert_clip(self, clip: AudioClip) -> None:
        import json
        self._conn.execute(
            """INSERT OR REPLACE INTO audio_clips (id, text, category, tags, takes)
               VALUES (?, ?, ?, ?, ?)""",
            (clip.id, clip.text, clip.category, json.dumps(clip.tags), clip.takes),
        )
        self._conn.commit()

    # --- Helpers ---

    def _row_to_question(self, row: sqlite3.Row) -> Question:
        import json
        return Question(
            id=row["id"],
            question_text=row["question_text"],
            answer=row["answer"],
            accept=json.loads(row["accept"]),
            category=row["category"],
            difficulty=row["difficulty"],
            times_asked=row["times_asked"],
            times_correct=row["times_correct"],
        )

    def _row_to_clip(self, row: sqlite3.Row) -> AudioClip:
        import json
        return AudioClip(
            id=row["id"],
            text=row["text"],
            category=row["category"],
            tags=json.loads(row["tags"]),
            takes=row["takes"],
        )


def resolve_audio_path(clip_id: str, category: str, takes: int = 1) -> str:
    """Resolve a clip ID to its audio file path within the active voice directory."""
    audio_dir = settings.audio_dir / category
    if takes > 1:
        # Pick a random take
        available = list(audio_dir.glob(f"{clip_id}_take*.wav"))
        if available:
            return str(random.choice(available))
    # Single take — just the base filename
    path = audio_dir / f"{clip_id}.wav"
    if path.exists():
        return str(path)
    # Fallback: try any matching file
    available = list(audio_dir.glob(f"{clip_id}*.wav"))
    return str(available[0]) if available else ""


# Singleton
question_db = QuestionDB()
