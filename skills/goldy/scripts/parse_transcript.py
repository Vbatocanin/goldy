#!/usr/bin/env python3
"""Goldy transcript parser.

Reads a Claude Code session transcript (JSONL) and distills it into an ordered
list of *nodes*:

  - "decision" nodes  -> Claude's reasoning / narration before it acts
  - "action"   nodes  -> a concrete tool call (Bash, Edit, Write, WebFetch, ...)
                         paired with a short excerpt of its result

The output JSON is intentionally *un-enriched*: it carries the raw facts. The
Goldy skill (i.e. Claude itself) then fills in `rationale` and `materials` for
each node before the renderer turns it into HTML.

Usage:
    python3 parse_transcript.py <transcript.jsonl> [-o nodes.json]
    python3 parse_transcript.py --latest [-o nodes.json]   # newest session for cwd
"""
import argparse
import glob
import json
import os
import sys

MAX_RESULT_CHARS = 1200
MAX_DETAIL_CHARS = 4000


def project_dir_for_cwd(cwd):
    """Claude Code stores transcripts under ~/.claude/projects/<slug> where the
    slug is the absolute cwd with every '/' (and '.') turned into '-'."""
    slug = cwd.replace("/", "-").replace(".", "-")
    return os.path.expanduser(f"~/.claude/projects/{slug}")


def find_latest_transcript():
    pdir = project_dir_for_cwd(os.getcwd())
    files = glob.glob(os.path.join(pdir, "*.jsonl"))
    if not files:
        sys.exit(f"goldy: no transcripts found in {pdir}")
    return max(files, key=os.path.getmtime)


def text_of(block):
    return (block.get("text") or block.get("thinking") or "").strip()


def first_line(s, n=90):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n…[truncated {len(s) - n} chars]"


def describe_tool(name, inp):
    """Produce (title, detail) for an action node from a tool_use block."""
    inp = inp or {}
    if name == "Bash":
        return inp.get("description") or "Run shell command", inp.get("command", "")
    if name in ("Edit", "Write"):
        path = inp.get("file_path", "?")
        verb = "Write" if name == "Write" else "Edit"
        body = inp.get("content") or inp.get("new_string") or ""
        return f"{verb} {os.path.basename(path)}", f"# {path}\n\n{body}"
    if name == "Read":
        return f"Read {os.path.basename(inp.get('file_path', '?'))}", inp.get("file_path", "")
    if name in ("WebFetch", "WebSearch"):
        return f"{name}: {inp.get('url') or inp.get('query', '')}", json.dumps(inp, indent=2)
    if name in ("Grep", "Glob"):
        return f"{name} {inp.get('pattern', '')}", json.dumps(inp, indent=2)
    if name in ("Agent", "Task"):
        return f"Delegate: {inp.get('description', 'subagent')}", inp.get("prompt", "")
    # Fallback: show the tool name + its input
    return name, json.dumps(inp, indent=2)


def result_text(result):
    """tool_result content may be a string or a list of blocks."""
    c = result.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = []
        for b in c:
            if isinstance(b, dict):
                out.append(b.get("text") or b.get("content") or "")
            else:
                out.append(str(b))
        return "\n".join(out)
    return ""


def parse(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Index every tool_result by its tool_use_id so actions can be paired.
    results = {}
    for r in rows:
        if r.get("type") != "user":
            continue
        for b in r.get("message", {}).get("content", []) or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                results[b.get("tool_use_id")] = b

    meta = {
        "session_id": None,
        "project": os.path.basename(os.getcwd()),
        "cwd": os.getcwd(),
        "transcript": os.path.abspath(path),
        "first_prompt": None,
    }

    nodes = []
    nid = 0

    def add(kind, **kw):
        nonlocal nid
        nid += 1
        node = {"id": f"n{nid}", "kind": kind, "rationale": "", "materials": []}
        node.update(kw)
        nodes.append(node)
        return node

    for r in rows:
        meta["session_id"] = meta["session_id"] or r.get("sessionId")
        rtype = r.get("type")

        if rtype == "user":
            # Capture the human's actual prompt(s) as context anchors.
            content = r.get("message", {}).get("content")
            txt = None
            if isinstance(content, str):
                txt = content.strip()
            elif isinstance(content, list):
                parts = [b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text"]
                txt = "\n".join(p for p in parts if p).strip()
            if txt and not txt.startswith("<"):
                if meta["first_prompt"] is None:
                    meta["first_prompt"] = first_line(txt, 240)
                add("prompt", title="Human request", summary=txt,
                    timestamp=r.get("timestamp"))

        elif rtype == "assistant":
            msg = r.get("message", {})
            ts = r.get("timestamp")
            # Merge consecutive thinking/text into a single decision node so the
            # graph reads as "reasoned, then acted".
            reason = []
            for b in msg.get("content", []) or []:
                bt = b.get("type")
                if bt in ("thinking", "text"):
                    t = text_of(b)
                    if t:
                        reason.append(t)
                elif bt == "tool_use":
                    if reason:
                        body = "\n\n".join(reason)
                        add("decision", title=first_line(body),
                            summary=body, timestamp=ts)
                        reason = []
                    title, detail = describe_tool(b.get("name"), b.get("input"))
                    res = results.get(b.get("id"), {})
                    rtxt = result_text(res)
                    add("action",
                        title=first_line(title, 110),
                        tool=b.get("name"),
                        detail=clip(detail, MAX_DETAIL_CHARS),
                        result_excerpt=clip(rtxt, MAX_RESULT_CHARS),
                        status="error" if res.get("is_error") else "ok",
                        timestamp=ts)
            if reason:
                body = "\n\n".join(reason)
                add("decision", title=first_line(body), summary=body, timestamp=ts)

    return {"meta": meta, "nodes": nodes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", nargs="?")
    ap.add_argument("--latest", action="store_true",
                    help="use the newest transcript for the current project")
    ap.add_argument("-o", "--out", default="-")
    args = ap.parse_args()

    path = find_latest_transcript() if (args.latest or not args.transcript) else args.transcript
    data = parse(path)
    data["meta"]["counts"] = {
        "total": len(data["nodes"]),
        "decision": sum(n["kind"] == "decision" for n in data["nodes"]),
        "action": sum(n["kind"] == "action" for n in data["nodes"]),
        "prompt": sum(n["kind"] == "prompt" for n in data["nodes"]),
    }
    out = json.dumps(data, indent=2)
    if args.out == "-":
        print(out)
    else:
        with open(args.out, "w") as fh:
            fh.write(out)
        print(f"goldy: wrote {data['meta']['counts']['total']} nodes -> {args.out}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
