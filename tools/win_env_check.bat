@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ============================================
echo  MYONL 测试环境检查（双击运行即可，只读不改）
echo ============================================
echo.

echo [1/5] Windows 版本
systeminfo 2>nul | findstr /B /C:"OS Name" /C:"OS Version"
ver
echo.

echo [2/5] 是否装了 Python（外部机器应当没有）
where python 2>nul
where py 2>nul
if errorlevel 1 echo   未发现 Python —— 符合"无 Python 真机"要求
echo.

echo [3/5] WebView2 运行时（编辑器界面依赖）
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
if not errorlevel 1 (
  echo   已安装（机器级）
) else (
  reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" /v pv >nul 2>&1
  if not errorlevel 1 (
    echo   已安装（用户级）
  ) else (
    echo   未检测到 WebView2 运行时 —— 编辑器可能打不开界面，请先装 Microsoft Edge WebView2 Runtime
  )
)
echo.

echo [4/5] 当前解压路径（含中文/空格也可以，但记录一下）
echo   %CD%
echo.

echo [5/5] 下一步：双击同目录上级的 editor\editor.exe，按测试说明操作
echo.
pause
