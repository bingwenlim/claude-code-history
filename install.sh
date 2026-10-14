#!/usr/bin/env bash
# Installer for `cch` — the Claude Code chat-history browser.
#
# Copies cch.py + cch.zsh into ~/.claude/history/ and adds a single source
# line to your shell rc. Idempotent: safe to re-run (it won't duplicate the
# source line, and it overwrites the scripts with the versions in this dir).
#
# Usage:
#   ./install.sh
#
# Requirements: fzf, python3. On macOS: `brew install fzf`.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${HOME}/.claude/history"

echo "cch installer"
echo "  source: ${SRC_DIR}"
echo "  dest:   ${DEST_DIR}"
echo

# 1. Dependency checks (warn, don't fail — user may install later).
if ! command -v fzf >/dev/null 2>&1; then
  echo "⚠  fzf not found. Install it before using cch:  brew install fzf"
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "⚠  python3 not found. Install Python 3 before using cch."
fi

# 2. Copy the two scripts into place.
mkdir -p "${DEST_DIR}"
cp "${SRC_DIR}/cch.py"  "${DEST_DIR}/cch.py"
cp "${SRC_DIR}/cch.zsh" "${DEST_DIR}/cch.zsh"
echo "✓ copied cch.py and cch.zsh to ${DEST_DIR}"

# 3. Add the source line to the right rc file (zsh or bash), once.
SOURCE_LINE='source "$HOME/.claude/history/cch.zsh"'
RC=""
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
  RC="${HOME}/.zshrc"
else
  RC="${HOME}/.bashrc"
fi

if [ -f "${RC}" ] && grep -qF "cch.zsh" "${RC}"; then
  echo "✓ ${RC} already sources cch.zsh (left unchanged)"
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
