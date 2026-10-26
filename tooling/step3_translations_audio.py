#!/usr/bin/env python3
"""
Step 3: Cross-check translations against Folkets Lexikon (a real bilingual
dictionary, not Wiktionary prose) and resolve the audio source for each word.

Why Folkets as the primary translation: spot checks showed Kaikki/Wiktionary
glosses are sometimes a jumbled list of loosely-related synonyms for a single
sense (e.g. "egen" -> "peculiar, eccentric, odd, unique, personal,
individualistic" -- none of which is the actual common meaning "own"), because
English Wiktionary glosses are descriptive, not translations. Folkets Lexikon
is a real Swedish->English bilingual dictionary and gives clean short
translations ("egen" -> "own"). We keep Kaikki's gloss as a fallback/secondary
field.

Audio waterfall (all local, no network needed for ~95% of A1):
  1. Lexin local recordings (data/audio/lexin/<word>.mp3) -- professional,
     91.6% direct-lemma hit rate on A1.
  2. Bildetema local recordings (data/audio/bildetema/<word>.mp3).
  3. Kaikki/Wikimedia Commons URL (needs downloading -- written to a separate
     download list, not fetched here).
  4. Otherwise: no_audio, left for a later synthetic-TTS pass if still needed.

Output: content/kelly_final.csv, build/needs_review.csv,
        build/audio_to_download.csv
"""
import csv
import html
import os
import re
from pathlib import Path

ENRICHED_CSV = Path("build/kelly_enriched.csv")
FOLKETS_XDXF = Path("data/sources/folkets_sv_en_public.xdxf")
LEXIN_AUDIO_DIR = Path("data/audio/lexin")
BILDETEMA_AUDIO_DIR = Path("data/audio/bildetema")
WIKIMEDIA_AUDIO_DIR = Path("data/audio/wikimedia_kaikki")
VERB_POS = {"verb", "aux verb"}
OUT_FINAL = Path("content/kelly_final.csv")
OUT_REVIEW = Path("build/needs_review.csv")
OUT_AUDIO_DOWNLOAD = Path("build/audio_to_download.csv")

# Folkets <gr> POS codes -> our clean pos
FOLKETS_POS_MAP = {
    "nn": "noun", "vb": "verb", "jj": "adjective", "ab": "adverb",
    "pp": "preposition", "pn": "pronoun", "kn": "conjunction",
    "in": "interjection", "rg": "numeral", "ie": "particle",
    "sn": "subjunction",
}


def _strip_pipe(text):
    """Folkets uses '|' as a compound/morpheme-boundary marker inside headwords
    and example text (e.g. "femte|del" = the compound "femtedel", "|" is not
    part of the orthography), so it must never reach a card verbatim."""
    return text.replace("|", "").strip()


def _is_real_sentence(text):
    """Reject single-word 'examples' that are actually just a related compound
    word (e.g. Folkets' "femte|del") rather than a sentence using the word."""
    return len(text.split()) >= 2


def _strip_variant_spelling(text):
    """Folkets tags US-English spelling variants inline, e.g. "share, (stock
    [US])" or standalone "(corporation [US])" -- drop the annotation when
    something else remains, otherwise unwrap it to the bare word so we don't
    end up with an empty translation."""
    stripped = re.sub(r",?\s*\([^()]*\[(?:US|UK|Br\.|Am\.)\][^()]*\)", "", text).strip().strip(",").strip()
    if stripped:
        return stripped
    m = re.search(r"\(([^()]*?)\s*\[(?:US|UK|Br\.|Am\.)\][^()]*\)", text)
    return m.group(1).strip() if m else text


def _prioritize_cognate(word, dtrns):
    """Folkets sometimes lists the exact English cognate (e.g. "situation" ->
    [position, occasion, situation], "till" -> [into, until, to]) behind other
    candidates -- since only the first 2 dtrns get kept, that obviously-best
    match can get truncated away. If the headword itself appears among its
    own dtrns, move it to the front."""
    word_lower = word.lower()
    for i, d in enumerate(dtrns):
        if d.lower() == word_lower and i > 0:
            return [dtrns[i]] + dtrns[:i] + dtrns[i + 1:]
    return dtrns


def _strip_trailing_paren(text):
    """Drop a trailing editorial clarification like "majority in the Riksdag
    (Parliament)" -- useful in a dictionary entry, out of place as the back
    of a flashcard whose front already names the word being clarified."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()


def _strip_explanatory_paren(text):
    """Folkets' idiom/phrase-type examples often embed an editorial gloss of
    the idiom right inside the example sentence itself -- e.g. ex_orig
    'fa en andring till stand ("genomfora en andring")' or 'fy sjutton!
    ("mild svordom")'. Strip any parenthetical that itself contains a quote
    mark (the signature of an explanation, not real Swedish/English) from
    anywhere in the string, plus the "(el. X)" alternate-wording marker --
    but leave other bare parentheticals alone (e.g. "(FN)", "(upp)", "(pa)"),
    since those are normal dictionary notation for an optional/alternate
    word, not explanatory clutter."""
    text = re.sub(r'\s*\([^()]*["“”][^()]*\)', "", text)
    text = re.sub(r"\s*\(el\.[^()]*\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_folkets():
    data = FOLKETS_XDXF.read_text(encoding="utf-8")
    articles = re.findall(r"<ar>(.*?)</ar>", data, re.S)
    index = {}
    for a in articles:
        k = re.search(r"<k>(.*?)</k>", a)
        if not k:
            continue
        word = _strip_pipe(k.group(1))
        gr = re.search(r"<gr>(.*?)</gr>", a)
        dtrns = re.findall(r"<dtrn>(.*?)</dtrn>", a)

        # Pair ex_orig/ex_transl from within the SAME <ex>...</ex> block --
        # an article can have several <ex> entries (a real sentence with no
        # translation, then unrelated compound/idiom examples that DO have
        # one), and grabbing each tag independently via a plain top-level
        # search pairs the wrong two together (e.g. "is"'s real example
        # sentence has no translation, so a bare search-first wrongly paired
        # it with "isflak" -> "ice floe", an unrelated compound's gloss).
        example_sv, example_en, is_sentence_example = "", "", False
        for ex_type, ex_block in re.findall(r'<ex type="([^"]*)">(.*?)</ex>', a, re.S):
            orig_m = re.search(r"<ex_orig>(.*?)</ex_orig>", ex_block, re.S)
            transl_m = re.search(r"<ex_transl>(.*?)</ex_transl>", ex_block, re.S)
            # Folkets' XML sometimes writes a literal quote character and
            # sometimes the &quot;/&#39; HTML entity for the same thing --
            # unescape before anything downstream tries to detect quotes.
            orig = _strip_pipe(html.unescape(re.sub(r"<[^>]+>", "", orig_m.group(1)))) if orig_m else ""
            transl = _strip_pipe(html.unescape(re.sub(r"<[^>]+>", "", transl_m.group(1)))) if transl_m else ""
            orig = _strip_explanatory_paren(orig)
            transl = _strip_explanatory_paren(transl)
            # Folkets uses "xxxx" as a redacted placeholder for an omitted
            # company/brand/place name (e.g. "anstalld vid xxxx" / "employed
            # at xxxx") -- not a usable example sentence, skip to the next <ex>.
            if "xxxx" in orig.lower() or "xxxx" in transl.lower():
                continue
            if _is_real_sentence(orig) and transl:
                example_sv, example_en = orig, _strip_trailing_paren(transl)
                is_sentence_example = ex_type == "exm"
                break

        index.setdefault(word, []).append(
            {
                "pos": FOLKETS_POS_MAP.get(gr.group(1), "") if gr else "",
                "dtrns": [_strip_variant_spelling(_strip_pipe(html.unescape(d))) for d in dtrns if d.strip()],
                "example_sv": example_sv,
                "example_en": example_en,
                "is_sentence_example": is_sentence_example,
            }
        )
    return index


def pick_folkets_entry(entries, pos, word, hint_gloss=""):
    """Pick ONE Folkets entry for (word, pos) and use it for BOTH translation
    and example -- Folkets carries no gender/sense marker of its own, so a
    homonym like "val" (whale, en) vs "val" (choice/election, ett) exists as
    several separate <ar> blocks under the identical spelling+pos, and
    picking translation/example independently (each just "first match") can
    pair a translation from one sense with an example from another. Kaikki's
    gloss is already gender-disambiguated (see step2's pick_entry), so use it
    as a hint: prefer the Folkets entry whose own dtrns share a (non-trivial)
    word with it -- excluding the headword itself, since several senses'
    dtrns can be the bare word again (e.g. "bank" -> dtrn "bank" for THREE
    different senses: cloud bank, storage bank, financial bank), which would
    otherwise "match" the hint by pure coincidence regardless of sense.
    When no sense-entry can be told apart that way, fall back to preferring
    one with a real illustrative sentence over a bare compound/idiom cross-
    reference -- dictionaries reserve full example sentences for a word's
    primary, most relevant sense more often than not. Returns
    (entry_or_None, ambiguous)."""
    matching = [e for e in entries if e["pos"] == pos and e["dtrns"]]
    if not matching:
        return None, False
    ambiguous = len(matching) > 1 and any(
        m["dtrns"][:1] != matching[0]["dtrns"][:1] for m in matching[1:]
    )
    if len(matching) > 1 and hint_gloss:
        word_lower = word.lower()
        hint_words = {w for w in re.findall(r"[a-zA-Z]+", hint_gloss.lower()) if w != word_lower}
        scored = []
        for e in matching:
            entry_words = {
                w.lower() for d in e["dtrns"] for w in re.findall(r"[a-zA-Z]+", d) if w.lower() != word_lower
            }
            overlap = hint_words & entry_words
            if overlap:
                scored.append((len(overlap), e))
        # Any hint-word overlap beats none -- even when several senses share
        # A word with the hint (e.g. "riva" = scratch/tear/demolish; Kaikki's
        # gloss "to tear, to rip" matches BOTH the "tear, grate" and the
        # "pull (tear) down, demolish" entries), the ones that share a real
        # signal with an independently-picked, correct-sense gloss are still
        # far more likely to be right than falling through to matching[0]
        # (Folkets' plain first entry, which can be a completely unrelated
        # sense, e.g. "scratch" -- previously happened here since only an
        # EXACT single match was ever trusted). Among several that share a
        # word, prefer the STRONGEST overlap (e.g. "aning": hint "a
        # suspicion, an idea, a notion" shares only "suspicion" with one
        # entry but "suspicion, idea, notion" -- 3 words -- with another;
        # the 3-word match is obviously the better signal), falling back to
        # Folkets' own document order only to break a tie.
        if scored:
            scored.sort(key=lambda pair: -pair[0])
            return scored[0][1], ambiguous
        if len(matching) > 1:
            sentence_entries = [e for e in matching if e["is_sentence_example"]]
            if len(sentence_entries) == 1:
                return sentence_entries[0], ambiguous
    return matching[0], ambiguous


def is_comma_soup(translation, max_commas=2):
    return translation.count(",") > max_commas


def clean_wiktionary_gloss(gloss):
    """Wiktionary glosses for proper nouns / big numbers tend to carry a long
    explanatory parenthetical or a comma-heavy elaboration (e.g. "China (a
    large country in East Asia, occupying ...)"). Trim to the lead clause,
    which is normally already a fine short translation on its own."""
    lead = gloss.split(" (")[0].strip()
    if len(lead) >= 3:
        gloss = lead
    parts = [p.strip() for p in gloss.split(",")]
    if len(parts) > 3:
        gloss = ", ".join(parts[:3])
    return gloss


# Confirmed (by fetching the live Lexin page) to carry audio for a
# DIFFERENT headword entirely, not just a different form of the same word --
# "ett" 's search results only bold "en (2)"/"en (4)", so the cached
# local file is the indefinite article "en", not "ett".
WORDS_WITH_WRONG_LEXIN_AUDIO = {"ett"}


def resolve_audio(word):
    if word in WORDS_WITH_WRONG_LEXIN_AUDIO:
        return "", ""
    lexin_path = LEXIN_AUDIO_DIR / f"{word}.mp3"
    if lexin_path.exists():
        return str(lexin_path), "lexin"
    bildetema_path = BILDETEMA_AUDIO_DIR / f"{word}.mp3"
    if bildetema_path.exists():
        return str(bildetema_path), "bildetema"
    return "", ""


def main():
    folkets_index = parse_folkets()
    rows = list(csv.DictReader(open(ENRICHED_CSV, encoding="utf-8")))

    review_rows = []
    download_rows = []
    # svalex_total_freq is intentionally NOT carried into this final file: it's
    # Spraakbanken's SVALex frequency data, licensed CC BY-NC-SA (non-commercial),
    # and nothing downstream (sorting, picking, card content) actually reads it --
    # kelly_rank is the real ordering signal. Dropping it here keeps this published
    # file cleanly under the dataset's CC BY-SA 4.0 license with no NC encumbrance.
    final_fields = [
        "word", "pos", "gender", "cefr", "kelly_rank",
        "translation", "translation_source", "translation_gloss", "forms",
        "ipa", "audio_path", "audio_source", "audio_credit_url", "example_sv", "example_en",
        "needs_review", "review_reason",
    ]

    with open(OUT_FINAL, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=final_fields)
        writer.writeheader()

        for row in rows:
            word, pos = row["word"], row["pos"]
            kaikki_gloss = row["translation"]

            folkets_entries = folkets_index.get(word, [])
            # Pick ONE Folkets entry (gender/sense-disambiguated via the
            # Kaikki gloss hint) and use it for BOTH translation and example,
            # so a homonym like "val" (en=whale / ett=choice) can't end up
            # with one sense's translation paired against another's example.
            folkets_entry, ambiguous = pick_folkets_entry(folkets_entries, pos, word, kaikki_gloss)
            folkets_dtrns = _prioritize_cognate(word, folkets_entry["dtrns"]) if folkets_entry else []
            folkets_translation = ", ".join(folkets_dtrns[:2]) if folkets_dtrns else None

            translation = folkets_translation or kaikki_gloss
            translation_source = "folkets" if folkets_translation else ("wiktionary" if kaikki_gloss else "")
            if translation_source == "wiktionary":
                translation = clean_wiktionary_gloss(translation)

            # When Folkets wins the translation, prefer ITS example too, even
            # if Kaikki already had one: Folkets pairs a gloss with its own
            # example from the same dictionary entry (guaranteed same sense),
            # while Kaikki's example comes from Kaikki's own (different)
            # sense-ranking -- for a polysemous word those can disagree (e.g.
            # "slag" translation "category, type" paired with a Kaikki
            # example about the Battle of Lutzen). Only fall back to Kaikki's
            # example, then to any Folkets example regardless of pos match,
            # if the sense-matched Folkets one isn't available.
            example_sv, example_en = "", ""
            if translation_source == "folkets" and folkets_entry:
                example_sv, example_en = folkets_entry["example_sv"], folkets_entry["example_en"]
            if not example_sv:
                example_sv, example_en = row["example_sv"], row["example_en"]
                if example_sv and not _is_real_sentence(example_sv):
                    example_sv, example_en = "", ""
                elif example_en:
                    example_en = _strip_trailing_paren(example_en)
            if not example_sv and folkets_entry:
                example_sv, example_en = folkets_entry["example_sv"], folkets_entry["example_en"]

            audio_path, audio_source = "", ""
            if pos in VERB_POS and row["audio_url"]:
                # Lexin's citation audio for Swedish verbs is the PRESENT
                # TENSE form ("kraver" for "krava", "talar" for "tala"), not
                # the infinitive our Word field shows -- confirmed against
                # Lexin's own page markup, not a scraping bug. Kaikki's
                # audio_url is reliably the infinitive, so prefer it for
                # verbs even when local Lexin/Bildetema audio also exists.
                wikimedia_path = WIKIMEDIA_AUDIO_DIR / f"{word}.mp3"
                if wikimedia_path.exists():
                    audio_path, audio_source = str(wikimedia_path), "wikimedia"
                else:
                    audio_source = "kaikki_download_pending"
                    download_rows.append({"word": word, "pos": pos, "cefr": row["cefr"], "url": row["audio_url"]})
            if not audio_path and audio_source != "kaikki_download_pending":
                audio_path, audio_source = resolve_audio(word)
                if not audio_path and row["audio_url"]:
                    audio_source = "kaikki_download_pending"
                    download_rows.append({"word": word, "pos": pos, "cefr": row["cefr"], "url": row["audio_url"]})

            review_reasons = []
            if not translation:
                review_reasons.append("no_translation")
            elif is_comma_soup(translation):
                review_reasons.append("comma_soup_translation")
            if ambiguous:
                review_reasons.append("ambiguous_folkets_sense")
            if not audio_path and audio_source != "kaikki_download_pending":
                review_reasons.append("no_audio")
            if not example_sv:
                review_reasons.append("no_example")

            # Keep the original Commons URL whenever we actually used Wikimedia
            # audio -- CC BY-SA requires per-file attribution (uploader/
            # license), and that can only be looked up from the source URL,
            # not reconstructed later from a bare local filename.
            audio_credit_url = row["audio_url"] if audio_source == "wikimedia" else ""

            out = {
                "word": word, "pos": pos, "gender": row["gender"], "cefr": row["cefr"],
                "kelly_rank": row["kelly_rank"],
                "translation": translation, "translation_source": translation_source,
                "translation_gloss": kaikki_gloss, "forms": row["forms"], "ipa": row["ipa"],
                "audio_path": audio_path, "audio_source": audio_source,
                "audio_credit_url": audio_credit_url,
                "example_sv": example_sv, "example_en": example_en,
                "needs_review": "yes" if review_reasons else "no",
                "review_reason": "|".join(review_reasons),
            }
            writer.writerow(out)
            if review_reasons:
                review_rows.append(out)

    with open(OUT_REVIEW, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=final_fields)
        writer.writeheader()
        writer.writerows(review_rows)

    with open(OUT_AUDIO_DOWNLOAD, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["word", "pos", "cefr", "url"])
        writer.writeheader()
        writer.writerows(download_rows)

    print(f"Wrote {len(rows)} rows to {OUT_FINAL}")
    print(f"Flagged {len(review_rows)} rows for review -> {OUT_REVIEW}")
    print(f"{len(download_rows)} words need audio downloaded -> {OUT_AUDIO_DOWNLOAD}")

    a1 = [r for r in csv.DictReader(open(OUT_FINAL, encoding="utf-8")) if r["cefr"] == "A1"]
    a1_review = [r for r in a1 if r["needs_review"] == "yes"]
    print(f"\nA1: {len(a1)} words, {len(a1_review)} flagged for review ({len(a1_review)/len(a1)*100:.1f}%)")
    a1_audio = sum(1 for r in a1 if r["audio_path"] or r["audio_source"] == "kaikki_download_pending")
    print(f"A1 audio (local + pending download): {a1_audio}/{len(a1)} ({a1_audio/len(a1)*100:.1f}%)")


if __name__ == "__main__":
    main()
