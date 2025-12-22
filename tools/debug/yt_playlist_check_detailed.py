from yt_dlp import YoutubeDL
from settings import load_settings

settings = load_settings()
pl = next((p for p in settings.get('playlists', []) if p.get('name','').lower()=='breakcore'), None)
if not pl:
    print('Breakcore playlist not found')
    raise SystemExit(1)

with YoutubeDL({'quiet': True}) as ydl:
    info = ydl.extract_info(pl['url'], download=False)
    entries = info.get('entries', []) if info else []
    print('Total entries returned by yt-dlp:', len(entries))
    unavailable = []
    for i, e in enumerate(entries, 1):
        vid = e.get('id')
        title = e.get('title')
        # Detect unavailable markers
        if e.get('ie_key') == 'Youtube' and (e.get('is_live') or e.get('is_private') or e.get('is_unavailable') or 'unavailable' in str(title).lower()):
            unavailable.append((i, vid, title, e))
        # Also detect if formats list is empty
        if 'formats' in e and not e['formats']:
            unavailable.append((i, vid, title, e))

    print('Unavailable/Problematic entries found:', len(unavailable))
    for u in unavailable:
        idx, vid, title, ent = u
        print(f'{idx}. {vid} - {title} - keys: {list(ent.keys())[:10]}')

    # Also report warnings summary: check for specific ids that had format warnings earlier
    suspects = ['AMc4kuUHmhw','zidL5oEJluM','-NEGsRc3fbA','beoNy4MMHTc','dHID5Yv-Z0s']
    print('\nSuspect format warnings check:')
    for s in suspects:
        try:
            vinfo = ydl.extract_info(f'https://www.youtube.com/watch?v={s}', download=False)
            print(s, 'formats:', len(vinfo.get('formats', [])))
        except Exception as ex:
            print(s, 'error:', ex)