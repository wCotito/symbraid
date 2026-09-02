[CmdletBinding()]
param(
    [switch]$SkipExtension,
    [switch]$SkipCodexPlugin,
    [switch]$SkipDependencies,
    [switch]$ReplaceLegacyExtension,
    [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'

if ($SkipDependencies) {
    Write-Warning '-SkipDependencies is retained for compatibility; uv/pipx manage the Symbraid project environment.'
}

$arguments = @()
if ($SkipExtension) { $arguments += '-SkipExtension' }
if ($SkipCodexPlugin) { $arguments += '-SkipCodexPlugin' }
if ($ReplaceLegacyExtension) { $arguments += '-ReplaceLegacyExtension' }
if ($NonInteractive) { $arguments += '-NonInteractive' }

& (Join-Path $PSScriptRoot 'install.ps1') @arguments
if ($LASTEXITCODE -ne 0) {
    throw "install.ps1 failed with exit code $LASTEXITCODE."
}
