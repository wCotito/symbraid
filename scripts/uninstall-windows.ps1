[CmdletBinding()]
param(
    [switch]$RemoveData,
    [switch]$RemoveMarketplace
)

$ErrorActionPreference = 'Stop'

$arguments = @()
if ($RemoveData) { $arguments += '-RemoveData' }
if ($RemoveMarketplace) { $arguments += '-RemoveMarketplace' }

& (Join-Path $PSScriptRoot 'uninstall.ps1') @arguments
if ($LASTEXITCODE -ne 0) {
    throw "uninstall.ps1 failed with exit code $LASTEXITCODE."
}
