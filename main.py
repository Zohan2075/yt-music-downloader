#!/usr/bin/env python3
"""
YouTube Playlist Manager - Main Orchestrator
Smart sync • Auto-download • Safe cleanup • Duplicate protection
"""

import os
import re
import subprocess
import sys
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
    cookies_path_if_exists,
    ytdlp_common_flags,
    normalize_url,
    is_probably_url,
)
from settings import load_settings, save_settings, setup_preferences
from downloader import PlaylistSyncer, PlaylistInfo, SyncMode
from progress import ProgressBar, format_bytes, format_speed, format_eta

ESCAPE_SENTINEL = "__SAFE_INPUT_ESC__"


def safe_input(prompt: str, default: str = "", allow_escape: bool = False) -> str:
    """Input wrapper that returns default on EOFError and strips whitespace."""
    if allow_escape and os.name == "nt" and sys.stdin.isatty() and sys.stdout.isatty():
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

    url = normalize_url(url)
    if not is_probably_url(url):
        print(f"{Colors.RED}❌ That doesn't look like a valid URL: {url}{Colors.RESET}")
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
    cookies_ready = cookies_path_if_exists() is not None
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

    cookies_path = cookies_path_if_exists()
    progress_bar = ProgressBar(total=1, width=36, title="Single download", show_counts=False)

    def progress_hook(data: Dict[str, Any]) -> None:
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            speed = data.get("speed")
            eta = data.get("eta")
            status_text = (
                f"{format_bytes(downloaded)} / {format_bytes(total)} • "
                f"{format_speed(speed)} • ETA {format_eta(eta)}"
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
    if cookies_path:
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

    cmd = ["yt-dlp"]
    cmd.extend(ytdlp_common_flags(debug=False))
    cmd.extend([
        "-f",
        "bestaudio/best",
        "--add-metadata",
        "--no-playlist",
        "-o",
        output_template,
        url,
    ])

    cookies_path = cookies_path_if_exists()
    if cookies_path:
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


def run_sync_mode(settings: Dict[str, Any]) -> None:
    """Synchronize all configured playlists in download-only mode."""
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
        folder = base_path / sanitize_folder_name(playlist.get("name", "playlist"))
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
    print(
        f"{Colors.GREEN}✓ Successfully processed: {success_count}/{len(playlists)} playlists{Colors.RESET}"
    )
    if total_new_downloads > 0:
        print(f"{Colors.GREEN}✓ New songs downloaded: {total_new_downloads}{Colors.RESET}")
    else:
        print(f"{Colors.YELLOW}✓ No new songs found to download{Colors.RESET}")
    if total_removed > 0:
        print(f"{Colors.RED}✓ Removed tracks no longer in the playlist: {total_removed}{Colors.RESET}")
    print(f"{Colors.GREEN}✓ New downloads were automatically cleaned & renamed{Colors.RESET}")
    print(f"{Colors.GREEN}✓ Location: {base_path}{Colors.RESET}")
    print(f"{Colors.GREEN}{'='*60}{Colors.RESET}")


def main() -> None:
    """Main orchestrator function"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    print_banner()
    
    try:
        ensure_dependencies()
    except RuntimeError as e:
        print(f"{Colors.RED}❌ {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}Please install: pip install yt-dlp{Colors.RESET}")
        return

    settings = load_settings()

    while True:
        print(f"{Colors.BLUE}Main Menu:{Colors.RESET}")
        print(" 1. Sync and Auto-download/deletion")
        print(" 2. Add or Remove Playlist")
        print(" 3. Download a single song/video")
        print(" X. Exit (press ESC to exit)")

        main_choice = safe_input(
            f"\n{Colors.BLUE}Select option (1/2/3 or X to exit) [1]: {Colors.RESET}",
            default="1",
            allow_escape=True,
        )

        if main_choice == ESCAPE_SENTINEL:
            print(f"\n{Colors.YELLOW}⏹ Exiting at user request.{Colors.RESET}")
            break

        normalized_choice = main_choice.lower()
        if normalized_choice in {"x", "exit", "q"}:
            print(f"\n{Colors.YELLOW}⏹ Exiting at user request.{Colors.RESET}")
            break

        if normalized_choice == "2":
            setup_preferences(settings)
            print(f"\n{Colors.GREEN}✓ Settings updated.{Colors.RESET}")
            settings = load_settings()
            continue

        if normalized_choice == "3":
            run_single_download_flow(settings)
            continue

        if normalized_choice == "1":
            if not settings.get("playlists"):
                print(f"\n{Colors.YELLOW}No playlists configured.{Colors.RESET}")
                print(f"{Colors.BLUE}You need to configure playlists first.{Colors.RESET}")
                configure_now = safe_input(
                    f"{Colors.BLUE}Configure now? (y/N): {Colors.RESET}", default=""
                ).lower()
                if configure_now in ("y", "yes"):
                    setup_preferences(settings)
                    settings = load_settings()
                continue

            run_sync_mode(settings)
            continue

        print(f"\n{Colors.YELLOW}Please select a valid option from the menu.{Colors.RESET}")
        

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠ Process interrupted by user{Colors.RESET}")
    except Exception as e:
        print(f"\n{Colors.RED}❌ Unexpected error: {e}{Colors.RESET}")