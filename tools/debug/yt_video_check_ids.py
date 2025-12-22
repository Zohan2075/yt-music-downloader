from yt_dlp import YoutubeDL

suspects = ['AMc4kuUHmhw','zidL5oEJluM','-NEGsRc3fbA','beoNy4MMHTc','dHID5Yv-Z0s','OBPV0lsorwU']

with YoutubeDL({'quiet': True}) as ydl:
    for s in suspects:
        try:
            info = ydl.extract_info(f'https://www.youtube.com/watch?v={s}', download=False)
            fmts = info.get('formats') or []
            print(s, 'title:', info.get('title','(no title)'), 'formats:', len(fmts))
        except Exception as e:
            print(s, 'ERROR:', e)