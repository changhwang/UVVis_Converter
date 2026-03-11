param(
    [string]$PythonExe = ".\\build_venv312\\Scripts\\python.exe",
    [switch]$EnsureDeps
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptRoot "..")
$requestedPythonPath = Join-Path $projectRoot $PythonExe

if (-not (Test-Path $requestedPythonPath)) {
    if ($PythonExe -eq ".\\build_venv312\\Scripts\\python.exe") {
        Write-Host "Creating build_venv312 using Python 3.12..."
        & py -3.12 -m venv (Join-Path $projectRoot "build_venv312")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create .\\build_venv312. Install Python 3.12 and retry."
        }
    }
    else {
        throw "Python executable not found: $requestedPythonPath"
    }
}

$pythonPath = Resolve-Path $requestedPythonPath
Write-Host "Project root: $projectRoot"
Write-Host "Python: $pythonPath"

Push-Location $projectRoot
$oldPythonPath = $env:PYTHONPATH
$oldPythonHome = $env:PYTHONHOME
try {
    if ($env:PYTHONPATH) {
        Write-Host "Clearing PYTHONPATH for reproducible build."
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    if ($env:PYTHONHOME) {
        Write-Host "Clearing PYTHONHOME for reproducible build."
        Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    }

    $pythonVersion = (& $pythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to detect Python version for $pythonPath"
    }
    Write-Host "Python version: $pythonVersion"

    $pythonMajorMinor = (& $pythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ([Version]$pythonMajorMinor -lt [Version]"3.12") {
        throw "Selected Python is $pythonVersion. Packaging requires Python 3.12+ to avoid known PyInstaller failures on Python 3.10.0."
    }

    if ($EnsureDeps) {
        Write-Host "Installing build dependencies..."
        & $pythonPath -m pip install -r requirements.txt pyinstaller
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install build dependencies."
        }
    }
    else {
        & $pythonPath -m pip show pyinstaller | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller is not installed in the selected environment. Re-run with -EnsureDeps."
        }
    }

    & $pythonPath -m PyInstaller --noconfirm --clean UVVisConverter.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    Write-Host ""
    Write-Host "Build complete."
    Write-Host "Output folder: $(Join-Path $projectRoot 'dist\\UVVisConverter')"
}
finally {
    if ($null -ne $oldPythonPath) { $env:PYTHONPATH = $oldPythonPath } else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
    if ($null -ne $oldPythonHome) { $env:PYTHONHOME = $oldPythonHome } else { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue }
    Pop-Location
}
