"""
Settings management
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import tkinter as tk
from tkinter import filedialog

from utils import select_download_folder, sanitize_folder_name, extract_playlist_id, normalize_url, is_probably_url
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

    existing_folder_names: set[str] = set()
    folder_display_map: Dict[str, str] = {}
    for pl in existing:
        name = pl.get("name", "")
        folder_override = pl.get("folder")
        if folder_override:
            sanitized = sanitize_folder_name(folder_override)
        else:
            sanitized = sanitize_folder_name(name)
        if sanitized:
            key = sanitized.lower()
            existing_folder_names.add(key)
            folder_display_map.setdefault(key, folder_override or sanitized)

    try:
        if base_folder.exists():
            for child in base_folder.iterdir():
                if child.is_dir():
                    sanitized = sanitize_folder_name(child.name)
                    key = sanitized.lower()
                    existing_folder_names.add(key)
                    folder_display_map[key] = child.name
    except Exception:
        pass

    def browse_existing_folder() -> Optional[Tuple[str, str]]:
        """Let the user pick an existing folder via dialog.

        Safety: only accept directories that are direct children of base_folder.
        Returns: (folder_key, display_name) or None.
        """
        try:
            if not base_folder.exists():
                print(f"{Colors.YELLOW}Base folder does not exist yet: {base_folder}{Colors.RESET}")
                return None

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.update_idletasks()
            picked = filedialog.askdirectory(
                title="Select an existing playlist folder (must be inside the base folder)",
                initialdir=str(base_folder),
            )
            root.destroy()

            if not picked:
                return None
            picked_path = Path(picked)
            try:
                picked_resolved = picked_path.resolve()
                base_resolved = base_folder.resolve()
            except Exception:
                picked_resolved = picked_path
                base_resolved = base_folder

            if picked_resolved.parent != base_resolved:
                print(
                    f"{Colors.RED}Selected folder must be a direct child of {base_folder}.{Colors.RESET}\n"
                )
                return None

            display = picked_resolved.name
            sanitized = sanitize_folder_name(display)
            return sanitized.lower(), display
        except Exception as e:
            print(f"{Colors.YELLOW}⚠ Folder picker failed: {e}{Colors.RESET}")
            return None

    def choose_existing_folder() -> Optional[Tuple[str, str]]:
        if not folder_display_map:
            print(f"{Colors.YELLOW}No existing folders detected in {base_folder}.{Colors.RESET}")
            return None

        options: List[Tuple[str, str]] = []
        seen: set[str] = set()
        for key, display in sorted(folder_display_map.items(), key=lambda item: item[1].lower()):
            if key in seen:
                continue
            seen.add(key)
            options.append((key, display))

        if not options:
            print(f"{Colors.YELLOW}No reusable folders available in {base_folder}.{Colors.RESET}")
            return None

        print(f"\n{Colors.BOLD}Select an existing folder to reuse:{Colors.RESET}")
        for idx, (_, display) in enumerate(options, 1):
            location = base_folder / display
            status = "✓" if location.exists() else "⚠"
            print(f" {idx:2}. {display} {Colors.GRAY}({status} {'exists' if status == '✓' else 'missing'}){Colors.RESET}")

        while True:
            choice = input(f"{Colors.BLUE}Enter number to reuse or press Enter to cancel: {Colors.RESET}").strip()
            if not choice:
                return None
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(options):
                    return options[idx - 1]
            print(f"{Colors.RED}Invalid selection. Try again.{Colors.RESET}")
    
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

            url = normalize_url(url)
            if not is_probably_url(url):
                print(f"{Colors.RED}That doesn't look like a valid URL: '{url}'. Skipping.{Colors.RESET}\n")
                continue

            # Safety: require a real playlist URL. A single-video link (youtu.be/...) will scan as an empty playlist
            # and the sync step can quarantine everything as "missing".
            playlist_id = extract_playlist_id(url)
            if not playlist_id:
                print(
                    f"{Colors.RED}That link is not a playlist (missing 'list='). Paste a YouTube playlist URL.{Colors.RESET}\n"
                )
                continue
            
            default_name = f"Playlist_{len(existing) + len(new_playlists) + 1}"

            sanitized_name: Optional[str] = None
            folder_key = ""
            folder_exists = False
            selected_folder_display = ""

            if folder_display_map:
                reuse_prompt = input(
                    f"{Colors.BLUE}Use an existing folder for this playlist? (y/N): {Colors.RESET}"
                ).strip().lower()
                if reuse_prompt in ("y", "yes"):
                    chosen = choose_existing_folder()
                    if chosen:
                        folder_key, selected_folder_display = chosen
                        sanitized_name = folder_display_map.get(folder_key, selected_folder_display)
                        folder_exists = True
                    else:
                        print(f"{Colors.YELLOW}No folder selected. A new folder will be configured.{Colors.RESET}")

            if not folder_exists:
                browse_prompt = input(
                    f"{Colors.BLUE}Browse to select an existing folder inside the base folder? (y/N): {Colors.RESET}"
                ).strip().lower()
                if browse_prompt in ("y", "yes"):
                    picked = browse_existing_folder()
                    if picked:
                        folder_key, selected_folder_display = picked
                        sanitized_name = selected_folder_display
                        folder_exists = True
                    else:
                        print(f"{Colors.YELLOW}No folder selected. A new folder will be configured.{Colors.RESET}")

            if not folder_exists:
                folder_input = input(
                    f" {Colors.BLUE}Folder name [{default_name}]: {Colors.RESET}"
                ).strip()
                if not folder_input:
                    folder_input = default_name
                sanitized_name = sanitize_folder_name(folder_input)
                folder_key = sanitized_name.lower()

                if folder_key in existing_folder_names:
                    print(
                        f"{Colors.RED}Folder '{sanitized_name}' already exists in {base_folder}. Choose another name or reuse an existing folder.{Colors.RESET}\n"
                    )
                    continue
            else:
                sanitized_name = sanitize_folder_name(sanitized_name or selected_folder_display)
                folder_key = sanitized_name.lower()

            if folder_exists:
                name = selected_folder_display or sanitized_name or default_name
            else:
                display_default = sanitized_name or default_name
                name = input(
                    f" {Colors.BLUE}Playlist name [{display_default}]: {Colors.RESET}"
                ).strip() or display_default

            name_key = name.strip().lower()

            if name_key and name_key in existing_name_keys:
                print(f"{Colors.RED}Playlist name '{name}' already exists. Choose a different name.{Colors.RESET}\n")
                continue

            if playlist_id and playlist_id in existing_playlist_ids:
                print(f"{Colors.RED}Playlist ID '{playlist_id}' is already configured locally. Use a different playlist.{Colors.RESET}\n")
                continue
            
            folder_for_storage = selected_folder_display if folder_exists else sanitized_name

            new_playlist = {
                "name": name.strip(),
                "url": url,
                "folder": folder_for_storage,
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
            if sanitized_name is not None:
                existing_folder_names.add(folder_key)
                folder_display_map[folder_key] = folder_for_storage or sanitized_name
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

                    # Keep new_playlists in sync as well.
                    def _playlist_key(item: Dict[str, Any]) -> str:
                        url_norm = normalize_url(str(item.get("url", "") or "")).strip()
                        pid = str(item.get("playlist_id") or extract_playlist_id(url_norm) or "").strip()
                        return (pid or url_norm).strip().lower()

                    removed_key = _playlist_key(removed)
                    if removed_key:
                        settings["new_playlists"] = [
                            item for item in settings.get("new_playlists", [])
                            if isinstance(item, dict) and _playlist_key(item) != removed_key
                        ]

                    # Offer to delete the playlist folder; default is to move it to a quarantine folder
                    base = Path(settings.get("download_path", Path.home() / "Music" / "YouTube Playlists"))
                    folder_hint = removed.get("folder") or removed_name
                    playlist_folder = base / sanitize_folder_name(str(folder_hint))

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