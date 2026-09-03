[CmdletBinding()]
param(
    [switch]$SkipExtension,
    [switch]$SkipCodexPlugin
)

$ErrorActionPreference = 'Stop'

$arguments = @()
if ($SkipExtension) { $arguments += '-SkipExtension' }
if ($SkipCodexPlugin) { $arguments += '-SkipCodexPlugin' }

& (Join-Path $PSScriptRoot 'install.ps1') @arguments
if ($LASTEXITCODE -ne 0) {
    throw "install.ps1 failed with exit code $LASTEXITCODE."
}
