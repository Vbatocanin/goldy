#!/usr/bin/env bash
# Goldy installer: symlink the skill and agent into ~/.claude so Claude Code
# loads them. Idempotent: safe to re-run after pulling updates.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

mkdir -p "$CLAUDE/skills" "$CLAUDE/agents"

link() {  # link <src> <dst>
  local src="$1" dst="$2"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    echo "  ! $dst exists and is not a symlink, skipping (move it aside first)"
    return
  fi
  ln -sfn "$src" "$dst"
  echo "  ✓ $dst -> $src"
}

chmod +x "$REPO"/skills/goldy/scripts/*.py "$REPO"/skills/goldy-init/scripts/*.sh 2>/dev/null || true

echo "Installing Goldy into $CLAUDE"
link "$REPO/skills/goldy"               "$CLAUDE/skills/goldy"
link "$REPO/skills/goldy-init"          "$CLAUDE/skills/goldy-init"
link "$REPO/skills/goldy-resources"     "$CLAUDE/skills/goldy-resources"
link "$REPO/skills/goldy-source-types"  "$CLAUDE/skills/goldy-source-types"
link "$REPO/agents/goldy-historian.md"  "$CLAUDE/agents/goldy-historian.md"

# Register the first-run nudge as a SessionStart hook (idempotent).
HOOK="$CLAUDE/skills/goldy-init/scripts/firstrun.sh"
SETTINGS="$CLAUDE/settings.json"
if command -v python3 >/dev/null 2>&1; then
  python3 - "$SETTINGS" "$HOOK" <<'PY'
import json, os, sys
settings_path, hook = sys.argv[1], sys.argv[2]
try:
    cfg = json.load(open(settings_path))
except Exception:
    cfg = {}
hooks = cfg.setdefault("hooks", {})
arr = hooks.setdefault("SessionStart", [])
cmd = f"bash {hook}"
already = any(
    h.get("command") == cmd
    for grp in arr if isinstance(grp, dict)
    for h in grp.get("hooks", []) if isinstance(h, dict)
)
if not already:
    arr.append({"hooks": [{"type": "command", "command": cmd}]})
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    json.dump(cfg, open(settings_path, "w"), indent=2)
    print("  + registered goldy-init first-run SessionStart hook")
else:
    print("  = first-run hook already registered")
PY
fi

echo
echo "Done. In any Claude Code session, run /goldy or ask for a Goldy report."
