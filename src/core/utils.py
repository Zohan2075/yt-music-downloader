"""
Utility functions
"""

import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Optional, List

from src.ui.colors import Colors

# Shared extension catalogs
AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.webm', '.opus', '.flac', '.wav', '.ogg'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

COOKIES_FILE = "cookies.txt"
JS_RUNTIMES = ["node", "deno", "quickjs", "bun"]
JS_RUNTIME = ""


def ensure_dependencies() -> None:
    """Ensure required dependencies are installed"""
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp module not found. Please install it with: pip install yt-dlp")

    global JS_RUNTIME
    runtime = JS_RUNTIME or _detect_js_runtime()
    if runtime:
        JS_RUNTIME = runtime
    else:
        print(f"{Colors.YELLOW}⚠ yt-dlp will miss formats without a JS runtime (node/deno/quickjs/bun).{Colors.RESET}")
        print(f"{Colors.YELLOW}  Install one and ensure it's on PATH for best results.{Colors.RESET}")

    if not Path(COOKIES_FILE).exists():
        print(f"{Colors.YELLOW}⚠ Cookies file '{COOKIES_FILE}' not found. Age-restricted videos may fail.{Colors.RESET}")
        print(f"{Colors.YELLOW}  Export cookies and place them next to this script when needed.{Colors.RESET}")


def ytdlp_common_flags(debug: bool = False) -> List[str]:
    """Common yt-dlp flags used across flows."""
    if debug:
        return ["-v"]
    return ["--quiet", "--no-warnings", "--progress", "--newline"]


def cookies_path_if_exists() -> Optional[Path]:
    """Return cookies file Path if it exists, else None."""
    p = Path(COOKIES_FILE)
    return p if p.exists() else None


def select_download_folder(current: str) -> str:
    """Open folder selector dialog"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    folder = filedialog.askdirectory(
        title="Select Base Folder for All Playlists",
        initialdir=current
    )
    root.destroy()
    return folder or current


def sanitize_path_component(name: str, default: str = "") -> str:
    """Sanitize a filesystem component, keeping ASCII-safe replacements."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
    cleaned = cleaned.strip().rstrip('.')
    return cleaned or default


def sanitize_folder_name(name: str) -> str:
    """Sanitize folder name for filesystem"""
    return sanitize_path_component(name, default="playlist")


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem"""
    return sanitize_path_component(name)


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return os.path.splitext(filename)[1].lower()


def is_audio_file(filename: str) -> bool:
    """Check if file is an audio file"""
    return get_file_extension(filename) in AUDIO_EXTENSIONS


def is_image_file(filename: str) -> bool:
    """Check if file is an image file"""
    return get_file_extension(filename) in IMAGE_EXTENSIONS


def get_video_id_from_filename(filename: str) -> str:
    """Extract YouTube video ID from filename"""
    patterns = [
        r"\[([A-Za-z0-9_-]{11})\]",
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"watch\?v=([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    return ""


def detected_js_runtime() -> str:
    """Return the JS runtime detected on PATH (empty string if none)."""
    return JS_RUNTIME


def _detect_js_runtime() -> str:
    for runtime in JS_RUNTIMES:
        if shutil.which(runtime):
            return runtime
    return ""


def extract_playlist_id(url: str) -> str:
    """Extract the playlist ID from a YouTube/Music URL."""
    if not url:
        return ""

    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "list" in params and params["list"]:
            return params["list"][0]

        match = re.search(r"list=([A-Za-z0-9_-]+)", url)
        if match:
            return match.group(1)
    except Exception:
        pass

    return ""


def normalize_url(url: str) -> str:
    """Best-effort URL normalization for user input.

    If the user pastes a YouTube domain without a scheme, prepend https://.
    Leaves other inputs unchanged.
    """
    if not url:
        return ""

    value = url.strip()
    if not value:
        return ""

    try:
        parsed = urlparse(value)
        if parsed.scheme:
            return value
    except Exception:
        return value

    lowered = value.lower()
    if lowered.startswith("www.") or "youtube." in lowered or "youtu.be" in lowered:
        return f"https://{value.lstrip('/')}"

    return value


def is_probably_url(url: str) -> bool:
    """Return True only for obvious http(s) URLs.

    This intentionally does not try to validate every yt-dlp supported input.
    """
    value = normalize_url(url)
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def looks_like_playlist_url(url: str) -> bool:
    """Heuristic to detect playlist links so single-download mode can reject them."""
    normalized = normalize_url(url)
    if not normalized:
        return False
    try:
        parsed = urlparse(normalized)
        params = parse_qs(parsed.query)
        if params.get("list"):
            return True
        if "playlist" in (parsed.path or ""):
            return True
        return False
    except Exception:
        return False