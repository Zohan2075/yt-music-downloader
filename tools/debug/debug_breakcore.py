import logging
from pathlib import Path
from src.core.settings import load_settings
from src.core.downloader import PlaylistInfo, PlaylistSyncer, SyncMode

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('debug')

settings = load_settings()
pl = None
for p in settings.get('playlists', []):
    if p.get('name','').lower() == 'breakcore':
        pl = p
        break

if not pl:
    print('Breakcore playlist not found in settings')
    raise SystemExit(1)

# Use an isolated temp folder under workspace
workspace = Path(__file__).parent
temp_dir = workspace / 'debug_output' / 'breakcore_test'
if temp_dir.exists():
    import shutil
    shutil.rmtree(temp_dir)

playlist_folder = temp_dir / 'Breakcore'
playlist_info = PlaylistInfo(name=pl.get('name'), url=pl.get('url'), folder=playlist_folder)

syncer = PlaylistSyncer(playlist_info, settings)

# Get videos
videos = syncer.get_playlist_videos()
print(f'Found {len(videos)} videos in Breakcore playlist')
# Identify new videos
new = syncer.get_new_videos(videos)
print(f'New videos to download: {len(new)}')
for v in new[:20]:
    print(f'- {v.id} : {v.title}')

# Attempt a test download of the new videos into the temp folder and capture success
if new:
    print('\n--- Starting test download into temporary folder ---')
    result = syncer.ytdlp.download_videos([v.url for v in new], output_dir=playlist_folder, archive_file=playlist_folder / 'archive.txt')
    print('Download function returned:', result.success)
    if result.failures:
        print('Failures detected:')
        for failure in result.failures:
            label = failure.video_id or failure.url or 'unknown'
            print(f'- {label}: {failure.reason}')
else:
    print('No new videos to download (nothing to test)')

print('Debug run complete')