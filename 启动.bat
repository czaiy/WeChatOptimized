@echo off
chcp 65001 >nul
title WeChatOptimized
echo ============================================
echo   WeChatOptimized - 微信智能桥接
echo ============================================
echo.
cd /d "%~dp0"
python main.py
pause
