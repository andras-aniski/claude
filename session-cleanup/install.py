#!/usr/bin/env python3
"""Install the session-cleanup tool into ~/.claude (Linux/Mac) or
%USERPROFILE%\\.claude (Windows).

Copies the core script and registers the /session-cleanup slash command. It does
not touch settings.json.
"""
import sys

if sys.version_info < (3, 8):
    print(f"Python 3.8+ required, found {sys.version.split()[0]}")
    sys.exit(1)

import os
import platform
import shutil
from pathlib import Path

HERE = Path(__file__).parent


def claude_dir() -> Path:
    if platform.system() == 'Windows':
        return Path(os.environ.get('USERPROFILE', Path.home())) / '.claude'
    return Path.home() / '.claude'


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  copied  {dst}")


def main() -> None:
    target = claude_dir()
    target.mkdir(parents=True, exist_ok=True)
    print(f"Installing into {target}\n")

    script = target / 'session_cleanup.py'
    copy_file(HERE / 'session_cleanup.py', script)

    command = target / 'commands' / 'session-cleanup.md'
    copy_file(HERE / 'command.md', command)

    if platform.system() != 'Windows':
        script.chmod(script.stat().st_mode | 0o111)
        print(f"  chmod+x {script}")

    print("\nDone.")
    print(f"  Slash command: /session-cleanup   (restart Claude Code to pick it up)")
    print(f"  Standalone:    python \"{script}\" --interactive")


if __name__ == '__main__':
    main()
