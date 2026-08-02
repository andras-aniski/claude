# claude

Personal Claude Code setup: global configuration, status line, skills, and
tools, version-controlled so they can be applied consistently across
machines.

## Contents

- [`statusline/`](statusline/README.md) — custom status line in two lines:
  directory, session duration, branch/dirty/ahead-behind and lines changed on
  the first, then model and reasoning effort, output style, 5-hour/weekly
  rate-limit gauges and a right-aligned context-window gauge on the second.
  See its README for install instructions.
- [`session-cleanup/`](session-cleanup/README.md) — list and delete the past
  sessions shown by `/resume`, via a standalone CLI or a `/session-cleanup`
  slash command. Deletions move to a recoverable trash; the active session is
  protected. See its README for install instructions.
