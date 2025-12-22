"""
Utility functions
"""

import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

COOKIES_FILE = "cookies.txt"


def ensure_dependencies() -> None:
    """Ensure required dependencies are installed"""
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp not found in PATH. Please install yt-dlp.")


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


def sanitize_folder_name(name: str) -> str:
    """Sanitize folder name for filesystem"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip().rstrip('.')
    return name or "playlist"


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip().rstrip('.')
    return name


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return os.path.splitext(filename)[1].lower()


def is_audio_file(filename: str) -> bool:
    """Check if file is an audio file"""
    audio_extensions = {'.mp3', '.m4a', '.webm', '.opus', '.flac', '.wav', '.ogg'}
    return get_file_extension(filename) in audio_extensions


def is_image_file(filename: str) -> bool:
    """Check if file is an image file"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
    return get_file_extension(filename) in image_extensions


def get_video_id_from_filename(filename: str) -> str:
    """Extract YouTube video ID from filename"""
    match = re.search(r'\[([A-Za-z0-9_-]{11})\]', filename)
    return match.group(1) if match else ""