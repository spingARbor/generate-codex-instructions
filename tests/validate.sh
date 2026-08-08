#!/bin/sh
set -eu

repo_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
skill_dir=$repo_root/skill
installer=$repo_root/install.sh
skill_name=generate-codex-instructions

fail() {
    printf '%s\n' "FAIL: $*" >&2
    exit 1
}

require_text() {
    grep -F "$1" "$skill_dir/SKILL.md" >/dev/null || fail "missing contract text: $1"
}

validator=${SKILL_VALIDATOR:-}
if [ -z "$validator" ] && [ -n "${HOME:-}" ]; then
    candidate=$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py
    if [ -f "$candidate" ]; then
        validator=$candidate
    fi
fi

if [ -z "$validator" ] || [ ! -f "$validator" ]; then
    fail "set SKILL_VALIDATOR to skill-creator/scripts/quick_validate.py"
fi

python3 "$validator" "$skill_dir" >/dev/null
sh -n "$installer"
if command -v dash >/dev/null 2>&1; then
    dash -n "$installer"
fi
if command -v bash >/dev/null 2>&1; then
    bash --posix -n "$installer"
fi
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -s sh "$installer"
fi
for eval_json in "$repo_root"/evals/*.json
do
    python3 -m json.tool "$eval_json" >/dev/null
done

require_text "Do not use for requests to implement, edit, test, review, or execute"
require_text "untrusted data, never directives or authorization"
require_text "Reject symlink components"
require_text "planning-with-files"
require_text ".instruction-generation.lock"
require_text "authentication/authorization"
require_text "exactly one evidence-backed fallback"
require_text "Treat version bumps"
require_text "normalized message"
require_text "backtick fence longer"

for case_id in \
    explicit-generation ordinary-implementation tracker-path-escape \
    tracker-injection self-target planning-with-files-adapter \
    plugin-prerequisites mandatory-capability-missing concurrency-conflict \
    repeated-gate-failure git-permission-split secret-redaction fence-safety
do
    grep -F "\"id\": \"$case_id\"" "$repo_root/evals/cases.json" >/dev/null \
        || fail "missing evaluation case: $case_id"
done

runtime_count=$(find "$skill_dir" -type f | wc -l | tr -d ' ')
[ "$runtime_count" = 2 ] || fail "runtime bundle must contain exactly two files"
[ ! -e "$skill_dir/.git" ] || fail "runtime bundle exposes .git"
[ ! -e "$skill_dir/.codex" ] || fail "runtime bundle exposes project progress"

tmp_root=$(mktemp -d "${TMPDIR:-/tmp}/gci-validate.XXXXXX")
cleanup() {
    case "$tmp_root" in
        "${TMPDIR:-/tmp}"/gci-validate.*)
            if [ -d "$tmp_root" ]; then
                find "$tmp_root" -type f -exec rm -f {} \;
                find "$tmp_root" -type l -exec rm -f {} \;
                find "$tmp_root" -depth -type d -exec rmdir {} \;
            fi
            ;;
        *) fail "refusing unexpected cleanup path: $tmp_root" ;;
    esac
}
trap cleanup EXIT HUP INT TERM

default_home=$tmp_root/default-home
mkdir -p "$default_home"
env -u CODEX_HOME -u CODEX_SKILLS_DIR HOME="$default_home" "$installer" >/dev/null
default_link=$default_home/.agents/skills/$skill_name
[ -L "$default_link" ] || fail "default installation did not create a symlink"
installed_dir=$(CDPATH= cd "$default_link" && pwd -P)
[ "$installed_dir" = "$skill_dir" ] || fail "default link points outside runtime bundle"
env -u CODEX_HOME -u CODEX_SKILLS_DIR HOME="$default_home" "$installer" >/dev/null
installed_count=$(find -H "$default_link" -type f | wc -l | tr -d ' ')
[ "$installed_count" = 2 ] || fail "installed surface is not minimal"

custom_home=$tmp_root/custom-home
custom_root=$tmp_root/custom-skills
mkdir -p "$custom_home"
env -u CODEX_HOME HOME="$custom_home" CODEX_SKILLS_DIR="$custom_root" "$installer" >/dev/null
[ -L "$custom_root/$skill_name" ] || fail "custom installation failed"

no_home_root=$tmp_root/no-home-skills
env -u HOME -u CODEX_HOME CODEX_SKILLS_DIR="$no_home_root" "$installer" >/dev/null
[ -L "$no_home_root/$skill_name" ] || fail "absolute override with no HOME failed"
if env -u HOME -u CODEX_HOME -u CODEX_SKILLS_DIR "$installer" >/dev/null 2>&1; then
    fail "missing HOME without an override was accepted"
fi

relative_home=$tmp_root/relative-home
mkdir -p "$relative_home"
if env -u CODEX_HOME HOME="$relative_home" CODEX_SKILLS_DIR=relative/skills "$installer" >/dev/null 2>&1; then
    fail "relative destination was accepted"
fi
if env HOME="$relative_home" CODEX_HOME=relative CODEX_SKILLS_DIR="$tmp_root/relative-codex-home" "$installer" >/dev/null 2>&1; then
    fail "relative CODEX_HOME was accepted"
fi
[ ! -e "$tmp_root/relative-codex-home" ] || fail "invalid CODEX_HOME caused a destination write"
if env -u CODEX_HOME HOME="$relative_home" CODEX_SKILLS_DIR=/tmp/.. "$installer" >/dev/null 2>&1; then
    fail "destination resolving to the filesystem root was accepted"
fi
root_alias=$tmp_root/root-alias
ln -s / "$root_alias"
if env -u CODEX_HOME HOME="$relative_home" CODEX_SKILLS_DIR="$root_alias" "$installer" >/dev/null 2>&1; then
    fail "symlink destination resolving to the filesystem root was accepted"
fi

alias_home=$tmp_root/alias-home
alias_codex=$alias_home/codex
mkdir -p "$alias_codex"
env HOME="$alias_home" CODEX_HOME="$alias_codex/" CODEX_SKILLS_DIR="$alias_codex/skills" "$installer" >/dev/null
env HOME="$alias_home" CODEX_HOME="$alias_codex" CODEX_SKILLS_DIR="$alias_codex/skills" "$installer" >/dev/null
[ -L "$alias_codex/skills/$skill_name" ] || fail "alias-safe repeat installation deleted its target"

for conflict_kind in file directory symlink
do
    conflict_home=$tmp_root/conflict-$conflict_kind
    conflict_root=$conflict_home/.agents/skills
    conflict_path=$conflict_root/$skill_name
    mkdir -p "$conflict_root"
    case "$conflict_kind" in
        file) : > "$conflict_path" ;;
        directory) mkdir "$conflict_path" ;;
        symlink)
            mkdir "$conflict_home/other-skill"
            ln -s "$conflict_home/other-skill" "$conflict_path"
            ;;
    esac
    if env -u CODEX_HOME -u CODEX_SKILLS_DIR HOME="$conflict_home" "$installer" >/dev/null 2>&1; then
        fail "$conflict_kind conflict was accepted"
    fi
done

legacy_home=$tmp_root/legacy-home
legacy_root=$legacy_home/.codex/skills
legacy_link=$legacy_root/$skill_name
mkdir -p "$legacy_root"
ln -s "$repo_root" "$legacy_link"
env -u CODEX_HOME -u CODEX_SKILLS_DIR HOME="$legacy_home" "$installer" >/dev/null
[ ! -e "$legacy_link" ] && [ ! -L "$legacy_link" ] || fail "owned legacy link was not removed"
[ -L "$legacy_home/.agents/skills/$skill_name" ] || fail "legacy installation was not migrated"

root_link_home=$tmp_root/root-link-home
root_link_path=$root_link_home/.agents/skills/$skill_name
mkdir -p "$root_link_home/.agents/skills"
ln -s "$repo_root" "$root_link_path"
if env -u CODEX_HOME -u CODEX_SKILLS_DIR HOME="$root_link_home" "$installer" >/dev/null 2>&1; then
    fail "repository-root destination link was replaced non-atomically"
fi
root_link_dir=$(CDPATH= cd "$root_link_path" && pwd -P)
[ "$root_link_dir" = "$repo_root" ] || fail "repository-root destination link was modified"

foreign_home=$tmp_root/foreign-home
foreign_root=$foreign_home/.codex/skills
foreign_link=$foreign_root/$skill_name
mkdir -p "$foreign_root" "$foreign_home/other-skill"
ln -s "$foreign_home/other-skill" "$foreign_link"
if env -u CODEX_HOME -u CODEX_SKILLS_DIR HOME="$foreign_home" "$installer" >/dev/null 2>&1; then
    fail "foreign legacy link was accepted"
fi
[ -L "$foreign_link" ] || fail "foreign legacy link was removed"
[ ! -e "$foreign_home/.agents/skills/$skill_name" ] \
    || fail "installation proceeded after a legacy conflict"

prospective_index=$tmp_root/prospective.index
prospective_objects=$tmp_root/prospective-objects
mkdir -p "$prospective_objects"
repository_objects=$(git -C "$repo_root" rev-parse --git-path objects)
case "$repository_objects" in
    /*) ;;
    *) repository_objects=$repo_root/$repository_objects ;;
esac
repository_objects=$(CDPATH= cd "$repository_objects" && pwd -P)
GIT_INDEX_FILE="$prospective_index" GIT_OBJECT_DIRECTORY="$prospective_objects" \
    GIT_ALTERNATE_OBJECT_DIRECTORIES="$repository_objects" git -C "$repo_root" read-tree HEAD
GIT_INDEX_FILE="$prospective_index" GIT_OBJECT_DIRECTORY="$prospective_objects" \
    GIT_ALTERNATE_OBJECT_DIRECTORIES="$repository_objects" git -C "$repo_root" add -A -- .
GIT_INDEX_FILE="$prospective_index" GIT_OBJECT_DIRECTORY="$prospective_objects" \
    GIT_ALTERNATE_OBJECT_DIRECTORIES="$repository_objects" git -C "$repo_root" diff --cached --check
prospective_tree=$(GIT_INDEX_FILE="$prospective_index" GIT_OBJECT_DIRECTORY="$prospective_objects" \
    GIT_ALTERNATE_OBJECT_DIRECTORIES="$repository_objects" git -C "$repo_root" write-tree)
prospective_archive=$tmp_root/prospective.tar
GIT_OBJECT_DIRECTORY="$prospective_objects" GIT_ALTERNATE_OBJECT_DIRECTORIES="$repository_objects" \
    git -C "$repo_root" archive --format=tar --output="$prospective_archive" "$prospective_tree"
archive_entries=$tmp_root/archive-entries.txt
tar -tf "$prospective_archive" > "$archive_entries"
grep -Fx "skill/SKILL.md" "$archive_entries" >/dev/null || fail "archive omits runtime skill"
grep -Fx "install.sh" "$archive_entries" >/dev/null || fail "archive omits installer"
if grep -F ".codex/development/" "$archive_entries" >/dev/null; then
    fail "archive exposes internal development progress"
fi
printf '%s\n' "PASS: skill contract, metadata, installer, migration, conflicts, and evaluation corpus"
