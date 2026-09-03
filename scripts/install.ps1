[CmdletBinding()]
param(
    [switch]$SkipExtension,
    [switch]$SkipCodexPlugin
)

$ErrorActionPreference = 'Stop'

function Test-CommandAvailable {
    param([Parameter(Mandatory)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$File,
        [Parameter()][object[]]$Arguments = @()
    )
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$File failed with exit code $LASTEXITCODE."
    }
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$componentRoot = Join-Path $repoRoot 'components\symbraid'
$extensionRoot = Join-Path $repoRoot 'extensions\vscode-symbraid'
if (-not (Test-Path -LiteralPath (Join-Path $componentRoot 'pyproject.toml'))) {
    throw "Symbraid component was not found: $componentRoot"
}

$tool = $null
if (Test-CommandAvailable 'uv') {
    $tool = 'uv'
    Invoke-Checked 'uv' @('tool', 'install', '--editable', '--force', $componentRoot)
} elseif (Test-CommandAvailable 'pipx') {
    $tool = 'pipx'
    Invoke-Checked 'pipx' @('install', '--editable', '--force', $componentRoot)
} else {
    throw 'Neither uv nor pipx was found. Install uv or pipx, then run this script again.'
}

if (Test-CommandAvailable 'symbraid') {
    Invoke-Checked 'symbraid' @('--help')
} elseif ($tool -eq 'uv') {
    Invoke-Checked 'uv' @('tool', 'run', '--from', $componentRoot, 'symbraid', '--help')
} else {
    throw 'Symbraid was installed, but its executable is not on PATH. Refresh PATH and retry.'
}

if (-not $SkipExtension) {
    foreach ($command in @('npm.cmd', 'npx.cmd', 'node', 'code.cmd')) {
        if (-not (Test-CommandAvailable $command)) {
            throw "$command was not found. Install Node.js and VS Code or use -SkipExtension."
        }
    }
    $packagePath = Join-Path $extensionRoot 'package.json'
    if (-not (Test-Path -LiteralPath $packagePath)) {
        throw "Symbraid VS Code extension was not found: $extensionRoot"
    }

    $vsix = Join-Path ([IO.Path]::GetTempPath()) ('symbraid-' + [guid]::NewGuid().ToString('N') + '.vsix')
    Push-Location $extensionRoot
    try {
        Invoke-Checked 'npm.cmd' @('ci', '--ignore-scripts')
        Invoke-Checked 'npm.cmd' @('test')
        foreach ($source in @('extension.js', 'executable.js', 'managePanel.js', 'media\manage.js')) {
            Invoke-Checked 'node' @('--check', (Join-Path $extensionRoot $source))
        }
        $package = Get-Content -LiteralPath $packagePath -Raw | ConvertFrom-Json
        if ($package.name -ne 'symbraid' -or $package.publisher -ne 'symbraid' -or $package.version -ne '0.3.0') {
            throw 'The VS Code extension package identity or version is not the expected Symbraid release.'
        }

        Invoke-Checked 'npx.cmd' @(
            'vsce', 'package', '--no-dependencies', '--allow-missing-repository',
            '--baseContentUrl', 'https://github.com/symbraid-project/symbraid/blob/main/extensions/vscode-symbraid',
            '-o', $vsix
        )
        if (-not (Test-Path -LiteralPath $vsix)) {
            throw "VSIX packaging did not produce $vsix"
        }

        Invoke-Checked 'code.cmd' @('--install-extension', $vsix, '--force')
        $installedAfter = (& code.cmd --list-extensions --show-versions | Out-String)
        if ($LASTEXITCODE -ne 0 -or $installedAfter -notmatch '(?im)^\s*symbraid\.symbraid(?:@|$)') {
            throw 'The Symbraid VS Code extension was not verified after installation.'
        }
    } finally {
        Pop-Location
        if (Test-Path -LiteralPath $vsix) {
            Remove-Item -LiteralPath $vsix -Force
        }
    }
}

if (-not $SkipCodexPlugin) {
    if (-not (Test-CommandAvailable 'codex')) {
        throw 'Codex CLI was not found. Install Codex or use -SkipCodexPlugin.'
    }
    $marketplaces = (& codex plugin marketplace list | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "codex plugin marketplace list failed with exit code $LASTEXITCODE."
    }
    if ($marketplaces -notmatch [regex]::Escape($repoRoot)) {
        Invoke-Checked 'codex' @('plugin', 'marketplace', 'add', $repoRoot)
    }
    Invoke-Checked 'codex' @('plugin', 'add', 'symbraid-search@symbraid')
}

Write-Host 'Symbraid installation completed.'
Write-Host 'Start a new Codex session and reload the VS Code window to pick up the integrations.'
