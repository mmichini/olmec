"""Answer judging — fuzzy matching of STT transcription against accepted answers."""

import logging
import re

logger = logging.getLogger(__name__)


def normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)  # Remove punctuation
    text = re.sub(r"\s+", " ", text)  # Collapse whitespace
    # Remove common filler words from STT output
    for filler in ["um", "uh", "like", "so", "well", "i think", "i believe", "it's", "its", "the answer is"]:
        text = text.replace(filler, "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def check_answer(transcription: str, accepted_answers: list[str]) -> tuple[bool, float]:
    """Check if a transcription matches any accepted answer.

    Returns (is_correct, confidence) where confidence is 0.0-1.0.
    Trivia answers are typically short (1-3 words), so we use
    simple substring matching rather than edit distance.
    """
    norm_response = normalize(transcription)

    if not norm_response:
        return False, 0.0

    for accepted in accepted_answers:
        norm_accepted = normalize(accepted)

        if not norm_accepted:
            continue

        # Exact match
        if norm_response == norm_accepted:
            return True, 1.0

        # Response contains the accepted answer
        if norm_accepted in norm_response:
            return True, 0.9

        # Accepted answer contains the response (e.g., they said "nile" and accepted is "the nile")
        if norm_response in norm_accepted and len(norm_response) >= 3:
            return True, 0.85

        # Check individual words for single-word answers
        response_words = set(norm_response.split())
        accepted_words = set(norm_accepted.split())
        if accepted_words and accepted_words.issubset(response_words):
            return True, 0.8

    return False, 0.0
