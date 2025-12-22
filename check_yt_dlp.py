import importlib
try:
    m = importlib.import_module('yt_dlp')
    print('yt_dlp module import OK, version:', getattr(m, '__version__', 'unknown'))
except Exception as e:
    print('yt_dlp import failed:', e)

import shutil
from pathlib import Path
print('where yt-dlp executable (PATH search):', shutil.which('yt-dlp'))
print('where python is:', Path().resolve())
