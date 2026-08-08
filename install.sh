#!/bin/sh
set -eu

skill_name=generate-codex-instructions
script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
default_codex_home=${CODEX_HOME:-"$HOME/.codex"}
destination_root=${CODEX_SKILLS_DIR:-"$default_codex_home/skills"}
destination="$destination_root/$skill_name"

if [ "${1:-}" = "--help" ]; then
    printf '%s\n' "Usage: ./install.sh"
    printf '%s\n' "Install $skill_name into CODEX_SKILLS_DIR or CODEX_HOME/skills."
    exit 0
fi

if [ "$#" -ne 0 ]; then
    printf '%s\n' "error: unsupported argument: $1" >&2
    exit 2
fi

if [ ! -f "$script_dir/SKILL.md" ]; then
    printf '%s\n' "error: SKILL.md not found in $script_dir" >&2
    exit 1
fi

mkdir -p "$destination_root"

if [ -L "$destination" ]; then
    installed_dir=$(CDPATH= cd "$destination" 2>/dev/null && pwd -P || true)
    if [ "$installed_dir" = "$script_dir" ]; then
        printf '%s\n' "$skill_name is already installed at $destination"
        exit 0
    fi
    printf '%s\n' "error: $destination is a symlink to a different skill" >&2
    exit 1
fi

if [ -e "$destination" ]; then
    printf '%s\n' "error: $destination already exists; remove or relocate it explicitly" >&2
    exit 1
fi

ln -s "$script_dir" "$destination"
printf '%s\n' "Installed $skill_name -> $script_dir"
printf '%s\n' "Codex will discover it on the next turn; restart Codex if needed."
