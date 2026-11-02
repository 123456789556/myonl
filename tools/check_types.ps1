# 迭代-01 / 八大方向 1.2：pyright 棘轮检查（本地入口，替代未就绪的 CI）。
#
# 机制：存量类型错误以 tools/pyright-baseline.json 的 file|rule 计数为基线；
# 本次扫描任何基线键计数上升、或出现基线外新键，判失败（exit 1）——
# 即"不许新增类型债"，存量债务随任务 1.1/1.3 修复逐步下调基线。
#
# 用法：powershell -File tools/check_types.ps1
# 注意：pyright 固定扫 engine/（见 pyrightconfig.json include）。

$ErrorActionPreference = "Stop"

$pyexe = & py -3 -c "import sys; print(sys.executable)"
if (-not $pyexe) { Write-Host "错误：未找到 py -3 解释器"; exit 2 }

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"  # pyright 的告警走 stderr，不能因 EAP=Stop 误判失败
$out = & py -3 -m pyright engine --pythonpath $pyexe --outputjson 2>$null | Out-String
$ErrorActionPreference = $prevEAP
if (-not $out) { Write-Host "错误：pyright 无输出（未安装？pip install -r requirements-dev.txt）"; exit 2 }
$scan = $out | ConvertFrom-Json

$basePath = Join-Path $PSScriptRoot "pyright-baseline.json"
$base = Get-Content $basePath -Raw -Encoding UTF8 | ConvertFrom-Json

# 当前扫描的 file|rule 计数
$cur = @{}
foreach ($d in $scan.generalDiagnostics) {
    $rule = if ($d.rule) { $d.rule } else { "unrule" }
    $k = "$(Split-Path $d.file -Leaf)|$rule"
    if ($cur.ContainsKey($k)) { $cur[$k] += 1 } else { $cur[$k] = 1 }
}

# 对比基线：新增键或计数上升 → 失败
$bad = @()
foreach ($k in $cur.Keys) {
    $prop = $base.counts.PSObject.Properties[$k]
    $b = if ($prop) { [int]$prop.Value } else { 0 }
    if ($cur[$k] -gt $b) { $bad += "新增类型错误：$k 基线 $b -> 当前 $($cur[$k])" }
}

# 存量下降 → 提示可下调基线
$good = @()
foreach ($prop in $base.counts.PSObject.Properties) {
    $k = $prop.Name; $b = [int]$prop.Value
    $c = if ($cur.ContainsKey($k)) { $cur[$k] } else { 0 }
    if ($c -lt $b) { $good += "存量减少：$k 基线 $b -> 当前 $c（可下调基线）" }
}

$total = $scan.summary.errorCount
Write-Host "pyright 扫描：engine/ 共 $total 个错误（基线 $($base._total)）"
foreach ($g in $good) { Write-Host "  [进展] $g" }

if ($bad.Count -gt 0) {
    foreach ($b in $bad) { Write-Host "  [失败] $b" }
    exit 1
}
Write-Host "棘轮检查通过：无新增类型错误"
exit 0
