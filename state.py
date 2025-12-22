"""
Sync state management for tracking downloaded videos
"""

import json
import os
from typing import Dict, Any, Set, List

STATE_FILE = "sync_state.json"


def load_state() -> Dict[str, Any]:
    """Load sync state from file"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: Dict[str, Any]) -> None:
    """Save sync state to file"""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠ Could not save state: {e}")


def get_downloaded_videos(playlist_id: str) -> Set[str]:
    """Get set of downloaded video IDs for a playlist"""
    state = load_state()
    playlist_state = state.get(playlist_id, {})
    return set(playlist_state.get("downloaded_videos", []))


def mark_video_downloaded(playlist_id: str, video_id: str) -> None:
    """Mark a video as downloaded for a playlist"""
    state = load_state()
    
    if playlist_id not in state:
        state[playlist_id] = {"downloaded_videos": []}
    
    if video_id not in state[playlist_id]["downloaded_videos"]:
        state[playlist_id]["downloaded_videos"].append(video_id)
        save_state(state)


def get_all_downloaded_videos() -> Dict[str, List[str]]:
    """Get all downloaded videos across all playlists"""
    state = load_state()
    result = {}
    
    for playlist_id, playlist_state in state.items():
        result[playlist_id] = playlist_state.get("downloaded_videos", [])
    
    return result