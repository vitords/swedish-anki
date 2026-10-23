#!/usr/bin/env python3
"""
Step 1: Build the leveled vocabulary spine from Kelly, cross-joined with SVALex
for a secondary frequency signal.

Kelly (data/sources/kelly_source.xml) is a hand-curated, frequency-ranked,
single-CEFR-labeled list of 8,425 Swedish lemmas, split into 6 buckets of
~1,404 words each (cefr 1=A1 ... 6=C2). kellyID is a genuine global frequency
rank. kellyPartOfSpeech distinguishes noun-en/noun-ett (article/gender).

Output: build/kelly_spine.csv, one row per Kelly lemma.
"""
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

KELLY_XML = Path("data/sources/kelly_source.xml")
SVALEX_TSV = Path("data/raw/svalex.tsv")
OUT_CSV = Path("build/kelly_spine.csv")

CEFR_MAP = {"1": "A1", "2": "A2", "3": "B1", "4": "B2", "5": "C1", "6": "C2"}

# Kelly's kellyPartOfSpeech -> (clean POS, gender or "")
POS_MAP = {
    "noun-en": ("noun", "en"),
    "noun-ett": ("noun", "ett"),
    "noun": ("noun", ""),
    "verb": ("verb", ""),
    "adjective": ("adjective", ""),
    "adverb": ("adverb", ""),
    "prep": ("preposition", ""),
    "pronoun": ("pronoun", ""),
    "numeral": ("numeral", ""),
    "subj": ("subjunction", ""),
    "particle": ("particle", ""),
    "interj": ("interjection", ""),
    "conj": ("conjunction", ""),
    "proper name": ("proper noun", ""),
    "det": ("determiner", ""),
}


def parse_kelly():
    tree = ET.parse(KELLY_XML)
    root = tree.getroot()
    rows = []
    for entry in root.iter("LexicalEntry"):
        lemma = entry.find("Lemma")
        if lemma is None:
            continue
        feats = {
            f.get("att"): f.get("val")
            for f in lemma.find("FormRepresentation").findall("feat")
        }
        word = feats.get("writtenForm", "").strip()
        if not word:
            continue
        # A couple of correlative conjunctions ("varken...eller") have a stray
        # NEL control char (\x85) in the source XML where an ellipsis belongs.
        word = word.replace("\x85", " ... ")
        kelly_pos_raw = feats.get("kellyPartOfSpeech", "")
        pos, gender = POS_MAP.get(kelly_pos_raw, (kelly_pos_raw, ""))

        # gram feat (e.g. "en"/"ett") is an explicit backup for gender
        gram = feats.get("gram", "")
        if gram in ("en", "ett") and not gender:
            gender = gram

        cefr_num = feats.get("cefr", "")
        cefr = CEFR_MAP.get(cefr_num, "")

        try:
            kelly_rank = int(feats.get("kellyID", "0"))
        except ValueError:
            kelly_rank = 0

        # SALDO sense references (may be multiple; keep the first as primary)
        saldo_senses = [
            karp.get("ref")
            for karp in entry.findall("karp:saldoLink", {"karp": "http://spraakbanken.gu.se/eng/research/infrastructure/karp/karp"})
        ]
        saldo_primary = saldo_senses[0] if saldo_senses else ""

        rows.append(
            {
                "word": word,
                "kelly_pos_raw": kelly_pos_raw,
                "pos": pos,
                "gender": gender,
                "cefr": cefr,
                "kelly_rank": kelly_rank,
                "saldo_sense_ref": saldo_primary,
                "saldo_all_senses": "|".join(saldo_senses),
            }
        )
    return rows


def load_svalex_freq():
    """word -> total_freq (summed across POS rows) from SVALex."""
    freq = {}
    with open(SVALEX_TSV, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            word = row.get("word", "").strip()
            if not word:
                continue
            try:
                total = float(row.get("total_freq@total", "0") or 0)
            except ValueError:
                total = 0.0
            freq[word] = freq.get(word, 0.0) + total
    return freq


def main():
    rows = parse_kelly()
    svalex_freq = load_svalex_freq()

    for row in rows:
        row["svalex_total_freq"] = round(svalex_freq.get(row["word"], 0.0), 2)

    rows.sort(key=lambda r: (r["cefr"], r["kelly_rank"]))

    OUT_CSV.parent.mkdir(exist_ok=True)
    fieldnames = [
        "word", "pos", "gender", "cefr", "kelly_rank", "svalex_total_freq",
        "kelly_pos_raw", "saldo_sense_ref", "saldo_all_senses",
    ]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_CSV}")
    from collections import Counter
    print("CEFR distribution:", Counter(r["cefr"] for r in rows))
    print("POS distribution:", Counter(r["pos"] for r in rows))


if __name__ == "__main__":
    main()
