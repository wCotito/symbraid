#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: uninstall.sh [options]

Remove the user-scoped Symbraid CLI, VS Code extension, and Codex integrations.
Configuration, indexes, caches, and state are retained unless --remove-data is
explicitly supplied.

Options:
  --remove-data         Remove only the exact Symbraid data directories.
  --remove-marketplace  Remove the repository Codex marketplace registration.
  -h, --help            Show this help.
EOF
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

remove_data=0
remove_marketplace=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove-data) remove_data=1 ;;
        --remove-marketplace) remove_marketplace=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

if [[ "$(id -u)" -eq 0 ]]; then
    die 'Do not run the uninstaller as root.'
fi

if command -v uv >/dev/null 2>&1; then
    uv_tools="$(uv tool list)"
    if printf '%s\n' "$uv_tools" | grep -Eiq '^[[:space:]]*symbraid([[:space:]]|$)'; then
        uv tool uninstall symbraid
    fi
fi
if command -v pipx >/dev/null 2>&1; then
    pipx_tools="$(pipx list)"
    if printf '%s\n' "$pipx_tools" | grep -Eiq '^[[:space:]]*package[[:space:]]+symbraid([[:space:]]|$)'; then
        pipx uninstall symbraid
    fi
fi

code_bin="$(command -v code || command -v code.cmd || true)"
if [[ -n "$code_bin" ]]; then
    installed_extensions="$("$code_bin" --list-extensions)"
    if printf '%s\n' "$installed_extensions" | grep -Eiq '^[[:space:]]*symbraid[.]symbraid([[:space:]]|$)'; then
        "$code_bin" --uninstall-extension symbraid.symbraid
    fi
fi

codex_bin="$(command -v codex || true)"
if [[ -n "$codex_bin" ]]; then
    plugins="$("$codex_bin" plugin list)"
    for plugin in symbraid-search@semantic-code-index-kit hybrid-code-search@semantic-code-index-kit; do
        if printf '%s\n' "$plugins" | grep -Fqi "$plugin"; then
            "$codex_bin" plugin remove "$plugin"
        fi
    done
    if [[ "$remove_marketplace" -eq 1 ]]; then
        marketplaces="$("$codex_bin" plugin marketplace list)"
        if printf '%s\n' "$marketplaces" | grep -Fqi semantic-code-index-kit; then
            "$codex_bin" plugin marketplace remove semantic-code-index-kit
        fi
    fi
fi

absolute_path() {
    local value="$1"
    if command -v realpath >/dev/null 2>&1; then
        realpath -m -- "$value"
    elif [[ "$value" == /* ]]; then
        printf '%s\n' "$value"
    else
        printf '%s/%s\n' "$PWD" "$value"
    fi
}

assert_safe_data_path() {
    local target="$1"
    [[ "$target" == /* && "$target" != "/" && "$target" != "$HOME" ]] ||
        die "Refusing unsafe data path: $target"
    [[ "$(basename -- "$target")" == "symbraid" ]] ||
        die "Refusing data path without the exact Symbraid leaf: $target"
    if [[ -e "$target" || -L "$target" ]]; then
        [[ -d "$target" && ! -L "$target" ]] ||
            die "Refusing to remove a non-directory or link: $target"
    fi
}

remove_exact_directory() {
    local target="$1"
    if [[ -e "$target" ]]; then
        rm -rf -- "$target"
    fi
}

if [[ "$remove_data" -eq 1 ]]; then
    symbraid_home="$(printenv SYMBRAID_HOME || true)"
    if [[ -n "$symbraid_home" ]]; then
        [[ ! -L "$symbraid_home" ]] || die 'Refusing a symlink SYMBRAID_HOME.'
        override_root="$(absolute_path "$symbraid_home")"
        assert_safe_data_path "$override_root"
        remove_exact_directory "$override_root"
    else
        xdg_config_home="$(printenv XDG_CONFIG_HOME || true)"
        xdg_data_home="$(printenv XDG_DATA_HOME || true)"
        xdg_cache_home="$(printenv XDG_CACHE_HOME || true)"
        xdg_state_home="$(printenv XDG_STATE_HOME || true)"
        [[ -n "$xdg_config_home" ]] || xdg_config_home="$HOME/.config"
        [[ -n "$xdg_data_home" ]] || xdg_data_home="$HOME/.local/share"
        [[ -n "$xdg_cache_home" ]] || xdg_cache_home="$HOME/.cache"
        [[ -n "$xdg_state_home" ]] || xdg_state_home="$HOME/.local/state"
        config_base="$(absolute_path "$xdg_config_home")"
        data_base="$(absolute_path "$xdg_data_home")"
        cache_base="$(absolute_path "$xdg_cache_home")"
        state_base="$(absolute_path "$xdg_state_home")"
        for base in "$config_base" "$data_base" "$cache_base" "$state_base"; do
            assert_safe_data_path "$base/symbraid"
            remove_exact_directory "$base/symbraid"
        done
    fi
fi

printf '%s\n' 'Symbraid uninstall completed.'
