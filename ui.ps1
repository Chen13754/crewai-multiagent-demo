$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$UiApp = Join-Path $ProjectRoot "src\ui_app.py"
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $Python)) {
    Write-Error "Project venv Python not found: $Python. Please install dependencies first."
}

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env not found. Run: Copy-Item .env.template .env, then fill DEEPSEEK_API_KEY."
}

$env:PYTHONIOENCODING = "utf-8"
chcp 65001 > $null

Push-Location $ProjectRoot
try {
    & $Python -m streamlit run $UiApp
}
finally {
    Pop-Location
}
