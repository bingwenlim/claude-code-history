#!/usr/bin/env python3
"""Claude Code history helper.

Subcommands:
  projects          Emit one row per project for fzf (plus a ★ Favourites row).
                    Columns: cwd \t display
  list [cwd]        Emit one row per session (optionally filtered to cwd).
                    Columns: file \t sessionId \t cwd \t display
  starred           Like list, but only starred sessions, across all projects.
  toggle <id> [cwd] Favourite/unfavourite a session; also archives/un-archives
                    its transcript so cleanupPeriodDays can't lose a favourite.
  restore <id>      Restore a favourite's archived transcript to its original
                    path if the live copy was cleaned up; prints its cwd.
  preview <file>    Render a readable transcript preview for the fzf side pane.
  html <file>       Render the full session to an HTML file; print its path.

Session files live under ~/.claude/projects/<slug>/<uuid>.jsonl
Stars are stored in ~/.claude/history/stars.json (keyed by session id).
"""
import sys
import os
import json
import html
import shutil
import textwrap
import datetime
from pathlib import Path

# Claude Code's own session logs — we only ever READ these, never write.
PROJECTS = Path.home() / ".claude" / "projects"

# Our user data (favourites, archived transcripts, HTML exports) lives apart
# from Claude Code's dir, under XDG state. Override with CCH_DATA_DIR.
DATA_DIR = Path(os.environ.get("CCH_DATA_DIR", Path.home() / ".local" / "state" / "cch"))
HTML_OUT = DATA_DIR / "rendered"
STARS_FILE = DATA_DIR / "stars.json"
ARCHIVE_DIR = DATA_DIR / "archive"

# ANSI colors for the fzf preview pane
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def load_stars():
    """Return the stars map {session_id: {starred_at, cwd, title}} (never None)."""
    try:
        with open(STARS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {}


def save_stars(stars):
    """Write the stars map atomically."""
    STARS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STARS_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(stars, fh, indent=2, sort_keys=True)
    os.replace(tmp, STARS_FILE)


def short_path(path, segments=2):
    """Human-friendly short path, anchored on ~ for the home directory.

    Examples (home = /Users/you):
      /Users/you/data-dbt                     -> ~/data-dbt
      /Users/you/work-app/App                 -> ~/work-app/App  (capped)
      /Users/you/a/b/c/d                      -> ~/…/c/d
      /opt/some/other/place                   -> …/other/place
    """
    if not path or path == "?":
        return "?"
    home = str(Path.home())
    p = path.rstrip("/")
    anchored = False
    if p == home or p.startswith(home + "/"):
        p = "~" + p[len(home):]
        anchored = True

    parts = p.split("/")
    # Keep the anchor (~) plus up to `segments` trailing components.
    if anchored:
        head, tail = parts[0], [x for x in parts[1:] if x]
        if len(tail) <= segments:
            return "/".join([head] + tail) if tail else head
        return "/".join([head, "…"] + tail[-segments:])
    else:
        comps = [x for x in parts if x]
        if len(comps) <= segments:
            return "/".join(comps)
        return "…/" + "/".join(comps[-segments:])


def path_header(path, maxlen=50):
    """Full ~-anchored path, kept as long as fits in `maxlen` chars.

    Unlike short_path (fixed segment count), this keeps the whole tail up to a
    character budget — 2 segments isn't always enough. Truncation drops from
    the FRONT (the meaningful folder is the tail) with a leading "…/".

    Examples (home = /Users/you, maxlen 50):
      /Users/you/data-dbt
        -> ~/data-dbt
      /Users/you/some-long-project/functions/stx/prediction-model
        -> …/functions/stx/prediction-model
    """
    if not path or path == "?":
        return "?"
    home = str(Path.home())
    p = path.rstrip("/")
    if p == home or p.startswith(home + "/"):
        p = "~" + p[len(home):]
    if len(p) <= maxlen:
        return p
    # Drop whole leading segments until the tail fits (reserve 2 for "…/").
    parts = p.split("/")
    budget = maxlen - 2
    tail = []
    for seg in reversed(parts):
        candidate = seg + ("/" + "/".join(tail) if tail else "")
        if len(candidate) > budget and tail:
            break
        tail.insert(0, seg)
    kept = "/".join(tail)
    # If even one segment overflows, hard-truncate it from the front.
    if len(kept) > budget:
        kept = kept[-(budget):]
    return "…/" + kept


def iter_lines(fp):
    """Yield parsed JSON objects from a .jsonl file, skipping bad lines."""
    try:
        with open(fp, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        return


def text_from_content(content, prose_only=False):
    """Flatten a message `content` (str or list of blocks) to plain text.

    When prose_only is True, tool calls, tool results, and thinking blocks are
    dropped entirely — only human/assistant prose survives. This is what the UI
    uses so previews aren't buried in `[tool: Bash]` / `[tool result]` noise.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                parts.append(b.get("text", ""))
            elif prose_only:
                continue
            elif bt == "tool_use":
                parts.append(f"[tool: {b.get('name', '?')}]")
            elif bt == "tool_result":
                parts.append("[tool result]")
            elif bt == "thinking":
                parts.append("[thinking]")
        return "\n".join(p for p in parts if p)
    return ""


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def session_meta(fp):
    """Extract summary metadata for one session file."""
    title = None
    cwd = None
    session_id = Path(fp).stem
    last_ts = None
    last_prompt = None
    first_user = None
    user_msgs = 0

    for o in iter_lines(fp):
        t = o.get("type")
        if t == "ai-title" and o.get("aiTitle"):
            title = o["aiTitle"]
        elif t == "last-prompt" and o.get("lastPrompt"):
            last_prompt = o["lastPrompt"]
        if o.get("cwd") and cwd is None:
            # Keep the FIRST cwd — where the session started, which is the
            # project dir claude --resume uses. A session may cd elsewhere
            # mid-run; overwriting would wrongly report that later directory.
            cwd = o["cwd"]
        if o.get("timestamp"):
            last_ts = o["timestamp"]
        if t == "user":
            msg = o.get("message", {})
            txt = text_from_content(msg.get("content"))
            # Skip tool-result-only user turns and system noise
            if txt and not txt.startswith("[tool") and "<" not in txt[:1]:
                user_msgs += 1
                if first_user is None:
                    first_user = txt

    # Fall back to file mtime if no timestamp in content
    if not last_ts:
        try:
            last_ts = datetime.datetime.fromtimestamp(
                os.path.getmtime(fp), tz=datetime.timezone.utc
            ).isoformat()
        except OSError:
            pass

    # Build the label from the ai-title, else the first user message.
    label = title or first_user or "(untitled)"
    label = " ".join(label.split())      # collapse newlines/runs of whitespace
    # Cap length: some sessions have no ai-title and fall back to a huge pasted
    # first message (thousands of chars). Left uncapped, that floods the preview
    # header and breaks fzf's scroll tracking. 100 chars is plenty for a label.
    if len(label) > 100:
        label = label[:99].rstrip() + "…"
    return {
        "file": str(fp),
        "session_id": session_id,
        "cwd": cwd or "?",
        "title": label,
        "last_ts": last_ts,
        "last_prompt": last_prompt,
        "first_user": first_user,
        "user_msgs": user_msgs,
    }


def human_time(dt):
    if not dt:
        return "        ?       "
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - dt
    secs = delta.total_seconds()
    if secs < 3600:
        rel = f"{int(secs // 60)}m ago"
    elif secs < 86400:
        rel = f"{int(secs // 3600)}h ago"
    elif secs < 86400 * 7:
        rel = f"{int(secs // 86400)}d ago"
    else:
        rel = dt.astimezone().strftime("%Y-%m-%d")
    return f"{rel:>8}"


def gather_sessions(cwd_filter=None):
    """Return [(sort_key, meta), ...] newest-first for all non-empty sessions.

    If cwd_filter is given, only sessions whose cwd matches are returned.
    """
    metas = []
    if PROJECTS.is_dir():
        # Only top-level session files: projects/<slug>/<uuid>.jsonl (depth 2).
        # Nested files live under <session-id>/subagents/agent-*.jsonl — those
        # are subagent transcripts, not independently resumable sessions, and
        # they lack an ai-title, so they must not appear in the list.
        for p in PROJECTS.glob("*/*.jsonl"):
            m = session_meta(p)
            # Skip trivial/empty sessions
            if m["user_msgs"] == 0:
                continue
            if cwd_filter is not None and m["cwd"] != cwd_filter:
                continue
            dt = parse_ts(m["last_ts"])
            # Sort key: real last-activity time; fall back to mtime
            if dt is not None:
                sort_key = dt.timestamp()
            else:
                try:
                    sort_key = p.stat().st_mtime
                except OSError:
                    sort_key = 0.0
            metas.append((sort_key, m))
    metas.sort(key=lambda x: x[0], reverse=True)
    return metas


def cmd_projects():
    """One row per project (cwd), sorted by its most recent session.

    A pinned "★ Starred (N)" virtual row is prepended when any stars exist.
    Columns: cwd \t display
    (the starred row uses the sentinel cwd "::starred::")
    """
    metas = gather_sessions()
    stars = load_stars()

    # Keep the newest session's sort_key per cwd, plus a session count.
    best = {}  # cwd -> [sort_key, count]
    for sort_key, m in metas:
        cwd = m["cwd"]
        # Skip phantom "projects": unknown cwd or a directory that no longer
        # exists (e.g. deleted worktrees, or odd nested session paths).
        if cwd == "?" or not os.path.isdir(cwd):
            continue
        if cwd not in best:
            best[cwd] = [sort_key, 0]
        best[cwd][1] += 1
        if sort_key > best[cwd][0]:
            best[cwd][0] = sort_key

    ordered = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)
    rows = []

    # Pinned starred row (only if there are stars).
    if stars:
        n = len(stars)
        label = "★ Favourites"
        display = (
            f"{'':8}  {MAGENTA}{BOLD}{label:<30.30}{RESET}"
            f"  {DIM}{n} chat" + ("s" if n != 1 else "") + f"{RESET}"
        )
        rows.append(f"::starred::\t{display}")

    for cwd, (sort_key, count) in ordered:
        dt = datetime.datetime.fromtimestamp(sort_key, tz=datetime.timezone.utc)
        rel = human_time(dt)
        label = short_path(cwd, 2)
        n = f"{count} session" + ("s" if count != 1 else "")
        display = (
            f"{rel}  {CYAN}{BOLD}{label:<30.30}{RESET}  {DIM}{n}{RESET}"
        )
        rows.append(f"{cwd}\t{display}")
    sys.stdout.write("\n".join(rows) + ("\n" if rows else ""))


def _session_display(m, stars, show_proj):
    """Build the visible column for one session row (with ★ if starred)."""
    dt = parse_ts(m["last_ts"])
    rel = human_time(dt)
    title = m["title"].replace("\t", " ").replace("\n", " ")
    if len(title) > 120:                 # keep list rows to one tidy line
        title = title[:119] + "…"
    star = f"{MAGENTA}★{RESET} " if m["session_id"] in stars else "  "
    if show_proj:
        proj = short_path(m["cwd"], 2)
        return f"{star}{rel}  {CYAN}{proj:<24.24}{RESET}  {title}"
    return f"{star}{rel}  {title}"


def cmd_list(cwd_filter=None):
    metas = gather_sessions(cwd_filter)
    stars = load_stars()
    rows = []
    for _, m in metas:
        # Within one project the path is redundant; across projects show it.
        display = _session_display(m, stars, show_proj=(cwd_filter is None))
        rows.append(f"{m['file']}\t{m['session_id']}\t{m['cwd']}\t{display}")
    sys.stdout.write("\n".join(rows) + ("\n" if rows else ""))


def cmd_projpreview(cwd):
    """Preview shown for a project in the picker: a full-path header (like the
    chat preview) followed by that project's session titles, newest-first.
    """
    width = shutil.get_terminal_size((80, 24)).columns
    width = max(40, min(width, 140))
    stars = load_stars()

    out = []
    if cwd == "::starred::":
        out.append(f"{BOLD}{MAGENTA}★ Favourites{RESET}")
        out.append(f"{DIM}starred chats across every folder{RESET}")
        metas = [(0, m) for m in _starred_metas(stars)]
    else:
        out.append(f"{BOLD}{path_header(cwd, 50)}{RESET}")
        n = sum(1 for _, m in gather_sessions(cwd))
        out.append(f"{DIM}{n} session" + ("s" if n != 1 else "") + f"{RESET}")
        metas = gather_sessions(cwd)
    out.append(f"{DIM}{'─' * (width - 2)}{RESET}")
    out.append("")

    for _, m in metas:
        dt = parse_ts(m["last_ts"])
        rel = human_time(dt)
        title = m["title"].replace("\t", " ").replace("\n", " ")
        if len(title) > width - 14:
            title = title[: width - 15] + "…"
        star = f"{MAGENTA}★{RESET} " if m["session_id"] in stars else "  "
        out.append(f"{star}{DIM}{rel}{RESET}  {title}")
    sys.stdout.write("\n".join(out) + "\n")



def _starred_metas(stars):
    """Return meta dicts for all starred sessions, newest-first.

    Uses the live session if still on disk, else synthesizes a minimal meta
    from the cached star info (so cleaned-up favourites still render).
    """
    found = {}
    for _, m in gather_sessions():
        found[m["session_id"]] = m
    rows = []
    for sid, info in stars.items():
        m = found.get(sid)
        if m is None:
            m = {
                "file": info.get("file", ""),
                "session_id": sid,
                "cwd": info.get("cwd", "?"),
                "title": info.get("title", "(session not found)"),
                "last_ts": info.get("starred_at"),
            }
        rows.append(m)
    rows.sort(key=lambda m: m.get("last_ts") or "", reverse=True)
    return rows


def cmd_starred():
    """List starred sessions across all projects, newest-first."""
    stars = load_stars()
    if not stars:
        return
    out = []
    for m in _starred_metas(stars):
        display = _session_display(m, stars, show_proj=True)
        out.append(f"{m['file']}\t{m['session_id']}\t{m['cwd']}\t{display}")
    sys.stdout.write("\n".join(out) + ("\n" if out else ""))


def _archive_path(session_id):
    return ARCHIVE_DIR / f"{session_id}.jsonl"


def cmd_toggle(session_id, cwd="", file="", title=""):
    """Toggle a favourite for session_id.

    On favourite: cache cwd/title/file + copy the transcript into the archive
    so it survives Claude Code's cleanupPeriodDays auto-deletion.
    On unfavourite: remove the archived copy.
    """
    stars = load_stars()
    if session_id in stars:
        # Unfavourite: drop the star and its archived copy.
        del stars[session_id]
        try:
            _archive_path(session_id).unlink()
        except OSError:
            pass
    else:
        entry = {"cwd": cwd, "file": file, "title": title}
        for _, m in gather_sessions(cwd or None):
            if m["session_id"] == session_id:
                entry["cwd"] = m["cwd"]
                entry["file"] = m["file"]
                entry["title"] = m["title"]
                entry["starred_at"] = m["last_ts"]
                break
        # Archive the transcript so cleanup can't lose a favourite.
        src = entry.get("file")
        if src and os.path.isfile(src):
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, _archive_path(session_id))
                entry["archived"] = True
            except OSError:
                entry["archived"] = False
        stars[session_id] = entry
    save_stars(stars)


def cmd_restore(session_id):
    """If a favourite's live transcript was cleaned up, copy the archived copy
    back to its original path so `claude --resume` works again.

    Prints the cwd on success (so the shell can cd there), nothing on failure.
    """
    stars = load_stars()
    entry = stars.get(session_id)
    if not entry:
        return
    dest = entry.get("file")
    arch = _archive_path(session_id)
    if dest and not os.path.isfile(dest) and arch.is_file():
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(arch, dest)
        except OSError:
            return
    if dest and os.path.isfile(dest):
        print(entry.get("cwd", ""))


def _wrap_message(who_label, who_color, text, width):
    """Render one message as colored lines, wrapped with a hanging indent.

    The speaker label sits in a 2-space gutter; wrapped continuation lines are
    indented to the same text column so it's always clear where a message
    starts and ends — no more flush-left wrap soup.
    """
    gutter = "  "          # left margin before text
    indent = " " * len(gutter)
    # Reserve the gutter plus a 1-col safety margin so unbreakable tokens
    # (em dashes, emoji, long `code` spans) rarely spill past the pane edge.
    text_width = max(20, width - len(gutter) - 1)
    lines = [f"{gutter}{who_color}{who_label}{RESET}"]
    in_code = False        # inside a ``` fenced block?
    for para in text.splitlines():
        para = para.rstrip()
        stripped = para.lstrip()
        # Toggle fenced-code state on ``` lines (and render the fence itself).
        if stripped.startswith("```"):
            in_code = not in_code
            lines.append(f"{indent}{DIM}{para[:text_width]}{RESET}")
            continue
        if not para:
            lines.append("")
            continue
        # Inside code, or long unbroken tokens (paths, URLs): truncate rather
        # than word-wrap, which would otherwise produce unreadable soup.
        if in_code or (" " not in stripped and len(para) > text_width):
            lines.append(f"{indent}{DIM}{para[:text_width]}{RESET}")
            continue
        wrapped = textwrap.wrap(
            para,
            width=text_width,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]
        for wl in wrapped:
            lines.append(f"{indent}{wl}")
    return lines


def cmd_preview(fp):
    m = session_meta(fp)
    dt = parse_ts(m["last_ts"])
    when = dt.astimezone().strftime("%Y-%m-%d %H:%M") if dt else "?"

    # Detect the preview pane width so text wraps to fit instead of relying on
    # the terminal's hard wrap (which breaks mid-word and ruins readability).
    # fzf exports its pane width via COLUMNS (= $FZF_PREVIEW_COLUMNS) and
    # re-runs this command on resize, so wrapping stays dynamic.
    width = shutil.get_terminal_size((80, 24)).columns
    width = max(40, min(width, 140))

    out = []
    # Wrap the title to the pane width so long titles don't hard-break mid-word.
    # Allow breaking long tokens (URLs/paths) so nothing runs off the edge.
    title_lines = textwrap.wrap(
        m["title"], width=max(20, width - 1), break_long_words=True
    ) or [m["title"]]
    for tl in title_lines:
        out.append(f"{BOLD}{tl}{RESET}")
    out.append(f"{DIM}{when}  ·  {short_path(m['cwd'], 3)}{RESET}")
    out.append("")
    out.append(f"{DIM}{'─' * (width - 2)}{RESET}")
    out.append(f"{DIM}newest first ↓{RESET}")

    # Collect prose-only turns (no tool calls / results / thinking), then show
    # newest-first so the last thing before the crash is at the top.
    turns = []
    for o in iter_lines(fp):
        t = o.get("type")
        if t not in ("user", "assistant"):
            continue
        msg = o.get("message", {})
        txt = text_from_content(msg.get("content"), prose_only=True).strip()
        if not txt:                      # tool-only turn → skip entirely
            continue
        if t == "user" and txt.startswith("<"):
            continue
        turns.append((t, txt))

    total = len(turns)
    # Keep only the most recent slice; preview is for orientation, not reading.
    shown = turns[-40:]
    dropped = total - len(shown)
    for t, txt in reversed(shown):
        if t == "user":
            who, color = "You", GREEN
        else:
            who, color = "Claude", YELLOW
        out.append("")
        out.extend(_wrap_message(who, color, txt, width))
    if dropped > 0:
        out.append("")
        out.append(
            f"{DIM}· {dropped} earlier message(s) — Ctrl-O opens the full "
            f"transcript{RESET}"
        )
    sys.stdout.write("\n".join(out) + "\n")


def cmd_html(fp):
    m = session_meta(fp)
    HTML_OUT.mkdir(parents=True, exist_ok=True)
    dt = parse_ts(m["last_ts"])
    when = dt.astimezone().strftime("%Y-%m-%d %H:%M") if dt else "?"

    blocks = []
    for o in iter_lines(fp):
        t = o.get("type")
        if t not in ("user", "assistant"):
            continue
        msg = o.get("message", {})
        txt = text_from_content(msg.get("content"), prose_only=True).strip()
        if not txt:
            continue
        if t == "user" and txt.startswith("<"):
            continue
        cls = "user" if t == "user" else "assistant"
        who = "You" if t == "user" else "Claude"
        esc = html.escape(txt)
        blocks.append(
            f'<div class="turn {cls}"><div class="who">{who}</div>'
            f'<div class="body"><pre>{esc}</pre></div></div>'
        )

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(m['title'])}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 15px/1.6 -apple-system, system-ui, sans-serif;
       max-width: 820px; margin: 0 auto; padding: 2rem 1.5rem;
       background: Canvas; color: CanvasText; }}
header {{ border-bottom: 1px solid color-mix(in srgb, CanvasText 15%, transparent);
         padding-bottom: 1rem; margin-bottom: 1.5rem; }}
h1 {{ font-size: 1.3rem; margin: 0 0 .3rem; }}
.meta {{ font-size: .8rem; opacity: .6; }}
.turn {{ margin: 1.1rem 0; }}
.who {{ font-weight: 600; font-size: .78rem; text-transform: uppercase;
        letter-spacing: .04em; opacity: .55; margin-bottom: .3rem; }}
.user .who {{ color: #3b9e5a; }}
.assistant .who {{ color: #c08a2d; }}
.body {{ background: color-mix(in srgb, CanvasText 5%, transparent);
         border-radius: 10px; padding: .7rem 1rem; }}
.user .body {{ background: color-mix(in srgb, #3b9e5a 10%, transparent); }}
pre {{ margin: 0; white-space: pre-wrap; word-break: break-word;
       font: inherit; }}
</style></head><body>
<header><h1>{html.escape(m['title'])}</h1>
<div class="meta">{when} &middot; {html.escape(m['cwd'])}<br>session {m['session_id']}</div>
</header>
{''.join(blocks)}
</body></html>"""

    out_path = HTML_OUT / f"{m['session_id']}.html"
    out_path.write_text(doc, encoding="utf-8")
    print(out_path)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "projects":
        cmd_projects()
    elif cmd == "list":
        cmd_list(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "starred":
        cmd_starred()
    elif cmd == "projpreview" and len(sys.argv) > 2:
        cmd_projpreview(sys.argv[2])
    elif cmd == "toggle" and len(sys.argv) > 2:
        # toggle <session_id> [cwd]
        cmd_toggle(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    elif cmd == "restore" and len(sys.argv) > 2:
        cmd_restore(sys.argv[2])
    elif cmd == "preview" and len(sys.argv) > 2:
        cmd_preview(sys.argv[2])
    elif cmd == "html" and len(sys.argv) > 2:
        cmd_html(sys.argv[2])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
