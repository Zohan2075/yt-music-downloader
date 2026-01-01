#!/usr/bin/env python3
"""
YouTube Playlist Manager - Main Orchestrator
Smart sync • Auto-download • Safe cleanup • Duplicate protection
"""

import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import time

from colors import Colors, print_banner
from utils import (
    ensure_dependencies,
    select_download_folder,
    sanitize_folder_name,
    sanitize_filename,
    COOKIES_FILE,
)
from settings import load_settings, save_settings, setup_preferences
from downloader import PlaylistSyncer, PlaylistInfo, SyncMode
from progress import ProgressBar

ESCAPE_SENTINEL = "__SAFE_INPUT_ESC__"


def safe_input(prompt: str, default: str = "", allow_escape: bool = False) -> str:
    """Input wrapper that returns default on EOFError and strips whitespace."""
    if allow_escape and os.name == "nt":
        try:
            import msvcrt  # type: ignore

            print(prompt, end="", flush=True)
            buffer: List[str] = []
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    print()
                    value = ''.join(buffer).strip()
                    return value or default
                if ch == "\x1b":
                    print()
                    return ESCAPE_SENTINEL
                if ch in ("\x08", "\x7f"):
                    if buffer:
                        buffer.pop()
                        print("\b \b", end="", flush=True)
                    continue
                buffer.append(ch)
                print(ch, end="", flush=True)
        except Exception:
            pass
    try:
        value = input(prompt)
        value = value.strip()
        if allow_escape and value == "\x1b":
            return ESCAPE_SENTINEL
        return value or default
    except EOFError:
        return default


def human_size(num_bytes: Optional[float]) -> str:
    """Return human readable size string."""
    if num_bytes is None or num_bytes <= 0:
        return "--"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:6.2f} {units[idx]}"


def human_speed(num_bytes_per_sec: Optional[float]) -> str:
    if num_bytes_per_sec is None or num_bytes_per_sec <= 0:
        return "--/s"
    return f"{human_size(num_bytes_per_sec)}/s"


def human_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


SIZE_TOKEN_RE = re.compile(r"(?P<value>[0-9]+(?:\.[0-9]+)?)(?P<unit>[KMGTP]?i?B)", re.IGNORECASE)
CLI_PROGRESS_RE = re.compile(
    r"\[download\]\s+(?P<percent>[0-9]+(?:\.[0-9]+)?)%.*?of\s+(?P<total>\S+)\s+at\s+(?P<speed>\S+)\s+ETA\s+(?P<eta>\S+)",
    re.IGNORECASE,
)
CLI_DONE_RE = re.compile(
    r"\[download\]\s+100%.*?of\s+(?P<total>\S+)\s+in\s+(?P<duration>\S+)\s+at\s+(?P<speed>\S+)",
    re.IGNORECASE,
)


def parse_size_token(token: str) -> Optional[float]:
    token = token.strip().replace("/s", "")
    match = SIZE_TOKEN_RE.match(token)
    if not match:
        return None
    value = float(match.group("value"))
    unit = match.group("unit").lower()
    multiplier = {
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000 ** 2,
        "mib": 1024 ** 2,
        "gb": 1000 ** 3,
        "gib": 1024 ** 3,
        "tb": 1000 ** 4,
        "tib": 1024 ** 4,
    }.get(unit, 1)
    return value * multiplier


def run_single_download_flow(settings: Dict[str, Any]) -> None:
    """Interactive flow for downloading a single video/audio file."""
    print(f"\n{Colors.GREEN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}⬇ SINGLE DOWNLOAD MODE{Colors.RESET}")
    print(f"{Colors.GRAY}Grab a one-off track or video without touching your playlists.{Colors.RESET}")

    url = safe_input(
        f"\n{Colors.BLUE}Paste the YouTube / YT Music link (ESC to cancel): {Colors.RESET}",
        allow_escape=True,
    ).strip()
    if url == ESCAPE_SENTINEL or not url:
        print(f"{Colors.YELLOW}⏹ Cancelled single download.{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")
        return

    print(f"\n{Colors.BLUE}1. Fetching metadata...{Colors.RESET}")
    title = fetch_video_title(url)
    if not title:
        print(f"{Colors.YELLOW}⚠ Could not detect the title. Using a generic name.{Colors.RESET}")
        title = "downloaded_track"
    else:
        print(f"{Colors.GREEN}✓ Original title detected: {title}{Colors.RESET}")

    default_base = settings.get("download_path") or str(Path.home())
    print(f"\n{Colors.BLUE}2. Choose destination folder{Colors.RESET}")
    print(f"{Colors.GRAY}Default base: {default_base}{Colors.RESET}")
    target_dir = Path(select_download_folder(default_base))
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"{Colors.GREEN}✓ Destination locked: {target_dir}{Colors.RESET}")

    print(f"\n{Colors.BLUE}3. Download & tag{Colors.RESET}")
    planned_stub = sanitize_filename(title) or "downloaded_track"
    cookies_ready = Path(COOKIES_FILE).exists()
    print(
        f"{Colors.GRAY}Format: bestaudio/best • Metadata tagging ✓ • Cookies: "
        f"{'auto' if cookies_ready else 'not found'}{Colors.RESET}"
    )
    print(f"{Colors.GRAY}Output preview: {planned_stub}.<ext>{Colors.RESET}")
    success = download_single_video(url, target_dir, title)
    if success:
        print(f"{Colors.GREEN}🎉 Download complete! Check the folder above.{Colors.RESET}")
    else:
        print(f"{Colors.RED}❌ Download failed. See details above and try again.{Colors.RESET}")
    print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")


def fetch_video_title(url: str, timeout: int = 15) -> Optional[str]:
    """Use yt-dlp to fetch a video's original title."""
    try:
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--skip-download",
            "--print",
            "%(title)s",
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
        title = result.stdout.strip().splitlines()
        return title[0] if title else None
    except Exception:
        return None


def download_single_video(url: str, folder: Path, display_name: str) -> bool:
    """Download a single video/audio file with a rich, colored progress bar."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        print(
            f"{Colors.YELLOW}⚠ Python yt-dlp module not found; falling back to basic console output.{Colors.RESET}"
        )
        return _download_single_video_cli(url, folder, display_name)

    return _download_single_video_with_api(yt_dlp, url, folder, display_name)


def _download_single_video_with_api(yt_dlp_module: Any, url: str, folder: Path, display_name: str) -> bool:
    safe_name = sanitize_filename(display_name) or "downloaded_track"
    output_template = str(folder / f"{safe_name}.%(ext)s")

    cookies_path = Path(COOKIES_FILE)
    progress_bar = ProgressBar(total=1, width=36, title="Single download", show_counts=False)

    def progress_hook(data: Dict[str, Any]) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            speed = data.get("speed")
            eta = data.get("eta")
            status_text = (
                f"{human_size(downloaded)} / {human_size(total)} • "
                f"{human_speed(speed)} • ETA {human_eta(eta)}"
            )
            progress_bar.update(downloaded, total=total, status=status_text)
        elif status == "finished":
            progress_bar.update(progress_bar.total or progress_bar.current, status="Tagging & cleanup…")

    ydl_opts: Dict[str, Any] = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "postprocessors": [{"key": "FFmpegMetadata"}],
    }
    if cookies_path.exists():
        ydl_opts["cookiefile"] = str(cookies_path)

    try:
        with yt_dlp_module.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        progress_bar.complete("All done!")
        return True
    except Exception as exc:  # yt_dlp reports detailed context in message
        print()
        print(f"{Colors.RED}❌ yt-dlp error: {exc}{Colors.RESET}")
        return False


def _download_single_video_cli(url: str, folder: Path, display_name: str) -> bool:
    """Fallback downloader using the yt-dlp CLI output (no fancy progress)."""
    safe_name = sanitize_filename(display_name) or "downloaded_track"
    output_template = str(folder / f"{safe_name}.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "--add-metadata",
        "--no-playlist",
        "--newline",
        "--progress",
        "--no-warnings",
        "-o",
        output_template,
        url,
    ]

    cookies_path = Path(COOKIES_FILE)
    if cookies_path.exists():
        cmd.extend(["--cookies", str(cookies_path)])

    try:
        print(f"{Colors.GRAY}Starting yt-dlp fallback download...{Colors.RESET}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
    except FileNotFoundError:
        print(f"{Colors.RED}yt-dlp binary not found. Please install it first.{Colors.RESET}")
        return False
    except Exception as exc:
        print(f"{Colors.RED}Unexpected error: {exc}{Colors.RESET}")
        return False

    progress_bar = ProgressBar(total=1, width=36, title="Single download", show_counts=False)
    total_bytes: Optional[float] = None

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        match = CLI_PROGRESS_RE.search(line)
        if match:
            percent = float(match.group("percent"))
            total_token = match.group("total")
            speed_token = match.group("speed")
            eta_token = match.group("eta")
            total_bytes = total_bytes or parse_size_token(total_token)
            downloaded = (
                percent / 100.0 * total_bytes if (total_bytes and total_bytes > 0) else percent
            )
            status_text = (
                f"{percent:5.1f}% • {speed_token} • ETA {eta_token} • total {total_token}"
            )
            progress_bar.update(downloaded, total=total_bytes or 100.0, status=status_text)
            continue
        match_done = CLI_DONE_RE.search(line)
        if match_done:
            total_token = match_done.group("total")
            speed_token = match_done.group("speed")
            duration_token = match_done.group("duration")
            total_bytes = total_bytes or parse_size_token(total_token)
            progress_bar.update(
                total_bytes or progress_bar.total or 1,
                total=total_bytes or progress_bar.total or 1,
                status=f"Finished in {duration_token} @ {speed_token}",
            )
            continue
        # Non-progress output (warnings/info)
        print(f"\n{Colors.YELLOW}{line}{Colors.RESET}")

    process.stdout.close()
    stderr_output = process.stderr.read() if process.stderr else ""
    return_code = process.wait()

    if stderr_output.strip():
        print(f"\n{Colors.YELLOW}{stderr_output.strip()}{Colors.RESET}")

    if return_code == 0:
        progress_bar.complete("All done!")
        return True

    progress_bar.update(progress_bar.current, status="Failed")
    print(f"\n{Colors.RED}yt-dlp returned exit code {return_code}.{Colors.RESET}")
    return False


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
    print(f" 1. Sync and Auto-download/deletion")
    print(f" 2. Add or Remove Playlist")
    print(f" 3. Download a single song/video")
    print(f" X. Exit (press ESC to exit)")
    
    main_choice = safe_input(
        f"\n{Colors.BLUE}Select option (1/2/3 or X to exit) [1]: {Colors.RESET}",
        default="1",
        allow_escape=True,
    )

    if main_choice == ESCAPE_SENTINEL:
        print(f"\n{Colors.YELLOW}⏹ Exiting at user request.{Colors.RESET}")
        return
    
    normalized_choice = main_choice.lower()
    if normalized_choice in {"x", "exit", "q"}:
        print(f"\n{Colors.YELLOW}⏹ Exiting at user request.{Colors.RESET}")
        return
    
    if normalized_choice == "2":

        # Go to settings configuration
        setup_preferences(settings)
        print(f"\n{Colors.GREEN}✓ Settings updated. Restart the program to sync.{Colors.RESET}")
        return
    if normalized_choice == "3":
        run_single_download_flow(settings)
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
    
    if normalized_choice == "1":
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
        total_removed = 0
        
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
                total_removed += res.get("removed_missing", 0)
            
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
        if total_removed > 0:
            print(f"{Colors.RED}✓ Removed tracks no longer in the playlist: {total_removed}{Colors.RESET}")
        print(f"{Colors.GREEN}✓ New downloads were automatically cleaned & renamed{Colors.RESET}")
        print(f"{Colors.GREEN}✓ Location: {base_path}{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")
        

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠ Process interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Unexpected error: {e}{Colors.RESET}")