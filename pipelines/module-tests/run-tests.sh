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
    [ -n "$(find "$d/src-test" \( -name '*.java' -o -name '*.groovy' \) -print -quit)" ] || continue
    args+=(--tests "${m}.*")
  done
fi

if [ "${#args[@]}" -eq 0 ]; then
  echo "::error::No hay módulos con tests para el grupo $group"
  exit 1
fi

excluded_file="$(dirname "$0")/excluded-tests.txt"
init_script="$(mktemp --suffix=.gradle)"
{
  echo 'allprojects { tasks.withType(Test).configureEach { filter {'
  echo '  failOnNoMatchingTests = false'
  if [ -f "$excluded_file" ]; then
    cut -f1 "$excluded_file" | grep -v '^[[:space:]]*$' | while read -r pattern; do
      echo "  excludeTestsMatching '${pattern}'"
    done
  fi
  echo '} } }'
} > "$init_script"
cat "$init_script"

printf '%s\n' "${args[@]}" | grep -v -- '--tests'
./gradlew test "${args[@]}" -I "$init_script" --continue
status=$?

mkdir -p results
[ -d build/test-results/test ] && cp -r build/test-results/test results/xml
[ -d build/reports/tests/test ] && cp -r build/reports/tests/test results/html
[ -d build/spock-reports ] && cp -r build/spock-reports results/spock
exit "$status"
