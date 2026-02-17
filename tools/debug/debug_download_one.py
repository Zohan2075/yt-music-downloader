import subprocess
from pathlib import Path

video_id = 'AMc4kuUHmhw'
url = f'https://www.youtube.com/watch?v={video_id}'
output_dir = Path('debug_output') / 'breakcore_single'
output_dir.mkdir(parents=True, exist_ok=True)
archive_file = output_dir / 'archive.txt'

cmd = [
    'python',
    '-m',
    'yt_dlp',
    '--no-warnings',
    '-f', 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio',
    '--add-metadata',
    '--restrict-filenames',
    '--download-archive', str(archive_file),
    '--no-overwrites',
    '--retries', '3',
    '--fragment-retries', '3',
    '--concurrent-fragments', '2',
    '--no-playlist',
    '-P', str(output_dir),
    '-o', '%(title)s [%(id)s].%(ext)s',
    url
]

print('Running command:', ' '.join(cmd))
try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print('returncode =', res.returncode)
    print('--- stdout ---')
    print(res.stdout[:8000])
    print('--- stderr ---')
    print(res.stderr[:8000])
except Exception as e:
    print('Exception running yt-dlp:', e)