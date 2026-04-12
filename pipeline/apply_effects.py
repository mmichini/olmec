#!/usr/bin/env python3
"""Apply audio effects (reverb, etc.) to generate 'wet' versions of audio clips.

Reads from data/audio/<voice>/  (dry originals)
Writes to  data/audio/<voice>-fx/ (processed copies)

Usage:
    # Process all clips for the active voice
    python pipeline/apply_effects.py

    # Process a specific voice
    python pipeline/apply_effects.py --voice-name olmec-v1

    # Adjust reverb settings
    python pipeline/apply_effects.py --room-size 0.8 --wet-level 0.35

    # Only process one category
    python pipeline/apply_effects.py --category questions
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, Reverb, HighpassFilter, Gain


def build_olmec_board(
    room_size: float = 0.7,
    damping: float = 0.5,
    wet_level: float = 0.3,
    dry_level: float = 0.8,
) -> Pedalboard:
    """Build an effects chain for the Olmec voice — cavernous temple reverb."""
    return Pedalboard([
        # Slight high-pass to remove low rumble before reverb
        HighpassFilter(cutoff_frequency_hz=80),
        # Cavernous reverb
        Reverb(
            room_size=room_size,
            damping=damping,
            wet_level=wet_level,
            dry_level=dry_level,
            width=1.0,
        ),
        # Slight gain boost to compensate for wet mix
        Gain(gain_db=2.0),
    ])


def process_file(board: Pedalboard, input_path: Path, output_path: Path) -> None:
    """Apply effects to a single audio file."""
    data, sr = sf.read(str(input_path), dtype="float32")

    # Ensure mono -> shape (N,) for pedalboard
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Pedalboard expects shape (channels, samples)
    data_2d = data.reshape(1, -1)
    processed = board(data_2d, sr)

    # Back to 1D
    processed = processed.squeeze()

    # Normalize to prevent clipping
    peak = np.max(np.abs(processed))
    if peak > 0.95:
        processed = processed * (0.95 / peak)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), processed, sr, subtype="PCM_16")


def main():
    parser = argparse.ArgumentParser(description="Apply audio effects to Olmec clips")
    parser.add_argument("--voice-name", default=None, help="Source voice directory (default: from OLMEC_VOICE env)")
    parser.add_argument("--fx-suffix", default="-fx", help="Suffix for output directory (default: -fx)")
    parser.add_argument("--category", help="Only process this category")
    parser.add_argument("--room-size", type=float, default=0.7, help="Reverb room size 0.0-1.0 (default: 0.7)")
    parser.add_argument("--damping", type=float, default=0.5, help="Reverb damping 0.0-1.0 (default: 0.5)")
    parser.add_argument("--wet-level", type=float, default=0.3, help="Reverb wet level 0.0-1.0 (default: 0.3)")
    parser.add_argument("--dry-level", type=float, default=0.8, help="Reverb dry level 0.0-1.0 (default: 0.8)")
    parser.add_argument("--regenerate-all", action="store_true", help="Overwrite existing processed files")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    voice_name = args.voice_name or os.environ.get("OLMEC_VOICE", "olmec-v1")
    audio_base = Path(__file__).parent.parent / "data" / "audio"
    input_dir = audio_base / voice_name
    output_dir = audio_base / f"{voice_name}{args.fx_suffix}"

    if not input_dir.exists():
        print(f"Error: Source directory not found: {input_dir}")
        sys.exit(1)

    board = build_olmec_board(
        room_size=args.room_size,
        damping=args.damping,
        wet_level=args.wet_level,
        dry_level=args.dry_level,
    )

    print(f"Source:  {input_dir}")
    print(f"Output:  {output_dir}")
    print(f"Effects: room={args.room_size} damping={args.damping} wet={args.wet_level} dry={args.dry_level}")
    print()

    # Find all wav files
    wav_files = sorted(input_dir.rglob("*.wav"))
    if args.category:
        wav_files = [f for f in wav_files if f.parent.name == args.category]

    processed = 0
    skipped = 0
    for wav_path in wav_files:
        rel = wav_path.relative_to(input_dir)
        out_path = output_dir / rel

        if out_path.exists() and not args.regenerate_all:
            skipped += 1
            continue

        print(f"  {rel}...", end=" ", flush=True)
        try:
            process_file(board, wav_path, out_path)
            processed += 1
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone! Processed {processed}, skipped {skipped} (already exist).")
    if processed > 0:
        print(f"\nTo use the processed voice, set OLMEC_VOICE={voice_name}{args.fx_suffix} in .env")


if __name__ == "__main__":
    main()
