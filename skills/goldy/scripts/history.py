#!/usr/bin/env python3
"""Goldy report history.

A repo accumulates many Claude Code conversations, and each one gets its own
report under `.goldy/reports/`. This module maintains the manifest that ties them
together, `.goldy/reports/index.json`, so a master index page can link to every
report. House style: no em dashes.

The manifest is `{"reports": [entry, ...]}`, newest first, where each entry is the
small bit of metadata the index needs (title, summary, date, file, kind counts),
never the full node list.
"""
import json
import os
import re
from datetime import datetime

_DEDASH = {ord("—"): "-", ord("–"): "-"}


def _nd(s):
    return (s or "").translate(_DEDASH)


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", _nd(s or "").lower()).strip("-")
    return s or "session"


def report_id(meta):
    """A stable id for a session: its transcript session_id when present, else a
    slug of the title or first prompt. Used as the manifest key and the html
    filename, so re-rendering the same session overwrites rather than duplicates."""
    sid = (meta.get("session_id") or "").strip()
    if sid:
        return slug(sid)
    return slug(meta.get("title") or meta.get("first_prompt") or "session")


def entry_from(meta, nodes, html_file, generated=None):
    """Build a manifest entry from a report's meta and nodes. `generated` falls
    back to meta.generated (the session's own date) and then to now."""
    counts = {}
    for n in nodes:
        counts[n["kind"]] = counts.get(n["kind"], 0) + 1
    title = _nd(meta.get("title") or meta.get("first_prompt") or "Session").strip()
    return {
        "id": report_id(meta),
        "title": title,
        "summary": _nd(meta.get("summary") or "").strip(),
        "project": meta.get("project", ""),
        "session_id": meta.get("session_id"),
        "generated": (generated or meta.get("generated")
                      or datetime.now().isoformat(timespec="seconds")),
        "file": os.path.basename(html_file),
        "steps": len(nodes),
        "counts": counts,
    }


def manifest_path(reports_dir):
    return os.path.join(reports_dir, "index.json")


def load(reports_dir):
    p = manifest_path(reports_dir)
    if os.path.isfile(p):
        try:
            return json.load(open(p)).get("reports", [])
        except (json.JSONDecodeError, OSError):
            return []
    return []


def upsert(reports_dir, entry):
    """Insert or replace `entry` (by id) in the manifest and write it back, newest
    first. Returns the full list."""
    os.makedirs(reports_dir, exist_ok=True)
    reports = [e for e in load(reports_dir) if e.get("id") != entry["id"]]
    reports.append(entry)
    reports.sort(key=lambda e: e.get("generated", ""), reverse=True)
    with open(manifest_path(reports_dir), "w") as fh:
        json.dump({"reports": reports}, fh, indent=2)
    return reports
