[CmdletBinding()]
param(
    [switch]$SkipExtension,
    [switch]$SkipMcp
)

$ErrorActionPreference = 'Stop'

$arguments = @()
if ($SkipExtension) { $arguments += '-SkipExtension' }
if ($SkipMcp) { $arguments += '-SkipMcp' }

& (Join-Path $PSScriptRoot 'verify.ps1') @arguments
if ($LASTEXITCODE -ne 0) {
    throw "verify.ps1 failed with exit code $LASTEXITCODE."
}
