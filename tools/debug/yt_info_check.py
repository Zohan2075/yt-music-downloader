from yt_dlp import YoutubeDL
from settings import load_settings
from downloader import PlaylistInfo, PlaylistSyncer

settings = load_settings()
pl = next((p for p in settings.get('playlists', []) if p.get('name','').lower()=='breakcore'), None)
if not pl:
    print('Breakcore playlist not found')
    raise SystemExit(1)

playlist_info = PlaylistInfo(name=pl['name'], url=pl['url'], folder=None)
ytdlp_opts = {'quiet': True, 'skip_download': True}

with YoutubeDL(ytdlp_opts) as ydl:
    data = ydl.extract_info(playlist_info.url, download=False)
    entries = data.get('entries', [])
    print(f'Found {len(entries)} entries, checking each individually...')
    failures = []
    for e in entries:
        vid = e.get('id')
        url = f'https://www.youtube.com/watch?v={vid}'
        try:
            info = ydl.extract_info(url, download=False)
            print(f'OK: {vid} - {info.get("title")[:60]}')
        except Exception as ex:
            print(f'ERR: {vid} - {ex}')
            failures.append((vid, str(ex)))

    print('\nFailures count:', len(failures))
    for f in failures[:50]:
        print(f)