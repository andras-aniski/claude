#!/bin/bash
# Claude Code status line, derived from the user's ~/.bashrc PS1:
#   PS1='\[\033[01;32m\][\u@\h\[\033[01;37m\] \W\[\033[01;32m\]]\$\[\033[00m\] '
# Trailing "$" prompt character removed per status line conventions.
#
# Line 1 is where the work is happening: dir + elapsed time, git branch /
# dirty state / ahead-behind, and the session's lines changed. Line 2 is what
# the session is spending: model + reasoning effort, output style, and the
# 5-hour / 7-day rate limit gauges, with the context window gauge pushed flush
# against the right edge when it fits.
#
# All of these come from the documented status line JSON stdin payload. Rate
# limit fields are only present for Claude.ai subscribers after the first API
# response of a session, and `effort` only for models that take a reasoning
# effort parameter, so every segment is omitted gracefully when absent.

input=$(cat)

# One jq invocation for every field. The script runs on each status line
# refresh, so it avoids re-spawning jq per field the way separate calls would.
#
# Fields are joined on US (\037) rather than tab: bash collapses runs of IFS
# *whitespace* into a single delimiter, so adjacent empty fields would shift
# every later value into the wrong variable. Any US/tab/newline inside a value
# is flattened to a space for the same reason.
#
# jq's `//` only falls through on null/false, so numeric zeros survive as "0"
# and are filtered by the per-segment guards below.
#
# .cost.total_cost_usd is deliberately not extracted: it's an estimate of what
# the tokens would have cost at API rates, which isn't money spent on a
# subscription plan. The 5h/7d gauges are the real constraint.
IFS=$'\037' read -r cwd_input model effort output_style \
  duration_ms lines_added lines_removed \
  ctx_used five_hour five_hour_reset seven_day seven_day_reset <<EOF
$(echo "$input" | jq -r '[
  (.workspace.current_dir // ""),
  (.model.display_name // ""),
  (.effort.level // ""),
  (.output_style.name // ""),
  (.cost.total_duration_ms // ""),
  (.cost.total_lines_added // ""),
  (.cost.total_lines_removed // ""),
  (.context_window.used_percentage // ""),
  (.rate_limits.five_hour.used_percentage // ""),
  (.rate_limits.five_hour.resets_at // ""),
  (.rate_limits.seven_day.used_percentage // ""),
  (.rate_limits.seven_day.resets_at // "")
] | map(tostring | gsub("\\s"; " ")) | join("\u001f")')
EOF

[ -z "$cwd_input" ] && cwd_input="$(pwd)"
dir=$(basename "$cwd_input")

# Colors tuned for a dark terminal background. Dim variants (2;3x) read as
# washed-out grey on dark backgrounds, so plain/bold variants are used
# instead for contrast. Written as $'...' so they hold real escape bytes and
# can be concatenated into variables, rather than relying on printf to
# interpret \033 inside a format string.
ESC=$'\033'
CYAN=$'\033[1;36m'    # separators / structure
WHITE=$'\033[0;37m'   # primary text (dir, bar labels)
GREY=$'\033[0;90m'    # secondary text (model name, session name, cost)
GREEN=$'\033[1;32m'   # lines added
RED=$'\033[1;31m'     # lines removed
RESET=$'\033[0m'

# Spacing carries the grouping, so it widens with conceptual distance: 1 cell
# inside a gauge, 2 between related gauges (acc_gap), 5 across concepts. A pipe
# padded narrower than the gap would read as the tighter break, which is
# backwards.
PIPE="  ${CYAN}|${RESET}  "
PIPE_WIDTH=5

# Cells left free at the right edge. Claude Code renders the status line
# indented by its own built-in spacing, so content filling all of COLUMNS
# overflows the row and comes back truncated with an ellipsis. Measured
# empirically: the usable width is COLUMNS - 3, and this carries one cell of
# headroom on top. Raise it if a trailing "…" ever reappears; drop it to 3 to
# sit flush against the last usable column.
RIGHT_MARGIN=4

# Cells each gauge occupies. The percentage is centred inside this field and
# the fill is drawn as a background under it, so this is the whole gauge width
# (minus its label), not just a bar sitting next to a number.
BAR_WIDTH=10

# Reasoning effort is a discrete enum rather than a scale, so it gets an
# explicit map instead of going through bar_bg()'s thresholds. Ultracode
# reports as 'xhigh'; anything unrecognised falls back to grey.
effort_color() {
  case "$1" in
    low)    echo "0;90" ;;
    medium) echo "1;32" ;;
    high)   echo "1;33" ;;
    xhigh)  echo "1;31" ;;
    max)    echo "1;35" ;;
    *)      echo "0;90" ;;
  esac
}

# Returns an ANSI background code (green/yellow/red) for the filled part of a
# gauge, based on usage thresholds, so high usage is obvious at a glance.
bar_bg() {
  pct=$1
  if awk -v p="$pct" 'BEGIN { exit !(p >= 85) }'; then
    echo "41"
  elif awk -v p="$pct" 'BEGIN { exit !(p >= 60) }'; then
    echo "43"
  else
    echo "42"
  fi
}

# Centres a string in a fixed-width field (locale-safe: the caller only passes
# ASCII, so ${#s} is a correct cell count here).
center() {
  c_text=$1
  c_width=$2
  c_left=$(( (c_width - ${#c_text}) / 2 ))
  [ "$c_left" -lt 0 ] && c_left=0
  c_right=$(( c_width - ${#c_text} - c_left ))
  [ "$c_right" -lt 0 ] && c_right=0
  printf '%*s%s%*s' "$c_left" '' "$c_text" "$c_right" ''
}

# Rounds a percentage to the nearest integer (locale-safe; bash's printf
# %.0f breaks under locales like hu_HU.UTF-8 that use ',' as the decimal
# separator).
round_pct() {
  LC_NUMERIC=C awk -v p="$1" 'BEGIN { printf "%d", p + 0.5 }'
}

# True when a numeric payload field is present and greater than zero, so
# "0" (which jq's // passes through) is treated as "nothing to show".
positive() {
  [ -n "$1" ] || return 1
  awk -v n="$1" 'BEGIN { exit !(n > 0) }'
}

# Formats an epoch as a local time. GNU date spells this `-d @<epoch>`; the
# BSD date shipped on macOS rejects -d outright and spells it `-r <epoch>`.
# Probed once at startup rather than per call, and defined as a function so
# format_reset stays free of the platform split.
if date -d @0 '+%s' >/dev/null 2>&1; then
  epoch_fmt() { LC_TIME=C date -d "@$1" "+$2"; }
else
  epoch_fmt() { LC_TIME=C date -r "$1" "+$2"; }
fi

# Formats a Unix timestamp as a short reset time. Shows just "HH:MM" if
# the reset falls within the next 24h, otherwise "Day HH:MM".
#
# Prints nothing for anything that isn't a usable epoch -- a millisecond-scale
# value, an ISO-8601 string -- so a payload change costs one segment rather than
# a shell arithmetic error on stderr every refresh.
# Locals are fr_-prefixed like the other helpers: bash 3.2 has no block scope,
# and a bare `diff` global would survive a failed conversion and hand the next
# gauge the previous one's <24h decision.
format_reset() {
  fr_ts=${1%%.*}   # tolerate "1785000000.0" the way format_duration does
  case "$fr_ts" in
    ''|*[!0-9]*) return ;;
  esac
  # Above the year-9999 epoch the formatting is meaningless anyway, and this
  # is the same bound Python's datetime.fromtimestamp() enforces.
  [ "$fr_ts" -gt 253402300799 ] && return

  fr_diff=$((fr_ts - $(date +%s)))
  if [ "$fr_diff" -lt 86400 ]; then
    epoch_fmt "$fr_ts" '%H:%M' 2>/dev/null
  else
    epoch_fmt "$fr_ts" '%a %H:%M' 2>/dev/null
  fi
}

# Formats a millisecond duration as 45s / 12m / 1h 5m. Pure arithmetic, so it
# needs no `date` at all and sidesteps the GNU/BSD split entirely.
format_duration() {
  total=$(( ${1%%.*} / 1000 ))
  if [ "$total" -lt 60 ]; then
    echo "${total}s"
    return
  fi
  minutes=$((total / 60))
  if [ "$minutes" -lt 60 ]; then
    echo "${minutes}m"
    return
  fi
  echo "$((minutes / 60))h $((minutes % 60))m"
}

# --- line 2 accumulators -----------------------------------------------------
#
# Right-alignment needs to know how many terminal cells a group occupies, so
# each group is built as a (styled string, visible width) pair. Width is
# passed explicitly rather than derived from the styled text, which would have
# to be stripped of ANSI escapes first.
ACC_S=""
ACC_N=0

acc_reset() { ACC_S=""; ACC_N=0; }
acc_add()   { ACC_S="${ACC_S}$1"; ACC_N=$((ACC_N + $2)); }
acc_sep()   { [ "$ACC_N" -gt 0 ] && acc_add "$PIPE" "$PIPE_WIDTH"; }
# Whitespace instead of a pipe, for segments that read as one cluster.
# Deliberately narrower than PIPE -- related things sit closer together.
acc_gap()   { acc_add "  " 2; }

# Appends a '<label> [ 42% ]' gauge, optionally followed by a reset time.
#
# The percentage is printed *on* the bar rather than beside it: the field is a
# fixed BAR_WIDTH cells with the number centred in it, and the filled portion
# is drawn as a colored background running under the text. That costs
# BAR_WIDTH cells total instead of BAR_WIDTH + 4 for a separate bar and number.
#
# The caller supplies any separator first, since gauges are divided from their
# neighbours by a pipe but from each other by plain whitespace.
gauge() {
  g_label=$1
  g_pct=$2
  g_reset=$3
  g_bg=$(bar_bg "$g_pct")
  g_field=$(center "$(round_pct "$g_pct")%" "$BAR_WIDTH")
  # Round to nearest cell for the fill boundary.
  g_filled=$(LC_NUMERIC=C awk -v p="$g_pct" -v w="$BAR_WIDTH" 'BEGIN { printf "%d", (p * w / 100) + 0.5 }')
  [ "$g_filled" -gt "$BAR_WIDTH" ] && g_filled=$BAR_WIDTH
  [ "$g_filled" -lt 0 ] && g_filled=0

  g_styled="${WHITE}${g_label} ${RESET}"
  # Black on the threshold color, so the digits stay legible on the fill.
  [ "$g_filled" -gt 0 ] && \
    g_styled="${g_styled}${ESC}[30;${g_bg}m${g_field:0:$g_filled}${RESET}"
  # Unfilled remainder keeps a dark track so the bar's extent is visible.
  [ "$g_filled" -lt "$BAR_WIDTH" ] && \
    g_styled="${g_styled}${ESC}[37;100m${g_field:$g_filled}${RESET}"

  acc_add "$g_styled" $(( ${#g_label} + 1 + BAR_WIDTH ))

  if [ -n "$g_reset" ]; then
    g_when=$(format_reset "$g_reset")
    # Empty when the payload timestamp is unusable; skip rather than pad.
    [ -n "$g_when" ] && acc_add " ${GREY}${g_when}${RESET}" $((1 + ${#g_when}))
  fi
}

# --- line 2 left group: what the session is spending -------------------------
#
# Built as a function so it can be rebuilt without the rate-limit reset times:
# they're the least critical thing on the line, and dropping them buys ~20
# cells, which keeps the alignment working on narrower terminals instead of
# overflowing. Leaves the result in ACC_S / ACC_N.
build_left() {
  bl_resets=$1
  acc_reset

  if [ -n "$model" ]; then
    acc_add "${GREY}${model}${RESET}" "${#model}"
    # Absent whenever the model doesn't take a reasoning effort parameter.
    if [ -n "$effort" ]; then
      color=$(effort_color "$effort")
      acc_add " ${ESC}[${color}m(${effort})${RESET}" $((3 + ${#effort}))
    fi
  fi

  if [ -n "$output_style" ] && [ "$output_style" != "default" ]; then
    acc_sep
    acc_add "${GREY}${output_style}${RESET}" "${#output_style}"
  fi

  # The rate-limit gauges stay in the left group: their reset times are easier
  # to track when they sit at a fixed offset rather than sliding with the
  # terminal width. Only the context gauge, which changes fastest, is pinned
  # to the right edge.
  if [ -n "$five_hour" ]; then
    acc_sep
    if [ "$bl_resets" -eq 1 ]; then
      gauge "5h" "$five_hour" "$five_hour_reset"
    else
      gauge "5h" "$five_hour"
    fi
  fi
  if [ -n "$seven_day" ]; then
    # The two rate-limit gauges read as one cluster, so whitespace divides
    # them rather than another pipe.
    if [ -n "$five_hour" ]; then acc_gap; else acc_sep; fi
    if [ "$bl_resets" -eq 1 ]; then
      gauge "7d" "$seven_day" "$seven_day_reset"
    else
      gauge "7d" "$seven_day"
    fi
  fi
}

# --- line 2 right group: context window --------------------------------------
acc_reset
[ -n "$ctx_used" ] && gauge "ctx" "$ctx_used"

right_s=$ACC_S
right_n=$ACC_N

# Single git invocation gathers branch, ahead/behind, and dirty state at
# once (rather than separate rev-parse/branch/rev-list/status calls), since
# this script runs on every status line refresh. Empty stdout means either
# not a repo or git is missing; either way the git segment is skipped.
git_status=$(git -C "$cwd_input" status --porcelain=v2 --branch 2>/dev/null)

git_line=""
if [ -n "$git_status" ]; then
  branch=""
  ab=""
  dirty=0
  # Pure-bash parsing (no awk/grep subprocesses) of the porcelain v2 output.
  while IFS= read -r line; do
    case "$line" in
      "# branch.head "*) branch="${line#"# branch.head "}" ;;
      "# branch.ab "*) ab="${line#"# branch.ab "}" ;;
      "#"*) ;;
      "") ;;
      *) dirty=1 ;;
    esac
  done <<< "$git_status"

  [ "$branch" = "(detached)" ] && branch="detached"

  if [ -n "$branch" ]; then
    git_line="${WHITE}${branch}${RESET}"
    [ "$dirty" -eq 1 ] && git_line="${git_line} ${ESC}[1;33m●${RESET}"

    if [ -n "$ab" ]; then
      ahead="${ab%% *}"
      behind="${ab#* }"
      ahead="${ahead#+}"
      behind="${behind#-}"
      [ "$ahead" -gt 0 ] 2>/dev/null && git_line="${git_line} ${GREY}↑${ahead}${RESET}"
      [ "$behind" -gt 0 ] 2>/dev/null && git_line="${git_line} ${GREY}↓${behind}${RESET}"
    fi
  fi
fi

# --- line 1: where the work is happening -------------------------------------
#
# Location and working-tree state: directory, how long this session has been
# going, the branch, and what it has changed. Nothing here is aligned, so it
# needs no width accounting.
first="${WHITE}${dir}${RESET}"

# Elapsed time rides directly on the directory rather than taking its own
# separator -- it reads as "how long have I been in here".
if positive "$duration_ms"; then
  elapsed=$(format_duration "$duration_ms")
  first="${first} ${GREY}${elapsed}${RESET}"
fi

[ -n "$git_line" ] && first="${first}${PIPE}${git_line}"

# Churn sits with the branch: both describe the working tree. It stands alone
# outside a repo, and is absent before the first edit.
[ -z "$lines_added" ] && lines_added=0
[ -z "$lines_removed" ] && lines_removed=0
if [ "$lines_added" -gt 0 ] 2>/dev/null || [ "$lines_removed" -gt 0 ] 2>/dev/null; then
  first="${first} ${GREEN}+${lines_added}${RESET} ${RED}-${lines_removed}${RESET}"
fi

printf '%s\n' "$first"

# --- line 2 ------------------------------------------------------------------
#
# Claude Code exports COLUMNS before running the status line; `tput cols`
# can't help here because stdout is captured rather than connected to the
# terminal. Reset times are dropped before alignment is given up on, and only
# a genuinely too-narrow terminal falls back to plain inline flow.
build_left 1
if [ "$ACC_N" -eq 0 ] && [ "$right_n" -eq 0 ]; then
  # Nothing to show, e.g. before the first API response; skip rather than
  # emitting a blank line.
  :
elif [ "$right_n" -eq 0 ]; then
  printf '%s\n' "$ACC_S"
elif [ -z "$COLUMNS" ] || ! [ "$COLUMNS" -gt 0 ] 2>/dev/null; then
  printf '%s%s%s\n' "$ACC_S" "$PIPE" "$right_s"
else
  usable=$((COLUMNS - RIGHT_MARGIN))
  placed=0
  for resets in 1 0; do
    build_left "$resets"
    pad=$((usable - ACC_N - right_n))
    if [ "$pad" -ge 1 ]; then
      printf '%s%*s%s\n' "$ACC_S" "$pad" '' "$right_s"
      placed=1
      break
    fi
  done
  if [ "$placed" -eq 0 ]; then
    build_left 0
    printf '%s%s%s\n' "$ACC_S" "$PIPE" "$right_s"
  fi
fi
