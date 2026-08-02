#!/usr/bin/env python3
"""Install the Claude Code status line into ~/.claude (Linux/Mac) or %USERPROFILE%\\.claude (Windows)."""
import sys

if sys.version_info < (3, 8):
    print("[statusline] Python 3.8+ required, found " + sys.version.split()[0])
    sys.exit(1)

import json
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
    shutil.copy2(src, dst)
    print(f"  copied  {dst}")


def merge_settings(dst_dir: Path, command: str) -> None:
    settings_path = dst_dir / 'settings.json'
    # refreshInterval keeps the elapsed-time segment ticking while the session
    # is idle; without it the status line only re-runs on events.
    status_line = {"type": "command", "command": command, "refreshInterval": 10}

    if settings_path.exists():
        current = json.loads(settings_path.read_text(encoding='utf-8'))
        if 'statusLine' in current:
            answer = input("  settings.json already has 'statusLine' - overwrite? [y/N] ")
            if answer.strip().lower() != 'y':
                print("  skipped settings.json")
                return
        current['statusLine'] = status_line
        settings_path.write_text(json.dumps(current, indent=2), encoding='utf-8')
        print(f"  updated {settings_path}")
    else:
        settings_path.write_text(json.dumps({"statusLine": status_line}, indent=2), encoding='utf-8')
        print(f"  created {settings_path}")


def main() -> None:
    target = claude_dir()
    target.mkdir(parents=True, exist_ok=True)
    print(f"Installing into {target}\n")

    copy_file(HERE / 'statusline.py', target / 'statusline.py')

    # Both branches go through the launcher rather than invoking the
    # interpreter directly: the launcher is what turns a missing or too-old
    # Python into a readable "[statusline] ..." message instead of the shell's
    # own "'python' is not recognized" / "command not found" landing in the
    # status line. The path is absolute so Claude Code needn't expand ~ or
    # %USERPROFILE%.
    if platform.system() == 'Windows':
        launcher = HERE / 'statusline-launcher.cmd'
        dst_launcher = target / launcher.name
        copy_file(launcher, dst_launcher)
        merge_settings(target, f'cmd /c "{dst_launcher}"')
    else:
        launcher = HERE / 'statusline-launcher.sh'
        dst_launcher = target / launcher.name
        copy_file(launcher, dst_launcher)
        dst_launcher.chmod(dst_launcher.stat().st_mode | 0o111)
        print(f"  chmod+x {dst_launcher}")
        merge_settings(target, f'bash "{dst_launcher}"')

    print("\nDone. Restart Claude Code for the status line to take effect.")


if __name__ == '__main__':
    main()
