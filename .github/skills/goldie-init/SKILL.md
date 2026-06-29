---
name: goldie-init
description: Initialize Goldie for a repo. A short wizard that scans the project, reads AGENTS.md and other doc files to understand the codebase, asks the user a few questions, and saves a project profile so later Goldie reports are tailored (right stack, right audience, right focus). Use when the user runs "goldie init", asks to set up or configure Goldie for this repo, or when no `.goldie/profile.json` exists yet.
license: MIT
---

# Goldie Init: profile the repo so reports are tailored

Run this once per repo. It produces `.goldie/profile.json`, which the main
`goldie` skill reads to tailor every report: the languages it explains, the
audience it writes for, the conventions it respects, and the topics it
emphasizes.

## House style

Never use an em dash or en dash. No dash as punctuation in prose. Hyphenated
compounds are fine. Never use emoji; Goldie uses hand-drawn SVG icons.

## What a good report looks like (set the repo up to hit this)

Goldie reports meet a high bar. Initialize the repo so reports can reach it:

- **Teaching nodes**: decisions carry alternatives and a WHY; principle,
  security, performance and testing nodes explain the ideas behind the work.
- **Docstring tooltips**: hovering a function, member or method shows a monospace
  signature line then a one-line description, with a "read more" link to the
  exact official-docs definition. Members resolve down the dotted chain
  (`os.path.expanduser`), and module tooltips summarize what the module contains.
- **Command literacy**: shell tokens (commands, subcommands, flags, redirections
  like `2>`, device files like `/dev/null`) and embedded or written code panels
  (`python3 -c`, heredocs, `.py` files) are hover-annotated, and shell links out
  to explainshell.
- **Trusted sources**: references are tagged by kind, deep-linked to the exact
  section, with a Read-summary, preferring the user's resource library and LabEx
  for hands-on topics.

The persistent registries that power this (all under `~/.goldie/`, shared
across projects) are what you prime in step 4:

- `resources.json` (the resource library), `source_types.json` + `icons.json`
  (source types and their SVG icons), `py_members.json` (function and member
  tooltips). The per-project `.goldie/profile.json` ties them to this repo.

## Wizard steps

### 1. Scan the repo

```bash
python3 ~/.copilot/skills/goldie-init/scripts/profile.py scan
```

This reports the doc files present (AGENTS.md, CLAUDE.md, README, CONTRIBUTING,
ARCHITECTURE, .cursorrules, ...), the manifests and stacks (package.json,
pyproject.toml, go.mod, Dockerfile, ...), the languages by file count, and short
excerpts of AGENTS.md / CLAUDE.md.

### 2. Read the docs

Actually read the important doc files the scan found, in full: `AGENTS.md` first,
then `CLAUDE.md`, `README`, `ARCHITECTURE`, `CONTRIBUTING`. Extract:

- what the project is and who it is for,
- the stack and key libraries,
- the conventions and rules the team follows (these shape how Goldie should
  describe changes, for example "we never use em dashes" or "prefer composition").

Do not guess. Pull these from the actual files.

### 3. Ask the user a few questions

Ask the user to confirm or fill gaps the scan and docs cannot answer. Keep it
short (2 to 4 questions). Good ones:

- **Audience**: who reads these reports (juniors learning, a senior team, mixed,
  external stakeholders)? This sets how much teaching depth to include.
- **Focus**: what should Goldie emphasize (security, performance, architecture and
  principles, testing, all of them)?
- **Depth**: concise summaries, or thorough with every decision and alternative?
- Anything the docs left ambiguous (primary language if several, the one
  convention that matters most).

### 4. Prime Goldie's registries for this repo

This is what makes the first report as rich as a tenth one. Set up the shared
registries from what you learned. Do the parts that fit the project; skip what
does not apply.

**a. Seed the resource library** with the best learning source for each detected
language and tool, so the research phase already has them on hand. Prefer LabEx
(`https://labex.io/learn/<topic>`) for linux, shell, git, docker, devops,
cybersecurity, databases, mysql, wireshark, data science and python; add the
official docs for every other framework in the stack. Use the `goldie-resources`
skill or `resources.py add`, tagging each with a `kind` and a `summary`.

**b. Pre-seed function and member tooltips for the libraries this repo actually
uses.** Read the manifests and a sample of imports to list the real dependencies.
For the notable functions, methods and members they expose, fetch the official
docs and persist docstring-style tooltips so code panels explain them from the
start. For Python, write `~/.goldie/py_members.json`:

```json
{
  "requests.get": {"tip": "requests.get(url, **kwargs)\nSend a GET request and return a Response object.", "url": "https://requests.readthedocs.io/en/latest/api/#requests.get"},
  "np.array": {"tip": "numpy.array(object, dtype=None)\nCreate an n-dimensional array.", "url": "https://numpy.org/doc/stable/reference/generated/numpy.array.html"}
}
```

Each value is a small docstring (a signature line, a newline, then one
description line) plus a link to the full definition, the same format the
built-in lexicon uses. Read the docs; do not guess a signature. (Deep per-token
tooltips currently apply to Python and shell. For other languages the lasting
value is the language reference and tutorial in the library, not per-token tips,
so put your effort into part a for those.)

**c. Add domain source types with custom SVG icons.** Decide whether the project
needs kinds beyond the built-ins (reference, docs, tutorial, how-to, language,
spec, book). A security repo often wants `advisory` or `cve`; a data project
wants `dataset`, `notebook` or `paper`; an infra repo wants `runbook`. Create
each genuinely useful one with a hand-drawn SVG icon (never emoji) via the
`goldie-source-types` skill:

```bash
python3 ~/.copilot/skills/goldie-source-types/scripts/source_types.py add \
  --kind runbook --label "Runbook" --icon-name runbook \
  --color "#1f6b61" --bg "#e2f3f0" \
  --svg '<rect x="3" y="2.5" width="10" height="11" rx="1"/><path d="M5.5 6h5M5.5 8.5h5M5.5 11h3"/>'
```

Two or three relevant types is plenty; do not invent ones the project will not use.

**d. Capture conventions and house rules** from AGENTS.md and friends (for example
"no em dashes", "prefer composition", commit style) so reports respect them.

### 5. Save the profile

```bash
python3 ~/.copilot/skills/goldie-init/scripts/profile.py save --audience "..." \
  --focus "security,performance,principles,testing" --stack "python,html" \
  --languages "python,shell" --summary "..." --conventions "..." \
  --doc_files "AGENTS.md,README.md" --preferred_resources "labex" --tone "..."
```

You can also pipe a full JSON object into `save`. Re-running merges, so the
profile can be refined later.

### 6. Confirm

Tell the user what was captured: the profile, the resources and member tooltips
seeded, and any new source types and icons. Done.

## How Goldie uses the profile

The `goldie` skill loads `.goldie/profile.json` at the start of its pipeline:
`python3 ~/.copilot/skills/goldie-init/scripts/profile.py show`. It uses `audience`
and `depth` to set teaching depth, `focus` to decide which insight nodes
(security, performance, principles) to emphasize, `stack`/`languages` to pick the
right references, and `conventions` to respect the team's house rules.

## Automatic first run

`scripts/firstrun.sh` is a nudge that, in any repo that has docs but no
`.goldie/profile.json` yet, prints a one-time instruction asking Copilot to run
this wizard. Wire it into whatever session-start or pre-prompt hook your Copilot
surface supports (for example the Copilot CLI); after the profile is saved the
nudge stops on its own.
