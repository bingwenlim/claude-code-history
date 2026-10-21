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

Clone it somewhere permanent (the clone *is* the install — you run cch from it
and `git pull` to update):

```sh
git clone https://github.com/bingwenlim/claude-code-history.git ~/claude-code-history
cd ~/claude-code-history
./install.sh
```

If `./install.sh` reports "permission denied", run `sh install.sh` instead
(git didn't preserve the executable bit).

The installer adds one `source` line to your `~/.zshrc` (or `~/.bashrc`)
pointing at this clone — no files are copied elsewhere. User data (favourites,
archived transcripts, HTML exports) lives separately in `~/.local/state/cch/`,
so it's never mixed into the git checkout. Re-running is safe and migrates data
from the old `~/.claude/history` location if present.

Then open a new terminal (or `source ~/.zshrc`) and run the command — it's
called `cch`:

```sh
cch
```

## Update

From the clone:

```sh
git pull
```

That's it — cch runs directly from the checkout, so a pull is the update.
(Re-running `./install.sh` is harmless but unnecessary.)

## Uninstall

Remove the two lines under `# Claude Code history browser (cch)` from your
`~/.zshrc`, then delete the clone and your data:

```sh
rm -rf ~/claude-code-history ~/.local/state/cch
```

Your Claude Code sessions under `~/.claude/projects` are never touched by cch.

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

- Code runs from your clone (e.g. `~/claude-code-history`). Your data
  (`stars.json`, `archive/`, `rendered/`) lives in `~/.local/state/cch/` —
  separate from the checkout. Override the data location with the
  `CCH_DATA_DIR` env var. Nothing personal is committed to the repo.
- cch only ever **reads** `~/.claude/projects` — it never writes to Claude
  Code's own files.
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
