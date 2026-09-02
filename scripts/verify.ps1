[CmdletBinding()]
param(
    [switch]$SkipExtension,
    [switch]$SkipMcp
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

function Invoke-PluginValidator {
    param([Parameter(Mandatory)][string]$PluginPath)
    $validator = Join-Path $env:USERPROFILE '.codex\skills\.system\plugin-creator\scripts\validate_plugin.py'
    if (-not (Test-Path -LiteralPath $validator)) {
        throw "Plugin validator was not found: $validator"
    }
    if (Test-CommandAvailable 'python') {
        & python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('yaml') else 1)"
        if ($LASTEXITCODE -eq 0) {
            Invoke-Checked 'python' @($validator, $PluginPath)
            return
        }
    }
    if (Test-CommandAvailable 'uv') {
        Invoke-Checked 'uv' @(
            'run', '--with', 'PyYAML', '--with', 'jsonschema', '--python', '3.10',
            'python', $validator, $PluginPath
        )
        return
    }
    throw 'PyYAML is unavailable. Install it in the verification environment or install uv.'
}

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$componentRoot = Join-Path $repoRoot 'components\symbraid'
$extensionRoot = Join-Path $repoRoot 'extensions\vscode-symbraid'

if (-not (Test-Path -LiteralPath (Join-Path $componentRoot 'pyproject.toml'))) {
    throw "Symbraid component was not found: $componentRoot"
}

if (Test-CommandAvailable 'symbraid') {
    Invoke-Checked 'symbraid' @('--help')
} elseif (Test-CommandAvailable 'uv') {
    Invoke-Checked 'uv' @('tool', 'run', '--from', $componentRoot, 'symbraid', '--help')
} else {
    throw 'Symbraid is not installed and uv is unavailable. Run install.ps1 first.'
}

if (Test-CommandAvailable 'uv') {
    Push-Location $componentRoot
    try {
        Invoke-Checked 'uv' @('run', '--project', $componentRoot, 'python', '-m', 'unittest', 'discover', '-s', 'tests', '-v')
    } finally {
        Pop-Location
    }
} else {
    throw 'uv is required to run Symbraid component tests.'
}

if (-not $SkipExtension) {
    foreach ($command in @('npm.cmd', 'node', 'code.cmd')) {
        if (-not (Test-CommandAvailable $command)) {
            throw "$command was not found. Use -SkipExtension to omit extension checks."
        }
    }
    Push-Location $extensionRoot
    try {
        Invoke-Checked 'npm.cmd' @('test')
        foreach ($source in @('extension.js', 'executable.js', 'managePanel.js', 'media\manage.js')) {
            Invoke-Checked 'node' @('--check', (Join-Path $extensionRoot $source))
        }
        $package = Get-Content -LiteralPath (Join-Path $extensionRoot 'package.json') -Raw | ConvertFrom-Json
        if ($package.name -ne 'symbraid' -or $package.publisher -ne 'symbraid' -or $package.version -ne '0.3.0') {
            throw 'The VS Code extension package identity or version is not the expected Symbraid release.'
        }
        $installed = (& code.cmd --list-extensions --show-versions | Out-String)
        if ($LASTEXITCODE -ne 0) {
            throw "code.cmd --list-extensions failed with exit code $LASTEXITCODE."
        }
        if ($installed -notmatch '(?im)^\s*symbraid\.symbraid(?:@|$)') {
            throw 'The Symbraid VS Code extension is not installed.'
        }
    } finally {
        Pop-Location
    }
}

Invoke-PluginValidator (Join-Path $repoRoot 'plugins\symbraid-search')
Invoke-PluginValidator (Join-Path $repoRoot 'plugins\hybrid-code-search')

$skillValidator = Join-Path $env:USERPROFILE '.codex\skills\.system\skill-creator\scripts\quick_validate.py'
if (-not (Test-Path -LiteralPath $skillValidator)) {
    throw "Skill validator was not found: $skillValidator"
}
$yamlAvailable = $false
if (Test-CommandAvailable 'python') {
    & python -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('yaml') else 1)"
    $yamlAvailable = $LASTEXITCODE -eq 0
}
if ($yamlAvailable) {
    Invoke-Checked 'python' @($skillValidator, (Join-Path $repoRoot 'plugins\symbraid-search\skills\symbraid-search'))
    Invoke-Checked 'python' @($skillValidator, (Join-Path $repoRoot 'plugins\hybrid-code-search\skills\hybrid-code-search'))
} elseif (Test-CommandAvailable 'uv') {
    Invoke-Checked 'uv' @('run', '--with', 'PyYAML', '--python', '3.10', 'python', $skillValidator, (Join-Path $repoRoot 'plugins\symbraid-search\skills\symbraid-search'))
    Invoke-Checked 'uv' @('run', '--with', 'PyYAML', '--python', '3.10', 'python', $skillValidator, (Join-Path $repoRoot 'plugins\hybrid-code-search\skills\hybrid-code-search'))
} else {
    throw 'PyYAML is unavailable. Install it in the verification environment or install uv.'
}

if (-not $SkipMcp) {
    if (-not (Test-CommandAvailable 'uv')) {
        throw 'uv is required for the MCP handshake because the Symbraid project declares the MCP dependency.'
    }
    Invoke-Checked 'uv' @('run', '--project', $componentRoot, 'python', (Join-Path $repoRoot 'scripts\verify_mcp.py'))
}

Write-Host 'Symbraid verification completed.'
