#!/usr/bin/env zsh
# Claude Code history browser.
#
# Usage:
#   cch         Pick a project, then a session, in an fzf picker with live preview.
#   cch .       Skip the project picker; jump straight to the current folder's sessions.
#
# Flow:
#   Step 1  Projects, ordered by most-recent session, with that timestamp + count.
#   Step 2  Sessions in the chosen project, newest first, with live transcript preview.
#
# Keys in the SESSION picker:
#   Enter        Resume the selected session (claude --resume in its project dir)
#   Click        Single-click selects a row; press Enter to resume it
#   Ctrl-F       Favourite / unfavourite the selected session (toggles ★)
#   Ctrl-O       Render the session to HTML and open it in your browser
#   Ctrl-Y       Copy the `cd … && claude --resume …` command to the clipboard
#   [ / ]        Scroll the transcript preview up / down one line
#   PgUp/PgDn    Scroll the transcript preview a page at a time
#   Esc          Go back to the project picker
#
# Note: Shift+arrow and the mouse wheel are swallowed by Warp before fzf sees
# them, so preview scrolling is bound to [ / ] and PgUp/PgDn instead.
#
# The project picker shows a pinned "★ Favourites" row (when you have any)
# that lists your favourite chats across every folder.
#
# Requires: fzf, python3. Backend logic lives in cch.py next to this file.

# Capture this script's own directory at source time (not call time), so the
# function can find cch.py wherever the installer placed it. Override: CCH_DIR.
typeset -g _CCH_DIR="${CCH_DIR:-${${(%):-%x}:A:h}}"

cch() {
  local here="${_CCH_DIR}"
  local py="${here}/cch.py"

  if ! command -v fzf >/dev/null 2>&1; then
    print -u2 "cch: fzf not found (brew install fzf)"
    return 1
  fi
  if [[ ! -f "$py" ]]; then
    print -u2 "cch: backend not found at $py"
    return 1
  fi

  # Shortcut: `cch .` jumps straight into the current directory's sessions.
  local jump_cwd=""
  if [[ "$1" == "." ]]; then
    jump_cwd="$PWD"
  fi

  while true; do
    local chosen_cwd="$jump_cwd"

    # ---- Step 1: pick a project (unless we were handed one) ----
    if [[ -z "$chosen_cwd" ]]; then
      local prow
      prow=$(
        python3 "$py" projects \
          | fzf \
              --ansi \
              --delimiter='\t' \
              --with-nth=2.. \
              --height=90% \
              --layout=reverse \
              --border=rounded \
              --prompt='project ❯ ' \
              --header=$'pick a project · ★ Favourites holds your starred chats' \
              --preview="COLUMNS=\$FZF_PREVIEW_COLUMNS python3 ${py} projpreview {1}" \
              --preview-window='right:55%' \
              --bind=']:preview-down,[:preview-up' \
              --bind='page-down:preview-page-down,page-up:preview-page-up'
      )
      [[ -z "$prow" ]] && return 0           # Esc at project list → quit
      chosen_cwd=$(printf '%s' "$prow" | awk -F'\t' '{print $1}')
    fi

    # ---- Step 2: pick a session within that project ----
    # The "::starred::" sentinel means "show favourites across all folders".
    local src_cmd
    if [[ "$chosen_cwd" == "::starred::" ]]; then
      src_cmd="python3 ${py} starred"
    else
      src_cmd="python3 ${py} list ${(q)chosen_cwd}"
    fi

    local srow
    srow=$(
      eval "$src_cmd" \
        | fzf \
            --ansi \
            --delimiter='\t' \
            --with-nth=4.. \
            --height=90% \
            --layout=reverse \
            --border=rounded \
            --prompt='session ❯ ' \
            --header=$'enter/click: resume │ ctrl-f: ★ favourite │ ctrl-o: html │ ctrl-y: copy │ [ ] pgup/pgdn: scroll │ esc: back' \
            --preview="COLUMNS=\$FZF_PREVIEW_COLUMNS python3 ${py} preview {1}" \
            --preview-window='right:55%' \
            --bind="ctrl-f:execute-silent(python3 ${py} toggle {2} {3})+reload(${src_cmd})" \
            --bind="ctrl-o:execute-silent(open \$(python3 ${py} html {1}))" \
            --bind="ctrl-y:execute-silent(printf 'cd %q && claude --resume %s' {3} {2} | pbcopy)" \
            --bind="page-down:preview-page-down,page-up:preview-page-up" \
            --bind=']:preview-down,[:preview-up'
    )

    if [[ -z "$srow" ]]; then
      # Esc in the session list: go back to projects, unless we jumped
      # straight here via `cch .`, in which case just quit.
      [[ -n "$jump_cwd" ]] && return 0
      continue
    fi

    local sid cwd
    sid=$(printf '%s' "$srow" | awk -F'\t' '{print $2}')
    cwd=$(printf '%s' "$srow" | awk -F'\t' '{print $3}')

    # If this is a favourite whose live transcript was cleaned up, restore the
    # archived copy to its original path so `claude --resume` can find it.
    python3 "$py" restore "$sid" >/dev/null 2>&1

    if [[ -d "$cwd" ]]; then
      builtin cd "$cwd" || return 1
    fi
    print -P "%F{cyan}▸ resuming%f ${sid}  %F{244}(${cwd})%f"
    claude --resume "$sid"
    return 0
  done
}
