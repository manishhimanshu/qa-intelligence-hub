# Set up the shared Python environment for both QA Intelligence Hub tools.
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $repoRoot "requirements.txt"
$envFile = Join-Path $repoRoot "rag\.env"
$envTemplate = Join-Path $repoRoot "rag\.env.example"

function Get-PythonInstallGuidance {
    $wingetCommand = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetCommand) {
        return "Python 3.12 or later is required. Install it with: winget install --id Python.Python.3.12 --exact`nAfter installation, close and reopen PowerShell, then rerun .\setup.ps1."
    }
    return "Python 3.12 or later is required. Install it from https://www.python.org/downloads/windows/ and enable the Python launcher or add Python to PATH. Close and reopen PowerShell, then rerun .\setup.ps1."
}

if (-not (Test-Path $requirements)) { throw "Root requirements.txt was not found at $requirements." }
if (-not (Test-Path $envTemplate)) { throw "Environment template was not found at $envTemplate." }

if (-not (Test-Path $venvPython)) {
    $venvPath = Join-Path $repoRoot ".venv"
    $created = $false
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        & $pythonLauncher.Source -3.12 -m venv $venvPath
        $created = ($LASTEXITCODE -eq 0)
    }
    if (-not $created) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw (Get-PythonInstallGuidance) }
        $basePython = $pythonCommand.Source
        $baseVersionText = & $basePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($LASTEXITCODE -ne 0 -or $baseVersionText -notmatch '^\d+\.\d+$') {
            throw (Get-PythonInstallGuidance)
        }
        if ([version]$baseVersionText -lt [version]"3.12") {
            throw "Found Python $baseVersionText, but Python 3.12 or later is required.`n$(Get-PythonInstallGuidance)"
        }
        & $basePython -m venv $venvPath
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the repository virtual environment." }
}

$venvVersionText = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) { throw "Could not run the repository Python environment at $venvPython." }
if ([version]$venvVersionText -lt [version]"3.12") {
    throw "The existing .venv uses Python $venvVersionText. Remove .venv and rerun with Python 3.12 or later."
}

if (-not (Test-Path $envFile)) {
    Copy-Item $envTemplate $envFile
    Write-Host "Created rag/.env from the template. Add your service credentials before using the tools."
} else {
    Write-Host "Preserving existing rag/.env."
}

Write-Host "Installing shared Python dependencies from root requirements.txt..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host ""
Write-Host "Python setup complete. Next:"
Write-Host "  1. Edit rag/.env and add the credentials needed for your workflows."
Write-Host "  2. Start the Streamlit app: .\.venv\Scripts\python.exe -m streamlit run .\custom-agent-ui\app.py"
Write-Host "  3. For Copilot, install Node.js 22+ and GitHub Copilot CLI, then run .\qa-copilot-cli\setup.ps1"