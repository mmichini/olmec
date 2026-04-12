"""Data models for questions and content."""

from dataclasses import dataclass, field


@dataclass
class Question:
    id: str
    question_text: str
    answer: str
    accept: list[str] = field(default_factory=list)  # acceptable answer variants
    category: str = ""
    difficulty: int = 3  # 1-5
    times_asked: int = 0
    times_correct: int = 0

    def check_answer(self, response: str) -> bool:
        """Check if a response matches any accepted answer (fuzzy)."""
        normalized = response.strip().lower()
        for accepted in self.accept:
            if accepted.lower() in normalized or normalized in accepted.lower():
                return True
        return False


@dataclass
class AudioClip:
    id: str
    text: str
    category: str  # "wandering", "canned", "correct", "incorrect", "correct_no_jello", "question"
    tags: list[str] = field(default_factory=list)
    takes: int = 1


@dataclass
class QuestionWithAudio:
    """A question bundled with its audio file path."""
    question: Question
    audio_path: str  # path to the question audio WAV
