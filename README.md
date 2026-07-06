# claude

Personal Claude Code setup: global configuration, status line, skills, and
tools, version-controlled so they can be applied consistently across
machines.

## Contents

- [`statusline/`](statusline/README.md) — custom status line showing
  current directory, model, context-window usage, 5-hour/weekly
  rate-limit usage as colored gauges, and (when run inside a git repo)
  branch/dirty/ahead-behind info. See its README for install instructions.
- [`session-cleanup/`](session-cleanup/README.md) — list and delete the past
  sessions shown by `/resume`, via a standalone CLI or a `/session-cleanup`
  slash command. Deletions move to a recoverable trash; the active session is
  protected. See its README for install instructions.
