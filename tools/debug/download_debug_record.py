import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from downloader import YTDLPWrapper

PLAYLIST_URL = "https://music.youtube.com/playlist?list=PLwd6ZICxmLpgPauW5gaGWVBHP0gbpvzf9"

OUT_DIR = Path('tools/debug/tmp_download')
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG = Path('tools/debug/latest_yt.log')

wrapper = YTDLPWrapper()
print('Fetching playlist info...')
info = wrapper.get_playlist_info(PLAYLIST_URL)
if not info:
    print('Failed to get playlist info')
    sys.exit(1)
entries = info.get('entries', [])
print(f'Found {len(entries)} entries')
vid = None
for e in entries:
    if isinstance(e, dict) and 'id' in e:
        vid = e['id']
        break
if not vid:
    print('No video ids found')
    sys.exit(1)

url = f"https://www.youtube.com/watch?v={vid}"
print('Testing download of', url)

cmd = [
    "yt-dlp",
    "-v",
    "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio",
    "--add-metadata",
    "--restrict-filenames",
    "--no-overwrites",
    "--download-archive", str(OUT_DIR / 'downloaded.txt'),
    "--no-playlist",
    "-P", str(OUT_DIR),
    "-o", "%(title)s [%(id)s].%(ext)s",
    url,
]

import subprocess
with open(LOG, 'w', encoding='utf-8') as lf:
    lf.write('Running: ' + ' '.join(cmd) + '\n')
    print('Running:', ' '.join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        lf.write(line)
    proc.wait()
    lf.write('\nReturn code: ' + str(proc.returncode) + '\n')

print('Return code:', proc.returncode)
print('Log path:', LOG)
print('Out dir listing:', list(OUT_DIR.iterdir()))
