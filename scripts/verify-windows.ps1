$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = Join-Path $env:LOCALAPPDATA 'CodeIndex\runtime\.venv\Scripts\python.exe'
$componentRoot = Join-Path $repoRoot 'components\code-index'
$extensionRoot = Join-Path $repoRoot 'extensions\vscode-code-index'

if (-not (Test-Path $runtimePython)) { throw 'Runtime is not installed. Run install-windows.ps1 first.' }
Push-Location $componentRoot
try { & $runtimePython -m unittest discover -s tests -v } finally { Pop-Location }
Push-Location $extensionRoot
try { & npm.cmd test; & node --check extension.js } finally { Pop-Location }
& $runtimePython "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" (Join-Path $repoRoot 'plugins\hybrid-code-search\skills\hybrid-code-search')
& $runtimePython "$env:USERPROFILE\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py" (Join-Path $repoRoot 'plugins\hybrid-code-search')
& $runtimePython (Join-Path $repoRoot 'scripts\check_docs.py')
& $runtimePython (Join-Path $repoRoot 'scripts\verify_mcp.py')
Write-Host 'All available checks passed.'
