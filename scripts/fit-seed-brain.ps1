# Runs python -m evolution_tools.fit_seed_brain (INFRA.9). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.fit_seed_brain @args
exit $LASTEXITCODE
