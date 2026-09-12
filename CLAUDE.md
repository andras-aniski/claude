# CLAUDE.md

Personal Claude Code setup: a custom status line and a session-cleanup tool,
kept in git so they install identically on every machine. The READMEs are the
documentation; this file only lists what a fresh session is likely to get
wrong.

- [`README.md`](README.md) — repo overview
- [`statusline/README.md`](statusline/README.md) — what the status line shows and why, install, customizing
- [`session-cleanup/README.md`](session-cleanup/README.md) — usage, trash semantics, install

## Rules

1. **`statusline/statusline.py` and `statusline/statusline-command.sh` are
   deliberate duplicates.** Every change to one must be mirrored in the other,
   then verified with `bash statusline/parity-test.sh` (must print `PASS`).
   They have drifted before; do not touch one without the other.
2. **`~/.claude` holds copies, not symlinks.** Editing a script here changes
   nothing until it is redeployed: `python statusline/install.py` or
   `python session-cleanup/install.py`.
3. **Stdlib only, Python 3.8+.** No third-party packages in either tool. The
   bash status line may use only `bash`, `jq`, `awk`, and must work with both
   GNU and BSD `date`.
4. **Commits** use a conventional-commit prefix with scope and an imperative
   subject: `fix(statusline): ...`, `docs(session-cleanup): ...`.
5. **Never commit `__pycache__/`** or `.DS_Store` (both gitignored).
6. **When behavior changes, update the matching README** so it keeps
   describing what the code actually does.
