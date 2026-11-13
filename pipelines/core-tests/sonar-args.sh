#!/usr/bin/env bash
set -euo pipefail
ui_modules="com.smf.userinterface.skin.legacy org.openbravo.client.widgets org.openbravo.client.htmlwidget com.smf.smartclient.debugtools org.openbravo.client.myob org.openbravo.userinterface.smartclient com.smf.smartclient.boostedui com.etendoerp.client.application"
exclusions=""
for m in $ui_modules; do exclusions="${exclusions:+$exclusions,}modules_core/$m/**"; done
deprecated=$(grep -rl --include=*.java -A1 '@Deprecated' src modules_core 2>/dev/null | while read -r f; do
  if grep -A1 '@Deprecated' "$f" | grep -q 'public class'; then echo "$f"; fi
done | paste -sd, -)
[ -n "$deprecated" ] && exclusions="$exclusions,$deprecated"
coverage=$(cat pipelines/unittests/coverage-exclusions.txt pipelines/core-tests/coverage-exclusions-unused.txt | sed 's/[[:space:]]*$//' | grep -v '^#' | grep -v '^$' | paste -sd, -)
sources=$(find modules_core -type d -name src -path 'modules_core/*/src' | sort | paste -sd, -)
sources="${sources:+$sources,}src"
if [ -n "${PR_NUMBER:-}" ]; then
  branch_args="-Dsonar.pullrequest.key=$PR_NUMBER -Dsonar.pullrequest.branch=$PR_HEAD -Dsonar.pullrequest.base=$PR_BASE"
else
  branch_args="-Dsonar.branch.name=$GITHUB_REF_NAME"
fi
echo "sources=$sources"
echo "exclusions=$exclusions"
echo "coverage_exclusions=$coverage"
echo "branch_args=$branch_args"
