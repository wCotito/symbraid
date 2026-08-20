[CmdletBinding()]
param(
    [switch]$SkipExtension,
    [switch]$SkipCodexPlugin,
    [switch]$SkipDependencies
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$componentRoot = Join-Path $repoRoot 'components\code-index'
$extensionRoot = Join-Path $repoRoot 'extensions\vscode-code-index'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'CodeIndex'
$appRoot = Join-Path $runtimeRoot 'app'
$venvRoot = Join-Path $runtimeRoot 'runtime\.venv'
$binRoot = Join-Path $runtimeRoot 'bin'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3.10+ was not found in PATH.'
}
$pythonVersion = [version](& python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))")
if ($pythonVersion -lt [version]'3.10') {
    throw "Python 3.10 or newer is required; found $pythonVersion."
}

New-Item -ItemType Directory -Force -Path $runtimeRoot, $binRoot | Out-Null
$stage = Join-Path $runtimeRoot ('app.stage-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
    Copy-Item -Recurse -Force (Join-Path $componentRoot 'code_index') $stage
    Copy-Item -Recurse -Force (Join-Path $componentRoot 'scripts') $stage
    Copy-Item -Force (Join-Path $componentRoot 'mcp_gateway.py'), (Join-Path $componentRoot 'requirements.txt'), (Join-Path $repoRoot 'LICENSE') $stage

    if (Test-Path -LiteralPath $appRoot) {
        $backup = Join-Path $runtimeRoot 'app.previous'
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
        Move-Item -LiteralPath $appRoot -Destination $backup
    }
    Move-Item -LiteralPath $stage -Destination $appRoot
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}

if (-not (Test-Path (Join-Path $venvRoot 'Scripts\python.exe'))) {
    & python -m venv $venvRoot
}
if (-not $SkipDependencies) {
    & (Join-Path $venvRoot 'Scripts\python.exe') -m pip install --disable-pip-version-check -r (Join-Path $appRoot 'requirements.txt')
}

$cliLauncher = "@echo off`r`n`"$venvRoot\Scripts\python.exe`" `"$appRoot\scripts\code_index_cli.py`" %*`r`n"
$mcpLauncher = "@echo off`r`n`"$venvRoot\Scripts\python.exe`" `"$appRoot\mcp_gateway.py`"`r`n"
Set-Content -Encoding Ascii -Path (Join-Path $binRoot 'code-index.cmd') -Value $cliLauncher
Set-Content -Encoding Ascii -Path (Join-Path $binRoot 'code-index-mcp.cmd') -Value $mcpLauncher

if (-not $SkipExtension) {
    foreach ($command in 'npm.cmd', 'npx.cmd', 'code.cmd') {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "$command was not found. Install Node.js and VS Code or use -SkipExtension."
        }
    }
    Push-Location $extensionRoot
    try {
        & npm.cmd ci --ignore-scripts
        & npm.cmd test
        $vsix = Join-Path $runtimeRoot 'ada-b.code-index-0.1.0.vsix'
        & npx.cmd vsce package --no-dependencies --allow-missing-repository -o $vsix
        & code.cmd --install-extension $vsix --force
    } finally { Pop-Location }
}

if (-not $SkipCodexPlugin) {
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        throw 'Codex CLI was not found. Install Codex or use -SkipCodexPlugin.'
    }
    $marketplaces = (& codex plugin marketplace list | Out-String)
    if ($marketplaces -notmatch [regex]::Escape($repoRoot)) {
        & codex plugin marketplace add $repoRoot
    }
    & codex plugin add hybrid-code-search@semantic-code-index-kit
}

& (Join-Path $binRoot 'code-index.cmd') defaults show
Write-Host "Code Index was installed to $runtimeRoot"
Write-Host 'Open a new Codex session and reload the VS Code window.'
