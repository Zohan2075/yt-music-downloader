import subprocess
from pathlib import Path
suspects = ['AMc4kuUHmhw','zidL5oEJluM','-NEGsRc3fbA','beoNy4MMHTc','dHID5Yv-Z0s']
output_dir = Path('debug_output') / 'batch_test'
output_dir.mkdir(parents=True, exist_ok=True)
archive_file = output_dir / 'archive.txt'

for vid in suspects:
    url = f'https://www.youtube.com/watch?v={vid}'
    cmd = [
        'yt-dlp',
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
    print('\n--- Running', vid, '---')
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        print('rc=', res.returncode)
        print('stdout:', (res.stdout or '').splitlines()[-6:])
        print('stderr:', (res.stderr or '').splitlines()[-6:])
    except Exception as e:
        print('Exception during download:', e)
        continue