# Claude Code status line

A custom status line for Claude Code, in two lines. Line 1 is *where the work
is happening*: directory, session duration, git branch and dirty state, and
the lines the session has changed. Line 2 is *what the session is spending*:
model + reasoning effort, output style, and the 5-hour / weekly rate-limit
gauges, with the context window gauge pinned to the right edge.

Example output, in a 100-column terminal:

```
MemButler 27m  |  main ● ↑2 ↓1 +312 -47
Sonnet 4.6 (high)  |  5h    72%     02:10  7d    91%     Fri 08:00                ctx    43%
```

The gap before `ctx` is the only part of that which isn't fixed: it's whatever
padding right-aligns the context gauge, so it grows and shrinks with the
terminal width while everything to its left stays put.

Each gauge is a 10-cell field with its percentage centred inside it. The
filled portion is drawn as a colored *background* running under the number,
rather than as a separate bar of block glyphs beside it — so the whole gauge
costs 10 cells instead of 14. In the snippet above the fill can't be shown,
but on screen the left `72%` of that field carries a yellow background and the
rest a dark track.

Line 1:

- `27m` — wall-clock time since the session started, riding directly on the
  directory name rather than taking its own separator. Omitted before the
  first API response.
- The git segment shows the current branch (or `detached`), a yellow `●` if
  there are uncommitted changes, and `↑N`/`↓M` if the branch is ahead/behind
  its upstream. It's built from a single `git status --porcelain=v2 --branch`
  call (no separate rev-parse/branch/rev-list calls), since the script runs on
  every status line refresh.
- `+312 -47` — lines added and removed across the session. It sits with the
  branch because both describe the working tree, stands alone outside a repo,
  and is absent before the first edit.

Line 2, left group:

- The reasoning effort in parentheses after the model reflects the live value,
  including mid-session `/effort` changes, and is colored by level: **grey**
  (low), **green** (medium), **yellow** (high), **red** (xhigh), **magenta**
  (max). Ultracode reports as `xhigh`. Absent for models that don't take a
  reasoning effort parameter — but not conditional on the model name, which is
  shown or omitted independently.
- The output style is shown only when it isn't `default`.
- `5h` / `7d` — percentage used of the 5-hour and weekly (7-day) rate-limit
  windows, followed by the local time (or day + time, if more than 24h away)
  the window resets. These stay on the left so their reset times sit at a
  fixed offset instead of sliding with the terminal width, and are divided
  from each other by whitespace rather than a pipe, since they read as one
  cluster.
- The 5h/7d segments only appear for Claude.ai subscription plans, once the
  first API response of a session has come back — they're omitted
  gracefully otherwise.

Line 2, right group:

- `ctx` — percentage of the context window used in the current conversation.
  It's the fastest-changing number on the line, so it gets its own fixed spot
  at the right edge.

Every gauge's fill is colored **green** (<60%), **yellow** (60–85%), or **red**
(≥85%) based on usage, with the digits drawn in black on top so they stay
legible against it.

`cost.total_cost_usd` is available in the payload but deliberately not shown:
it's an estimate of what the tokens would have cost at API rates, which isn't
money spent on a subscription plan. The 5h/7d gauges are the real constraint.

Line 2's right group is aligned using the `COLUMNS` environment variable, which
Claude Code sets before running the script (`tput cols` can't help, because
stdout is captured rather than connected to the terminal).

`COLUMNS` is the full terminal width, but Claude Code renders the status line
indented by its own built-in spacing, so a line filling all of `COLUMNS`
overflows the row and comes back truncated with an ellipsis. Measured
empirically, the usable width is `COLUMNS - 3`. The `RIGHT_MARGIN` constant
near the top of each script (default `4`, one cell of headroom on top of that)
keeps the content clear of the edge — raise it if a trailing `…` ever
reappears, drop it to `3` to sit flush against the last usable column.

As the terminal narrows, line 2 degrades in one step before it gives up:

1. The rate-limit reset times are dropped (they're the least critical thing on
   the line and buy back ~20 cells), keeping the context gauge aligned.
2. Below that there's no width management left: the groups are concatenated
   with a `|` between them and whatever that comes to is printed, so the result
   is subject to the same truncation as any other over-long line.

Line 1 is never width-managed at all — it's built in one pass with no cell
accounting, since nothing on it is aligned.

Spacing carries the grouping and widens with conceptual distance: 1 cell
inside a gauge, 2 between the related 5h/7d gauges, and 5 across concepts (the
padded `|`). A pipe padded narrower than the gap would read as the tighter
break, which is backwards.

Line 2 is dropped entirely rather than printed blank when there's nothing to
put on it — before the first API response of a session, for instance.

`install.py` and the settings snippets set `"refreshInterval": 10`, which
re-runs the script every 10 seconds in addition to the event-driven updates.
Without it the elapsed-time segment freezes whenever the session sits idle.
Drop the key if you'd rather the script only run on events.

## Two implementations

| File | Platform | Requirements |
|---|---|---|
| `statusline.py` + launcher | Linux, Mac, Windows | Python 3.8+ |
| `statusline-command.sh` | Linux, Mac | bash, jq, awk |

The Python implementation is the one to use: it's cross-platform and needs
nothing beyond the standard library. The bash implementation exists for hosts
without a usable Python — it is strictly the heavier of the two, since it needs
`jq` and `awk` on top of a shell.

It is also a near-verbatim second copy of the same ~350 lines: every constant
(`RIGHT_MARGIN`, `BAR_WIDTH`, the 60/85 thresholds, the effort colors) and every
algorithm (`gauge`, `center`, the fit loop, porcelain-v2 parsing, duration
formatting) exists twice. **Any change to one has to be mirrored in the other
and the two re-checked for identical output** — they have drifted before.

`parity-test.sh` does that re-checking. It feeds both implementations the same
18 payloads at four terminal widths and asserts their stdout is byte-identical
and neither writes to stderr:

```bash
bash statusline/parity-test.sh   # -> PASS -- 72 cases, ...
```

The payload matrix is mostly regressions: reset timestamps in milliseconds or
as ISO strings, `0` percentages, float line counts, reasoning effort without a
model name. Run it after touching either script. It's a development aid —
`install.py` doesn't deploy it.

## Python install (cross-platform)

### Requirements

Python 3.8 or later. No third-party packages — only the standard library.

Test your Python version:

```bash
python3 --version   # Linux / Mac
python --version    # Windows
```

### Install

```sh
python statusline/install.py
```

This copies `statusline.py` and the platform's launcher into `~/.claude`
(`%USERPROFILE%\.claude` on Windows), marks the launcher executable, and merges
a `statusLine` key into `settings.json` pointing at it — prompting first if one
is already there. Restart Claude Code for it to take effect.

### Installing by hand

The installer is the recommended path; it's the only one that sets
`refreshInterval`, which the elapsed-time segment needs (see above). If you'd
rather do it manually:

**Linux / Mac**

```bash
cp statusline.py statusline-launcher.sh ~/.claude/
chmod +x ~/.claude/statusline-launcher.sh
jq -s '.[0] * .[1]' ~/.claude/settings.json settings.snippet.linux.json \
  > /tmp/settings.json && mv /tmp/settings.json ~/.claude/settings.json
```

**Windows**

```powershell
Copy-Item statusline.py,statusline-launcher.cmd "$env:USERPROFILE\.claude\"
```

Then merge the `statusLine` key from `settings.snippet.windows.json` into
`%USERPROFILE%\.claude\settings.json`.

In both cases, if `settings.json` doesn't exist yet, copy the snippet to it
directly instead of merging. The launcher resolves `statusline.py` relative to
itself, so the two just have to stay in the same directory.

If `python` is not found on your PATH but `py` (the Python Launcher for
Windows) is, change `python` to `py` in `statusline-launcher.cmd`.

### Testing without Claude Code

```bash
echo '{}' | python3 ~/.claude/statusline.py                   # minimal (just cwd)
echo '{"model":{"display_name":"Sonnet 4.6"},"effort":{"level":"high"}}' \
  | python3 ~/.claude/statusline.py

# Right-alignment: set COLUMNS explicitly, since the shell won't export it to
# a non-interactive script the way Claude Code does.
echo '{"model":{"display_name":"Sonnet 4.6"},"context_window":{"used_percentage":43}}' \
  | COLUMNS=160 python3 ~/.claude/statusline.py
```

If Python is missing or below 3.8, the launcher prints a `[statusline]` warning
in place of the normal output so you know exactly what to fix.

## Bash install (Linux / Mac only)

### Requirements

- `bash`, `jq`, `awk`.

Formatting an epoch is the one place the two `date` implementations disagree —
GNU spells it `date -d "@<epoch>"`, the BSD `date` shipped on macOS rejects
`-d` outright and spells it `date -r <epoch>`. The script probes for this once
at startup (`epoch_fmt`), so reset times render on both.

### Install

`install.py` only installs the Python implementation, so this one is by hand:

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

- `bar_bg()` controls the green/yellow/red thresholds (currently 60% / 85%)
  and returns the ANSI *background* code for the filled part of a gauge.
- `effort_color()` (`EFFORT_COLORS` in the Python version) maps each reasoning
  effort level to a color. It's a discrete lookup rather than a threshold
  function like `bar_bg()`, since effort is an enum, not a scale.
- `BAR_WIDTH` sets how many cells a gauge occupies (currently 10, so one cell
  per 10%). The percentage is centred in that field by `gauge()`, which also
  decides the black-on-fill and white-on-track color pairs.
- The `CYAN` / `WHITE` / `GREY` / `GREEN` / `RED` constants near the top
  control the color palette — tuned for a dark terminal background.
- `RIGHT_MARGIN` controls how many cells are left free at the right edge.
- Which segments land in which group is decided by whether they're appended
  to the left or the right accumulator. Both scripts track a segment's visible
  width alongside its styled text, because right-alignment needs a cell count
  and ANSI escapes would otherwise have to be stripped back out. If you add a
  segment to line 1, keep it single-width — an emoji occupies two cells and
  will throw the alignment off.
