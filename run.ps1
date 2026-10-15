# Runs the Evolution Simulator window from a source checkout (INFRA.10).
#
#   .\run.ps1                    opens the newest saved run, or a new world
#   .\run.ps1 --new --seed 7     every argument is passed on to the program (--fake, --world, ...)
#
# It finds Python 3.12 or newer, builds or reuses the virtual environment in .venv, installs the
# program with the window libraries only when pyproject.toml or version.toml changed since the last
# time (a stamp inside .venv), starts the window and exits with the program's exit code.
#
# If PowerShell says "running scripts is disabled on this system", use run.bat (double-click it) or
#   powershell -ExecutionPolicy Bypass -File .\run.ps1
# which lifts the block for that one run and changes no setting. A script that came from a downloaded
# zip may also say it is "not digitally signed": Unblock-File .\run.ps1 clears that.
#
# This file is plain ASCII and uses nothing newer than Windows PowerShell 5.1 (it also runs in 7).
# It never changes the folder it was started from, so relative paths in the arguments still work.

$minimum = [version]"3.12"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$stamp = Join-Path $venv "install-stamp.txt"
if ([System.IO.Path]::DirectorySeparatorChar -eq "\") {
    $venvPython = Join-Path $venv "Scripts\python.exe"
} else {
    $venvPython = Join-Path $venv "bin/python"  # not Windows: only so the launcher can be tested
}

function Stop-Launcher($message, $code = 1) {
    Write-Host ""
    Write-Host $message -ForegroundColor Red
    exit $code
}

function Get-PythonVersion($exe, $prefix) {
    # The version of this Python as [version] "3.12", or $null if it is missing or does not run.
    try {
        $out = & $exe @prefix -c "import sys; print(sys.version_info[0], sys.version_info[1])" 2>$null
    } catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0) { return $null }
    if ("$out".Trim() -match '^(\d+) (\d+)$') { return [version]"$($Matches[1]).$($Matches[2])" }
    return $null
}

function Find-Python {
    # The first Python of 3.12 or newer, as @{ Exe; Prefix; Version }, or $null.
    $candidates = @(
        @{ Exe = "py"; Prefix = @("-3.12") },
        @{ Exe = "py"; Prefix = @("-3") },
        @{ Exe = "python"; Prefix = @() },
        @{ Exe = "python3"; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $version = Get-PythonVersion $candidate.Exe $candidate.Prefix
        if ($null -ne $version -and $version -ge $minimum) {
            $candidate.Version = $version
            return $candidate
        }
    }
    return $null
}

function Get-Fingerprint {
    # What the installed packages depend on: the two project files.
    $parts = foreach ($name in "pyproject.toml", "version.toml") {
        $file = Join-Path $root $name
        if (Test-Path -LiteralPath $file) {
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
        } else {
            "missing"
        }
    }
    return ($parts -join " ")
}

# 1. The virtual environment: reuse .venv if its Python works and is new enough, else build it again.
$have = $null
if (Test-Path -LiteralPath $venvPython) {
    $have = Get-PythonVersion $venvPython @()
}
if ($null -eq $have -or $have -lt $minimum) {
    $python = Find-Python
    if ($null -eq $python) {
        Stop-Launcher @"
Python $minimum or newer was not found.

Install it, then run this again:
  - from https://www.python.org/downloads/windows/ (keep "py launcher" ticked and tick "Add python.exe to PATH"), or
  - in a terminal:  winget install Python.Python.3.12

(If a Python opens the Microsoft Store instead, that is only a shortcut: install Python as above.)
"@
    }
    if (Test-Path -LiteralPath $venv) {
        Write-Host "The virtual environment in .venv is missing, broken or older than Python $minimum; building it again."
        try {
            Remove-Item -LiteralPath $venv -Recurse -Force -ErrorAction Stop
        } catch {
            Stop-Launcher "Could not remove the old .venv folder ($($_.Exception.Message)). Close any open Evolution Simulator window and run this again."
        }
    }
    Write-Host "Creating the virtual environment in .venv with Python $($python.Version) ..."
    $prefix = $python.Prefix
    & $python.Exe @prefix -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        Stop-Launcher "Could not create the virtual environment in $venv."
    }
}

# 2. The program and the window libraries, only when the project files changed since the last install.
$want = Get-Fingerprint
$done = ""
if (Test-Path -LiteralPath $stamp) {
    $done = "$(Get-Content -LiteralPath $stamp -Raw)".Trim()
}
if ($done -ne $want) {
    Write-Host "Installing the Evolution Simulator and its libraries (this takes a minute the first time) ..."
    Push-Location -LiteralPath $root
    try {
        & $venvPython -m pip install --disable-pip-version-check -e ".[gui]"
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0) {
        Stop-Launcher "The install failed (pip exit code $code). Check the internet connection and that this is a 64-bit Python, then run this again." $code
    }
    Set-Content -LiteralPath $stamp -Value $want -Encoding ASCII
}

# 3. The window. Its console stays open while it runs and shows any message it prints.
& $venvPython -m evolution_simulator.viewer @args
exit $LASTEXITCODE
