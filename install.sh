#!/usr/bin/env bash
# Installer for `cch` — the Claude Code chat-history browser.
#
# Layout:
#   code  ->  ~/.local/share/cch/     (cch.py, cch.zsh)
#   data  ->  ~/.local/state/cch/     (stars.json, archive/, rendered/)
#
# It reads Claude Code's own logs under ~/.claude/projects (read-only) and
# never writes there. Idempotent: safe to re-run (updates the scripts, won't
# duplicate the shell source line). Migrates data from the old
# ~/.claude/history location if it's still around.
#
# Usage:
#   ./install.sh          (or:  sh install.sh)
#
# Requirements: fzf, python3.  macOS: brew install fzf

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CODE_DIR="${HOME}/.local/share/cch"
DATA_DIR="${HOME}/.local/state/cch"
OLD_DIR="${HOME}/.claude/history"

echo "cch installer"
echo "  code: ${CODE_DIR}"
echo "  data: ${DATA_DIR}"
echo

# 1. Dependency checks (warn, don't fail — user may install later).
command -v fzf     >/dev/null 2>&1 || echo "⚠  fzf not found. Install it:  brew install fzf"
command -v python3 >/dev/null 2>&1 || echo "⚠  python3 not found. Install Python 3 (3.8+)."

# 2. Install the scripts.
mkdir -p "${CODE_DIR}" "${DATA_DIR}/archive" "${DATA_DIR}/rendered"
cp "${SRC_DIR}/cch.py"  "${CODE_DIR}/cch.py"
cp "${SRC_DIR}/cch.zsh" "${CODE_DIR}/cch.zsh"
echo "✓ installed cch.py and cch.zsh to ${CODE_DIR}"

# 3. One-time migration from the old ~/.claude/history layout.
if [ -d "${OLD_DIR}" ]; then
  if [ -f "${OLD_DIR}/stars.json" ] && [ ! -f "${DATA_DIR}/stars.json" ]; then
    cp "${OLD_DIR}/stars.json" "${DATA_DIR}/stars.json"
    echo "✓ migrated favourites from ${OLD_DIR}"
  fi
  [ -d "${OLD_DIR}/archive" ]  && cp -R "${OLD_DIR}/archive/."  "${DATA_DIR}/archive/"  2>/dev/null || true
  [ -d "${OLD_DIR}/rendered" ] && cp -R "${OLD_DIR}/rendered/." "${DATA_DIR}/rendered/" 2>/dev/null || true
fi

# 4. Add the source line to the right rc file, once.
SOURCE_LINE='source "$HOME/.local/share/cch/cch.zsh"'
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
  RC="${HOME}/.zshrc"
else
  RC="${HOME}/.bashrc"
fi

if [ -f "${RC}" ] && grep -qF "cch.zsh" "${RC}"; then
  echo "✓ ${RC} already sources cch (left unchanged)"
else
  {
    echo ""
    echo "# Claude Code history browser (cch)"
    echo "${SOURCE_LINE}"
  } >> "${RC}"
  echo "✓ added source line to ${RC}"
fi

echo
echo "Done. Open a new terminal (or run: source ${RC}) and type:  cch"
