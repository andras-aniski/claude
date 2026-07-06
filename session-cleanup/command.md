---
description: List past Claude Code sessions and delete the ones you no longer need (moves them to a recoverable trash).
argument-hint: "[--all]"
allowed-tools: Bash, AskUserQuestion
---

Help the user clean up the sessions that appear in `/resume`. Claude Code has no
built-in way to remove a session, so use the `session_cleanup.py` helper.

Steps:

1. List sessions as JSON. Default to the current workspace; if the user asked for
   every workspace (or passed `--all` in `$ARGUMENTS`), add `--all`:

   ```bash
   python ~/.claude/session_cleanup.py list --json $ARGUMENTS
   ```

   (On Windows via PowerShell, use `python "$env:USERPROFILE\.claude\session_cleanup.py" list --json`.)

2. Present the sessions as a compact numbered table: **name**, first-prompt
   **title**, **date**, **git branch** if present, and **message count**. Clearly
   mark the entry whose `is_current` is `true` as the CURRENT session.

3. Ask which to delete — accept numbers/ranges (e.g. `1,3-5`) or phrases like
   "all except the current one". Never include the current session unless the user
   is explicit. Use AskUserQuestion if a quick confirmation helps.

4. After confirmation, delete the chosen sessions by id. They are moved to
   `~/.claude/.trash/` (recoverable), and the active session is refused
   automatically:

   ```bash
   python ~/.claude/session_cleanup.py delete <id1> <id2> ...
   ```

5. Report what was moved to trash and remind the user they can restore an entry by
   moving it back into its `projects/<workspace>/` folder, or run
   `python ~/.claude/session_cleanup.py trash --list` to review the trash.

Notes:
- The deleted sessions disappear from `/resume` immediately; a restored one
  reappears.
- For time-based auto-cleanup instead, `cleanupPeriodDays` in `settings.json`
  purges sessions older than N days (default 30). This tool is for selective,
  on-demand removal.
