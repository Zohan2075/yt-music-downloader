Debug utilities for Playlist retriever

This folder contains small helper scripts useful when diagnosing playlist or yt-dlp issues.

Files:
- debug_breakcore.py — scans the 'Breakcore' playlist and lists new videos, optionally attempts test downloads into a `debug_output/` folder.
- debug_download_one.py — attempts a single video download (configurable `video_id` at top).
- debug_batch_download.py — runs a small batch of sample downloads and prints return codes / stdout / stderr for each.
- yt_info_check.py — extracts playlist entries and checks per-video extract_info calls for failures.
- yt_playlist_check_detailed.py — detailed playlist inspection for unavailable/problematic entries.
- yt_video_check_ids.py — quick format count check for a list of suspect ids.

Usage:
- Run any script with your normal python interpreter from the project root, e.g.: `python tools/debug/debug_download_one.py`
- The scripts write to `tools/debug/debug_output/` by default; delete that directory when done.

Safety:
- Scripts are read-only except for writing to the `debug_output/` temporary folders and an `archive.txt` file for testing downloads.
- Keep them for future debugging or move them to a separate archive if you prefer a cleaner workspace.
