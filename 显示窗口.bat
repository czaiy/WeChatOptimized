@echo off
chcp 65001 >nul
cd /d "%~dp0"
python 显示窗口.py
timeout /t 2 >nul
