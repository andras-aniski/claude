import sys

if sys.version_info < (3, 8):
    # Pure ASCII deliberately: this runs before the stdout UTF-8 reconfigure
    # below, so a non-ASCII character here would raise UnicodeEncodeError on a
    # legacy Windows code page -- a traceback in place of the actual message.
    # The '[statusline]' prefix matches what the launchers print.
    print("[statusline] Python 3.8+ required, found " + sys.version.split()[0])
    sys.exit(0)

import json
import os
import re
import subprocess
import time
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
GREEN  = '\033[1;32m'
YELLOW = '\033[1;33m'
RED    = '\033[1;31m'
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


def format_reset(ts) -> str:
    """Formats a Unix timestamp as a short reset time: "HH:MM" if the reset
    falls within the next 24h, otherwise "Day HH:MM".

    Returns '' for anything that isn't a usable epoch -- a millisecond-scale
    value, an ISO-8601 string -- so a payload change costs one segment rather
    than the whole line. Unguarded, this is the only place where untrusted
    payload data reaches a conversion that can raise.
    """
    try:
        reset = datetime.fromtimestamp(float(ts))
    except (TypeError, ValueError, OSError, OverflowError):
        return ''
    diff = reset - datetime.now()
    if diff.total_seconds() < 86400:
        return reset.strftime('%H:%M')
    return reset.strftime('%a %H:%M')


def decimal(value):
    """A payload value as a float if it reads as plain digits with an optional
    fraction, otherwise None.

    Deliberately narrower than float(): it accepts exactly what the bash
    version's decimal() pattern accepts -- a number or numeric string, no sign,
    no exponent, not a bool -- so both degrade identically on an odd payload.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    text = str(value)
    if not re.fullmatch(r'[0-9]+(\.[0-9]+)?', text):
        return None
    return float(text)


def whole(value, limit: int):
    """Integer part of a decimal() payload value, or None if it isn't one or
    exceeds limit. The digit-count cap mirrors the bash version, where a
    longer string would overflow shell arithmetic before the comparison."""
    if decimal(value) is None:
        return None
    digits = str(value).split('.')[0]
    if len(digits) > 15:
        return None
    number = int(digits)
    return number if number <= limit else None


def format_tokens(count: int) -> str:
    """850 / 45k / 1.2M."""
    if count < 1000:
        return str(count)
    if count < 999500:
        return f'{(count + 500) // 1000}k'
    return f'{count / 1000000:.1f}M'


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
    stripping ANSI escapes back out afterwards. Every glyph either line emits
    (including git's ● ↑ ↓) is single-width, so len() is a correct cell count
    -- do not introduce emoji here. Directory and branch names are counted the
    same way, so a wide character in one of them shifts the line 1 alignment.
    """

    def __init__(self) -> None:
        self.styled = ''
        self.width  = 0

    def add(self, styled: str, plain: str) -> None:
        self.styled += styled
        self.width  += len(plain)

    def extend(self, other: 'Line') -> None:
        self.styled += other.styled
        self.width  += other.width

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
        # Empty when the payload timestamp is unusable; skip rather than pad.
        if when:
            line.add(f' {GREY}{when}{RESET}', f' {when}')


def terminal_columns() -> int:
    """Claude Code exports COLUMNS before running the status line. tput and
    shutil.get_terminal_size() can't help here because stdout is captured
    rather than connected to the terminal."""
    try:
        return int(os.environ.get('COLUMNS', ''))
    except ValueError:
        return 0


def align(left: Line, right: Line):
    """Pads left so right ends at the usable edge, or None when it can't be
    aligned: COLUMNS is missing, or the two don't fit side by side.

    Claude Code indents the status line by its own built-in spacing, so a line
    of exactly COLUMNS cells overflows the row it's rendered into and gets
    truncated with an ellipsis. RIGHT_MARGIN keeps the content clear of that.
    """
    columns = terminal_columns()
    if columns <= 0:
        return None
    pad = columns - RIGHT_MARGIN - left.width - right.width
    if pad < 1:
        return None
    return left.styled + ' ' * pad + right.styled


def compose(full: Line, build_left, right: Line) -> str:
    """Pins the context gauge to the right edge when it fits.

    Takes the already-built left group *and* the callable that produced it:
    every path needs the full version, and only the narrow ones need it rebuilt
    without the rate-limit reset times. Those are the least critical thing on
    the line and dropping them buys ~20 cells, which keeps the alignment working
    instead of overflowing. Building is not free -- it forks awk per gauge and
    date per reset -- and this runs every refreshInterval seconds, so the group
    is built once on the happy path and at most twice ever.
    """
    if not right.width:
        return full.styled

    aligned = align(full, right)
    if aligned:
        return aligned

    if terminal_columns() <= 0:
        return full.styled + PIPE + right.styled

    trimmed = build_left(False)
    # Genuinely too narrow to align: inline flow, still without reset times.
    return align(trimmed, right) or trimmed.styled + PIPE + right.styled


def cache_segment(cache) -> Line:
    """'cache 91%  2 misses  42m' while warm, 'cache 91%  cold 45k' once not.

    The percentage is the session's hit ratio, the misses count only appears
    once there is one, and the countdown is how long until the cached prefix
    expires -- yellow in the last fifth of its TTL. Once cold, the countdown
    gives way to what the next request will have to re-cache.

    Empty when the payload has no prompt_cache yet (before the first API
    response) or caching isn't being reported at all.
    """
    segment = Line()
    if not isinstance(cache, dict) or not cache:
        return segment
    if cache.get('caching_observed') is False:
        return segment

    segment.add(f'{WHITE}cache{RESET}', 'cache')

    ratio = decimal(cache.get('hit_ratio'))
    if ratio is not None:
        pct = round_pct(ratio * 100)
        segment.add(f' {GREY}{pct}%{RESET}', f' {pct}%')

    misses = whole(cache.get('misses'), 10 ** 9)
    if misses:
        word = 'miss' if misses == 1 else 'misses'
        segment.add(f'  {YELLOW}{misses} {word}{RESET}', f'  {misses} {word}')

    # expires_at can lag the clock by up to a refresh interval, so a past
    # expiry reads as cold even while the payload still says warm.
    expires = whole(cache.get('expires_at'), 253402300799)
    left = expires - int(time.time()) if expires is not None else None

    if cache.get('warm') is True and (left is None or left > 0):
        if left is not None:
            ttl = 3600 if cache.get('ttl') == '1h' else 300
            color = YELLOW if left * 5 < ttl else GREEN
            when = format_duration(left * 1000)
            segment.add(f'  {color}{when}{RESET}', f'  {when}')
    else:
        segment.add(f'  {RED}cold{RESET}', '  cold')
        recache = whole(cache.get('recache_tokens_if_cold'), 10 ** 15)
        if recache:
            tokens = format_tokens(recache)
            segment.add(f' {GREY}{tokens}{RESET}', f' {tokens}')

    return segment


def git_segment(cwd: str) -> Line:
    """Branch, dirty marker and ahead/behind counts; empty outside a repo.

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

    segment = Line()
    if not git_out:
        return segment

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
        return segment

    segment.add(f'{WHITE}{branch}{RESET}', branch)
    if dirty:
        segment.add(f' {YELLOW}●{RESET}', ' ●')

    if ab:
        tokens = ab.split()
        if len(tokens) == 2:
            try:
                ahead  = int(tokens[0].lstrip('+'))
                behind = int(tokens[1].lstrip('-'))
                if ahead  > 0:
                    segment.add(f' {GREY}↑{ahead}{RESET}', f' ↑{ahead}')
                if behind > 0:
                    segment.add(f' {GREY}↓{behind}{RESET}', f' ↓{behind}')
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
    #
    # cost.total_lines_added/removed are unused too: they count Claude's edits
    # across the whole session, survive commits, and include files outside the
    # repo, so they say nothing about the working tree. git's dirty marker does.
    duration = (data.get('cost') or {}).get('total_duration_ms')

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
    # been going, and the branch -- with the prompt cache pinned to the right
    # edge, directly above the context gauge.
    first = Line()
    first.add(f'{WHITE}{directory}{RESET}', directory)

    # Elapsed time rides directly on the directory rather than taking its own
    # separator -- it reads as "how long have I been in here".
    if duration:
        clock = format_duration(duration)
        first.add(f' {GREY}{clock}{RESET}', f' {clock}')

    branch = git_segment(cwd)
    if branch.width:
        first.add(PIPE, PIPE_PLAIN)
        first.extend(branch)

    cache = cache_segment(data.get('prompt_cache'))
    if not cache.width:
        print(first.styled)
    else:
        print(align(first, cache) or first.styled + PIPE + cache.styled)

    # --- line 2: what the session is spending -------------------------------
    def build_left(with_resets: bool) -> Line:
        left = Line()

        if model:
            left.add(f'{GREY}{model}{RESET}', model)

        # Absent when the model takes no reasoning effort parameter. Guarded
        # independently of the model name rather than nested under it, so a
        # payload carrying one but not the other still renders what it has.
        if effort:
            color = EFFORT_COLORS.get(effort, '0;90')
            space = ' ' if model else ''
            left.add(f'{space}\033[{color}m({effort}){RESET}', f'{space}({effort})')

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
    # first API response of a session. The group built for that test is the
    # same one compose() needs, so it's passed along rather than rebuilt.
    full = build_left(True)
    if full.width or right.width:
        print(compose(full, build_left, right))


if __name__ == '__main__':
    main()
