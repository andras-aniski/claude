import sys

if sys.version_info < (3, 8):
    print(f"⚠ Python 3.8+ required, found {sys.version.split()[0]}")
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
GREEN = '\033[1;32m'
RED   = '\033[1;31m'
RESET = '\033[0m'

# Spacing carries the grouping, so it widens with conceptual distance: 1 cell
# inside a gauge, 2 between related gauges (Line.gap), 5 across concepts. A
# pipe padded narrower than the gap would read as the tighter break, which is
# backwards.
PIPE       = f'  {CYAN}|{RESET}  '
PIPE_PLAIN = '  |  '

# Reasoning effort is a discrete enum rather than a scale, so it gets an
# explicit map instead of going through bar_bg()'s thresholds. Ultracode
# reports as 'xhigh'; anything unrecognised falls back to grey.
EFFORT_COLORS = {
    'low':    '0;90',
    'medium': '1;32',
    'high':   '1;33',
    'xhigh':  '1;31',
    'max':    '1;35',
}

# Cells left free at the right edge. Claude Code renders the status line
# indented by its own built-in spacing, so content filling all of COLUMNS
# overflows the row and comes back truncated with an ellipsis. Measured
# empirically: the usable width is COLUMNS - 3, and this carries one cell of
# headroom on top. Raise it if a trailing "…" ever reappears; drop it to 3 to
# sit flush against the last usable column.
RIGHT_MARGIN = 4

# Cells each gauge occupies. The percentage is centred inside this field and
# the fill is drawn as a background under it, so this is the whole gauge width
# (minus its label), not just a bar sitting next to a number.
BAR_WIDTH = 10


def bar_bg(pct: float) -> str:
    """ANSI background code for the filled part of a gauge."""
    if pct >= 85:
        return '41'   # red
    if pct >= 60:
        return '43'   # yellow
    return '42'       # green


def round_pct(pct: float) -> int:
    return int(pct + 0.5)


def format_reset(ts: int) -> str:
    reset = datetime.fromtimestamp(ts)
    diff = reset - datetime.now()
    if diff.total_seconds() < 86400:
        return reset.strftime('%H:%M')
    return reset.strftime('%a %H:%M')


def format_duration(ms: float) -> str:
    total = int(ms // 1000)
    if total < 60:
        return f'{total}s'
    minutes, _ = divmod(total, 60)
    if minutes < 60:
        return f'{minutes}m'
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes}m'


class Line:
    """Accumulates styled text alongside its visible width.

    Right-alignment needs to know how many cells a segment occupies, and
    tracking that as the line is built is cheaper and less brittle than
    stripping ANSI escapes back out afterwards. Every character on line 2 is
    single-width, so len() is a correct cell count -- do not introduce emoji
    here.
    """

    def __init__(self) -> None:
        self.styled = ''
        self.width  = 0

    def add(self, styled: str, plain: str) -> None:
        self.styled += styled
        self.width  += len(plain)

    def sep(self) -> None:
        if self.width:
            self.add(PIPE, PIPE_PLAIN)

    def gap(self) -> None:
        """Whitespace instead of a pipe, for segments that read as one cluster.

        Deliberately narrower than PIPE -- related things sit closer together.
        """
        self.add('  ', '  ')


def gauge(line: Line, label: str, pct: float, reset=None) -> None:
    """Appends a '<label> [ 42% ]' gauge, optionally followed by a reset time.

    The percentage is printed *on* the bar rather than beside it: the field is
    a fixed BAR_WIDTH cells with the number centred in it, and the filled
    portion is drawn as a colored background running under the text. That
    costs BAR_WIDTH cells total instead of BAR_WIDTH + 4 for a separate bar
    and number.

    The caller supplies any separator first, since gauges are divided from
    their neighbours by a pipe but from each other by plain whitespace.
    """
    field  = f'{round_pct(pct)}%'.center(BAR_WIDTH)
    filled = min(BAR_WIDTH, max(0, int(pct * BAR_WIDTH / 100 + 0.5)))
    bg     = bar_bg(pct)

    styled = f'{WHITE}{label} {RESET}'
    if filled:
        # Black on the threshold color, so the digits stay legible on the fill.
        styled += f'\033[30;{bg}m{field[:filled]}{RESET}'
    if filled < BAR_WIDTH:
        # Unfilled remainder keeps a dark track so the bar's extent is visible.
        styled += f'\033[37;100m{field[filled:]}{RESET}'

    line.add(styled, f'{label} {field}')

    if reset is not None:
        when = format_reset(reset)
        line.add(f' {GREY}{when}{RESET}', f' {when}')


def terminal_columns() -> int:
    """Claude Code exports COLUMNS before running the status line. tput and
    shutil.get_terminal_size() can't help here because stdout is captured
    rather than connected to the terminal."""
    try:
        return int(os.environ.get('COLUMNS', ''))
    except ValueError:
        return 0


def compose(build_left, right: Line) -> str:
    """Pins the context gauge to the right edge when it fits.

    Claude Code indents the status line by its own built-in spacing, so a line
    of exactly COLUMNS cells overflows the row it's rendered into and gets
    truncated with an ellipsis. RIGHT_MARGIN keeps the content clear of that.

    build_left is a callable rather than a finished Line so the left group can
    be rebuilt without the rate-limit reset times: they're the least critical
    thing on the line, and dropping them buys ~20 cells, which keeps the
    alignment working on narrower terminals instead of overflowing.
    """
    if not right.width:
        return build_left(True).styled

    columns = terminal_columns()
    if not columns:
        return build_left(True).styled + PIPE + right.styled

    usable = columns - RIGHT_MARGIN
    for with_resets in (True, False):
        left = build_left(with_resets)
        pad = usable - left.width - right.width
        if pad >= 1:
            return left.styled + ' ' * pad + right.styled

    # Genuinely too narrow to align: inline flow, still without reset times.
    return build_left(False).styled + PIPE + right.styled


def git_segment(cwd: str) -> str:
    """Branch, dirty marker and ahead/behind counts, or '' outside a repo.

    A single git invocation gathers all three (rather than separate
    rev-parse/branch/rev-list/status calls), since this runs on every status
    line refresh.
    """
    try:
        result = subprocess.run(
            ['git', '-C', cwd, 'status', '--porcelain=v2', '--branch'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
        git_out = result.stdout
    except FileNotFoundError:
        git_out = ''

    if not git_out:
        return ''

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
        return ''

    segment = f'{WHITE}{branch}{RESET}'
    if dirty:
        segment += f' \033[1;33m●{RESET}'

    if ab:
        tokens = ab.split()
        if len(tokens) == 2:
            try:
                ahead  = int(tokens[0].lstrip('+'))
                behind = int(tokens[1].lstrip('-'))
                if ahead  > 0:
                    segment += f' {GREY}↑{ahead}{RESET}'
                if behind > 0:
                    segment += f' {GREY}↓{behind}{RESET}'
            except ValueError:
                pass

    return segment


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        data = {}

    cwd = (data.get('workspace') or {}).get('current_dir') or os.getcwd()
    directory = os.path.basename(cwd) or cwd

    model  = (data.get('model') or {}).get('display_name')
    effort = (data.get('effort') or {}).get('level')
    style  = (data.get('output_style') or {}).get('name')

    # cost.total_cost_usd is deliberately unused: it's an estimate of what the
    # tokens would have cost at API rates, which isn't money spent on a
    # subscription plan. The 5h/7d gauges are the real constraint.
    cost     = data.get('cost') or {}
    duration = cost.get('total_duration_ms')
    added    = cost.get('total_lines_added') or 0
    removed  = cost.get('total_lines_removed') or 0

    ctx_used = (data.get('context_window') or {}).get('used_percentage')

    five_h      = (data.get('rate_limits') or {}).get('five_hour') or {}
    seven_d     = (data.get('rate_limits') or {}).get('seven_day') or {}
    five_pct    = five_h.get('used_percentage')
    seven_pct   = seven_d.get('used_percentage')
    five_reset  = five_h.get('resets_at')
    seven_reset = seven_d.get('resets_at')

    # --- line 1: where the work is happening --------------------------------
    #
    # Location and working-tree state: directory, how long this session has
    # been going, the branch, and what it has changed. Nothing here is aligned,
    # so it needs no width accounting.
    first = f'{WHITE}{directory}{RESET}'

    # Elapsed time rides directly on the directory rather than taking its own
    # separator -- it reads as "how long have I been in here".
    if duration:
        clock = format_duration(duration)
        first += f' {GREY}{clock}{RESET}'

    branch = git_segment(cwd)
    if branch:
        first += PIPE + branch

    # Churn sits with the branch: both describe the working tree. It stands
    # alone outside a repo, and is absent before the first edit.
    if added or removed:
        first += f' {GREEN}+{added}{RESET} {RED}-{removed}{RESET}'

    print(first)

    # --- line 2: what the session is spending -------------------------------
    def build_left(with_resets: bool) -> Line:
        left = Line()

        if model:
            left.add(f'{GREY}{model}{RESET}', model)
            # Absent when the model takes no reasoning effort parameter.
            if effort:
                color = EFFORT_COLORS.get(effort, '0;90')
                left.add(f' \033[{color}m({effort}){RESET}', f' ({effort})')

        if style and style != 'default':
            left.sep()
            left.add(f'{GREY}{style}{RESET}', style)

        # The rate-limit gauges stay in the left group: their reset times are
        # easier to track when they sit at a fixed offset rather than sliding
        # with the terminal width. Only the context gauge, which changes
        # fastest, is pinned to the right edge.
        if five_pct is not None:
            left.sep()
            gauge(left, '5h', five_pct, five_reset if with_resets else None)
        if seven_pct is not None:
            # The two rate-limit gauges read as one cluster, so whitespace
            # divides them rather than another pipe.
            if five_pct is None:
                left.sep()
            else:
                left.gap()
            gauge(left, '7d', seven_pct, seven_reset if with_resets else None)

        return left

    right = Line()
    if ctx_used is not None:
        gauge(right, 'ctx', ctx_used)

    # Skip the line entirely rather than emitting a blank one, e.g. before the
    # first API response of a session.
    if build_left(True).width or right.width:
        print(compose(build_left, right))


if __name__ == '__main__':
    main()
