#!/usr/bin/env python3
"""
Fetch the raw upstream dumps the pipeline needs, into a local, gitignored
`sources/` directory. These are large (hundreds of MB to a few GB combined)
and are never committed to this repo -- see ATTRIBUTION.md for why each one
is here and what license it carries.

This covers the 3 straightforward, stable bulk downloads. It does NOT cover
Lexin audio scraping, which the pipeline still expects as a pre-existing
local cache under data/audio/ -- turning that into real, runnable tooling is
a known gap, tracked in CONTRIBUTING.md.

Usage: python3 tooling/fetch_sources.py
"""
import gzip
import shutil
import urllib.request
from pathlib import Path

SOURCES_DIR = Path("sources")
HEADERS = {"User-Agent": "SwedishAnkiDeckBuilder/1.0 (personal language-learning project)"}

# Kaikki's bulk Swedish-language dump (the whole site's download page is
# https://kaikki.org/dictionary/Swedish/ -- the file below is linked from
# its "Download raw JSONL data" section).
DOWNLOADS = {
    "kaikki_swedish_raw.jsonl.gz": "https://kaikki.org/dictionary/Swedish/kaikki.org-dictionary-Swedish.jsonl.gz",
    "folkets_sv_en_public.xdxf": "https://folkets-lexikon.csc.kth.se/folkets/folkets_sv_en_public.xdxf",
}

# The Kelly list is gated behind a license click-through on Språkbanken's
# site rather than a stable direct-download URL, so it can't be fetched
# automatically -- download it by hand from the resource page and place the
# XML at sources/kelly_source.xml.
MANUAL_DOWNLOADS = {
    "kelly_source.xml": "https://spraakbanken.gu.se/en/resources/kelly",
}


def download(url, dest):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def main():
    SOURCES_DIR.mkdir(exist_ok=True)
    for filename, url in DOWNLOADS.items():
        dest = SOURCES_DIR / filename
        if dest.exists():
            print(f"  already have {filename}")
            continue
        print(f"  downloading {filename} ...")
        try:
            download(url, dest)
            print(f"  OK: {filename}")
        except Exception as e:
            print(f"  FAILED: {filename} ({e})")

    print()
    for filename, page_url in MANUAL_DOWNLOADS.items():
        dest = SOURCES_DIR / filename
        if dest.exists():
            print(f"  already have {filename}")
            continue
        print(f"  MANUAL STEP NEEDED: download the Kelly list XML from {page_url}")
        print(f"    and save it as {dest}")


if __name__ == "__main__":
    main()
