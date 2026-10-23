#!/usr/bin/env python3
"""
Step 4: Build the Anki deck (genanki) for one CEFR level.

One note type, three card templates (per the approved plan):
  1. Word card       -- recognition: word + audio + badges -> translation + forms + IPA
  2. Cloze-sentence   -- context recall: example sentence with the word blanked,
                         typed-answer check -> full sentence + English translation
                         (only generated when we found a clean word-span to blank)
  3. Production card -- English -> typed Swedish word -> word + audio + forms

Design choices (see docs/plan): native Anki `[sound:...]` autoplay (not JS),
one small neutral+accent CSS palette with explicit light/dark support, no giant
hidden data-dump field -- CEFR/POS/gender become tags and one deck per level.

Usage: python3 step4_build_deck.py A1 [--limit N]
"""
import csv
import os
import re
import shutil
import sys
from pathlib import Path

import genanki

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from style.templates import FIELDS, TEMPLATES, CSS  # noqa: E402

FINAL_CSV = Path("content/kelly_final.csv")
DECKS_DIR = Path("decks")
MEDIA_STAGING_DIR = Path("build/media")

# Stable IDs so re-generating/re-importing a level updates existing notes/deck
# rather than creating duplicates. One offset per CEFR level.
MODEL_ID = 1979231600
DECK_ID_BASE = 1979300000
CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

GENDER_LABEL = {"en": "en", "ett": "ett"}


def word_display(word, pos, gender):
    """Nouns show their article inline ("en katt", "ett hus") on every card
    face, not just as a separate badge on the Word card -- reinforces the
    gender/article pairing everywhere, including the Cloze/Production back
    where the badge doesn't appear. The bare `Word` field (used for the
    typed-answer check and cloze/example matching) is left untouched, so this
    is purely a display change -- typing "katt" still counts as correct."""
    if pos == "noun" and gender in GENDER_LABEL:
        return f"{GENDER_LABEL[gender]} {word}"
    return word


def find_cloze_span(word, forms_str, example_sv):
    """Find the surface form of `word` inside `example_sv` (lemma or any known
    inflected form from the `forms` string), case-insensitively. Returns the
    matched candidate's OWN casing (not the sentence's -- a sentence-initial
    match like "Igar regnade det" would otherwise return "Igar" capitalized,
    which then becomes the typed-answer target and marks a learner's correctly
    lowercase "igar" as wrong) and its (start, end) span in example_sv, or
    (None, None)."""
    candidates = [word] + [f.strip() for f in re.split(r"[•·]", forms_str) if f.strip()]

    # Pass 1: exact whole-word/whole-phrase match. Multi-word candidates
    # (many Kelly headwords are phrases, e.g. "i alla fall", "till exempel")
    # join on \s+ rather than being skipped, so exact whitespace doesn't matter.
    for cand in candidates:
        if not cand:
            continue
        pattern = r"\s+".join(re.escape(part) for part in cand.split())
        m = re.search(r"\b" + pattern + r"\b", example_sv, re.IGNORECASE)
        if m:
            return cand, m.span()

    # Pass 2: compound-word fallback. Swedish compounds are head-final
    # ("supertrevlig" = super+trevlig), so the lemma often appears as a
    # trailing substring of a larger merged word ("Hon ar supertrevlig!").
    # Require a boundary only on the trailing side; skip short candidates
    # to avoid matching a short lemma inside an unrelated longer word.
    for cand in candidates:
        if not cand or " " in cand or len(cand) < 4:
            continue
        m = re.search(re.escape(cand) + r"\b", example_sv, re.IGNORECASE)
        if m:
            return cand, m.span()

    return None, None


def blank_and_highlight(word, forms_str, example_sv):
    """Blank/highlight every occurrence of the matched surface form, not just
    the first -- a word that recurs in the sentence (e.g. "hjalp ... om
    hjalp") would otherwise still leak the answer in the supposedly-blanked
    text. Returns (blanked, highlighted, answer) with answer="" if no match."""
    matched, _ = find_cloze_span(word, forms_str, example_sv)
    if not matched:
        return "", example_sv, ""

    # Trailing-boundary-only (not a leading \b too) so this still finds a
    # compound-fallback match like "trevlig" inside "supertrevlig" -- pass 1
    # matches already satisfy the stricter double-boundary case anyway.
    pattern = r"\s+".join(re.escape(part) for part in matched.split()) + r"\b"
    spans = [m.span() for m in re.finditer(pattern, example_sv, re.IGNORECASE)]
    blanked, highlighted = example_sv, example_sv
    for start, end in reversed(spans):
        blanked = blanked[:start] + "_____" + blanked[end:]
        highlighted = highlighted[:start] + f'<span class="cloze-fill">{highlighted[start:end]}</span>' + highlighted[end:]
    return blanked, highlighted, matched


def build_model():
    """Field schema, templates, and CSS all live in style/templates.py -- this
    function just assembles them into a genanki.Model. Editing how a card
    looks never requires touching this file."""
    return genanki.Model(
        MODEL_ID,
        "Swedish Vocabulary v2",
        fields=FIELDS,
        templates=TEMPLATES,
        css=CSS,
    )


def main():
    level = sys.argv[1] if len(sys.argv) > 1 else "A1"
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    rows = [r for r in csv.DictReader(open(FINAL_CSV, encoding="utf-8")) if r["cefr"] == level]
    rows.sort(key=lambda r: int(r["kelly_rank"]))

    # Kelly occasionally lists the same (word, pos, gender) twice under two
    # different kellyIDs pointing at two different SALDO senses (e.g. "krona"
    # once for the coin-heads idiom, once as a broader catch-all that also
    # covers the currency sense) -- our picking only ever sees word/pos/
    # gender, so both rows resolve to the identical translation/example AND
    # the identical note guid (guid_for(word, pos, level)), which would
    # silently collide on import. Keep only the higher-frequency (lower
    # kelly_rank) row; any word/gender/pos nuance the second row carried is
    # handled via manual_overrides.csv instead.
    seen = set()
    deduped = []
    for r in rows:
        key = (r["word"], r["pos"], r["gender"])
        if key in seen:
            print(f"Skipping duplicate Kelly entry for {key} (kelly_rank {r['kelly_rank']})")
            continue
        seen.add(key)
        deduped.append(r)
    rows = deduped

    if limit:
        rows = rows[:limit]

    model = build_model()
    deck_id = DECK_ID_BASE + CEFR_ORDER.index(level)
    deck_name = f"Swedish::{level}"
    if limit:
        deck_name += f" (top {limit})"
    deck = genanki.Deck(deck_id, deck_name)

    MEDIA_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    media_files = []
    cloze_count = 0
    for row in rows:
        audio_field = ""
        if row["audio_path"] and os.path.exists(row["audio_path"]):
            # Stage into a word+pos+rank-qualified basename rather than reusing
            # the source file's own name -- several homonyms share a bare
            # source filename (e.g. "vara" the verb vs. "vara" the noun both
            # resolve to a source file literally named vara.mp3, from two
            # different audio directories). genanki's media_files are flattened
            # into one folder by basename, so two different notes both
            # referencing "vara.mp3" would collide and one would silently play
            # the other's audio. kelly_rank is unique per row, guaranteeing no
            # collision regardless of word/pos/gender overlap.
            ext = Path(row["audio_path"]).suffix
            staged_name = f"{row['word']}_{row['pos'].replace(' ', '_')}_{row['kelly_rank']}{ext}"
            staged_path = MEDIA_STAGING_DIR / staged_name
            if not staged_path.exists():
                shutil.copy(row["audio_path"], staged_path)
            audio_field = f"[sound:{staged_name}]"
            media_files.append(str(staged_path))

        example_sv, example_en = row["example_sv"], row["example_en"]
        example_blanked, example_highlighted, cloze_answer = "", "", ""
        if example_sv:
            example_blanked, example_highlighted, cloze_answer = blank_and_highlight(
                row["word"], row["forms"], example_sv
            )
            if cloze_answer:
                cloze_count += 1

        note = genanki.Note(
            model=model,
            fields=[
                row["word"], audio_field, row["pos"], GENDER_LABEL.get(row["gender"], ""),
                row["cefr"], row["kelly_rank"], row["translation"], row["forms"], row["ipa"],
                example_sv, example_en, example_blanked, example_highlighted, cloze_answer,
                word_display(row["word"], row["pos"], row["gender"]),
            ],
            tags=[f"cefr::{level}", f"pos::{row['pos'].replace(' ', '_')}"] + (
                [f"gender::{row['gender']}"] if row["gender"] else []
            ),
            guid=genanki.guid_for(row["word"], row["pos"], level),
        )
        deck.add_note(note)

    DECKS_DIR.mkdir(exist_ok=True)
    out_path = DECKS_DIR / f"Swedish_{level}{f'_top{limit}' if limit else ''}.apkg"
    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(out_path)

    print(f"Built {out_path} with {len(rows)} notes ({cloze_count} with cloze card, {len(media_files)} audio files)")


if __name__ == "__main__":
    main()
