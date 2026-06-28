#!/usr/bin/env python3
"""Goldy resource library.

A small, persistent index of learning resources (URLs the user trusts, crawled
and distilled into "what it can teach") so Goldy can prefer them when enriching
a report. The library is cross-project, stored at:

    ~/.claude/goldy/resources.json   (override with $GOLDY_RESOURCES)

Each record:
    {
      "url", "title", "domain",
      "topics":   ["git", "shell", ...],     # what subjects it covers
      "teaches":  ["branching", "rebasing"], # principles / skills a reader gains
      "languages":["python", ...],
      "summary":  "2 to 4 sentences",
      "sections": [{"title","url","note"}],  # deep links into the resource
      "added":    "YYYY-MM-DD"
    }

Usage:
    resources.py add   < record.json          # or use the --flags below
    resources.py list  [--topic git]
    resources.py search "<terms>"             # matches topics, teaches, title, summary
    resources.py materials "<terms>" [-n 3]   # ready-to-merge Goldy material entries
    resources.py path
"""
import argparse
import datetime
import json
import os
import re
import select
import sys


def read_stdin():
    """Read piped JSON if any is immediately available; never block on a tty."""
    if sys.stdin.isatty():
        return ""
    r, _, _ = select.select([sys.stdin], [], [], 0.05)
    return sys.stdin.read().strip() if r else ""


def lib_path():
    return os.environ.get("GOLDY_RESOURCES",
                          os.path.expanduser("~/.claude/goldy/resources.json"))


def load():
    p = lib_path()
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except (json.JSONDecodeError, OSError):
            pass
    return {"resources": []}


def save(d):
    p = lib_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        json.dump(d, fh, indent=2)


def domain_of(url):
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]


def csv(v):
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def cmd_add(args):
    raw = read_stdin()
    rec = json.loads(raw) if raw else {}
    for k in ("url", "title", "summary"):
        if getattr(args, k, None):
            rec[k] = getattr(args, k)
    if args.topics:
        rec["topics"] = csv(args.topics)
    if args.teaches:
        rec["teaches"] = csv(args.teaches)
    if args.languages:
        rec["languages"] = csv(args.languages)
    if not rec.get("url"):
        sys.exit("resources: a record needs a url (stdin JSON or --url)")
    rec.setdefault("title", rec["url"])
    rec.setdefault("domain", domain_of(rec["url"]))
    rec.setdefault("topics", [])
    rec.setdefault("teaches", [])
    rec.setdefault("languages", [])
    rec.setdefault("sections", [])
    rec.setdefault("summary", "")
    rec.setdefault("added", datetime.date.today().isoformat())
    d = load()
    d["resources"] = [r for r in d["resources"] if r.get("url") != rec["url"]]
    d["resources"].append(rec)
    save(d)
    print(f"resources: saved {rec['url']} ({len(d['resources'])} in library)",
          file=sys.stderr)


def _match(rec, terms):
    hay = " ".join([rec.get("title", ""), rec.get("summary", ""), rec.get("domain", "")]
                   + rec.get("topics", []) + rec.get("teaches", [])
                   + rec.get("languages", [])).lower()
    return all(t in hay for t in terms.lower().split())


def cmd_list(args):
    rs = load()["resources"]
    if args.topic:
        rs = [r for r in rs if args.topic.lower() in [t.lower() for t in r.get("topics", [])]]
    print(json.dumps(rs, indent=2))


def cmd_search(args):
    rs = [r for r in load()["resources"] if _match(r, args.terms)]
    print(json.dumps(rs, indent=2))


def cmd_materials(args):
    """Emit Goldy material entries (title/url/note/kind/summary) for a query,
    ready to merge straight into a node's `materials`."""
    out = []
    for r in load()["resources"]:
        if not _match(r, args.terms):
            continue
        # prefer the most relevant section if one matches, else the resource root
        target = r
        for s in r.get("sections", []):
            if _match({"title": s.get("title", ""), "summary": s.get("note", "")}, args.terms):
                target = {"url": s["url"], "title": s.get("title", r["title"]),
                          "summary": s.get("note", r.get("summary", ""))}
                break
        out.append({
            "title": target.get("title", r["title"]),
            "url": target["url"],
            "kind": "tutorial",
            "note": r.get("teaches") and f"Hands-on: {', '.join(r['teaches'][:4])}." or r.get("summary", ""),
            "summary": target.get("summary", r.get("summary", "")),
        })
        if len(out) >= args.n:
            break
    print(json.dumps(out, indent=2))


def cmd_path(args):
    print(lib_path())


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--url"); a.add_argument("--title"); a.add_argument("--summary")
    a.add_argument("--topics"); a.add_argument("--teaches"); a.add_argument("--languages")
    a.set_defaults(fn=cmd_add)
    li = sub.add_parser("list"); li.add_argument("--topic"); li.set_defaults(fn=cmd_list)
    se = sub.add_parser("search"); se.add_argument("terms"); se.set_defaults(fn=cmd_search)
    mt = sub.add_parser("materials"); mt.add_argument("terms")
    mt.add_argument("-n", type=int, default=3); mt.set_defaults(fn=cmd_materials)
    pa = sub.add_parser("path"); pa.set_defaults(fn=cmd_path)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
