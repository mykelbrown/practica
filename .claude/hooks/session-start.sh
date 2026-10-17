#!/bin/bash
# Prepares a Claude Code cloud session for Practica and reports where the learner is.
# Practica needs only python3, bash and git (standard library only), so nothing is installed.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PRACTICA=(python3 "$ROOT/bin/practica.py")

# ~/practica, ~/devops-lab and ~/.local/bin/practica, so lesson paths and the command work.
"${PRACTICA[@]}" setup >/dev/null
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
fi

# Everything printed below becomes context for the session, so Claude resumes the course.
echo "== Practica session context =="
"${PRACTICA[@]}" doctor | tail -1
"${PRACTICA[@]}" status || true
echo
"${PRACTICA[@]}" next || true
