@echo off
chcp 65001 >nul
setlocal
rem 一键跑全部回归测试（双击即可）。使用 %~dp0 定位脚本，避免中文路径写死。
set PYEXE=
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set PYEXE="%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if "%PYEXE%"=="" if exist "C:\Users\82453\.workbuddy\binaries\python\versions\3.13.12\python.exe" set PYEXE="C:\Users\82453\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if "%PYEXE%"=="" set PYEXE=python
%PYEXE% "%~dp0run_all_tests.py" %*
echo.
pause
