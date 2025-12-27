#!/usr/bin/env python3
"""
Transcribe audio using Groq or OpenAI Whisper API.
Supports automatic splitting for files exceeding 25MB limit.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_FILE_SIZE = 24 * 1024 * 1024  # 24MB (safety margin below 25MB limit)
CHUNK_DURATION = 600  # 10 minutes per chunk


def get_file_size(file_path: str) -> int:
    return os.path.getsize(file_path)


def get_audio_duration(file_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def split_audio(file_path: str, output_dir: str, chunk_duration: int = CHUNK_DURATION) -> list[str]:
    """Split audio into chunks of specified duration."""
    duration = get_audio_duration(file_path)
    chunks = []

    for i, start in enumerate(range(0, int(duration), chunk_duration)):
        output_path = os.path.join(output_dir, f"chunk_{i:04d}.mp3")
        cmd = [
            "ffmpeg", "-y", "-i", file_path,
            "-ss", str(start), "-t", str(chunk_duration),
            "-acodec", "libmp3lame", "-b:a", "64k",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        chunks.append(output_path)
        print(f"Created chunk {i + 1}/{(int(duration) // chunk_duration) + 1}", file=sys.stderr)

    return chunks


def transcribe_with_groq(file_path: str, api_key: str, timestamps: bool = False, language: str = "ja") -> dict:
    """Transcribe using Groq Whisper API."""
    import requests

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "audio/mpeg")}
        data = {
            "model": "whisper-large-v3-turbo",
            "language": language,
            "response_format": "verbose_json" if timestamps else "json"
        }

        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.json()


def transcribe_with_openai(file_path: str, api_key: str, timestamps: bool = False, language: str = "ja") -> dict:
    """Transcribe using OpenAI Whisper API."""
    import requests

    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "audio/mpeg")}
        data = {
            "model": "whisper-1",
            "language": language,
            "response_format": "verbose_json" if timestamps else "json"
        }

        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.json()


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def format_output(result: dict, timestamps: bool, time_offset: float = 0) -> str:
    """Format transcription result."""
    if timestamps and "segments" in result:
        lines = []
        for segment in result["segments"]:
            start = segment.get("start", 0) + time_offset
            text = segment.get("text", "").strip()
            if text:
                lines.append(f"{format_timestamp(start)} {text}")
        return "\n".join(lines)
    return result.get("text", "")


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio using Whisper API")
    parser.add_argument("audio_file", help="Path to audio file")
    parser.add_argument("--api-key", required=True, help="API key (Groq or OpenAI)")
    parser.add_argument("--provider", choices=["groq", "openai"], default="groq", help="API provider")
    parser.add_argument("--timestamps", action="store_true", help="Include timestamps")
    parser.add_argument("--language", default="ja", help="Language code (default: ja)")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")

    args = parser.parse_args()

    if not os.path.exists(args.audio_file):
        print(f"Error: File not found: {args.audio_file}", file=sys.stderr)
        sys.exit(1)

    transcribe_fn = transcribe_with_groq if args.provider == "groq" else transcribe_with_openai

    file_size = get_file_size(args.audio_file)

    if file_size > MAX_FILE_SIZE:
        print(f"File size ({file_size / 1024 / 1024:.1f}MB) exceeds limit. Splitting...", file=sys.stderr)

        with tempfile.TemporaryDirectory() as temp_dir:
            chunks = split_audio(args.audio_file, temp_dir)

            all_text = []
            time_offset = 0

            for i, chunk in enumerate(chunks):
                print(f"Transcribing chunk {i + 1}/{len(chunks)}...", file=sys.stderr)
                result = transcribe_fn(chunk, args.api_key, args.timestamps, args.language)

                chunk_text = format_output(result, args.timestamps, time_offset)
                all_text.append(chunk_text)

                time_offset += CHUNK_DURATION

            output = "\n".join(all_text)
    else:
        print("Transcribing...", file=sys.stderr)
        result = transcribe_fn(args.audio_file, args.api_key, args.timestamps, args.language)
        output = format_output(result, args.timestamps)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
