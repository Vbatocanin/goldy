#!/usr/bin/env python3
"""Goldy source types.

Register a new material "kind" (source type) so Goldy can tag references with it,
each with a custom inline SVG icon and colour. Built-in kinds are reference,
docs, tutorial, how-to, language, spec, book. New kinds are persisted to:

    ~/.claude/goldy/source_types.json   {kind: {label, icon, color, bg}}
    ~/.claude/goldy/icons.json          {icon-name: "<svg inner markup>"}

The renderer merges both at render time, so a new type appears with its own icon
and colour without editing any code.

Usage:
    source_types.py add --kind video --label "Video" --icon-name video \
        --color "#7a2e8a" --bg "#f3e8f7" \
        --svg '<circle cx="8" cy="8" r="6"/><path d="M6.5 5.5l4 2.5-4 2.5z"/>'
    source_types.py list
    source_types.py path
"""
import argparse
import json
import os
import select
import sys


def read_stdin():
    """Read piped JSON if any is immediately available; never block on a tty."""
    if sys.stdin.isatty():
        return ""
    r, _, _ = select.select([sys.stdin], [], [], 0.05)
    return sys.stdin.read().strip() if r else ""

DIR = os.path.expanduser("~/.claude/goldy")
TYPES = os.path.join(DIR, "source_types.json")
ICONS = os.path.join(DIR, "icons.json")


def _load(p):
    if os.path.isfile(p):
        try:
            return json.load(open(p))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(p, d):
    os.makedirs(DIR, exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=2)


def cmd_add(args):
    raw = read_stdin()
    rec = json.loads(raw) if raw else {}
    for k in ("kind", "label", "icon_name", "color", "bg", "svg"):
        if getattr(args, k, None):
            rec[k] = getattr(args, k)
    kind = rec.get("kind")
    if not kind:
        sys.exit("source_types: --kind is required")
    icon_name = rec.get("icon_name") or kind
    types = _load(TYPES)
    types[kind] = {"label": rec.get("label", kind), "icon": icon_name,
                   "color": rec.get("color", "#5a6675"),
                   "bg": rec.get("bg", "#eef1f4")}
    _save(TYPES, types)
    if rec.get("svg"):
        icons = _load(ICONS)
        icons[icon_name] = rec["svg"]
        _save(ICONS, icons)
    print(f"source_types: registered '{kind}' "
          f"({'with custom icon' if rec.get('svg') else 'icon ' + icon_name}); "
          f"{len(types)} custom types", file=sys.stderr)


def cmd_list(args):
    print(json.dumps({"types": _load(TYPES), "icons": sorted(_load(ICONS))},
                     indent=2))


def cmd_path(args):
    print(f"types:  {TYPES}\nicons:  {ICONS}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind"); a.add_argument("--label"); a.add_argument("--icon-name")
    a.add_argument("--color"); a.add_argument("--bg"); a.add_argument("--svg")
    a.set_defaults(fn=cmd_add)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("path").set_defaults(fn=cmd_path)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
