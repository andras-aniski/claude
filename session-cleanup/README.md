# Session cleanup

Delete the past Claude Code sessions that clutter the `/resume` picker.

Claude Code stores every session as a `.jsonl` transcript (plus a sidecar folder)
under `~/.claude/projects/<encoded-cwd>/`, but it offers **no built-in way to
remove a specific one** — only `/rename`, and time-based auto-cleanup via
`cleanupPeriodDays`. This tool lists sessions with readable metadata and moves the
ones you pick into a recoverable trash.

It ships in two forms sharing one script:

- **Standalone CLI** — `python ~/.claude/session_cleanup.py --interactive`
- **Slash command** — `/session-cleanup` inside Claude Code

Cross-platform (Windows / macOS / Linux), Python 3.8+, no dependencies.

## Install

```sh
python session-cleanup/install.py
```

This copies `session_cleanup.py` into `~/.claude/` and registers the
`/session-cleanup` command in `~/.claude/commands/`. Restart Claude Code to pick
up the command. It does not modify `settings.json`.

## Usage

### Interactive CLI

```sh
python ~/.claude/session_cleanup.py --interactive          # current workspace
python ~/.claude/session_cleanup.py --interactive --all    # every workspace
```

Shows a numbered table; type the rows to delete (e.g. `1,3-5`), confirm, done.

### Slash command

Run `/session-cleanup` (or `/session-cleanup --all`). Claude lists the sessions,
asks which to remove, and deletes them for you.

### Non-interactive

```sh
python ~/.claude/session_cleanup.py list [--all] [--json]
python ~/.claude/session_cleanup.py delete <id> [<id> ...] [--purge] [--force]
python ~/.claude/session_cleanup.py trash --list
python ~/.claude/session_cleanup.py trash --purge-older-than 30
```

## Behavior

- **Names.** Each session shows its `/rename` title if set, otherwise its
  auto-generated slug, otherwise the first user prompt.
- **Trash, not destruction.** `delete` moves the `.jsonl` and its sidecar folder
  into `~/.claude/.trash/<timestamp>/`. Restore by moving them back into the
  session's `projects/<workspace>/` folder. `--purge` deletes permanently, and
  `trash --purge-older-than N` empties old batches.
- **The active session is protected.** It's marked `*` and refused by `delete`
  (unless `--force`), identified via `$CLAUDE_CODE_SESSION_ID`.
- **Scope.** Defaults to the current working directory's sessions, like `/resume`;
  `--all` spans every workspace under `~/.claude/projects/`.
- Deleted sessions vanish from `/resume` immediately; restored ones reappear.

## Note on `cleanupPeriodDays`

For hands-off, time-based pruning, set `cleanupPeriodDays` in
`~/.claude/settings.json` (default 30) — Claude Code auto-deletes sessions older
than that. This tool complements it for selective, on-demand removal.
