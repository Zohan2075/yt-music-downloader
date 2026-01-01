"""
Settings management
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
import tkinter as tk
from tkinter import filedialog

from utils import select_download_folder, sanitize_folder_name, extract_playlist_id
from colors import Colors

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "download_path": str(Path.home() / "Music" / "YouTube Playlists"),
    "playlists": [],
    "max_workers": 4,
    "new_playlists": [],  # NEW: Track newly added playlists
}


def load_settings() -> Dict[str, Any]:
    """Load settings from file"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                # Ensure new_playlists key exists for backward compatibility
                if "new_playlists" not in settings:
                    settings["new_playlists"] = []
                return settings
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: Dict[str, Any]) -> None:
    """Save settings to file"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"{Colors.YELLOW}⚠ Could not save settings: {e}{Colors.RESET}")


def setup_preferences(settings: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
    """Interactive setup for preferences.
    Returns: (were_new_playlists_added, new_playlists_list)
    """
    print(f"\n{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{'PLAYLIST SYNC SETUP':^60}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n")
    
    current = settings.get("download_path") or DEFAULT_SETTINGS["download_path"]
    print(f"{Colors.YELLOW}Current base folder:{Colors.RESET}")
    print(f" {Colors.GRAY}{current}{Colors.RESET}\n")
    
    change = input(f"{Colors.BLUE}Change folder? (y/N): {Colors.RESET}").strip().lower()
    if change in ("y", "yes"):
        print(f"{Colors.YELLOW}Opening folder selector...{Colors.RESET}")
        new_path = select_download_folder(current)
        settings["download_path"] = new_path
        print(f"{Colors.GREEN}✓ New folder: {new_path}{Colors.RESET}\n")
        current = new_path
    base_folder = Path(settings.get("download_path", DEFAULT_SETTINGS["download_path"]))
    
    print(f"{Colors.CYAN}{'-'*60}{Colors.RESET}")
    print(f"{Colors.BOLD}PLAYLIST MANAGEMENT{Colors.RESET}\n")
    
    existing = settings.get("playlists", [])
    new_playlists = []  # Track newly added playlists

    existing_name_keys = {
        pl.get("name", "").strip().lower()
        for pl in existing
        if pl.get("name")
    }

    existing_playlist_ids = set()
    for pl in existing:
        stored_id = pl.get("playlist_id") or extract_playlist_id(pl.get("url", ""))
        if stored_id:
            existing_playlist_ids.add(stored_id)

    existing_folder_names = set()
    for pl in existing:
        name = pl.get("name", "")
        if name:
            existing_folder_names.add(sanitize_folder_name(name).lower())

    try:
        if base_folder.exists():
            for child in base_folder.iterdir():
                if child.is_dir():
                    existing_folder_names.add(child.name.lower())
    except Exception:
        pass
    
    if existing:
        print(f"{Colors.YELLOW}Current playlists:{Colors.RESET}")
        for i, pl in enumerate(existing, 1):
            print(f" {i:2}. {pl.get('name','(unnamed)')}")
        print()
    
    while True:
        action = input(f"{Colors.BLUE}(A)dd, (R)emove, or (F)inish? {Colors.RESET}").strip().lower()
        if action in ("f", "finish", ""):
            break
        elif action in ("a", "add"):
            print(f"\n{Colors.GREEN}Adding new playlist:{Colors.RESET}")
            url = input(f" {Colors.BLUE}Playlist URL: {Colors.RESET}").strip()
            if not url:
                print(f"{Colors.RED}URL required. Skipping.{Colors.RESET}\n")
                continue
            
            default_name = f"Playlist_{len(existing) + len(new_playlists) + 1}"
            name = input(f" {Colors.BLUE}Folder name [{default_name}]: {Colors.RESET}").strip()
            if not name:
                name = default_name

            playlist_id = extract_playlist_id(url)
            sanitized_name = sanitize_folder_name(name)
            name_key = name.strip().lower()
            folder_key = sanitized_name.lower()

            if name_key and name_key in existing_name_keys:
                print(f"{Colors.RED}Playlist name '{name}' already exists. Choose a different name.{Colors.RESET}\n")
                continue

            if folder_key in existing_folder_names:
                print(
                    f"{Colors.RED}Folder '{sanitized_name}' already exists in {base_folder}. Choose another name or remove the folder first.{Colors.RESET}\n"
                )
                continue

            if playlist_id and playlist_id in existing_playlist_ids:
                print(f"{Colors.RED}Playlist ID '{playlist_id}' is already configured locally. Use a different playlist.{Colors.RESET}\n")
                continue
            
            new_playlist = {
                "name": name.strip(),
                "url": url,
                "is_new": True  # Mark as new
            }
            if playlist_id:
                new_playlist["playlist_id"] = playlist_id
            
            # Add to both lists
            settings.setdefault("playlists", []).append(new_playlist)
            new_playlists.append(new_playlist)
            existing.append(new_playlist)
            if name_key:
                existing_name_keys.add(name_key)
            existing_folder_names.add(folder_key)
            if playlist_id:
                existing_playlist_ids.add(playlist_id)
            
            print(f"{Colors.GREEN}✓ Added '{name}'{Colors.RESET}\n")
        
        elif action in ("r", "remove") and existing:
            try:
                idx = int(input(f"{Colors.BLUE}Enter number to remove (1-{len(existing)}): {Colors.RESET}"))
                if 1 <= idx <= len(existing):
                    removed = existing.pop(idx-1)
                    removed_name = removed.get('name','(unnamed)')
                    print(f"{Colors.YELLOW}Removed '{removed_name}'{Colors.RESET}\n")

                    # Offer to delete the playlist folder; default is to move it to a quarantine folder
                    base = Path(settings.get("download_path", Path.home() / "Music" / "YouTube Playlists"))
                    playlist_folder = base / sanitize_folder_name(removed_name)

                    if playlist_folder.exists():
                        choice = input(f"{Colors.BLUE}Also remove the folder for '{removed_name}'? (Q)uarantine/(D)elete/(N)o [Q]: {Colors.RESET}").strip().lower()

                        # Permanently delete
                        if choice in ("d", "delete"):
                            confirm = input(f"{Colors.RED}PERMANENT delete '{playlist_folder}' (this cannot be undone). Confirm (y/N): {Colors.RESET}").strip().lower()
                            if confirm in ("y", "yes"):
                                try:
                                    import shutil
                                    shutil.rmtree(playlist_folder)
                                    print(f"{Colors.RED}✖ Permanently deleted: {playlist_folder}{Colors.RESET}\n")
                                except Exception as e:
                                    print(f"{Colors.YELLOW}⚠ Failed to delete: {e}{Colors.RESET}\n")
                            else:
                                print(f"{Colors.YELLOW}Skipping permanent delete.{Colors.RESET}\n")

                        # Move to quarantine (default)
                        elif choice in ("q", "", "quarantine"):
                            try:
                                import shutil, time
                                quarantine_dir = base / ".quarantined_playlists"
                                quarantine_dir.mkdir(parents=True, exist_ok=True)
                                timestamp = time.strftime('%Y%m%d-%H%M%S')
                                dest = quarantine_dir / f"{sanitize_folder_name(removed_name)}_{timestamp}"
                                shutil.move(str(playlist_folder), str(dest))
                                print(f"{Colors.RED}🗄 Moved to quarantine: {dest}{Colors.RESET}\n")
                            except Exception as e:
                                print(f"{Colors.YELLOW}⚠ Failed to move to quarantine: {e}{Colors.RESET}\n")

                        else:
                            print(f"{Colors.YELLOW}Left folder in place: {playlist_folder}{Colors.RESET}\n")
                    else:
                        print(f"{Colors.GRAY}Folder not found: {playlist_folder}{Colors.RESET}\n")

                else:
                    print(f"{Colors.RED}Invalid number.{Colors.RESET}\n")
            except Exception:
                print(f"{Colors.RED}Invalid input.{Colors.RESET}\n")
    
    # Store new playlists in settings
    if new_playlists:
        settings["new_playlists"] = new_playlists
    
    save_settings(settings)
    print(f"{Colors.GREEN}✓ Settings saved!{Colors.RESET}")
    
    # Return whether new playlists were added
    return len(new_playlists) > 0, new_playlists