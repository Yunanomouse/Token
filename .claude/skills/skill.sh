#!/usr/bin/env bash
# Resolve a Taste Skill install name to its vendored SKILL.md path.
#
#   ./.claude/skills/skill.sh                       # list install names
#   ./.claude/skills/skill.sh design-taste-frontend # print the path
#   cat "$(./.claude/skills/skill.sh brandkit)"     # read one
#
# Upstream ships this keyed to its own folder names. Here the folders are named
# by each skill's install name, so the mapping is the identity and the script
# just validates and resolves.

set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mapfile -t skills < <(
  find "$dir" -mindepth 2 -maxdepth 2 -name SKILL.md -printf '%h\n' | xargs -r -n1 basename | sort
)

if [[ $# -eq 0 ]]; then
  printf 'Available skills (%d):\n' "${#skills[@]}"
  printf '  %s\n' "${skills[@]}"
  exit 0
fi

target="$dir/$1/SKILL.md"
if [[ ! -f "$target" ]]; then
  printf 'Unknown skill: %s\n\nAvailable:\n' "$1" >&2
  printf '  %s\n' "${skills[@]}" >&2
  exit 1
fi
printf '%s\n' "$target"
