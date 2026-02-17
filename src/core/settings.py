"""
Settings management
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import tkinter as tk
from tkinter import filedialog

from src.core.utils import (
    select_download_folder,
    sanitize_folder_name,
    extract_playlist_id,
    normalize_url,
    is_probably_url,
)
from src.ui.colors import Colors

SETTINGS_FILE = Path(__file__).resolve().parents[2] / "settings.json"

DEFAULT_SETTINGS = {
    "download_path": str(Path.home() / "Music" / "YouTube Playlists"),
    "playlists": [],
    "max_workers": 4,
    "new_playlists": [],  # NEW: Track newly added playlists
}


def load_settings() -> Dict[str, Any]:
    """Load settings from file"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                # Ensure new_playlists key exists for backward compatibility
                if "new_playlists" not in settings:
                    settings["new_playlists"] = []

                changed = False

                def _dedupe_and_normalize_playlist_list(value: Any) -> Tuple[List[Dict[str, Any]], bool]:
                    if not isinstance(value, list):
                        return [], True

                    cleaned: List[Dict[str, Any]] = []
                    seen_keys: set[str] = set()
                    local_changed = False

                    for item in value:
                        if not isinstance(item, dict):
                            local_changed = True
                            continue

                        url = str(item.get("url", "") or "").strip()
                        url_norm = normalize_url(url)
                        if url_norm != url:
                            item = {**item, "url": url_norm}
                            local_changed = True

                        playlist_id = item.get("playlist_id") or extract_playlist_id(url_norm)
                        if playlist_id and item.get("playlist_id") != playlist_id:
                            item = {**item, "playlist_id": playlist_id}
                            local_changed = True

                        key = (playlist_id or url_norm).strip().lower()
                        if not key:
                            local_changed = True
                            continue
                        if key in seen_keys:
                            local_changed = True
                            continue

                        seen_keys.add(key)
                        cleaned.append(item)

                    return cleaned, local_changed

                playlists, playlists_changed = _dedupe_and_normalize_playlist_list(settings.get("playlists", []))
                new_playlists, new_playlists_changed = _dedupe_and_normalize_playlist_list(settings.get("new_playlists", []))

                # Ensure new playlists are actually syncable.
                # Historically, newly-added entries were tracked in `new_playlists` but `main.py` only syncs `playlists`.
                # Merge any missing entries into `playlists` while keeping `new_playlists` for bookkeeping.
                merged = False
                playlist_keys: set[str] = set()
                for item in playlists:
                    url_norm = normalize_url(str(item.get("url", "") or "")).strip()
                    pid = str(item.get("playlist_id") or extract_playlist_id(url_norm) or "").strip()
                    key = (pid or url_norm).strip().lower()
                    if key:
                        playlist_keys.add(key)

                for item in new_playlists:
                    url_norm = normalize_url(str(item.get("url", "") or "")).strip()
                    pid = str(item.get("playlist_id") or extract_playlist_id(url_norm) or "").strip()
                    key = (pid or url_norm).strip().lower()
                    if key and key not in playlist_keys:
                        playlists.append(item)
                        playlist_keys.add(key)
                        merged = True

                if playlists_changed:
                    settings["playlists"] = playlists
                    changed = True
                elif merged:
                    settings["playlists"] = playlists
                    changed = True
                if new_playlists_changed:
                    settings["new_playlists"] = new_playlists
                    changed = True

                invalid = [pl for pl in settings.get("playlists", []) if not is_probably_url(pl.get("url", ""))]
                if invalid:
                    print(f"{Colors.YELLOW}⚠ Some configured playlists have invalid URLs and will fail:{Colors.RESET}")
                    for pl in invalid:
                        name = pl.get("name", "(unnamed)")
                        url = pl.get("url", "")
                        print(f"  - {name}: {Colors.GRAY}{url}{Colors.RESET}")

                if changed:
                    save_settings(settings)

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
    try:
        base_folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    def _fetch_playlist_title(url: str, timeout: int = 20) -> Optional[str]:
        """Best-effort fetch of the playlist title via yt-dlp.

        This keeps Option 2 self-contained and avoids importing downloader modules.
        """
        try:
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--skip-download",
                "--dump-single-json",
                url,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                return None

            data = json.loads(result.stdout or "{}")
            title = data.get("title") or data.get("playlist_title")
            if not title:
                return None
            name = str(title).strip()
            return name or None
        except Exception:
            return None

    def _pick_playlist_folder(base_dir: Path) -> Optional[Path]:
        """Pick (or create) a playlist folder. Returns None if user cancels."""
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.update_idletasks()
            folder = filedialog.askdirectory(
                title="Select Folder to Store This Playlist",
                initialdir=str(base_dir),
                mustexist=False,
            )
            root.destroy()
        except Exception:
            return None

        folder = (folder or "").strip()
        if not folder:
            return None
        return Path(folder)

    def _is_within_base(base_dir: Path, folder: Path) -> bool:
        try:
            folder.resolve().relative_to(base_dir.resolve())
            return True
        except Exception:
            return False

    def _registered_folder_keys(playlists: List[Dict[str, Any]]) -> set[str]:
        keys: set[str] = set()
        for pl in playlists:
            folder_hint = (pl.get("folder") or "").strip()
            if folder_hint:
                keys.add(folder_hint.strip().lower())
                continue
            name = (pl.get("name") or "").strip()
            if name:
                keys.add(sanitize_folder_name(name).lower())
        return keys

    def _scan_unregistered_folders(base_dir: Path, playlists: List[Dict[str, Any]]) -> List[Path]:
        registered = _registered_folder_keys(playlists)
        missing: List[Path] = []
        try:
            if not base_dir.exists():
                return []
            for child in base_dir.iterdir():
                if not child.is_dir():
                    continue
                if child.name.startswith("."):
                    continue
                key = child.name.lower()
                if key not in registered:
                    missing.append(child)
        except Exception:
            return []
        return sorted(missing, key=lambda p: p.name.lower())

    def _unique_name(desired: str, taken: set[str]) -> str:
        """Return a unique playlist name based on desired, avoiding taken (lowercased)."""
        base = (desired or "playlist").strip() or "playlist"
        candidate = base
        suffix = 2
        while candidate.strip().lower() in taken:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate
    
    print(f"{Colors.CYAN}{'-'*60}{Colors.RESET}")
    print(f"{Colors.BOLD}PLAYLIST MANAGEMENT{Colors.RESET}\n")
    
    existing = settings.get("playlists", [])
    settings.setdefault("new_playlists", [])
    session_new_playlists: List[Dict[str, Any]] = []  # newly added in this session

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

    existing_folder_keys = _registered_folder_keys(existing)
    
    if existing:
        print(f"{Colors.YELLOW}Current playlists:{Colors.RESET}")
        for i, pl in enumerate(existing, 1):
            print(f" {i:2}. {pl.get('name','(unnamed)')}")
        print()
    
    while True:
        action = input(
            f"{Colors.BLUE}(A)dd, (R)emove, (I)mport folders, or (F)inish? {Colors.RESET}"
        ).strip().lower()
        if action in ("f", "finish", ""):
            break
        elif action in ("a", "add"):
            print(f"\n{Colors.GREEN}Adding new playlist:{Colors.RESET}")
            url = input(f" {Colors.BLUE}Playlist URL: {Colors.RESET}").strip()
            if not url:
                print(f"{Colors.RED}URL required. Skipping.{Colors.RESET}\n")
                continue

            url = normalize_url(url)
            if not is_probably_url(url):
                print(f"{Colors.RED}That doesn't look like a valid URL: '{url}'. Skipping.{Colors.RESET}\n")
                continue

            # Safety: require a real playlist URL. A single-video link will scan as an empty playlist
            # and can trigger destructive cleanup logic in sync.
            playlist_id = extract_playlist_id(url)
            if not playlist_id:
                print(
                    f"{Colors.RED}That link is not a playlist (missing 'list='). Paste a YouTube playlist URL.{Colors.RESET}\n"
                )
                continue

            # Prevent duplicates by playlist ID before creating any folders.
            if playlist_id in existing_playlist_ids:
                print(
                    f"{Colors.RED}That playlist is already configured locally (same playlist ID).{Colors.RESET}\n"
                )
                continue

            # Fetch the real playlist name and use it as the folder name.
            playlist_title = _fetch_playlist_title(url)
            if not playlist_title:
                print(
                    f"{Colors.YELLOW}⚠ Could not fetch the playlist title via yt-dlp.{Colors.RESET}"
                )
                playlist_title = input(
                    f" {Colors.BLUE}Enter a name for this playlist (recommended to match YouTube): {Colors.RESET}"
                ).strip() or "playlist"
            else:
                print(f" {Colors.GRAY}Detected playlist title: {playlist_title}{Colors.RESET}")

            name = _unique_name(playlist_title, existing_name_keys)
            name_key = name.strip().lower()

            folder_base = sanitize_folder_name(playlist_title)
            folder_name = folder_base
            folder_path = base_folder / folder_name

            # If a folder already exists with the exact playlist title, reuse it if it's not registered.
            if folder_path.exists() and folder_path.is_dir() and folder_name.strip().lower() not in existing_folder_keys:
                print(f" {Colors.GRAY}Using existing folder: {folder_path}{Colors.RESET}")
            else:
                # Otherwise, choose a unique folder name.
                suffix = 2
                while True:
                    key = folder_name.strip().lower()
                    candidate = base_folder / folder_name

                    # Block if name is already registered to another playlist.
                    if key in existing_folder_keys:
                        pass
                    # Block if a non-folder exists at that path.
                    elif candidate.exists() and not candidate.is_dir():
                        pass
                    # Block if a folder exists but is already registered.
                    elif candidate.exists() and candidate.is_dir() and key in existing_folder_keys:
                        pass
                    else:
                        folder_path = candidate
                        break

                    folder_name = f"{folder_base}_{suffix}"
                    suffix += 1

                try:
                    folder_path.mkdir(parents=True, exist_ok=True)
                    if folder_path.exists():
                        print(f" {Colors.GRAY}Folder ready: {folder_path}{Colors.RESET}")
                except Exception as e:
                    print(f"{Colors.RED}Failed to create folder '{folder_name}': {e}{Colors.RESET}\n")
                    continue

            folder_key = folder_name.strip().lower()
            
            new_playlist = {
                "name": name.strip(),
                "url": url,
                "folder": folder_name,
                "is_new": True  # Mark as new
            }
            if playlist_id:
                new_playlist["playlist_id"] = playlist_id
            
            # Add to settings + session tracking
            settings.setdefault("playlists", []).append(new_playlist)
            settings.setdefault("new_playlists", []).append(new_playlist)
            session_new_playlists.append(new_playlist)
            existing.append(new_playlist)
            if name_key:
                existing_name_keys.add(name_key)
            existing_folder_keys.add(folder_key)
            if playlist_id:
                existing_playlist_ids.add(playlist_id)
            
            print(f"{Colors.GREEN}✓ Added '{name}'{Colors.RESET}\n")

        elif action in ("i", "import"):
            unregistered = _scan_unregistered_folders(base_folder, existing)
            if not unregistered:
                print(f"\n{Colors.GRAY}No unregistered subfolders found under: {base_folder}{Colors.RESET}\n")
                continue

            print(f"\n{Colors.YELLOW}Found {len(unregistered)} unregistered folder(s) under:{Colors.RESET}")
            print(f" {Colors.GRAY}{base_folder}{Colors.RESET}")
            do_import = input(f"{Colors.BLUE}Import/register them now? (y/N): {Colors.RESET}").strip().lower()
            if do_import not in ("y", "yes"):
                print()
                continue

            for folder in unregistered:
                print(f"\n{Colors.CYAN}Folder:{Colors.RESET} {folder.name}")
                url = input(f" {Colors.BLUE}Playlist URL for this folder (blank to skip): {Colors.RESET}").strip()
                if not url:
                    continue
                url = normalize_url(url)
                if not is_probably_url(url):
                    print(f" {Colors.RED}Invalid URL. Skipping.{Colors.RESET}")
                    continue

                playlist_id = extract_playlist_id(url)
                if not playlist_id:
                    print(f" {Colors.RED}That link is not a playlist (missing 'list='). Skipping.{Colors.RESET}")
                    continue
                if playlist_id and playlist_id in existing_playlist_ids:
                    print(f" {Colors.RED}That playlist ID is already configured. Skipping.{Colors.RESET}")
                    continue

                name = folder.name
                name_key = name.strip().lower()
                if name_key and name_key in existing_name_keys:
                    name = f"{name}_imported"
                    name_key = name.lower()

                folder_key = folder.name.lower()
                if folder_key in existing_folder_keys:
                    print(f" {Colors.RED}Folder already registered in settings. Skipping.{Colors.RESET}")
                    continue

                imported = {
                    "name": name,
                    "url": url,
                    "folder": folder.name,
                    "is_new": False,
                }
                if playlist_id:
                    imported["playlist_id"] = playlist_id

                settings.setdefault("playlists", []).append(imported)
                existing.append(imported)
                existing_name_keys.add(name_key)
                existing_folder_keys.add(folder_key)
                if playlist_id:
                    existing_playlist_ids.add(playlist_id)

                print(f" {Colors.GREEN}✓ Imported '{name}'{Colors.RESET}")
        
        elif action in ("r", "remove") and existing:
            try:
                idx = int(input(f"{Colors.BLUE}Enter number to remove (1-{len(existing)}): {Colors.RESET}"))
                if 1 <= idx <= len(existing):
                    removed = existing.pop(idx-1)
                    removed_name = removed.get('name','(unnamed)')
                    print(f"{Colors.YELLOW}Removed '{removed_name}'{Colors.RESET}\n")

                    # Update persisted playlist list
                    try:
                        settings["playlists"] = existing
                    except Exception:
                        pass

                    # Keep new_playlists in sync as well (use normalized playlist key).
                    def _playlist_key(item: Dict[str, Any]) -> str:
                        url_norm = normalize_url(str(item.get("url", "") or "")).strip()
                        pid = str(item.get("playlist_id") or extract_playlist_id(url_norm) or "").strip()
                        return (pid or url_norm).strip().lower()

                    removed_key = _playlist_key(removed)
                    if removed_key:
                        settings["new_playlists"] = [
                            item
                            for item in settings.get("new_playlists", [])
                            if isinstance(item, dict) and _playlist_key(item) != removed_key
                        ]

                    # Offer to delete the playlist folder; default is to move it to a quarantine folder
                    base = Path(settings.get("download_path", Path.home() / "Music" / "YouTube Playlists"))
                    folder_hint = (removed.get("folder") or "").strip() or removed_name
                    if os.path.isabs(folder_hint):
                        playlist_folder = Path(folder_hint)
                    else:
                        playlist_folder = base / sanitize_folder_name(folder_hint)

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

    save_settings(settings)
    print(f"{Colors.GREEN}✓ Settings saved!{Colors.RESET}")
    
    # Return whether new playlists were added
    return len(session_new_playlists) > 0, session_new_playlists