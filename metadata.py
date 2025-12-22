"""
Metadata extraction and formatting
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List

METADATA_CACHE_FILE = "metadata_cache.json"


class MetadataManager:
    """Manages metadata extraction and caching"""
    
    def __init__(self):
        self.cache_file = Path(METADATA_CACHE_FILE)
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, str]]:
        """Load metadata cache from file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        """Save metadata cache to file"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠ Could not save metadata cache: {e}")

    def get_metadata(self, video_id: str, video_title: str) -> Dict[str, str]:
        """Get clean metadata for a song"""
        if video_id and video_id in self.cache:
            return self.cache[video_id]
        metadata = self._extract_metadata(video_id, video_title)
        if video_id:
            self.cache[video_id] = metadata
            self._save_cache()
        return metadata

    def _extract_metadata(self, video_id: str, video_title: str) -> Dict[str, str]:
        """Extract clean metadata from song title and YouTube info"""
        clean_title = self._clean_video_title(video_title)
        # Try yt-dlp metadata if we have an id
        if video_id:
            try:
                result = subprocess.run(
                    ["yt-dlp", "--dump-json", "--no-warnings", f"https://www.youtube.com/watch?v={video_id}"],
                    capture_output=True,
                    text=True,
                    timeout=12
                )
                if result.returncode == 0 and result.stdout:
                    try:
                        info = json.loads(result.stdout)
                        artist = info.get("artist") or info.get("uploader") or ""
                        track = info.get("track") or info.get("title") or clean_title
                        album = info.get("album") or ""
                        if artist and track:
                            return {
                                "artist": self._clean_string(artist),
                                "track": self._clean_string(track),
                                "album": self._clean_string(album) if album else "",
                                "original_title": clean_title
                            }
                    except Exception:
                        pass
            except Exception:
                pass

        # Fallback: parse from the cleaned title
        parsed = self._parse_music_title(clean_title)
        return {
            "artist": parsed["artist"] or "Unknown Artist",
            "track": parsed["track"] or clean_title,
            "album": parsed.get("album", ""),
            "original_title": clean_title
        }

    def _clean_video_title(self, title: str) -> str:
        """Clean YouTube song title but preserve meaningful parentheses (like album)"""
        patterns_to_remove = [
            r"\(Official Video\)", r"\(Official Music Video\)", r"\(Official Audio\)",
            r"\(Lyric Video\)", r"\(Visualizer\)", r"\(Audio\)", r"\(Music Video\)",
            r"\[.*?]",  # remove bracketed tags
        ]
        clean = title
        for pattern in patterns_to_remove:
            clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\b(official video|official audio|lyrics|lyric video)\b", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\b(HD|4K|1080p|720p|\d{3,4}p)\b", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\b(ft\.|feat\.|featuring)\b.*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s+', ' ', clean)
        clean = re.sub(r'\s*[|–—]\s*', ' - ', clean)
        clean = clean.strip(' -')
        return clean.strip()

    def _parse_music_title(self, title: str) -> Dict[str, str]:
        """Parse music title into artist, track, and album"""
        patterns = [
            (r"^(.*?)\s*[-–—]\s*(.*?)\s*(?:\((.*?)\))?$", "dash"),
            (r'^(.*?)\s*["\'](.*?)["\'](?:\s*\((.*?)\))?$', "quote"),
            (r"^(.*?)\s+by\s+(.*?)(?:\s*\((.*?)\))?$", "by"),
        ]
        for pattern, kind in patterns:
            m = re.match(pattern, title, re.IGNORECASE)
            if m:
                if kind == "dash":
                    artist = self._clean_string(m.group(1))
                    track = self._clean_string(m.group(2))
                    album = self._clean_string(m.group(3)) if m.group(3) else ""
                    return {"artist": artist, "track": track, "album": album}
                elif kind == "quote":
                    artist = self._clean_string(m.group(1))
                    track = self._clean_string(m.group(2))
                    album = self._clean_string(m.group(3)) if m.group(3) else ""
                    return {"artist": artist, "track": track, "album": album}
                elif kind == "by":
                    part1 = self._clean_string(m.group(1))
                    part2 = self._clean_string(m.group(2))
                    album = self._clean_string(m.group(3)) if m.group(3) else ""
                    return {"artist": part2, "track": part1, "album": album}

        if " - " in title:
            parts = title.split(" - ", 1)
            if len(parts) == 2 and len(parts[1]) < 200:
                return {"artist": self._clean_string(parts[0]), "track": self._clean_string(parts[1]), "album": ""}
        return {"artist": "", "track": self._clean_string(title), "album": ""}

    def _clean_string(self, text: str) -> str:
        """Clean a string for use in filenames"""
        if not text:
            return ""
        text = re.sub(r'[<>:"/\\|?*]', '_', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.strip(' ._-')
        if len(text) > 100:
            text = text[:97] + "..."
        return text


class FileNameFormatter:
    """Formats filenames from metadata"""
    
    @staticmethod
    def format_filename(metadata: Dict[str, str]) -> str:
        """Format filename from metadata"""
        artist = metadata.get("artist", "Unknown Artist")
        track = metadata.get("track", "Unknown Track")
        album = metadata.get("album", "")
        artist_clean = FileNameFormatter._clean_component(artist)
        track_clean = FileNameFormatter._clean_component(track)
        album_clean = FileNameFormatter._clean_component(album) if album else ""
        if album_clean:
            return f"{artist_clean} - {track_clean} ({album_clean})"
        else:
            return f"{artist_clean} - {track_clean}"

    @staticmethod
    def _clean_component(text: str) -> str:
        """Clean a component for use in filenames"""
        if not text:
            return ""
        # Remove ALL duplicate markers (multiple passes to catch nested ones)
        original = text
        while True:
            # Remove (dup), (copy), (1), (2), etc.
            new_text = re.sub(r'\s*\(dup\)\s*$', '', text, flags=re.IGNORECASE)
            new_text = re.sub(r'\s*\(copy\)\s*$', '', new_text, flags=re.IGNORECASE)
            new_text = re.sub(r'\s*\(\d+\)\s*$', '', new_text)
            new_text = re.sub(r'\s*\(dup\)\s*', ' ', new_text, flags=re.IGNORECASE)
            new_text = re.sub(r'\s*\(copy\)\s*', ' ', new_text, flags=re.IGNORECASE)
            new_text = re.sub(r'\s*\(\d+\)\s*', ' ', new_text)
            
            # Remove multiple spaces
            new_text = re.sub(r'\s+', ' ', new_text)
            new_text = new_text.strip()
            
            if new_text == text:
                break
            text = new_text
        
        # If we removed everything, use original
        if not text:
            text = original
        
        # Clean file system unsafe characters
        text = re.sub(r'[<>:"/\\|?*]', '_', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.strip(' .')
        return text