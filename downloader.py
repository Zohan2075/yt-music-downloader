"""
Enhanced YouTube Playlist Downloader Module
"""

import json
import os
import re
import subprocess
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set, Tuple, Optional, Generator, Callable
from dataclasses import dataclass
from enum import Enum
import logging

from colors import Colors
from progress import ProgressBar
from metadata import MetadataManager, FileNameFormatter
from utils import COOKIES_FILE, sanitize_folder_name, detected_js_runtime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SyncMode(Enum):
    """Sync modes for playlist synchronization"""
    DOWNLOAD_ONLY = "download"
    COMPLETE_SYNC = "complete"
    SYNC_ONLY = "sync"
    AUTO_NEW = "auto"

@dataclass
class PlaylistInfo:
    """Data class for playlist information"""
    name: str
    url: str
    folder: Path

@dataclass
class VideoInfo:
    """Data class for video information"""
    id: str
    title: str
    metadata: Dict[str, str]
    url: str

@dataclass
class DownloadFailure:
    """Represents a single video yt-dlp could not download"""
    video_id: str
    url: str
    reason: str

@dataclass
class DownloadResult:
    """Aggregate result of a yt-dlp run"""
    success: bool
    failures: List[DownloadFailure]

class DownloadError(Exception):
    """Custom exception for download errors"""
    pass

class MetadataError(Exception):
    """Custom exception for metadata errors"""
    pass

class YTDLPWrapper:
    """Wrapper for yt-dlp commands with better error handling"""
    
    @staticmethod
    def get_playlist_info(url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """Get playlist information from yt-dlp"""
        try:
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--dump-single-json",
                "--quiet",
                "--no-warnings",
                url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(f"yt-dlp failed with error: {result.stderr[:200]}")
                return None
                
            return json.loads(result.stdout) if result.stdout else None
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout getting playlist info for {url}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse yt-dlp output: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting playlist info: {e}")
            return None
    
    @staticmethod
    def download_videos(
        video_urls: List[str],
        output_dir: Path,
        archive_file: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
        debug: bool = False,
        log_file_path: Optional[Path] = None,
    ) -> DownloadResult:
        """Download multiple videos using yt-dlp and capture errors"""
        if not video_urls:
            return DownloadResult(success=True, failures=[])
            
        batch_file = output_dir / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        log_file = None
        lf = None
        failures: List[DownloadFailure] = []
        seen_failure_ids: Set[str] = set()
        
        try:
            # Write video URLs to batch file
            with open(batch_file, "w", encoding="utf-8") as f:
                for url in video_urls:
                    f.write(f"{url}\n")
            
            # Build command
            cmd = ["yt-dlp"]

            runtime = detected_js_runtime()
            if runtime:
                cmd.extend(["--js-runtime", runtime])
                cmd.extend(["--remote-components", "ejs:github"])

            # In debug mode, add verbose flag
            if debug:
                cmd.append("-v")
            else:
                cmd.extend(["--quiet", "--no-warnings", "--progress", "--newline"])

            cmd.extend([
                "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio",
                "--add-metadata",
                "--restrict-filenames",
                "--download-archive", str(archive_file),
                "--no-overwrites",
                "--retries", "3",
                "--fragment-retries", "3",
                "--concurrent-fragments", "2",
                "--no-playlist",  # Ensure we only download individual videos
                "-P", str(output_dir),
                "-o", "%(title)s [%(id)s].%(ext)s",
                "-a", str(batch_file),
            ])
            
            # Add cookies if available (COOKIES_FILE is a string path)
            if Path(COOKIES_FILE).exists():
                cmd.extend(["--cookies", str(Path(COOKIES_FILE))])
            
            # Open debug log if requested
            if debug:
                log_file = log_file_path or (output_dir / "yt-dlp-debug.log")
                log_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    lf = open(log_file, "a", encoding="utf-8")
                    lf.write(f"---- yt-dlp run: {datetime.now().isoformat()} ----\n")
                    lf.write("Command: " + ' '.join(cmd) + "\n")
                    lf.flush()
                except Exception as e:
                    logger.warning(f"Could not open debug log: {e}")

            # Run download
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Process output for progress tracking
            downloaded_count = 0
            for line in process.stdout:
                line = line.rstrip("\n")
                if not line:
                    continue

                # Write full output to debug log when enabled
                if lf:
                    try:
                        lf.write(line + "\n")
                        lf.flush()
                    except Exception:
                        pass

                # Check for download completion
                if any(pattern in line for pattern in [
                    "[download] 100%",
                    "has already been downloaded",
                    "has already been recorded"
                ]):
                    downloaded_count += 1
                    if progress_callback:
                        progress_callback(downloaded_count)
                        
                # Log errors
                if "[error]" in line.lower():
                    logger.error(f"yt-dlp error: {line}")

                error_match = re.search(r"ERROR:\s+\[[^\]]+\]\s+([A-Za-z0-9_-]{11}):\s+(.*)", line)
                if error_match:
                    video_id = error_match.group(1)
                    if video_id not in seen_failure_ids:
                        reason = error_match.group(2).strip()
                        url = next((url for url in video_urls if video_id in url), "")
                        failures.append(DownloadFailure(video_id=video_id, url=url, reason=reason))
                        seen_failure_ids.add(video_id)
            
            process.wait()

            # If debug, record return code and a brief directory listing
            if lf:
                try:
                    lf.write(f"Return code: {process.returncode}\n")
                    lf.write("Contents:\n")
                    for p in sorted(output_dir.iterdir()):
                        try:
                            lf.write(f"{p.name}  {p.stat().st_size}\n")
                        except Exception:
                            lf.write(f"{p.name}\n")
                    lf.write("---- end run ----\n\n")
                    lf.flush()
                except Exception:
                    pass
                finally:
                    try:
                        lf.close()
                    except Exception:
                        pass

            return DownloadResult(success=(process.returncode == 0), failures=failures)
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            if not failures:
                failures.append(DownloadFailure(video_id="", url="", reason=str(e)))
            if lf:
                try:
                    lf.write(f"Exception: {e}\n")
                    lf.flush()
                    lf.close()
                except Exception:
                    pass
            return DownloadResult(success=False, failures=failures)
        finally:
            # Clean up batch file unless debugging (keep for inspection)
            try:
                if batch_file.exists() and not debug:
                    batch_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete batch file: {e}")

class FileProcessor:
    """Handles file operations and duplicate detection"""
    
    # Common audio extensions
    AUDIO_EXTENSIONS = {".webm", ".mp3", ".m4a", ".opus", ".flac", ".wav", ".ogg"}
    
    # Common image extensions
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize a name for duplicate detection (Unicode-safe).

        This preserves letters in other scripts and strips diacritics where possible,
        falling back to removing non-word characters. Avoid returning an empty
        string when possible to prevent accidental mass-matching.
        """
        import unicodedata
        if not name:
            return ""
        # Normalize unicode and remove combining marks (diacritics)
        norm = unicodedata.normalize('NFKD', name)
        norm = ''.join(ch for ch in norm if not unicodedata.combining(ch))
        norm = norm.lower()
        # Remove any non-word characters (keeps unicode letters and digits), then drop underscores
        norm = re.sub(r'[\W_]+', '', norm, flags=re.UNICODE)
        return norm
    
    @staticmethod
    def clean_filename(filename: str) -> str:
        """Clean filename by removing duplicate markers and extra spaces"""
        cleaned = filename
        
        # Remove duplicate markers
        patterns = [
            r'\s*\(dup\)\s*$',
            r'\s*\(copy\)\s*$',
            r'\s*\(\d+\)\s*$',
            r'\s*\[dup\]\s*$',
            r'\s*\[copy\]\s*$',
            r'\s*\[\d+\]\s*$'
        ]
        
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    @staticmethod
    def extract_video_id(filename: str) -> Optional[str]:
        """Extract YouTube video ID from filename"""
        patterns = [
            r'\[([A-Za-z0-9_-]{11})\]',
            r'[?&]v=([A-Za-z0-9_-]{11})',
            r'youtu\.be/([A-Za-z0-9_-]{11})',
            r'watch\?v=([A-Za-z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1)
        
        return None
    
    @staticmethod
    def get_audio_files(folder: Path) -> List[Path]:
        """Get all audio files in a folder"""
        audio_files = []
        for ext in FileProcessor.AUDIO_EXTENSIONS:
            audio_files.extend(folder.glob(f"*{ext}"))
            audio_files.extend(folder.glob(f"*{ext.upper()}"))
        return sorted(audio_files)
    
    @staticmethod
    def get_recent_files(files: List[Path], minutes: int = 10) -> List[Path]:
        """Get files modified in the last X minutes"""
        now = time.time()
        threshold = now - (minutes * 60)
        
        recent_files = []
        for file in files:
            try:
                if file.stat().st_mtime >= threshold:
                    recent_files.append(file)
            except OSError:
                continue
        
        return recent_files

class PlaylistSyncer:
    """Enhanced playlist synchronization with better performance and error handling"""
    
    def __init__(self, playlist: PlaylistInfo, settings: Dict[str, Any]):
        self.playlist = playlist
        self.settings = settings
        self.metadata_manager = MetadataManager()
        self.ytdlp = YTDLPWrapper()
        self.file_processor = FileProcessor()
        
        # Ensure playlist folder exists
        self.playlist.folder.mkdir(parents=True, exist_ok=True)
        self.archive_file = self.playlist.folder / "downloaded.txt"
    
    @contextmanager
    def operation_context(self, operation_name: str):
        """Context manager for operations with timing and error handling"""
        start_time = time.time()
        logger.info(f"Starting {operation_name} for '{self.playlist.name}'")
        
        try:
            yield
            elapsed = time.time() - start_time
            logger.info(f"Completed {operation_name} in {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Failed {operation_name} after {elapsed:.2f}s: {e}")
            raise
    
    def get_existing_video_ids(self) -> Set[str]:
        """Get all existing video IDs from archive and filenames"""
        existing_ids = set()
        
        # From archive file
        if self.archive_file.exists():
            try:
                with open(self.archive_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Try multiple patterns to extract video ID
                        video_id = self.file_processor.extract_video_id(line)
                        if video_id:
                            existing_ids.add(video_id)
            except Exception as e:
                logger.warning(f"Failed to read archive file: {e}")
        
        # From existing filenames
        for file in self.file_processor.get_audio_files(self.playlist.folder):
            video_id = self.file_processor.extract_video_id(file.name)
            if video_id:
                existing_ids.add(video_id)
        
        return existing_ids
    
    def get_existing_song_names(self) -> Set[str]:
        """Get normalized song names from existing files"""
        existing_songs = set()
        
        for file in self.file_processor.get_audio_files(self.playlist.folder):
            try:
                # Extract video ID
                video_id = self.file_processor.extract_video_id(file.name)
                
                # Get metadata
                metadata = self.metadata_manager.get_metadata(
                    video_id or "", 
                    file.stem
                )
                
                # Format and normalize
                clean_name = FileNameFormatter.format_filename(metadata)
                normalized = self.file_processor.normalize_name(clean_name)
                existing_songs.add(normalized)
                
            except Exception as e:
                logger.warning(f"Failed to process {file.name}: {e}")
                # Fallback to filename
                clean_name = self.file_processor.clean_filename(file.stem)
                normalized = self.file_processor.normalize_name(clean_name)
                existing_songs.add(normalized)
        
        return existing_songs
    
    def get_playlist_videos(self) -> List[VideoInfo]:
        """Get all videos from playlist with metadata"""
        with self.operation_context("playlist scan"):
            print(f"\n{Colors.CYAN}📡 Scanning '{self.playlist.name}'...{Colors.RESET}")
            
            playlist_data = self.ytdlp.get_playlist_info(self.playlist.url)
            if not playlist_data:
                print(f"{Colors.RED}❌ Failed to scan playlist{Colors.RESET}")
                return []
            
            videos = []
            entries = playlist_data.get("entries", [])
            
            # Process entries in parallel for better performance
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                for entry in entries:
                    if entry and isinstance(entry, dict):
                        futures.append(
                            executor.submit(self._process_playlist_entry, entry)
                        )
                
                for future in as_completed(futures):
                    video_info = future.result()
                    if video_info:
                        videos.append(video_info)
            
            print(f"{Colors.GREEN}✓ Found {len(videos)} songs in playlist{Colors.RESET}")
            return videos
    
    def _process_playlist_entry(self, entry: Dict[str, Any]) -> Optional[VideoInfo]:
        """Process a single playlist entry"""
        try:
            video_id = entry.get("id")
            title = entry.get("title", "(No title)")
            
            if not video_id:
                return None
            
            # Get metadata
            metadata = self.metadata_manager.get_metadata(video_id, str(title))
            
            return VideoInfo(
                id=video_id,
                title=str(title),
                metadata=metadata,
                url=f"https://www.youtube.com/watch?v={video_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to process playlist entry: {e}")
            return None
    
    def get_new_videos(self, all_videos: List[VideoInfo]) -> List[VideoInfo]:
        """Identify new videos that need to be downloaded"""
        if not all_videos:
            return []
        
        with self.operation_context("duplicate check"):
            existing_ids = self.get_existing_video_ids()
            existing_songs = self.get_existing_song_names()
            
            print(f"{Colors.GRAY}✓ Already have {len(existing_ids)} songs by video ID{Colors.RESET}")
            print(f"{Colors.GRAY}✓ Already have {len(existing_songs)} unique songs by name{Colors.RESET}")
            
            new_videos = []
            duplicate_count = 0
            
            for video in all_videos:
                # Check by video ID
                if video.id in existing_ids:
                    continue
                
                # Check by song name
                clean_name = FileNameFormatter.format_filename(video.metadata)
                normalized = self.file_processor.normalize_name(clean_name)
                
                if normalized in existing_songs:
                    print(f"{Colors.YELLOW}⚠ Already have song (different video): {clean_name}{Colors.RESET}")
                    duplicate_count += 1
                    continue
                
                new_videos.append(video)
            
            if duplicate_count > 0:
                print(f"{Colors.YELLOW}⚠ Found {duplicate_count} songs already downloaded{Colors.RESET}")
            
            return new_videos
    
    def download_videos(self, videos: List[VideoInfo], debug: bool = False) -> bool:
        """Download specified videos. When debug=True, yt-dlp output will be logged."""
        if not videos:
            return True
        
        with self.operation_context("download"):
            print(f"\n{Colors.MAGENTA}⬇ Downloading {len(videos)} new song(s)...{Colors.RESET}")
            
            video_urls = [video.url for video in videos]
            progress_bar = ProgressBar(total=len(videos), title="Downloading")
            
            def update_progress(count: int):
                progress_bar.update(count)
            
            if debug:
                print(f"{Colors.YELLOW}Debug download enabled: yt-dlp logs and batch files will be kept in {self.playlist.folder}{Colors.RESET}")
                log_dir = Path("yt-dlp-logs")
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path = log_dir / f"{sanitize_folder_name(self.playlist.name)}.log"
                print(f"{Colors.GRAY}➡ yt-dlp log: {log_path.resolve()}{Colors.RESET}")
            else:
                log_path = None

            result = self.ytdlp.download_videos(
                video_urls=video_urls,
                output_dir=self.playlist.folder,
                archive_file=self.archive_file,
                progress_callback=update_progress,
                debug=debug,
                log_file_path=log_path,
            )
            success = result.success
            
            if success:
                progress_bar.complete(f"✓ Downloaded {len(videos)}/{len(videos)}")
            else:
                progress_bar.complete(f"⚠ Download issues occurred")

            if result.failures:
                self._report_failures(result.failures, log_path)
            
            return success
    
    def clean_and_organize_files(self, dry_run: bool = False) -> Tuple[int, int]:
        """Clean, rename, and remove duplicates from all files."""
        with self.operation_context("file organization"):
            print(f"\n{Colors.CYAN}🏷 Organizing files...{Colors.RESET}")
            
            audio_files = self.file_processor.get_audio_files(self.playlist.folder)
            if not audio_files:
                print(f"{Colors.YELLOW}⏭ No audio files to organize{Colors.RESET}")
                return (0, 0)
            
            # Add safety check
            if not dry_run:
                confirmation = input(f"\n{Colors.YELLOW}⚠ About to process {len(audio_files)} files. Continue? (y/N): {Colors.RESET}")
                if confirmation.lower() != 'y':
                    print(f"{Colors.YELLOW}⏭ Operation cancelled{Colors.RESET}")
                    return (0, 0)
            
            used_names = {}
            renamed_count = 0
            duplicates_removed = 0
            
            # Add debugging output
            print(f"{Colors.GRAY}Processing {len(audio_files)} files...{Colors.RESET}")
            
            progress_bar = ProgressBar(total=len(audio_files), title="Processing")
            
            for i, file in enumerate(audio_files, 1):
                try:
                    video_id = self.file_processor.extract_video_id(file.name)
                    metadata = self.metadata_manager.get_metadata(
                        video_id or "", 
                        file.stem
                    )
                    
                    clean_name = FileNameFormatter.format_filename(metadata)
                    normalized = self.file_processor.normalize_name(clean_name)
                    
                    # DEBUG: Show what's happening
                    logger.debug(f"Processing: '{file.name}' -> clean: '{clean_name}' -> normalized: '{normalized}'")
                    
                    # Check for duplicates
                    if normalized in used_names:
                        duplicates_removed += 1
                        print(f"\n{Colors.YELLOW}⚠ Duplicate detected: {clean_name} (norm: {normalized}){Colors.RESET}")
                        
                        # Show what it's a duplicate of
                        print(f"  {Colors.GRAY}Already processed file with same normalized name{Colors.RESET}")
                        
                        if dry_run:
                            print(f"  {Colors.YELLOW}Would move to quarantine: {file.name}{Colors.RESET}")
                        else:
                            if self._quarantine_file(file):
                                print(f"  {Colors.RED}🗑 Moved to quarantine: {file.name}{Colors.RESET}")
                            else:
                                # Don't delete as fallback - just skip
                                print(f"  {Colors.RED}❌ Failed to quarantine, skipping: {file.name}{Colors.RESET}")
                        
                    else:
                        used_names[normalized] = file  # Store the actual file for reference
                        
                        # Check if renaming is needed
                        current_clean = self.file_processor.clean_filename(file.stem)
                        current_normalized = self.file_processor.normalize_name(current_clean)
                        
                        if current_normalized == normalized:
                            progress_bar.update(i)
                            continue
                        
                        # Rename file
                        new_ext = file.suffix.lower()
                        if video_id:
                            new_filename = f"{clean_name} [{video_id}]{new_ext}"
                        else:
                            new_filename = f"{clean_name}{new_ext}"
                        
                        new_path = self.playlist.folder / new_filename
                        
                        if not new_path.exists() and new_path != file:
                            if dry_run:
                                print(f"  {Colors.YELLOW}Would rename: {file.name} -> {new_filename}{Colors.RESET}")
                                renamed_count += 1
                            else:
                                try:
                                    file.rename(new_path)
                                    renamed_count += 1
                                    logger.info(f"Renamed: {file.name} -> {new_filename}")
                                except Exception as rename_error:
                                    logger.error(f"Failed to rename {file}: {rename_error}")
                
                except Exception as e:
                    logger.warning(f"Failed to process {file.name}: {e}")
                    # Don't skip the file - log and continue
                    used_names[f"error_{i}"] = file
                
                progress_bar.update(i)
            
            progress_bar.complete(
                f"✓ Renamed {renamed_count} files, removed {duplicates_removed} duplicates{' (dry-run)' if dry_run else ''}"
            )
            
            # Final safety check
            remaining_files = len(self.file_processor.get_audio_files(self.playlist.folder))
            if remaining_files < (len(audio_files) - duplicates_removed):
                logger.error(f"CRITICAL: Expected {len(audio_files) - duplicates_removed} files, found {remaining_files}")
            
            return (renamed_count, duplicates_removed)
    
    def _remove_from_archive(self, video_id: str):
        """Remove video ID from archive file"""
        try:
            if not self.archive_file.exists():
                return
            
            with open(self.archive_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Filter out lines containing this video ID
            pattern = re.compile(rf".*{re.escape(video_id)}.*")
            new_lines = [line for line in lines if not pattern.search(line.strip())]
            
            if len(new_lines) < len(lines):
                with open(self.archive_file, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                    
        except Exception as e:
            logger.warning(f"Failed to update archive: {e}")

    def _quarantine_file(self, file: Path) -> bool:
        """Move a file to the playlist quarantine folder instead of deleting it."""
        try:
            quarantine_dir = self.playlist.folder / "quarantine"
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            dest = quarantine_dir / file.name
            # Handle name collisions
            if dest.exists():
                timestamp = int(time.time())
                dest = quarantine_dir / f"{file.stem}_{timestamp}{file.suffix}"
            file.replace(dest)
            return True
        except Exception as e:
            logger.warning(f"Failed to quarantine {file}: {e}")
            return False
    
    def cleanup_files(self):
        """Clean up temporary and image files"""
        with self.operation_context("cleanup"):
            self._delete_temp_files()
            self._delete_image_files()
    
    def _delete_temp_files(self):
        """Delete temporary files"""
        temp_patterns = ["batch_*.txt", "*.part", "*.ytdl", "*.tmp"]
        deleted_count = 0
        
        for pattern in temp_patterns:
            for file in self.playlist.folder.glob(pattern):
                try:
                    file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file}: {e}")
        
        if deleted_count > 0:
            print(f"{Colors.GREEN}✓ Deleted {deleted_count} temporary files{Colors.RESET}")
    
    def _delete_image_files(self):
        """Delete image files"""
        deleted_count = 0
        
        for ext in self.file_processor.IMAGE_EXTENSIONS:
            for file in self.playlist.folder.glob(f"*{ext}"):
                try:
                    file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {file}: {e}")
        
        if deleted_count > 0:
            print(f"{Colors.GREEN}✓ Deleted {deleted_count} image files{Colors.RESET}")

    def _report_failures(self, failures: List[DownloadFailure], log_path: Optional[Path]):
        """Print and persist a summary of download failures"""
        if not failures:
            return

        print(f"\n{Colors.RED}❌ {len(failures)} download(s) failed:{Colors.RESET}")
        for failure in failures:
            label = failure.video_id or failure.url or "Unknown video"
            print(f"  {Colors.RED}- {label}: {failure.reason}{Colors.RESET}")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_path = self.playlist.folder / "failed_downloads.txt"
        lines = [f"[{timestamp}] Playlist: {self.playlist.name}\n"]
        for failure in failures:
            label = failure.video_id or failure.url or "unknown"
            lines.append(f"- {label}: {failure.reason}\n")
        lines.append("\n")

        try:
            with open(report_path, "a", encoding="utf-8") as report_file:
                report_file.writelines(lines)
        except Exception as exc:
            logger.warning(f"Failed to write failure report: {exc}")

        if log_path:
            print(f"{Colors.GRAY}Check detailed log at {log_path.resolve()} for more context.{Colors.RESET}")
    
    def sync(self, mode: SyncMode = SyncMode.COMPLETE_SYNC, dry_run: bool = False, debug: bool = False) -> Dict[str, Any]:
        """
        Main synchronization method
        
        If dry_run=True, the operation will not modify files (moves/renames are simulated).
        If debug=True, yt-dlp runs will log verbose output to the playlist folder and keep batch files.
        Returns: Dictionary with sync results
        """
        results = {
            "playlist": self.playlist.name,
            "mode": mode.value,
            "new_downloads": 0,
            "renamed": 0,
            "duplicates_removed": 0,
            "success": True,
            "dry_run": dry_run
        }
        
        try:
            if mode == SyncMode.DOWNLOAD_ONLY:
                results.update(self._download_only_mode(dry_run=dry_run, debug=debug))
            elif mode == SyncMode.SYNC_ONLY:
                results.update(self._sync_only_mode(dry_run=dry_run))
            elif mode == SyncMode.AUTO_NEW:
                results.update(self._auto_new_mode(dry_run=dry_run))
            else:  # COMPLETE_SYNC
                results.update(self._complete_sync_mode(dry_run=dry_run, debug=debug))
        
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            results["success"] = False
            results["error"] = str(e)
        
        return results
    
    def _download_only_mode(self, dry_run: bool = False, debug: bool = False) -> Dict[str, Any]:
        """Download-only mode implementation"""
        print_header(f"DOWNLOAD MODE: {self.playlist.name}")
        
        videos = self.get_playlist_videos()
        new_videos = self.get_new_videos(videos)
        
        if not new_videos:
            print(f"\n{Colors.GREEN}✓ All songs already downloaded{Colors.RESET}")
            return {"new_downloads": 0, "renamed": 0, "duplicates_removed": 0}
        
        # Download new videos (no dry-run for actual download)
        success = True
        if not dry_run:
            success = self.download_videos(new_videos, debug=debug)
        else:
            print(f"{Colors.YELLOW}Dry-run: Skipping actual downloads ({len(new_videos)} videos){Colors.RESET}")
        
        # Clean only new downloads
        renamed = self._clean_new_downloads(dry_run=dry_run)
        
        # Cleanup temp files (skip actual deletions in dry-run)
        if not dry_run:
            self._delete_temp_files()
            # Also delete image files after the scan/downloads as requested
            self._delete_image_files()
        else:
            logger.debug("Dry-run: skipping temp file deletions and image deletions")
        
        # Show summary
        show_summary(
            folder=self.playlist.folder,
            total_files=len(self.file_processor.get_audio_files(self.playlist.folder)),
            new_downloads=len(new_videos) if not dry_run else 0,
            renamed=renamed
        )
        
        return {
            "new_downloads": len(new_videos) if not dry_run else 0,
            "renamed": renamed,
            "duplicates_removed": 0
        }
    
    def _sync_only_mode(self, dry_run: bool = False) -> Dict[str, Any]:
        """Sync-only mode implementation"""
        print_header(f"SYNC MODE: {self.playlist.name}")
        
        renamed, duplicates = self.clean_and_organize_files(dry_run=dry_run)
        # Cleanup: in dry-run, skip deletions
        if not dry_run:
            self.cleanup_files()
        else:
            logger.debug("Dry-run: skipping cleanup operations")
        
        show_summary(
            folder=self.playlist.folder,
            total_files=len(self.file_processor.get_audio_files(self.playlist.folder)),
            renamed=renamed,
            duplicates_removed=duplicates
        )
        
        return {
            "new_downloads": 0,
            "renamed": renamed,
            "duplicates_removed": duplicates
        }
    
    def _complete_sync_mode(self, dry_run: bool = False, debug: bool = False) -> Dict[str, Any]:
        """Complete sync mode implementation"""
        print_header(f"COMPLETE SYNC: {self.playlist.name}")
        
        videos = self.get_playlist_videos()
        new_videos = self.get_new_videos(videos)
        
        # Download new videos
        if new_videos and not dry_run:
            self.download_videos(new_videos, debug=debug)
        elif new_videos and dry_run:
            print(f"{Colors.YELLOW}Dry-run: would download {len(new_videos)} new videos{Colors.RESET}")
        
        # Organize all files
        renamed, duplicates = self.clean_and_organize_files(dry_run=dry_run)
        
        # Cleanup
        if not dry_run:
            self.cleanup_files()
        else:
            logger.debug("Dry-run: skipping cleanup operations")
        
        show_summary(
            folder=self.playlist.folder,
            total_files=len(self.file_processor.get_audio_files(self.playlist.folder)),
            new_downloads=len(new_videos) if not dry_run else 0,
            renamed=renamed,
            duplicates_removed=duplicates
        )
        
        return {
            "new_downloads": len(new_videos) if not dry_run else 0,
            "renamed": renamed,
            "duplicates_removed": duplicates
        }
    
    def _auto_new_mode(self) -> Dict[str, Any]:
        """Auto-new playlist mode implementation"""
        print_header(f"AUTO-SYNC NEW PLAYLIST: {self.playlist.name}")
        print(f"{Colors.YELLOW}🔄 New playlist detected. Running complete sync...{Colors.RESET}")
        
        return self._complete_sync_mode()
    
    def _clean_new_downloads(self, dry_run: bool = False) -> int:
        """Clean only newly downloaded files"""
        all_files = self.file_processor.get_audio_files(self.playlist.folder)
        new_files = self.file_processor.get_recent_files(all_files, minutes=10)
        
        if not new_files:
            return 0
        
        print(f"{Colors.GRAY}Found {len(new_files)} newly downloaded files to clean{Colors.RESET}")
        
        renamed_count = 0
        progress_bar = ProgressBar(total=len(new_files), title="Cleaning new files")
        
        for i, file in enumerate(new_files, 1):
            try:
                video_id = self.file_processor.extract_video_id(file.name)
                metadata = self.metadata_manager.get_metadata(
                    video_id or "", 
                    file.stem
                )
                
                clean_name = FileNameFormatter.format_filename(metadata)
                current_clean = self.file_processor.clean_filename(file.stem)
                
                # Skip if already correctly named
                if self.file_processor.normalize_name(current_clean) == \
                   self.file_processor.normalize_name(clean_name):
                    progress_bar.update(i)
                    continue
                
                # Rename file
                new_ext = file.suffix.lower()
                if video_id:
                    new_filename = f"{clean_name} [{video_id}]{new_ext}"
                else:
                    new_filename = f"{clean_name}{new_ext}"
                
                new_path = self.playlist.folder / new_filename
                
                if not new_path.exists() and new_path != file:
                    if dry_run:
                        print(f"  {Colors.YELLOW}Would rename: {file.name} -> {new_filename}{Colors.RESET}")
                        renamed_count += 1
                    else:
                        file.rename(new_path)
                        renamed_count += 1
                    
            except Exception as e:
                logger.warning(f"Failed to clean {file.name}: {e}")
            
            progress_bar.update(i)
        
        progress_bar.complete(f"✓ Cleaned {renamed_count} new files{' (dry-run)' if dry_run else ''}")
        return renamed_count

# Helper functions
def print_header(title: str):
    """Print formatted header"""
    print(f"\n{Colors.MAGENTA}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{title}{Colors.RESET}")
    print(f"{Colors.MAGENTA}{'='*60}{Colors.RESET}")

def show_summary(
    folder: Path,
    total_files: int,
    new_downloads: int = 0,
    renamed: int = 0,
    duplicates_removed: int = 0
):
    """Display sync summary"""
    print(f"\n{Colors.GREEN}{'─'*60}{Colors.RESET}")
    print(f"{Colors.BOLD}📊 Sync Summary:{Colors.RESET}")
    print(f" 📁 Folder: {Colors.CYAN}{folder}{Colors.RESET}")
    print(f" 🎵 Total tracks: {Colors.GREEN}{total_files}{Colors.RESET}")
    
    if new_downloads > 0:
        print(f" 🆕 New downloads: {Colors.GREEN}{new_downloads}{Colors.RESET}")
    if duplicates_removed > 0:
        print(f" 🗑️ Duplicates removed: {Colors.RED}{duplicates_removed}{Colors.RESET}")
    if renamed > 0:
        print(f" 🏷 Files renamed: {Colors.GREEN}{renamed}{Colors.RESET}")
    
    print(f"{Colors.GREEN}{'─'*60}{Colors.RESET}")

# Simple download function for single videos
def download_audio(video_id: str, output_folder: str) -> bool:
    """Download single audio file"""
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--add-metadata",
        "--no-overwrites",
        "--quiet",
        "-o", f"{output_folder}/%(title)s.%(ext)s",
        url
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Download failed: {e.stderr.decode()[:200]}")
        return False