#!/usr/bin/env python3
"""
YouTube Playlist Manager - Main Orchestrator
Smart sync • Auto-download • Safe cleanup • Duplicate protection
"""

from pathlib import Path
from typing import List, Dict, Any
import time

from colors import Colors, print_banner
from utils import ensure_dependencies, select_download_folder, sanitize_folder_name
from settings import load_settings, save_settings, setup_preferences
from downloader import PlaylistSyncer, PlaylistInfo, SyncMode


def safe_input(prompt: str, default: str = "") -> str:
    """Input wrapper that returns default on EOFError and strips whitespace."""
    try:
        return input(prompt).strip() or default
    except EOFError:
        return default


def main() -> None:
    """Main orchestrator function"""
    print_banner()
    
    try:
        ensure_dependencies()
    except RuntimeError as e:
        print(f"{Colors.RED}❌ {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Please install: pip install yt-dlp{Colors.RESET}")
        return

    # Load settings
    settings = load_settings()
    
    # Main menu - SIMPLIFIED: Only 3 options now
    print(f"{Colors.BLUE}Main Menu:{Colors.RESET}")
    print(f" 1. Sync and Auto-download.")
    print(f" 2. Sync & organize existing library")
    print(f" 3. Add or Remove Playlist")
    
    main_choice = safe_input(f"\n{Colors.BLUE}Select option (1/2/3) [1]: {Colors.RESET}", default="1")
    
    if main_choice == "3":

        # Go to settings configuration
        setup_preferences(settings)
        print(f"\n{Colors.GREEN}✓ Settings updated. Restart the program to sync.{Colors.RESET}")
        return
    
    # Check if we have playlists to sync
    if not settings.get("playlists"):
        print(f"\n{Colors.YELLOW}No playlists configured.{Colors.RESET}")
        print(f"{Colors.BLUE}You need to configure playlists first.{Colors.RESET}")
        
        configure_now = safe_input(f"{Colors.BLUE}Configure now? (y/N): {Colors.RESET}", default="").lower()
        if configure_now in ("y", "yes"):
            setup_preferences(settings)
            print(f"\n{Colors.GREEN}✓ Settings saved. Restart the program to sync.{Colors.RESET}")
        return
    
    base_path = Path(settings["download_path"])
    base_path.mkdir(parents=True, exist_ok=True)
    
    if main_choice == "1":
        # SYNC & AUTO-DOWNLOAD MODE: Sync playlists and auto-download new songs
        print(f"\n{Colors.GREEN}⬇ SYNC & AUTO-DOWNLOAD MODE: Syncing & auto-downloading new songs{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠ Will sync playlists, download new songs, and auto-clean/rename them{Colors.RESET}")
        print(f"{Colors.GRAY}Base folder: {base_path}{Colors.RESET}\n")
        
        # Optional debug logging for this run
        debug_choice = safe_input(f"{Colors.BLUE}Enable debug download logging for this run? (y/N): {Colors.RESET}", default="").lower()
        debug_enabled = debug_choice in ("y","yes")
        if debug_enabled:
            print(f"{Colors.YELLOW}Debug mode enabled: yt-dlp logs and batch files will be written to each playlist folder{Colors.RESET}")
        
        success_count = 0
        total_new_downloads = 0
        
        for i, playlist in enumerate(settings["playlists"], 1):
            print(f"\n{Colors.BLUE}[{i}/{len(settings['playlists'])}]{Colors.RESET}")
            folder = base_path / sanitize_folder_name(playlist.get('name','playlist'))
            pl_info = PlaylistInfo(name=playlist.get('name','playlist'), url=playlist.get('url',''), folder=folder)
            syncer = PlaylistSyncer(pl_info, settings)
            
            # Download mode: only downloads new songs, cleans them
            res = syncer.sync(SyncMode.DOWNLOAD_ONLY, debug=debug_enabled)
            if res.get("success", False):
                success_count += 1
                total_new_downloads += res.get("new_downloads", 0)
            
            if i < len(settings['playlists']):
                time.sleep(0.5)
        
        # Summary for Download Mode
        print(f"\n{Colors.GREEN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}✅ Sync & Auto-download Complete!{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Successfully processed: {success_count}/{len(settings['playlists'])} playlists{Colors.RESET}")
        if total_new_downloads > 0:
            print(f"{Colors.GREEN}✓ New songs downloaded: {total_new_downloads}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}✓ No new songs found to download{Colors.RESET}")
        print(f"{Colors.GREEN}✓ New downloads were automatically cleaned & renamed{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Location: {base_path}{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")
        
    elif main_choice == "2":
        # SYNC MODE: Only clean/organize existing files
        print(f"\n{Colors.GREEN}🔄 SYNC MODE: Organizing existing library{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠ Will clean duplicates, rename files, and organize everything{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠ No new songs will be downloaded{Colors.RESET}")
        print(f"{Colors.GRAY}Base folder: {base_path}{Colors.RESET}\n")
        
        success_count = 0
        total_duplicates_removed = 0
        total_files_renamed = 0
        
        apply_all = False
        stop_processing = False
        for i, playlist in enumerate(settings["playlists"], 1):
            if stop_processing:
                break
            print(f"\n{Colors.BLUE}[{i}/{len(settings['playlists'])}]{Colors.RESET}")
            folder = base_path / sanitize_folder_name(playlist.get('name','playlist'))
            pl_info = PlaylistInfo(name=playlist.get('name','playlist'), url=playlist.get('url',''), folder=folder)
            syncer = PlaylistSyncer(pl_info, settings)

            # First run a dry-run to show proposed actions
            print(f"\n{Colors.YELLOW}Running dry-run (no changes will be made)...{Colors.RESET}")
            dry_res = syncer.sync(SyncMode.SYNC_ONLY, dry_run=True)

            if apply_all:
                confirm = 'a'
            else:
                confirm = safe_input(f"{Colors.BLUE}Apply these changes for this playlist? (y/N/a=apply all/s=stop): {Colors.RESET}", default="").lower()

            if confirm == 'a':
                apply_all = True
                real_res = syncer.sync(SyncMode.SYNC_ONLY, dry_run=False)
            elif confirm == 'y':
                real_res = syncer.sync(SyncMode.SYNC_ONLY, dry_run=False)
            elif confirm == 's':
                print(f"{Colors.YELLOW}Stopping further processing.{Colors.RESET}")
                stop_processing = True
                break
            else:
                print(f"{Colors.YELLOW}Skipping changes for this playlist.{Colors.RESET}")
                real_res = {"success": True, "renamed": 0, "duplicates_removed": 0}

            if real_res.get("success", False):
                success_count += 1
                total_duplicates_removed += real_res.get("duplicates_removed", 0)
                total_files_renamed += real_res.get("renamed", 0)

            if i < len(settings['playlists']):
                time.sleep(0.5)
        
        # Summary for Sync Mode
        print(f"\n{Colors.GREEN}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}✅ Library Sync Complete!{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Successfully organized: {success_count}/{len(settings['playlists'])} playlists{Colors.RESET}")
        print(f"{Colors.GREEN}✓ All files named as: Artist - Track (Album){Colors.RESET}")
        if total_duplicates_removed > 0:
            print(f"{Colors.RED}✓ Duplicates removed: {total_duplicates_removed}{Colors.RESET}")
        if total_files_renamed > 0:
            print(f"{Colors.GREEN}✓ Files renamed: {total_files_renamed}{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Image files automatically deleted{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Location: {base_path}{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠ Process interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Unexpected error: {e}{Colors.RESET}")