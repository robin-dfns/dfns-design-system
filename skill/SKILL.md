# DFNS slide skill

You make brand-exact DFNS slides. One JSON spec in, an editable SVG and a
1920 × 1080 JPG out. Works with any model that can run Python — the geometry is
in the data files, not in your judgment.

**Read this file before writing anything.** If you read only this file, you can
still produce a correct slide.

---

## The flow

1. Ask what the slide has to say, and to whom. One slide carries one idea.
2. Pick an archetype (below). If none fits, say so and stop — see *When nothing fits*.
3. Write the title as a **two-beat formula** (below). This is the hard part.
4. Write the spec as JSON.
5. Run `python3 dfns_slide.py make <spec>.json`
6. **Show the JPG in your reply and hand over the file.** Not one or the other.

---

## Three rules you cannot bend

### 1. The title is two beats, not one sentence

The DFNS H1 is two segments. The first, in Ultra Purple, sets the premise. The
second, in Cold Grey, lands the claim. It reads as two sentences more often than
as one clause.

```
Trust nothing. Verify everything.  │  Us too.
The exit is built in.              │  That's why the entrance is safe.
Eight steps.                       │  No exception.
Same category.                     │  One market leader.
100+ blockchains.                  │  One API.
Your core speaks ledgers.          │  The new core speaks blockchains.
```

A single flat clause is off-brand even when every colour and token is right. The
builder refuses a title that is not exactly two segments.

Write the second beat first if it helps — it is the one that has to land.

### 2. Never state a figure this pack cannot vouch for

Every number lives in `data/facts.json`, dated. You may not state a figure from
memory, from the web, or by inference — not `$100B+`, not a client count, not a
price, however confident you are.

If a slide needs a figure that is not in `facts.json`, write the literal marker
`⟦FACT NEEDED: assets secured⟧` in the copy and tell the user what is missing.
A visible hole is recoverable; a plausible wrong number in a client deck is not.

The builder scans the copy and flags any figure it cannot match. Do not work
around the warning — fix the copy, or have the fact added with an owner and a date.

Third-party quotes are reproduced **verbatim**. Never trim, paraphrase or
house-style them. Banned words inside a quote belong to the speaker.

### 3. Every figure is set in mono

`$200B+`, `99.997%`, `100+`, `1,284`, and step numbers `01`…`08` are Roboto Mono
in Ultra Purple. The builder does this for you — but it means you should not
bury a number inside a body sentence when it deserves to be a figure.

---

## Writing the copy

- **Short declaratives.** Two sentences where one would sag.
- **Active voice, second person.** "DFNS secures your keys", not "Keys are secured by DFNS."
- **Say what we don't do** as plainly as what we do.
- **Never** buzzwords (`revolutionary`, `game-changing`, `next-gen`, `cutting-edge`),
  padding (`powerful`, `seamlessly`, `easily`, `robust`), hedging (`we believe`),
  exclamation marks, or emoji.
- **Never** a superlative we award ourselves. `#1 wallet infrastructure` works
  only with G2 named alongside it.
- **Spelling:** `DFNS` in caps, `onchain` as one word, `Policy Engine` and
  `Governance Engine` as proper nouns, `key management` not `key custody`.
- American English, always.

---

## Archetypes in this build

Eleven. Everything else routes to the MASTER LIBRARY.

Pick from the **shape of the idea**, not from the list:

| The idea is… | Archetype |
|---|---|
| several parallel points of equal weight | `cards-row` (3–5) · `cards-2x2` (4) |
| a definition in a few facets, no card chrome | `columns-ruled` (3–4) |
| a sequence with an order that matters | `numbered-cards` (a journey, tinted light→dark) · `numbered-rows` (controls, each with proof) |
| a comparison across the same columns | `text-table` (4–8 rows) |
| a capability broken into features | `icon-list` (3–5) |
| the numbers themselves | `kpi-row` (4–6) |
| old world versus new | `contrast-list` (3–5) |
| one sentence that should be the whole slide | `statement` |
| the cover, or a section divider | `opening` |

Every archetype except `statement` and `opening` takes `eyebrow`, `title`,
optional `lead`, and optional `strip`.

### `cards-row` — 3 to 5 parallel ideas

The workhorse. Use it when the slide makes one claim supported by several ideas
of equal weight.

```json
{
  "archetype": "cards-row",
  "eyebrow": "Zero trust security",
  "title": ["Trust nothing. Verify everything.", "Us too."],
  "lead": "One or two sentences. Optional. Never repeats the title.",
  "cards": [
    { "icon": "finger-print", "title": "Every request is signed",
      "body": "One or two sentences." }
  ],
  "strip": {
    "variant": "quote",
    "author": "Thibault de Lachèze-Murel",
    "role": "CISO, DFNS",
    "text": "“The quote, verbatim.”"
  }
}
```

- 3 to 5 cards. Four short ones beat five cramped ones.
- Card titles: 2 to 5 words. Bodies: one or two sentences.
- `icon` — a name from `assets/icons.json` (Heroicons solid). Omit it if unsure;
  a missing icon is better than a wrong one.
- `strip` is optional. Variants: `quote`, `proof-logos`.

### `statement` — one line, full stop

Use it as a hinge between sections, when one sentence should be the whole slide.
No eyebrow, no cards, no strip.

```json
{
  "archetype": "statement",
  "title": ["Every single use case you just saw", "needs a wallet*."],
  "footnote": {
    "text": "* The question is what type of wallet? Learn more:",
    "link": "dfns.co/article/the-wallet-service-guide"
  }
}
```

`footnote` is optional.

### `opening` — the cover and every section divider

One layout, two uses. A divider is a cover whose first beat is the section number.

```json
{ "archetype": "opening", "ground": "opening",
  "eyebrow": "Overview deck · 2026",
  "title": ["Core Banking Platform", "for Digital Assets"] }

{ "archetype": "opening", "ground": "opening",
  "eyebrow": "Overview deck · 2026",
  "title": ["01", "The Company"] }
```

Always `"ground": "opening"`. Here the two beats stack rather than sit inline.

### The other seven

Same header keys throughout; only the body key changes.

```json
"cards-2x2":      "cards":   [{ "title": "", "body": "" }]          // exactly 4
"columns-ruled":  "columns": [{ "icon": "", "title": "", "body": "" }]
"icon-list":      "entries": [{ "icon": "", "title": "", "body": "" }]
"kpi-row":        "kpis":    [{ "value": "$200B+", "label": "assets secured" }]
"numbered-cards": "steps":   [{ "title": "", "body": "" }]
"numbered-rows":  "rows":    [{ "title": "", "body": "", "proof": "" }]
"contrast-list":  "rows":    [{ "old": "T+1 settlement", "new": "…" }]
"text-table":     "headers": ["The capability", "Why it matters", "What it changes"],
                  "rows":    [{ "title": "", "cells": ["", "", ""] }]
```

Numbers are generated — never write `01` into a title yourself.
`proof` renders the green chip; omit it when there is no proof to show.
`kpi-row` values must come from `facts.json`, verbatim.

### Ground

`"ground": "content"` (white, the default) or `"opening"` (Steel 100). Dark is
declared in the tokens but no archetype uses it yet.

### When a slide overflows

The builder refuses a slide whose content runs past the chrome, and says by how
much. **The fix is editorial.** Cut the longest body, drop an item, or split it
across two slides. Never shrink the type — the sizes are the brand, and a slide
that fits only because it was shrunk is off-brand in a way nobody will catch.

---

## When nothing fits

The MASTER LIBRARY has seventeen more archetypes this pack does not generate:
case studies, industry slides, team grids, logo walls, bento layouts, charts,
comparison matrices, layer stacks, quadrants, steppers. Each needs a real asset
or a judgment that is not a salesperson's to make alone.

When the need is one of those, **name the MASTER LIBRARY slide to reuse and
stop**. Do not approximate it with `cards-row`. An approximation that looks
finished is worse than an honest redirect, because nobody fixes it later.

If the same unmet need comes up three times, it earns a new archetype. Tell the
brand team; do not improvise one.

---

## Running it

```bash
python3 dfns_slide.py make   slide.json     # SVG + JPG
python3 dfns_slide.py build  slide.json     # the editable SVG alone
python3 dfns_slide.py render slide.json     # the JPG alone
python3 dfns_slide.py check  slide.json     # the fact guard alone
python3 dfns_slide.py audit  deck.txt       # check an existing deck — see CHECK.md
```

Needs Pillow. Nothing else. The fonts ship with the pack — if one is missing the
builder stops rather than substituting, because a substituted font produces an
off-brand slide that still looks finished.

`--scale 2` renders at 3840 × 2160 for print or a large screen.

---

## Handing the slide over

**Display the JPG in your reply, and make the file downloadable. Both.**

This is not a formality. A generated file the person cannot open is a slide they
did not get — and some environments return a link that silently fails. If your
first attempt only produces a filename, render the image inline as well, and say
plainly if you cannot.

Also tell them, in one line:

- which archetype you used, and why that one;
- any `⟦FACT NEEDED⟧` marker left in the slide, and what it is waiting on;
- that the `.svg` beside the `.jpg` is the editable source, if they want a change
  made properly rather than pasted over.

The JPG is frozen. Every figure inside it was true on the date stamped in
`facts.json` and nowhere else. If the deck will be presented weeks later,
say so.
