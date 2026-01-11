from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from src.ui.colors import Colors
from src.core.cli import safe_input
from src.core.utils import sanitize_folder_name
from src.core.downloader import PlaylistSyncer, PlaylistInfo, SyncMode


def run_sync_mode(settings: Dict[str, Any]) -> None:
    """Menu option 1: synchronize all configured playlists in download-only mode."""
    playlists = settings.get("playlists", [])
    if not playlists:
        print(f"\n{Colors.YELLOW}No playlists configured.{Colors.RESET}")
        return

    base_path = Path(settings["download_path"])
    base_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{Colors.GREEN}⬇ SYNC & AUTO-DOWNLOAD MODE: Syncing & auto-downloading new songs{Colors.RESET}")
    print(f"{Colors.YELLOW}⚠ Will sync playlists, download new songs, and auto-clean/rename them{Colors.RESET}")
    print(f"{Colors.GRAY}Base folder: {base_path}{Colors.RESET}\n")

    debug_choice = safe_input(
        f"{Colors.BLUE}Enable debug download logging for this run? (y/N): {Colors.RESET}",
        default="",
    ).lower()
    debug_enabled = debug_choice in ("y", "yes")
    if debug_enabled:
        print(
            f"{Colors.YELLOW}Debug mode enabled: yt-dlp logs and batch files will be written to each playlist folder{Colors.RESET}"
        )

    success_count = 0
    total_new_downloads = 0
    total_removed = 0

    for index, playlist in enumerate(playlists, 1):
        print(f"\n{Colors.BLUE}[{index}/{len(playlists)}]{Colors.RESET}")
        folder_hint = playlist.get("folder") or playlist.get("name", "playlist")
        folder = base_path / sanitize_folder_name(str(folder_hint))
        pl_info = PlaylistInfo(
            name=playlist.get("name", "playlist"),
            url=playlist.get("url", ""),
            folder=folder,
        )
        syncer = PlaylistSyncer(pl_info, settings)
        result = syncer.sync(SyncMode.DOWNLOAD_ONLY, debug=debug_enabled)

        if result.get("success", False):
            success_count += 1
            total_new_downloads += result.get("new_downloads", 0)
            total_removed += result.get("removed_missing", 0)

        if index < len(playlists):
            time.sleep(0.5)

    print(f"\n{Colors.GREEN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}✅ Sync & Auto-download Complete!{Colors.RESET}")
    print(f"{Colors.GREEN}✓ Successfully processed: {success_count}/{len(playlists)} playlists{Colors.RESET}")
    if total_new_downloads > 0:
        print(f"{Colors.GREEN}✓ New songs downloaded: {total_new_downloads}{Colors.RESET}")
    else:
        print(f"{Colors.YELLOW}✓ No new songs found to download{Colors.RESET}")
    if total_removed > 0:
        print(f"{Colors.RED}✓ Playlist removals applied: {total_removed}{Colors.RESET}")
    print(f"{Colors.GREEN}✓ New downloads were automatically cleaned & renamed{Colors.RESET}")
    print(f"{Colors.GREEN}✓ Location: {base_path}{Colors.RESET}")
    print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")
