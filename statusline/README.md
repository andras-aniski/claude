# Claude Code status line

A custom status line for Claude Code that shows the current directory, model,
context-window usage, and 5-hour/weekly rate-limit usage as colored gauges.

Example output:

```
MemButler | Sonnet 4.6 | ctx ████░░░░░░ 43% | 5h ███████░░░ 72% 02:10 | 7d █████████░ 91% Fri 08:00
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

## Requirements

- `bash`, `jq`, `awk`, GNU `date` (the `date -d "@<epoch>"` syntax used for
  reset times is a GNU coreutils feature — it will not work with the BSD
  `date` shipped on macOS; install GNU coreutils, e.g. via `brew install
  coreutils` and use `gdate`, if you need this on macOS).

## Install

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

## Customizing

The script is self-contained and meant to be edited directly:

- `bar_color()` controls the green/yellow/red thresholds (currently 60% /
  85%).
- `make_bar()` controls the gauge width (currently 10 blocks, one per 10%)
  and the block characters (`█` filled / `░` empty).
- The `CYAN` / `WHITE` / `GREY` variables near the top control the color
  palette — tuned for a dark terminal background.
