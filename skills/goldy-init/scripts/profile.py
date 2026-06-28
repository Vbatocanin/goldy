#!/usr/bin/env python3
"""Goldy project profile.

`goldy init` builds a small profile of the current repo so later Goldy reports
are tailored: the right stack, the right audience, the right focus, and the
project's own conventions pulled from CLAUDE.md and friends. The profile is
stored per project at `.goldy/profile.json`.

Subcommands:
    profile.py scan              inspect the repo and print findings as JSON
                                 (doc files, manifests, languages, doc excerpts)
    profile.py save  < json      write/merge the profile (stdin JSON or flags)
    profile.py show              print the saved profile (or {})
    profile.py path              print the profile path
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

PROFILE = os.path.join(".goldy", "profile.json")

DOC_NAMES = [
    "CLAUDE.md", "AGENTS.md", "README.md", "README.rst", "README.txt",
    "CONTRIBUTING.md", "ARCHITECTURE.md", "DESIGN.md", "STYLE.md",
    "CODE_OF_CONDUCT.md", ".cursorrules", ".github/copilot-instructions.md",
]
# manifest file -> (stack label, languages)
MANIFESTS = {
    "package.json": ("node", ["javascript", "typescript"]),
    "tsconfig.json": ("typescript", ["typescript"]),
    "pyproject.toml": ("python", ["python"]),
    "requirements.txt": ("python", ["python"]),
    "setup.py": ("python", ["python"]),
    "Pipfile": ("python", ["python"]),
    "Cargo.toml": ("rust", ["rust"]),
    "go.mod": ("go", ["go"]),
    "Gemfile": ("ruby", ["ruby"]),
    "composer.json": ("php", ["php"]),
    "pom.xml": ("java", ["java"]),
    "build.gradle": ("java", ["java", "kotlin"]),
    "Dockerfile": ("docker", []),
    "docker-compose.yml": ("docker", []),
    "Makefile": ("make", []),
}
EXT_LANG = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".rb": "ruby", ".go": "go",
    ".rs": "rust", ".java": "java", ".kt": "kotlin", ".php": "php", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cs": "csharp", ".sh": "shell",
    ".bash": "shell", ".html": "html", ".css": "css", ".scss": "css",
    ".sql": "sql", ".md": "markdown",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", ".next", "target", "vendor", ".goldy", ".idea", ".vscode"}


def scan():
    root = os.getcwd()
    docs, manifests, lang_counts = [], [], {}
    files_seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        depth = dirpath[len(root):].count(os.sep)
        if depth > 4:
            dirnames[:] = []
            continue
        for fn in filenames:
            files_seen += 1
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXT_LANG:
                lang_counts[EXT_LANG[ext]] = lang_counts.get(EXT_LANG[ext], 0) + 1
            if fn in MANIFESTS and dirpath == root:
                manifests.append(fn)

    # doc files (resolve nested names like .github/copilot-instructions.md)
    for name in DOC_NAMES:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            size = os.path.getsize(p)
            excerpt = ""
            if name in ("CLAUDE.md", "AGENTS.md", ".cursorrules") and size < 200000:
                with open(p, errors="replace") as fh:
                    excerpt = fh.read(1500)
            docs.append({"file": name, "bytes": size, "excerpt": excerpt})

    stacks = sorted({MANIFESTS[m][0] for m in manifests})
    langs = sorted(lang_counts, key=lang_counts.get, reverse=True)
    return {
        "project": os.path.basename(root),
        "cwd": root,
        "doc_files": docs,
        "manifests": manifests,
        "stacks": stacks,
        "languages": [l for l in langs if l != "markdown"][:8],
        "language_counts": lang_counts,
        "files_seen": files_seen,
        "has_ci": os.path.isdir(os.path.join(root, ".github", "workflows")),
    }


def load_profile():
    if os.path.isfile(PROFILE):
        try:
            return json.load(open(PROFILE))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def cmd_scan(args):
    print(json.dumps(scan(), indent=2))


def cmd_save(args):
    raw = read_stdin()
    prof = load_profile()
    if raw:
        prof.update(json.loads(raw))
    for k in ("project", "summary", "audience", "conventions", "tone"):
        if getattr(args, k, None):
            prof[k] = getattr(args, k)
    for k in ("stack", "languages", "focus", "preferred_resources", "doc_files"):
        v = getattr(args, k, None)
        if v:
            prof[k] = [x.strip() for x in v.split(",") if x.strip()]
    prof.setdefault("project", os.path.basename(os.getcwd()))
    prof["updated"] = datetime.date.today().isoformat()
    prof.setdefault("created", prof["updated"])
    os.makedirs(".goldy", exist_ok=True)
    with open(PROFILE, "w") as fh:
        json.dump(prof, fh, indent=2)
    print(f"goldy: saved profile -> {PROFILE}", file=sys.stderr)


def cmd_show(args):
    print(json.dumps(load_profile(), indent=2))


def cmd_path(args):
    print(PROFILE)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan").set_defaults(fn=cmd_scan)
    sv = sub.add_parser("save")
    for f in ("project", "summary", "audience", "conventions", "tone",
              "stack", "languages", "focus", "preferred_resources", "doc_files"):
        sv.add_argument(f"--{f}")
    sv.set_defaults(fn=cmd_save)
    sub.add_parser("show").set_defaults(fn=cmd_show)
    sub.add_parser("path").set_defaults(fn=cmd_path)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
