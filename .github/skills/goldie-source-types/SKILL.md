---
name: goldie-source-types
description: Add a new source type (material kind) to Goldie with a custom hand-drawn SVG icon and colour, so references of that type render with their own badge. Use when the user wants a new kind of resource in reports (for example "video", "course", "paper", "internal wiki"), asks to add a source type, or asks for a custom icon for a material kind.
license: MIT
---

# Goldie Source Types: new material kinds with custom SVG icons

Goldie tags every reference with a *kind* (reference, docs, tutorial, how-to,
language, spec, book), each shown with its own SVG icon and colour. This skill
adds new kinds. Goldie uses only SVG icons, never emoji, so a new type always
comes with a hand-drawn icon.

## House style

Never use an em dash or en dash. No dash as punctuation in prose. Hyphenated
compounds are fine. Never use emoji; design an SVG icon instead.

## How to add a source type

### 1. Decide the type

Agree with the user on: the `kind` slug (lowercase, for example `video`), a short
`label` shown on the badge (for example "Video"), and a colour pair (`color` for
text, `bg` for the badge background) that fits Goldie's palette.

### 2. Draw the icon

Design a small, recognizable line glyph as **SVG inner markup** for a `0 0 16 16`
viewBox. Rules so it matches the rest of the set:

- Use paths/circles/rects only. No `<text>`, no emoji, no raster.
- Do not set `fill` or `stroke` on the elements: the renderer wraps your markup
  in an `<svg>` with `fill="none" stroke="currentColor" stroke-width="1.5"` and
  round caps, so the icon takes the badge colour automatically.
- Keep it inside roughly `2..14` so it has padding. Aim for one clear idea (a
  play triangle for video, a mortarboard for a course, a page for a paper).

Example (a video glyph):

```
<circle cx="8" cy="8" r="6"/><path d="M6.6 5.5l4 2.5-4 2.5z"/>
```

### 3. Register it

```bash
python3 ~/.copilot/skills/goldie-source-types/scripts/source_types.py add \
  --kind video --label "Video" --icon-name video \
  --color "#7a2e8a" --bg "#f3e8f7" \
  --svg '<circle cx="8" cy="8" r="6"/><path d="M6.6 5.5l4 2.5-4 2.5z"/>'
```

This writes the type to `~/.goldie/source_types.json` and the icon to
`~/.goldie/icons.json`. The renderer merges both at render time, so any
material tagged `"kind": "video"` now shows the new badge and icon. You can also
pipe a JSON record into `add`.

### 4. Use it

Tell the user the kind is ready. When enriching a report, set `"kind": "video"`
(or whatever slug) on a material and it renders with the custom icon and colour.
List what exists with `source_types.py list`.

## Notes

- Re-adding a kind updates it. Built-in kinds can be overridden the same way.
- Icons are shared with the whole icon set, so an `icon-name` can be reused by
  several types or referenced elsewhere.
