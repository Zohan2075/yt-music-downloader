import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from downloader import YTDLPWrapper

PLAYLIST_URL = "https://music.youtube.com/playlist?list=PLwd6ZICxmLpgPauW5gaGWVBHP0gbpvzf9"

def main():
    wrapper = YTDLPWrapper()
    print("Fetching playlist info...")
    info = wrapper.get_playlist_info(PLAYLIST_URL)
    if not info:
        print("Failed to get playlist info")
        return
    entries = info.get('entries', [])
    print(f"Found {len(entries)} entries (flat)")
    # Pick first valid id
    vid = None
    for e in entries:
        if isinstance(e, dict) and 'id' in e:
            vid = e['id']
            break
    if not vid:
        print("No video ids found")
        return

    url = f"https://www.youtube.com/watch?v={vid}"
    print(f"Testing download of: {url}")

    with tempfile.TemporaryDirectory() as td:
        tdpath = Path(td)
        archive = tdpath / 'downloaded.txt'
        log = tdpath / 'ytlog.txt'
        print(f"Temp dir: {td}")
        # Build a command similar to YTDLPWrapper but verbosely
        cmd = [
            "yt-dlp",
            "-v",
            "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio",
            "--add-metadata",
            "--restrict-filenames",
            "--no-overwrites",
            "--download-archive", str(archive),
            "--no-playlist",
            "-P", str(tdpath),
            "-o", "%(title)s [%(id)s].%(ext)s",
            url,
        ]
        import subprocess
        print("Running:", ' '.join(cmd))
        with open(log, 'w', encoding='utf-8') as lf:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                lf.write(line)
                lf.flush()
                print(line, end='')
            proc.wait()
        print(f"Return code: {proc.returncode}")
        print("Log written to:", log)
        print("Temp dir contents:")
        print(list(tdpath.iterdir()))

if __name__ == '__main__':
    main()
