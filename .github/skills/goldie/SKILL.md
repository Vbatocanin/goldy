---
name: goldie
description: Export the current GitHub Copilot session into a human-readable, Notion-style HTML report. Works in five explicit phases (ingest the full chat history, take inventory, research, enrich, then render) and produces an interactive graph of request, decision, principle, security, performance, testing, networking and action nodes plus a closing summary, each rendered as a collapsible bubble with the rationale behind it and a "Learn more" drawer linking the references, tutorials and summaries needed to understand it. Use when the user asks to "explain what you did", "show your work", "document this session", or "generate a Goldie report".
license: MIT
---

# Goldie: make your codebase changes legible

Goldie keeps developers in touch with what GitHub Copilot does to their
codebase. It turns the raw chat session into a self-contained HTML document
where every step is a node, every node carries the reasoning behind it, and
every decision links the materials a human needs to understand it.

Goldie is a port of Goldy (the Claude Code skill set) to the GitHub Copilot
agent-skills standard. The pipeline and renderer are the same; the one
Copilot-specific piece is how the session is ingested (see Phase 1).

## House style (non-negotiable)

**Never use an em dash or en dash** in any text you write: rationale, summaries,
materials, explainers, node titles, commit messages, your replies. In casual
prose do not reach for a dash of any kind as punctuation; use a comma, a colon,
parentheses, or two sentences instead. Hyphens inside compound words
(self-contained, on-disk) are fine. The renderer also strips em and en dashes
that slip through, but write clean text in the first place.

## When to run

When the user asks to document, explain, or "show the work" of the current
session, or asks for a Goldie report.

## The pipeline: five explicit phases, in order

Goldie works in five separate phases. **Finish each phase before starting the
next.** The whole point is to learn before you teach: do not write a single line
of the HTML until you have read the full history, taken inventory of what it
used, and researched those topics. Scripts live in this skill's `scripts/`
directory (referenced below at their installed path
`~/.copilot/skills/goldie/scripts/`); outputs go in `.goldie/` inside the user's
project. Announce each phase to the user as you enter it so the separation is
visible.

### Phase 1: Ingest the full session history

First, load the project profile if Goldie was initialized for this repo:

```bash
python3 ~/.copilot/skills/goldie-init/scripts/profile.py show
```

If it returns a profile, let it shape the whole report: `audience` and `depth`
set how much teaching to include, `focus` decides which insight nodes (security,
performance, principles) to emphasize, `stack` and `languages` steer references,
and `conventions` are house rules to respect. If it returns `{}`, the repo has no
profile yet; suggest the user run `goldie-init` for sharper, tailored reports,
then continue with sensible defaults.

Then parse the chat session into raw nodes and read the whole thing end to end.
Do not skim and do not start enriching yet.

```bash
mkdir -p .goldie
python3 ~/.copilot/skills/goldie/scripts/parse_chat.py --latest -o .goldie/nodes.json
```

`parse_chat.py` reads VS Code Copilot Chat session JSON from the editor's
`workspaceStorage` for the current workspace (run `--list` to see candidates,
or pass an explicit `session.json` path to document a past session). VS Code
does not publish a stable schema for these files, so the parser is best-effort:
read the nodes it produces and sanity-check them against what actually happened
in this conversation, since you have the real history in front of you. It
produces nodes of kind `prompt`, `decision` and `action` with empty `rationale`
and `materials`. Read every node, including the full `detail` and
`result_excerpt`, so you understand the whole arc of what Copilot did before you
explain any part of it.

### Phase 2: Take inventory (learn what you will need to teach)

From the full history, write down (in `.goldie/inventory.md` or your working
notes) everything a developer would need explained to follow this session:

- **Languages and tools**: every language written or run (Python, shell, HTML,
  CSS, ...), every CLI and library used, every file format touched.
- **Principles and practices**: the architectural decisions, software principles
  and engineering practices the session relied on, named explicitly.
- **Security and performance angles**: where secrets, permissions, untrusted
  input, time, memory or cost mattered.
- **Concepts and APIs**: anything domain-specific (a chat-session schema, a
  tool's semantics, a protocol).

This inventory is your teaching plan. It drives the next phase.

### Phase 3: Research and build the knowledge base

**First, consult the user's own resource library.** For each inventory topic,
check what the user has already chosen to index:

```bash
python3 ~/.copilot/skills/goldie-resources/scripts/resources.py materials "<topic>" -n 3
```

This returns ready-to-merge material entries (with `kind: tutorial`, a note and a
summary) pointing at the best matching section of a trusted resource. Prefer
these. To add a new resource the user pastes, use the `goldie-resources` skill.

**Prefer LabEx for hands-on practice.** LabEx (`https://labex.io/learn`) is the
user's preferred interactive platform. Whenever a node involves Linux, shell,
git, devops, cybersecurity, docker, databases or MySQL, Wireshark, data science
or Python, attach the matching LabEx course as a `tutorial` material (for example
`https://labex.io/learn/git`, `https://labex.io/learn/linux`,
`https://labex.io/learn/python`) alongside the conceptual reference.

**Check whether a new source type or icon is needed.** As you gather materials,
some may not fit the built-in kinds (reference, docs, tutorial, how-to, language,
spec, book). If a recurring material is really a different type (a `video`, a
`paper`, a `dataset`, a `cve`), create it, with a hand-drawn SVG icon and never an
emoji, through the `goldie-source-types` skill before tagging materials with it.
Reuse existing types when they fit; only add a type that earns its place.

Then, for any inventory item still missing a good source, inform yourself before
you write about it. Use your web tools (web search and fetch) and delegate bulk
work to the `goldie-historian` skill. Produce, per item, the materials you will
attach later:

- Find the **authoritative reference** (official docs first), and for any
  concrete language or tool also a **hands-on tutorial or how-to**. Tag each with
  a `kind`: `reference`, `docs`, `tutorial`, `how-to`, `language`, `spec`, `book`.
- **Link the exact part to read.** Deep-link to the specific section with a URL
  fragment you have confirmed exists (Wikipedia anchors are reliable; many blogs
  have none). If there is no stable anchor, link the page and name the exact
  section in the `note`. Never point at a long article's front and make the reader
  hunt.
- Write a **`summary`** for each source: 2 to 4 sentences of its most important
  points, drawn from the actual fetched content, not the title. It appears behind
  a "Read summary" toggle so the reader gets the gist without leaving the page.
- Refine your own understanding as you go. If research changes how you would
  describe a decision, update your notes and the inventory before moving on.

Only when the knowledge base is built do you proceed.

### Phase 4: Enrich the nodes and add the teaching nodes

Now edit `.goldie/nodes.json`, applying what you learned. Keep the `meta` block.

**Tone: precise and professional.** Write every explanation (titles, transitions,
rationale, summaries) as a senior engineer would in a design doc: concrete and
specific, naming the actual file, command, type or trade-off involved. State things
plainly and in the present or simple past. No vague filler ("we did some setup"),
no hedging, no chatty asides or hype, no exclamation. Prefer the exact noun over a
gesture at it ("indexed tool-call blocks by id for O(1) pairing", not "handled the
results nicely").

For each node add:

- **`title`**: a short, summarized label (aim for under ~8 words), not a sentence
  of raw transcript text. It is what shows on the node's collapsed bubble, so a
  decision like "I'll start by understanding the current state of the goldie
  directory and how..." becomes "Survey the project's starting point". The
  renderer truncates over-long titles as a fallback, but write a real label.
- **`transition`**: a single connective sentence that bridges this node to the
  next step, so the bubbles read as a story top to bottom ("That meant inspecting
  the project and where Copilot keeps its skills."). Write one per node in
  document order; the last node needs none. When the detail-level or type filters
  discard nodes, the renderer stitches the discarded nodes' transitions together
  into the surviving gap, so keep each sentence able to stand on its own and flow
  into the next.
- **`rationale`**: a tight 1 to 3 sentence "why". Not what happened (the node
  shows that) but why it was the right call given the alternatives. For an action
  that produces or changes something, open with the preparation: what was learned
  or verified just before it, so the trace reads as "first learn, then write".
- **`materials`**: the references you gathered in Phase 3, each
  `{"title","url","note","kind","summary"}`, or `{"title","doc"}` for a
  self-contained explainer when no good source exists. Attach generously to
  decisions and insight nodes; actions usually need 0 to 1 plus their language
  reference.
- **`alternatives`** (decisions especially): the other viable approaches, each
  `{"option","tradeoff","url"?}`, so a developer can debug or adapt the choice.
  Two to four real options, honest about why each was not taken.
- **`priority`**: `high`, `medium` or `low`, driving the report's detail-level
  filter. `high` is a step the reader must not miss: a code-changing action
  (writing or editing a file, scaffolding the repo), a pivotal request or
  decision, or a security risk. `medium` is a supporting teaching node:
  principles and other additional learnings (performance, testing, networking)
  sit below the code changes. `low` is a minor or exploratory step (a quick
  inspection, a read, a check). If you leave it unset the renderer infers a
  default: requests, decisions and security are high; file-write and file-edit
  actions are high because they change the codebase; principles and the other
  teaching nodes are medium; all other actions are low. Hand-set it when an
  action changes code through a terminal command (a scaffold, a migration) so it
  is promoted to high too.
- **`detail_tips`** / **`result_tips`** / **`code_tips`** (optional): override the
  hover bubble for a specific token the built-in lexicon does not know.
  `detail_tips` and `result_tips` cover shell command and output tokens;
  `code_tips` covers tokens inside an embedded or written code panel, keyed by the
  bare name or the dotted path:
  `{"my_helper": {"tip": "...", "url": "..."}, "obj.method": {"tip": "..."}}`.

  **Denote what a script does.** When a step runs a script, by an interpreter
  (`python3 deploy.py`, `node seed.js`) or directly (`./run.sh`, `zsh build.zsh`),
  the renderer already flags the script filename as a script. Add a `detail_tips`
  override keyed by that filename (for example `"deploy.py"` or `"./run.sh"`) whose
  `tip` states, in one or two precise sentences, what the script actually does
  (its inputs, its effect), reading the file if it is in the repo. Do not leave a
  run-script step explained only as a generic argument.

  **Fetch the docs for notable functions.** The renderer already explains common
  language keywords, builtins, modules and module members (for example
  `os.path.expanduser`, `json.loads`). When the code calls a function, method or
  library member that is *not* common and matters to the step, fetch its
  documentation and write an accurate one-line tooltip from it. Persist reusable
  ones to `~/.goldie/py_members.json` (`{"pkg.func": "what it does"}` or
  `{"pkg.func": {"tip": "...", "url": "..."}}`) so every future report explains
  them too; use `code_tips` for one-off, project-local names. Do not guess what a
  function does, read its docs.

Then insert **teaching nodes** next to the steps they explain, one per real idea,
never invented:

- **`principle`**: an architectural or software principle the session used.
- **`security`**: a cybersecurity consideration (secrets, permissions, untrusted
  input, symlinks, injection, exposure); link OWASP or CWE.
- **`optimization`**: a performance, memory or cost consideration; explain the
  cost, the approach, the tradeoff, and link the complexity or profiling source.
- **`testing`**: how to verify the change. List the different ways to test it at
  each level (UI, unit/code, integration, manual, end-to-end), what each catches,
  and which the session actually used. Link the relevant testing references.
- **`networking`**: when the work touches the network or web, explain it: URL
  anatomy (scheme, host, path, query, fragment), HTTP requests and status codes,
  web-API design and versioning, DNS, TLS/HTTPS, ports and protocols. Link MDN
  HTTP, the URL standard, and the relevant networking references.

- **`summary`**: a single closing node, appended last, that recaps the whole
  walkthrough. Pull the through-line of the session into a short lead plus a few
  bulleted takeaways (the key decisions and principles, in the reader's words),
  and a one-line `rationale`. It is `priority: high` so it always shows, and its
  bubble carries a distinct neutral accent so the finale reads as a capstone, not
  another step. Add exactly one.

Each teaching node has the same shape as a decision (`title`, `summary`,
`rationale`, `materials`, optional `alternatives`) with its own `kind`.

### Phase 5: Render the HTML (only now)

Only after Phases 1 to 4 are complete, write the document. A repo accumulates many
conversations, so each one gets its **own report** under `.goldie/reports/`, and a
**master index** at `.goldie/goldie-report.html` links to all of them. Render this
session's report (registering it in the history manifest), then rebuild the index:

```bash
python3 ~/.copilot/skills/goldie/scripts/render.py .goldie/nodes.json \
  -o .goldie/reports/<id>.html --register
python3 ~/.copilot/skills/goldie/scripts/render_index.py .goldie/reports \
  -o .goldie/goldie-report.html
```

Use the session id for `<id>` (the renderer defaults to `meta.session_id`, or a
slug of the title, when `--register` is given without `--id`), so re-rendering the
same conversation overwrites its report rather than adding a duplicate. `--register`
upserts a small entry (title, summary, date, kind counts) into
`.goldie/reports/index.json`; `render_index.py` turns that manifest into the master
page, newest first. Each report shows an up-arrow back to the index (the parent
doc): with `--register` the link defaults to `../goldie-report.html`, or set it
explicitly with `--parent <href>`. Offer to open `.goldie/goldie-report.html` (the
hub) when done.

**Detail level.** The report opens with a Detail control (Essentials, Standard,
Everything) the reader can flip live to filter nodes by their `priority`:
Essentials keeps only `high` nodes, Standard adds `medium`, Everything shows all.
Set the starting level for a report either by adding `"detail"` to the `meta`
block in `nodes.json` (`"essentials"`, `"standard"` or `"everything"`) or with
`--detail <level>` on the render command; the flag wins. Default is `standard`.
Honor the profile here: a low-`depth` or executive `audience` profile suggests
opening at `essentials`; a teaching-heavy one at `everything`.

**Interactive graph.** The graph opens as a folded overview of bubbles: every node
starts collapsed to a big round, kind-coloured icon face with its title beside it,
the card chrome (border, fill, padding, body) melted away. Clicking a bubble morphs
it into the full card: the icon face shrinks from a 58px bubble to a small header
badge while the card grows around it and the body unfolds, all on one element so
open and closed read as the same object resizing. Bubbles are keyboard-focusable,
so Enter or Space toggles them too. The icon face is the only marker (there is no
separate spine bead), and it sits in front of the spine, so the lines tuck behind
it. Two fold controls, Expand all and Collapse all, drive the whole graph at once.
The spine is drawn per node, so the connecting line begins at the first face and
ends at the last, with no stub past either end. Hovering a bubble lights its
connector and spine segment in the bubble's own colour, with a brighter band
flowing along them toward the next node, so the link reads as live current.

**Priority staircase and story.** Bubbles step right by priority: high-priority
nodes sit closest to the spine and lower-priority ones cascade outward, so the
shape of the graph shows the hierarchy at a glance. Between every two bubbles, the
node's `transition` sentence is shown as connective narration, turning the graph
into a walkthrough you can read top to bottom. If a reader filters nodes out (by
detail level or type), the discarded nodes' transitions are stitched into the gap
so the story never breaks. Hovering a card lifts it, grows its spine dot and lights
its connector. All of this is self-contained CSS and JS with a
`prefers-reduced-motion` fallback, so the document stays a single file with no
dependencies.

The renderer also annotates code for free: shell tokens (commands, subcommands,
flags, paths, operators), command output (paths, permissions, exit codes,
errors), embedded programs (`python3 -c ...`, heredocs) and written code files
(`.py`, `.sh`, ...) all get language-aware hover help, so you do not hand-annotate
syntax. Tell the user the path and offer to open it
(`open .goldie/goldie-report.html`). To preview it yourself, serve the folder
(`python3 -m http.server`) since `file://` may be blocked in some browsers.

## Quality bar

- Rationale, not narration. Explain the choice and the alternative rejected.
- Real links first. Only write a `doc` explainer when no good source exists.
- Honesty. If a step failed or was a dead end, say so in the rationale.
- No em dashes. No leaked secrets (scan enriched text before rendering).
