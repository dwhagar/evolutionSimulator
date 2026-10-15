@echo off
rem Runs python -m evolution_tools.bench_dna_distance (INFRA.9). All arguments are passed on.
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\src"
cd /d "%ROOT%"
python -m evolution_tools.bench_dna_distance %*
exit /b %ERRORLEVEL%
