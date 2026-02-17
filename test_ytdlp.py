#!/usr/bin/env python3
import subprocess
import json

url = "https://youtube.com/playlist?list=PLwd6ZICxmLpidoZ1IsoG1l0m5PYDBQF7N"

cmd = [
    "python",
    "-m",
    "yt_dlp",
    "--flat-playlist",
    "--dump-single-json",
    "--quiet",
    "--no-warnings",
    url
]

print(f"Running: {' '.join(cmd)}")
print(f"Testing URL: {url}\n")

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=30
)

print(f"Return code: {result.returncode}")
print(f"\nstdout length: {len(result.stdout)}")
print(f"stderr length: {len(result.stderr)}")

if result.stderr:
    print(f"\nstderr output:\n{result.stderr}")

if result.stdout:
    print(f"\nFirst 500 chars of stdout:\n{result.stdout[:500]}")
    try:
        data = json.loads(result.stdout)
        print(f"Successfully parsed JSON")
        print(f"Keys: {list(data.keys())}")
        if 'entries' in data:
            print(f"Number of entries: {len(data['entries'])}")
    except Exception as e:
        print(f"Failed to parse JSON: {e}")
else:
    print("No stdout output")
