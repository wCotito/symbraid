#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: verify.sh [options]

Run the Symbraid component, plugin, optional extension, and MCP checks.

Options:
  --skip-extension   Do not check the VS Code extension.
  --skip-mcp         Do not launch the MCP stdio handshake.
  -h, --help         Show this help.
EOF
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

skip_extension=0
skip_mcp=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-extension) skip_extension=1 ;;
        --skip-mcp) skip_mcp=1 ;;
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

if command -v symbraid >/dev/null 2>&1; then
    symbraid --help
elif command -v uv >/dev/null 2>&1; then
    uv tool run --from "$component_root" symbraid --help
else
    die 'Symbraid is not installed and uv is unavailable. Run install.sh first.'
fi

command -v uv >/dev/null 2>&1 || die 'uv is required to run the editable Symbraid component tests.'
(
    cd -- "$component_root"
    uv run --project "$component_root" python -m unittest discover -s tests -v
)

python_bin="$(command -v python3 || command -v python || true)"
[[ -n "$python_bin" ]] || die 'Python is required to validate the plugin manifests and skills.'
plugin_validator="$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py"
skill_validator="$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py"
[[ -f "$plugin_validator" ]] || die "Plugin validator was not found: $plugin_validator"
[[ -f "$skill_validator" ]] || die "Skill validator was not found: $skill_validator"

run_plugin_validator() {
    local plugin_path="$1"
    if "$python_bin" -c 'import yaml' >/dev/null 2>&1; then
        "$python_bin" "$plugin_validator" "$plugin_path"
    else
        uv run --with PyYAML --with jsonschema --python 3.10 python "$plugin_validator" "$plugin_path"
    fi
}

run_skill_validator() {
    local skill_path="$1"
    if "$python_bin" -c 'import yaml' >/dev/null 2>&1; then
        "$python_bin" "$skill_validator" "$skill_path"
    else
        uv run --with PyYAML --python 3.10 python "$skill_validator" "$skill_path"
    fi
}

run_plugin_validator "$repo_root/plugins/symbraid-search"
run_plugin_validator "$repo_root/plugins/hybrid-code-search"
run_skill_validator "$repo_root/plugins/symbraid-search/skills/symbraid-search"
run_skill_validator "$repo_root/plugins/hybrid-code-search/skills/hybrid-code-search"

if [[ "$skip_extension" -eq 0 ]]; then
    npm_bin="$(command -v npm || true)"
    node_bin="$(command -v node || true)"
    code_bin="$(command -v code || command -v code.cmd || true)"
    [[ -n "$npm_bin" && -n "$node_bin" && -n "$code_bin" ]] ||
        die 'npm, node, and code are required for extension checks; use --skip-extension to omit them.'
    (
        cd -- "$extension_root"
        "$npm_bin" test
        "$node_bin" --check extension.js
        "$node_bin" --check executable.js
        "$node_bin" --check managePanel.js
        "$node_bin" --check media/manage.js
        "$node_bin" -e "const p=require('./package.json'); if (p.name !== 'symbraid' || p.publisher !== 'symbraid' || p.version !== '0.3.0') process.exit(1)"
    )
    installed_extensions="$("$code_bin" --list-extensions --show-versions)"
    printf '%s\n' "$installed_extensions" | grep -Eiq '(^|[[:space:]])symbraid[.]symbraid(@|$)' ||
        die 'The Symbraid VS Code extension is not installed.'
fi

if [[ "$skip_mcp" -eq 0 ]]; then
    uv run --project "$component_root" python "$repo_root/scripts/verify_mcp.py"
fi

printf '%s\n' 'Symbraid verification completed.'
