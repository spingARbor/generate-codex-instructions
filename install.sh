#!/bin/sh
set -eu

skill_name=generate-codex-instructions
script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
skill_dir="$script_dir/skill"

if [ "${1:-}" = "--help" ]; then
    printf '%s\n' "Usage: ./install.sh"
    printf '%s\n' "Install $skill_name into CODEX_SKILLS_DIR or \$HOME/.agents/skills."
    printf '%s\n' "A legacy \$CODEX_HOME/skills link owned by this repository is migrated safely."
    exit 0
fi

if [ "$#" -ne 0 ]; then
    printf '%s\n' "error: unsupported argument: $1" >&2
    exit 2
fi

runtime_bundle_error() {
    printf '%s\n' "error: runtime skill bundle violates the exact physical entry contract in $skill_dir: $1" >&2
    exit 1
}

validate_runtime_bundle() {
    runtime_root=$1
    runtime_owner=$(id -u)

    [ -d "$runtime_root" ] && [ ! -L "$runtime_root" ] \
        || runtime_bundle_error "root must be a physical directory"
    unexpected_root=$(find "$runtime_root" -mindepth 1 -maxdepth 1 \
        ! -name SKILL.md ! -name agents ! -name scripts -exec printf x \;)
    [ -z "$unexpected_root" ] || runtime_bundle_error "unexpected root entry"
    [ -d "$runtime_root/agents" ] && [ ! -L "$runtime_root/agents" ] \
        || runtime_bundle_error "agents must be a physical directory"
    unexpected_agents=$(find "$runtime_root/agents" -mindepth 1 -maxdepth 1 \
        ! -name openai.yaml -exec printf x \;)
    [ -z "$unexpected_agents" ] || runtime_bundle_error "unexpected agents entry"
    [ -d "$runtime_root/scripts" ] && [ ! -L "$runtime_root/scripts" ] \
        || runtime_bundle_error "scripts must be a physical directory"
    unexpected_scripts=$(find "$runtime_root/scripts" -mindepth 1 -maxdepth 1 \
        ! -name status_fingerprint.py -exec printf x \;)
    [ -z "$unexpected_scripts" ] || runtime_bundle_error "unexpected scripts entry"

    for runtime_file in \
        "$runtime_root/SKILL.md" "$runtime_root/agents/openai.yaml" \
        "$runtime_root/scripts/status_fingerprint.py"
    do
        [ -f "$runtime_file" ] && [ ! -L "$runtime_file" ] \
            || runtime_bundle_error "expected entry must be a regular file"
        single_link=$(find "$runtime_file" -prune -type f -links 1 -exec printf x \;)
        [ "$single_link" = x ] || runtime_bundle_error "runtime file must have one hard link"
    done

    for runtime_entry in \
        "$runtime_root" "$runtime_root/agents" "$runtime_root/scripts" \
        "$runtime_root/SKILL.md" "$runtime_root/agents/openai.yaml" \
        "$runtime_root/scripts/status_fingerprint.py"
    do
        owned=$(find "$runtime_entry" -prune -user "$runtime_owner" -exec printf x \;)
        [ "$owned" = x ] || runtime_bundle_error "runtime entry must be owned by $runtime_owner"
    done
}

validate_runtime_bundle "$skill_dir"
skill_dir=$(CDPATH= cd "$skill_dir" && pwd -P)

normalize_absolute() {
    normalized_path=$1
    path_label=$2
    case "$normalized_path" in
        /*) ;;
        *)
            printf '%s\n' "error: $path_label must be an absolute path: $normalized_path" >&2
            exit 1
            ;;
    esac
    while [ "$normalized_path" != / ] && [ "${normalized_path%/}" != "$normalized_path" ]; do
        normalized_path=${normalized_path%/}
    done
    case "$normalized_path" in
        *//*|*/./*|*/../*|*/.|*/..)
            printf '%s\n' "error: $path_label must not contain empty, '.' or '..' components: $normalized_path" >&2
            exit 1
            ;;
    esac
}

resolve_without_writing() {
    unresolved_path=$1
    unresolved_suffix=
    while [ ! -d "$unresolved_path" ]; do
        unresolved_component=${unresolved_path##*/}
        unresolved_parent=${unresolved_path%/*}
        if [ -z "$unresolved_component" ] || [ "$unresolved_parent" = "$unresolved_path" ]; then
            printf '%s\n' "error: cannot resolve path safely: $1" >&2
            exit 1
        fi
        if [ -z "$unresolved_parent" ]; then
            unresolved_parent=/
        fi
        unresolved_suffix=/$unresolved_component$unresolved_suffix
        unresolved_path=$unresolved_parent
    done
    resolved_path=$(CDPATH= cd "$unresolved_path" && pwd -P)$unresolved_suffix
}

if [ "${CODEX_SKILLS_DIR+x}" = x ]; then
    destination_root=$CODEX_SKILLS_DIR
else
    if [ -z "${HOME:-}" ]; then
        printf '%s\n' "error: HOME must be set when CODEX_SKILLS_DIR is not provided" >&2
        exit 1
    fi
    destination_root=$HOME/.agents/skills
fi
normalize_absolute "$destination_root" "skill destination"
destination_root=$normalized_path

legacy_root=
if [ "${CODEX_HOME+x}" = x ]; then
    normalize_absolute "$CODEX_HOME" "CODEX_HOME"
    legacy_root=$normalized_path/skills
elif [ -n "${HOME:-}" ]; then
    case "$HOME" in
        /*) legacy_root=$HOME/.codex/skills ;;
    esac
fi

resolve_without_writing "$destination_root"
destination_root=$resolved_path
if [ "$destination_root" = / ]; then
    printf '%s\n' "error: refusing a destination that resolves to the filesystem root" >&2
    exit 1
fi
mkdir -p "$destination_root"
destination_root=$(CDPATH= cd "$destination_root" && pwd -P)
destination="$destination_root/$skill_name"

legacy_destination=
if [ -n "$legacy_root" ]; then
    resolve_without_writing "$legacy_root"
    legacy_destination=$resolved_path/$skill_name
fi

legacy_owned=false
if [ -n "$legacy_destination" ] && [ "$legacy_destination" != "$destination" ]; then
    if [ -L "$legacy_destination" ]; then
        legacy_dir=$(CDPATH= cd "$legacy_destination" 2>/dev/null && pwd -P || true)
        if [ "$legacy_dir" = "$script_dir" ] || [ "$legacy_dir" = "$skill_dir" ]; then
            legacy_owned=true
        else
            printf '%s\n' "error: legacy path $legacy_destination is a symlink to a different skill" >&2
            exit 1
        fi
    elif [ -e "$legacy_destination" ]; then
        printf '%s\n' "error: legacy path $legacy_destination already exists and is not owned by this installer" >&2
        exit 1
    fi
fi

already_installed=false
if [ -L "$destination" ]; then
    installed_dir=$(CDPATH= cd "$destination" 2>/dev/null && pwd -P || true)
    if [ "$installed_dir" = "$skill_dir" ]; then
        already_installed=true
    elif [ "$installed_dir" = "$script_dir" ]; then
        printf '%s\n' "error: $destination exposes the repository root; remove it explicitly, then rerun" >&2
        exit 1
    else
        printf '%s\n' "error: $destination is a symlink to a different skill" >&2
        exit 1
    fi
elif [ -e "$destination" ]; then
    printf '%s\n' "error: $destination already exists; remove or relocate it explicitly" >&2
    exit 1
fi

if [ "$already_installed" = false ]; then
    ln -s "$skill_dir" "$destination"
fi

if [ "$legacy_owned" = true ]; then
    unlink "$legacy_destination"
    printf '%s\n' "Removed legacy link $legacy_destination"
fi

if [ "$already_installed" = true ]; then
    printf '%s\n' "$skill_name is already installed at $destination"
else
    printf '%s\n' "Installed $skill_name -> $skill_dir"
fi
printf '%s\n' "Codex will discover it on the next turn; restart Codex if needed."
