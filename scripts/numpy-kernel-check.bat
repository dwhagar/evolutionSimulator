@echo off
rem Runs python -m evolution_tools.numpy_kernel_check (INFRA.9). All arguments are passed on.
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\src"
cd /d "%ROOT%"
python -m evolution_tools.numpy_kernel_check %*
exit /b %ERRORLEVEL%
