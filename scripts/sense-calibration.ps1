# Runs python -m evolution_tools.sense_calibration (SENSE.13). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.sense_calibration @args
exit $LASTEXITCODE
