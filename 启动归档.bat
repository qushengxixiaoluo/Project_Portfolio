@echo off
rem DangKu launcher: start backend and open browser (zero-ask archiving)
rem Uses explicit %%SystemRoot%% paths so it works even with a stripped PATH.
cd /d "%~dp0"

set "CURL=%SystemRoot%\System32\curl.exe"
if not exist "%CURL%" set "CURL=curl"
set "PING=%SystemRoot%\System32\ping.exe"

rem 1) already running?
"%CURL%" -s -o nul -m 2 --noproxy "*" http://127.0.0.1:8000/ >nul 2>&1
if not errorlevel 1 goto already

rem 2) detect python: PATH -> py launcher -> venv -> common install dirs
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto havepy
py --version >nul 2>&1
if not errorlevel 1 set "PY=py"
if defined PY goto havepy
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if defined PY goto havepy
if exist "D:\Python\python.exe" set "PY=D:\Python\python.exe"
if defined PY goto havepy
echo [ERROR] Python not found. Install Python and add it to PATH.
pause
exit /b 1

:havepy
echo [..] Using %PY%
start "DangKu-Service" cmd /k "%PY% -m uvicorn main:app --host 127.0.0.1 --port 8000"
set /a n=0

:wait
"%PING%" -n 2 127.0.0.1 >nul
"%CURL%" -s -o nul -m 2 --noproxy "*" http://127.0.0.1:8000/ >nul 2>&1
if not errorlevel 1 goto ready
set /a n+=1
if %n% lss 30 goto wait
echo [ERROR] Startup timeout. Check the service window for errors.
pause
exit /b 1

:ready
echo [OK] Service ready: http://127.0.0.1:8000
echo       Originals auto-save to data\uploads\ (no prompts ever).
echo       Keep the service window open; closing it stops the service.
start "" http://127.0.0.1:8000
exit /b 0

:already
echo [OK] Service already running. Opening browser...
start "" http://127.0.0.1:8000
exit /b 0
