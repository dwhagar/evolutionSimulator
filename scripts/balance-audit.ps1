# Runs python -m evolution_tools.balance_audit (INFRA.9). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.balance_audit @args
exit $LASTEXITCODE
