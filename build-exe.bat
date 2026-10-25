@echo off
rem build flashq-gui.exe (single file, app window) -> dist\flashq-gui.exe
rem usage: build-exe.bat            (PyInstaller, no C compiler needed)
rem        build-exe.bat nuitka     (native compile, harder to reverse, needs MinGW)
chcp 65001 >nul
title build flashq exe
set ENGINE=%1
if "%ENGINE%"=="" set ENGINE=pyinstaller
set PYTHONIOENCODING=utf-8
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_exe.ps1" -Engine %ENGINE%
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
echo.
echo DONE: %~dp0dist\flashq-gui.exe
explorer "%~dp0dist"
pause
