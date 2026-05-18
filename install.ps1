# Stop the script immediately if a native PowerShell command fails
$ErrorActionPreference = "Stop"

Write-Host "Creating virtual environment (.venv) using Python 3.12..." -ForegroundColor Cyan
& py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create the virtual environment. Exiting."
    Exit $LASTEXITCODE
}

# Verify the activation script exists before running it
$ActivateScript = ".\.venv\Scripts\Activate.ps1"
if (-not (Test-Path $ActivateScript)) {
    Write-Error "Activation script not found at $ActivateScript. Exiting."
    Exit 1
}

Write-Host "Activating the virtual environment..." -ForegroundColor Cyan
& $ActivateScript

Write-Host "Upgrading pip..." -ForegroundColor Cyan
& py -m pip install -U pip
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to upgrade pip. Exiting."
    Exit $LASTEXITCODE
}

Write-Host "Installing the package in editable mode..." -ForegroundColor Cyan
# Note: Corrected 'py install -e .' to 'py -m pip install -e .'
& py -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install the package in editable mode. Exiting."
    Exit $LASTEXITCODE
}

Write-Host "Environment setup completed successfully!" -ForegroundColor Green