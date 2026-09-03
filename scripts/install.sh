#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: install.sh [options]

Install the Symbraid CLI with uv (preferred) or pipx, and optionally install
the VS Code extension and Codex plugin.

Options:
  --skip-extension     Do not build or install the VS Code extension.
  --skip-codex-plugin  Do not install the Codex plugin.
  -h, --help           Show this help.
EOF
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

if [[ "$(id -u)" -eq 0 ]]; then
    die 'Do not run the installer as root; use a user-scoped uv tool or pipx install.'
fi

skip_extension=0
skip_codex_plugin=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-extension) skip_extension=1 ;;
        --skip-codex-plugin) skip_codex_plugin=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

script_dir="$(cd -- "$(dirname -- "$0")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"
component_root="$repo_root/components/symbraid"
extension_root="$repo_root/extensions/vscode-symbraid"
[[ -f "$component_root/pyproject.toml" ]] || die "Symbraid component was not found: $component_root"

tool=''
if command -v uv >/dev/null 2>&1; then
    tool=uv
    uv tool install --editable --force "$component_root"
elif command -v pipx >/dev/null 2>&1; then
    tool=pipx
    pipx install --editable --force "$component_root"
else
    die 'Neither uv nor pipx was found. Install uv or pipx, then run this script again.'
fi
if command -v symbraid >/dev/null 2>&1; then
    symbraid --help
elif [[ "$tool" == uv ]]; then
    uv tool run --from "$component_root" symbraid --help
else
    die 'Symbraid was installed, but its executable is not on PATH. Refresh PATH and retry.'
fi

if [[ "$skip_extension" -eq 0 ]]; then
    npm_bin="$(command -v npm || true)"
    npx_bin="$(command -v npx || true)"
    node_bin="$(command -v node || true)"
    code_bin="$(command -v code || command -v code.cmd || true)"
    [[ -n "$npm_bin" && -n "$npx_bin" && -n "$node_bin" && -n "$code_bin" ]] ||
        die 'npm, npx, node, and code are required for extension installation; use --skip-extension to omit it.'
    [[ -f "$extension_root/package.json" ]] || die "Symbraid VS Code extension was not found: $extension_root"
    extension_version="$(
        cd -- "$extension_root"
        "$node_bin" -p "const p=require('./package.json'); if (p.name !== 'symbraid' || p.publisher !== 'symbraid' || p.version !== '0.3.0') process.exit(1); p.version"
    )" || die 'The VS Code extension package identity or version is not the expected Symbraid release.'
    tmp_base="$(printenv TMPDIR || true)"
    [[ -n "$tmp_base" ]] || tmp_base=/tmp
    vsix_dir="$(mktemp -d "$tmp_base/symbraid-vsix.XXXXXX")"
    vsix="$vsix_dir/symbraid-$extension_version.vsix"
    cleanup_vsix() { rm -rf -- "$vsix_dir"; }
    trap cleanup_vsix EXIT
    (
        cd -- "$extension_root"
        "$npm_bin" ci --ignore-scripts
        "$npm_bin" test
        "$node_bin" --check extension.js
        "$node_bin" --check executable.js
        "$node_bin" --check managePanel.js
        "$node_bin" --check media/manage.js
        "$npx_bin" vsce package --no-dependencies --allow-missing-repository \
            --baseContentUrl https://github.com/wCotito/symbraid/blob/main/extensions/vscode-symbraid \
            -o "$vsix"
    )
    [[ -f "$vsix" ]] || die "VSIX packaging did not produce $vsix"
    "$code_bin" --install-extension "$vsix" --force
    installed_after="$("$code_bin" --list-extensions --show-versions)"
    printf '%s\n' "$installed_after" | grep -Eiq '(^|[[:space:]])symbraid[.]symbraid(@|$)' ||
        die 'The Symbraid VS Code extension was not verified after installation.'
    trap - EXIT
    cleanup_vsix
fi

if [[ "$skip_codex_plugin" -eq 0 ]]; then
    codex_bin="$(command -v codex || true)"
    [[ -n "$codex_bin" ]] || die 'Codex CLI was not found. Install Codex or use --skip-codex-plugin.'
    marketplaces="$("$codex_bin" plugin marketplace list)" || die 'codex plugin marketplace list failed.'
    if ! printf '%s\n' "$marketplaces" | grep -Fqi "$repo_root"; then
        "$codex_bin" plugin marketplace add "$repo_root"
    fi
    "$codex_bin" plugin add symbraid-search@symbraid
fi

printf '%s\n' 'Symbraid installation completed.'
printf '%s\n' 'Start a new Codex session and reload the VS Code window to pick up the integrations.'
