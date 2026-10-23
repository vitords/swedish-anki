# Swedish vocabulary Anki deck

A Swedish vocabulary Anki deck built from curated, openly-licensed
dictionary and corpus sources — not scraped translations dumped onto a
template, but a pipeline that actually picks the right sense of each word,
pairs it with a matching example sentence, and ships it as clean,
mobile-friendly Anki cards.

## Get the deck

Pre-built `.apkg` files are attached to each
[release](../../releases). Download one and import it in Anki (desktop or
AnkiMobile) the normal way.

Currently shipped: **Swedish A1** (the 1,404 most frequent words per the
[Kelly list](https://spraakbanken.gu.se/en/resources/kelly)), ~1,400 notes,
three card types each (recognition, cloze-sentence, production), audio on
~95% of notes. A2 through C2 are planned, reusing the same pipeline.

## Why this exists

Most "comprehensive" Swedish vocab decks floating around are frequency
lists with a translation bolted on — no sense disambiguation (so a
polysemous word's translation and example sentence can come from two
completely unrelated meanings), no curation of which homonym you're actually
looking at, and audio that often doesn't match the headword's actual
citation form. This project's pipeline exists specifically to fix that
class of bug systematically, not just for one word at a time.

## Card design

One note type, three templates:

- **Word card** — word + audio + gender/POS/CEFR badges, flip to see
  translation, forms, IPA, and an example sentence.
- **Cloze sentence** — a real example sentence with the word blanked out and
  a typed-answer box, flip to see it filled in plus the translation and
  forms.
- **Production** — translation shown, type the Swedish word from memory.

See `style/templates.py` and `style/cards.css` for the actual templates —
independent of everything else in this repo, see `CONTRIBUTING.md`.

## Repo layout

```
style/      card templates + CSS — how a card looks, nothing else
tooling/    the extraction/build pipeline — how content gets picked and assembled
content/    the curated dataset itself: words, translations, examples, audio
decks/      built .apkg output (gitignored — built locally, or grab a release)
```

Each is meant to be reviewed independently — see `CONTRIBUTING.md` for what
belongs where, and the licensing/sourcing behind `content/` in
`ATTRIBUTION.md` and `LICENSE-CONTENT.md`.

## Building it yourself

```
pip install -r requirements.txt
python3 tooling/fetch_sources.py          # pulls the raw dictionary dumps into sources/
python3 tooling/step1_kelly_spine.py
python3 tooling/step2_kaikki_enrich.py
python3 tooling/step3_translations_audio.py
python3 tooling/step3b_apply_overrides.py
python3 tooling/step3c_download_audio.py A1
python3 tooling/step3e_apply_examples.py
python3 tooling/step4_build_deck.py A1
```

Audio resolution also depends on a pre-existing local Lexin/Bildetema cache
under `data/audio/` that isn't fetchable by a script yet — see the "Known
gap" note in `CONTRIBUTING.md`. Without it you'll still get a working deck,
just with less audio coverage until Wikimedia fallback fills some of the
gap.

## License

- Code (`tooling/`, `style/`): MIT — `LICENSE`.
- Curated dataset (`content/`): CC BY-SA 4.0 — `LICENSE-CONTENT.md`.
- Upstream sources and their individual licenses, including per-file
  Wikimedia Commons audio attribution: `ATTRIBUTION.md` and
  `ATTRIBUTION_AUDIO.md`.
