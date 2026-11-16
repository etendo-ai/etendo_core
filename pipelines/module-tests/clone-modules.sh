#!/usr/bin/env bash
set -euo pipefail

main_repo="${MAIN_MODULE_REPO:-https://github.com/etendo-ai/com.etendoerp.go.git}"
candidates=()
for b in "${MODULES_BRANCH:-}" epic/ETP-3504 main; do
  [ -n "$b" ] && [[ ! " ${candidates[*]} " =~ " $b " ]] && candidates+=("$b")
done

to_https() {
  local url="$1"
  if [[ "$url" =~ ^git@github\.com:(.+)$ ]]; then
    if [ -n "${GH_TOKEN:-}" ]; then
      echo "https://x-access-token:${GH_TOKEN}@github.com/${BASH_REMATCH[1]}"
    else
      echo "https://github.com/${BASH_REMATCH[1]}"
    fi
  else
    echo "$url"
  fi
}

pick_branch() {
  local url="$1"
  for b in "${candidates[@]}"; do
    if git ls-remote --exit-code --heads "$url" "$b" </dev/null >/dev/null 2>&1; then
      echo "$b"
      return 0
    fi
  done
  return 1
}

clone() {
  local url name branch
  url="$(to_https "$1")"
  name="$(basename "$1" .git)"
  if [ -n "${2:-}" ]; then
    branch="$2"
  elif ! branch="$(pick_branch "$url")"; then
    echo "::error::$name: ninguna de las ramas (${candidates[*]}) existe"
    return 1
  fi
  git clone -q --depth 1 --branch "$branch" "$url" "modules/$name" </dev/null
  printf '%s\t%s\t%s\n' "$name" "$branch" "$(git -C "modules/$name" rev-parse --short HEAD)" | tee -a modules-cloned.tsv
}

mkdir -p modules
: > modules-cloned.tsv
clone "$main_repo" "${MAIN_MODULE_BRANCH:-main}"

list="modules/com.etendoerp.go/jenkinsExtraModules.txt"
[ -f "$list" ] || { echo "::error::No existe $list"; exit 1; }

mapfile -t urls < <(tr ',' '\n' < "$list" | sed 's/[[:space:]]//g' | grep -v '^$')
echo "Módulos en $list: ${#urls[@]}"

failed=0
for url in "${urls[@]}"; do
  clone "$url" || failed=1
done

exit "$failed"
