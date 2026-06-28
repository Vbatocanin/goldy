#!/usr/bin/env bash
# Goldy first-run nudge (SessionStart hook).
#
# Fires once per repo: if the project has documentation but no Goldy profile yet
# (.goldy/profile.json is missing), it prints an instruction that Claude Code
# picks up as context, asking Claude to run the goldy-init wizard. Once the
# profile is saved the condition is false, so it never nudges again.
#
# It stays silent in non-projects (no docs, no manifests) and in any repo that
# has already been initialized or explicitly skipped (.goldy/.init-skipped).
set -euo pipefail

[ -f ".goldy/profile.json" ] && exit 0
[ -f ".goldy/.init-skipped" ] && exit 0

# Only nudge in something that looks like a real codebase.
has_signal=0
for f in CLAUDE.md AGENTS.md README.md README.rst package.json pyproject.toml \
         requirements.txt go.mod Cargo.toml Gemfile composer.json pom.xml; do
  [ -e "$f" ] && { has_signal=1; break; }
done
[ "$has_signal" -eq 0 ] && exit 0

cat <<'MSG'
[Goldy] This repo has documentation but no Goldy profile yet (.goldy/profile.json
is missing). Before doing other work, run the goldy-init wizard once: invoke the
goldy-init skill, which scans the repo, reads CLAUDE.md and the other doc files,
asks the user a few short questions, and saves the profile so future Goldy
reports are tailored to this codebase. If the user declines, create an empty
.goldy/.init-skipped file so this stops asking.
MSG
exit 0
