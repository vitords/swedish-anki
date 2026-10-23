#!/usr/bin/env python3
"""
Step 3c: Download the small number of Wikimedia Commons audio files (via Kaikki
URLs) needed to fill audio gaps not covered by the local Lexin/Bildetema
recordings, for a given CEFR level (default A1). Public CC-licensed audio,
already identified per-word in build/audio_to_download.csv.

Downloaded files go to data/audio/wikimedia_kaikki/<word>.mp3 and
content/kelly_final.csv is updated in place with the resulting local path.
"""
import csv
import sys
import time
import urllib.request
from pathlib import Path

AUDIO_DOWNLOAD_CSV = Path("build/audio_to_download.csv")
FINAL_CSV = Path("content/kelly_final.csv")
OUT_DIR = Path("data/audio/wikimedia_kaikki")

HEADERS = {"User-Agent": "SwedishAnkiDeckBuilder/1.0 (personal language-learning project; contact vitords.42@gmail.com) Python-urllib"}


def download(url, dest):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def main():
    level = sys.argv[1] if len(sys.argv) > 1 else "A1"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    to_download = [r for r in csv.DictReader(open(AUDIO_DOWNLOAD_CSV, encoding="utf-8")) if r["cefr"] == level]
    print(f"Downloading audio for {len(to_download)} {level} words...")

    resolved = {}
    source_urls = {}
    for i, row in enumerate(to_download, 1):
        dest = OUT_DIR / f"{row['word']}.mp3"
        source_urls[row["word"]] = row["url"]
        if dest.exists():
            resolved[row["word"]] = str(dest)
            continue
        try:
            download(row["url"], dest)
            resolved[row["word"]] = str(dest)
            print(f"  [{i}/{len(to_download)}] OK: {row['word']}")
        except Exception as e:
            print(f"  [{i}/{len(to_download)}] FAILED: {row['word']} ({e})")
        time.sleep(2.0)

    rows = list(csv.DictReader(open(FINAL_CSV, encoding="utf-8")))
    fieldnames = list(rows[0].keys())
    updated = 0
    for row in rows:
        if row["word"] in resolved and not row["audio_path"]:
            row["audio_path"] = resolved[row["word"]]
            row["audio_source"] = "wikimedia"
            row["audio_credit_url"] = source_urls.get(row["word"], "")
            if "no_audio" in row["review_reason"]:
                reasons = [r for r in row["review_reason"].split("|") if r != "no_audio"]
                row["review_reason"] = "|".join(reasons)
                row["needs_review"] = "yes" if reasons else "no"
            updated += 1

    with open(FINAL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Downloaded {len(resolved)} files, updated {updated} rows in {FINAL_CSV}")


if __name__ == "__main__":
    main()
