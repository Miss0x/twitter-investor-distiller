@echo off
chcp 65001 >nul 2>&1
title %2
cd /d "%~dp0"
echo ============================================
echo   %2
echo ============================================
echo 开始时间: %date% %time%
echo.
python -u "%~dp0scripts\%1"
set RC=%ERRORLEVEL%
echo.
echo 结束时间: %date% %time%
echo 退出码: %RC%
echo.
echo 按任意键关闭...
pause >nul
