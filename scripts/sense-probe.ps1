# Runs python -m evolution_tools.sense_probe (SENSE.13). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.sense_probe @args
exit $LASTEXITCODE
