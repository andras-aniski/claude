#!/bin/bash
# Asserts that statusline.py and statusline-command.sh are interchangeable.
#
# The two are a near-verbatim copy of the same ~350 lines (see "Two
# implementations" in README.md), which means every change to one has to be
# mirrored in the other. They have drifted before -- most of what this matrix
# covers are cases where they silently disagreed: malformed reset timestamps
# crashed the Python version while the bash version printed shell syntax errors
# to stderr, and `date -d` being GNU-only made macOS drop every reset time.
#
# For each payload x terminal width it checks three things:
#   1. python writes nothing to stderr
#   2. bash writes nothing to stderr
#   3. their stdout is byte-identical
#
# Run it after touching either implementation:
#
#   bash statusline/parity-test.sh
#
# Development aid only -- install.py does not deploy this.
cd "$(dirname "$0")" || exit 1

NOW=$(date +%s)
SOON=$((NOW + 3600))       # < 24h away  -> "HH:MM"
LATER=$((NOW + 200000))    # > 24h away  -> "Day HH:MM"

# name|payload. The awkward-looking ones are all regressions: a reset time in
# milliseconds or as an ISO string used to raise/print errors, a 0 percentage
# has to render (it is a real state, not an absent field), float churn used to
# be dropped by bash only, and effort without a model used to render nothing.
payloads=(
  'empty|{}'
  'model-only|{"model":{"display_name":"Sonnet 4.6"}}'
  'model+effort|{"model":{"display_name":"Sonnet 4.6"},"effort":{"level":"high"}}'
  'effort-no-model|{"effort":{"level":"max"}}'
  'style-default|{"model":{"display_name":"Opus 5"},"output_style":{"name":"default"}}'
  'style-set|{"model":{"display_name":"Opus 5"},"output_style":{"name":"Explanatory"}}'
  "reset-valid|{\"rate_limits\":{\"five_hour\":{\"used_percentage\":72,\"resets_at\":$SOON},\"seven_day\":{\"used_percentage\":91,\"resets_at\":$LATER}}}"
  'reset-ms|{"rate_limits":{"five_hour":{"used_percentage":72,"resets_at":1785000000000}}}'
  "reset-float|{\"rate_limits\":{\"five_hour\":{\"used_percentage\":72,\"resets_at\":$SOON.0}}}"
  'reset-string|{"rate_limits":{"five_hour":{"used_percentage":72,"resets_at":"2026-08-03T10:00:00Z"}}}'
  'reset-zero|{"rate_limits":{"five_hour":{"used_percentage":72,"resets_at":0}}}'
  'pct-zero|{"rate_limits":{"five_hour":{"used_percentage":0}},"context_window":{"used_percentage":0}}'
  'churn-int|{"cost":{"total_lines_added":312,"total_lines_removed":47}}'
  'churn-float|{"cost":{"total_lines_added":312.0,"total_lines_removed":47.0}}'
  'churn-zero|{"cost":{"total_lines_added":0,"total_lines_removed":0}}'
  'duration|{"cost":{"total_duration_ms":1620000}}'
  'ctx-only|{"context_window":{"used_percentage":43}}'
  "full|{\"model\":{\"display_name\":\"Sonnet 4.6\"},\"effort\":{\"level\":\"high\"},\"context_window\":{\"used_percentage\":43},\"cost\":{\"total_duration_ms\":1620000,\"total_lines_added\":312,\"total_lines_removed\":47},\"rate_limits\":{\"five_hour\":{\"used_percentage\":72,\"resets_at\":$SOON},\"seven_day\":{\"used_percentage\":91,\"resets_at\":$LATER}}}"
)

# Unset exercises the no-COLUMNS fallback; 40 is narrow enough to force the
# reset times to be dropped and then to give up on alignment entirely.
widths=("" 40 80 160)

fails=0
for cols in "${widths[@]}"; do
  for entry in "${payloads[@]}"; do
    name=${entry%%|*}
    json=${entry#*|}
    label="[cols=${cols:-unset}] $name"

    py_err=$(mktemp); sh_err=$(mktemp)
    py=$(printf '%s' "$json" | COLUMNS=$cols python3 statusline.py 2>"$py_err")
    sh=$(printf '%s' "$json" | COLUMNS=$cols bash statusline-command.sh 2>"$sh_err")

    if [ -s "$py_err" ]; then
      echo "FAIL $label -- python wrote to stderr:"
      sed 's/^/    /' "$py_err"
      fails=$((fails + 1))
    fi
    if [ -s "$sh_err" ]; then
      echo "FAIL $label -- bash wrote to stderr:"
      sed 's/^/    /' "$sh_err"
      fails=$((fails + 1))
    fi
    if [ "$py" != "$sh" ]; then
      echo "FAIL $label -- output differs (< python, > bash):"
      diff <(printf '%s\n' "$py" | LC_ALL=C cat -v) \
           <(printf '%s\n' "$sh" | LC_ALL=C cat -v) | sed 's/^/    /'
      fails=$((fails + 1))
    fi
    rm -f "$py_err" "$sh_err"
  done
done

total=$(( ${#widths[@]} * ${#payloads[@]} ))
echo
if [ "$fails" -eq 0 ]; then
  echo "PASS -- $total cases, both implementations agree, no stderr"
  exit 0
fi
echo "FAIL -- $fails failure(s) across $total cases"
exit 1
