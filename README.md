# cch — Claude Code chat-history browser

A fast terminal UI for browsing, reading, resuming, and favouriting your
Claude Code sessions. Built on `fzf` with a Python backend that reads the
session logs under `~/.claude/projects`.

## What it does

- **Browse by project, then session** — projects ordered by most-recent
  activity; pick one to see its chats (newest first).
- **Live transcript preview** — read a chat (newest message first, tool noise
  stripped, wrapped to the pane) before deciding to resume it.
- **Resume** — Enter jumps back into a session with `claude --resume`.
- **Favourites** — star chats across any folder (`Ctrl-F`); reach them via the
  pinned `★ Favourites` row. Favourited transcripts are archived so they
  survive Claude Code's auto-cleanup, and auto-restored on resume.
- **Export to HTML** — `Ctrl-O` renders a chat to a styled page in your browser.

## Requirements

- [`fzf`](https://github.com/junegunn/fzf) — `brew install fzf`
- `python3` (3.8+)
- zsh (bash works too; the installer picks your rc file)

## Install

```sh
./install.sh
```

This copies `cch.py` and `cch.zsh` into `~/.claude/history/` and adds one
`source` line to your `~/.zshrc` (or `~/.bashrc`). It's idempotent — re-running
updates the scripts without duplicating the source line.

Then open a new terminal (or `source ~/.zshrc`) and run:

```sh
cch
```

## Keys

**Project picker**

| Key        | Action                                  |
|------------|-----------------------------------------|
| Enter      | Open the project's session list         |
| `[` / `]`  | Scroll the preview up / down            |
| Esc        | Quit                                    |

**Session picker**

| Key          | Action                                        |
|--------------|-----------------------------------------------|
| Enter / click| Resume the selected session                   |
| Ctrl-F       | Favourite / unfavourite (toggles ★)           |
| Ctrl-O       | Render the chat to HTML and open it           |
| Ctrl-Y       | Copy the `cd … && claude --resume …` command  |
| `[` / `]`    | Scroll the transcript up / down one line      |
| PgUp / PgDn  | Scroll the transcript a page at a time        |
| Esc          | Back to the project picker                    |

Shortcut: `cch .` jumps straight to the current folder's sessions.

## Notes

- Nothing personal is bundled — the scripts use only `$HOME`-relative paths.
  Your favourites (`stars.json`), archived transcripts (`archive/`), and HTML
  exports (`rendered/`) are created locally and are not part of the package.
- Preview scrolling uses `[` `]` and PgUp/PgDn because some terminals (e.g.
  Warp) swallow Shift+arrow and the mouse wheel before `fzf` sees them.

## Optional: keep history longer

Claude Code deletes session transcripts after `cleanupPeriodDays` (default 30).
If you want sessions to live longer, add this to `~/.claude/settings.json`
(this is a personal choice and is **not** done by the installer):

```json
{ "cleanupPeriodDays": 365 }
```

`cch` already archives favourited chats regardless of this setting.
