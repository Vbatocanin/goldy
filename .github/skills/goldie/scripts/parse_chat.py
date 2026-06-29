#!/usr/bin/env python3
"""Goldie chat parser (GitHub Copilot / VS Code).

Reads a VS Code Copilot Chat session and distills it into an ordered list of
*nodes*, the same shape Goldie's renderer expects:

  - "prompt"   nodes -> a turn the user typed
  - "decision" nodes -> Copilot's narration / reasoning before it acts
  - "action"   nodes -> a concrete tool call (run in terminal, edit a file,
                        fetch a page, ...) paired with a short result excerpt

The output JSON is intentionally *un-enriched*: it carries the raw facts. The
Goldie prompt (Copilot itself) then fills in `rationale` and `materials` for
each node before the renderer turns it into HTML.

Note on the source format. VS Code does not publish a stable schema for chat
session files. This parser reverse-engineers the on-disk JSON that the Copilot
Chat extension writes under the editor's `workspaceStorage`, so it is
best-effort and degrades gracefully on parts it does not recognize. If a future
VS Code release changes the shape, only this file needs updating; the rest of
the Goldie pipeline is unchanged.

Usage:
    python3 parse_chat.py <session.json> [-o nodes.json]
    python3 parse_chat.py --latest [-o nodes.json]   # newest session for cwd
    python3 parse_chat.py --list                      # list candidate sessions
"""
import argparse
import glob
import hashlib
import json
import os
import sys

MAX_RESULT_CHARS = 1200
MAX_DETAIL_CHARS = 4000


# --- Locating VS Code chat session files -----------------------------------

def _vscode_user_dirs():
    """Candidate VS Code `User` directories, stable build first, across the
    common editor flavours and platforms."""
    home = os.path.expanduser("~")
    flavours = ["Code", "Code - Insiders", "VSCodium", "Cursor"]
    bases = []
    if sys.platform == "darwin":
        bases = [os.path.join(home, "Library", "Application Support", f) for f in flavours]
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        bases = [os.path.join(appdata, f) for f in flavours]
    else:
        cfg = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
        bases = [os.path.join(cfg, f) for f in flavours]
    return [os.path.join(b, "User") for b in bases if os.path.isdir(os.path.join(b, "User"))]


def _workspace_folder_uri(cwd):
    # VS Code records workspace folders as file URIs without a trailing slash.
    path = os.path.abspath(cwd)
    return "file://" + path


def _storage_matches_cwd(storage_dir, cwd):
    """A workspaceStorage subfolder owns a `workspace.json` naming the folder it
    belongs to. Match it against the current working directory."""
    meta = os.path.join(storage_dir, "workspace.json")
    if not os.path.isfile(meta):
        return False
    try:
        with open(meta, encoding="utf-8") as fh:
            info = json.load(fh)
    except Exception:
        return False
    folder = (info.get("folder") or info.get("configuration") or "")
    target = _workspace_folder_uri(cwd)
    # Compare case-insensitively and ignore trailing slashes / URL-encoding noise.
    return folder.rstrip("/").lower().endswith(os.path.abspath(cwd).rstrip("/").lower()) \
        or folder.rstrip("/").lower() == target.rstrip("/").lower()


def _session_globs(storage_dir):
    # Sessions have lived under a couple of folder names across versions.
    pats = ["chatSessions", "chatEditingSessions"]
    out = []
    for p in pats:
        out += glob.glob(os.path.join(storage_dir, p, "*.json"))
    return out


def find_sessions(cwd):
    """Return chat session JSON paths for `cwd`, newest first. Falls back to all
    sessions in all workspaces when no workspace match is found."""
    matched, every = [], []
    for user in _vscode_user_dirs():
        for storage in glob.glob(os.path.join(user, "workspaceStorage", "*")):
            if not os.path.isdir(storage):
                continue
            files = _session_globs(storage)
            every += files
            if _storage_matches_cwd(storage, cwd):
                matched += files
    chosen = matched or every
    return sorted(chosen, key=os.path.getmtime, reverse=True)


def find_latest_session():
    files = find_sessions(os.getcwd())
    if not files:
        sys.exit("goldie: no Copilot chat sessions found for this workspace. "
                 "Open the chat once in VS Code, or pass a session.json path.")
    return files[0]


# --- Reading values out of the (loosely typed) session JSON -----------------

def md_text(val):
    """Coerce VS Code's many string shapes (plain str, IMarkdownString
    `{"value": ...}`, `{"text": ...}`) into text."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        return (val.get("value") or val.get("text") or val.get("message") or "").strip()
    if isinstance(val, list):
        return " ".join(md_text(v) for v in val).strip()
    return str(val).strip()


def first_line(s, n=90):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n…[truncated {len(s) - n} chars]"


# Goldie's own machinery: a session that runs Goldie records the report build in
# its own transcript, so by default drop it. Editing Goldie's *source* is real
# work and is not filtered.
GOLDIE_SCRIPTS = ("parse_chat.py", "render.py", "render_index.py", "history.py")


def is_goldie_meta(detail):
    d = (detail or "")
    return any(s in d for s in GOLDIE_SCRIPTS) or ".goldie/" in d


def describe_tool(part):
    """Produce (title, detail, result) for an action node from a tool-invocation
    response part. Best-effort across the toolId / toolSpecificData variants.

    TODO(copilot): validate against a real VS Code Copilot chat session (run this
    file with --list, then parse it) and extend the toolId / part-shape handling
    here for any real tool calls this gets wrong. Tested so far only on a
    synthetic session matching the reverse-engineered schema.
    """
    tool = part.get("toolId") or part.get("toolName") or part.get("kind") or "tool"
    msg = md_text(part.get("invocationMessage") or part.get("pastTenseMessage"))
    spec = part.get("toolSpecificData") or {}
    detail, title = "", ""

    # Terminal / shell command.
    cmd = ""
    if isinstance(spec, dict):
        cmd = md_text(spec.get("command") or spec.get("commandLine"))
        if not cmd and isinstance(spec.get("commandLine"), dict):
            cmd = md_text(spec["commandLine"].get("original") or spec["commandLine"].get("toolEdited"))
    if cmd:
        detail = cmd
        title = first_line(cmd)
    else:
        # File operations carry a uri / filePath.
        uri = md_text(spec.get("uri") or spec.get("filePath") or part.get("uri"))
        if uri:
            detail = uri
            t = tool.lower()
            if "create" in t:
                verb = "Create"
            elif any(w in t for w in ("edit", "replace", "insert", "write", "apply")):
                verb = "Edit"
            else:
                verb = "Read"
            title = f"{verb} {os.path.basename(uri.rstrip('/'))}"
        else:
            detail = msg or json.dumps(spec)[:MAX_DETAIL_CHARS]
            title = first_line(msg or tool)

    result = ""
    rd = part.get("resultDetails")
    if isinstance(rd, dict):
        result = md_text(rd.get("output") or rd.get("message") or rd.get("value"))
    elif isinstance(rd, str):
        result = rd
    if not result:
        result = md_text(part.get("pastTenseMessage"))
    return title or tool, clip(detail, MAX_DETAIL_CHARS), clip(result, MAX_RESULT_CHARS)


def is_tool_part(part):
    if not isinstance(part, dict):
        return False
    k = (part.get("kind") or "")
    return "toolInvocation" in k or "toolId" in part or "toolName" in part


def is_text_part(part):
    if isinstance(part, str):
        return True
    if not isinstance(part, dict):
        return False
    if is_tool_part(part):
        return False
    return bool(md_text(part.get("value") or part.get("text")))


def parse_requests(session):
    """Walk requests -> response parts, emitting prompt/decision/action nodes."""
    requests = session.get("requests") or session.get("exchanges") or []
    nodes = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"n{n}"

    for req in requests:
        if not isinstance(req, dict):
            continue
        # User turn.
        prompt = md_text(req.get("message") or req.get("request") or req.get("prompt"))
        if isinstance(req.get("message"), dict):
            prompt = md_text(req["message"].get("text") or req["message"])
        if prompt:
            nodes.append({
                "id": nid(), "kind": "prompt",
                "title": first_line(prompt, 70), "detail": clip(prompt, MAX_DETAIL_CHARS),
                "result_excerpt": "", "rationale": "", "materials": [],
            })

        # Assistant turn: a list of response parts.
        response = req.get("response") or req.get("result") or []
        if isinstance(response, dict):
            response = response.get("parts") or [response]
        narration = []
        for part in response if isinstance(response, list) else []:
            if is_tool_part(part):
                if narration:
                    text = "\n\n".join(narration).strip()
                    if text:
                        nodes.append({
                            "id": nid(), "kind": "decision",
                            "title": first_line(text, 70), "detail": clip(text, MAX_DETAIL_CHARS),
                            "result_excerpt": "", "rationale": "", "materials": [],
                        })
                    narration = []
                title, detail, result = describe_tool(part)
                if is_goldie_meta(detail):
                    continue
                nodes.append({
                    "id": nid(), "kind": "action",
                    "title": title, "detail": detail,
                    "result_excerpt": result, "rationale": "", "materials": [],
                })
            elif is_text_part(part):
                narration.append(md_text(part if isinstance(part, str) else (part.get("value") or part.get("text"))))
        if narration:
            text = "\n\n".join(narration).strip()
            if text:
                nodes.append({
                    "id": nid(), "kind": "decision",
                    "title": first_line(text, 70), "detail": clip(text, MAX_DETAIL_CHARS),
                    "result_excerpt": "", "rationale": "", "materials": [],
                })
    return nodes


def main():
    ap = argparse.ArgumentParser(description="Parse a VS Code Copilot chat session into Goldie nodes.")
    ap.add_argument("session", nargs="?", help="path to a chat session .json")
    ap.add_argument("--latest", action="store_true", help="use the newest session for this workspace")
    ap.add_argument("--list", action="store_true", help="list candidate session files and exit")
    ap.add_argument("-o", "--out", default="-", help="output path (default stdout)")
    args = ap.parse_args()

    if args.list:
        for f in find_sessions(os.getcwd()):
            print(f)
        return

    path = args.session or (find_latest_session() if args.latest else None)
    if not path:
        ap.error("pass a session.json path or --latest")
    if not os.path.isfile(path):
        sys.exit(f"goldie: no such session file: {path}")

    with open(path, encoding="utf-8") as fh:
        session = json.load(fh)

    nodes = parse_requests(session)
    sid = os.path.splitext(os.path.basename(path))[0]
    title = ""
    for nd in nodes:
        if nd["kind"] == "prompt":
            title = nd["title"]
            break
    meta = {
        "source": "github-copilot",
        "session_id": hashlib.sha1(sid.encode()).hexdigest()[:12],
        "session_file": path,
        "title": title or "Copilot session",
    }
    out = {"meta": meta, "nodes": nodes}

    text = json.dumps(out, indent=2, ensure_ascii=False)
    if args.out == "-":
        print(text)
    else:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"goldie: parsed {len(nodes)} nodes from {os.path.basename(path)} -> {args.out}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
