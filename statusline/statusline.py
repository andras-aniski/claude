import sys

if sys.version_info < (3, 8):
    print(f"\u26a0 Python 3.8+ required, found {sys.version.split()[0]}")
    sys.exit(0)

import json
import os
import subprocess
from datetime import datetime

# Re-encode stdout to UTF-8 so block/arrow chars render correctly on Windows.
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Colors tuned for a dark terminal background.
CYAN  = '\033[1;36m'
WHITE = '\033[0;37m'
GREY  = '\033[0;90m'
RESET = '\033[0m'


def bar_color(pct: float) -> str:
    if pct >= 85:
        return '1;31'
    if pct >= 60:
        return '1;33'
    return '1;32'


def make_bar(pct: float) -> str:
    width = 10
    filled = min(width, max(0, int(pct * width / 100 + 0.5)))
    return '█' * filled + '░' * (width - filled)


def round_pct(pct: float) -> int:
    return int(pct + 0.5)


def format_reset(ts: int) -> str:
    reset = datetime.fromtimestamp(ts)
    diff = reset - datetime.now()
    if diff.total_seconds() < 86400:
        return reset.strftime('%H:%M')
    return reset.strftime('%a %H:%M')


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        data = {}

    cwd = (data.get('workspace') or {}).get('current_dir') or os.getcwd()
    directory = os.path.basename(cwd) or cwd

    model    = (data.get('model') or {}).get('display_name')
    ctx_used = (data.get('context_window') or {}).get('used_percentage')

    five_h      = (data.get('rate_limits') or {}).get('five_hour') or {}
    seven_d     = (data.get('rate_limits') or {}).get('seven_day') or {}
    five_pct    = five_h.get('used_percentage')
    seven_pct   = seven_d.get('used_percentage')
    five_reset  = five_h.get('resets_at')
    seven_reset = seven_d.get('resets_at')

    out = f'{WHITE}{directory}{RESET}'

    if model:
        out += f' {CYAN}|{RESET} {GREY}{model}{RESET}'

    if ctx_used is not None:
        bar = make_bar(ctx_used)
        c   = bar_color(ctx_used)
        out += f' {CYAN}|{RESET} {WHITE}ctx \033[{c}m{bar} {RESET}\033[{c}m{round_pct(ctx_used)}%{RESET}'

    if five_pct is not None:
        bar = make_bar(five_pct)
        c   = bar_color(five_pct)
        out += f' {CYAN}|{RESET} {WHITE}5h \033[{c}m{bar} {RESET}\033[{c}m{round_pct(five_pct)}%{RESET}'
        if five_reset is not None:
            out += f' {GREY}{format_reset(five_reset)}{RESET}'

    if seven_pct is not None:
        bar = make_bar(seven_pct)
        c   = bar_color(seven_pct)
        out += f' {CYAN}|{RESET} {WHITE}7d \033[{c}m{bar} {RESET}\033[{c}m{round_pct(seven_pct)}%{RESET}'
        if seven_reset is not None:
            out += f' {GREY}{format_reset(seven_reset)}{RESET}'

    print(out)

    # Single git invocation gathers branch, ahead/behind, and dirty state at once.
    try:
        result = subprocess.run(
            ['git', '-C', cwd, 'status', '--porcelain=v2', '--branch'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
        git_out = result.stdout
    except FileNotFoundError:
        git_out = ''

    if not git_out:
        return

    branch = ''
    ab     = ''
    dirty  = False
    for line in git_out.splitlines():
        if line.startswith('# branch.head '):
            branch = line[len('# branch.head '):]
        elif line.startswith('# branch.ab '):
            ab = line[len('# branch.ab '):]
        elif not line.startswith('#') and line:
            dirty = True

    if branch == '(detached)':
        branch = 'detached'

    if not branch:
        return

    git_line = f'{WHITE}{branch}{RESET}'
    if dirty:
        git_line += f' \033[1;33m\u25cf{RESET}'

    if ab:
        tokens = ab.split()
        if len(tokens) == 2:
            try:
                ahead  = int(tokens[0].lstrip('+'))
                behind = int(tokens[1].lstrip('-'))
                if ahead  > 0:
                    git_line += f' {GREY}\u2191{ahead}{RESET}'
                if behind > 0:
                    git_line += f' {GREY}\u2193{behind}{RESET}'
            except ValueError:
                pass

    print(git_line)


if __name__ == '__main__':
    main()
