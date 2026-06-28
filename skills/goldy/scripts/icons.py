#!/usr/bin/env python3
"""Goldy icon set.

Inline, dependency-free SVG icons used throughout a report. No emoji anywhere.
Every icon is a 16x16 line glyph drawn with `currentColor`, so it takes the
colour of whatever chip or dot it sits in.

Custom icons (for new source types, see the `goldy-source-types` skill) live in
`~/.claude/goldy/icons.json` as `{ "name": "<svg inner markup>" }` and are merged
over the built-ins, so the set is extensible without touching this file.
"""
import json
import os

# inner markup of each 16x16 icon (viewBox 0 0 16 16, stroke = currentColor)
ICONS = {
    # node kinds
    "request":   '<path d="M8 2.2l1.5 4.3 4.3 1.5-4.3 1.5L8 13.8 6.5 9.5 2.2 8l4.3-1.5z"/>',
    "decision":  '<path d="M8 2l6 6-6 6-6-6z"/>',
    "action":    '<path d="M5 3.5l7 4.5-7 4.5z"/>',
    "principle": '<circle cx="4.3" cy="9.7" r="2.6"/><circle cx="11.7" cy="9.7" r="2.6"/><path d="M6.7 9.1c.5-.7 2.1-.7 2.6 0"/><path d="M1.8 8.3L3 4.6M14.2 8.3L13 4.6"/>',
    "security":  '<path d="M8 2.2l5 1.8v3.6c0 3-2 5.2-5 6.2-3-1-5-3.2-5-6.2V4z"/>',
    "performance": '<path d="M9 2L4 9h3.2l-1 5 5-7.2H8z"/>',
    "testing":   '<path d="M6.3 2v6.6l-2.2 3.1a1.4 1.4 0 001.1 2.2h5.6a1.4 1.4 0 001.1-2.2L9.7 8.6V2"/><path d="M5.5 2h5M6.5 9.5h3"/>',
    "network":   '<circle cx="3.8" cy="4" r="1.7"/><circle cx="12.2" cy="4.6" r="1.7"/><circle cx="7.4" cy="12.2" r="1.7"/><path d="M5.4 4.3l5.1.5M5.1 5.2l1.6 5.5M10.7 6l-2.6 4.9"/>',
    "recap":     '<path d="M3.5 2.6h9v10.8h-9z"/><path d="M5.6 5.4h4.8M5.6 8h4.8M5.6 10.6h3"/>',
    # Goldy's brand mark: a single golden thread tied in an overhand knot. A round
    # bight up top, the two ends woven through one over/under crossing (the gap in
    # the under-strand shows the weave), trailing off as tails
    "goldy":     '<path d="M6.5 7.6C4.9 6.7 4.7 4 6.4 3 8.1 2 10.9 2.7 11.2 5 11.4 6.5 10.8 7.2 9.5 7.6"/><path d="M6.5 7.6C7.1 9 8.4 9.7 9.6 10.6 10.6 11.4 11.3 12.2 11.7 13.2"/><path d="M9.5 7.6C9.1 8.6 8.7 9.1 8.4 9.5"/><path d="M7.5 10.2C6.6 11.1 5.6 11.9 4.3 13.2"/>',
    # tools
    "terminal":  '<rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M4.6 6.4L7 8l-2.4 1.6M8.4 9.8H11"/>',
    "pencil":    '<path d="M10.5 2.8l2.7 2.7-7.4 7.4-3.3.6.6-3.3z"/><path d="M9.2 4.1l2.7 2.7"/>',
    "filePlus":  '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/><path d="M8 8v3.5M6.25 9.75h3.5"/>',
    "fileText":  '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/><path d="M6 8.5h4M6 10.8h3"/>',
    "search":    '<circle cx="7" cy="7" r="3.6"/><path d="M9.7 9.7l3 3"/>',
    "globe":     '<circle cx="8" cy="8" r="6"/><path d="M2.2 8h11.6M8 2.2c2.4 2 2.4 9.6 0 11.6M8 2.2c-2.4 2-2.4 9.6 0 11.6"/>',
    "cpu":       '<rect x="4.5" y="4.5" width="7" height="7" rx="1"/><path d="M6.5 1.8v2.7M9.5 1.8v2.7M6.5 11.5v2.7M9.5 11.5v2.7M1.8 6.5h2.7M1.8 9.5h2.7M11.5 6.5h2.7M11.5 9.5h2.7"/>',
    # ui chrome
    "folder":    '<path d="M2 4.5h4l1.5 2H14V12H2z"/>',
    "clock":     '<circle cx="8" cy="8" r="6"/><path d="M8 4.8V8l2.3 1.6"/>',
    "books":     '<path d="M3 3.5h3v9H3zM6 3.5h3v9H6z"/><path d="M9.2 4.2l2.9.8-2 8.3-2.9-.8"/>',
    "spark":     '<path d="M8 2.6l1.1 3.3 3.3 1.1-3.3 1.1L8 11.4 6.9 8.1 3.6 7l3.3-1.1z"/>',
    "chevron":   '<path d="M6 4l4 4-4 4"/>',
    "arrowUp":   '<path d="M8 13V3.4M4.3 7.1L8 3.4l3.7 3.7"/>',
    "expand":    '<path d="M5.5 6.5L8 4l2.5 2.5M5.5 9.5L8 12l2.5-2.5"/>',
    "collapse":  '<path d="M5.5 4.5L8 7l2.5-2.5M5.5 11.5L8 9l2.5 2.5"/>',
    "alert":     '<path d="M8 2.4l6.2 10.8H1.8z"/><path d="M8 6.4v3.2M8 11.4h.01"/>',
    "fork":      '<path d="M8 13.2V8M8 8L4.7 4.7M8 8l3.3-3.3"/><circle cx="4.4" cy="4.4" r="1.2"/><circle cx="11.6" cy="4.4" r="1.2"/><circle cx="8" cy="13.4" r="1.2"/>',
    "code":      '<path d="M5.8 4.5L2.8 8l3 3.5M10.2 4.5l3 3.5-3 3.5"/>',
    "result":    '<path d="M5 4v3.5h6"/><path d="M9 5.5L11.5 7.5 9 9.5"/>',
    "link":      '<path d="M6.7 9.3l2.6-2.6M7.2 5.1l1-1a2.6 2.6 0 013.7 3.7l-1 1M8.8 10.9l-1 1a2.6 2.6 0 01-3.7-3.7l1-1"/>',
    "doc":       '<path d="M4 2h5l3 3v9H4z"/><path d="M9 2v3h3"/>',
    # source-type (material kind) icons
    "bookmark":  '<path d="M5 2.2h6V14l-3-2.4L5 14z"/>',
    "bookOpen":  '<path d="M8 4.2C6.4 3.2 4 3.2 2.6 3.7v7.8C4 11 6.4 11 8 12c1.6-1 4-1 5.4-.5V3.7C12 3.2 9.6 3.2 8 4.2zM8 4.2V12"/>',
    "cap":       '<path d="M8 3l6 2.4L8 7.8 2 5.4z"/><path d="M4.3 6.7v3.1c0 1 1.7 1.9 3.7 1.9s3.7-.9 3.7-1.9V6.7"/>',
    "wrench":    '<path d="M11.2 2.6a3 3 0 01-3.9 3.9l-4.1 4.1 1.6 1.6 4.1-4.1a3 3 0 013.9-3.9l-1.9 1.9-1.1-1.1z"/>',
    "ruler":     '<rect x="2.2" y="5.2" width="11.6" height="5.6" rx="1"/><path d="M5 5.2v1.8M7.5 5.2v2.6M10 5.2v1.8M12.2 5.2v2.6"/>',
    "book":      '<path d="M4 2.2h6.5a1 1 0 011 1v10.6H5a1 1 0 01-1-1z"/><path d="M4 12.3h7.5"/>',
}

_loaded = False


def _ensure_loaded():
    global _loaded
    if _loaded:
        return
    _loaded = True
    p = os.path.expanduser("~/.claude/goldy/icons.json")
    if os.path.isfile(p):
        try:
            ICONS.update(json.load(open(p)))
        except (json.JSONDecodeError, OSError):
            pass


def icon(name, cls=""):
    """Inline SVG for `name`, or empty string if unknown."""
    _ensure_loaded()
    inner = ICONS.get(name)
    if not inner:
        return ""
    c = f"ic {cls}".strip()
    return (f"<svg class='{c}' viewBox='0 0 16 16' fill='none' "
            f"stroke='currentColor' stroke-width='1.5' stroke-linecap='round' "
            f"stroke-linejoin='round' aria-hidden='true'>{inner}</svg>")
