"""
Card look: field schema, Anki note templates (mustache), and CSS. No data or
build logic lives here -- a PR that only wants to change how a card looks
(colors, layout, which fields appear where) should never need to touch
anything under tooling/.

FIELDS is the genanki field-name list, in field order. The order matters for
schema-migration safety when re-importing over an existing Anki collection:
append new fields at the end, don't insert them in the middle.
"""
from pathlib import Path

FIELDS = [
    {"name": "Word"}, {"name": "Audio"}, {"name": "POS"}, {"name": "Gender"},
    {"name": "CEFR"}, {"name": "KellyRank"}, {"name": "Translation"},
    {"name": "Forms"}, {"name": "IPA"}, {"name": "ExampleSV"}, {"name": "ExampleEN"},
    {"name": "ExampleSVBlanked"}, {"name": "ExampleSVHighlighted"}, {"name": "ClozeAnswer"},
    {"name": "WordDisplay"},
]

WORD_QFMT = """
<div class="card word-card">
  <div class="word">{{WordDisplay}}</div>
  {{Audio}}
  <div class="badges">
    <span class="badge pos">{{POS}}{{#Gender}} · {{Gender}}{{/Gender}}</span>
    <span class="badge cefr cefr-{{CEFR}}">{{CEFR}}</span>
  </div>
</div>
"""

WORD_AFMT = WORD_QFMT + """
<hr class="divider">
<div class="translation">{{Translation}}</div>
{{#Forms}}<div class="forms">{{Forms}}</div>{{/Forms}}
{{#IPA}}<div class="ipa">[{{IPA}}]</div>{{/IPA}}
{{#ExampleSVHighlighted}}
<div class="example-block">
  <div class="example">{{ExampleSVHighlighted}}</div>
  <div class="example-en">{{ExampleEN}}</div>
</div>
{{/ExampleSVHighlighted}}
"""

# {{type:Field}} only renders its real input box during an actual review
# (Study Now); it stays blank in Preview/Browse on both desktop and
# AnkiMobile. It's otherwise a reliable, well-supported Anki feature, so both
# the Cloze and Production cards use it for real typed recall when studying.
CLOZE_QFMT = """
{{#ExampleSVBlanked}}
<div class="card cloze-card">
  <div class="example">{{ExampleSVBlanked}}</div>
  <div class="example-en hint">{{ExampleEN}}</div>
  {{type:ClozeAnswer}}
</div>
{{/ExampleSVBlanked}}
"""

CLOZE_AFMT = """
<div class="card cloze-card">
  <div class="example">{{ExampleSVHighlighted}}</div>
  {{type:ClozeAnswer}}
  {{Audio}}
  <hr class="divider">
  <div class="word small">{{WordDisplay}}</div>
  <div class="translation small">{{Translation}}</div>
  {{#Forms}}<div class="forms">{{Forms}}</div>{{/Forms}}
</div>
"""

PROD_QFMT = """
{{#Translation}}
<div class="card prod-card">
  <div class="translation">{{Translation}}</div>
  {{type:Word}}
</div>
{{/Translation}}
"""

PROD_AFMT = """
<div class="card prod-card">
  <div class="translation small">{{Translation}}</div>
  {{type:Word}}
  {{Audio}}
  <hr class="divider">
  {{#Forms}}<div class="forms">{{Forms}}</div>{{/Forms}}
</div>
"""

TEMPLATES = [
    {"name": "Word card", "qfmt": WORD_QFMT, "afmt": WORD_AFMT},
    {"name": "Cloze sentence", "qfmt": CLOZE_QFMT, "afmt": CLOZE_AFMT},
    {"name": "Production", "qfmt": PROD_QFMT, "afmt": PROD_AFMT},
]

CSS = (Path(__file__).parent / "cards.css").read_text(encoding="utf-8")
