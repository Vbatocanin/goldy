#!/usr/bin/env bash
# Goldie first-run nudge.
#
# Fires once per repo: if the project has documentation but no Goldie profile
# yet (.goldie/profile.json is missing), it prints an instruction that Copilot
# picks up as context, asking it to run the goldie-init wizard. Once the profile
# is saved the condition is false, so it never nudges again.
#
# Wire it up where your Copilot surface supports a session-start or pre-prompt
# hook (for example the Copilot CLI). It stays silent in non-projects (no docs,
# no manifests) and in any repo already initialized or skipped
# (.goldie/.init-skipped).
set -euo pipefail

[ -f ".goldie/profile.json" ] && exit 0
[ -f ".goldie/.init-skipped" ] && exit 0

# Only nudge in something that looks like a real codebase.
has_signal=0
for f in AGENTS.md CLAUDE.md README.md README.rst package.json pyproject.toml \
         requirements.txt go.mod Cargo.toml Gemfile composer.json pom.xml; do
  [ -e "$f" ] && { has_signal=1; break; }
done
[ "$has_signal" -eq 0 ] && exit 0

cat <<'MSG'
[Goldie] This repo has documentation but no Goldie profile yet
(.goldie/profile.json is missing). Before doing other work, run the goldie-init
wizard once: invoke the goldie-init skill, which scans the repo, reads AGENTS.md
and the other doc files, asks the user a few short questions, and saves the
profile so future Goldie reports are tailored to this codebase. If the user
declines, create an empty .goldie/.init-skipped file so this stops asking.
MSG
exit 0
