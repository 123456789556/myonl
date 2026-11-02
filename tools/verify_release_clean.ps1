# MYONL release clean-space smoke test.
# Simulates a new user's first launch:
#   - extracts the release zip to a temp folder
#   - uses a fresh empty AppData / UserProfile / TEMP
#   - removes Python/dev environment variables and minimizes PATH
#   - runs the frozen editor, the frozen demo worker, and opens the real editor window
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools/verify_release_clean.ps1
#   powershell -ExecutionPolicy Bypass -File tools/verify_release_clean.ps1 -SkipWindow
#
# Exit codes: 0 = pass, 1 = frozen exe failed, 2 = zip missing,
#             3 = WebView2 missing (editor UI blocked), 4 = editor window did not open.

param(
    [string]$Zip = "",
    [switch]$Keep,
    [switch]$SkipWindow
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $Zip) {
    $Zip = Get-ChildItem (Join-Path $root "dist\release\MYONL*.zip") -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Zip -or -not (Test-Path $Zip)) {
    Write-Host "ERROR: release zip not found (run tools/build_release_zip.py first)"
    exit 2
}

$work = Join-Path $env:TEMP ("myonl_clean_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $work | Out-Null

$saved = @{
    PATH = $env:PATH
    PYTHONHOME = $env:PYTHONHOME
    PYTHONPATH = $env:PYTHONPATH
    APPDATA = $env:APPDATA
    LOCALAPPDATA = $env:LOCALAPPDATA
    USERPROFILE = $env:USERPROFILE
    TEMP = $env:TEMP
    TMP = $env:TMP
}

try {
    Write-Host "[0/5] zip: $Zip"
    Expand-Archive -Path $Zip -DestinationPath $work -Force
    $base = Get-ChildItem $work -Directory | Select-Object -First 1
    $exe = Join-Path $base.FullName "editor\editor.exe"
    $project = Join-Path $base.FullName "games\教程示例"
    $quick = Join-Path $base.FullName "文档\快速上手.md"
    if (-not (Test-Path $exe)) { throw "editor.exe missing from release zip" }
    if (-not (Test-Path $quick)) { throw "文档/快速上手.md missing from release zip" }

    # Simulate a machine without Python: no PYTHONHOME/PYTHONPATH, minimal PATH.
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $null
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:SDL_VIDEODRIVER = "dummy"
    $env:SDL_AUDIODRIVER = "dummy"
    $env:PYTHONUTF8 = "1"

    Write-Host "[1/5] editor.exe -h"
    & $exe -h | Out-Null
    $code1 = $LASTEXITCODE

    Write-Host "[2/5] editor.exe --demo-worker (headless 30 frames)"
    & $exe --demo-worker (Join-Path $project "script.gal") --assets $project --auto --max-frames 30 | Out-Null
    $code2 = $LASTEXITCODE

    Write-Host "[3/5] WebView2 runtime"
    $webview2 = $false
    foreach ($key in @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "HKCU:\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    )) {
        if (Test-Path $key) { $webview2 = $true; break }
    }

    Write-Host "[4/5] editor first-run window (fresh AppData)"
    $windowOk = $true
    $windowTitle = ""
    $proc = $null
    if (-not $SkipWindow) {
        $profile = Join-Path $work "_profile"
        $env:APPDATA = Join-Path $profile "AppData\Roaming"
        $env:LOCALAPPDATA = Join-Path $profile "AppData\Local"
        $env:USERPROFILE = $profile
        $env:TEMP = Join-Path $profile "Temp"
        $env:TMP = $env:TEMP
        New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:LOCALAPPDATA, $env:TEMP | Out-Null
        $proc = Start-Process -FilePath $exe -ArgumentList @("--project", $project) -PassThru
        for ($i = 0; $i -lt 25; $i++) {
            Start-Sleep -Seconds 1
            $proc.Refresh()
            if ($proc.HasExited) { break }
            if ($proc.MainWindowTitle) { break }
        }
        $proc.Refresh()
        $windowTitle = $proc.MainWindowTitle
        $windowOk = (-not $proc.HasExited) -and [bool]$windowTitle
        if (-not $proc.HasExited) {
            & taskkill /PID $proc.Id /T /F | Out-Null
        }
        $proc = $null
    }

    Write-Host "[5/5] summary"
    Write-Host "  editor.exe -h            exit $code1"
    Write-Host "  editor.exe --demo-worker exit $code2"
    Write-Host "  WebView2 runtime         $(if ($webview2) { 'present' } else { 'MISSING' })"
    if (-not $SkipWindow) {
        Write-Host "  editor window            $(if ($windowOk) { "opened [$windowTitle]" } else { 'FAILED' })"
    }

    if ($code1 -ne 0 -or $code2 -ne 0) {
        Write-Host "FAIL: frozen editor/demo failed in the clean folder"
        exit 1
    }
    if (-not $webview2) {
        Write-Host "BLOCKED: WebView2 missing - editor window will show the install prompt"
        exit 3
    }
    if (-not $windowOk) {
        Write-Host "FAIL: editor window did not open with a fresh AppData profile"
        exit 4
    }
    Write-Host "PASS: release package runs like a new install (no Python, empty AppData, real editor window)"
    exit 0
}
finally {
    $env:PATH = $saved.PATH
    $env:PYTHONHOME = $saved.PYTHONHOME
    $env:PYTHONPATH = $saved.PYTHONPATH
    $env:APPDATA = $saved.APPDATA
    $env:LOCALAPPDATA = $saved.LOCALAPPDATA
    $env:USERPROFILE = $saved.USERPROFILE
    $env:TEMP = $saved.TEMP
    $env:TMP = $saved.TMP
    Remove-Item Env:SDL_VIDEODRIVER -ErrorAction SilentlyContinue
    Remove-Item Env:SDL_AUDIODRIVER -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.HasExited) { & taskkill /PID $proc.Id /T /F | Out-Null }
    if (-not $Keep) { Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue }
    else { Write-Host "kept: $work" }
}
