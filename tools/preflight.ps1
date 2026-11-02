# M0 收口：一键门禁（pytest + pyright 棘轮 [+ 覆盖率] + 刷新 STATUS 数字）
#
# 用法：
#   powershell -NoProfile -File tools/preflight.ps1 -Fast      # 日常：pytest -m "not slow" + pyright（约 60s）
#   powershell -NoProfile -File tools/preflight.ps1            # 提交前：全量 pytest + pyright（约 2 分钟）
#   powershell -NoProfile -File tools/preflight.ps1 -WithCoverage  # release 前：再加覆盖率门禁（约 5 分钟）
# 退出码：0 = 全部通过；1 = 有门禁失败；2 = 环境缺失。

param(
    [switch]$Fast,
    [switch]$WithCoverage
)

$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
$failed = @()
$sw = [System.Diagnostics.Stopwatch]::StartNew()

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

try {
    Write-Step "[1/4] pytest$(if ($Fast) { '（-m "not slow"）' } else { '（全量）' })"
    if ($Fast) { & py -3 -m pytest -q -m "not slow" } else { & py -3 -m pytest -q }
    if ($LASTEXITCODE -ne 0) { $failed += "pytest" }

    Write-Step "[2/4] pyright 棘轮（tools/check_types.ps1）"
    & powershell -NoProfile -File (Join-Path $PSScriptRoot "check_types.ps1")
    if ($LASTEXITCODE -ne 0) { $failed += "pyright" }

    if ($WithCoverage) {
        Write-Step "[3/4] 覆盖率门禁（tools/check_coverage.ps1）"
        & powershell -NoProfile -File (Join-Path $PSScriptRoot "check_coverage.ps1")
        if ($LASTEXITCODE -ne 0) { $failed += "coverage" }
    }
    else {
        Write-Step "[3/4] 覆盖率门禁：跳过（加 -WithCoverage 才跑，约 5 分钟）"
    }

    Write-Step "[4/4] 刷新 docs/STATUS.md 自动数字区"
    & py -3 tools/status.py --write
    if ($LASTEXITCODE -ne 0) { $failed += "status" }
}
finally {
    Pop-Location
}

$sw.Stop()
Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host ("preflight 通过（{0:N1}s）：pytest / pyright{1} / STATUS 全部 OK" -f $sw.Elapsed.TotalSeconds, $(if ($WithCoverage) { " / coverage" } else { "" })) -ForegroundColor Green
    exit 0
}
Write-Host ("preflight 失败（{0:N1}s）：{1}" -f $sw.Elapsed.TotalSeconds, ($failed -join ", ")) -ForegroundColor Red
exit 1
