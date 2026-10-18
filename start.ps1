param(
    [ValidateRange(1,65535)][int]$Port = 8000,
    [switch]$CheckOnly,
    [switch]$SkipInstall,
    [switch]$Configure
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            & $launcher.Source -3 -m venv .venv
        } else {
            $launcher = Get-Command python -ErrorAction SilentlyContinue
            if (-not $launcher) { throw 'Install Python 3.11+ (64-bit) and enable the Python launcher or add Python to PATH.' }
            & $launcher.Source -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed. Install Python 3.11+.' }
    }
    & $pythonPath -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'"
    if ($LASTEXITCODE -ne 0) { throw 'This .venv uses an unsupported Python version.' }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $dependencyHash = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'requirements.txt')))).Replace('-', '') } finally { $sha.Dispose() }
    $marker = Join-Path $PSScriptRoot '.venv\requirements.sha256'
    $installedHash = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
    if (-not $SkipInstall -and $installedHash -ne $dependencyHash) {
        & $pythonPath -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check network access and pip configuration.' }
        Set-Content -LiteralPath $marker -Value $dependencyHash -Encoding ascii
    }
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    # First run without a key opens the interactive wizard; -Configure always opens it.
    if (-not $env:DEEPSEEK_API_KEY) {
        $savedKey = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
        if (-not $savedKey) { $savedKey = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'Machine') }
        if ($savedKey) { $env:DEEPSEEK_API_KEY = $savedKey }
    }
    & $pythonPath -c "from app.config import settings; import sys; sys.exit(0 if settings.openai_api_key else 2)"
    $needsKey = $LASTEXITCODE -eq 2
    if ($Configure -or ($needsKey -and -not $CheckOnly)) {
        & $pythonPath -m scripts.configure
        if ($LASTEXITCODE -ne 0) { throw 'Configuration wizard did not finish.' }
    }
    # Read the persisted user variable when the terminal predates its creation.
    if (-not $env:DEEPSEEK_API_KEY) {
        $savedKey = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
        if (-not $savedKey) { $savedKey = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'Machine') }
        if ($savedKey) { $env:DEEPSEEK_API_KEY = $savedKey }
    }
    & $pythonPath -c "from app.config import settings; from app.db import initialize; assert settings.openai_api_key, 'Set DEEPSEEK_API_KEY in your environment or local .env'; initialize(); print('Configuration and database ready. API key is configured (not displayed).')"
    if ($LASTEXITCODE -ne 0) { throw 'Configuration check failed. Use KEY=value syntax in a UTF-8 .env file. Do not use export or $env: syntax inside .env.' }
    if ($CheckOnly) { Write-Host 'Startup check passed.'; exit 0 }
    Write-Host "Open http://127.0.0.1:$Port - press Ctrl+C to stop. Keep this window running for daily schedules."
    & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
    if ($LASTEXITCODE -ne 0) { throw 'Server stopped with an error. Check whether the port is already in use.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
