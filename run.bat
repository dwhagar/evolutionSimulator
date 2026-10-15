@echo off
rem Double-click launcher for the Evolution Simulator (INFRA.10): runs run.ps1 next to it, with
rem PowerShell's script block lifted for this one run (no setting is changed), passes every
rem argument on and exits with its exit code. If it fails after a double-click, the window waits
rem for a key so the message can be read.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo %cmdcmdline% | find /i " /c " >nul && pause
exit /b %CODE%
