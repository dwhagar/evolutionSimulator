# Runs python -m evolution_tools.bench_storage (INFRA.9). All arguments are passed on.
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $root "src"
Set-Location $root
python -m evolution_tools.bench_storage @args
exit $LASTEXITCODE
