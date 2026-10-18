@echo off
rem flashq dashboard - double-click to open http://127.0.0.1:4097/ (already running = just open the browser)
rem extra args are passed through, e.g.  flashq-ui.bat --port 4098
chcp 65001 >nul
title flashq ui
python "%~dp0flashq.py" ui %*
if errorlevel 1 pause
