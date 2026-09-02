[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$RemoveData,
    [switch]$RemoveMarketplace
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

if (Test-CommandAvailable 'uv') {
    $uvTools = (& uv tool list | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "uv tool list failed with exit code $LASTEXITCODE."
    }
    if ($uvTools -match '(?im)^\s*symbraid(?:\s|$)') {
        Invoke-Checked 'uv' @('tool', 'uninstall', 'symbraid')
    }
}
if (Test-CommandAvailable 'pipx') {
    $pipxTools = (& pipx list | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "pipx list failed with exit code $LASTEXITCODE."
    }
    if ($pipxTools -match '(?im)^\s*package\s+symbraid\b') {
        Invoke-Checked 'pipx' @('uninstall', 'symbraid')
    }
}

if (Test-CommandAvailable 'code.cmd') {
    $installedExtensions = (& code.cmd --list-extensions | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "code.cmd --list-extensions failed with exit code $LASTEXITCODE."
    }
    if ($installedExtensions -match '(?im)^\s*symbraid\.symbraid(?:@|$)') {
        Invoke-Checked 'code.cmd' @('--uninstall-extension', 'symbraid.symbraid')
    }
}

if (Test-CommandAvailable 'codex') {
    $plugins = (& codex plugin list | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "codex plugin list failed with exit code $LASTEXITCODE."
    }
    foreach ($plugin in @('symbraid-search@semantic-code-index-kit', 'hybrid-code-search@semantic-code-index-kit')) {
        if ($plugins -match [regex]::Escape($plugin)) {
            Invoke-Checked 'codex' @('plugin', 'remove', $plugin)
        }
    }
    if ($RemoveMarketplace) {
        $marketplaces = (& codex plugin marketplace list | Out-String)
        if ($LASTEXITCODE -ne 0) {
            throw "codex plugin marketplace list failed with exit code $LASTEXITCODE."
        }
        if ($marketplaces -match '(?im)semantic-code-index-kit') {
            Invoke-Checked 'codex' @('plugin', 'marketplace', 'remove', 'semantic-code-index-kit')
        }
    }
}

if ($RemoveData) {
    $overrideConfigured = -not [string]::IsNullOrWhiteSpace($env:SYMBRAID_HOME)
    if (-not $overrideConfigured) {
        $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
        if ([string]::IsNullOrWhiteSpace($localAppData)) {
            throw 'The Windows local application data directory could not be resolved.'
        }
        $symbraidRoot = [IO.Path]::GetFullPath((Join-Path $localAppData 'Symbraid'))
    } else {
        $symbraidRoot = [IO.Path]::GetFullPath($env:SYMBRAID_HOME)
    }

    $trimmedRoot = $symbraidRoot.TrimEnd('\', '/')
    $pathRoot = [IO.Path]::GetPathRoot($symbraidRoot)
    $userHome = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    if ([string]::IsNullOrWhiteSpace($trimmedRoot) -or
        $symbraidRoot -ieq $pathRoot -or
        (-not [string]::IsNullOrWhiteSpace($userHome) -and $symbraidRoot -ieq ([IO.Path]::GetFullPath($userHome)))) {
        throw "Unsafe Symbraid data removal path: $symbraidRoot"
    }

    $leaf = [IO.Path]::GetFileName($trimmedRoot)
    if ($leaf -ine 'Symbraid') {
        throw "Unexpected Symbraid data directory: $symbraidRoot"
    }
    if (Test-Path -LiteralPath $symbraidRoot) {
        $item = Get-Item -LiteralPath $symbraidRoot -Force
        if (-not $item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Refusing to remove a non-directory or link: $symbraidRoot"
        }
        if ($PSCmdlet.ShouldProcess($symbraidRoot, 'Remove Symbraid configuration, data, cache, and state')) {
            Remove-Item -LiteralPath $symbraidRoot -Recurse -Force
        }
    }
}

Write-Host 'Symbraid uninstall completed.'
