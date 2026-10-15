# Runs python -m evolution_tools.reproduction_check (INFRA.9). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.reproduction_check @args
exit $LASTEXITCODE
