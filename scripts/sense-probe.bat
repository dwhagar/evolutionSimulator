@echo off
rem Runs python -m evolution_tools.sense_probe (SENSE.13). All arguments are passed on.
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\src"
cd /d "%ROOT%"
python -m evolution_tools.sense_probe %*
exit /b %ERRORLEVEL%
