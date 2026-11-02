@echo off
chcp 65001 >nul
rem MYONL 编辑器一键打包：生成 dist\editor\editor.exe（双击开窗）
cd /d "%~dp0"
set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=py -3"
echo [1/3] 检查依赖 pywebview / PyInstaller ...
%PY% -c "import webview, PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo 缺少依赖，正在安装：pywebview PyInstaller
  %PY% -m pip install pywebview pyinstaller
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
)
echo [2/3] 检查玩家模板（发行版里一键打包游戏要用）...
%PY% tools\build_player_template.py --check
if errorlevel 1 (
  echo 首次构建玩家模板，约 1~2 分钟...
  %PY% tools\build_player_template.py
  if errorlevel 1 (
    echo 玩家模板构建失败，请查看上面的中文提示。
    pause
    exit /b 1
  )
)
echo [3/3] 开始打包编辑器（onedir，约需 1~3 分钟）...
%PY% -m PyInstaller --noconfirm --clean editor.spec
if errorlevel 1 (
  echo.
  echo 打包失败，请查看上面的中文提示。
  pause
  exit /b 1
)
echo.
echo 打包完成：dist\editor\editor.exe
echo 双击 editor.exe 即可打开编辑器窗口（依赖系统 WebView2，Win10/11 自带）。
pause
