# Claude Code status line

A custom status line for Claude Code that shows the current directory, model,
context-window usage, and 5-hour/weekly rate-limit usage as colored gauges.
When run inside a git repo, a second line shows the branch, dirty state, and
ahead/behind-upstream counts.

Example output:

```
MemButler | Sonnet 4.6 | ctx ████░░░░░░ 43% | 5h ███████░░░ 72% 02:10 | 7d █████████░ 91% Fri 08:00
main ● ↑2 ↓1
```

- `ctx` — percentage of the context window used in the current conversation.
- `5h` / `7d` — percentage used of the 5-hour and weekly (7-day) rate-limit
  windows, followed by the local time (or day + time, if more than 24h away)
  the window resets.
- Each gauge is colored **green** (<60%), **yellow** (60–85%), or **red**
  (≥85%) based on usage.
- The 5h/7d segments only appear for Claude.ai subscription plans, once the
  first API response of a session has come back — they're omitted
  gracefully otherwise.
- The git line shows the current branch (or `detached`), a yellow `●` if
  there are uncommitted changes, and `↑N`/`↓M` if the branch is ahead/behind
  its upstream. It's omitted entirely outside a git repo. It's built from a
  single `git status --porcelain=v2 --branch` call (no separate
  rev-parse/branch/rev-list calls), since the script runs on every status
  line refresh.

## Two implementations

| File | Platform | Requirements |
|---|---|---|
| `statusline.py` + launcher | Linux, Mac, Windows | Python 3.8+ |
| `statusline-command.sh` | Linux, Mac | bash, jq, awk, GNU date |

The Python implementation is cross-platform and has no external dependencies
beyond the Python standard library. The bash implementation is retained for
environments where bash tooling is preferred.

## Python install (cross-platform)

### Requirements

Python 3.8 or later. No third-party packages — only the standard library.

Test your Python version:

```bash
python3 --version   # Linux / Mac
python --version    # Windows
```

### Linux / Mac

1. Copy the script and launcher into place:

   ```bash
   cp statusline.py ~/.claude/statusline.py
   cp statusline-launcher.sh ~/.claude/statusline-launcher.sh
   chmod +x ~/.claude/statusline-launcher.sh
   ```

2. Wire it up in `~/.claude/settings.json`. If that file doesn't exist yet,
   copy `settings.snippet.linux.json` to `~/.claude/settings.json`. Otherwise
   merge in the `statusLine` key:

   ```bash
   jq -s '.[0] * .[1]' ~/.claude/settings.json settings.snippet.linux.json \
     > /tmp/settings.json && mv /tmp/settings.json ~/.claude/settings.json
   ```

3. Restart Claude Code for the status line to take effect.

### Windows

1. Copy the script and launcher into place:

   ```powershell
   Copy-Item statusline.py "$env:USERPROFILE\.claude\statusline.py"
   Copy-Item statusline-launcher.cmd "$env:USERPROFILE\.claude\statusline-launcher.cmd"
   ```

2. Merge the `statusLine` key from `settings.snippet.windows.json` into
   `%USERPROFILE%\.claude\settings.json`. If the settings file doesn't exist
   yet, copy `settings.snippet.windows.json` directly.

3. Restart Claude Code for the status line to take effect.

If `python` is not found on your PATH but `py` (the Python Launcher for
Windows) is, change `python` to `py` in `statusline-launcher.cmd`.

### Testing without Claude Code

```bash
echo '{}' | python3 ~/.claude/statusline.py                   # minimal (just cwd)
echo '{"model":{"display_name":"Sonnet 4.6"}}' | python3 ~/.claude/statusline.py
```

If Python is missing or below 3.8, the launcher prints a `[statusline]` warning
in place of the normal output so you know exactly what to fix.

## Bash install (Linux / Mac only)

### Requirements

- `bash`, `jq`, `awk`, GNU `date` (the `date -d "@<epoch>"` syntax used for
  reset times is a GNU coreutils feature — it will not work with the BSD
  `date` shipped on macOS; install GNU coreutils, e.g. via `brew install
  coreutils` and use `gdate`, if you need this on macOS).

### Install

1. Copy the script into place:

   ```bash
   cp statusline-command.sh ~/.claude/statusline-command.sh
   chmod +x ~/.claude/statusline-command.sh
   ```

2. Wire it up in `~/.claude/settings.json`. If that file doesn't exist yet,
   just copy `settings.snippet.json` to `~/.claude/settings.json`. If it
   already exists, merge in the `statusLine` key from `settings.snippet.json`
   without overwriting your other settings, e.g.:

   ```bash
   jq -s '.[0] * .[1]' ~/.claude/settings.json settings.snippet.json > /tmp/settings.json \
     && mv /tmp/settings.json ~/.claude/settings.json
   ```

3. Restart Claude Code (or start a new session) for the status line to take
   effect.

Step 1 copies the file rather than symlinking it, so after editing
`statusline-command.sh` in this repo, re-run the `cp` command to deploy the
change to `~/.claude/statusline-command.sh` — otherwise Claude Code keeps
running the old version.

## Customizing

Both scripts are self-contained and meant to be edited directly:

- `bar_color()` controls the green/yellow/red thresholds (currently 60% /
  85%).
- `make_bar()` controls the gauge width (currently 10 blocks, one per 10%)
  and the block characters (`█` filled / `░` empty).
- The `CYAN` / `WHITE` / `GREY` constants near the top control the color
  palette — tuned for a dark terminal background.
