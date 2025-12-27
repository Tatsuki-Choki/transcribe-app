#!/usr/bin/env python3
"""
Download audio from video URLs using yt-dlp.
Supports YouTube, Vimeo, and many other platforms.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def get_video_title(url: str, cookies_file: str = None) -> str:
    """Get video title using yt-dlp."""
    cmd = ["yt-dlp", "--get-title", "--no-playlist", url]
    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(["--cookies", cookies_file])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        # Sanitize title for filename
        title = result.stdout.strip()
        # Remove or replace invalid filename characters
        title = re.sub(r'[<>:"/\\|?*]', '_', title)
        title = re.sub(r'\s+', '_', title)
        return title[:100]  # Limit length
    return "untitled"


def download_audio(url: str, output_path: str = None, cookies_file: str = None) -> tuple[str, str]:
    """
    Download audio from URL using yt-dlp.

    Args:
        url: Video URL
        output_path: Output file path (optional, auto-generated if not provided)
        cookies_file: Path to cookies file for authenticated downloads

    Returns:
        Tuple of (path to downloaded audio file, video title)
    """
    # Get video title first
    title = get_video_title(url, cookies_file)

    if output_path is None:
        output_path = os.path.join(tempfile.gettempdir(), "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "0",  # Best quality
        "-o", output_path,
        "--no-playlist",  # Single video only
        "--restrict-filenames",  # Safe filenames
    ]

    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(["--cookies", cookies_file])

    cmd.append(url)

    print(f"Downloading audio from: {url}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Find the actual output file
    if "%(title)s" in output_path:
        # yt-dlp prints the destination path
        for line in result.stdout.split("\n"):
            if "[ExtractAudio] Destination:" in line:
                return line.split("Destination:")[-1].strip(), title
            if "has already been downloaded" in line:
                # Extract filename from the message
                parts = line.split("[download]")
                if len(parts) > 1:
                    return parts[1].strip().split(" ")[0], title

    # Fallback: look for mp3 file in output directory
    output_dir = os.path.dirname(output_path) or tempfile.gettempdir()
    mp3_files = list(Path(output_dir).glob("*.mp3"))
    if mp3_files:
        return str(sorted(mp3_files, key=os.path.getmtime)[-1]), title

    return output_path.replace("%(title)s", "audio").replace("%(ext)s", "mp3"), title


def download_from_direct_url(url: str, output_path: str = None, title: str = None) -> tuple[str, str]:
    """
    Download audio from direct video/audio URL using ffmpeg.
    Useful for embedded videos or direct media links.

    Returns:
        Tuple of (path to downloaded audio file, title)
    """
    if output_path is None:
        output_path = os.path.join(tempfile.gettempdir(), "downloaded_audio.mp3")

    if title is None:
        title = "untitled"

    cmd = [
        "ffmpeg", "-y",
        "-i", url,
        "-vn",  # No video
        "-acodec", "libmp3lame",
        "-b:a", "128k",
        output_path
    ]

    print(f"Downloading audio from direct URL: {url}", file=sys.stderr)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return output_path, title


def main():
    parser = argparse.ArgumentParser(description="Download audio from video URLs")
    parser.add_argument("url", help="Video URL")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--cookies", help="Path to cookies file for authenticated downloads")
    parser.add_argument("--direct", action="store_true", help="Treat URL as direct media link")
    parser.add_argument("--title", help="Video title (for direct downloads)")

    args = parser.parse_args()

    if args.direct:
        output, title = download_from_direct_url(args.url, args.output, args.title)
    else:
        output, title = download_audio(args.url, args.output, args.cookies)

    print(f"Downloaded: {output}", file=sys.stderr)
    print(f"Title: {title}", file=sys.stderr)
    # Output JSON for easy parsing
    print(json.dumps({"path": output, "title": title}))


if __name__ == "__main__":
    main()
