"""
Authentication module
"""

import os
import json
from typing import Optional


def authenticate() -> Optional[dict]:
    """Simple authentication placeholder"""
    # For now, we'll use yt-dlp with cookies.txt if available
    if os.path.exists("cookies.txt"):
        return {"cookies": "cookies.txt"}
    return None


def save_credentials(credentials: dict) -> None:
    """Save credentials to file"""
    try:
        with open("credentials.json", "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=2)
    except Exception as e:
        print(f"⚠ Could not save credentials: {e}")


def load_credentials() -> Optional[dict]:
    """Load credentials from file"""
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None