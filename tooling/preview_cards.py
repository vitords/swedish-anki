#!/usr/bin/env python3
"""
Render a handful of real notes through the actual card templates/CSS used in
step4_build_deck.py, as static HTML, side by side light vs. dark (using Anki's
own `.nightMode` class, which the CSS already keys off). For visual QA before
importing anything into real Anki.
"""
import csv
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from step4_build_deck import build_model, blank_and_highlight, word_display  # noqa: E402

FINAL_CSV = Path("content/kelly_final.csv")
OUT_DIR = Path("build/card_preview")
SAMPLE_WORDS = ["katt", "resa", "stor", "bok", "vara", "slag", "trevlig", "gilla", "till exempel", "igår", "vid", "ska", "riva", "egen", "mål", "krona", "aning", "myndighet"]


def mustache_render(tmpl, fields, is_back):
    def cond(m):
        name, body = m.group(1), m.group(2)
        return body if fields.get(name, "").strip() else ""
    tmpl = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", cond, tmpl, flags=re.S)

    def render_type(m):
        # Real Anki only renders {{type:Field}} during an actual review
        # session (not Preview/Browse -- which is exactly why this static
        # renderer can't show it live either). Approximate: an empty input
        # on the front, a "correct answer" diff-style chip on the back, so
        # the page still communicates what studying it will look like.
        value = fields.get(m.group(1), "")
        if not is_back:
            return f'<input class="typeans" type="text" placeholder="type your answer...">'
        return f'<span class="typeGood">{value}</span>'

    tmpl = re.sub(r"\{\{type:(\w+)\}\}", render_type, tmpl)
    tmpl = re.sub(r"\{\{(\w+)\}\}", lambda m: fields.get(m.group(1), ""), tmpl)
    return tmpl


def main():
    model = build_model()
    templates = model.templates
    css = model.css

    rows = {r["word"]: r for r in csv.DictReader(open(FINAL_CSV, encoding="utf-8"))}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if (OUT_DIR / "audio").exists():
        shutil.rmtree(OUT_DIR / "audio")
    (OUT_DIR / "audio").mkdir()

    cards_html = []
    for word in SAMPLE_WORDS:
        row = rows.get(word)
        if not row:
            continue
        audio_field = ""
        if row["audio_path"] and os.path.exists(row["audio_path"]):
            basename = os.path.basename(row["audio_path"])
            shutil.copy(row["audio_path"], OUT_DIR / "audio" / basename)
            audio_field = f'<audio controls src="audio/{basename}"></audio>'

        example_sv, example_en = row["example_sv"], row["example_en"]
        example_blanked, example_highlighted, cloze_answer = "", "", ""
        if example_sv:
            example_blanked, example_highlighted, cloze_answer = blank_and_highlight(
                row["word"], row["forms"], example_sv
            )

        fields = {
            "Word": row["word"], "WordDisplay": word_display(row["word"], row["pos"], row["gender"]),
            "Audio": audio_field, "POS": row["pos"],
            "Gender": {"en": "en", "ett": "ett"}.get(row["gender"], ""), "CEFR": row["cefr"],
            "KellyRank": row["kelly_rank"], "Translation": row["translation"],
            "Forms": row["forms"], "IPA": row["ipa"], "ExampleSV": example_sv,
            "ExampleEN": example_en, "ExampleSVBlanked": example_blanked,
            "ExampleSVHighlighted": example_highlighted, "ClozeAnswer": cloze_answer,
        }

        for tmpl in templates:
            front = mustache_render(tmpl["qfmt"], fields, is_back=False)
            back = mustache_render(tmpl["afmt"], fields, is_back=True)
            if not front.strip():
                continue
            for theme_label, theme_class in [("Light", ""), ("Dark", "nightMode")]:
                cards_html.append(
                    f'<div class="preview-card {theme_class}">'
                    f'<div class="preview-label">{word} — {tmpl["name"]} — {theme_label} — FRONT</div>{front}</div>'
                )
                cards_html.append(
                    f'<div class="preview-card {theme_class}">'
                    f'<div class="preview-label">{word} — {tmpl["name"]} — {theme_label} — BACK</div>{back}</div>'
                )

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>A1 Deck Card Preview</title>
<style>
:root {{
  --wrap-bg: #eef0f3; --wrap-fg: #3f4552; --wrap-surface: #ffffff; --wrap-border: #d7dbe2;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ --wrap-bg: #121317; --wrap-fg: #b8bcc6; --wrap-surface: #1a1b20; --wrap-border: #2a2c33; }}
}}
:root[data-theme="dark"] {{ --wrap-bg: #121317; --wrap-fg: #b8bcc6; --wrap-surface: #1a1b20; --wrap-border: #2a2c33; }}
body {{ background: var(--wrap-bg); color: var(--wrap-fg); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; }}
header {{ padding: 20px 24px 4px; }}
header h1 {{ font-size: 18px; margin: 0 0 2px; }}
header p {{ font-size: 13px; color: var(--wrap-fg); opacity: .7; margin: 0; }}
.grid {{ display: flex; flex-wrap: wrap; gap: 16px; padding: 20px 24px; align-items: flex-start; }}
.preview-card {{ border-radius: 14px; overflow: hidden; border: 1px solid var(--wrap-border); background: var(--wrap-surface); width: 340px; }}
.preview-label {{
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  color: var(--wrap-fg); opacity: .55; padding: 8px 12px 0;
}}
{css}
</style></head><body>
<header>
  <h1>Swedish A1 deck — card template preview</h1>
  <p>Real data through the actual genanki templates/CSS. Each set: Front then Back, Light then Dark.</p>
</header>
<div class="grid">{''.join(cards_html)}</div></body></html>"""

    (OUT_DIR / "preview.html").write_text(page, encoding="utf-8")
    print(f"Wrote {OUT_DIR / 'preview.html'} ({len(cards_html)} card renders)")


if __name__ == "__main__":
    main()
