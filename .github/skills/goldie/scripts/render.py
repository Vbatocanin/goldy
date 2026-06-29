#!/usr/bin/env python3
"""Goldie renderer.

Turns an (enriched) nodes JSON into a single self-contained, Notion-styled HTML
file: a vertical graph of request / decision / principle / action nodes, each
with a rationale and a collapsible "Learn more" drawer that links every
supporting article or, when no URL is available, renders a nested explainer
inline.

The "What ran" section of every shell action is tokenized: hovering a command,
flag, variable, path or operator opens a bubble explaining it, with a "read
more" link to the relevant reference.

House style: no em dashes, anywhere. Text pulled from the transcript is
sanitized on the way in.

Usage:
    python3 render.py nodes.json -o goldie-report.html
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icons import icon  # noqa: E402

# ---------------------------------------------------------------------------
# house style: never emit an em or en dash
# ---------------------------------------------------------------------------
_DEDASH = {ord("—"): "-", ord("–"): "-"}


def nd(s):
    return (s or "").translate(_DEDASH)


def esc(s):
    return html.escape(nd(s))


def short_title(s, limit=64):
    """A node title shown on its bubble should be a short label, not a wall of
    raw prompt text. Collapse whitespace and, if it is still too long, cut at a
    word boundary with an ellipsis. Enrichment should set a concise title; this
    is the safety net for titles that come straight from the transcript."""
    s = re.sub(r"\s+", " ", nd(s or "").strip())
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


# ---------------------------------------------------------------------------
# tiny, safe markdown -> html (paragraphs, code, bold/italic, links, lists)
# ---------------------------------------------------------------------------
def md(text):
    if not text:
        return ""
    text = esc(text)

    def fence(m):
        return f"<pre class='code'>{m.group(1)}</pre>"

    text = re.sub(r"```[a-zA-Z0-9]*\n(.*?)```", fence, text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                  r"<a href='\2' target='_blank' rel='noreferrer'>\1</a>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    blocks = []
    for para in re.split(r"\n\s*\n", text.strip()):
        hm = re.match(r"(#{1,6})\s+(.*)", para)
        if para.startswith("<pre"):
            blocks.append(para)
        elif hm:
            lvl = len(hm.group(1))
            rest = para.split("\n", 1)
            blocks.append(f"<h{lvl} class='md-h md-h{lvl}'>{hm.group(2)}</h{lvl}>")
            if len(rest) > 1 and rest[1].strip():
                blocks.append("<p>" + rest[1].replace("\n", "<br>") + "</p>")
        elif re.match(r"\s*[-*] ", para):
            items = "".join(f"<li>{re.sub(r'^\s*[-*] ', '', ln)}</li>"
                             for ln in para.splitlines() if ln.strip())
            blocks.append(f"<ul>{items}</ul>")
        else:
            blocks.append("<p>" + para.replace("\n", "<br>") + "</p>")
    return "\n".join(blocks)


KIND = {
    "prompt":       {"label": "Request",     "icon": "request",     "cls": "k-prompt"},
    "decision":     {"label": "Decision",    "icon": "decision",    "cls": "k-decision"},
    "principle":    {"label": "Principle",   "icon": "principle",   "cls": "k-principle"},
    "security":     {"label": "Security",    "icon": "security",    "cls": "k-security"},
    "optimization": {"label": "Performance", "icon": "performance", "cls": "k-optim"},
    "testing":      {"label": "Testing",     "icon": "testing",     "cls": "k-test"},
    "networking":   {"label": "Networking",  "icon": "network",     "cls": "k-net"},
    "action":       {"label": "Action",      "icon": "action",      "cls": "k-action"},
    "summary":      {"label": "Summary",     "icon": "recap",       "cls": "k-summary"},
}

TOOL_ICON = {
    "Bash": "terminal", "Edit": "pencil", "Write": "filePlus", "Read": "fileText",
    "Grep": "search", "Glob": "search", "WebFetch": "globe",
    "WebSearch": "search", "Agent": "cpu", "Task": "cpu",
}

# ---------------------------------------------------------------------------
# priority system: every node has a priority, and the reader picks how much
# detail to see. A higher rank survives a coarser detail level.
# ---------------------------------------------------------------------------
PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
# fallback when a node carries no explicit priority: infer from its kind, so a
# report is still sensibly filterable before enrichment hand-sets priorities.
# The story-carrying nodes are high (requests, decisions, security risks);
# principles and the other teaching nodes sit below them at medium; routine
# actions are low. A code-changing action (see below) is promoted to high.
KIND_PRIORITY = {
    "prompt": "high", "decision": "high", "security": "high", "summary": "high",
    "principle": "medium", "optimization": "medium", "testing": "medium",
    "networking": "medium", "action": "low",
}
# tools whose actions touch the codebase itself; these are high by default
# because a change to the code is exactly what a reader most needs to see.
CODE_CHANGE_TOOLS = {"Write", "Edit"}
# detail level -> the lowest rank that still shows. Coarser levels keep only the
# higher-priority nodes; "everything" keeps them all.
DETAIL_MIN_RANK = {"essentials": 3, "standard": 2, "everything": 1}
DETAIL_LEVELS = [
    ("essentials", "Essentials", "Only the key requests and decisions."),
    ("standard", "Standard", "Key steps plus the actions that carried them out."),
    ("everything", "Everything", "Every node, including minor and supporting steps."),
]
DEFAULT_DETAIL = "standard"


def node_priority(n):
    """The node's priority name, explicit if set and valid, else inferred. A
    code-changing action (Write or Edit) defaults to high; everything else falls
    back to its kind default."""
    p = str(n.get("priority") or "").lower()
    if p in PRIORITY_RANK:
        return p
    if n.get("kind") == "action" and n.get("tool") in CODE_CHANGE_TOOLS:
        return "high"
    return KIND_PRIORITY.get(n.get("kind"), "medium")

# ---------------------------------------------------------------------------
# shell lexicon used to explain "What ran" tokens on hover
# ---------------------------------------------------------------------------
CMD = {
    "ls": "List directory contents.",
    "find": "Walk a directory tree looking for files that match tests.",
    "mkdir": "Create directories.",
    "rmdir": "Remove empty directories.",
    "rm": "Remove files or directories.",
    "cp": "Copy files and directories.",
    "mv": "Move or rename files.",
    "ln": "Create links (with -s, symbolic links) between files.",
    "chmod": "Change a file's mode (permission) bits.",
    "python3": "Run the Python 3 interpreter.",
    "python": "Run the Python interpreter.",
    "git": "The Git version-control system.",
    "grep": "Search input for lines matching a pattern.",
    "sed": "Stream editor for filtering and transforming text.",
    "awk": "Pattern-scanning and text-processing language.",
    "file": "Guess a file's type by inspecting its contents.",
    "wc": "Count lines, words and bytes.",
    "sort": "Sort lines of text.",
    "uniq": "Filter adjacent matching lines.",
    "tr": "Translate or delete characters.",
    "head": "Print the first part of a file.",
    "tail": "Print the last part of a file.",
    "echo": "Print a line of text to standard output.",
    "printf": "Format and print data.",
    "sleep": "Pause for a given duration.",
    "set": "Set shell options and positional parameters.",
    "cd": "Change the shell's working directory.",
    "open": "macOS: open a file or URL in its default application.",
    "curl": "Transfer data to or from a server.",
    "cat": "Concatenate files and print them.",
}

# (command, flag) -> meaning. command None means "any command".
FLAG = {
    ("ls", "-la"): "Long format, one entry per line, including hidden (dot) files.",
    ("ls", "-l"): "Long listing format with permissions, size and date.",
    ("ls", "-a"): "Show entries that start with a dot.",
    ("ls", "-t"): "Sort by modification time, newest first.",
    ("find", "-name"): "Match files whose name fits the following glob.",
    ("find", "-type"): "Match by type: f for file, d for directory.",
    ("find", "-newermt"): "Match files modified more recently than the given time.",
    ("find", "-path"): "Match against the whole path, not just the name.",
    ("grep", "-o"): "Print only the matched part of each line.",
    ("grep", "-c"): "Print a count of matching lines instead of the lines.",
    ("grep", "-r"): "Search directories recursively.",
    ("grep", "-E"): "Interpret the pattern as an extended regular expression.",
    ("grep", "-n"): "Prefix each match with its line number.",
    ("grep", "-i"): "Match case-insensitively.",
    ("python3", "-c"): "Run the Python code given on the command line.",
    ("python3", "-m"): "Run a library module as a script.",
    ("mkdir", "-p"): "Create parent directories as needed; no error if it exists.",
    ("cp", "-r"): "Copy directories and their contents recursively.",
    ("ln", "-s"): "Create a symbolic (soft) link rather than a hard link.",
    ("ln", "-sfn"): "Symbolic, force-overwrite, and treat an existing link as a file.",
    ("head", "-1"): "Stop after the first line.",
    ("wc", "-l"): "Count lines only.",
    ("wc", "-c"): "Count bytes only.",
    ("sort", "-u"): "Output only unique lines.",
}

# commands whose first argument is a subcommand (git add, npm install, ...)
SUBCMD_CMDS = {"git", "npm", "yarn", "pnpm", "cargo", "docker", "kubectl", "go",
               "pip", "pip3", "brew", "apt", "systemctl", "gh", "deno", "bun"}
SUBCMD = {
    ("git", "init"): "Create an empty Git repository (a .git directory) in the current folder.",
    ("git", "add"): "Stage file changes so they go into the next commit.",
    ("git", "commit"): "Record the staged changes as a new commit in history.",
    ("git", "status"): "Show which files are staged, modified or untracked.",
    ("git", "log"): "Show the commit history.",
    ("git", "diff"): "Show line-by-line changes not yet staged.",
    ("git", "checkout"): "Switch branches or restore files from another commit.",
    ("git", "branch"): "List, create or delete branches.",
    ("git", "push"): "Send local commits to a remote repository.",
    ("git", "pull"): "Fetch from a remote and merge into the current branch.",
    ("git", "clone"): "Copy a remote repository, with full history, to a new folder.",
    ("git", "rm"): "Remove files from the working tree and the index.",
    ("git", "reset"): "Move the current branch tip, optionally changing staged files.",
    ("npm", "install"): "Install dependencies listed in package.json (or a named package).",
    ("npm", "run"): "Run a script defined in package.json.",
    ("pip", "install"): "Install a Python package and its dependencies.",
    ("pip3", "install"): "Install a Python package and its dependencies.",
    ("docker", "build"): "Build an image from a Dockerfile.",
    ("docker", "run"): "Create and start a container from an image.",
    ("gh", "pr"): "Work with GitHub pull requests.",
    ("cargo", "build"): "Compile the current Rust package.",
}

OP = {
    "|": "Pipe: feed this command's output into the next command's input.",
    "||": "Or: run the next command only if this one fails.",
    "&&": "And: run the next command only if this one succeeds.",
    ">": "Redirect output to a file, overwriting it.",
    ">>": "Redirect output to a file, appending to it.",
    "2>": "Redirect standard error.",
    "<": "Read standard input from a file.",
    ";": "Separator: run the commands in sequence.",
    "&": "Run the preceding command in the background.",
    "$(": "Command substitution: run a command and use its output.",
}

BASH_MAN = "https://www.gnu.org/software/bash/manual/bash.html"
PERM_RE = re.compile(r"^[+\-=][rwxXstugoa]+$")
ASSIGN_RE = re.compile(r"^\w+=")
PATHY_RE = re.compile(r"[/~.]")

TOKEN_RE = re.compile(r"""
      (?P<ws>\s+)
    | (?P<str>'[^']*'|"[^"]*")
    | (?P<var>\$\{?\w+\}?)
    | (?P<sub>\$\()
    | (?P<redir>&>>|&>|\d*>>&?\d*|\d*>&?\d*|<<<|<<|<)
    | (?P<op>\|\||&&|[|&;])
    | (?P<flag>--?[A-Za-z][\w-]*)
    | (?P<word>[^\s'"|&;<>]+)
""", re.X)

# redirection operators and the standard streams they move
REDIR = {
    ">": "Redirect standard output to a file, overwriting it.",
    ">>": "Redirect standard output to a file, appending to it.",
    "<": "Read standard input from a file.",
    "<<": "Here-document: feed the following lines in as standard input.",
    "<<<": "Here-string: feed the given string in as standard input.",
    "&>": "Redirect both standard output and standard error to a file.",
    "&>>": "Append both standard output and standard error to a file.",
    "1>": "Redirect standard output (file descriptor 1) to a file.",
    "2>": "Redirect standard error (file descriptor 2) to a file.",
    "2>>": "Append standard error to a file.",
    "2>&1": "Send standard error to wherever standard output currently goes.",
    "1>&2": "Send standard output to wherever standard error currently goes.",
    ">&2": "Redirect standard output to standard error.",
    ">&1": "Redirect standard output to file descriptor 1.",
}
# special device files that show up as redirection targets
DEV_FILES = {
    "/dev/null": "The null device: anything written here is discarded. The usual way to silence output.",
    "/dev/stdout": "A device file standing for the process's standard output stream.",
    "/dev/stderr": "A device file standing for the process's standard error stream.",
    "/dev/stdin": "A device file standing for the process's standard input stream.",
    "/dev/zero": "A device that yields an endless stream of zero bytes when read.",
    "/dev/tty": "The controlling terminal of the current process.",
}
REDIR_URL = BASH_MAN + "#Redirections"
DEV_NULL_URL = "https://en.wikipedia.org/wiki/Null_device"


def redir_tip(tok):
    if tok in REDIR:
        return REDIR[tok]
    if "<" in tok:
        return "Input redirection: read standard input from the given source."
    return ("Redirection: send a file descriptor's stream to a file or to "
            "another descriptor.")


def explain_url(cmd):
    return "https://explainshell.com/explain?cmd=" + quote(cmd.strip()[:200])


def tip_span(text, tip, url, cls):
    """One hoverable token: visible text plus a docstring-style bubble (a
    monospace signature line, then a description) with an optional link. A tip
    with a newline is split into signature + description; otherwise it is just a
    description."""
    sig, _, desc = (tip or "").partition("\n")
    if desc:
        body = (f"<span class='tip-sig'>{esc(sig)}</span>"
                f"<span class='tip-d'>{esc(desc)}</span>")
    else:
        body = f"<span class='tip-d'>{esc(sig)}</span>"
    link = (f"<a class='tip-l' href='{html.escape(url)}' target='_blank' "
            f"rel='noreferrer'>read more ↗</a>") if url else ""
    return (f"<span class='tok {cls}' tabindex='0'>{esc(text)}"
            f"<span class='tip'>{body}{link}</span></span>")


# A command that runs a script, by an interpreter (python3 deploy.py) or directly
# (./run.sh), should call the script out as a script and say what it does. The
# renderer flags it; enrichment supplies the "what it does" via a token override.
SCRIPT_EXT = {".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript",
              ".ts": "TypeScript", ".sh": "shell", ".bash": "Bash", ".zsh": "Zsh",
              ".rb": "Ruby", ".pl": "Perl", ".ps1": "PowerShell", ".rs": "Rust",
              ".go": "Go", ".lua": "Lua", ".php": "PHP"}


def script_lang_name(tok):
    """The language label if `tok` names a script file (by extension), else None."""
    m = re.search(r"(\.[A-Za-z0-9]+)$", tok or "")
    return SCRIPT_EXT.get(m.group(1).lower()) if m else None


def script_tip(tok, cur_cmd):
    """Default tooltip for a script token: name it, say how it is run, and point at
    the step's own description for what it does (enrichment can override this)."""
    name = tok.split("/")[-1]
    lang = script_lang_name(tok) or "executable"
    how = "run directly" if (cur_cmd in (None, name)) else f"run by '{cur_cmd}'"
    return (f"{name}\n{lang} script, {how}. This step is what the script does; "
            "see the step's description for the specifics.")


def annotate_bash(cmd, overrides=None):
    return "<div class='cmd'>" + annotate_bash_inner(cmd, overrides) + "</div>"


def annotate_bash_inner(cmd, overrides=None):
    """Return hover-annotated spans for a shell command (no wrapper div)."""
    overrides = overrides or {}
    url_whole = explain_url(cmd.splitlines()[0] if cmd else "")
    out = []
    at_cmd = True       # next word token sits in command position
    cur_cmd = None      # the command the current flags belong to
    expect_sub = False  # next word is a subcommand (git add, npm run, ...)

    for m in TOKEN_RE.finditer(cmd):
        kind = m.lastgroup
        tok = m.group()
        if kind == "ws":
            out.append(esc(tok))
            continue

        ov = overrides.get(tok)
        if ov:
            ocls = "t-script" if script_lang_name(tok) else "t-arg"
            out.append(tip_span(tok, ov.get("tip", ""), ov.get("url"), ocls))
            continue

        if kind == "str":
            out.append(tip_span(tok, "Quoted string literal passed as one argument.",
                                url_whole, "t-str"))
        elif kind == "var":
            out.append(tip_span(tok, "Shell variable: expands to its stored value.",
                                url_whole, "t-var"))
        elif kind == "sub":
            out.append(tip_span(tok, OP["$("], url_whole, "t-op"))
            at_cmd = True
        elif kind == "redir":
            out.append(tip_span(tok, redir_tip(tok), url_whole, "t-redir"))
        elif kind == "op":
            out.append(tip_span(tok, OP.get(tok, "Shell operator."), url_whole, "t-op"))
            at_cmd = tok in ("|", "||", "&&", ";", "&")
            if at_cmd:
                expect_sub = False
        elif kind == "flag":
            tip = (FLAG.get((cur_cmd, tok)) or FLAG.get((None, tok))
                   or f"Option for '{cur_cmd or 'the command'}': changes how it "
                      "behaves. Hover read more for the full reference.")
            out.append(tip_span(tok, tip, url_whole, "t-flag"))
        else:  # word
            if at_cmd and not ASSIGN_RE.match(tok):
                cur_cmd = tok.split("/")[-1]
                if script_lang_name(tok):       # the command itself is a script
                    out.append(tip_span(tok, script_tip(tok, cur_cmd), None, "t-script"))
                else:
                    tip = CMD.get(cur_cmd, "Program or builtin invoked as a command.")
                    out.append(tip_span(tok, tip, url_whole, "t-cmd"))
                at_cmd = False
                expect_sub = cur_cmd in SUBCMD_CMDS
            elif ASSIGN_RE.match(tok):
                out.append(tip_span(tok, "Inline variable assignment for this command.",
                                    url_whole, "t-var"))
            elif expect_sub and re.match(r"^[a-z][\w-]*$", tok):
                tip = SUBCMD.get((cur_cmd, tok),
                                 f"'{cur_cmd} {tok}': a subcommand of {cur_cmd}. "
                                 "Hover read more for what it does.")
                out.append(tip_span(tok, tip, url_whole, "t-sub"))
                expect_sub = False
            elif script_lang_name(tok):          # a script passed to an interpreter
                out.append(tip_span(tok, script_tip(tok, cur_cmd), None, "t-script"))
            elif tok in DEV_FILES:
                out.append(tip_span(tok, DEV_FILES[tok], DEV_NULL_URL, "t-dev"))
            elif PERM_RE.match(tok):
                out.append(tip_span(tok, "Permission bits, e.g. +x adds the execute bit.",
                                    "https://en.wikipedia.org/wiki/Chmod", "t-flag"))
            elif PATHY_RE.search(tok):
                out.append(tip_span(tok, f"A file or directory path given to "
                                    f"'{cur_cmd or 'the command'}'.", url_whole, "t-path"))
            else:
                out.append(tip_span(tok, f"Argument to '{cur_cmd or 'the command'}'. "
                                    "Hover read more to see how it is used.",
                                    url_whole, "t-arg"))
    return "".join(out)


# ---------------------------------------------------------------------------
# embedded programs: python3 -c '...', heredocs, etc. get their own language
# panel so the inner code is taught, not buried as one opaque shell string.
# ---------------------------------------------------------------------------
LANG_META = {
    "python": {"name": "Python", "icon": "code", "docs": "https://docs.python.org/3/"},
    "javascript": {"name": "JavaScript", "icon": "code",
                   "docs": "https://developer.mozilla.org/en-US/docs/Web/JavaScript"},
    "bash": {"name": "Bash", "icon": "terminal", "docs": BASH_MAN},
    "ruby": {"name": "Ruby", "icon": "code", "docs": "https://www.ruby-lang.org/en/documentation/"},
    "perl": {"name": "Perl", "icon": "code", "docs": "https://perldoc.perl.org/"},
    "text": {"name": "Text", "icon": "doc", "docs": None},
}
INTERP_LANG = {"python": "python", "python3": "python", "node": "javascript",
               "ruby": "ruby", "perl": "perl", "bash": "bash", "sh": "bash",
               "cat": "text", "tee": "text"}
EXT_LANG = {".py": "python", ".js": "javascript", ".mjs": "javascript",
            ".sh": "bash", ".bash": "bash", ".rb": "ruby", ".pl": "perl"}


def lang_from_path(path):
    m = re.search(r"(\.[A-Za-z0-9]+)\s*$", (path or "").strip())
    return EXT_LANG.get(m.group(1).lower()) if m else None

# the -c/-e argument is one shell word, possibly several quoted and unquoted
# pieces concatenated (e.g. 'a'"$f"'b'); capture the whole word, not just the
# first quote, so a Python string that switches quoting is not cut in half.
DASH_C_RE = re.compile(r"\b(python3?|node|ruby|perl)\s+(?:-\w+\s+)*(-c|-e)\s+"
                       r"((?:'[^']*'|\"[^\"]*\"|[^\s'\"|&;<>])+)", re.S)
HEREDOC_RE = re.compile(r"([^\n|;&]*?)<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n[ \t]*\2\b",
                        re.S)
_SEG_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"|([^'\"]+)")


def reconstruct_dashc(word):
    """Join the concatenated shell-quoted pieces of a -c argument back into the
    program source, dropping the shell quoting (e.g. 'a'"$f"'b' -> a$fb)."""
    parts = []
    for m in _SEG_RE.finditer(word):
        parts.append(m.group(1) or m.group(2) or m.group(3) or "")
    return "".join(parts)

PY_KW = {"import", "from", "for", "in", "if", "elif", "else", "while", "def",
         "return", "lambda", "with", "as", "try", "except", "finally", "class",
         "and", "or", "not", "is", "pass", "break", "continue", "yield",
         "global", "None", "True", "False", "del", "assert", "raise"}
PY_BUILTIN = {
    "print": "print(*values, sep=' ', end='\\n')\nPrint values to standard output.",
    "open": "open(file, mode='r')\nOpen a file and return a file object.",
    "len": "len(obj)\nReturn the number of items in a container.",
    "range": "range(stop) or range(start, stop, step)\nAn immutable sequence of integers.",
    "sorted": "sorted(iterable, *, key=None, reverse=False)\nReturn a new sorted list.",
    "set": "set(iterable=())\nAn unordered collection of unique items.",
    "list": "list(iterable=())\nA mutable sequence.",
    "dict": "dict(**kwargs)\nA mapping of keys to values.",
    "str": "str(object='')\nReturn a string version of object.",
    "int": "int(x=0, base=10)\nReturn an integer parsed from x.",
    "float": "float(x=0.0)\nReturn a floating-point number from x.",
    "enumerate": "enumerate(iterable, start=0)\nYield (index, item) pairs.",
    "type": "type(obj)\nReturn the type of obj.",
    "isinstance": "isinstance(obj, classinfo)\nReturn True if obj is an instance of classinfo.",
    "map": "map(func, iterable)\nApply func to each item, lazily.",
    "filter": "filter(func, iterable)\nKeep the items for which func(item) is true.",
    "zip": "zip(*iterables)\nYield tuples pairing items from each iterable.",
    "sum": "sum(iterable, start=0)\nReturn the sum of the items.",
    "min": "min(iterable, *, key=None)\nReturn the smallest item.",
    "max": "max(iterable, *, key=None)\nReturn the largest item.",
    "abs": "abs(x)\nReturn the absolute value of x.",
    "repr": "repr(obj)\nReturn a printable representation of obj.",
    "input": "input(prompt='')\nRead a line from standard input.",
}
# module -> one-line summary of what it contains. Module tooltips always carry a
# quick summary so a reader knows what the module is for (general rule, applied
# per language; this is the Python standard library).
PY_MODULE = {
    "json": "encode and decode JSON data",
    "sys": "interpreter state: argv, stdin and stdout, exit",
    "os": "operating-system interface: files, paths, environment",
    "re": "regular expressions for matching and substituting text",
    "glob": "filename matching with shell-style wildcards",
    "pathlib": "object-oriented filesystem paths",
    "math": "mathematical functions and constants",
    "datetime": "dates, times and durations",
    "argparse": "parse command-line arguments",
    "collections": "specialized containers (deque, Counter, defaultdict)",
    "itertools": "iterator building blocks for efficient looping",
    "subprocess": "run and communicate with external processes",
    "html": "HTML escaping and entity helpers",
    "urllib": "URL handling and HTTP requests",
    "select": "wait for input/output readiness on file descriptors",
}
PY_KW_URL = "https://docs.python.org/3/reference/lexical_analysis.html#keywords"
PY_BUILTIN_URL = "https://docs.python.org/3/library/functions.html"

# qualified module members -> what they do. The annotator walks the dotted chain
# (os, then os.path, then os.path.expanduser) and explains each part. This is the
# general rule for module attributes and functions, not a special case.
# Each value is a small docstring: a signature line, a newline, then a one-line
# description (what `help()` would show in miniature).
PY_MEMBER = {
    "os.path": "os.path\nSubmodule for manipulating filesystem path names.",
    "os.path.expanduser": "os.path.expanduser(path)\nExpand a leading ~ to the user's home directory.",
    "os.path.join": "os.path.join(a, *paths)\nJoin path parts with the correct separator.",
    "os.path.exists": "os.path.exists(path)\nReturn True if path refers to an existing path.",
    "os.path.isfile": "os.path.isfile(path)\nReturn True if path is an existing regular file.",
    "os.path.isdir": "os.path.isdir(path)\nReturn True if path is an existing directory.",
    "os.path.basename": "os.path.basename(path)\nReturn the final component of a path.",
    "os.path.dirname": "os.path.dirname(path)\nReturn the directory portion of a path.",
    "os.path.abspath": "os.path.abspath(path)\nReturn a normalized, absolute version of path.",
    "os.path.splitext": "os.path.splitext(path)\nSplit a path into (root, extension).",
    "os.path.getsize": "os.path.getsize(path)\nReturn the size of a file in bytes.",
    "os.path.getmtime": "os.path.getmtime(path)\nReturn the last-modified time of path, in seconds.",
    "os.makedirs": "os.makedirs(name, exist_ok=False)\nCreate a directory and any missing parents.",
    "os.environ": "os.environ\nMapping object of the process's environment variables.",
    "os.getcwd": "os.getcwd()\nReturn the current working directory.",
    "os.walk": "os.walk(top)\nWalk a directory tree, yielding (dirpath, dirnames, filenames).",
    "os.listdir": "os.listdir(path='.')\nReturn a list of the entries in a directory.",
    "os.sep": "os.sep\nThe character that separates path components on this OS.",
    "sys.argv": "sys.argv\nThe list of command-line arguments passed to the script.",
    "sys.exit": "sys.exit(arg=0)\nExit the program; a string arg is printed to stderr.",
    "sys.stdin": "sys.stdin\nThe interpreter's standard input stream (a file object).",
    "sys.stdout": "sys.stdout\nThe interpreter's standard output stream.",
    "sys.stderr": "sys.stderr\nThe interpreter's standard error stream.",
    "sys.path": "sys.path\nThe list of directories searched when importing modules.",
    "json.loads": "json.loads(s)\nParse a JSON string and return the Python object.",
    "json.dumps": "json.dumps(obj, indent=None)\nSerialize a Python object to a JSON string.",
    "json.load": "json.load(fp)\nRead and parse JSON from a file object.",
    "json.dump": "json.dump(obj, fp, indent=None)\nWrite a Python object as JSON to a file object.",
    "re.compile": "re.compile(pattern, flags=0)\nCompile a regex pattern into a reusable object.",
    "re.sub": "re.sub(pattern, repl, string)\nReplace matches of pattern in string with repl.",
    "re.match": "re.match(pattern, string)\nMatch pattern at the start of string, or None.",
    "re.search": "re.search(pattern, string)\nFind the first match of pattern anywhere, or None.",
    "re.findall": "re.findall(pattern, string)\nReturn all non-overlapping matches as a list.",
    "re.split": "re.split(pattern, string)\nSplit string by the occurrences of pattern.",
    "re.finditer": "re.finditer(pattern, string)\nReturn an iterator over match objects.",
    "glob.glob": "glob.glob(pathname)\nReturn a list of paths matching a shell wildcard pattern.",
    "datetime.now": "datetime.now(tz=None)\nReturn the current local date and time.",
    "datetime.date": "datetime.date(year, month, day)\nAn idealized calendar date.",
    "pathlib.Path": "pathlib.Path(*segments)\nAn object-oriented filesystem path.",
}
# common method names on unknown receivers, as small docstrings
PY_METHOD = {
    "get": "dict.get(key, default=None)\nReturn the value for key, or default if it is missing.",
    "keys": "dict.keys()\nReturn a view of the mapping's keys.",
    "values": "dict.values()\nReturn a view of the mapping's values.",
    "items": "dict.items()\nReturn a view of the mapping's (key, value) pairs.",
    "append": "list.append(x)\nAdd an item to the end of the list.",
    "extend": "list.extend(iterable)\nExtend the list by appending items from the iterable.",
    "update": "update(other)\nMerge items from other into this dict or set.",
    "setdefault": "dict.setdefault(key, default=None)\nReturn key's value, inserting default if absent.",
    "add": "set.add(elem)\nAdd an element to the set.",
    "pop": "pop()\nRemove and return an item.",
    "sort": "list.sort(*, key=None, reverse=False)\nSort the list in place.",
    "replace": "str.replace(old, new, count=-1)\nReturn a copy with all old replaced by new.",
    "strip": "str.strip(chars=None)\nReturn a copy with leading and trailing whitespace removed.",
    "lstrip": "str.lstrip(chars=None)\nReturn a copy with leading whitespace removed.",
    "rstrip": "str.rstrip(chars=None)\nReturn a copy with trailing whitespace removed.",
    "split": "str.split(sep=None, maxsplit=-1)\nSplit the string into a list of parts.",
    "rsplit": "str.rsplit(sep=None, maxsplit=-1)\nSplit from the right into a list of parts.",
    "splitlines": "str.splitlines()\nSplit the string at line boundaries into a list.",
    "join": "str.join(iterable)\nJoin the iterable's strings, using this string as the separator.",
    "startswith": "str.startswith(prefix)\nReturn True if the string starts with prefix.",
    "endswith": "str.endswith(suffix)\nReturn True if the string ends with suffix.",
    "format": "str.format(*args, **kwargs)\nSubstitute values into a format string.",
    "encode": "str.encode(encoding='utf-8')\nReturn an encoded bytes version of the string.",
    "decode": "bytes.decode(encoding='utf-8')\nReturn a string decoded from bytes.",
    "read": "read(size=-1)\nRead and return up to size bytes or characters.",
    "write": "write(s)\nWrite the string or bytes s to the stream.",
    "readlines": "readlines()\nRead and return a list of all lines from the stream.",
    "group": "match.group(n=0)\nReturn the text matched by the whole pattern or group n.",
    "groups": "match.groups()\nReturn a tuple of all the captured groups.",
}
# official-docs link for each method (full definition)
_STD = "https://docs.python.org/3/library/stdtypes.html#"
_LIST = "https://docs.python.org/3/tutorial/datastructures.html#more-on-lists"
_IO = "https://docs.python.org/3/library/io.html#io.IOBase"
PY_METHOD_URL = {
    "get": _STD + "dict.get", "keys": _STD + "dict.keys", "values": _STD + "dict.values",
    "items": _STD + "dict.items", "setdefault": _STD + "dict.setdefault",
    "update": _STD + "dict.update", "add": _STD + "frozenset.add",
    "append": _LIST, "extend": _LIST, "pop": _LIST, "sort": _STD + "list.sort",
    "replace": _STD + "str.replace", "strip": _STD + "str.strip",
    "lstrip": _STD + "str.lstrip", "rstrip": _STD + "str.rstrip",
    "split": _STD + "str.split", "rsplit": _STD + "str.rsplit",
    "splitlines": _STD + "str.splitlines", "join": _STD + "str.join",
    "startswith": _STD + "str.startswith", "endswith": _STD + "str.endswith",
    "format": _STD + "str.format", "encode": _STD + "str.encode",
    "decode": _STD + "bytes.decode", "read": _IO, "write": _IO, "readlines": _IO,
    "group": "https://docs.python.org/3/library/re.html#re.Match.group",
    "groups": "https://docs.python.org/3/library/re.html#re.Match.groups",
}


def member_url(cand):
    page = "os.path" if cand.startswith("os.path") else cand.split(".")[0]
    return f"https://docs.python.org/3/library/{page}.html#{cand}"


def _load_py_members():
    """Merge fetched-doc tooltips Goldie has persisted for specific functions.
    Each entry is `"module.attr": "what it does"` or
    `"module.attr": {"tip": "...", "url": "..."}`."""
    p = os.path.expanduser("~/.goldie/py_members.json")
    if os.path.isfile(p):
        try:
            for k, v in json.load(open(p)).items():
                PY_MEMBER[k] = v
        except (json.JSONDecodeError, OSError):
            pass


_load_py_members()


def _member_tip(cand):
    v = PY_MEMBER.get(cand)
    if isinstance(v, dict):
        return v.get("tip", cand), v.get("url", member_url(cand))
    return v, member_url(cand)

PY_RE = re.compile(r"""
      (?P<cmt>\#[^\n]*)
    | (?P<str>'''.*?'''|\"\"\".*?\"\"\"|'[^']*'|\"[^\"]*\")
    | (?P<num>\b\d+\.?\d*\b)
    | (?P<name>[A-Za-z_]\w*)
    | (?P<op>[=:+\-*/%<>!&|]+|[()\[\]{},.])
    | (?P<other>.)
""", re.X | re.S)


def annotate_python_inner(code, tips=None):
    tips = tips or {}
    out = []
    prev_dot = False
    chain = ""   # the dotted prefix we are walking, e.g. "os.path"
    for m in PY_RE.finditer(code):
        kind, tok = m.lastgroup, m.group()
        if kind == "cmt":
            out.append(tip_span(tok, "A comment: ignored when the code runs.",
                                None, "t-cmt"))
        elif kind == "str":
            out.append(tip_span(tok, "A string literal.", None, "t-str"))
        elif kind == "num":
            out.append(tip_span(tok, "A numeric literal.", None, "t-num"))
        elif kind == "name":
            cand = (chain + "." + tok) if (prev_dot and chain) else tok
            ov = tips.get(cand) or tips.get(tok)
            if ov:
                out.append(tip_span(tok, ov.get("tip", cand), ov.get("url"), "t-attr"))
                chain = cand
            elif prev_dot:
                # an attribute or method access (module member or object method)
                if cand in PY_MEMBER:
                    tip, url = _member_tip(cand)
                    out.append(tip_span(tok, tip, url, "t-attr"))
                elif tok in PY_METHOD:
                    out.append(tip_span(tok, PY_METHOD[tok],
                                        PY_METHOD_URL.get(tok), "t-attr"))
                else:
                    out.append(tip_span(tok, "Attribute or method accessed on the "
                                        "preceding value.", None, "t-name"))
                chain = cand
            elif tok in PY_KW:
                out.append(tip_span(tok, f"keyword {tok}\nPart of Python's control "
                                    "or declaration syntax.", PY_KW_URL, "t-kw"))
                chain = ""
            elif tok in PY_BUILTIN:
                out.append(tip_span(tok, PY_BUILTIN[tok],
                                    PY_BUILTIN_URL + f"#{tok}", "t-builtin"))
                chain = ""
            elif tok in PY_MODULE:
                desc = PY_MODULE[tok]
                out.append(tip_span(tok, f"module {tok}\n{desc[0].upper()}{desc[1:]}.",
                                    f"https://docs.python.org/3/library/{tok}.html",
                                    "t-mod"))
                chain = tok
            else:
                out.append(tip_span(tok, "Identifier: a variable, function, "
                                    "attribute or parameter name.", None, "t-name"))
                chain = tok
        else:
            out.append(esc(tok))
            if tok != ".":
                chain = ""
        prev_dot = (tok == ".")
    return "".join(out)


def lang_of(prefix):
    for w in re.findall(r"[A-Za-z0-9_]+", prefix or ""):
        if w in INTERP_LANG:
            return INTERP_LANG[w]
    return "text"


def split_embedded(cmd):
    """Split a shell command into [(lang, text), ...] segments, pulling out any
    embedded program (a -c/-e argument or a heredoc body) as its own segment.
    For -c/-e the whole concatenated word is replaced and the displayed text is
    the reconstructed program source."""
    spans = []  # (start, end, lang, text)
    for m in DASH_C_RE.finditer(cmd):
        spans.append((m.start(3), m.end(3), INTERP_LANG.get(m.group(1), "text"),
                      reconstruct_dashc(m.group(3))))
    for m in HEREDOC_RE.finditer(cmd):
        spans.append((m.start(3), m.end(3), lang_of(m.group(1)), m.group(3)))
    spans.sort()
    picked, end = [], -1
    for s, e, lang, text in spans:
        if s >= end:
            picked.append((s, e, lang, text))
            end = e
    segs, last = [], 0
    for s, e, lang, text in picked:
        if s > last:
            segs.append(("sh", cmd[last:s]))
        segs.append((lang, text))
        last = e
    if last < len(cmd):
        segs.append(("sh", cmd[last:]))
    return segs or [("sh", cmd)]


def embedded_panel(lang, code, tips=None):
    meta = LANG_META.get(lang, LANG_META["text"])
    if lang == "python":
        inner = annotate_python_inner(code, tips)
    elif lang == "bash":
        inner = annotate_bash_inner(code)
    else:
        inner = esc(code)
    more = (f"<a class='emb-more' href='{html.escape(meta['docs'])}' target='_blank' "
            f"rel='noreferrer'>Learn {meta['name']} syntax ↗</a>") if meta["docs"] else ""
    return (f"<div class='emb'><div class='emb-head'>"
            f"<span class='emb-lang'>{icon(meta['icon'])} {meta['name']}</span>"
            f"<span class='emb-path'>embedded program</span></div>"
            f"<div class='cmd emb-code'>{inner}</div>{more}</div>")


def embedded_langs(detail):
    return [lang for lang, _ in split_embedded(detail)
            if lang not in ("sh", "text")]


def filewrite_lang(detail):
    """Language of a Write/Edit body, inferred from its '# <path>' header."""
    first = (detail or "").splitlines()[0] if detail else ""
    return lang_from_path(first[2:]) if first.startswith("# ") else None


def filewrite_html(detail, lang, tips=None):
    """Render a written code file as a labeled, hover-annotated language panel."""
    lines = detail.splitlines()
    path = ""
    body = detail
    if lines and lines[0].startswith("# "):
        path = lines[0][2:].strip()
        body = "\n".join(lines[1:]).lstrip("\n")
    meta = LANG_META.get(lang, LANG_META["text"])
    if lang == "python":
        inner = annotate_python_inner(body, tips)
    elif lang == "bash":
        inner = annotate_bash_inner(body)
    else:
        inner = esc(body)
    more = (f"<a class='emb-more' href='{html.escape(meta['docs'])}' target='_blank' "
            f"rel='noreferrer'>Learn {meta['name']} syntax ↗</a>") if meta["docs"] else ""
    short = "/".join(path.split("/")[-3:]) if path.count("/") > 3 else path
    head = (f"<div class='emb-head'><span class='emb-lang'>{icon(meta['icon'])} "
            f"{meta['name']}</span><span class='emb-path' title='{html.escape(path)}'>"
            f"…/{esc(short)}</span></div>")
    return f"<div class='emb'>{head}<div class='cmd emb-code'>{inner}</div>{more}</div>"


def explainshell_link(detail):
    first = detail.splitlines()[0] if detail else ""
    return (f"<a class='shell-explain' href='{html.escape(explain_url(first))}' "
            f"target='_blank' rel='noreferrer'>{icon('terminal')} Explain this "
            "command on explainshell ↗</a>")


def whatran_html(detail, overrides=None, code_tips=None):
    segs = split_embedded(detail)
    code_segs = [(l, t) for l, t in segs if l not in ("sh", "text")]
    link = explainshell_link(detail)
    if not code_segs:
        return ("<div class='cmd'>" + annotate_bash_inner(detail, overrides)
                + "</div>" + link)
    # shell line with a placeholder chip where each embedded program sits
    parts = []
    for lang, text in segs:
        if lang in ("sh", "text"):
            parts.append(annotate_bash_inner(text, overrides) if lang == "sh"
                         else esc(text))
        else:
            meta = LANG_META.get(lang, LANG_META["text"])
            parts.append(f"<span class='emb-chip'>{icon(meta['icon'])} {meta['name']} "
                         "code, see below</span>")
    html_out = "<div class='cmd'>" + "".join(parts) + "</div>" + link
    for lang, text in segs:
        if lang not in ("sh", "text"):
            html_out += embedded_panel(lang, text, code_tips)
    return html_out


# ---------------------------------------------------------------------------
# output lexicon: explain the meaningful tokens that show up in command results
# ---------------------------------------------------------------------------
WIKI_PERM = "https://en.wikipedia.org/wiki/File-system_permissions#Notation_of_traditional_Unix_permissions"
WIKI_EXIT = "https://en.wikipedia.org/wiki/Exit_status"
WIKI_LINK = "https://en.wikipedia.org/wiki/Symbolic_link"

OUT_RE = re.compile(r"""
      (?P<url>https?://[^\s'"<>]+)
    | (?P<perm>[-dlbcps][rwxsStT-]{9})
    | (?P<exit>(?i:exit\ code\ \d+|exited\ with(?:\ code)?\ \d+))
    | (?P<err>(?<![\w])(?i:permission\ denied|no\ such\ file(?:\ or\ directory)?
        |command\ not\ found|not\ found|traceback|exception|fatal|errors?
        |failed|failure|denied|cannot)(?![\w]))
    | (?P<warn>(?<![\w])(?i:warnings?|deprecated)(?![\w]))
    | (?P<arrow>->)
    | (?P<path>(?<![\w])~?\.?/[\w.\-/]+)
""", re.X)

OUT_TIP = {
    "url": ("A web address printed in the output.", None),  # url filled per match
    "perm": ("Unix file mode. First char is the type (d=dir, l=link, -=file), "
             "then read/write/execute bits for owner, group and others.", WIKI_PERM),
    "exit": ("Process exit status. 0 means success; any other value means the "
             "command reported a failure.", WIKI_EXIT),
    "err": ("An error signal in the output. This is usually the first place to "
            "look when debugging why a step failed.", None),
    "warn": ("A warning. Not fatal, but worth reading before relying on the "
             "result.", None),
    "arrow": ("Symlink indicator. The name on the left points to the target on "
              "the right.", WIKI_LINK),
    "path": ("A filesystem path in the output.", None),
}
OUT_CLS = {"url": "t-url", "perm": "t-perm", "exit": "t-exit", "err": "t-err",
           "warn": "t-warn", "arrow": "t-op", "path": "t-path"}


def annotate_output(text, overrides=None):
    """Render command output with a hover bubble on the meaningful tokens."""
    overrides = overrides or {}
    out, last = [], 0
    for m in OUT_RE.finditer(text):
        out.append(esc(text[last:m.start()]))
        tok, kind = m.group(), m.lastgroup
        ov = overrides.get(tok)
        if ov:
            out.append(tip_span(tok, ov.get("tip", ""), ov.get("url"), "t-arg"))
        else:
            tip, url = OUT_TIP[kind]
            if kind == "url":
                url = tok
            out.append(tip_span(tok, tip, url, OUT_CLS[kind]))
        last = m.end()
    out.append(esc(text[last:]))
    return "<div class='cmd out'>" + "".join(out) + "</div>"


def alts_html(alts):
    """Render the 'other paths considered' branch points of a decision."""
    rows = []
    for a in alts:
        opt = esc(a.get("option", ""))
        tr = md(a.get("tradeoff", ""))
        url = a.get("url")
        link = (f"<a class='alt-l' href='{html.escape(url)}' target='_blank' "
                f"rel='noreferrer'>read more ↗</a>") if url else ""
        rows.append(f"<li class='alt'><span class='alt-opt'>{opt}</span>"
                    f"<span class='alt-tr'>{tr}{link}</span></li>")
    return "<ul class='alts-list'>" + "".join(rows) + "</ul>"


def chip(text, cls="", ic=None, style=""):
    sv = icon(ic) if ic else ""
    st = f" style='{style}'" if style else ""
    return f"<span class='chip {cls}'{st}>{sv}{esc(text)}</span>"


def kind_chip(kind, count, label):
    """A clickable header chip that toggles every node of `kind` on or off. The
    count lives in its own span so it can be recomputed live as the detail level
    changes (it then reflects how many of that kind show at the current level)."""
    info = KIND[kind]
    sv = icon(info["icon"])
    return (f"<button type='button' class='chip h-chip h-toggle {info['cls']}' "
            f"data-kind='{kind}' aria-pressed='true' "
            f"title='Click to hide or show {esc(label)}'>"
            f"{sv}<span class='h-n'>{count}</span> {esc(label)}</button>")


# material kinds (source types): (label, icon-name, css-class). A reader can
# tell docs from a tutorial at a glance. Extensible: custom types added by the
# goldie-source-types skill are merged from ~/.goldie/source_types.json,
# each carrying {label, icon, color, bg} and rendered with an inline style.
MAT_KIND = {
    "reference": ("reference", "bookmark", "mk-ref"),
    "docs":      ("docs", "bookOpen", "mk-ref"),
    "tutorial":  ("tutorial", "cap", "mk-tut"),
    "how-to":    ("how-to", "wrench", "mk-tut"),
    "language":  ("language", "code", "mk-lang"),
    "spec":      ("spec", "ruler", "mk-spec"),
    "book":      ("book", "book", "mk-book"),
    "principle": ("principle", "principle", "mk-book"),
}
MAT_KIND_STYLE = {}  # kind -> inline style for custom types


def _load_source_types():
    p = os.path.expanduser("~/.goldie/source_types.json")
    if not os.path.isfile(p):
        return
    try:
        data = json.load(open(p))
    except (json.JSONDecodeError, OSError):
        return
    for kind, m in data.items():
        MAT_KIND[kind] = (m.get("label", kind), m.get("icon", "bookmark"),
                          f"mk-{kind}")
        if m.get("color") or m.get("bg"):
            MAT_KIND_STYLE[kind] = (f"background:{m.get('bg', '#eee')};"
                                    f"color:{m.get('color', '#555')}")


_load_source_types()


def materials_html(materials):
    if not materials:
        return ("<div class='mat-empty'>No external references attached to this "
                "step.</div>")
    out = []
    for mm in materials:
        title = esc(mm.get("title", "Reference"))
        note = md(mm.get("note", ""))
        url = mm.get("url")
        doc = mm.get("doc")
        kind = mm.get("kind", "")
        label, favname, kcls = MAT_KIND.get(kind, ("", "link", ""))
        kstyle = MAT_KIND_STYLE.get(kind, "")
        st = f" style='{kstyle}'" if kstyle else ""
        kchip = (f"<span class='mat-kind {kcls}'{st}>{esc(label)}</span>") if label else ""
        fav = f"<span class='mat-fav'>{icon(favname)}</span>"
        summary = mm.get("summary")
        if url:
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            sum_html = (
                f"<details class='mat-sum'><summary>{icon('spark', 'ms-ic')} "
                "Read summary</summary>"
                f"<div class='mat-sum-body'>{md(summary)}</div></details>"
            ) if summary else ""
            out.append(
                "<div class='mat-link mat-card'>"
                f"<a class='mat-open' href='{html.escape(url)}' target='_blank' "
                f"rel='noreferrer'>{fav}"
                f"<span class='mat-body'><span class='mat-title'>{title}{kchip}</span>"
                f"<span class='mat-host'>{esc(host)}</span>"
                f"{f'<span class=mat-note>{note}</span>' if note else ''}</span></a>"
                f"{sum_html}</div>")
        elif doc:
            out.append(
                f"<details class='mat-doc'><summary><span class='mat-fav'>{icon('doc')}</span>"
                f"<span class='mat-title'>{title}</span>"
                "<span class='mat-host'>nested explainer</span></summary>"
                f"<div class='mat-doc-body'>{md(doc)}</div></details>")
        else:
            out.append(f"<div class='mat-link'>{fav}"
                       f"<span class='mat-body'><span class='mat-title'>{title}"
                       f"</span>{note}</span></div>")
    return "\n".join(out)


def node_html(n, idx):
    k = KIND.get(n["kind"], KIND["decision"])
    chips = [chip(k["label"], k["cls"])]
    if n.get("tool"):
        chips.append(chip(n["tool"], "c-tool", ic=TOOL_ICON.get(n["tool"], "code")))
        if n["tool"] == "Bash" and n.get("detail"):
            seen = []
            for lang in embedded_langs(n["detail"]):
                if lang in seen:
                    continue
                seen.append(lang)
                meta = LANG_META.get(lang, LANG_META["text"])
                chips.append(chip(meta["name"], "c-lang", ic=meta["icon"]))
        if n["tool"] in ("Write", "Edit") and n.get("detail"):
            flang = filewrite_lang(n["detail"])
            if flang:
                meta = LANG_META.get(flang, LANG_META["text"])
                chips.append(chip(meta["name"], "c-lang", ic=meta["icon"]))
    if n.get("status") == "error":
        chips.append(chip("error", "c-err", ic="alert"))
    prio = node_priority(n)
    if prio == "high":
        chips.append(chip("key", "c-key", ic="spark"))
    elif prio == "low":
        chips.append(chip("detail", "c-minor"))
    ts = n.get("timestamp", "")
    if ts:
        chips.append(chip(ts[11:19] if "T" in ts else ts, "c-time", ic="clock"))

    body = []
    if n.get("summary"):
        body.append(f"<div class='node-summary'>{md(n['summary'])}</div>")

    if n.get("detail"):
        flang = filewrite_lang(n["detail"]) if n.get("tool") in ("Write", "Edit") else None
        if n.get("tool") == "Bash":
            ran = whatran_html(n["detail"], n.get("detail_tips"), n.get("code_tips"))
            hint = ("<span class='dw-hint'>hover a token to learn what it does"
                    "</span>")
        elif flang:
            ran = filewrite_html(n["detail"], flang, n.get("code_tips"))
            hint = ""
        else:
            ran = f"<pre class='code'>{esc(n['detail'])}</pre>"
            hint = ""
        body.append(
            "<details class='drawer code-drawer'><summary>"
            f"{icon('code', 'dw-ic')} <span class='dw-label'>What ran</span>"
            f"{hint}{icon('chevron', 'chev')}</summary>"
            f"{ran}</details>")
    if n.get("result_excerpt"):
        out_html = annotate_output(n["result_excerpt"], n.get("result_tips"))
        body.append(
            "<details class='drawer code-drawer res-drawer'><summary>"
            f"{icon('result', 'dw-ic')} <span class='dw-label'>Result</span>"
            "<span class='dw-hint'>hover output for meaning</span>"
            f"{icon('chevron', 'chev')}</summary>"
            f"{out_html}</details>")

    if n.get("rationale"):
        body.append(
            "<div class='rationale'><span class='rat-tag'>WHY</span>"
            f"<div class='rat-body'>{md(n['rationale'])}</div></div>")

    if n.get("alternatives"):
        body.append(
            "<div class='alts'><div class='alts-head'>"
            f"{icon('fork', 'alts-ic')} Other paths considered "
            "<span class='alts-sub'>so you can debug or adapt this</span></div>"
            f"{alts_html(n['alternatives'])}</div>")

    mats = n.get("materials", [])
    badge = f"<span class='mat-count'>{len(mats)}</span>" if mats else ""
    label = "Sources & principles" if n["kind"] == "principle" else "Learn more"
    body.append(
        "<details class='drawer materials'><summary>"
        f"{icon('books', 'dw-ic')} {label} {badge}</summary>"
        f"<div class='mat-wrap'>{materials_html(mats)}</div></details>")

    transition = esc(n.get("transition", ""))
    brcls = "bridge" if n.get("transition") else "bridge empty"
    bridge = (f'<div class="{brcls}" data-transition="{transition}">'
              f'<span class="br-ic">{icon("chevron")}</span>'
              f'<span class="br-text">{transition}</span></div>')
    return f"""
    <div class="node collapsed {k['cls']}" data-kind="{n['kind']}" data-prio="{prio}" data-rank="{PRIORITY_RANK[prio]}" style="--i:{idx}">
      <div class="spine-dot">{icon(k['icon'])}</div>
      <div class="card">
        <div class="card-head" role="button" tabindex="0" aria-expanded="false" aria-label="Collapse or expand this step">
          <span class="node-ico">{icon(k['icon'])}</span>
          <div class="ch-text">
            <h3 class="node-title">{esc(short_title(n.get('title','Untitled step')))}</h3>
            <div class="chips">{''.join(chips)}</div>
          </div>
          <span class="node-caret">{icon('chevron')}</span>
        </div>
        <div class="card-body"><div class="cb-inner">
        {''.join(body)}
        </div></div>
      </div>
      {bridge}
    </div>"""


def detail_control(active):
    """The segmented Detail control: one button per level, the active one
    pre-marked so the report opens at the chosen depth even before any click."""
    btns = []
    for level, label, desc in DETAIL_LEVELS:
        cls = "dc-btn active" if level == active else "dc-btn"
        btns.append(f"<button type='button' class='{cls}' data-level='{level}' "
                    f"title='{esc(desc)}'>{esc(label)}</button>")
    return ("<div class='detail-ctl'>"
            "<span class='dc-lead'>Detail level</span>"
            f"<div class='dc-seg' role='group' aria-label='Detail level'>{''.join(btns)}</div>"
            "<span class='dc-count'></span></div>")


def graph_tools():
    """The fold controls: collapse or expand every node at once. Individual
    nodes also fold by clicking their header."""
    return ("<div class='graph-tools'>"
            f"<button type='button' class='gt-btn' data-act='expand'>"
            f"{icon('expand')}Expand all</button>"
            f"<button type='button' class='gt-btn' data-act='collapse'>"
            f"{icon('collapse')}Collapse all</button></div>")


def render(data, detail=None, parent=None):
    meta = data.get("meta", {})
    nodes = data.get("nodes", [])
    counts = {kk: sum(n["kind"] == kk for n in nodes) for kk in KIND}
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    # initial detail level: CLI flag wins, then meta.detail, then the default.
    detail = (detail or meta.get("detail") or DEFAULT_DETAIL).lower()
    if detail not in DETAIL_MIN_RANK:
        detail = DEFAULT_DETAIL

    # Header chips are now exclusively the clickable type filters: one per node
    # kind, each toggling that kind on or off. The project name and the generated
    # timestamp are plain context, so they live in a muted byline, not here.
    hc = [kind_chip("decision", counts["decision"], "decisions")]
    if counts["principle"]:
        hc.append(kind_chip("principle", counts["principle"], "principles"))
    if counts["security"]:
        hc.append(kind_chip("security", counts["security"], "security"))
    if counts["optimization"]:
        hc.append(kind_chip("optimization", counts["optimization"], "performance"))
    if counts["testing"]:
        hc.append(kind_chip("testing", counts["testing"], "testing"))
    if counts["networking"]:
        hc.append(kind_chip("networking", counts["networking"], "networking"))
    hc += [kind_chip("action", counts["action"], "actions"),
           kind_chip("prompt", counts["prompt"], "requests")]

    byline = (f"<div class='byline'>"
              f"<span class='by-item'>{icon('folder')}{esc(meta.get('project', 'project'))}</span>"
              f"<span class='by-item'>{icon('clock')}generated {esc(generated)}</span></div>")

    # Headline: prefer an explicit, hand-written meta.title. Otherwise derive a
    # short, clean title from the first prompt: take its first sentence and cap
    # it, so the header is never a wall of raw prompt text.
    headline = nd(meta.get("title") or "").strip()
    if not headline:
        fp = nd(meta.get("first_prompt") or "Session walkthrough").strip().split("\n", 1)[0]
        headline = re.split(r"(?<=[.!?:])\s", fp)[0].strip().rstrip(".:")
        if len(headline) > 62:
            headline = headline[:61].rsplit(" ", 1)[0] + "…"

    summary = nd(meta.get("summary") or
                 "A walkthrough of every decision and action in this session, each "
                 "with the reasoning behind it and the sources to understand it.").strip()

    parent_link = ""
    if parent:
        parent_link = (f"<a class='parent-link' href='{html.escape(parent)}' "
                       f"title='Go to parent doc' aria-label='Go to parent doc'>"
                       f"{icon('arrowUp')}</a>")

    body = "\n".join(node_html(n, i) for i, n in enumerate(nodes))
    return TEMPLATE.format(
        title=esc(meta.get("project", "Goldie") + " · Goldie report"),
        header_chips="".join(hc), headline=esc(headline), summary=esc(summary),
        byline=byline, detail_control=detail_control(detail), parent_link=parent_link,
        graph_tools=graph_tools(), detail=detail, goldie_mark=icon("goldie"),
        nodes=body, css=CSS, js=JS)


CSS = r"""
:root{
  --bg:#f7f6f3; --card:#ffffff; --ink:#2c2a26; --muted:#7a756c; --line:#e8e4dd;
  --gold:#eaa81f; --gold-soft:#fdedc4; --blue:#2f7fe6; --blue-soft:#e0eeff;
  --violet:#8b46ec; --violet-soft:#efe2ff; --teal:#08b6a4; --teal-soft:#ccf6ee;
  --red:#ef4b3c; --red-soft:#ffe2dc;
  --radius:14px; --shadow:0 1px 2px rgba(40,36,28,.06),0 8px 24px rgba(40,36,28,.05);
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(120% 80% at 50% -10%,#fffdf7,var(--bg));
  color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;}
.wrap{max-width:820px;margin:0 auto;padding:56px 24px 120px}
header{margin-bottom:40px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-weight:700;
  letter-spacing:.14em;font-size:12px;color:var(--gold);text-transform:uppercase}
.eyebrow .dot{width:9px;height:9px;border-radius:50%;background:var(--gold);
  box-shadow:0 0 0 4px var(--gold-soft)}
.eyebrow .goldie-mark{width:18px;height:18px}.eyebrow .goldie-mark .ic{width:18px;height:18px}
/* up-arrow back to the master index (the parent doc), inline with the eyebrow */
.top-row{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.parent-link{flex:none;display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:32px;border:1px solid var(--line);border-radius:50%;background:var(--card);
  color:var(--gold);text-decoration:none;box-shadow:var(--shadow);
  transition:transform .18s cubic-bezier(.2,.7,.3,1),box-shadow .2s,border-color .2s}
.parent-link:hover{transform:translateY(-2px);border-color:#e3d8bf;box-shadow:0 5px 14px rgba(40,36,28,.12)}
.parent-link .ic{width:16px;height:16px}
h1{font-size:30px;line-height:1.2;margin:14px 0 8px;font-weight:800;letter-spacing:-.02em;
  max-width:24ch}
.intro{color:var(--muted);font-size:15.5px;max-width:62ch;line-height:1.55}
/* muted context byline: project and generated time, kept out of the chip row */
.byline{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:14px;color:#a39d92;
  font-size:12.5px}
.byline .by-item{display:inline-flex;align-items:center;gap:6px}
.byline .ic{width:14px;height:14px;color:#b6b0a4}
/* type-filter row: a small lead label, then the clickable kind chips */
.filters{margin-top:18px}
.filters-lead{display:block;font-size:11px;font-weight:700;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);margin-bottom:9px}
.head-chips{display:flex;flex-wrap:wrap;gap:8px}
.how{margin-top:22px;padding:14px 18px;border:1px solid var(--line);border-radius:12px;
  background:linear-gradient(180deg,#fffdf7,#fbf9f3);display:flex;flex-direction:column;
  align-items:flex-start;gap:9px}
.how-lead{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  color:var(--gold);margin-bottom:2px}
.how-step{font-size:13px;color:var(--muted);line-height:1.65}
.how-step b{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;
  border-radius:50%;background:var(--gold-soft);color:#8a6d1f;font-size:11px;font-weight:700;
  margin-right:7px;vertical-align:-4px}
.how-step em{font-style:normal;font-weight:600;color:var(--ink)}
/* detail level control: a segmented switch that filters nodes by priority */
.detail-ctl{margin-top:14px;display:flex;align-items:center;flex-wrap:wrap;gap:10px 14px}
.dc-lead{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted)}
.dc-seg{display:inline-flex;background:#efece6;border:1px solid var(--line);border-radius:999px;
  padding:3px}
.dc-btn{appearance:none;border:none;background:transparent;cursor:pointer;font:inherit;
  font-size:12.5px;font-weight:600;color:var(--muted);padding:5px 14px;border-radius:999px;
  transition:.15s}
.dc-btn:hover{color:var(--ink)}
.dc-btn.active{background:var(--card);color:var(--ink);
  box-shadow:0 1px 2px rgba(40,36,28,.12);font-weight:700}
.dc-count{font-size:12px;color:#a39d92;font-variant-numeric:tabular-nums}
/* fold controls: collapse or expand every node at once */
.graph-tools{display:flex;gap:8px;margin-top:14px}
.gt-btn{display:inline-flex;align-items:center;gap:6px;font:inherit;font-size:12.5px;
  font-weight:600;color:var(--muted);background:#efece6;border:1px solid var(--line);
  border-radius:999px;padding:5px 13px;cursor:pointer;transition:.15s}
.gt-btn:hover{color:var(--ink);border-color:#ded8cf;background:#f3f0ea;transform:translateY(-1px)}
.gt-btn:active{transform:translateY(0)}
.gt-btn:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.gt-btn .ic{width:14px;height:14px;color:var(--gold)}
/* filter 1: hide nodes whose rank is below the chosen detail level */
.graph[data-detail="essentials"] .node:not([data-rank="3"]){display:none}
.graph[data-detail="standard"] .node[data-rank="1"]{display:none}
/* filter 2: hide a node kind toggled off via its header chip (composes with the
   detail filter; either rule hiding a node wins) */
.graph.hide-prompt .node[data-kind="prompt"],
.graph.hide-decision .node[data-kind="decision"],
.graph.hide-principle .node[data-kind="principle"],
.graph.hide-security .node[data-kind="security"],
.graph.hide-optimization .node[data-kind="optimization"],
.graph.hide-testing .node[data-kind="testing"],
.graph.hide-networking .node[data-kind="networking"],
.graph.hide-action .node[data-kind="action"]{display:none}
.chip{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:999px;
  font-size:12px;font-weight:600;background:#efece6;color:var(--muted);border:1px solid var(--line);
  white-space:nowrap}
.h-chip{padding:5px 12px;font-size:12.5px}
/* clickable type-filter chips */
.h-toggle{font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;
  transition:.15s;-webkit-appearance:none;appearance:none}
.h-toggle:hover{filter:brightness(.97)}
.h-toggle:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.h-toggle.off{opacity:.4;text-decoration:line-through;
  background:#f1efea;color:#a39d92;border-color:var(--line)}
.h-toggle.off .ic{opacity:.6}
/* none of this kind survive the current detail level: dimmed, not struck */
.h-toggle.empty:not(.off){opacity:.45}
.h-n{font-variant-numeric:tabular-nums}
.k-decision{background:var(--gold-soft);color:#8a6d1f;border-color:#efe1bd}
.k-action{background:var(--blue-soft);color:#2c5681;border-color:#cfe0f1}
.k-prompt{background:var(--violet-soft);color:#5a3fa0;border-color:#ddd2f5}
.k-principle{background:var(--teal-soft);color:#1f6b61;border-color:#bfe4dd}
.k-security{background:#fdeceb;color:#b0382c;border-color:#f3ccc7}
.k-optim{background:#fff2dd;color:#9a6a16;border-color:#f3dcae}
.k-test{background:#e6f4ec;color:#2f7d54;border-color:#c6e6d3}
.k-net{background:#e2f1f8;color:#1f6f93;border-color:#c2e2ef}
.k-summary{background:#efeae1;color:#5f574a;border-color:#ddd5c7}
.c-tool{background:#f0eee9;color:#5b5650;font-family:ui-monospace,Menlo,monospace}
.c-err{background:var(--red-soft);color:var(--red);border-color:#f0cbbb}
.c-key{background:var(--gold-soft);color:#8a6d1f;border-color:#efe1bd;
  text-transform:uppercase;letter-spacing:.06em;font-size:11px}
.c-minor{background:transparent;color:#b0aa9e;border-style:dashed;
  text-transform:uppercase;letter-spacing:.06em;font-size:11px}
.c-time{background:transparent;color:#a39d92}
.mat-count{background:var(--gold);color:#fff;border-radius:999px;padding:0 7px;
  font-size:11px;font-weight:700;margin-left:2px}
/* inline SVG icons (no emoji anywhere) */
.ic{width:1.05em;height:1.05em;flex:none;vertical-align:-0.15em}
.spine-dot .ic{width:13px;height:13px;vertical-align:0}
.chip .ic{margin-right:1px}
.mat-fav{display:flex;color:#9a948a}.mat-fav .ic{width:16px;height:16px}
.dw-ic .ic,.dw-ic{display:inline-flex}
.mat-kind .ic{display:none}

.graph{position:relative;padding-left:34px}
/* spine: each node draws the segment from its own dot down to the next node's,
   so the line starts at the first dot and stops at the last (no stub past either
   end). It tracks live height, so collapse/expand keeps the segments connected.
   Each segment takes its node's colour, turning the spine into a colour chain. */
.node::before{content:"";position:absolute;left:-23px;top:var(--bead-y);width:2px;
  height:calc(100% + var(--gap));background:var(--accent);z-index:0}
.node:last-child::before{display:none}
.node{position:relative;margin:0 0 var(--gap);opacity:0;transform:translateY(14px);
  animation:rise .5s cubic-bezier(.2,.7,.3,1) forwards;animation-delay:calc(var(--i)*60ms);
  --indent:0px;--bead-y:35px;--gap:42px;--accent:var(--gold);background:transparent}
/* each kind's accent colour, used by the spine, the bead and the hover flow */
.k-action{--accent:var(--blue)} .k-prompt{--accent:var(--violet)}
.k-principle{--accent:var(--teal)} .k-security{--accent:#ec3a2c}
.k-optim{--accent:#f7a008} .k-test{--accent:#12b866} .k-net{--accent:#119bd8}
.k-summary{--accent:#6e6699}
@keyframes rise{to{opacity:1;transform:none}}
/* priority staircase: lower-priority nodes step further right off the spine, so
   the key steps sit closest to the line and minor ones cascade outward */
.node[data-rank="2"]{--indent:28px}
.node[data-rank="1"]{--indent:56px}
/* the spine bead is gone: the kind icon badge (.node-ico) is the only marker in
   both states, so an open card shows one icon, not two. */
.spine-dot{display:none}
.k-action .spine-dot{background:var(--blue)} .k-prompt .spine-dot{background:var(--violet)}
.k-principle .spine-dot{background:var(--teal)}
.k-security .spine-dot{background:#c0392b} .k-optim .spine-dot{background:#d99412}
.k-test .spine-dot{background:#2f9d63} .k-net .spine-dot{background:#1f87b0}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:18px 20px;margin-left:var(--indent,0px);
  transition:transform .25s,box-shadow .28s,border-color .28s,background-color .28s,padding .28s,border-radius .3s cubic-bezier(.2,.7,.3,1)}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 10px rgba(40,36,28,.08),0 18px 40px rgba(40,36,28,.08);
  border-color:#ded8cf}
/* connector tick: stretches from the spine to the card, so it spans the staircase
   indent and visibly links each stepped-out card back to its bead */
.node::after{content:"";position:absolute;left:-22px;top:calc(var(--bead-y) - 1px);height:2px;
  width:calc(18px + var(--indent,0px));background:var(--line);
  background-size:220% 100%;transition:width .2s,background-color .2s}
/* on hover the connector lights up in the bubble's own colour and a brighter band
   flows along it toward the bubble, so the link reads as live current */
.node:hover::after{
  background-image:linear-gradient(90deg,
    color-mix(in srgb,var(--accent) 12%,transparent) 0%,
    var(--accent) 45%,
    color-mix(in srgb,#fff 65%,var(--accent)) 50%,
    var(--accent) 55%,
    color-mix(in srgb,var(--accent) 12%,transparent) 100%);
  animation:flow 1s linear infinite}
@keyframes flow{from{background-position:-120% 0}to{background-position:120% 0}}
/* and the same live current runs down the bubble's own spine segment to the next */
.node:hover::before{background-image:linear-gradient(180deg,
    var(--accent) 0%,
    color-mix(in srgb,#fff 65%,var(--accent)) 50%,
    var(--accent) 100%);
  background-size:100% 220%;animation:flowv 1.1s linear infinite}
@keyframes flowv{from{background-position:0 -120%}to{background-position:0 120%}}
/* story bridge: the connective sentence that ties this step to the next. It sits
   in the gap below the card, along the spine. When detail or type filters discard
   nodes, JS stitches their sentences together so the narrative stays unbroken. */
.bridge{display:flex;align-items:flex-start;gap:7px;margin:11px 0 1px;padding-left:3px;
  color:#94897c;font-size:12.5px;font-style:italic;line-height:1.5;max-width:60ch}
.bridge.empty{display:none}
.br-ic{flex:none;margin-top:1px;color:#c4bdb0;line-height:0}
.br-ic .ic{width:13px;height:13px;transform:rotate(90deg)}
.br-text{flex:1;min-width:0}
.k-decision .card{border-left:3px solid var(--gold)}
.k-action .card{border-left:3px solid var(--blue)}
.k-prompt .card{border-left:3px solid var(--violet)}
.k-principle .card{border-left:3px solid var(--teal);
  background:linear-gradient(180deg,#fbfffe,#fff)}
.k-security .card{border-left:3px solid var(--accent);background:linear-gradient(180deg,#fffbfb,#fff)}
.k-optim .card{border-left:3px solid var(--accent);background:linear-gradient(180deg,#fffdf8,#fff)}
.k-test .card{border-left:3px solid var(--accent);background:linear-gradient(180deg,#fafffb,#fff)}
.k-security .node-title{color:#a8362b} .k-optim .node-title{color:#8a6012}
.k-test .node-title{color:#256b45}
.k-test .rationale{background:linear-gradient(#f3fbf6,#e8f6ee);border-color:#cbe8d6}
.k-test .rat-tag{color:#2f9d63}
.k-net .card{border-left:3px solid var(--accent);background:linear-gradient(180deg,#f8fdff,#fff)}
.k-net .node-title{color:#1a647f}
.k-summary .card{border-left:3px solid var(--accent);background:linear-gradient(180deg,#fcfaf6,#fff)}
.k-summary .node-title{color:#5a5246}
.k-net .rationale{background:linear-gradient(#f2fafd,#e6f3f9);border-color:#c4e3ef}
.k-net .rat-tag{color:#1f87b0}
.k-security .rationale{background:linear-gradient(#fff6f5,#fdeceb);border-color:#f3cdc8}
.k-security .rat-tag{color:#c0392b}
.k-optim .rationale{background:linear-gradient(#fffaf0,#fff3df);border-color:#f0dcb0}
.k-optim .rat-tag{color:#cf8c14}
/* the card header doubles as a collapse toggle for its node */
.card-head{display:flex;align-items:flex-start;gap:12px;margin:-6px -8px 6px;padding:6px 8px;
  border-radius:10px;cursor:pointer;user-select:none;transition:background .15s}
.card-head:hover{background:rgba(202,162,74,.08)}
.card-head:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
/* the kind icon, rendered as a round badge. It is small in the open card and
   swells into the big bubble face when the node collapses, morphing on one
   element so the open/closed states read as the same object resizing. */
.node-ico{flex:none;align-self:flex-start;display:grid;place-items:center;
  position:relative;z-index:2;       /* the face sits in front of the spine lines */
  width:34px;height:34px;border-radius:50%;color:#fff;background:var(--accent);
  box-shadow:0 2px 6px rgba(40,36,28,.16);
  transition:width .32s cubic-bezier(.2,.7,.3,1),height .32s cubic-bezier(.2,.7,.3,1),
    box-shadow .28s,transform .24s cubic-bezier(.2,.7,.3,1)}
.node-ico .ic{width:18px;height:18px;transition:width .32s cubic-bezier(.2,.7,.3,1),
  height .32s cubic-bezier(.2,.7,.3,1)}
.ch-text{display:flex;flex-direction:column;gap:8px;flex:1;min-width:0}
.node-caret{flex:none;margin-top:3px;color:#c4bdb0;line-height:0;
  transition:transform .25s cubic-bezier(.2,.7,.3,1),color .15s}
.node-caret .ic{width:15px;height:15px}
.card-head:hover .node-caret{color:var(--gold)}
.card-head[aria-expanded="true"] .node-caret{transform:rotate(90deg)}
/* collapsible body: smooth height via the grid-template-rows 1fr/0fr trick */
.card-body{display:grid;grid-template-rows:1fr;
  transition:grid-template-rows .3s cubic-bezier(.2,.7,.3,1),opacity .22s ease}
.cb-inner{overflow:hidden;min-height:0}
/* once a card is open, let its content overflow so hover tooltips are not clipped
   at the card edge. The switch is delayed past the reveal so collapsing still clips
   cleanly; collapsing reverts to hidden immediately (base rule, no transition). */
.node:not(.collapsed) .cb-inner{overflow:visible;transition:overflow 0s .32s}
.node.collapsed .card-body{grid-template-rows:0fr;opacity:0}
/* collapsed node = a graph bubble: the kind icon swells into a big round face
   with the title beside it, the card chrome (border, fill, padding, body) all
   melting away. Clicking shrinks the face back to a badge and the full card
   grows around it, so open and closed read as one object resizing. */
.node.collapsed{--bead-y:39px}                   /* spine meets the big face centre */
.node.collapsed .card{background:transparent;border:none;box-shadow:none;
  padding:4px 0;border-radius:0}
.node.collapsed .card:hover{transform:none}
.node.collapsed .card-head{margin:0;padding:6px 4px;gap:16px;align-items:center}
.node.collapsed .card-head:hover{background:transparent}
.node.collapsed .node-ico{width:58px;height:58px;box-shadow:0 5px 16px rgba(40,36,28,.20)}
.node.collapsed .node-ico .ic{width:27px;height:27px}
.node.collapsed:hover .node-ico{transform:scale(1.07);box-shadow:0 8px 22px rgba(40,36,28,.26)}
.node.collapsed .chips{display:none}
.node.collapsed .node-caret{display:none}
.node.collapsed .node-title{font-size:15.5px}
/* the spine connector reaches into the big face when collapsed */
.node.collapsed::after{width:calc(34px + var(--indent,0px))}
.node-title{font-size:16px;margin:0;font-weight:700;letter-spacing:-.01em}
.k-principle .node-title{color:#1f6b61}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.node-summary{color:#534f48;font-size:14.5px}
.node-summary p{margin:.5em 0}
.rationale{display:flex;gap:10px;margin-top:12px;padding:12px 14px;border-radius:10px;
  background:linear-gradient(#fffdf6,#fdf8ea);border:1px solid #f0e6c8}
.k-principle .rationale{background:linear-gradient(#f4fbf9,#e9f6f3);border-color:#cdeae3}
.rat-tag{font-size:10px;font-weight:800;letter-spacing:.12em;color:var(--gold);margin-top:2px}
.k-principle .rat-tag{color:var(--teal)}
.rat-body{font-size:14px;color:#5f5743}
.k-principle .rat-body{color:#3c5a55}
.rat-body p{margin:.3em 0}

.drawer{margin-top:10px;border-top:1px dashed var(--line);padding-top:8px}
.drawer summary{cursor:pointer;list-style:none;font-size:13px;font-weight:600;
  color:var(--muted);display:flex;align-items:center;gap:8px;user-select:none}
.drawer summary::-webkit-details-marker{display:none}
.dw-ic{font-family:ui-monospace,monospace;font-size:12px;color:var(--gold)}
.dw-hint{font-weight:500;font-size:11.5px;color:#b4ad9f;font-style:italic;margin-left:auto}
.drawer[open] summary{color:var(--ink)}

/* prominent, obviously-clickable What ran / Result toggles */
.code-drawer{border-top:none;margin-top:14px;padding-top:0}
.code-drawer>summary{padding:10px 14px;border:1px solid #d8c9f2;border-radius:10px;
  background:linear-gradient(#7c4ddb,#6b3fce);color:#fff;font-size:13.5px;font-weight:800;
  letter-spacing:.01em;box-shadow:0 2px 8px rgba(108,63,206,.28);transition:.15s}
.code-drawer>summary:hover{background:linear-gradient(#8a5ce8,#7a4ee0);
  box-shadow:0 4px 14px rgba(108,63,206,.38)}
.code-drawer>summary .dw-ic{font-size:13px;color:#fff}
.code-drawer>summary .dw-label{font-weight:800}
.code-drawer>summary .dw-hint{color:#e6dafb;opacity:.95}
.code-drawer>summary .chev{margin-left:8px;font-size:12px;color:#fff;
  transition:transform .2s}
.code-drawer[open]>summary .chev{transform:rotate(90deg)}
.code-drawer[open]>summary{border-bottom-left-radius:0;border-bottom-right-radius:0;
  border-bottom-color:transparent}
.code-drawer .dw-hint{margin-left:auto}
.res-drawer>summary{background:linear-gradient(#eef4fb,#e6eff8);border-color:#cfe0f1;
  color:#2c5681;box-shadow:0 1px 2px rgba(40,36,28,.05)}
.res-drawer>summary:hover{border-color:var(--blue);background:#e3eefa}
.res-drawer>summary .dw-ic,.res-drawer>summary .chev{color:var(--blue)}
.res-drawer>summary .dw-hint{color:#7e93ad;opacity:1}
.code-drawer .cmd,.code-drawer .code,.code-drawer .emb{margin-top:0;
  border-top-left-radius:0;border-top-right-radius:0}
.drawer .code,.drawer .cmd,.drawer .mat-wrap{animation:fade .25s ease}
@keyframes fade{from{opacity:0;transform:translateY(-4px)}to{opacity:1}}
.code{background:#1f1d1a;color:#e8e3d8;border-radius:8px;padding:12px 14px;margin:8px 0 2px;
  font:12.5px/1.55 ui-monospace,Menlo,monospace;overflow:auto;white-space:pre-wrap;word-break:break-word}
.code.dim{background:#2a2824;color:#bdb6a6}
code{background:#f0ece3;border-radius:5px;padding:1px 5px;font:12.5px ui-monospace,Menlo,monospace}

/* annotated shell command: overflow visible so tooltips are not clipped */
.cmd{background:#1f1d1a;color:#d7d1c5;border-radius:8px;padding:12px 14px;margin:8px 0 2px;
  font:12.5px/1.7 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word;
  overflow:visible}
.tok{position:relative;border-radius:3px;cursor:help;transition:background .12s}
.tok:hover,.tok:focus{background:rgba(255,255,255,.10);outline:none}
.t-cmd{color:#f0c969;font-weight:600} .t-flag{color:#7fb2e8} .t-str{color:#9ed98b}
.t-var{color:#e8a76b} .t-op{color:#e98aa8;font-weight:600} .t-path{color:#cfc8bb}
.t-arg{color:#d7d1c5} .t-sub{color:#7fd4b0;font-weight:600}
.t-redir{color:#e0a85a;font-weight:600} .t-dev{color:#9ed0e8;font-style:italic}
.t-script{color:#7fd4b0;font-weight:600;text-decoration:underline dotted rgba(255,255,255,.45);
  text-underline-offset:3px}
.cmd.out{background:#2a2824;color:#bdb6a6;line-height:1.65}
.t-url{color:#7fb2e8;text-decoration:underline} .t-perm{color:#6fd0c4}
.t-exit{color:#f0c969;font-weight:600} .t-err{color:#ef8a6a;font-weight:600}
.t-warn{color:#e8c069;font-weight:600}
/* embedded program panel + python tokens */
.emb-chip{display:inline-block;padding:1px 9px;border-radius:6px;background:#3a4a5a;
  color:#cfe0f1;font-weight:600;font-size:11.5px}
/* overflow visible so a tooltip on the first code line is not clipped by the panel;
   corners are rounded per child instead of by clipping the container */
.emb{margin:8px 0 2px;border:1px solid #34302a;border-radius:8px;overflow:visible;
  background:#17150f}
.emb-head{display:flex;align-items:center;gap:9px;padding:8px 12px;background:#221f18;
  border-radius:7px 7px 0 0;font:600 12px ui-monospace,Menlo,monospace;color:#cdc6b8}
.emb>:last-child{border-radius:0 0 7px 7px}
.emb-lang{flex:none;background:#2f6b61;color:#eafff8;border-radius:999px;padding:2px 10px;
  font-size:11px;font-weight:700}
.emb-path{flex:1;min-width:0;color:#8f897b;font-size:11.5px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.emb-code{margin:0;border-radius:0;background:#17150f}
.emb-more{display:inline-block;margin:0;padding:8px 12px;font-size:12px;font-weight:700;
  color:#7fb2e8;text-decoration:none;background:#221f18;width:100%}
.emb-more:hover{text-decoration:underline}
.shell-explain{display:flex;align-items:center;gap:6px;padding:7px 12px;font-size:12px;
  font-weight:700;color:#2c5681;text-decoration:none;background:#eef4fb;
  border:1px solid #cfe0f1;border-top:none;border-radius:0 0 8px 8px}
.shell-explain:hover{background:#e3eefa;text-decoration:underline}
.t-kw{color:#d987c9;font-weight:600} .t-builtin{color:#f0c969} .t-mod{color:#6fd0c4}
.t-name{color:#d7d1c5} .t-num{color:#e8a76b} .t-cmt{color:#7c766a;font-style:italic}
.t-attr{color:#9fd0e8}
.c-lang{background:#e7f6ee;color:#1f7a4d;border-color:#bfe4cf;font-weight:700}
.tok .tip{visibility:hidden;opacity:0;position:absolute;left:0;bottom:calc(100% + 8px);
  width:max-content;max-width:300px;background:#fff;color:var(--ink);border:1px solid var(--line);
  border-radius:10px;box-shadow:0 8px 28px rgba(20,18,14,.22);padding:10px 12px;z-index:20;
  font:13px/1.45 -apple-system,Inter,sans-serif;transition:opacity .14s,transform .14s;
  transform:translateY(4px);text-align:left;white-space:normal}
.tok .tip::after{content:"";position:absolute;left:16px;top:100%;border:6px solid transparent;
  border-top-color:#fff}
.tok:hover .tip,.tok:focus .tip{visibility:visible;opacity:1;transform:translateY(0);
  transition-delay:.12s}
.tip-sig{display:block;font:600 12.5px/1.4 ui-monospace,Menlo,monospace;color:#1f1d1a;
  padding-bottom:5px;margin-bottom:5px;border-bottom:1px solid var(--line);
  white-space:pre-wrap;word-break:break-word}
.tip-d{display:block;color:#4a453d}
.tip-l{display:inline-block;margin-top:7px;font-size:12px;font-weight:700;color:var(--blue);
  text-decoration:none}
.tip-l:hover{text-decoration:underline}

/* other paths considered */
.alts{margin-top:12px;padding:12px 14px;border-radius:10px;background:#f3f7fb;
  border:1px solid #d9e6f2}
.alts-head{font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
  color:var(--blue);display:flex;align-items:center;gap:7px}
.alts-ic{font-size:14px}
.alts-sub{font-weight:600;letter-spacing:0;text-transform:none;font-size:11.5px;
  color:#9bb0c4;font-style:italic}
.alts-list{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-direction:column;gap:8px}
.alt{display:flex;gap:10px;padding-left:12px;border-left:2px solid #bcd3e8}
.alt-opt{font-weight:700;font-size:13.5px;color:#2c5681;flex:0 0 auto;min-width:120px}
.alt-tr{font-size:13.5px;color:#52617a}
.alt-tr p{margin:0;display:inline}
.alt-l{margin-left:6px;font-size:12px;font-weight:700;color:var(--blue);text-decoration:none}
.alt-l:hover{text-decoration:underline}

.mat-kind{display:inline-block;margin-left:7px;padding:1px 7px;border-radius:999px;
  font-size:10px;font-weight:700;letter-spacing:.03em;vertical-align:middle;
  text-transform:uppercase;background:#eee;color:#666}
.mk-ref{background:#eef1f4;color:#5a6675} .mk-tut{background:#e7f6ee;color:#1f7a4d}
.mk-lang{background:#efeafb;color:#5a3fa0} .mk-spec{background:#fdf3df;color:#8a6d1f}
.mk-book{background:#f6eae3;color:#9a5a37}
.mat-wrap{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.mat-link{display:flex;gap:11px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;
  text-decoration:none;color:inherit;background:#fcfbf8;transition:.18s}
a.mat-link:hover{border-color:var(--gold);background:var(--gold-soft);transform:translateX(2px)}
.mat-card{flex-direction:column;gap:0;padding:0;overflow:hidden}
.mat-card:hover{border-color:var(--gold)}
.mat-open{display:flex;gap:11px;padding:10px 12px;text-decoration:none;color:inherit}
.mat-open:hover{background:var(--gold-soft)}
.mat-sum{border-top:1px dashed var(--line);background:#fbfaf6}
.mat-sum summary{cursor:pointer;list-style:none;padding:7px 12px;font-size:12px;
  font-weight:700;color:var(--gold);display:flex;align-items:center;gap:6px;user-select:none}
.mat-sum summary::-webkit-details-marker{display:none}
.ms-ic{font-size:11px}
.mat-sum[open] summary{color:#8a6d1f}
.mat-sum-body{padding:2px 14px 12px;font-size:13.5px;color:#534f48;animation:fade .2s ease}
.mat-sum-body p{margin:.35em 0}
.mat-fav{font-size:15px;margin-top:1px}
.mat-body{display:flex;flex-direction:column;gap:1px}
.mat-title{font-weight:700;font-size:14px;color:var(--ink)}
.mat-host{font-size:12px;color:var(--blue)}
.mat-note{font-size:12.5px;color:var(--muted);margin-top:3px}
.mat-doc{border:1px solid var(--line);border-radius:10px;background:#fcfbf8;overflow:hidden}
.mat-doc summary{display:flex;gap:11px;align-items:center;padding:10px 12px;cursor:pointer;
  list-style:none;font-weight:700}
.mat-doc summary::-webkit-details-marker{display:none}
.mat-doc[open] summary{border-bottom:1px solid var(--line);background:#faf8f2}
.mat-doc-body{padding:12px 16px;font-size:14px;color:#534f48}
.md-h{margin:.6em 0 .3em;line-height:1.25;color:var(--ink);font-weight:700}
.md-h1{font-size:18px} .md-h2{font-size:16px} .md-h3{font-size:14.5px;color:#5f5743}
.md-h:first-child{margin-top:0}
.mat-empty{font-size:13px;color:#a39d92;font-style:italic;padding:4px 0}
footer{margin-top:60px;text-align:center;color:#b6b0a4;font-size:12.5px}
footer b{color:var(--gold)}
/* respect a reader who prefers less motion: keep state changes, drop the animation */
@media (prefers-reduced-motion:reduce){
  .node{animation:none;opacity:1;transform:none}
  .card,.card-body,.spine-dot,.node::after,.node::before,.node-caret,.node-ico,
  .node-ico .ic,.gt-btn,.drawer .code,.drawer .cmd,.drawer .mat-wrap{transition:none;animation:none}
}
"""

JS = r"""
document.querySelectorAll('.drawer.materials').forEach(d=>{
  d.addEventListener('toggle',()=>{if(d.open)d.scrollIntoView({behavior:'smooth',block:'nearest'});});
});

// Detail level: clicking a segment filters nodes by priority and updates the
// live count. CSS does the hiding from the graph's data-detail attribute.
(function(){
  var graph=document.querySelector('.graph');
  if(!graph)return;
  var MINRANK={essentials:3,standard:2,everything:1};
  var btns=document.querySelectorAll('.dc-btn');
  var toggles=document.querySelectorAll('.h-toggle');
  var count=document.querySelector('.dc-count');
  var nodes=[].slice.call(graph.querySelectorAll('.node'));
  function isVisible(n){return getComputedStyle(n).display!=='none';}
  function bridgeText(n){var b=n.querySelector('.bridge');return b?b.getAttribute('data-transition'):'';}
  // each visible node's bridge narrates the path to the next visible node: its own
  // sentence plus the sentences of every discarded node in between, stitched up.
  function updateBridges(){
    for(var i=0;i<nodes.length;i++){
      var br=nodes[i].querySelector('.bridge');
      if(!br)continue;
      if(!isVisible(nodes[i])){br.classList.add('empty');continue;}
      var parts=[],own=bridgeText(nodes[i]);
      if(own)parts.push(own);
      var next=false;
      for(var j=i+1;j<nodes.length;j++){
        if(isVisible(nodes[j])){next=true;break;}
        var t=bridgeText(nodes[j]);if(t)parts.push(t);
      }
      var span=br.querySelector('.br-text');
      if(!next||!parts.length){br.classList.add('empty');if(span)span.textContent='';continue;}
      if(span)span.textContent=parts.join(' ');
      br.classList.remove('empty');
    }
  }
  function update(){
    var min=MINRANK[graph.getAttribute('data-detail')]||1;
    // each type chip shows how many of its kind survive the current level
    toggles.forEach(function(b){
      var k=b.dataset.kind,c=0;
      nodes.forEach(function(n){
        if(n.getAttribute('data-kind')===k && +n.getAttribute('data-rank')>=min)c++;
      });
      var ns=b.querySelector('.h-n');
      if(ns)ns.textContent=c;
      b.classList.toggle('empty',c===0);
    });
    if(count){
      var vis=0;
      nodes.forEach(function(n){if(getComputedStyle(n).display!=='none')vis++;});
      count.textContent='showing '+vis+' of '+nodes.length+' steps';
    }
    updateBridges();
  }
  btns.forEach(function(b){
    b.addEventListener('click',function(){
      graph.setAttribute('data-detail',b.dataset.level);
      btns.forEach(function(x){x.classList.toggle('active',x===b);});
      update();
    });
  });
  // Type chips: each opts its node kind in or out, composing with the level.
  document.querySelectorAll('.h-toggle').forEach(function(b){
    b.addEventListener('click',function(){
      var off=graph.classList.toggle('hide-'+b.dataset.kind);
      b.classList.toggle('off',off);
      b.setAttribute('aria-pressed',off?'false':'true');
      update();
    });
  });
  update();
})();

// Per-node fold: a card header is a toggle; the fold-all buttons drive them all.
(function(){
  function setNode(node,collapsed){
    node.classList.toggle('collapsed',collapsed);
    var h=node.querySelector('.card-head');
    if(h)h.setAttribute('aria-expanded',collapsed?'false':'true');
  }
  document.querySelectorAll('.card-head').forEach(function(h){
    var node=h.closest('.node');
    function toggle(){setNode(node,!node.classList.contains('collapsed'));}
    h.addEventListener('click',toggle);
    h.addEventListener('keydown',function(e){
      if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle();}
    });
  });
  document.querySelectorAll('.gt-btn').forEach(function(b){
    b.addEventListener('click',function(){
      var collapse=b.dataset.act==='collapse';
      document.querySelectorAll('.node').forEach(function(n){setNode(n,collapse);});
    });
  });
})();
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{css}</style></head>
<body><div class="wrap">
<header>
  <div class="top-row">{parent_link}<span class="eyebrow"><span class="goldie-mark">{goldie_mark}</span>Goldie walkthrough</span></div>
  <h1>{headline}</h1>
  <p class="intro">{summary}</p>
  {byline}
  {detail_control}
  <div class="filters">
    <span class="filters-lead">Filter by type</span>
    <div class="head-chips">{header_chips}</div>
  </div>
  {graph_tools}
  <div class="how">
    <span class="how-lead">How to read this</span>
    <span class="how-step"><b>1</b> Scroll the cards top to bottom: each is one step Claude took.</span>
    <span class="how-step"><b>2</b> Cards start folded: click a card's <em>header</em> to open it, or use <em>Expand all</em>.</span>
    <span class="how-step"><b>3</b> Open <em>What ran</em> and <em>Learn more</em> for the command, reasoning and sources.</span>
    <span class="how-step"><b>4</b> Set the <em>detail level</em> to hide minor steps, or click a <em>type chip</em> above to hide that kind.</span>
  </div>
</header>
<main class="graph" data-detail="{detail}">
{nodes}
</main>
<footer>Generated by <b>Goldie</b>, keeping you in touch with your codebase.</footer>
</div><script>{js}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nodes", help="enriched nodes JSON (or - for stdin)")
    ap.add_argument("-o", "--out", default="goldie-report.html")
    ap.add_argument("--detail", choices=list(DETAIL_MIN_RANK),
                    help="initial detail level (default: meta.detail or standard)")
    ap.add_argument("--id", help="explicit report id for the history manifest "
                    "(default: the session id, or a slug of the title)")
    ap.add_argument("--register", action="store_true",
                    help="record this report in the reports-dir history manifest "
                    "(index.json beside the output file)")
    ap.add_argument("--parent", help="href of the master index for the 'Go to "
                    "parent doc' back-link (default: ../goldie-report.html when "
                    "--register is set)")
    args = ap.parse_args()
    raw = sys.stdin.read() if args.nodes == "-" else open(args.nodes).read()
    data = json.loads(raw)
    out_parent = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_parent, exist_ok=True)
    # registered reports live in reports/<id>.html, so the index is one level up
    parent = args.parent or ("../goldie-report.html" if args.register else None)
    with open(args.out, "w") as fh:
        fh.write(render(data, detail=args.detail, parent=parent))
    print(f"goldie: rendered {len(data.get('nodes', []))} nodes -> {args.out}",
          file=sys.stderr)
    if args.register:
        import history
        entry = history.entry_from(data.get("meta", {}), data.get("nodes", []),
                                   args.out)
        if args.id:
            entry["id"] = history.slug(args.id)
        reports_dir = os.path.dirname(os.path.abspath(args.out))
        history.upsert(reports_dir, entry)
        print(f"goldie: registered '{entry['id']}' in {reports_dir}/index.json",
              file=sys.stderr)


if __name__ == "__main__":
    main()
