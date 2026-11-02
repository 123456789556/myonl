# 迭代-02 / 八大方向 7.4：engine/ 覆盖率门禁（本地入口）。
#
# 口径：只统计 engine/（--cov=engine），不含 tests/ 与 editor/。
# 基线：2026-10-31 全量实测 engine/ 覆盖率 81.09%（term 显示 81%），
#       向下取整 81%，再留 1% 浮动余量 → 门禁阈值 80%。
#       复验：同日并行 1080p UI 比例任务合入后实测 82.63%，阈值维持 80。
#       小改动造成的覆盖率波动不会误红；新增大量无测试代码会触发失败。
#
# 用法：powershell -File tools/check_coverage.ps1
# 退出码：0 = 覆盖率达标且测试全绿；1 = 覆盖率低于阈值 / 存在失败用例；2 = 环境缺失。
# 注意：--cov 只在本脚本里加，不写入 pytest.ini.addopts，默认 pytest -q 不受影响。

$ErrorActionPreference = "Stop"
$Threshold = 80
$Baseline = "81.09"

# 固定从仓库根目录跑（pytest.ini 与 .coverage 都在根目录）
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
$exitCode = 0

try {
    $pyexe = & py -3 -c "import sys; print(sys.executable)"
    if (-not $pyexe) {
        Write-Host "错误：未找到 py -3 解释器"
        $exitCode = 2
    }
    else {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"  # pytest 的 warning 走 stderr，不能因 EAP=Stop 误判失败
        & py -3 -c "import pytest_cov" 2>$null
        $hasCov = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEAP

        if (-not $hasCov) {
            Write-Host "错误：未安装 pytest-cov（py -3 -m pip install -r requirements-dev.txt）"
            $exitCode = 2
        }
        else {
            # 清掉上一次的 .coverage，保证下面读到的就是本次实测
            $covFile = Join-Path $root ".coverage"
            if (Test-Path $covFile) { Remove-Item $covFile -Force }

            Write-Host "覆盖率门禁：engine/ 阈值 $Threshold%（2026-10-31 基线 $Baseline%）"
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & py -3 -m pytest tests -q --cov=engine --cov-report=term-missing --cov-fail-under=$Threshold
            $code = $LASTEXITCODE
            $ErrorActionPreference = $prevEAP

            # 取本次精确覆盖率（pytest 结束时 coverage 数据已落盘）
            $pct = & py -3 -c "import coverage, io; c = coverage.Coverage(); c.load(); b = io.StringIO(); t = c.report(file=b); print(f'{t:.2f}')" 2>$null
            if ($pct) {
                Write-Host "本次实测：engine/ 覆盖率 $pct%（阈值 $Threshold%，基线 $Baseline%）"
            }

            if ($code -eq 0) {
                Write-Host "覆盖率门禁通过：engine/ 覆盖率不低于 $Threshold%"
            }
            else {
                Write-Host "覆盖率门禁失败：engine/ 覆盖率低于 $Threshold%，或存在失败用例（pytest 退出码 $code）"
                $exitCode = 1
            }

            # 写机器可读摘要：STATUS 自动数字区只认这一份（避免读到随手 --cov 产生的部分数据）
            $head = (& git rev-parse --short HEAD 2>$null | Out-String).Trim()
            $covValue = if ($pct) { [double]$pct } else { $null }
            $summary = [ordered]@{
                coverage    = $covValue
                threshold   = $Threshold
                baseline    = $Baseline
                passed      = ($code -eq 0)
                command     = "py -3 -m pytest tests -q --cov=engine --cov-report=term-missing --cov-fail-under=$Threshold"
                measured_at = (Get-Date).ToString("s")
                head        = $head
            }
            $summary | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $root ".coverage-summary.json")
        }
    }
}
finally {
    Pop-Location
}

exit $exitCode
