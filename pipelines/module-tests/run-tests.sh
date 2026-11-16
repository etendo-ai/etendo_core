#!/usr/bin/env bash
set -uo pipefail

group="$1"
main_module="com.etendoerp.go"
args=()

if [ "$group" = "etendo" ]; then
  args+=(--tests "${main_module}.*")
else
  for d in modules/*/; do
    m="$(basename "$d")"
    [ "$m" = "$main_module" ] && continue
    [ -d "$d/src-test" ] || continue
    find "$d/src-test" \( -name '*.java' -o -name '*.groovy' \) | grep -q . || continue
    args+=(--tests "${m}.*")
  done
fi

if [ "${#args[@]}" -eq 0 ]; then
  echo "::error::No hay módulos con tests para el grupo $group"
  exit 1
fi

printf '%s\n' "${args[@]}" | grep -v -- '--tests'
./gradlew test "${args[@]}" --continue
status=$?

mkdir -p results
[ -d build/test-results/test ] && cp -r build/test-results/test results/xml
[ -d build/reports/tests/test ] && cp -r build/reports/tests/test results/html
[ -d build/spock-reports ] && cp -r build/spock-reports results/spock
exit "$status"
