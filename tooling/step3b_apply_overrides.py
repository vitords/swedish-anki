#!/usr/bin/env python3
"""
Step 3b: Apply a small hand-curated override list on top of content/kelly_final.csv.

Automated sense-picking (Kaikki etymology ordering + Folkets first-match) gets
the vast majority of words right, but a handful of extremely high-frequency
function words (vara, om, av, for, till, ...) landed on a rarer homonym/sense.
Given the whole point of the leveled rollout is to nail the ~1,400 A1 words
first, these are worth a direct, human-verified fix rather than more automated
heuristics chasing a handful of cases.

Reads content/manual_overrides.csv (word,pos,word_override,translation_override,note)
and rewrites content/kelly_final.csv in place, clearing the review flag for any
row it touches.

When word_override swaps the displayed headword for a different surface form
(e.g. Kelly's archaic verb lemma "skola" -> the actually-used present tense
"ska"), the row's audio/IPA were resolved for the OLD word and now mismatch
what's shown on the card (playing "skola"'s pronunciation under a card that
displays "ska"). So for any such row, re-resolve audio+IPA from Kaikki for
the NEW word too, downloading its own Wikimedia clip if one exists.
"""
import csv
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from step2_kaikki_enrich import KAIKKI_JSONL, POS_TO_KAIKKI, pick_entry, pick_audio_ipa  # noqa: E402

FINAL_CSV = Path("content/kelly_final.csv")
OVERRIDES_CSV = Path("content/manual_overrides.csv")
WIKIMEDIA_AUDIO_DIR = Path("data/audio/wikimedia_kaikki")
HEADERS = {"User-Agent": "SwedishAnkiDeckBuilder/1.0 (personal language-learning project; contact vitords.42@gmail.com) Python-urllib"}


def resolve_override_word_audio_ipa(override_words):
    """Stream Kaikki once for the (small) set of override target words and
    return {word: (audio_url, ipa)}."""
    found = {}
    if not override_words:
        return found
    with open(KAIKKI_JSONL, "rt", encoding="utf-8") as f:
        for line in f:
            if '"word": "' not in line:
                continue
            import json
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            w = d.get("word")
            if w in override_words and w not in found:
                found.setdefault(w, []).append(d)
    resolved = {}
    for w, entries in found.items():
        entry = pick_entry(entries, "verb") or pick_entry(entries, None)
        if entry:
            resolved[w] = pick_audio_ipa(entry)
    return resolved


def main():
    overrides = {}
    with open(OVERRIDES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            overrides[(row["word"], row["pos"])] = row

    override_words = {ov["word_override"] for ov in overrides.values() if ov["word_override"]}
    audio_ipa = resolve_override_word_audio_ipa(override_words)

    rows = list(csv.DictReader(open(FINAL_CSV, encoding="utf-8")))
    fieldnames = list(rows[0].keys())
    applied_keys = set()

    WIKIMEDIA_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for row in rows:
        key = (row["word"], row["pos"])
        if key not in overrides:
            continue
        ov = overrides[key]
        if ov["word_override"]:
            new_word = ov["word_override"]
            row["word"] = new_word
            audio_url, ipa = audio_ipa.get(new_word, ("", ""))
            if ipa:
                row["ipa"] = ipa
            if audio_url:
                dest = WIKIMEDIA_AUDIO_DIR / f"{new_word}.mp3"
                if not dest.exists():
                    try:
                        req = urllib.request.Request(audio_url, headers=HEADERS)
                        with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as out_f:
                            out_f.write(resp.read())
                        time.sleep(1.0)
                    except Exception as e:
                        print(f"WARNING: failed to download override audio for {new_word}: {e}")
                        dest = None
                if dest and dest.exists():
                    row["audio_path"] = str(dest)
                    row["audio_source"] = "wikimedia"
                    row["audio_credit_url"] = audio_url
        if ov.get("clear_example") == "yes":
            row["example_sv"] = ""
            row["example_en"] = ""
        row["translation"] = ov["translation_override"]
        row["translation_source"] = "manual"
        row["needs_review"] = "no"
        row["review_reason"] = ""
        applied_keys.add(key)

    with open(FINAL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Applied {len(applied_keys)}/{len(overrides)} overrides to {FINAL_CSV}")
    missed = set(overrides) - applied_keys
    if missed:
        print("WARNING: these overrides did not match any row:", missed)


if __name__ == "__main__":
    main()
