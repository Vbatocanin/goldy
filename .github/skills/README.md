# Goldie: Goldy for GitHub Copilot

Goldie is a port of [Goldy](../../README.md) to the GitHub Copilot
[agent-skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)
standard. It turns a Copilot session into a self-contained, Notion-style HTML
report: an interactive graph where every step is a collapsible bubble carrying
the reasoning behind it and a "Learn more" drawer of references.

Same pipeline, same renderer as Goldy. The one Copilot-specific piece is how the
session is ingested: instead of reading a Claude Code `.jsonl` transcript, Goldie
reads VS Code Copilot Chat session JSON (`scripts/parse_chat.py`).

## The skills

| Skill | What it does |
| --- | --- |
| `goldie` | The main pipeline: ingest, inventory, research, enrich, render. |
| `goldie-init` | One-time wizard that profiles the repo so reports are tailored. |
| `goldie-resources` | Crawl and index a learning URL into the resource library. |
| `goldie-source-types` | Add a new material kind with a hand-drawn SVG icon. |
| `goldie-historian` | Research helper that fills "Learn more" drawers in bulk. |

## Install

GitHub Copilot discovers skills from `.github/skills/` in any repo, so vendoring
this directory is enough to use Goldie in that project, no install step required.

To make the skills available in **every** repo, symlink them into your personal
skills directory (`~/.copilot/skills`):

```bash
.github/skills/install.sh
```

Copilot also reads personal skills from `~/.agents/skills`; set
`COPILOT_SKILLS_DIR` to target a different location.

## Use

Ask Copilot to "generate a Goldie report", "document this session", or "show your
work". Goldie runs five explicit phases (ingest, inventory, research, enrich,
render) and writes:

- `.goldie/reports/<id>.html` per conversation, and
- `.goldie/goldie-report.html`, a master index linking all of them.

Run `goldie-init` once per repo first for sharper, tailored reports.

## Shared registries

Like Goldy, Goldie keeps cross-project registries under `~/.goldie/`:
`resources.json` (resource library), `source_types.json` + `icons.json` (source
types and their icons), and `py_members.json` (function and member tooltips). The
per-project `.goldie/profile.json` ties them to a repo.

## Note on chat ingestion

VS Code does not publish a stable schema for chat session files, so
`parse_chat.py` reverse-engineers the on-disk JSON under the editor's
`workspaceStorage`. It is best-effort and degrades gracefully on shapes it does
not recognize. Run `python3 scripts/parse_chat.py --list` to see the candidate
session files for the current workspace. If a future VS Code release changes the
format, only `parse_chat.py` needs updating; the rest of the pipeline is
unchanged.

## House style

No em dashes or en dashes anywhere. No emoji; Goldie uses hand-drawn SVG icons.
