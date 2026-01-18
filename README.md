# YouTube Playlist Manager

Terminal-first playlist synchroniser that mirrors YouTube and YouTube Music playlists into a local audio library you control. With safety: it only downloads what is missing, renames files consistently, quarantines removals, and keeps verbose audit logs for every action.

---

## ✨ Highlights

This tool helps you keep your local music folders in sync with your YouTube / YouTube Music playlists.

What it does for you:

- ⬇️ Downloads new songs from your playlists into a folder you choose.
- 🧹 Keeps your files tidy by renaming new downloads into a consistent format.
- ⚡ Skips songs you already have on disk (so rerunning sync is fast).
- 🧪 If a song disappears from the online playlist, it does **not** instantly delete it — it moves it to a `quarantine/` folder inside that playlist so you can review.
- 🧾 Writes logs so you can see what happened if something fails.

Menu options:

- 🔄 Option 1 (Sync): “Update my playlist folders to match YouTube”.
- 🗂️ Option 2 (Manage): “Pick where playlists are stored, add/remove playlists, or register existing folders”.
- 🎵 Option 3 (Single download): “Download one link into a folder”.

Safety basics:

- 🛑 If the playlist scan returns **zero** items (for example: wrong URL, blocked request, cookies needed), sync aborts and will **not** quarantine/remove anything.
- 🧩 If something is listed as downloaded in `downloaded.txt` but the file is missing locally, the tool can re-download it automatically.

---

## ✅ Intended Use (Rights / Permission)

This project is designed for managing downloads of content you are authorised to download — for example:

- Your own uploads (your own channel / playlists of your uploads)
- Content with explicit permission from the rights holder
- Content under permissive licences (for example Creative Commons, where applicable)

It is not intended to be a general-purpose “download any song from YouTube” tool.

Notes:

- YouTube’s Terms of Service and copyright law are separate concerns.
- Downloading copyrighted music you don’t have rights/permission for may be illegal and/or a ToS violation depending on your jurisdiction.

---

## ✅ Requirements

- Python 3.9 or newer (the repo currently uses a `.venv` on Windows).
- yt-dlp available either as the Python package (`pip install yt-dlp`) or the standalone binary in PATH.
- FFmpeg on PATH is strongly recommended so yt-dlp can remux/tag audio correctly.
- Optional: a valid cookies.txt export in the project root for age-restricted or private content.
- Tkinter (bundled with the standard CPython installer) for the folder picker.

---

## 🧰 Installation & Setup

1. Ensure Python, yt-dlp, and FFmpeg are installed and reachable from the command line.
2. (Optional) Create and activate a virtual environment.
3. Install yt-dlp into that environment if you prefer the Python module:
   ```bash
   pip install yt-dlp
   ```
4. Place an exported YouTube cookies file at cookies.txt if you need authenticated downloads.

The first run will create settings.json, metadata_cache.json, and other artefacts automatically.

---

## ▶️ Running The Tool

Execute the entry point from the repository root:

```bash
python main.py
```

On Windows with the checked-in virtual environment, you can run:

```powershell
& ".\.venv\Scripts\python.exe" .\main.py
```

Or activate the venv first:

```powershell
.\.venv\Scripts\Activate.ps1
python .\main.py
```

You will see a colourised menu with three primary options:

1. Sync and Auto-download/deletion - downloads newly published tracks, cleans metadata, removes files no longer in the source playlist (by moving them to a per-playlist quarantine/), and writes a concise summary.
2. Add or Remove Playlist - opens an interactive setup flow where you can change the base download folder and manage playlist entries stored in settings.json.
   - Adding a playlist requires a real playlist URL (must contain `list=`) and uses a folder picker to choose where that playlist is stored.
   - You can also import/register untracked subfolders found under the base folder.
3. Download a single song/video - fetches an individual URL to a chosen folder with the rich progress bar. Playlist URLs are rejected so the sync path remains authoritative.

Press ESC at most prompts to back out safely.

---

## ⚙️ Configuration Model

- settings.json holds the global download directory and playlist list. Each playlist tracks a display name, URL, derived playlist ID, and an optional `folder` name (subfolder under the base folder).
- downloaded.txt in each playlist folder is a yt-dlp archive that prevents redownloading the same video ID. The tool can automatically recover from stale archive entries if files are missing locally.
- .quarantined_playlists/ inside the base directory stores removed folders so data can be recovered later.
- metadata_cache.json caches parsed titles per video ID to avoid re-querying yt-dlp.
- sync_state.json (repo root) keeps a lightweight record of fetched IDs across sessions.
- Debug runs drop yt-dlp command dumps, batch URL manifests, and failure reports (for example failed_downloads.txt) next to each playlist.

All files are JSON and safe to edit manually if needed; the tool will normalise URLs, deduplicate entries, and persist changes on exit.

---

## 🔁 Sync Pipeline Details

- Fetch playlist metadata using yt-dlp with retry logic and optional per-run verbose logging.
- Compare remote video IDs with what is actually on disk (filename heuristics) and download missing entries.
   - If an ID exists in downloaded.txt but the audio file is missing locally, the tool will re-download it by pruning the stale archive entry before the run.
- Post-process fresh audio files immediately: metadata lookup, consistent filename formatting, duplicate pruning, and junk (image/log) cleanup.
- Detect tracks that disappeared from the online playlist and move them into quarantine/ so users can review before permanent deletion.
- Produce colourised terminal summaries plus persistent plain-text logs for every failure.

Safety notes:
- If a playlist scan returns zero entries (common when a non-playlist URL was pasted or yt-dlp is blocked), the sync aborts and will not quarantine/remove anything.

---

## 🎧 Single Download Mode

The standalone downloader accepts any non-playlist YouTube/YouTube Music URL, offers a destination picker, and streams progress via the animated status bar. When the Python module variant of yt-dlp is available it keeps everything in-process; otherwise it falls back to the CLI but still parses progress into the same UI.

---

## 🛠️ Debugging & Maintenance

- Enable debug logging when prompted during sync to keep per-playlist yt-dlp command transcripts and batch files for audit.
- Inspect yt-dlp-logs/ for per-playlist download logs.
- Inspect debug_output/ and scripts in tools/debug/ for focused smoke tests, batch checks, or metadata verification workflows built during development.
- If downloads start failing with HTTP 403 responses, refresh cookies.txt from your browser session and retry.
- For stubborn playlists, delete the corresponding downloaded.txt archive to force a clean re-fetch (existing files will still be renamed and deduplicated).

---

## 🧱 Project Layout

- main.py is the entry point.
- src/core contains the downloader, settings manager, metadata handling, progress UI, and utilities.
- src/flows contains the interactive menu flows.
- src/ui contains terminal colours and banner helpers.
- tools/debug contains helper scripts for local diagnostics.