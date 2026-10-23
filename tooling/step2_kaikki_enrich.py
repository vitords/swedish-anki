#!/usr/bin/env python3
"""
Step 2: Enrich the Kelly spine with Kaikki/Wiktextract data (English Wiktionary's
Swedish section). This is a single streaming pass over the ~305k-line JSONL file,
keeping only entries whose word appears in our spine (so this scales to the full
8,425-word Kelly list without loading everything into memory).

For each spine row we extract: one clean English gloss (translation candidate),
a compact conjugation/declension string, one Wikimedia audio URL + IPA, and one
Swedish/English example sentence pair.

Output: build/kelly_enriched.csv
"""
import csv
import json
import re
from pathlib import Path

SPINE_CSV = Path("build/kelly_spine.csv")
KAIKKI_JSONL = Path("data/sources/kaikki_swedish_raw.jsonl.gz")  # plain JSONL despite name
OUT_CSV = Path("build/kelly_enriched.csv")

POS_TO_KAIKKI = {
    "noun": {"noun"},
    "verb": {"verb"},
    "aux verb": {"verb"},
    "adjective": {"adj"},
    "adverb": {"adv"},
    "preposition": {"prep"},
    "pronoun": {"pron"},
    "numeral": {"num"},
    "subjunction": {"conj"},
    "particle": {"particle"},
    "interjection": {"intj"},
    "conjunction": {"conj"},
    "proper noun": {"name"},
    "determiner": {"det"},
}

BAD_SENSE_TAGS = {
    "obsolete", "archaic", "rare", "dated", "vulgar", "offensive", "derogatory",
    "form-of",  # e.g. "comparative degree of bra", "imperative of soka" -- a
                # grammatical cross-reference, not a translation
}

# Backstop for pick_gloss()'s tag-agnostic fallback pass: catches the same
# "form-of" glosses by shape (e.g. "indefinite neuter singular of betydlig",
# "neuter singular of denna") even when every sense happens to be so tagged.
FORM_OF_GLOSS_RE = re.compile(
    r"^(inflection of|form of|comparative degree of|superlative degree of|"
    r"imperative of|present tense of|past tense of|present participle of|"
    r"past participle of|(?:indefinite |definite )?"
    r"(?:neuter|common|masculine|feminine|singular|plural)\b.*\bof\b)",
    re.IGNORECASE,
)

MAX_EXAMPLE_LEN = 110


def load_target_words():
    words = set()
    with open(SPINE_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            words.add(row["word"])
    return words


def stream_kaikki_entries(target_words):
    """word -> list of raw kaikki entries, only for words we care about."""
    index = {}
    with open(KAIKKI_JSONL, "rt", encoding="utf-8") as f:
        for line in f:
            # cheap pre-filter before the (more expensive) json.loads
            if '"word": "' not in line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            w = d.get("word")
            if w in target_words:
                index.setdefault(w, []).append(d)
    return index


def _entry_gender(entry):
    """'en' (common gender, Kaikki tag 'c') or 'ett' (neuter, tag 'n'), or ''
    if not a noun / not stated. Swedish has real noun homonyms that differ
    ONLY by gender (e.g. "val" c = a whale, "val" n = a choice/election) --
    Kaikki gives each its own etymology entry, so this is the only reliable
    way to tell them apart."""
    for tmpl in entry.get("head_templates", []):
        g = (tmpl.get("args") or {}).get("g")
        if g == "c":
            return "en"
        if g == "n":
            return "ett"
    return ""


def pick_entry(entries, pos, gender=None):
    wanted = POS_TO_KAIKKI.get(pos, set())
    matching = [e for e in entries if e.get("pos") in wanted] if wanted else []
    candidates = matching or entries
    if not candidates:
        return None

    # Kelly already tells us the gender for nouns -- when several homonym
    # entries exist (different etymologies), narrow to the one(s) Kaikki
    # tags with the SAME gender before ranking by etymology/richness, so we
    # don't silently pick a same-spelled, different-gender, different-word
    # entry (e.g. picking "val" c/whale for a Kelly row that says "val" n).
    if pos == "noun" and gender:
        gender_matched = [e for e in candidates if _entry_gender(e) == gender]
        if gender_matched:
            candidates = gender_matched

    # Prefer the lowest etymology number first (etymology 1 / unnumbered is the
    # primary, more basic word -- a homonym with MORE senses listed under a later
    # etymology is often a rarer word, e.g. "resa" etym 1 = "to travel" (1 sense),
    # etym 2 = "to raise/erect" (3 senses) -- richness alone would wrongly pick
    # the rarer one). Only fall back to richness within the same etymology group.
    min_etym = min(e.get("etymology_number", 1) for e in candidates)
    top = [e for e in candidates if e.get("etymology_number", 1) == min_etym]

    def score(e):
        return (
            len(e.get("forms", [])),
            len(e.get("senses", [])),
            1 if e.get("sounds") else 0,
        )
    return max(top, key=score)


def _clean_gloss(gloss):
    gloss = gloss.split(";")[0].strip()
    if gloss.endswith(":"):
        gloss = gloss[:-1].strip()
    return gloss


def _sense_example(sense):
    for ex in sense.get("examples", []):
        # Wiktextract tags attributed literary/historical/legal citations as
        # type "quotation" (with a "ref") rather than a plain invented
        # "example" -- these skew archaic, dialectal, or otherwise unsuitable
        # for a learner (old spelling, parliamentary speeches, song lyrics),
        # so only take clean made-up examples.
        if ex.get("type") == "quotation" or ex.get("ref"):
            continue
        text = (ex.get("text") or "").strip()
        english = (ex.get("english") or ex.get("translation") or "").strip()
        if text and english and len(text) <= MAX_EXAMPLE_LEN:
            return text, english
    return "", ""


def pick_gloss_and_example(entry):
    """Pick the gloss AND its example from the SAME sense, not two separate
    passes -- a word like "slag" (noun) has ~10 senses ("a hit", "a battle",
    "a kind/sort", "a while", ...), and picking the gloss from whichever
    sense ranks first while independently picking the example from whichever
    OTHER sense happens to have one produces a card whose translation and
    example don't agree (e.g. gloss "category, type" paired with an example
    sentence about the Battle of Lutzen). Returns (gloss, example_sv,
    example_en); example fields are "" if that specific sense has none."""
    def is_stub(gloss):
        return bool(FORM_OF_GLOSS_RE.match(gloss.strip()))

    for require_good_tags in (True, False):
        for sense in entry.get("senses", []):
            if require_good_tags and (set(sense.get("tags", [])) & BAD_SENSE_TAGS):
                continue
            glosses = sense.get("glosses") or []
            if not glosses or is_stub(glosses[0]):
                continue
            ex_sv, ex_en = _sense_example(sense)
            return _clean_gloss(glosses[0]), ex_sv, ex_en
    return "", "", ""


def pick_audio_ipa(entry):
    audio_url, ipa = "", ""
    for s in entry.get("sounds", []):
        if not audio_url:
            audio_url = s.get("mp3_url") or s.get("ogg_url") or ""
        if not ipa and s.get("ipa"):
            ipa = s["ipa"]
    return audio_url, ipa


def form_lookup(entry, tag_sets, source=None):
    """Return the first form string whose tags match any of the given tag sets.
    source=None restricts to the compact head-line forms (no 'source' key, e.g.
    verb present/preterite/supine/imperative and adjective comparative/superlative);
    a specific source (e.g. 'declension') looks only within that detailed table
    (needed for nouns, which have no compact head-line forms of their own)."""
    if source is None:
        forms = [f for f in entry.get("forms", []) if "source" not in f]
    else:
        forms = [f for f in entry.get("forms", []) if f.get("source") == source]
    for wanted_tags in tag_sets:
        wanted = set(wanted_tags)
        for f in forms:
            if set(f.get("tags", [])) == wanted:
                return f.get("form", "")
    return ""


def build_forms_string(entry, pos):
    if pos in ("verb", "aux verb"):
        present = form_lookup(entry, [["present"]])
        preterite = form_lookup(entry, [["preterite"], ["past"]])
        supine = form_lookup(entry, [["supine"]])
        imperative = form_lookup(entry, [["imperative"]])
        parts = [p for p in [present, preterite, supine, imperative] if p]
        return " • ".join(parts)
    if pos == "noun":
        indef_sg = form_lookup(entry, [["indefinite", "nominative", "singular"], ["indefinite", "singular"]], source="declension")
        def_sg = form_lookup(entry, [["definite", "nominative", "singular"], ["definite", "singular"]], source="declension")
        indef_pl = form_lookup(entry, [["indefinite", "nominative", "plural"], ["indefinite", "plural"]], source="declension")
        def_pl = form_lookup(entry, [["definite", "nominative", "plural"], ["definite", "plural"]], source="declension")
        parts = [p for p in [indef_sg, def_sg, indef_pl, def_pl] if p]
        return " • ".join(parts)
    if pos == "adjective":
        # Agreement forms (neuter "-t", plural/definite "-a") are a distinct
        # axis from comparative/superlative -- e.g. "demokratisk" needs both
        # "demokratiskt" and "demokratiska" to match "de demokratiska
        # spelreglerna" for cloze-blanking, not just "mer/mest demokratisk".
        neuter = form_lookup(entry, [["indefinite", "neuter", "positive", "singular"]], source="declension")
        plural = form_lookup(entry, [["indefinite", "plural", "positive"]], source="declension")
        comparative = form_lookup(entry, [["comparative"]])
        superlative = form_lookup(entry, [["superlative"]])
        parts = [p for p in [neuter, plural, comparative, superlative] if p]
        return " • ".join(parts)
    return ""


def main():
    spine_rows = list(csv.DictReader(open(SPINE_CSV, encoding="utf-8")))
    target_words = {r["word"] for r in spine_rows}
    print(f"Streaming Kaikki for {len(target_words)} target words...")
    index = stream_kaikki_entries(target_words)
    print(f"Matched {len(index)} words in Kaikki")

    out_fields = [
        "word", "pos", "gender", "cefr", "kelly_rank", "svalex_total_freq",
        "translation", "translation_source", "forms", "ipa", "audio_url",
        "example_sv", "example_en", "kaikki_matched",
    ]
    written = 0
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=out_fields)
        writer.writeheader()
        for row in spine_rows:
            entries = index.get(row["word"], [])
            entry = pick_entry(entries, row["pos"], row.get("gender")) if entries else None
            out = {
                "word": row["word"],
                "pos": row["pos"],
                "gender": row["gender"],
                "cefr": row["cefr"],
                "kelly_rank": row["kelly_rank"],
                "svalex_total_freq": row["svalex_total_freq"],
                "translation": "",
                "translation_source": "",
                "forms": "",
                "ipa": "",
                "audio_url": "",
                "example_sv": "",
                "example_en": "",
                "kaikki_matched": "no",
            }
            if entry:
                out["kaikki_matched"] = "yes"
                gloss, ex_sv, ex_en = pick_gloss_and_example(entry)
                if gloss:
                    out["translation"] = gloss
                    out["translation_source"] = "wiktionary"
                out["forms"] = build_forms_string(entry, row["pos"])
                audio_url, ipa = pick_audio_ipa(entry)
                out["audio_url"] = audio_url
                out["ipa"] = ipa
                out["example_sv"] = ex_sv
                out["example_en"] = ex_en
            writer.writerow(out)
            written += 1

    print(f"Wrote {written} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
