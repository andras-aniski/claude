#!/usr/bin/env python3
"""List and delete Claude Code sessions (the entries shown by /resume).

Sessions are stored as ~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl, each
with an optional sidecar directory of the same name. Claude Code has no built-in
way to remove a specific session, so this tool lists them with readable metadata
and moves the ones you pick into a recoverable trash (~/.claude/.trash/).

Zero dependencies, Python 3.8+, cross-platform (Windows / macOS / Linux).

Usage:
    session_cleanup.py list [--all] [--json]
    session_cleanup.py delete <id> [<id> ...] [--purge] [--force]
    session_cleanup.py trash [--list] [--purge-older-than N]
    session_cleanup.py --interactive [--all]
"""
import sys

if sys.version_info < (3, 8):
    print(f"Python 3.8+ required, found {sys.version.split()[0]}")
    sys.exit(1)

import argparse
import json
import os
import platform
import re
import shutil
from datetime import datetime
from pathlib import Path

# The .jsonl line format is internal to Claude Code and changes between versions,
# so every field below is treated as optional and parsing is defensive.
TITLE_MAX = 60


def claude_dir() -> Path:
    """Location of the Claude config dir (matches statusline/install.py)."""
    if platform.system() == 'Windows':
        return Path(os.environ.get('USERPROFILE', Path.home())) / '.claude'
    return Path.home() / '.claude'


def projects_dir() -> Path:
    return claude_dir() / 'projects'


def encode_cwd(path: Path) -> str:
    """Encode an absolute path the way Claude Code names its project folders:
    every non-alphanumeric character becomes a dash."""
    return re.sub(r'[^a-zA-Z0-9]', '-', str(path))


def current_project_dir() -> Path:
    """The projects/<encoded-cwd> folder for the current working directory.

    Matched case-insensitively because the drive-letter case can differ between
    the encoded cwd and the folder Claude Code actually created."""
    base = projects_dir()
    encoded = encode_cwd(Path.cwd())
    if base.is_dir():
        for child in base.iterdir():
            if child.is_dir() and child.name.lower() == encoded.lower():
                return child
    return base / encoded


def current_session_id() -> str:
    """Id of the running session, if the harness exposed it.

    Claude Code sets CLAUDE_CODE_SESSION_ID for the live session; this is the
    only reliable signal, so the active session is never deleted by mistake."""
    return (os.environ.get('CLAUDE_CODE_SESSION_ID')
            or os.environ.get('CLAUDE_SESSION_ID')
            or '')


def _first_user_title(obj) -> str:
    """Extract readable text from a user message object, or '' if not usable."""
    if obj.get('type') != 'user' or obj.get('isMeta'):
        return ''
    content = (obj.get('message') or {}).get('content')
    text = ''
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'text':
                text = block.get('text', '')
                if text:
                    break
    text = (text or '').strip()
    # Skip slash-command / local-command envelopes; they aren't real prompts.
    if not text or text.startswith('<command-') or text.startswith('<local-command'):
        return ''
    return ' '.join(text.split())


def read_session(path: Path) -> dict:
    """Parse one <sessionId>.jsonl into a metadata record (defensively)."""
    session_id = path.stem
    custom_title = slug = title = git_branch = ''
    messages = 0
    for line in _iter_lines(path):
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        t = obj.get('type')
        if t == 'custom-title' and obj.get('customTitle'):
            custom_title = obj['customTitle']          # set via /rename
        if not slug and obj.get('slug'):
            slug = obj['slug']                          # auto-generated name
        if obj.get('gitBranch'):
            git_branch = obj['gitBranch']
        if t in ('user', 'assistant'):
            messages += 1
        if not title:
            title = _first_user_title(obj)
    try:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime)
        size = stat.st_size
    except OSError:
        modified, size = datetime.fromtimestamp(0), 0
    name = custom_title or slug or title or session_id[:8]
    return {
        'id': session_id,
        'project': path.parent.name,
        'name': name,
        'title': title,
        'modified': modified,
        'messages': messages,
        'size': size,
    }


def _iter_lines(path: Path):
    try:
        with path.open(encoding='utf-8', errors='replace') as fh:
            for line in fh:
                yield line
    except OSError:
        return


def collect_sessions(all_workspaces: bool) -> list:
    """All session records, newest first, with is_current marked."""
    if all_workspaces:
        base = projects_dir()
        dirs = [d for d in base.iterdir() if d.is_dir()] if base.is_dir() else []
    else:
        d = current_project_dir()
        dirs = [d] if d.is_dir() else []

    records = []
    for d in dirs:
        for jsonl in d.glob('*.jsonl'):
            records.append(read_session(jsonl))

    records.sort(key=lambda r: r['modified'], reverse=True)

    active = current_session_id()
    for r in records:
        r['is_current'] = bool(active) and r['id'] == active
    return records


# --------------------------------------------------------------------------- #
# Delete / trash                                                              #
# --------------------------------------------------------------------------- #

def trash_dir() -> Path:
    return claude_dir() / '.trash'


def find_session_files(session_id: str) -> list:
    """The .jsonl and any sidecar dir for a session, across all workspaces."""
    base = projects_dir()
    found = []
    if base.is_dir():
        for d in base.iterdir():
            if not d.is_dir():
                continue
            jsonl = d / f'{session_id}.jsonl'
            sidecar = d / session_id
            if jsonl.exists():
                found.append(jsonl)
            if sidecar.is_dir():
                found.append(sidecar)
    return found


def delete_sessions(ids: list, purge: bool, force: bool, current: str = '') -> int:
    # Only ever protect a session we can positively identify as active (from the
    # harness env or an explicit --current). Never guess, so we can't trash the
    # wrong file.
    active = current or current_session_id()

    dest = None
    if not purge:
        dest = trash_dir() / datetime.now().strftime('%Y%m%d-%H%M%S')

    handled = 0
    for sid in ids:
        is_current = bool(active) and sid == active
        if is_current and not force:
            print(f"  skipped {sid[:8]}  (looks like the active session; use --force)")
            continue
        files = find_session_files(sid)
        if not files:
            print(f"  not found: {sid}")
            continue
        for f in files:
            if purge:
                _remove(f)
                print(f"  deleted  {f.name}")
            else:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(dest / f.name))
                print(f"  trashed  {f.name}")
        handled += 1

    if handled and not purge:
        print(f"\nMoved to {dest}")
        print("Restore any item by moving it back into its projects/<workspace>/ folder.")
    return handled


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #

def _size(n: int) -> str:
    units = ['B', 'KB', 'MB', 'GB']
    v = float(n)
    for u in units:
        if v < 1024 or u == 'GB':
            return f"{v:.0f}{u}" if u == 'B' else f"{v:.1f}{u}"
        v /= 1024
    return f"{n}B"


def print_table(records: list, show_project: bool) -> None:
    if not records:
        print("No sessions found.")
        return
    width = len(str(len(records)))
    for i, r in enumerate(records, 1):
        marker = '* ' if r.get('is_current') else '  '
        when = r['modified'].strftime('%Y-%m-%d %H:%M')
        head = f"{i:>{width}}. {marker}{r['name']}"
        meta = f"{when}  {r['messages']} msgs  {_size(r['size'])}"
        if show_project:
            meta += f"  [{r['project']}]"
        print(head)
        line = f"     {meta}"
        if r['title'] and r['title'] != r['name']:
            t = r['title']
            line += f"\n       \"{t[:TITLE_MAX]}{'...' if len(t) > TITLE_MAX else ''}\""
        print(line)
    if any(r.get('is_current') for r in records):
        print("\n* = current session")


def records_to_json(records: list) -> str:
    out = []
    for r in records:
        d = dict(r)
        d['modified'] = r['modified'].isoformat()
        out.append(d)
    return json.dumps(out, indent=2)


# --------------------------------------------------------------------------- #
# Interactive picker                                                          #
# --------------------------------------------------------------------------- #

def parse_selection(text: str, count: int) -> list:
    """Parse '1,3-5' into a sorted list of 0-based indices within range."""
    picked = set()
    for part in text.replace(' ', '').split(','):
        if not part:
            continue
        if '-' in part:
            a, _, b = part.partition('-')
            if a.isdigit() and b.isdigit():
                for n in range(int(a), int(b) + 1):
                    if 1 <= n <= count:
                        picked.add(n - 1)
        elif part.isdigit():
            n = int(part)
            if 1 <= n <= count:
                picked.add(n - 1)
    return sorted(picked)


def interactive(all_workspaces: bool, purge: bool) -> int:
    records = collect_sessions(all_workspaces)
    print_table(records, show_project=all_workspaces)
    if not records:
        return 0
    try:
        raw = input("\nEnter numbers to delete (e.g. 1,3-5), or 'q' to quit: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if raw.lower() in ('q', 'quit', 'exit', ''):
        print("Nothing deleted.")
        return 0
    idx = parse_selection(raw, len(records))
    if not idx:
        print("No valid selection; nothing deleted.")
        return 0
    chosen = [records[i] for i in idx]
    print("\nWill delete:")
    for r in chosen:
        flag = '  (CURRENT SESSION)' if r.get('is_current') else ''
        print(f"  - {r['name']}{flag}")
    try:
        ans = input(f"\n{'Permanently delete' if purge else 'Move to trash'} these {len(chosen)}? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return 0
    if ans.strip().lower() != 'y':
        print("Cancelled.")
        return 0
    return delete_sessions([r['id'] for r in chosen], purge=purge, force=False)


# --------------------------------------------------------------------------- #
# Trash management                                                            #
# --------------------------------------------------------------------------- #

def manage_trash(list_only: bool, purge_older_than) -> None:
    root = trash_dir()
    if not root.is_dir():
        print("Trash is empty.")
        return
    batches = sorted([d for d in root.iterdir() if d.is_dir()])
    if purge_older_than is not None:
        cutoff = datetime.now().timestamp() - purge_older_than * 86400
        removed = 0
        for b in batches:
            if b.stat().st_mtime < cutoff:
                shutil.rmtree(b, ignore_errors=True)
                removed += 1
                print(f"  purged {b.name}")
        print(f"Purged {removed} trash batch(es) older than {purge_older_than} day(s).")
        return
    if not batches:
        print("Trash is empty.")
        return
    for b in batches:
        items = list(b.iterdir())
        print(f"{b.name}  ({len(items)} item(s))")
        for it in items:
            print(f"    {it.name}")


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="List and delete Claude Code sessions.")
    p.add_argument('--interactive', '-i', action='store_true',
                   help="Interactive picker (default action if no subcommand).")
    p.add_argument('--all', action='store_true',
                   help="Operate across all workspaces, not just the current one.")
    p.add_argument('--purge', action='store_true',
                   help="Delete permanently instead of moving to trash.")
    sub = p.add_subparsers(dest='command')

    lp = sub.add_parser('list', help="List sessions.")
    lp.add_argument('--all', action='store_true')
    lp.add_argument('--json', action='store_true')

    dp = sub.add_parser('delete', help="Delete sessions by id.")
    dp.add_argument('ids', nargs='+')
    dp.add_argument('--purge', action='store_true')
    dp.add_argument('--force', action='store_true',
                    help="Allow deleting the active session.")
    dp.add_argument('--current', default='', metavar='ID',
                    help="Session id to treat as active/protected (defaults to "
                         "$CLAUDE_CODE_SESSION_ID).")

    tp = sub.add_parser('trash', help="Inspect or purge the trash.")
    tp.add_argument('--list', action='store_true')
    tp.add_argument('--purge-older-than', type=int, metavar='DAYS')
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == 'list':
        records = collect_sessions(all_workspaces=args.all)
        if args.json:
            print(records_to_json(records))
        else:
            print_table(records, show_project=args.all)
        return

    if args.command == 'delete':
        n = delete_sessions(args.ids, purge=args.purge, force=args.force,
                            current=args.current)
        if n == 0:
            sys.exit(1)
        return

    if args.command == 'trash':
        manage_trash(args.list, args.purge_older_than)
        return

    # No subcommand: interactive picker (also the -i path).
    interactive(all_workspaces=args.all, purge=args.purge)


if __name__ == '__main__':
    main()
