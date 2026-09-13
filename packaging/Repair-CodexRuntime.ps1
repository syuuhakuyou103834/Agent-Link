[CmdletBinding()]
param([string]$CodexPath, [switch]$Repair)
$ErrorActionPreference = 'Stop'
$names = @('codex-windows-sandbox-setup.exe','codex-command-runner.exe','codex-code-mode-host.exe')
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $env:LOCALAPPDATA "AgentLinkGUI\diagnostics\codex-runtime-$stamp"
New-Item -ItemType Directory -Path $out -Force | Out-Null
$report = [ordered]@{schema=1; host=$env:COMPUTERNAME; repair_requested=[bool]$Repair; model_requests=0; status='checking'; files=@()}
try {
    $versionFile = Join-Path (Split-Path -Parent $PSScriptRoot) 'app\__init__.py'
    $versionMatch = [regex]::Match((Get-Content -LiteralPath $versionFile -Raw), '__version__\s*=\s*"([^"]+)"')
    if (-not $versionMatch.Success) { throw 'AgentLink source version is missing.' }
    $agentLinkVersion = $versionMatch.Groups[1].Value
    $report.agentlink_version = $agentLinkVersion
    $base = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'
    if (-not $CodexPath) {
        $settingsFile = Join-Path $env:LOCALAPPDATA 'AgentLinkGUI\settings.json'
        if (Test-Path -LiteralPath $settingsFile) { $CodexPath = (Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json).codex }
        $candidates = @(Get-ChildItem -Path (Join-Path $base '*\codex.exe') -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        if ((-not $CodexPath -or [IO.Path]::GetFullPath($CodexPath) -eq (Join-Path $base 'codex.exe') -or -not (Test-Path -LiteralPath $CodexPath)) -and $candidates.Count) { $CodexPath = $candidates[0].FullName }
    }
    if (-not $CodexPath -or -not (Test-Path -LiteralPath $CodexPath -PathType Leaf)) { throw 'Codex executable was not found. Repair or install Codex Desktop first.' }
    $exe = (Resolve-Path -LiteralPath $CodexPath).Path
    if ($exe.StartsWith('\\')) { throw 'Select a local Codex installation, not a network executable.' }
    $dir = Split-Path -Parent $exe
    $report.codex = $exe
    $report.codex_sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
    if ($Repair) {
        # Only the installed OpenAI desktop package can supply repair files.
        # Match the complete codex.exe hash before copying any companion.
        $packages = @(Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue)
        $source = $null
        foreach ($pkg in $packages) {
            $candidate = Join-Path $pkg.InstallLocation 'app\resources'
            $main = Join-Path $candidate 'codex.exe'
            if (Test-Path -LiteralPath $main -PathType Leaf) {
                if ((Get-FileHash -LiteralPath $main -Algorithm SHA256).Hash -eq $report.codex_sha256) {
                    $absent = @($names | Where-Object { -not (Test-Path -LiteralPath (Join-Path $candidate $_) -PathType Leaf) })
                    if ($absent.Count -eq 0) { $source = $candidate; break }
                }
            }
        }
        if (-not $source) { throw 'No complete installed OpenAI.Codex runtime matches this codex.exe SHA-256. Nothing copied. Update/reinstall Codex Desktop and select its current runtime in AgentLink.' }
        $report.source = $source
        $backup = Join-Path $dir ('.agentlink-helper-backup-' + $stamp)
        foreach ($name in $names) {
            $src = Join-Path $source $name
            $dst = Join-Path $dir $name
            $expected = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
            if ((Test-Path -LiteralPath $dst -PathType Leaf) -and (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash -eq $expected) { continue }
            if (Test-Path -LiteralPath $dst) {
                New-Item -ItemType Directory -Path $backup -Force | Out-Null
                Copy-Item -LiteralPath $dst -Destination (Join-Path $backup $name)
            }
            $temp = Join-Path $dir ('.agentlink-copy-' + [Guid]::NewGuid().ToString('N') + '.tmp')
            Copy-Item -LiteralPath $src -Destination $temp
            if ((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -ne $expected) { throw ('Hash mismatch: ' + $name) }
            Move-Item -LiteralPath $temp -Destination $dst -Force
            if ((Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash -ne $expected) { throw ('Published hash mismatch: ' + $name) }
        }
    }
    $report.files = @($names | ForEach-Object {
        $file = Join-Path $dir $_
        [ordered]@{name=$_; exists=(Test-Path -LiteralPath $file -PathType Leaf); sha256=$(if(Test-Path -LiteralPath $file -PathType Leaf){(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash}else{$null})}
    })
    $missing = @($report.files | Where-Object { -not $_.exists })
    if ($missing.Count) { $report.status='missing_components' } else { $report.status='components_present' }
    Write-Host ('Status: ' + $report.status)
    Write-Host ('Codex: ' + $exe)
    foreach($entry in $report.files){Write-Host ($entry.name + ': ' + $entry.exists)}
    Write-Host ('Restart AgentLink ' + $agentLinkVersion + ' on both PCs. File presence is not a sandbox or two-PC acceptance test.')
} catch {
    $report.status = 'blocked'
    $report.error = $_.Exception.Message
    Write-Warning $report.error
} finally {
    $json = $report | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText((Join-Path $out 'result.json'), $json, (New-Object Text.UTF8Encoding($false)))
    Write-Host ('Diagnostic result: ' + (Join-Path $out 'result.json'))
}
if ($report.status -ne 'components_present') { exit 1 }
