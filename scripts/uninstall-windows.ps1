[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$RemoveData,
    [switch]$RemoveMarketplace
)

$ErrorActionPreference = 'Stop'
$runtimeRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CodeIndex'))

if (Get-Command code.cmd -ErrorAction SilentlyContinue) {
    & code.cmd --uninstall-extension ada-b.code-index
}
if (Get-Command codex -ErrorAction SilentlyContinue) {
    & codex plugin remove hybrid-code-search@semantic-code-index-kit
    if ($RemoveMarketplace) {
        & codex plugin marketplace remove semantic-code-index-kit
    }
}
if ($RemoveData -and $PSCmdlet.ShouldProcess($runtimeRoot, 'Remove Code Index runtime, configuration, models, and indexes')) {
    $expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'CodeIndex'))
    if ($runtimeRoot -ne $expected) { throw "Unsafe removal path: $runtimeRoot" }
    if (Test-Path -LiteralPath $runtimeRoot) { Remove-Item -LiteralPath $runtimeRoot -Recurse -Force }
}
