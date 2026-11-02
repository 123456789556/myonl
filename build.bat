@echo off
chcp 65001 >nul
rem MYONL 一键打包：把游戏目录拖到本文件上，或在命令行执行 build.bat 游戏目录 [游戏名]
if "%~1"=="" (
  echo 用法：build.bat 游戏目录 [游戏名]
  echo 例：  build.bat 示例游戏 夜班便利店
  pause
  exit /b 1
)
set "PY=python"
where python >nul 2>nul
if errorlevel 1 set "PY=py -3"
if "%~2"=="" (
  %PY% pack.py "%~1"
) else (
  %PY% pack.py "%~1" --name "%~2"
)
if errorlevel 1 (
  echo.
  echo 打包失败，请查看上面的中文提示。
  pause
)
