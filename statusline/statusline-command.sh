#!/bin/bash
# Claude Code status line, derived from the user's ~/.bashrc PS1:
#   PS1='\[\033[01;32m\][\u@\h\[\033[01;37m\] \W\[\033[01;32m\]]\$\[\033[00m\] '
# Trailing "$" prompt character removed per status line conventions.
#
# Additionally renders:
#   - context window usage (from .context_window.used_percentage)
#   - 5-hour rate limit usage (from .rate_limits.five_hour.used_percentage)
#   - 7-day (weekly) rate limit usage (from .rate_limits.seven_day.used_percentage)
#   - a second line with git branch / dirty state / ahead-behind, when cwd
#     is inside a git repo
# These fields are part of the documented status line JSON stdin payload.
# Rate limit fields are only present for Claude.ai subscribers after the
# first API response of a session, so they are omitted gracefully if absent.

input=$(cat)

cwd_input=$(echo "$input" | jq -r '.workspace.current_dir // empty')
[ -z "$cwd_input" ] && cwd_input="$(pwd)"
dir=$(basename "$cwd_input")

model=$(echo "$input" | jq -r '.model.display_name // empty')

ctx_used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
five_hour=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
seven_day=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
five_hour_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
seven_day_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')

# Colors tuned for a dark terminal background. Dim variants (2;3x) read as
# washed-out grey on dark backgrounds, so plain/bold variants are used
# instead for contrast.
CYAN='\033[1;36m'    # separators / structure
WHITE='\033[0;37m'   # primary text (dir, bar labels)
GREY='\033[0;90m'     # secondary text (model name)
RESET='\033[0m'

# Returns an ANSI color code (green/yellow/red) based on usage thresholds,
# so high usage is visually obvious at a glance.
bar_color() {
  pct=$1
  if awk -v p="$pct" 'BEGIN { exit !(p >= 85) }'; then
    echo "1;31"
  elif awk -v p="$pct" 'BEGIN { exit !(p >= 60) }'; then
    echo "1;33"
  else
    echo "1;32"
  fi
}

# Renders a 10-block gauge (e.g. [████░░░░░░]) for a 0-100 percentage,
# one block per 10%.
make_bar() {
  pct=$1
  width=10
  # Round to nearest integer for bar-segment math.
  filled=$(LC_NUMERIC=C awk -v p="$pct" -v w="$width" 'BEGIN { printf "%d", (p * w / 100) + 0.5 }')
  [ "$filled" -gt "$width" ] && filled=$width
  [ "$filled" -lt 0 ] && filled=0
  empty=$((width - filled))
  bar=""
  i=0
  while [ "$i" -lt "$filled" ]; do bar="${bar}█"; i=$((i + 1)); done
  i=0
  while [ "$i" -lt "$empty" ]; do bar="${bar}░"; i=$((i + 1)); done
  echo "$bar"
}

# Rounds a percentage to the nearest integer (locale-safe; bash's printf
# %.0f breaks under locales like hu_HU.UTF-8 that use ',' as the decimal
# separator).
round_pct() {
  LC_NUMERIC=C awk -v p="$1" 'BEGIN { printf "%d", p + 0.5 }'
}

# Formats a Unix timestamp as a short reset time. Shows just "HH:MM" if
# the reset falls within the next 24h, otherwise "Day HH:MM".
format_reset() {
  ts=$1
  now=$(date +%s)
  diff=$((ts - now))
  if [ "$diff" -lt 86400 ]; then
    LC_TIME=C date -d "@$ts" '+%H:%M' 2>/dev/null
  else
    LC_TIME=C date -d "@$ts" '+%a %H:%M' 2>/dev/null
  fi
}

# Single git invocation gathers branch, ahead/behind, and dirty state at
# once (rather than separate rev-parse/branch/rev-list/status calls), since
# this script runs on every status line refresh. Empty stdout means either
# not a repo or git is missing; either way the git line is skipped.
git_status=$(git -C "$cwd_input" status --porcelain=v2 --branch 2>/dev/null)

printf "${WHITE}%s${RESET}" "$dir"

if [ -n "$model" ]; then
  printf " ${CYAN}|${RESET} ${GREY}%s${RESET}" "$model"
fi

if [ -n "$ctx_used" ]; then
  printf " ${CYAN}|${RESET}"
  bar=$(make_bar "$ctx_used")
  color=$(bar_color "$ctx_used")
  printf " ${WHITE}ctx \033[%sm%s ${RESET}\033[%sm%s%%${RESET}" \
    "$color" "$bar" "$color" "$(round_pct "$ctx_used")"
fi

if [ -n "$five_hour" ]; then
  printf " ${CYAN}|${RESET}"
  bar=$(make_bar "$five_hour")
  color=$(bar_color "$five_hour")
  printf " ${WHITE}5h \033[%sm%s ${RESET}\033[%sm%s%%${RESET}" \
    "$color" "$bar" "$color" "$(round_pct "$five_hour")"
  [ -n "$five_hour_reset" ] && printf " ${GREY}%s${RESET}" "$(format_reset "$five_hour_reset")"
fi

if [ -n "$seven_day" ]; then
  printf " ${CYAN}|${RESET}"
  bar=$(make_bar "$seven_day")
  color=$(bar_color "$seven_day")
  printf " ${WHITE}7d \033[%sm%s ${RESET}\033[%sm%s%%${RESET}" \
    "$color" "$bar" "$color" "$(round_pct "$seven_day")"
  [ -n "$seven_day_reset" ] && printf " ${GREY}%s${RESET}" "$(format_reset "$seven_day_reset")"
fi

printf "\n"

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
    printf "${WHITE}%s${RESET}" "$branch"
    [ "$dirty" -eq 1 ] && printf " \033[1;33m●${RESET}"

    if [ -n "$ab" ]; then
      ahead="${ab%% *}"
      behind="${ab#* }"
      ahead="${ahead#+}"
      behind="${behind#-}"
      [ "$ahead" -gt 0 ] 2>/dev/null && printf " ${GREY}↑%s${RESET}" "$ahead"
      [ "$behind" -gt 0 ] 2>/dev/null && printf " ${GREY}↓%s${RESET}" "$behind"
    fi

    printf "\n"
  fi
fi
