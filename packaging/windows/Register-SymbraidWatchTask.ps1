[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Project,
    [string]$TaskName = 'Symbraid Watch',
    [string]$Executable = 'symbraid',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$resolvedProject = Resolve-Path -LiteralPath $Project -ErrorAction Stop
$projectItem = Get-Item -LiteralPath $resolvedProject.Path -Force
if (-not $projectItem.PSIsContainer) {
    throw "The project path must be a directory: $Project"
}
$projectPath = [IO.Path]::GetFullPath($projectItem.FullName)

$executableCommand = Get-Command -Name $Executable -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $executableCommand) {
    throw "The Symbraid executable was not found in PATH: $Executable"
}
$executablePath = [IO.Path]::GetFullPath($executableCommand.Source)
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "The resolved Symbraid executable is not a file: $executablePath"
}

# This script is opt-in: registering a task is performed only by this explicit invocation.
$escapedProject = $projectPath.Replace('"', '\"')
$action = New-ScheduledTaskAction -Execute $executablePath -Argument ('watch "{0}"' -f $escapedProject) -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (-not $Force -and $null -ne (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "A task named '$TaskName' already exists. Use -Force only when replacement is intentional."
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description ('Symbraid watcher for ' + $projectPath) -Force:$Force | Out-Null

Write-Host "Registered user task '$TaskName' for $projectPath."
Write-Host ('Remove it explicitly with: Unregister-ScheduledTask -TaskName ''{0}'' -Confirm:$false' -f $TaskName)
