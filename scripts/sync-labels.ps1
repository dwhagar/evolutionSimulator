# Runs python -m evolution_tools.sync_labels (INFRA.9). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.sync_labels @args
exit $LASTEXITCODE
