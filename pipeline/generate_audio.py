#!/usr/bin/env python3
"""Generate audio clips from text content using ElevenLabs TTS API.

Usage:
    # Generate all missing clips
    python pipeline/generate_audio.py

    # Regenerate everything (new voice, etc.)
    python pipeline/generate_audio.py --regenerate-all

    # Use a specific voice
    python pipeline/generate_audio.py --voice-id YOUR_VOICE_ID

    # Output to a different voice directory
    python pipeline/generate_audio.py --voice-name olmec-v2

    # List available voices
    python pipeline/generate_audio.py --list-voices
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from elevenlabs import ElevenLabs


# --- Content loading from YAML ---

CONTENT_DIR = Path(__file__).parent.parent / "data" / "content"


def load_content_from_yaml() -> dict[str, list[tuple[str, str, int]]]:
    """Load all content from YAML files. Returns {category: [(id, text, takes), ...]}."""
    import yaml

    content = {}

    # Questions
    path = CONTENT_DIR / "questions.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text())
        content["questions"] = [
            (entry["id"], entry["question_text"], entry.get("takes", 1))
            for entry in data
        ]
        # Answer reveal clips: "The correct answer was [answer]."
        content["reveals"] = [
            (f"reveal_{entry['id']}", f"The correct answer was {entry['answer']}.", 1)
            for entry in data
        ]

    # Responses (has sub-categories: correct, incorrect, correct_no_jello)
    path = CONTENT_DIR / "responses.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text())
        responses = []
        for _category, entries in data.items():
            for entry in entries:
                responses.append((entry["id"], entry["text"], entry.get("takes", 1)))
        content["responses"] = responses

    # Wandering
    path = CONTENT_DIR / "wandering.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text())
        content["wandering"] = [
            (entry["id"], entry["text"], entry.get("takes", 1))
            for entry in data
        ]

    # Canned
    path = CONTENT_DIR / "canned.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text())
        content["canned"] = [
            (entry["id"], entry["text"], entry.get("takes", 1))
            for entry in data
        ]

    return content


def list_voices(client: ElevenLabs):
    """Print available ElevenLabs voices."""
    response = client.voices.get_all()
    print("\nAvailable voices:\n")
    for voice in response.voices:
        labels = ", ".join(f"{k}={v}" for k, v in (voice.labels or {}).items())
        print(f"  {voice.voice_id}  {voice.name:30s}  {labels}")
    print()


def generate_clip(
    client: ElevenLabs,
    voice_id: str,
    text: str,
    output_path: Path,
    model_id: str = "eleven_multilingual_v2",
):
    """Generate a single audio clip and save as WAV."""
    import io
    import soundfile as sf
    import numpy as np

    audio_generator = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        output_format="mp3_44100_128",
    )

    # Collect all audio bytes (MP3)
    mp3_bytes = b"".join(audio_generator)

    # Convert MP3 to WAV (16-bit 44.1kHz mono) using soundfile
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data, samplerate = sf.read(io.BytesIO(mp3_bytes))

    # Convert to mono if stereo
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Resample to 44100 if needed
    if samplerate != 44100:
        from scipy.signal import resample
        num_samples = int(len(data) * 44100 / samplerate)
        data = resample(data, num_samples).astype(np.float32)
        samplerate = 44100

    sf.write(str(output_path), data, samplerate, subtype="PCM_16")


def main():
    parser = argparse.ArgumentParser(description="Generate Olmec audio clips via ElevenLabs")
    parser.add_argument("--voice-id", help="ElevenLabs voice ID (overrides ELEVENLABS_VOICE_ID env var)")
    parser.add_argument("--voice-name", default=None, help="Output voice directory name (default: from OLMEC_VOICE env var)")
    parser.add_argument("--regenerate-all", action="store_true", help="Regenerate all clips, even if they exist")
    parser.add_argument("--list-voices", action="store_true", help="List available ElevenLabs voices and exit")
    parser.add_argument("--category", help="Only generate clips for this category (wandering, questions, responses, canned)")
    parser.add_argument("--model", default="eleven_multilingual_v2", help="ElevenLabs model ID")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated without calling the API")
    args = parser.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)

    client = ElevenLabs(api_key=api_key)

    if args.list_voices:
        list_voices(client)
        return

    voice_id = args.voice_id or os.environ.get("ELEVENLABS_VOICE_ID")
    if not voice_id:
        print("Error: No voice ID. Use --voice-id or set ELEVENLABS_VOICE_ID in .env")
        print("Run with --list-voices to see available voices.")
        sys.exit(1)

    voice_name = args.voice_name or os.environ.get("OLMEC_VOICE", "olmec-v1")
    output_base = Path(__file__).parent.parent / "data" / "audio" / voice_name

    all_content = load_content_from_yaml()

    # Filter categories if specified
    categories = all_content
    if args.category:
        if args.category not in all_content:
            print(f"Error: Unknown category '{args.category}'. Choose from: {', '.join(all_content.keys())}")
            sys.exit(1)
        categories = {args.category: all_content[args.category]}

    # Count total clips to generate
    total = 0
    to_generate = []
    for category, entries in categories.items():
        for name, text, takes in entries:
            for take_num in range(1, takes + 1):
                if takes == 1:
                    filename = f"{name}.wav"
                else:
                    filename = f"{name}_take{take_num:02d}.wav"
                filepath = output_base / category / filename

                if filepath.exists() and not args.regenerate_all:
                    continue

                to_generate.append((category, name, text, takes, take_num, filepath))
                total += 1

    if total == 0:
        print("All clips already exist. Use --regenerate-all to regenerate.")
        return

    print(f"\nGenerating {total} audio clips with voice {voice_id}")
    print(f"Output: {output_base}\n")

    if args.dry_run:
        for category, name, text, takes, take_num, filepath in to_generate:
            take_label = f" (take {take_num}/{takes})" if takes > 1 else ""
            print(f"  [{category}] {filepath.name}{take_label}: \"{text[:60]}...\"" if len(text) > 60 else f"  [{category}] {filepath.name}{take_label}: \"{text}\"")
        print(f"\n{total} clips would be generated (dry run)")
        return

    generated = 0
    errors = 0
    for category, name, text, takes, take_num, filepath in to_generate:
        take_label = f" (take {take_num}/{takes})" if takes > 1 else ""
        print(f"  [{generated + 1}/{total}] {category}/{filepath.name}{take_label}...", end=" ", flush=True)
        try:
            generate_clip(client, voice_id, text, filepath, model_id=args.model)
            generated += 1
            print("OK")
            # Small delay to avoid rate limiting
            time.sleep(0.5)
        except Exception as e:
            errors += 1
            print(f"ERROR: {e}")

    print(f"\nDone! Generated {generated} clips, {errors} errors.")


if __name__ == "__main__":
    main()
