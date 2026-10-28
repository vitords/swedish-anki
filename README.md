# Swedish vocabulary Anki deck

[![Download the deck](https://img.shields.io/badge/%E2%AC%87%EF%B8%8F_Download_the_deck-.apkg-2563eb?style=for-the-badge)](https://github.com/vitords/swedish-anki/releases/latest/download/Swedish_A1.apkg)

A Swedish vocabulary Anki deck built from curated, openly-licensed
dictionary and corpus sources, not scraped translations dumped onto a
template, but a pipeline that actually picks the right sense of each word,
pairs it with a matching example sentence, and ships it as clean,
mobile-friendly Anki cards.

## Get the deck

The button above always points at the `.apkg` from the
[latest release](../../releases/latest), so it never goes stale as new
releases come out. Download it and import it in Anki (desktop or
AnkiMobile) the normal way.

Currently shipped: **Swedish A1** (the 1,404 most frequent words per the
[Kelly list](https://spraakbanken.gu.se/en/resources/kelly)), ~1,400 notes,
three card types each (recognition, cloze-sentence, production), audio on
~95% of notes. A2 through C2 are planned, reusing the same pipeline.

## Why this exists

Most "comprehensive" Swedish vocab decks floating around are frequency
lists with a translation bolted on. No sense disambiguation, so a
polysemous word's translation and example sentence can come from two
completely unrelated meanings), no curation of which homonym you're actually
looking at, and audio that often doesn't match the headword's actual
citation form. This project's pipeline exists specifically to fix that
class of bug systematically, not just for one word at a time.

## Card design

One note type, three templates:

- **Word card**: word + audio + gender/POS/CEFR badges, flip to see
  translation, forms, IPA, and an example sentence.
- **Cloze sentence**: a real example sentence with the word blanked out and
  a typed-answer box, flip to see it filled in plus the translation and
  forms.
- **Production**: translation shown, type the Swedish word from memory.

See [`style/templates.py`](style/templates.py) and
[`style/cards.css`](style/cards.css) for the actual templates. For how this
fits with everything else in this repo, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Repo layout

```
style/      card templates + CSS: how a card looks, nothing else
tooling/    the extraction/build pipeline: how content gets picked and assembled
content/    the curated dataset itself: words, translations, examples, audio
decks/      built .apkg output (gitignored, built locally, or grab a release)
```

Each is meant to be reviewed independently. See [`CONTRIBUTING.md`](CONTRIBUTING.md)
for what belongs where, and the licensing/sourcing behind
[`content/`](content/) in [`ATTRIBUTION.md`](ATTRIBUTION.md) and
[`LICENSE-CONTENT.md`](LICENSE-CONTENT.md).

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

Audio resolution also depends on a pre-existing local Lexin cache
under `data/audio/` that isn't fetchable by a script yet. See the "Known
gap" note in [`CONTRIBUTING.md`](CONTRIBUTING.md). Without it you'll still
get a working deck, just with less audio coverage until Wikimedia fallback
fills some of the gap.

## Cutting a release

[`content/`](content/) already has everything
[`step4_build_deck.py`](tooling/step4_build_deck.py) needs (curated data +
audio), so a release build only runs that last step, no fetching or
re-curation. Pushing a `v*` tag triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which
builds `decks/Swedish_A1.apkg` and attaches it to a new GitHub Release
automatically:

```
git tag v1.0.0
git push origin v1.0.0
```

## License

- Code ([`tooling/`](tooling/), [`style/`](style/)): MIT, see [`LICENSE`](LICENSE).
- Curated dataset ([`content/`](content/)): CC BY-SA 4.0, see [`LICENSE-CONTENT.md`](LICENSE-CONTENT.md).
- Upstream sources and their individual licenses, including per-file
  Wikimedia Commons audio attribution: [`ATTRIBUTION.md`](ATTRIBUTION.md) and
  [`ATTRIBUTION_AUDIO.md`](ATTRIBUTION_AUDIO.md).
