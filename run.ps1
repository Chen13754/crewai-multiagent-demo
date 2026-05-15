param(
    [ValidateSet("flash", "pro")]
    [string]$Model = "",

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Topic
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Main = Join-Path $ProjectRoot "src\main.py"
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $Python)) {
    Write-Error "Project venv Python not found: $Python. Please install dependencies first."
}

if (-not (Test-Path $EnvFile)) {
    Write-Error ".env not found. Run: Copy-Item .env.template .env, then fill DEEPSEEK_API_KEY."
}

# Keep CrewAI's unicode logs readable in Windows terminals.
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 > $null

Push-Location $ProjectRoot
try {
    $ResolvedTopic = ($Topic -join " ").Trim()
    $Args = @()

    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $Args += "--model"
        $Args += $Model
    }

    if ([string]::IsNullOrWhiteSpace($ResolvedTopic)) {
        & $Python $Main @Args
    }
    else {
        $Args += $ResolvedTopic
        & $Python $Main @Args
    }
}
finally {
    Pop-Location
}
