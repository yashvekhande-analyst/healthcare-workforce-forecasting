$ErrorActionPreference = 'Stop'
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Create .venv and install the dependencies using the README quick start first.'
}
Push-Location -LiteralPath $PSScriptRoot
try { & $pythonExe -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501 }
finally { Pop-Location }
