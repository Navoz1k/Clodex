[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$AllowForceClose
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$copy = Join-Path $root 'desktop-copy'
$modifiedExe = Join-Path $copy 'ChatGPT.exe'
$profile = Join-Path $root 'mod-profile'
$log = Join-Path $root 'switch.log'
$manifest = Get-Content -LiteralPath (Join-Path $copy 'clodex-build.json') -Raw | ConvertFrom-Json
$stockExe = (Resolve-Path -LiteralPath $manifest.originalExecutable).Path
$archive = Join-Path $copy 'resources/app.asar'

Get-Item -LiteralPath $modifiedExe,$archive | Out-Null
if ($stockExe -eq $modifiedExe -or (Split-Path $stockExe -Leaf) -ne 'ChatGPT.exe') {
    throw 'The original and modified Codex executables are not distinct.'
}
if (-not $Apply) {
    [pscustomobject]@{
        Original = $stockExe
        Modified = $modifiedExe
        ModifiedProfile = $profile
        Action = 'Preview only'
    }
    return
}

function Get-CodexProcesses([string]$Executable) {
    Get-Process -Name ChatGPT -ErrorAction SilentlyContinue |
        Where-Object Path -eq $Executable
}

function Wait-ForWindow([string]$Executable) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Get-CodexProcesses $Executable | Where-Object MainWindowHandle -ne 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Set-Content -LiteralPath $log -Value 'Switching from original Codex to the modified copy.'
$stockWasOpen = [bool](Get-CodexProcesses $stockExe)
$modifiedAlreadyOpen = [bool](Get-CodexProcesses $modifiedExe)
$startedModified = $false
try {
    Get-CodexProcesses $stockExe | Where-Object MainWindowHandle -ne 0 |
        ForEach-Object { [void]$_.CloseMainWindow() }
    for ($attempt = 0; $attempt -lt 12 -and (Get-CodexProcesses $stockExe); $attempt++) {
        Start-Sleep -Milliseconds 500
    }
    if ((Get-CodexProcesses $stockExe) -and $AllowForceClose) {
        Get-CodexProcesses $stockExe | Stop-Process
        for ($attempt = 0; $attempt -lt 12 -and (Get-CodexProcesses $stockExe); $attempt++) {
            Start-Sleep -Milliseconds 250
        }
    }
    if (Get-CodexProcesses $stockExe) {
        throw 'Original Codex is still running. Quit it from the tray before switching.'
    }
    if (-not $modifiedAlreadyOpen) {
        Start-Process -FilePath $modifiedExe -WorkingDirectory $copy -ArgumentList @(
            ('"--user-data-dir=' + $profile + '"'), '--force-prefers-no-reduced-motion', '--no-first-run'
        )
        $startedModified = $true
    }
    if (-not (Wait-ForWindow $modifiedExe)) {
        throw 'The modified Codex did not open its window.'
    }
    Add-Content -LiteralPath $log -Value 'The original Codex is closed and the modified window is open.'
} catch {
    Add-Content -LiteralPath $log -Value $_.Exception.Message
    if ($startedModified) {
        Get-CodexProcesses $modifiedExe | Stop-Process -ErrorAction SilentlyContinue
    }
    if ($stockWasOpen -and -not (Get-CodexProcesses $stockExe)) {
        Start-Process -FilePath $stockExe -WorkingDirectory (Split-Path $stockExe -Parent)
        Add-Content -LiteralPath $log -Value 'Requested reopening of original Codex.'
    }
    throw
}
