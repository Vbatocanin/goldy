#!/usr/bin/env bash
# Rebuild the self-referential demo: one report per session under reports/, plus
# the master history index at goldy-report.html. Idempotent.
set -euo pipefail
cd "$(dirname "$0")"
SK=../skills/goldy/scripts

# 1. enrich the primary (Building Goldy) session in place
python3 enrich.py

# 2. render one report per conversation, registering each in reports/index.json
python3 "$SK/render.py" nodes.json \
  -o reports/building-goldy.html --id building-goldy --register
python3 "$SK/render.py" sessions/interactive-graph.json \
  -o reports/interactive-graph.html --id interactive-graph --register

# 3. build the master index that links to them all
python3 "$SK/render_index.py" reports -o goldy-report.html

echo "built: $(ls reports/*.html | wc -l | tr -d ' ') reports + master index"
echo "dashes in output: $(grep -rc '—\|–' goldy-report.html reports/*.html | grep -v ':0' || echo none)"
