---
name: goldy-resources
description: Crawl a learning resource URL the user pastes, distill what it can teach (topics, principles, skills, languages, key sections), and persist it to Goldy's resource library, also harvesting reusable function and member tooltips and any new source type, so future Goldy reports prefer it and explain code better. Use when the user pastes a URL and asks to index it, "add this resource", "learn from this link", "crawl this for learning material", or "remember this site for Goldy".
---

# Goldy Resources: crawl, index, and persist learning material

This skill builds and maintains Goldy's **resource library**: a persistent index
of URLs the user trusts, distilled into what they can teach. Once a resource is
in the library, the main `goldy` skill prefers it when attaching materials.

Index for reuse, not just for this one report. A page is rarely only a link: it
also carries function documentation, principles, and sometimes a new kind of
source. Harvest all of it into Goldy's shared registries (all under
`~/.claude/goldy/`) so the knowledge compounds across projects:

- `resources.json`: the resource library itself (`scripts/resources.py`).
- `py_members.json`: docstring-style tooltips for functions and members (used by
  the renderer to explain code on hover).
- `source_types.json` + `icons.json`: a new reference kind and its SVG icon, via
  the `goldy-source-types` skill.

## House style

Never use an em dash or en dash. No dash as punctuation in prose. Hyphenated
compounds are fine. Never use emoji; Goldy uses hand-drawn SVG icons.

## Workflow

### 1. Fetch the URL the user pasted

Use `WebFetch` (or the MCP fetch tool) to retrieve the page. If it is an index or
landing page, also fetch a few of its most relevant same-domain subpages (a
shallow crawl, roughly 3 to 6 pages, do not spider the whole site). If a site
blocks fetching, fall back to `WebSearch` to learn its structure and the URLs of
its sections, and tell the user you indexed it from search rather than a crawl.

### 2. Distill what it teaches

From the content, work out:

- **`topics`**: the subjects it covers (for example `git`, `shell`, `docker`,
  `python`, `cybersecurity`, `mysql`, `wireshark`).
- **`teaches`**: the concrete principles, skills and concepts a reader gains
  (for example `branching`, `rebasing`, `file permissions`, `tcp handshake`).
- **`languages`**: any languages involved.
- **`summary`**: 2 to 4 sentences on what the resource is and who it helps.
- **`sections`**: the most useful deep links, each `{"title","url","note"}`,
  pointing at the exact page or anchor a reader should open for a given subtopic.

### 2b. Harvest reusable knowledge into the other registries

This is what lets the library extrapolate. While the page is open:

- **If it documents an API (functions, methods, members)**, capture the notable
  ones as docstring-style tooltips and persist them to
  `~/.claude/goldy/py_members.json` (for Python). Each value is a signature line,
  a newline, then a one-line description, plus a deep link to that function's
  exact definition on the page:
  ```json
  {"pandas.read_csv": {"tip": "pandas.read_csv(path, sep=',')\nRead a CSV file into a DataFrame.", "url": "https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html"}}
  ```
  Now any future report that shows code calling those functions explains them on
  hover, for free. Read the real signature from the docs; never invent one.
- **If the resource is a new kind of source** that the built-in kinds do not
  cover (a `video`, `course`, `paper`, `dataset`, `advisory`), create it with a
  hand-drawn SVG icon through the `goldy-source-types` skill, then tag the
  resource and its sections with that kind.
- **Generalize**: note the platform and its topic taxonomy in the `summary` and
  `topics` so sibling pages on the same site are recognized later.

### 3. Persist it

Write the record as JSON and pipe it into the library:

```bash
echo '<record-json>' | python3 "$SKILL_DIR/scripts/resources.py" add
```

Or use flags for a quick add:

```bash
python3 "$SKILL_DIR/scripts/resources.py" add \
  --url "https://labex.io/learn/git" --title "Git, hands-on labs (LabEx)" \
  --topics "git,version-control" --teaches "repositories,branching,merging,rebasing" \
  --summary "Interactive, no-setup Git labs..."
```

Adding the same URL again replaces the old record, so re-indexing refreshes it.

### 4. Confirm

Tell the user what was indexed (topics and teaches), how many resources are now
in the library (`resources.py list`), and that Goldy will prefer these.

## How Goldy uses the library

During its research phase, the `goldy` skill runs:

```bash
python3 ~/.claude/skills/goldy-resources/scripts/resources.py materials "<topic>" -n 3
```

which returns ready-to-merge material entries (with `kind: tutorial`, a note and
a summary, pointing at the best matching section). Goldy attaches those to the
relevant nodes, so the things the user chose to index become the references the
report teaches from.

## Preferred platform

LabEx (`https://labex.io/learn`) is the user's preferred hands-on platform for
Linux, shell, git, devops, cybersecurity, docker, databases or MySQL, Wireshark,
data science and Python. When indexing or recommending learning material for any
of those, include the matching LabEx course or skill tree.
