# Runs python -m evolution_tools.founder_economy (INFRA.9). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.founder_economy @args
exit $LASTEXITCODE
