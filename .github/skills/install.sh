#!/usr/bin/env bash
# Goldie installer: symlink the skills into ~/.copilot/skills so GitHub Copilot
# loads them as personal skills across every repo. Idempotent: safe to re-run
# after pulling updates. The skills also work in-place from any repo that
# vendors this `.github/skills/` directory, with no install needed.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COPILOT="${COPILOT_SKILLS_DIR:-$HOME/.copilot/skills}"

mkdir -p "$COPILOT"

link() {  # link <src> <dst>
  local src="$1" dst="$2"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    echo "  ! $dst exists and is not a symlink, skipping (move it aside first)"
    return
  fi
  ln -sfn "$src" "$dst"
  echo "  ✓ $dst -> $src"
}

chmod +x "$REPO"/goldie/scripts/*.py \
         "$REPO"/goldie-init/scripts/*.py "$REPO"/goldie-init/scripts/*.sh \
         "$REPO"/goldie-resources/scripts/*.py \
         "$REPO"/goldie-source-types/scripts/*.py 2>/dev/null || true

echo "Installing Goldie into $COPILOT"
link "$REPO/goldie"               "$COPILOT/goldie"
link "$REPO/goldie-init"          "$COPILOT/goldie-init"
link "$REPO/goldie-resources"     "$COPILOT/goldie-resources"
link "$REPO/goldie-source-types"  "$COPILOT/goldie-source-types"
link "$REPO/goldie-historian"     "$COPILOT/goldie-historian"

echo
echo "Done. In any Copilot session, ask to 'generate a Goldie report' or run goldie-init."
echo "Optional: wire $COPILOT/goldie-init/scripts/firstrun.sh into a session-start hook."
