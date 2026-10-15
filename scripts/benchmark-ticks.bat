@echo off
rem Runs python -m evolution_tools.benchmark_ticks (INFRA.9). All arguments are passed on.
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\src"
cd /d "%ROOT%"
python -m evolution_tools.benchmark_ticks %*
exit /b %ERRORLEVEL%
