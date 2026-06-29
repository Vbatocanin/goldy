#!/usr/bin/env python3
"""Goldie master index.

Reads a reports directory's history manifest (`index.json`, maintained by
history.py) and writes a single self-contained landing page that links to every
per-conversation report, newest first. This is the "master report": one repo, many
sessions, one hub. House style: no em dashes.

Usage:
    python3 render_index.py .goldie/reports -o .goldie/goldie-report.html
"""
import argparse
import html
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icons import icon  # noqa: E402
import history  # noqa: E402
from render import KIND, esc  # noqa: E402

# the order kinds are shown as count chips on a report card
CHIP_ORDER = ["prompt", "decision", "action", "principle", "security",
              "optimization", "testing", "networking", "summary"]
CHIP_LABEL = {"prompt": "requests", "decision": "decisions", "action": "actions",
              "principle": "principles", "security": "security",
              "optimization": "performance", "testing": "testing",
              "networking": "networking", "summary": "summary"}


def fmt_date(iso):
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return esc(iso or ""), ""


def chips_for(counts):
    out = []
    for k in CHIP_ORDER:
        c = counts.get(k)
        if not c:
            continue
        info = KIND.get(k, KIND["decision"])
        out.append(f"<span class='kchip {info['cls']}'>{icon(info['icon'])}"
                   f"<b>{c}</b> {esc(CHIP_LABEL.get(k, k))}</span>")
    return "".join(out)


def card(entry, href):
    date, time = fmt_date(entry.get("generated", ""))
    summary = esc(entry.get("summary", "")) or "A documented Claude Code session."
    meta = (f"<span class='rc-m'>{icon('clock')}{date}"
            + (f" · {time}" if time else "") + "</span>"
            f"<span class='rc-m'>{icon('fork')}{entry.get('steps', 0)} steps</span>")
    return (f"<a class='rcard' href='{html.escape(href)}'>"
            f"<span class='rc-mark'>{icon('goldie')}</span>"
            f"<span class='rc-body'>"
            f"<span class='rc-top'><h2 class='rc-title'>{esc(entry.get('title', 'Session'))}</h2>"
            f"<span class='rc-open'>open {icon('chevron')}</span></span>"
            f"<span class='rc-sum'>{summary}</span>"
            f"<span class='rc-meta'>{meta}</span>"
            f"<span class='rc-chips'>{chips_for(entry.get('counts', {}))}</span>"
            f"</span></a>")


CSS = """
*{box-sizing:border-box}
:root{
  --bg:#fbf9f3; --card:#fff; --ink:#2b2720; --muted:#6f685c; --line:#e7e1d6;
  --gold:#eaa81f; --gold-soft:#fdedc4; --blue:#2f7fe6; --blue-soft:#e0eeff;
  --violet:#8b46ec; --violet-soft:#efe2ff; --teal:#08b6a4; --teal-soft:#ccf6ee;
  --shadow:0 1px 2px rgba(40,36,28,.05),0 8px 24px rgba(40,36,28,.05);
}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:56px 26px 80px}
.hero{display:flex;align-items:center;gap:18px;margin-bottom:8px}
.hero .goldie-mark{flex:none;width:54px;height:54px;display:grid;place-items:center;
  color:var(--gold);background:var(--gold-soft);border-radius:50%;
  box-shadow:0 2px 8px rgba(202,162,74,.25)}
.hero .goldie-mark .ic{width:32px;height:32px}
.eyebrow{font-weight:700;letter-spacing:.14em;font-size:12px;color:var(--gold);
  text-transform:uppercase}
h1{font-size:30px;line-height:1.15;margin:2px 0 2px;font-weight:800;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:14.5px;margin:0 0 30px}
.sub b{color:var(--ink)}
.reports{display:flex;flex-direction:column;gap:14px}
.rcard{display:flex;gap:16px;text-decoration:none;color:inherit;background:var(--card);
  border:1px solid var(--line);border-radius:16px;padding:18px 20px;box-shadow:var(--shadow);
  transition:transform .2s cubic-bezier(.2,.7,.3,1),box-shadow .25s,border-color .25s}
.rcard:hover{transform:translateY(-3px);box-shadow:0 6px 14px rgba(40,36,28,.08),0 22px 48px rgba(40,36,28,.10);
  border-color:#ddd5c4}
.rc-mark{flex:none;width:44px;height:44px;display:grid;place-items:center;color:var(--gold);
  background:var(--gold-soft);border-radius:50%}
.rc-mark .ic{width:25px;height:25px}
.rc-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px}
.rc-top{display:flex;align-items:center;justify-content:space-between;gap:12px}
.rc-title{font-size:17px;font-weight:700;margin:0;letter-spacing:-.01em;line-height:1.25}
.rc-open{flex:none;display:inline-flex;align-items:center;gap:3px;font-size:12.5px;
  font-weight:600;color:var(--gold);opacity:0;transform:translateX(-4px);
  transition:opacity .2s,transform .2s}
.rc-open .ic{width:14px;height:14px}
.rcard:hover .rc-open{opacity:1;transform:none}
.rc-sum{color:#534f48;font-size:14px}
.rc-meta{display:flex;flex-wrap:wrap;gap:14px;color:var(--muted);font-size:12.5px}
.rc-m{display:inline-flex;align-items:center;gap:5px}
.rc-m .ic{width:13px;height:13px}
.rc-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:2px}
.kchip{display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;
  font-size:11.5px;font-weight:600;border:1px solid var(--line);background:#f4f1ea;color:var(--muted)}
.kchip .ic{width:12px;height:12px}.kchip b{font-weight:700}
.k-decision{background:var(--gold-soft);color:#8a6d1f;border-color:#efe1bd}
.k-action{background:var(--blue-soft);color:#2c5681;border-color:#cfe0f1}
.k-prompt{background:var(--violet-soft);color:#5a3fa0;border-color:#ddd2f5}
.k-principle{background:var(--teal-soft);color:#1f6b61;border-color:#bfe4dd}
.k-security{background:#fdeceb;color:#b0382c;border-color:#f3ccc7}
.k-optim{background:#fff2dd;color:#9a6a16;border-color:#f3dcae}
.k-test{background:#e6f4ec;color:#2f7d54;border-color:#c6e6d3}
.k-net{background:#e2f1f8;color:#1f6f93;border-color:#c2e2ef}
.k-summary{background:#efeae1;color:#5f574a;border-color:#ddd5c7}
.empty{color:#a39d92;font-style:italic;padding:30px 0}
footer{margin-top:48px;text-align:center;color:#b6b0a4;font-size:12.5px}
footer b{color:var(--gold)}
@media (prefers-reduced-motion:reduce){.rcard,.rc-open{transition:none}}
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div class="wrap">
<div class="hero"><span class="goldie-mark">{mark}</span>
  <div><span class="eyebrow">Goldie history</span>
  <h1>{project}</h1></div></div>
<p class="sub"><b>{n}</b> {word} documented in this repo. Each is a full walkthrough of one Claude Code conversation, newest first.</p>
<div class="reports">{cards}</div>
<footer>Generated by <b>Goldie</b>, keeping you in touch with your codebase.</footer>
</div></body></html>"""


def render_index(reports_dir, out_dir):
    entries = history.load(reports_dir)
    project = entries[0].get("project") if entries else os.path.basename(os.getcwd())
    cards = []
    for e in entries:
        href = os.path.relpath(os.path.join(reports_dir, e.get("file", "")), out_dir)
        cards.append(card(e, href))
    body = "".join(cards) or "<div class='empty'>No reports yet. Generate one with the goldie skill.</div>"
    return TEMPLATE.format(
        title=esc((project or "Goldie") + " · Goldie history"),
        css=CSS, mark=icon("goldie"), project=esc(project or "This repo"),
        n=len(entries), word="conversation" if len(entries) == 1 else "conversations",
        cards=body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", help="the reports directory (holds index.json)")
    ap.add_argument("-o", "--out", default="goldie-report.html",
                    help="master index output path")
    args = ap.parse_args()
    out_dir = os.path.dirname(os.path.abspath(args.out))
    with open(args.out, "w") as fh:
        fh.write(render_index(args.reports, out_dir))
    n = len(history.load(args.reports))
    print(f"goldie: master index of {n} report(s) -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
