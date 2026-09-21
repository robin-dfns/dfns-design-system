# Pack assets

Nothing here is authored by hand. Each file has a source, and that source wins.

| File | Source |
|---|---|
| `fonts/Inter-*.ttf` | rsms/inter v4.1, `extras/ttf/`. OFL. |
| `fonts/RobotoMono-Light.ttf` | googlefonts/RobotoMono, `fonts/ttf/`. Apache 2.0. |
| `icons.json` | Extracted from the design system's `assets/icons/icon-data.js` (Heroicons v2.2.0 solid 24). 73 curated glyphs. |
| `logotype-light-full.svg` | Copied from the design system's `assets/logos/`. |
| `hex-wave-banner.svg` | **Generated**, not exported: `node assets/img/generate-hex-wave.mjs 1920 454 0 1 > skill/assets/hex-wave-banner.svg` |

The hex wave is the one to watch. A Figma export of the same field existed
briefly in this folder and was replaced on 2026-09-21: the design system already
carries the generator that produced it, and two sources for one visual is the
failure this whole project exists to prevent. Regenerate; never re-export.
