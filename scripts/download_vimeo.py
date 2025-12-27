#!/usr/bin/env python3
"""
Download audio from Vimeo videos using HLS stream.
Works with private/unlisted videos accessible via shared links.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import ssl


def get_cookies_from_browser(browser_profile: str = "chrome:Profile 27") -> str:
    """Export cookies from browser using yt-dlp."""
    cookies_file = os.path.join(tempfile.gettempdir(), "vimeo_cookies.txt")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", browser_profile,
        "--cookies", cookies_file,
        "--skip-download",
        "https://www.youtube.com"  # Dummy URL to trigger cookie export
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return cookies_file


def fetch_url(url: str, cookies_file: str = None, referer: str = None) -> bytes:
    """Fetch URL with optional cookies and referer."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    if referer:
        headers["Referer"] = referer

    req = urllib.request.Request(url, headers=headers)

    # Add cookies if provided
    if cookies_file and os.path.exists(cookies_file):
        # Read cookies file and add to request
        # This is a simplified version - for full cookie support, use requests library
        pass

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as f:
        return f.read()


def extract_video_id_and_hash(url: str) -> tuple[str, str]:
    """Extract video ID and hash from Vimeo URL."""
    # Pattern: https://vimeo.com/1092622704/a6116d48f4
    match = re.search(r'vimeo\.com/(\d+)(?:/([a-f0-9]+))?', url)
    if match:
        video_id = match.group(1)
        hash_code = match.group(2) or ""
        return video_id, hash_code
    raise ValueError(f"Invalid Vimeo URL: {url}")


def get_player_config(video_id: str, hash_code: str, cookies_file: str = None) -> dict:
    """Get Vimeo player config containing HLS URLs."""
    # First, get the player page to find config URL
    player_url = f"https://player.vimeo.com/video/{video_id}"
    if hash_code:
        player_url += f"?h={hash_code}"

    print(f"Fetching player page: {player_url}", file=sys.stderr)

    # Use curl with cookies for better compatibility
    cmd = ["curl", "-s", player_url]
    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(["-b", cookies_file])
    cmd.extend(["-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    player_html = result.stdout

    # Find config URL in the page
    config_match = re.search(r'https://player\.vimeo\.com/video/\d+/config[^"]+', player_html)
    if not config_match:
        raise ValueError("Could not find config URL in player page")

    config_url = config_match.group(0).replace("\\u0026", "&")
    print(f"Found config URL", file=sys.stderr)

    # Fetch the config
    cmd = ["curl", "-s", config_url]
    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(["-b", cookies_file])
    cmd.extend(["-H", "User-Agent: Mozilla/5.0"])
    cmd.extend(["-H", "Referer: https://vimeo.com/"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)


def get_hls_url(config: dict) -> str:
    """Extract HLS URL from config."""
    files = config.get("files", {})
    hls = files.get("hls", {})
    cdns = hls.get("cdns", {})

    # Prefer fastly_skyfire as it tends to work better
    if "fastly_skyfire" in cdns:
        return cdns["fastly_skyfire"]["url"]

    # Fallback to first available CDN
    for cdn_name, cdn_info in cdns.items():
        if "url" in cdn_info:
            return cdn_info["url"]

    raise ValueError("No HLS URL found in config")


def get_video_title(config: dict) -> str:
    """Extract video title from config."""
    video = config.get("video", {})
    title = video.get("title", "untitled")
    # Sanitize for filename
    title = re.sub(r'[<>:"/\\|?*]', '_', title)
    title = re.sub(r'\s+', '_', title)
    return title[:100]


def download_audio_from_hls(hls_url: str, output_path: str) -> str:
    """Download audio from HLS stream using ffmpeg."""
    print(f"Downloading audio from HLS stream...", file=sys.stderr)

    cmd = [
        "ffmpeg", "-y",
        "-i", hls_url,
        "-vn",  # No video
        "-acodec", "libmp3lame",
        "-b:a", "128k",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr[:500]}", file=sys.stderr)
        raise RuntimeError("FFmpeg failed to download audio")

    return output_path


def download_vimeo_audio(url: str, output_path: str = None, browser_profile: str = None) -> tuple[str, str]:
    """
    Download audio from Vimeo URL.

    Args:
        url: Vimeo video URL
        output_path: Output file path (optional)
        browser_profile: Browser profile for cookies (e.g., "chrome:Profile 27")

    Returns:
        Tuple of (output_path, video_title)
    """
    # Get cookies if browser profile specified
    cookies_file = None
    if browser_profile:
        print(f"Exporting cookies from {browser_profile}...", file=sys.stderr)
        cookies_file = get_cookies_from_browser(browser_profile)

    # Extract video ID and hash
    video_id, hash_code = extract_video_id_and_hash(url)
    print(f"Video ID: {video_id}, Hash: {hash_code or 'none'}", file=sys.stderr)

    # Get player config
    config = get_player_config(video_id, hash_code, cookies_file)

    # Get title
    title = get_video_title(config)
    print(f"Title: {title}", file=sys.stderr)

    # Get HLS URL
    hls_url = get_hls_url(config)
    print(f"Found HLS stream", file=sys.stderr)

    # Set output path
    if output_path is None:
        output_path = os.path.join(tempfile.gettempdir(), f"{title}.mp3")

    # Download audio
    download_audio_from_hls(hls_url, output_path)

    print(f"Downloaded: {output_path}", file=sys.stderr)
    return output_path, title


def main():
    parser = argparse.ArgumentParser(description="Download audio from Vimeo videos")
    parser.add_argument("url", help="Vimeo video URL")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--browser", default="chrome:Profile 27",
                        help="Browser profile for cookies (e.g., 'chrome:Profile 27')")

    args = parser.parse_args()

    try:
        output, title = download_vimeo_audio(args.url, args.output, args.browser)
        # Output JSON for easy parsing
        print(json.dumps({"path": output, "title": title}))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
