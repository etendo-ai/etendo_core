#!/usr/bin/env bash
# Runs the stress suites in order against STRESS_BASE and leaves one CSV per suite in STRESS_OUT.
#
#   STRESS_SUITES  comma-separated subset of: read,write,confirm,onboarding,master,journey
#                  (default: all of them)
#   STRESS_OUT     results directory (default ./stress-results)
#
# Each suite's own output goes to $STRESS_OUT/logs/<suite>.log and only its exit status is printed:
# the measurements go to Datadog (report_datadog.py), not to a log anyone can read.
# The write suites leave confirmed orders and onboarded clients behind: run it on a throwaway
# environment only.
set -uo pipefail
cd "$(dirname "$0")"

export STRESS_OUT="${STRESS_OUT:-$PWD/stress-results}"
SUITES=",${STRESS_SUITES:-read,write,confirm,onboarding,master,journey},"
LOGS="$STRESS_OUT/logs"
EMAIL_FILE="$STRESS_OUT/onboarded-email"
mkdir -p "$LOGS"
FAILED=0

run() {  # $1 = suite name, rest = command
  local name=$1; shift
  local t0=$SECONDS
  if "$@" >"$LOGS/$name.log" 2>&1; then
    echo "$name: ok ($((SECONDS - t0)) s)"
  else
    echo "$name: failed with exit $? ($((SECONDS - t0)) s)"
    FAILED=1
  fi
}
wants() { [[ "$SUITES" == *",$1,"* ]]; }

# Warm the JVM up first; its numbers are thrown away.
run warmup env STRESS_OUT="$STRESS_OUT/warmup" STRESS_LEVELS=1,5 python3 read_load.py

wants read && run read python3 read_load.py
wants write && run write python3 write_load.py
wants confirm && run confirm python3 confirm_load.py
if wants onboarding || wants master; then
  run onboarding-seq env OB_MODE=seq OB_N=3 OB_EMAIL_FILE="$EMAIL_FILE" python3 onboarding_load.py
fi
if wants master; then
  if [ -s "$EMAIL_FILE" ]; then
    run master env STRESS_EMAIL="$(cat "$EMAIL_FILE")" STRESS_PASSWORD="${OB_PASSWORD:-Onboard!Test2026}" \
      python3 master_data_load.py
  else
    echo "master: skipped, no onboarded account"
    FAILED=1
  fi
fi
wants journey && run journey python3 journey_load.py
wants onboarding && run onboarding-conc env OB_MODE=conc OB_N=3 python3 onboarding_load.py

rm -f "$EMAIL_FILE"
exit $FAILED
