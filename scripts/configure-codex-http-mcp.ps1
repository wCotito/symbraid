[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('Configure', 'Status', 'Remove')]
    [string]$Action = 'Configure',
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]*$')]
    [string]$TokenEnvironmentVariable = 'SYMBRAID_CODEX_MCP_TOKEN',
    [string]$CodexHome,
    [string]$StateDirectory,
    [string[]]$PluginId = @(),
    [switch]$InstallStartupTask,
    [switch]$NoStart,
    [switch]$RemoveManagedToken
)

$ErrorActionPreference = 'Stop'
$script:StartMarker = '# BEGIN SYMBRAID MANAGED HTTP MCP'
$script:EndMarker = '# END SYMBRAID MANAGED HTTP MCP'
$script:LegacyStartMarker = '# BEGIN SYMBRAID CODEX HTTP MCP'
$script:LegacyEndMarker = '# END SYMBRAID CODEX HTTP MCP'
$script:McpServerId = 'io.github.wcotito/symbraid'
$script:TaskName = 'Symbraid Codex HTTP MCP'
$script:ExpectedTools = @('semantic_search', 'index_status', 'list_index_sources')

function Throw-UsageError {
    param([Parameter(Mandatory)][string]$Message)
    throw $Message
}

function Get-FullPath {
    param([Parameter(Mandatory)][string]$Path)
    if (-not [IO.Path]::IsPathRooted($Path)) {
        Throw-UsageError "Path must be absolute: $Path"
    }
    return [IO.Path]::GetFullPath($Path)
}

function Resolve-CodexHomePath {
    $explicit = -not [string]::IsNullOrWhiteSpace($CodexHome)
    if ($explicit) {
        return Get-FullPath $CodexHome
    }

    $candidate = [Environment]::GetEnvironmentVariable('CODEX_HOME', 'Process')
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $candidate = [Environment]::GetEnvironmentVariable('CODEX_HOME', 'User')
    }
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $profile = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
        if ([string]::IsNullOrWhiteSpace($profile)) {
            Throw-UsageError 'The Windows user profile directory could not be resolved. Pass -CodexHome explicitly.'
        }
        $candidate = Join-Path $profile '.codex'
    }

    $resolved = Get-FullPath $candidate
    if ($resolved -match '(?i)(^|[\\/])CodexSandbox[^\\/]*([\\/]|$)') {
        Throw-UsageError "Refusing to use a sandbox shadow profile: $resolved. Run this script from an external PowerShell or pass the real Codex directory with -CodexHome."
    }

    $profileFromApi = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $profileFromEnv = [Environment]::GetEnvironmentVariable('USERPROFILE', 'Process')
    if (-not [string]::IsNullOrWhiteSpace($profileFromEnv) -and -not [string]::IsNullOrWhiteSpace($profileFromApi)) {
        if ((Get-FullPath $profileFromEnv) -ine (Get-FullPath $profileFromApi)) {
            Throw-UsageError 'USERPROFILE and the Windows profile API resolve to different locations. Pass the intended Codex directory with -CodexHome.'
        }
    }
    return $resolved
}

function Get-Paths {
    param([Parameter(Mandatory)][string]$CodexRoot)
    $localAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        $localAppData = [Environment]::GetEnvironmentVariable('LOCALAPPDATA', 'Process')
    }
    if ([string]::IsNullOrWhiteSpace($localAppData)) {
        Throw-UsageError 'The Windows local application data directory could not be resolved.'
    }
    if (-not [string]::IsNullOrWhiteSpace($StateDirectory)) {
        $stateDirectory = Get-FullPath $StateDirectory
    } else {
        $stateDirectory = Join-Path (Get-FullPath $localAppData) 'Symbraid'
    }
    return [pscustomobject]@{
        Home = $CodexRoot
        Config = Join-Path $CodexRoot 'config.toml'
        StateDirectory = $stateDirectory
        State = Join-Path $stateDirectory 'codex-http-mcp.json'
        LogDirectory = Join-Path $stateDirectory 'logs'
        Stdout = Join-Path $stateDirectory 'logs\codex-http-mcp.stdout.log'
        Stderr = Join-Path $stateDirectory 'logs\codex-http-mcp.stderr.log'
    }
}

function Read-TextFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject]@{ Text = ''; Encoding = (New-Object Text.UTF8Encoding($false)); Exists = $false }
    }
    $bytes = [IO.File]::ReadAllBytes($Path)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    $encoding = New-Object Text.UTF8Encoding($hasBom)
    return [pscustomobject]@{
        Text = [IO.File]::ReadAllText($Path, $encoding)
        Encoding = $encoding
        Exists = $true
    }
}

function Write-AtomicText {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Text,
        [Parameter(Mandatory)][Text.Encoding]$Encoding
    )
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText($temporary, $Text, $Encoding)
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
    }
}

function Write-AtomicJson {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)]$Value)
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $text = $Value | ConvertTo-Json -Depth 8
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText($temporary, $text, (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-ManagedBlockInfo {
    param([Parameter(Mandatory)][string]$Text)
    $pairs = @(
        [pscustomobject]@{ Start = $script:StartMarker; End = $script:EndMarker },
        [pscustomobject]@{ Start = $script:LegacyStartMarker; End = $script:LegacyEndMarker }
    )
    $found = @()
    foreach ($pair in $pairs) {
        $startPattern = '(?m)^' + [regex]::Escape($pair.Start) + '\r?$'
        $endPattern = '(?m)^' + [regex]::Escape($pair.End) + '\r?$'
        $starts = [regex]::Matches($Text, $startPattern).Count
        $ends = [regex]::Matches($Text, $endPattern).Count
        if ($starts -ne $ends -or $starts -gt 1) {
            Throw-UsageError "Managed Symbraid block markers are incomplete or duplicated for '$($pair.Start)'."
        }
        if ($starts -eq 1) {
            $pattern = '(?ms)^' + [regex]::Escape($pair.Start) + '\r?\n.*?^' + [regex]::Escape($pair.End) + '\r?\n?'
            $match = [regex]::Match($Text, $pattern)
            if (-not $match.Success) {
                Throw-UsageError 'Managed Symbraid block markers are malformed.'
            }
            $found += [pscustomobject]@{ Match = $match; Legacy = ($pair.Start -eq $script:LegacyStartMarker) }
        }
    }
    if ($found.Count -gt 1) {
        Throw-UsageError 'Both current and legacy Symbraid managed blocks are present. Remove one manually before retrying.'
    }
    if ($found.Count -eq 0) {
        return [pscustomobject]@{ Text = $Text; Exists = $false; Legacy = $false }
    }
    $match = $found[0].Match
    return [pscustomobject]@{
        Text = $Text.Remove($match.Index, $match.Length)
        Exists = $true
        Legacy = $found[0].Legacy
    }
}

function Get-PluginIdsFromConfig {
    param([Parameter(Mandatory)][string]$Text)
    $ids = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $pattern = '(?m)^\[plugins\."(?<id>[^"]+)"(?:\.[^\r\n]*)?\]\s*$'
    foreach ($match in [regex]::Matches($Text, $pattern)) {
        $id = $match.Groups['id'].Value
        if ($id -like 'symbraid-search@*' -or $id -like 'hybrid-code-search@*') {
            [void]$ids.Add($id)
        }
    }
    foreach ($id in $PluginId) {
        if (-not [string]::IsNullOrWhiteSpace($id)) {
            [void]$ids.Add($id)
        }
    }
    return @($ids | Sort-Object)
}

function Escape-TomlString {
    param([Parameter(Mandatory)][string]$Value)
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

function Get-ManagedBlock {
    param(
        [Parameter(Mandatory)][string]$ConfigText,
        [Parameter(Mandatory)][int]$TargetPort,
        [Parameter(Mandatory)][string]$TokenName,
        [string[]]$PluginIds
    )
    $newline = if ($ConfigText.Contains("`r`n")) { "`r`n" } else { "`n" }
    $withoutBlock = Get-ManagedBlockInfo $ConfigText
    $outside = $withoutBlock.Text
    $serverHeader = '[mcp_servers."' + $script:McpServerId + '"]'
    $serverConflict = '(?m)^\[mcp_servers\."' + [regex]::Escape($script:McpServerId) + '"\]\s*$'
    if ([regex]::IsMatch($outside, $serverConflict)) {
        Throw-UsageError "A standalone MCP server table for '$script:McpServerId' exists outside the managed block. Remove or reconcile it manually."
    }

    $lines = @($script:StartMarker)
    foreach ($id in $PluginIds) {
        $safeId = Escape-TomlString $id
        $pluginHeader = '[plugins."' + $safeId + '".mcp_servers."' + $script:McpServerId + '"]'
        if ([regex]::IsMatch($outside, '(?m)^\[plugins\."' + [regex]::Escape($id) + '"\.mcp_servers\."' + [regex]::Escape($script:McpServerId) + '"\]\s*$')) {
            Throw-UsageError "A plugin MCP override for '$id' exists outside the managed block. Remove or reconcile it manually."
        }
        $lines += $pluginHeader
        $lines += 'enabled = false'
        $lines += ''
    }
    $endpoint = "http://127.0.0.1:$TargetPort/mcp"
    $lines += $serverHeader
    $lines += 'url = "' + $endpoint + '"'
    $lines += 'bearer_token_env_var = "' + (Escape-TomlString $TokenName) + '"'
    $lines += 'enabled_tools = ["semantic_search", "index_status", "list_index_sources"]'
    $lines += 'startup_timeout_sec = 20'
    $lines += 'tool_timeout_sec = 120'
    $lines += $script:EndMarker
    $block = ($lines -join $newline) + $newline
    if ([string]::IsNullOrEmpty($outside)) {
        $updated = $block
    } elseif ($outside.EndsWith($newline + $newline)) {
        $updated = $outside + $block
    } elseif ($outside.EndsWith($newline)) {
        $updated = $outside + $newline + $block
    } else {
        $updated = $outside + $newline + $newline + $block
    }
    return [pscustomobject]@{
        Original = $ConfigText
        Updated = $updated
        ExistingBlock = $withoutBlock.Exists
        LegacyBlock = $withoutBlock.Legacy
        PluginIds = $PluginIds
        Endpoint = $endpoint
    }
}

function Get-SymbraidExecutable {
    $command = Get-Command symbraid -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        Throw-UsageError 'The symbraid executable was not found on PATH. Install the current core with scripts\install.ps1, then retry.'
    }
    return $command.Source
}

function Assert-SymbraidRuntime {
    param([Parameter(Mandatory)][string]$Executable)
    $versionOutput = (& $Executable '--version' 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        Throw-UsageError "Unable to execute '$Executable --version'."
    }
    $helpOutput = (& $Executable 'mcp' '--help' 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or
        $helpOutput -notmatch 'streamable-http' -or
        $helpOutput -notmatch '--allow-all-projects' -or
        $helpOutput -notmatch '--auth-token-env') {
        Throw-UsageError "The installed Symbraid runtime is too old for global HTTP MCP. Install the current core with scripts\install.ps1, then retry."
    }
    return $versionOutput.Trim()
}

function Get-State {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json }
    catch { return $null }
}

function Test-TcpPort {
    param([Parameter(Mandatory)][int]$TargetPort)
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $TargetPort)
        if (-not $task.Wait(300)) { return $false }
        return $client.Connected
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Get-McpPayload {
    param([Parameter(Mandatory)][string]$Body)
    $trimmed = $Body.Trim()
    if ($trimmed.StartsWith('{')) {
        return $trimmed | ConvertFrom-Json
    }
    foreach ($line in ($Body -split "`r?`n")) {
        if ($line -match '^data:\s*(\{.*\})\s*$') {
            try { return $Matches[1] | ConvertFrom-Json } catch { }
        }
    }
    return $null
}

function Invoke-McpRequest {
    param(
        [Parameter(Mandatory)][Net.Http.HttpClient]$Client,
        [Parameter(Mandatory)][string]$Endpoint,
        [Parameter(Mandatory)][string]$Token,
        [Parameter(Mandatory)]$Payload,
        [string]$SessionId
    )
    $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, $Endpoint)
    try {
        $request.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Token)
        $request.Headers.Accept.ParseAdd('application/json')
        $request.Headers.Accept.ParseAdd('text/event-stream')
        if (-not [string]::IsNullOrWhiteSpace($SessionId)) {
            $request.Headers.Add('Mcp-Session-Id', $SessionId)
        }
        $json = $Payload | ConvertTo-Json -Depth 10 -Compress
        $request.Content = [Net.Http.StringContent]::new($json, [Text.Encoding]::UTF8, 'application/json')
        $response = $Client.SendAsync($request).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $session = $null
        try { $session = ($response.Headers.GetValues('Mcp-Session-Id') | Select-Object -First 1) } catch { }
        return [pscustomobject]@{
            Success = $response.IsSuccessStatusCode
            Status = [int]$response.StatusCode
            Body = $body
            SessionId = $session
        }
    }
    finally { $request.Dispose() }
}

function Test-McpHealth {
    param([Parameter(Mandatory)][string]$Endpoint, [Parameter(Mandatory)][string]$Token)
    Add-Type -AssemblyName System.Net.Http
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(5)
    try {
        $initialize = Invoke-McpRequest $client $Endpoint $Token @{
            jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{
                protocolVersion = '2025-06-18'; capabilities = @{}; clientInfo = @{ name = 'symbraid-configure'; version = '1' }
            }
        }
        if (-not $initialize.Success) { throw "initialize returned HTTP $($initialize.Status)" }
        $session = $initialize.SessionId
        $initialized = Invoke-McpRequest $client $Endpoint $Token @{ jsonrpc = '2.0'; method = 'notifications/initialized'; params = @{} } $session
        if (-not $initialized.Success -and $initialized.Status -notin @(200, 202, 204)) { throw "initialized notification returned HTTP $($initialized.Status)" }
        $toolsResponse = Invoke-McpRequest $client $Endpoint $Token @{ jsonrpc = '2.0'; id = 2; method = 'tools/list'; params = @{} } $session
        if (-not $toolsResponse.Success) { throw "tools/list returned HTTP $($toolsResponse.Status)" }
        $payload = Get-McpPayload $toolsResponse.Body
        $names = @($payload.result.tools | ForEach-Object { $_.name })
        $missing = @($script:ExpectedTools | Where-Object { $_ -notin $names })
        if ($missing.Count -gt 0) { throw "MCP tools are missing: $($missing -join ', ')" }
        return [pscustomobject]@{ Healthy = $true; Tools = $names; SessionId = $session }
    }
    finally { $client.Dispose(); $handler.Dispose() }
}

function Wait-McpHealth {
    param([Parameter(Mandatory)][string]$Endpoint, [Parameter(Mandatory)][string]$Token, [int]$TimeoutSeconds = 20)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try { return Test-McpHealth $Endpoint $Token }
        catch { $lastError = $_.Exception.Message; Start-Sleep -Milliseconds 250 }
    }
    throw "Symbraid MCP did not become healthy within $TimeoutSeconds seconds. Last error: $lastError"
}

function Get-ProcessForState {
    param([Parameter(Mandatory)]$State, [Parameter(Mandatory)][string]$Executable)
    if ($null -eq $State -or [int]$State.manual_process_id -le 0) { return $null }
    $process = Get-Process -Id ([int]$State.manual_process_id) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    try {
        if (-not [string]::IsNullOrWhiteSpace($process.Path) -and
            (Get-FullPath $process.Path) -ine (Get-FullPath $Executable)) { return $null }
    } catch { }
    return $process
}

function Get-ManagedTask {
    param([Parameter(Mandatory)][string]$Executable)
    $task = Get-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) { return $null }
    $arguments = (($task.Actions | ForEach-Object { $_.Arguments }) -join ' ')
    $leaf = [regex]::Escape((Split-Path -Leaf $Executable))
    if ($arguments -notmatch '--allow-all-projects' -or $arguments -notmatch $leaf -or $arguments -notmatch '--transport\s+streamable-http') {
        return [pscustomobject]@{ Foreign = $true; Task = $task }
    }
    return [pscustomobject]@{ Foreign = $false; Task = $task }
}

function New-ManagedTask {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][int]$TargetPort,
        [Parameter(Mandatory)][string]$TokenName
    )
    $powershell = (Get-Command powershell.exe -CommandType Application -ErrorAction Stop).Source
    $safeExecutable = $Executable.Replace("'", "''")
    $safeToken = $TokenName.Replace("'", "''")
    $command = "& { `$env:$TokenName = [Environment]::GetEnvironmentVariable('$safeToken','User'); & '$safeExecutable' mcp --transport streamable-http --allow-all-projects --host 127.0.0.1 --port $TargetPort --auth-token-env $TokenName; exit `$LASTEXITCODE }"
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + $command.Replace('"', '\"') + '"'
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    return [pscustomobject]@{ Action = $action; Trigger = $trigger; Settings = $settings; Arguments = $arguments }
}

function Stop-ManagedProcess {
    param([Parameter(Mandatory)]$Process, [Parameter(Mandatory)][string]$Endpoint)
    if ($null -eq $Process) { return $false }
    if ($PSCmdlet.ShouldProcess("PID $($Process.Id)", 'Stop managed Symbraid MCP process')) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
    return $true
}

if ($Action -ne 'Configure' -and ($InstallStartupTask -or $NoStart)) {
    Throw-UsageError '-InstallStartupTask and -NoStart are valid only with -Action Configure.'
}
if ($Action -ne 'Remove' -and $RemoveManagedToken) {
    Throw-UsageError '-RemoveManagedToken is valid only with -Action Remove.'
}

$codexHomePath = Resolve-CodexHomePath
$paths = Get-Paths $codexHomePath
$endpoint = "http://127.0.0.1:$Port/mcp"
$state = Get-State $paths.State

if ($Action -eq 'Status') {
    $config = Read-TextFile $paths.Config
    $block = Get-ManagedBlockInfo $config.Text
    $configured = $block.Exists
    $configuredEndpoint = $null
    if ($configured -and $config.Text -match '(?m)^url\s*=\s*"(?<url>http://127\.0\.0\.1:\d+/mcp)"') { $configuredEndpoint = $Matches['url'] }
    $tokenName = if ($state -and $state.token_environment_variable) { [string]$state.token_environment_variable } else { $TokenEnvironmentVariable }
    $tokenPresent = -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($tokenName, 'Process')) -or -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($tokenName, 'User'))
    $healthy = $false
    $health = $null
    if ($configured -and $tokenPresent -and $configuredEndpoint) {
        $token = [Environment]::GetEnvironmentVariable($tokenName, 'Process')
        if ([string]::IsNullOrWhiteSpace($token)) { $token = [Environment]::GetEnvironmentVariable($tokenName, 'User') }
        try { $health = Test-McpHealth $configuredEndpoint $token; $healthy = $true } catch { }
    }
    $taskPresent = $false
    try { $taskPresent = $null -ne (Get-ScheduledTask -TaskName $script:TaskName -ErrorAction SilentlyContinue) } catch { }
    $status = if ($healthy) { 'healthy' } elseif ($configured) { 'configured but stopped' } else { 'not configured' }
    [pscustomobject]@{
        status = $status
        codex_home = $codexHomePath
        config_path = $paths.Config
        endpoint = $configuredEndpoint
        token_environment_variable = $tokenName
        token_present = $tokenPresent
        managed_block_present = $configured
        startup_task_name = $script:TaskName
        startup_task_present = $taskPresent
        process_id = if ($state) { $state.manual_process_id } else { $null }
        tools = if ($health) { $health.Tools } else { @() }
    } | ConvertTo-Json -Depth 6
    exit 0
}

if ($Action -eq 'Remove') {
    $config = Read-TextFile $paths.Config
    $block = Get-ManagedBlockInfo $config.Text
    if ($block.Exists -and $PSCmdlet.ShouldProcess($paths.Config, 'Remove Symbraid managed HTTP MCP block')) {
        Write-AtomicText $paths.Config $block.Text $config.Encoding
    }

    $runtime = Get-Command symbraid -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $executable = if ($runtime) { $runtime.Source } else { $null }
    if ($state -and $executable) {
        $process = Get-ProcessForState $state $executable
        if ($process) { [void](Stop-ManagedProcess $process $endpoint) }
    }
    $taskInfo = if ($executable) { Get-ManagedTask $executable } else { $null }
    if ($taskInfo -and $taskInfo.Foreign) {
        Throw-UsageError "Scheduled Task '$script:TaskName' exists but is not a managed Symbraid task; refusing to remove it."
    }
    if ($taskInfo -and $PSCmdlet.ShouldProcess($script:TaskName, 'Remove managed logon task')) {
        Unregister-ScheduledTask -TaskName $script:TaskName -Confirm:$false
    }

    if ($RemoveManagedToken -and $state -and [bool]$state.token_managed) {
        $name = [string]$state.token_environment_variable
        if ($PSCmdlet.ShouldProcess("user environment variable $name", 'Remove managed bearer token')) {
            [Environment]::SetEnvironmentVariable($name, $null, 'User')
            [Environment]::SetEnvironmentVariable($name, $null, 'Process')
        }
    }
    if (Test-Path -LiteralPath $paths.State) {
        if ($PSCmdlet.ShouldProcess($paths.State, 'Remove Symbraid MCP state')) {
            Remove-Item -LiteralPath $paths.State -Force
        }
    }
    [pscustomobject]@{ status = 'removed'; config_path = $paths.Config; task = $script:TaskName } | ConvertTo-Json
    exit 0
}

$executable = Get-SymbraidExecutable
$version = Assert-SymbraidRuntime $executable
$config = Read-TextFile $paths.Config
$pluginIds = @(Get-PluginIdsFromConfig $config.Text)
$block = Get-ManagedBlock $config.Text $Port $TokenEnvironmentVariable $pluginIds

$token = [Environment]::GetEnvironmentVariable($TokenEnvironmentVariable, 'Process')
$tokenManaged = $false
if ([string]::IsNullOrWhiteSpace($token)) {
    $token = [Environment]::GetEnvironmentVariable($TokenEnvironmentVariable, 'User')
}
if ([string]::IsNullOrWhiteSpace($token)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $token = ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    $tokenManaged = $true
    if ($PSCmdlet.ShouldProcess("user environment variable $TokenEnvironmentVariable", 'Create bearer token')) {
        [Environment]::SetEnvironmentVariable($TokenEnvironmentVariable, $token, 'User')
        [Environment]::SetEnvironmentVariable($TokenEnvironmentVariable, $token, 'Process')
    }
} else {
    [Environment]::SetEnvironmentVariable($TokenEnvironmentVariable, $token, 'Process')
}

if ($WhatIfPreference) {
    [pscustomobject]@{
        status = 'what-if'
        runtime = $version
        config_path = $paths.Config
        endpoint = $endpoint
        plugin_ids = $pluginIds
        startup_task = [bool]$InstallStartupTask
        start_server = -not [bool]$NoStart
    } | ConvertTo-Json -Depth 6
    exit 0
}

$startedProcess = $null
$configChanged = $false
$taskChanged = $false
$oldConfigExists = $config.Exists
$oldConfigText = $config.Text
try {
    if (-not $NoStart -and -not $InstallStartupTask) {
        $alreadyHealthy = $false
        try {
            if (Test-TcpPort $Port) {
                $existingToken = $token
                $health = Test-McpHealth $endpoint $existingToken
                $alreadyHealthy = $true
            }
        } catch { }
        if (-not $alreadyHealthy) {
            if (Test-TcpPort $Port) {
                Throw-UsageError "TCP port $Port is already in use by an unrecognized process. Choose another -Port."
            }
            New-Item -ItemType Directory -Path $paths.LogDirectory -Force | Out-Null
            $arguments = @('mcp', '--transport', 'streamable-http', '--allow-all-projects', '--host', '127.0.0.1', '--port', "$Port", '--auth-token-env', $TokenEnvironmentVariable)
            if ($PSCmdlet.ShouldProcess($endpoint, 'Start external Symbraid MCP server')) {
                $startedProcess = Start-Process -FilePath $executable -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput $paths.Stdout -RedirectStandardError $paths.Stderr -PassThru
                try { [void](Wait-McpHealth $endpoint $token 20) } catch { if ($startedProcess -and -not $startedProcess.HasExited) { Stop-Process -Id $startedProcess.Id -Force -ErrorAction SilentlyContinue }; throw }
            }
        }
    }

    if ($block.Updated -ne $block.Original -and $PSCmdlet.ShouldProcess($paths.Config, 'Configure global Streamable HTTP MCP')) {
        Write-AtomicText $paths.Config $block.Updated $config.Encoding
        $configChanged = $true
    }

    if ($InstallStartupTask) {
        $taskInfo = Get-ManagedTask $executable
        if ($taskInfo -and $taskInfo.Foreign) {
            Throw-UsageError "Scheduled Task '$script:TaskName' exists but is not a managed Symbraid task; refusing to replace it."
        }
        $task = New-ManagedTask $executable $Port $TokenEnvironmentVariable
        if ($PSCmdlet.ShouldProcess($script:TaskName, 'Register per-user Symbraid MCP logon task')) {
            Register-ScheduledTask -TaskName $script:TaskName -Action $task.Action -Trigger $task.Trigger -Settings $task.Settings -Force | Out-Null
            $taskChanged = $true
            if (-not $NoStart) {
                $running = $false
                try { [void](Test-McpHealth $endpoint $token); $running = $true } catch { }
                if (-not $running) {
                    Start-ScheduledTask -TaskName $script:TaskName
                    [void](Wait-McpHealth $endpoint $token 20)
                }
            }
        }
    }

    $stateValue = [ordered]@{
        schema_version = 1
        codex_home = $codexHomePath
        config_path = $paths.Config
        endpoint = $endpoint
        port = $Port
        token_environment_variable = $TokenEnvironmentVariable
        token_managed = $tokenManaged
        symbraid_executable = $executable
        plugin_ids = $pluginIds
        managed_block_version = 1
        startup_task_name = if ($InstallStartupTask) { $script:TaskName } else { $null }
        manual_process_id = if ($startedProcess) { $startedProcess.Id } else { $null }
        updated_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    Write-AtomicJson $paths.State $stateValue
    [pscustomobject]@{
        status = if ($NoStart) { 'configured, not running' } else { 'ok' }
        runtime = $version
        endpoint = $endpoint
        codex_home = $codexHomePath
        serves_all_registered_projects = $true
        startup_task_installed = [bool]$InstallStartupTask
        process_id = if ($startedProcess) { $startedProcess.Id } else { $null }
        authenticated_handshake = if ($NoStart) { $false } else { $true }
        restart_codex_required = $true
    } | ConvertTo-Json -Depth 6
}
catch {
    if ($configChanged) {
        if ($oldConfigExists) { Write-AtomicText $paths.Config $oldConfigText $config.Encoding }
        elseif (Test-Path -LiteralPath $paths.Config) { Remove-Item -LiteralPath $paths.Config -Force -ErrorAction SilentlyContinue }
    }
    if ($taskChanged) {
        Unregister-ScheduledTask -TaskName $script:TaskName -Confirm:$false -ErrorAction SilentlyContinue
    }
    if ($startedProcess -and -not $startedProcess.HasExited) {
        Stop-Process -Id $startedProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw
}
