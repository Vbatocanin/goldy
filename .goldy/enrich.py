#!/usr/bin/env python3
"""Idempotent enrichment for the self-referential demo report: adds rationale,
verified materials, architectural principle nodes and a token-tip override to
the nodes Goldy parsed from its own build session. House style: no em dashes."""
import json
import pathlib

p = pathlib.Path(__file__).parent / "nodes.json"
d = json.loads(p.read_text())

# A short, hand-written headline and summary beat the raw first prompt.
d.setdefault("meta", {})
d["meta"]["title"] = "Building Goldy"
d["meta"]["summary"] = (
    "Goldy is a set of Claude Code skills and agents that turn a session into a "
    "readable report. This walkthrough traces how it was built, step by step, "
    "with the reasoning and sources behind each decision.")
# Open the report at the middle detail level by default.
d["meta"]["detail"] = "standard"

# Per-node priority drives the detail-level filter (high survives "Essentials",
# medium needs "Standard", low only shows at "Everything"). Code-changing steps
# are high; principles and other teaching nodes sit below them; exploratory
# inspections are low. The Write actions (n12, n14) auto-promote to high in the
# renderer, so only the non-obvious cases are pinned here.
PRIORITY = {
    "n1": "high",   # the human request
    "n5": "high",   # source from the transcript: the pivotal decision
    "n9": "high",   # design locks in
    "n11": "high",  # language choice, with alternatives
    "n13": "high",  # single self-contained HTML file
    "n10": "high",  # scaffolds the repo: a change to the codebase
    "n3": "low", "n4": "low", "n6": "low",  # exploratory inspection actions
    "n7": "low", "n8": "low",
}

SKILLS = {"title": "Extend Claude with Skills, Claude Code Docs", "kind": "docs",
          "url": "https://code.claude.com/docs/en/skills",
          "note": "The SKILL.md frontmatter and progressive-disclosure model Goldy's skill is built on.",
          "summary": "A skill is a folder containing a SKILL.md file whose YAML frontmatter (name and description) is preloaded into the system prompt so Claude knows when to use it. The fuller instructions, plus optional scripts, references and assets, load only when the skill is actually triggered. This progressive disclosure keeps base context small while still giving the agent deep, on-demand capability."}
SKILLS_ENG = {"title": "Equipping agents for the real world with Agent Skills, Anthropic",
              "kind": "reference",
              "url": "https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills",
              "note": "Anthropic's rationale for the skills architecture: why bundled scripts plus instructions beat a megaprompt.",
              "summary": "Anthropic frames skills as a way to package real-world procedures as instructions plus bundled code and assets, instead of stuffing everything into a single prompt. Only a skill's short description stays in context until it is invoked, so an agent can carry many capabilities without bloating its system prompt. The result composes better and is easier to maintain than one giant instruction blob."}
SUBAGENTS = {"title": "Create custom subagents, Claude Code Docs", "kind": "docs",
             "url": "https://code.claude.com/docs/en/sub-agents",
             "note": "Defines the ~/.claude/agents/*.md format and tool and model scoping used by goldy-historian.",
             "summary": "Custom subagents are Markdown files with YAML frontmatter stored in .claude/agents (project) or ~/.claude/agents (user). Each subagent gets its own system prompt, its own tool allowlist and optionally its own model, and Claude delegates to one automatically when a task matches its description. They can run in parallel and with different permission scopes, for example a read-only researcher alongside a full-access implementer."}

E = {
 "n1": dict(rationale="The brief is three coupled requirements: capture the full reasoning and action trace, attach a justification and learning links to each step, and present it as a polished Notion-like document. That framing drove the parse, enrich, render split that follows.",
            materials=[SKILLS, SUBAGENTS]),
 "n2": dict(rationale="Before designing anything, ground the build in reality: the actual on-disk layout of skills and agents and the conventions a real installed skill (sentry-cli) follows. Matching existing conventions beats inventing a format Claude Code will not load.",
            materials=[SKILLS]),
 "n3": dict(rationale="Listing the project plus the skills and agents directories answers two questions at once, is this a greenfield repo and what is the canonical install location, in a single round trip.",
            detail_tips={"sentry-cli": {"tip": "The one skill already installed on this machine, used here as a reference implementation.", "url": "https://docs.sentry.io/cli/"}},
            materials=[{"title": "Claude Code settings and directories", "url": "https://code.claude.com/docs/en/settings", "note": "Where user-level skills and agents live (~/.claude)."}]),
 "n4": dict(rationale="The sentry-cli skill is a working reference implementation. Reading its SKILL.md frontmatter and references layout reveals the exact schema (name, description, requires) so Goldy's skill is loadable rather than guesswork.",
            materials=[SKILLS]),
 "n5": dict(rationale="Key realization: the whole thinking and implementation process is not something to reconstruct, Claude Code already persists it as a session transcript. Sourcing from the transcript makes Goldy faithful rather than a paraphrase.",
            alternatives=[
                {"option": "Logging proxy", "tradeoff": "Wrap Claude Code behind a proxy that records traffic live. Captures everything, but needs a running service and changes how users launch the tool."},
                {"option": "Scrape terminal scrollback", "tradeoff": "Read what was printed to the screen. No extra files, but fragile and it loses the thinking and tool metadata that the structured log keeps."},
                {"option": "Ask the model to self-summarize", "tradeoff": "Cheap and simple, but it is a paraphrase rather than the real trace and can drift from what actually happened."}],
            materials=[{"title": "Claude Code session transcripts (JSONL logs)", "doc": "## Where the trace lives\n\nClaude Code writes every session to a JSON-Lines file under:\n\n`~/.claude/projects/<slug>/<session-id>.jsonl`\n\nThe **slug** is the project's absolute path with `/` and `.` replaced by `-`. Each line is one event object with a `type`:\n\n- `user` and `assistant`: message turns; `message.content` is an array of blocks (`text`, `thinking`, `tool_use`, `tool_result`).\n- `file-history-snapshot`, `mode`, `permission-mode`: session bookkeeping.\n\nBecause it is append-only JSONL, Goldy can parse it line by line without loading the whole session into memory, and a crashed write only loses the last line."},
                       {"title": "JSON Lines (JSONL) format", "kind": "spec", "url": "https://jsonlines.org/", "note": "The append-friendly, line-delimited JSON format Claude Code uses for transcripts."}]),
 "n6": dict(rationale="Do not trust assumptions about the log schema, inspect it. Dumping the first events' types and keys confirms where messages, modes and snapshots live before writing a parser against them.",
            materials=[]),
 "n7": dict(rationale="Counting event types and content-block types maps the whole transcript's shape at a glance, confirming that reasoning (thinking and text) and actions (tool_use and tool_result) are cleanly separable into the two node kinds Goldy needs.",
            materials=[{"title": "Anthropic Messages API, tool use", "url": "https://platform.claude.com/docs/en/build-with-claude/tool-use", "note": "Explains the tool_use and tool_result pairing the parser relies on to match an action to its result."}]),
 "n8": dict(rationale="A final shape check of the actual thinking, text, tool_use ordering inside an assistant turn. This confirmed the reason-then-act grouping the parser uses to merge narration into one decision node ahead of its actions.",
            materials=[]),
 "n9": dict(rationale="With the schema verified, the design locks in: decision nodes from thinking and text, action nodes from tool_use paired with their result. Verifying before building avoids a parser written against an imagined format.",
            materials=[SKILLS_ENG]),
 "n10": dict(rationale="Lay the project out the way Claude Code expects: skills/goldy and agents mirror the loader's search paths, and git-init it since this is a GitHub project, so an install script can later symlink it into ~/.claude.",
            materials=[SUBAGENTS,
                       {"title": "Learn Git with Hands-on Labs (LabEx)", "kind": "tutorial", "url": "https://labex.io/learn/git", "note": "Hands-on Git: repositories, staging, branching, merging, collaboration.", "summary": "Interactive, no-setup Git labs in a real environment, progressing from repositories and branching to team collaboration workflows. The preferred place to practice the git commands this step uses."},
                       {"title": "Shell Scripting Learning Path (LabEx)", "kind": "tutorial", "url": "https://labex.io/learn/shell", "note": "Hands-on shell: pipes, redirection, variables, scripting.", "summary": "A systematic, hands-on path for the shell, covering pipes, redirection, variables and scripting through interactive exercises rather than video."}]),
 "n11": dict(rationale="Python was chosen for the parser: it ships on macOS with zero install, has first-class JSON, and keeps the mechanical work (transcript to nodes) out of the model so it is deterministic and cheap. The model is reserved for the judgement-heavy enrichment.",
            alternatives=[
                {"option": "Node.js", "tradeoff": "Equally good at JSON, but it adds a runtime that is not guaranteed on every machine the way Python 3 is on macOS."},
                {"option": "jq plus shell", "tradeoff": "Excellent for quick one-line filters, but painful once you need the branching request/decision/action node model."},
                {"option": "Parse inside the model", "tradeoff": "Most flexible, but nondeterministic, slower, and spends tokens on purely mechanical work."}],
            materials=[{"title": "Python json, encoder and decoder", "kind": "language", "url": "https://docs.python.org/3/library/json.html", "note": "The standard-library module that makes line-by-line JSONL parsing a few lines of code."},
                       {"title": "Learn Python with Hands-on Labs (LabEx)", "kind": "tutorial", "url": "https://labex.io/learn/python", "note": "Hands-on Python: syntax, data structures, OOP, file IO.", "summary": "A structured, interactive Python roadmap covering syntax, data structures and object-oriented programming in a real browser environment. The preferred place to practice the Python this parser is written in."},
                       {"title": "Working with JSON Data in Python (Real Python)", "kind": "tutorial", "url": "https://realpython.com/python-json/", "note": "A hands-on walkthrough of reading and writing JSON in Python, the exact task the parser does."}]),
 "n12": dict(rationale="With the JSONL schema already confirmed by hand (the learning step just before), the parser could be written directly against the real shape. It is intentionally dumb: it extracts raw facts and leaves rationale and materials empty, so extraction stays separate from interpretation and each piece is independently testable.",
            materials=[{"title": "Python: dictionaries", "kind": "language", "url": "https://docs.python.org/3/tutorial/datastructures.html#dictionaries", "note": "The dict used to index tool results by id for O(1) pairing with their tool calls."},
                       {"title": "Working with JSON Data in Python (Real Python)", "kind": "tutorial", "url": "https://realpython.com/python-json/", "note": "A hands-on guide to the json parsing the script does line by line."},
                       {"title": "Separation of concerns", "kind": "reference", "url": "https://en.wikipedia.org/wiki/Separation_of_concerns", "note": "Why parsing, enrichment and rendering are three swappable stages rather than one script."}]),
 "n13": dict(rationale="The renderer emits a single self-contained HTML file (inline CSS and JS, no network). That makes a report portable, emailable, committable, viewable offline, and the Notion-like styling (spine graph, chips, drawers, scroll-in animation) is pure CSS so it never breaks.",
            alternatives=[
                {"option": "Static-site generator", "tradeoff": "Tools like Eleventy give nice output, but add a build step and dependencies to install and keep current.", "url": "https://www.11ty.dev/"},
                {"option": "Render to PDF", "tradeoff": "Very portable, but static: no hover tips and no drawers, so the interactive learning parts are lost."},
                {"option": "React single-page app", "tradeoff": "Rich and componentized, but needs bundling and a server, and will rot as its dependencies age."}],
            materials=[{"title": "HTML details and summary disclosure element", "kind": "language", "url": "https://developer.mozilla.org/en-US/docs/Web/HTML/Element/details", "note": "The native, JS-free primitive powering Goldy's Learn more and code drawers."},
                       {"title": "CSS keyframe animations", "kind": "language", "url": "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_animations/Using_CSS_animations", "note": "How the staggered node rise-in effect is done with delays and no JavaScript."},
                       {"title": "Using CSS animations, step by step (CSS-Tricks)", "kind": "tutorial", "url": "https://css-tricks.com/almanac/properties/a/animation/", "note": "A practical tutorial for building the kind of keyframe effects the report uses."}]),
 "n14": dict(rationale="render.py keeps a tiny safe markdown converter and the full template in one file so a report can be regenerated from nodes.json alone, no build step, no dependencies, easy to audit before sharing.",
            materials=[{"title": "Python: regular expressions (re)", "kind": "language", "url": "https://docs.python.org/3/library/re.html", "note": "The re module behind the tiny markdown converter and the shell and Python tokenizers."},
                       {"title": "Python string formatting (f-strings)", "kind": "tutorial", "url": "https://realpython.com/python-f-strings/", "note": "How the HTML is assembled from node data without a templating dependency."},
                       {"title": "Notion-style document design", "kind": "reference", "url": "https://www.notion.com/help/writing-and-editing-basics", "note": "The clean-card, chip and toggle vocabulary the report's visual language borrows from."}]),
}

# High-level architectural / educational nodes, inserted after the decision
# they explain. Each names a principle and links the book or blog it comes from.
PRINCIPLES = [
 ("after", "n4", dict(id="p1", kind="principle",
   title="Progressive disclosure: load only what is needed, when needed",
   summary="A skill exposes just its name and description up front; the full instructions and scripts load only when it is actually used.",
   rationale="Goldy follows the same idea internally. The report shows a one-line title and chips first, and tucks the command, result and references into drawers. The reader controls depth instead of drowning in everything at once.",
   materials=[{"title": "Progressive Disclosure (Nielsen Norman Group)", "url": "https://www.nngroup.com/articles/progressive-disclosure/", "note": "The interaction-design principle the drawers and the skill's metadata-first loading both apply."}, SKILLS_ENG])),
 ("after", "n9", dict(id="p5", kind="principle",
   title="Preparation phase: learn first, then write",
   summary="Every writing step in this build was preceded by a learning step. The directory was inspected, the transcript schema was dumped and verified, and only then was code written against the real shape of the data.",
   rationale="Understanding the ground truth before changing anything prevents whole classes of bug: the parser was written against a schema that had been confirmed by hand, not imagined. The cost of a few read-only checks up front is far smaller than rewriting code built on a wrong assumption.",
   materials=[{"title": "Chesterton's Fence", "kind": "reference", "url": "https://fs.blog/chestertons-fence/", "note": "Do not change (or build on) something until you understand why it is the way it is.", "summary": "Chesterton's Fence is the rule that you should not remove or rely on a thing until you understand why it exists. Applied to engineering, it means learn the existing system and its constraints before you act, because the reason for the current state is often not obvious. It is the principle behind inspecting the transcript format before writing a parser for it."},
              {"title": "Effective context engineering for AI agents (Anthropic)", "kind": "reference", "url": "https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents", "note": "Gather the right context first; an agent that acts before it understands its inputs makes avoidable mistakes."},
              {"title": "Measure twice, cut once", "kind": "reference", "url": "https://en.wiktionary.org/wiki/measure_twice_and_cut_once", "note": "The craft idiom for verifying before you commit to an irreversible step."}])),
 ("after", "n9", dict(id="p2", kind="principle",
   title="Separation of concerns: parse, enrich, render",
   summary="Three stages with one job each, talking only through nodes.json.",
   rationale="Each stage can be tested and replaced on its own: swap the renderer's theme without touching the parser, re-enrich without re-parsing. Coupling them into one script would make every change risky.",
   materials=[{"title": "Separation of concerns", "kind": "reference", "url": "https://en.wikipedia.org/wiki/Separation_of_concerns", "note": "The foundational idea behind the three-stage split.", "summary": "Separation of concerns means dividing a program so each part addresses one concern, with minimal overlap. When concerns are isolated behind clear interfaces, you can understand, change or replace one part without disturbing the others. It is the general principle that justifies splitting parsing, enrichment and rendering into independent stages."},
              {"title": "The Clean Architecture (Robert C. Martin)", "kind": "book", "url": "https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html", "note": "Read the section 'The Dependency Rule': source dependencies may only point inward, which keeps outer details (UI, DB) swappable.", "summary": "The post collects several architectures (hexagonal, onion, others) into one model of concentric layers, with business rules at the center and frameworks, UI and databases at the edges. Its core is the Dependency Rule: source-code dependencies may only point inward, so inner layers know nothing about outer ones. That is what lets you swap a detail like the renderer or the database without touching the policy at the core."}])),
 ("after", "n11", dict(id="p3", kind="principle",
   title="Deterministic core, model at the edges",
   summary="Mechanical work (parsing, rendering) is plain Python; judgement (rationale, research) is left to the model.",
   rationale="Keeping the model out of the predictable parts makes Goldy cheap, repeatable and easy to debug, and spends model effort only where taste and reasoning actually matter.",
   materials=[{"title": "Building Effective AI Agents (Anthropic)", "kind": "reference", "url": "https://www.anthropic.com/research/building-effective-agents", "note": "Read the section 'When (and when not) to use agents': find the simplest solution first and add agentic complexity only when it earns its keep.", "summary": "Anthropic distinguishes workflows (LLMs and tools orchestrated through predefined code paths) from agents (the model dynamically directs its own steps). Its central advice is to find the simplest solution that works and only add complexity, and cost and latency, when the task genuinely needs it. Goldy applies this by keeping deterministic code paths for parsing and rendering and spending model effort only on judgement."},
              {"title": "The Unix Philosophy", "kind": "reference", "url": "https://en.wikipedia.org/wiki/Unix_philosophy#Doug_McIlroy_on_Unix_programming", "note": "See McIlroy's summary: make each program do one thing well and expect its output to become another program's input.", "summary": "The Unix philosophy favors small programs that each do one thing well and combine through simple, text-based interfaces. McIlroy's famous formulation is to write programs that do one thing well and that work together, expecting the output of one to be the input of another. This is the lineage behind Goldy's parse-to-nodes-to-render pipeline."}])),
 ("after", "n14", dict(id="p4", kind="principle",
   title="Single file, zero dependencies, portable output",
   summary="The report is one HTML file with inline CSS and JS and no network needs.",
   rationale="A document you can email, commit or open offline in five years outlives any toolchain. No build step and no package install means nothing to rot, and the whole artifact is auditable before it is shared.",
   materials=[{"title": "The Art of Unix Programming (Eric S. Raymond)", "url": "http://www.catb.org/~esr/writings/taoup/html/", "note": "On simplicity, transparency and durable, text-first artifacts."}, {"title": "Data URLs and self-contained documents (MDN)", "url": "https://developer.mozilla.org/en-US/docs/Web/URI/Schemes/data", "note": "Background on bundling assets inline so a file stands alone."}])),
]

SECURITY = [
 ("after", "n12", dict(id="s1", kind="security",
   title="Secret hygiene: keep tokens and keys out of the report",
   summary="A session trace can contain API keys, tokens or private paths from command output. The report must not leak them.",
   rationale="The parser caps every captured result, and the skill scans enriched text for secrets before rendering. A Goldy report is meant to be shared (committed, emailed), so treating the output as untrusted and redacting is the safe default.",
   materials=[{"title": "OWASP: Secrets Management Cheat Sheet", "kind": "reference", "url": "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html", "note": "Practices for handling secrets so they do not end up in logs or artifacts."},
              {"title": "CWE-532: Insertion of Sensitive Information into Log File", "kind": "reference", "url": "https://cwe.mitre.org/data/definitions/532.html", "note": "The exact weakness a trace tool risks: leaking secrets through captured output.", "summary": "CWE-532 is the weakness where an application writes sensitive data (credentials, tokens, personal data) into logs or trace files that are less protected than the data deserves. The fix is to keep secrets out of captured output and to scrub or redact before anything is persisted or shared. A session-trace tool like Goldy is squarely in this risk category, which is why it caps and scans output before rendering."}])),
 ("after", "n10", dict(id="s2", kind="security",
   title="Least privilege and symlink safety in the installer",
   summary="Transcripts live in a private ~/.claude (mode 0700), and the installer refuses to clobber a real file when linking.",
   rationale="The install step only creates symlinks and bails out if the target exists and is not already a link, which avoids overwriting user data and the classic symlink-swap attack. Goldy reads the private transcript directory but never widens its permissions.",
   materials=[{"title": "CWE-59: Link Following", "kind": "reference", "url": "https://cwe.mitre.org/data/definitions/59.html", "note": "Why an installer must be careful about following or replacing symlinks."},
              {"title": "Principle of least privilege", "kind": "reference", "url": "https://en.wikipedia.org/wiki/Principle_of_least_privilege", "note": "The access-control idea behind keeping the transcript directory private."}])),
]

OPTIM = [
 ("after", "n11", dict(id="o1", kind="optimization",
   title="Stream the transcript line by line, not all at once",
   summary="The parser reads the JSONL file one line per iteration instead of loading and parsing the whole session into memory.",
   rationale="A long session can be large. Iterating the file object yields one line at a time, so memory stays roughly constant and the work is a single O(n) pass. Tool results are indexed once into a dict for O(1) pairing with their tool calls.",
   materials=[{"title": "Reading files lazily in Python", "kind": "tutorial", "url": "https://realpython.com/python-iterators-iterables/", "note": "Why iterating a file object streams it rather than buffering the whole thing.", "summary": "Iterators produce values one at a time and only when asked, so they let you process data that is large or even unbounded without holding it all in memory. A Python file object is itself an iterator over lines, so looping directly over it reads one line per step. That is exactly how the parser walks a transcript without loading the whole session."},
              {"title": "Time complexity (Big O)", "kind": "reference", "url": "https://en.wikipedia.org/wiki/Time_complexity", "note": "Framing the single-pass parse and the O(1) dict lookups.", "summary": "Big O describes how an algorithm's running time grows with input size. A single pass over n lines is O(n), and a hash-map (dict) lookup is on average O(1) regardless of size. Indexing tool results into a dict once and then pairing them by id keeps the parser linear instead of quadratic."}],
   alternatives=[
       {"option": "json.load the whole file", "tradeoff": "Simplest to write, but JSONL is not one JSON document, and it would hold the entire session in memory at once."},
       {"option": "Read all lines into a list first", "tradeoff": "Convenient random access, but defeats the streaming win on large transcripts."}])),
 ("after", "n12", dict(id="o2", kind="optimization",
   title="Cap captured output to bound size and cost",
   summary="Each result excerpt and command body is truncated to a fixed budget before it ever reaches nodes.json.",
   rationale="Capping output keeps nodes.json small, keeps the rendered HTML light in the browser, and crucially bounds the token cost of the enrichment step, where the model reads every node. The cap is explicit so the tradeoff between detail and size is visible in one place.",
   materials=[{"title": "Why payload size matters for web performance", "kind": "reference", "url": "https://developer.mozilla.org/en-US/docs/Learn/Performance/Multimedia", "note": "Background on keeping rendered document weight down."},
              {"title": "Token-based pricing and context limits", "kind": "docs", "url": "https://platform.claude.com/docs/en/about-claude/models", "note": "Why bounding the text the model reads during enrichment controls cost."}])),
]

TESTING = [
 ("after", "n14", dict(id="t1", kind="testing",
   title="How to verify a change like this",
   summary="The renderer was checked at several levels, cheapest first:\n\n- **Unit**: call the pure token functions (annotate_bash_inner, annotate_python_inner) directly and assert the token classes, for example that '2>' is a redirection and '/dev/null' is a device file.\n- **Integration**: run the whole parse, enrich, render pipeline and grep the HTML for expected structure (chip counts, drawer markers, SVG icon count, zero em dashes).\n- **UI**: open the report in a headless browser, screenshot it, and read it back to confirm layout, colours and the hover affordances actually render.\n- **Manual**: open .goldy/goldy-report.html and click the What ran and Result toggles and hover tokens.",
   rationale="Match the test to the risk. Pure functions get fast unit checks; the end-to-end shape gets a cheap integration grep; anything visual (a Notion-like report) needs a real render and a look, because HTML and CSS bugs never show up in asserts.",
   materials=[{"title": "The Practical Test Pyramid (Martin Fowler)", "kind": "reference", "url": "https://martinfowler.com/articles/practical-test-pyramid.html", "note": "Read the 'The Test Pyramid' section: many fast unit tests, fewer integration, fewest slow end-to-end.", "summary": "The test pyramid recommends writing many small, fast unit tests, fewer integration tests, and only a few slow end-to-end tests. Higher-level tests are more realistic but slower and more brittle, so push coverage down to the cheapest level that still catches the bug. It is the rationale for unit-testing the token functions and only screenshotting the whole report a few times."},
              {"title": "Python unittest", "kind": "language", "url": "https://docs.python.org/3/library/unittest.html", "note": "The standard-library framework for the unit-level checks on the pure functions."},
              {"title": "Playwright for Python", "kind": "tutorial", "url": "https://playwright.dev/python/docs/intro", "note": "Driving a real browser to render, screenshot and assert on the UI."}])),
]

NETWORKING = [
 ("after", "n7", dict(id="net1", kind="networking",
   title="Networking: how this report reaches the web",
   summary="Goldy is itself a networked tool. A few concepts make its links precise and durable:\n\n- **URL anatomy**: every reference is a URL with a scheme (https), a host (docs.python.org), a path (/3/library/os.path.html), an optional query string (explainshell uses ?cmd=...) and a fragment (#os.path.expanduser, which jumps to the exact definition).\n- **HTTP requests**: the research phase makes HTTP GET requests through WebFetch and WebSearch. When a site answered 403 Forbidden (a client-error status code), Goldy fell back to indexing it from search instead.\n- **API versioning**: doc links pin a version (docs.python.org/3/, Godot's /en/stable/) so they keep resolving to the right reference as upstream evolves.\n- **HTTPS and TLS**: links use https, so the connection to each source is encrypted and the server's identity is verified.",
   rationale="Reading a URL's parts, knowing what a status code means, and pinning an API version are what let Goldy deep-link to an exact, versioned, encrypted source rather than a fragile guess. The same literacy helps a developer debug any request, in any tool.",
   materials=[{"title": "What is a URL (MDN)", "kind": "reference", "url": "https://developer.mozilla.org/en-US/docs/Learn/Common_questions/Web_mechanics/What_is_a_URL", "note": "Read the 'Anatomy of a URL' section: scheme, host, port, path, query, fragment.", "summary": "A URL is made of a scheme (https), an authority (host and optional port), a path, an optional query string after ?, and an optional fragment after #. Each part has a distinct job: the query passes parameters and the fragment points at a location within the resource. This is exactly what lets a link target one function on a docs page."},
              {"title": "HTTP response status codes (MDN)", "kind": "reference", "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status", "note": "The 1xx to 5xx classes; 403 Forbidden is why LabEx was indexed from search.", "summary": "HTTP status codes are grouped: 2xx success, 3xx redirection, 4xx client errors, 5xx server errors. A 403 means the server understood the request but refuses to authorize it, so a crawler must adapt rather than retry blindly."},
              {"title": "Versioning a RESTful web API (Microsoft)", "kind": "how-to", "url": "https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design#versioning-a-restful-web-api", "note": "URI, query-string, header and media-type versioning compared.", "summary": "An API can be versioned in the URI path (/v3/), in a query string, in a custom header, or via media types. Each trades off visibility, caching and client simplicity. Pinning the version in the path, as the Python and Godot docs do, makes a link stable and obvious."},
              {"title": "HTTP (MDN)", "kind": "docs", "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP", "note": "The full reference for requests, responses, methods, headers and caching."}])),
]

# 1. apply rationale / materials / detail_tips / alternatives overrides
for n in d["nodes"]:
    e = E.get(n["id"])
    if e:
        n["rationale"] = e["rationale"]
        n["materials"] = e["materials"]
        if "detail_tips" in e:
            n["detail_tips"] = e["detail_tips"]
        if "alternatives" in e:
            n["alternatives"] = e["alternatives"]
    if n["id"] in PRIORITY:
        n["priority"] = PRIORITY[n["id"]]

# 2. drop any previously inserted insight nodes so this is idempotent
INSIGHT_KINDS = {"principle", "security", "optimization", "testing", "networking"}
d["nodes"] = [n for n in d["nodes"] if n.get("kind") not in INSIGHT_KINDS]

# 3. insert insight nodes after the node they explain
for _, anchor, node in PRINCIPLES + SECURITY + OPTIM + TESTING + NETWORKING:
    node.setdefault("rationale", "")
    idx = next((i for i, n in enumerate(d["nodes"]) if n["id"] == anchor), None)
    if idx is not None:
        d["nodes"].insert(idx + 1, node)

# 4. short, summarized titles for the long raw decision headlines, so each bubble
# reads as a label rather than a paragraph.
TITLES = {
    "n2": "Survey the project's starting point",
    "n5": "Source the report from the session transcript",
    "n9": "Lock in the parse model: decisions and actions",
    "n11": "Build the transcript parser in Python",
    "n13": "Render one self-contained HTML report",
}

# 5. story transitions: a one-sentence bridge from each node to the next, in the
# final node order. They turn the bubbles into a walkthrough; when filters discard
# nodes, the renderer stitches the discarded ones' sentences into the gap.
TRANSITIONS = {
    "n1": "To turn that brief into a plan, the first move was to see what already existed.",
    "n2": "That meant inspecting the project and where Claude Code keeps its skills and agents.",
    "n3": "The empty layout raised a question best answered by a real example.",
    "n4": "Reading an installed skill revealed a pattern worth naming.",
    "p1": "With the skill format understood, the question became where the report's content comes from.",
    "n5": "The answer was the session transcript, so its on-disk format had to be opened up.",
    "n6": "Seeing the raw events, the next step was to measure how often each kind occurs.",
    "n7": "Those events also reach out to the web, which is worth a short detour.",
    "net1": "Back in the transcript, one more check settled how a single turn is ordered.",
    "n8": "With the shape fully confirmed, the data model could be locked in.",
    "n9": "That decision rests on a principle worth stating plainly.",
    "p2": "It pairs with a second habit visible all through the build.",
    "p5": "Grounded by that preparation, the first real change to the repo could happen.",
    "n10": "Creating files and an installer immediately raises a safety concern.",
    "s2": "With the repo laid out safely, the first script could be designed.",
    "n11": "How that script reads the file is a performance choice worth noting.",
    "o1": "That efficiency reflects a broader stance about where work belongs.",
    "p3": "With the approach settled, the parser was actually written.",
    "n12": "Writing it surfaced a question about how much output to keep.",
    "o2": "Capping output also helps keep something dangerous out of the report.",
    "s1": "With extraction safe and bounded, the final stage could be designed.",
    "n13": "That design then had to become real code.",
    "n14": "Once written, the renderer had to be verified.",
    "t1": "The way it was verified points to one last principle.",
}
for n in d["nodes"]:
    if n["id"] in TITLES:
        n["title"] = TITLES[n["id"]]
    n["transition"] = TRANSITIONS.get(n["id"], "")

p.write_text(json.dumps(d, indent=2))
print("enriched", sum(1 for n in d["nodes"] if n.get("rationale")), "nodes;",
      sum(1 for n in d["nodes"] if n["kind"] == "principle"), "principles")
