#!/usr/bin/env python3
"""Seed the SQLite database from YAML content files.

Usage:
    python pipeline/seed_db.py
"""

from pathlib import Path

import yaml

# Add project root to path so we can import olmec
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from olmec.questions.db import QuestionDB
from olmec.questions.models import AudioClip, Question

CONTENT_DIR = Path(__file__).parent.parent / "data" / "content"
DB_PATH = Path(__file__).parent.parent / "data" / "questions.db"


def load_questions(db: QuestionDB) -> int:
    path = CONTENT_DIR / "questions.yaml"
    if not path.exists():
        print(f"  Skipping {path} (not found)")
        return 0

    data = yaml.safe_load(path.read_text())
    count = 0
    for entry in data:
        q = Question(
            id=entry["id"],
            question_text=entry["question_text"],
            answer=entry["answer"],
            accept=entry.get("accept", [entry["answer"].lower()]),
            category=entry.get("category", ""),
            difficulty=entry.get("difficulty", 3),
        )
        db.upsert_question(q)

        # Also register the question audio clip
        clip = AudioClip(
            id=entry["id"],
            text=entry["question_text"],
            category="questions",
            takes=entry.get("takes", 1),
        )
        db.upsert_clip(clip)
        count += 1

    return count


def load_responses(db: QuestionDB) -> int:
    path = CONTENT_DIR / "responses.yaml"
    if not path.exists():
        print(f"  Skipping {path} (not found)")
        return 0

    data = yaml.safe_load(path.read_text())
    count = 0
    for category, entries in data.items():
        for entry in entries:
            clip = AudioClip(
                id=entry["id"],
                text=entry["text"],
                category=category,
                takes=entry.get("takes", 1),
            )
            db.upsert_clip(clip)
            count += 1

    return count


def load_simple_clips(db: QuestionDB, filename: str, category: str) -> int:
    path = CONTENT_DIR / filename
    if not path.exists():
        print(f"  Skipping {path} (not found)")
        return 0

    data = yaml.safe_load(path.read_text())
    count = 0
    for entry in data:
        clip = AudioClip(
            id=entry["id"],
            text=entry["text"],
            category=category,
            tags=entry.get("tags", []),
            takes=entry.get("takes", 1),
        )
        db.upsert_clip(clip)
        count += 1

    return count


def main():
    print(f"Seeding database: {DB_PATH}")
    print(f"Content dir: {CONTENT_DIR}\n")

    db = QuestionDB(db_path=DB_PATH)
    db.open()

    n = load_questions(db)
    print(f"  Questions: {n}")

    n = load_responses(db)
    print(f"  Responses: {n}")

    n = load_simple_clips(db, "wandering.yaml", "wandering")
    print(f"  Wandering: {n}")

    n = load_simple_clips(db, "canned.yaml", "canned")
    print(f"  Canned: {n}")

    db.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
