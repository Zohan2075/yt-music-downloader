from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from src.ui.colors import Colors
from src.core.cli import safe_input, ESCAPE_SENTINEL
from src.core.progress import ProgressBar, format_bytes, format_speed, format_eta
from src.core.utils import (
    cookies_path_if_exists,
    is_probably_url,
    looks_like_playlist_url,
    normalize_url,
    sanitize_filename,
    select_download_folder,
    ytdlp_common_flags,
)


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
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }.get(unit, 1)
    return value * multiplier


def run_single_download_mode(settings: Dict[str, Any]) -> None:
    """Menu option 3: download a single track/video without touching playlists."""
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

    if looks_like_playlist_url(url):
        print(
            f"{Colors.YELLOW}⚠ That link points to a playlist. Use option 1 for playlist sync/downloads.{Colors.RESET}"
        )
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
    except Exception as exc:
        print()
        print(f"{Colors.RED}❌ yt-dlp error: {exc}{Colors.RESET}")
        return False


def _download_single_video_cli(url: str, folder: Path, display_name: str) -> bool:
    """Fallback downloader using the yt-dlp CLI output (no Python module required)."""
    safe_name = sanitize_filename(display_name) or "downloaded_track"
    output_template = str(folder / f"{safe_name}.%(ext)s")

    cmd = ["yt-dlp"]
    cmd.extend(ytdlp_common_flags(debug=False))
    cmd.extend(
        [
            "-f",
            "bestaudio/best",
            "--add-metadata",
            "--no-playlist",
            "-o",
            output_template,
            url,
        ]
    )

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
            downloaded = percent / 100.0 * total_bytes if (total_bytes and total_bytes > 0) else percent
            status_text = f"{percent:5.1f}% • {speed_token} • ETA {eta_token} • total {total_token}"
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
