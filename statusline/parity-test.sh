#!/bin/bash
# Asserts that statusline.py and statusline-command.sh are interchangeable.
#
# The two are a near-verbatim copy of the same ~500 lines (see "Two
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
# Cache expiries sit mid-minute so the countdown reads the same even if the
# clock ticks over between the python and the bash run.
WARM=$((NOW + 1530))       # -> "25m", green under a 1h TTL
NEARLY=$((NOW + 330))      # -> "5m", yellow under a 1h TTL (last fifth)
PAST=$((NOW - 100))        # payload still says warm, clock says cold

# name|payload. The awkward-looking ones are all regressions: a reset time in
# milliseconds or as an ISO string used to raise/print errors, a 0 percentage
# has to render (it is a real state, not an absent field), and effort without
# a model used to render nothing.
# The cache-* ones cover each state of the line 1 cache segment, plus malformed
# values that decimal() and whole() have to reject identically.
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
  'duration|{"cost":{"total_duration_ms":1620000}}'
  'ctx-only|{"context_window":{"used_percentage":43}}'
  'cache-empty|{"prompt_cache":{}}'
  'cache-not-object|{"prompt_cache":"warm"}'
  'cache-unobserved|{"prompt_cache":{"caching_observed":false,"warm":false,"hit_ratio":null}}'
  "cache-warm|{\"prompt_cache\":{\"caching_observed\":true,\"warm\":true,\"ttl\":\"1h\",\"expires_at\":$WARM,\"hit_ratio\":0.91,\"misses\":0}}"
  "cache-nearly-cold|{\"prompt_cache\":{\"caching_observed\":true,\"warm\":true,\"ttl\":\"1h\",\"expires_at\":$NEARLY,\"hit_ratio\":0.5,\"misses\":1}}"
  "cache-5m-ttl|{\"prompt_cache\":{\"caching_observed\":true,\"warm\":true,\"ttl\":\"5m\",\"expires_at\":$NEARLY,\"hit_ratio\":0,\"misses\":2}}"
  'cache-warm-no-expiry|{"prompt_cache":{"caching_observed":true,"warm":true,"expires_at":null,"hit_ratio":0.995}}'
  "cache-expired|{\"prompt_cache\":{\"caching_observed\":true,\"warm\":true,\"ttl\":\"1h\",\"expires_at\":$PAST,\"hit_ratio\":0.91,\"recache_tokens_if_cold\":45000}}"
  'cache-cold|{"prompt_cache":{"caching_observed":true,"warm":false,"expires_at":null,"hit_ratio":0.91,"misses":3,"recache_tokens_if_cold":999499}}'
  'cache-cold-mega|{"prompt_cache":{"caching_observed":true,"warm":false,"hit_ratio":0.91,"recache_tokens_if_cold":1250000}}'
  'cache-cold-small|{"prompt_cache":{"caching_observed":true,"warm":false,"recache_tokens_if_cold":850.0}}'
  'cache-malformed|{"prompt_cache":{"caching_observed":"false","warm":"true","expires_at":"2026-08-03T10:00:00Z","hit_ratio":"abc","misses":-1,"recache_tokens_if_cold":1e20}}'
  'cache-ms-expiry|{"prompt_cache":{"warm":true,"expires_at":1785000000000,"hit_ratio":"0.75","misses":"007"}}'
  "full|{\"model\":{\"display_name\":\"Sonnet 4.6\"},\"effort\":{\"level\":\"high\"},\"context_window\":{\"used_percentage\":43},\"cost\":{\"total_duration_ms\":1620000,\"total_lines_added\":312,\"total_lines_removed\":47},\"rate_limits\":{\"five_hour\":{\"used_percentage\":72,\"resets_at\":$SOON},\"seven_day\":{\"used_percentage\":91,\"resets_at\":$LATER}},\"prompt_cache\":{\"caching_observed\":true,\"warm\":true,\"ttl\":\"1h\",\"expires_at\":$WARM,\"hit_ratio\":0.91,\"misses\":2}}"
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
