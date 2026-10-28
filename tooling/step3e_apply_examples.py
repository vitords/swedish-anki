#!/usr/bin/env python3
"""
Step 3e: Fill in hand-authored example sentences for words where neither
Kaikki nor Folkets had a real one.

That gap isn't random: both sources are far more likely to carry an example
for an idiomatic or "harder" word than for a simple, extremely common one
(cardinal/ordinal numbers, month names, country names, everyday nouns like
"far"/"dator"); editors don't bother exemplifying "five" or "January". For
the A1 top-1000 batch that gap concentrated in exactly the highest-value
words (kelly_rank 2-86 is almost entirely numerals, months, and country
names), so it's worth a direct, hand-written fix rather than a fancier
matching heuristic chasing sentences that don't exist in either source.

Reads content/manual_examples.csv (word,pos,example_sv,example_en) and fills
example_sv/example_en on content/kelly_final.csv wherever they're empty. Never
overwrites an example that already came from Kaikki/Folkets.
"""
import csv
from pathlib import Path

FINAL_CSV = Path("content/kelly_final.csv")
EXAMPLES_CSV = Path("content/manual_examples.csv")


def main():
    examples = {}
    with open(EXAMPLES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            examples[(row["word"], row["pos"])] = row

    rows = list(csv.DictReader(open(FINAL_CSV, encoding="utf-8")))
    fieldnames = list(rows[0].keys())
    applied_keys = set()

    for row in rows:
        if row["example_sv"]:
            continue
        key = (row["word"], row["pos"])
        if key not in examples:
            continue
        ex = examples[key]
        row["example_sv"] = ex["example_sv"]
        row["example_en"] = ex["example_en"]
        if "no_example" in row["review_reason"]:
            reasons = [r for r in row["review_reason"].split("|") if r != "no_example"]
            row["review_reason"] = "|".join(reasons)
            row["needs_review"] = "yes" if reasons else "no"
        applied_keys.add(key)

    with open(FINAL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Applied {len(applied_keys)}/{len(examples)} manual examples to {FINAL_CSV}")
    missed = set(examples) - applied_keys
    if missed:
        print("WARNING: these manual examples did not match any empty-example row:", missed)


if __name__ == "__main__":
    main()
