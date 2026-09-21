# Sandbox test — the go/no-go

The pack draws its bitmap natively through Pillow instead of rasterizing the SVG,
because cairosvg, svglib, reportlab, rsvg and resvg are all routinely missing from
a code sandbox and a missing one is a hard stop. Pillow is the single dependency.

> **Passed — 2026-09-21.** Gemini and ChatGPT both ran the pack and produced both
> slides. Gemini's output was compared against the local render cell by cell:
> max deviation **2 luminance levels out of 255**, concentrated in text areas —
> JPEG encoder rounding, nothing structural. The Pillow-first call holds.
>
> One finding that is not about rendering: Gemini's download links did not work.
> A generated file the seller cannot open is a slide they did not get, which is
> why `SKILL.md` requires the model to display the image *and* hand over the file.

Re-run this whenever the pack changes shape — new dependency, new asset, new
Python version.

---

## What to do

Upload `dfns-slide-skill.zip` to ChatGPT and to Gemini, one at a time, and paste:

```
Unzip this. Then run, from inside the unzipped folder:

    python3 dfns_slide.py make examples/zero-trust.json
    python3 dfns_slide.py make examples/needs-a-wallet.json

Show me the two .jpg files, and paste any error in full.
```

That is the whole test. No prompt engineering — if it needs coaxing, it has failed.

---

## What a pass looks like

Two 1920 × 1080 JPGs:

- **zero-trust.jpg** — five white cards with purple Heroicons, a two-tone title
  reading *Trust nothing. Verify everything.* in purple then *Us too.* in grey, a
  two-line lead, and a quote strip at the bottom with the name over the role.
- **needs-a-wallet.jpg** — one centred two-tone line over a faint field of hex
  dots, with an underlined link in the footnote.

Compare them against the same slides in the MASTER LIBRARY. They should be
indistinguishable at a glance.

## What a failure looks like

| Symptom | Meaning |
|---|---|
| `ModuleNotFoundError: PIL` | Pillow is absent. The whole approach fails; fall back to shipping the SVG and exporting from a browser. |
| `FONT MISSING: …` | The fonts did not survive the upload. Check the zip, not the code. |
| The JPG appears but the type looks wrong | **The worst case.** It means a font was substituted silently. The code is written to refuse rather than do this — if it happens anyway, that guard is broken and must be fixed before anyone uses the pack. |
| Icons missing, everything else fine | The path flattener hit a command it does not handle. Recoverable, not a blocker. |
| No hex dots on the statement slide | The decorative art failed. Cosmetic, not a blocker. |

Report the symptom, not a diagnosis — the failure mode matters more than the fix.

---

## Verifying without a sandbox

Locally, the same two commands work with nothing but Pillow installed. This
machine has no cairosvg, no rsvg, no resvg and no system Inter, and both slides
render — which is the evidence that made the Pillow-first call. It is not evidence
about ChatGPT or Gemini.

---

## Regression net — `verify`

Not part of the seller's path. This is how we notice the slides changing when we
did not mean them to.

```bash
python3 dfns_slide.py verify            # compare every example to its golden grid
python3 dfns_slide.py verify --update   # re-record the grids, deliberately
```

Each example carries a 16 × 9 luminance fingerprint in `examples/fingerprints.json`.
A cell that moves by more than 3 levels fails the run and the exit code is 1.

**Run it after every change to `tokens.json`, `layouts.json` or the builder.** A
real defect moves a cell by tens of levels — a test slip of `cardTitle` from 28 to
34 px shows up as a delta of 9. Encoder noise moves it by one or two.

Its limits, so nobody trusts it further than it goes: the grid is coarse. It
catches a font substitution, a dropped icon, a column that shifted, a colour that
slid a step. It will not catch a one-pixel nudge or a swap between two glyphs of
the same weight. It is a smoke alarm, not an inspection.

`--update` rewrites the reference. Only run it when the change was intended — the
golden file *is* the record of what the slides are supposed to look like.

## Fact guard

Worth exercising once, because it is the part that keeps a frozen bitmap honest:

```
python3 dfns_slide.py check examples/zero-trust.json
```

Then edit the copy to claim `$150B+` and run it again. It must flag the figure as
unvouched — it is not in `data/facts.json` — while leaving `99.997%` alone,
because that one is.
