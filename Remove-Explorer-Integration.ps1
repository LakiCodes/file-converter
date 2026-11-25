$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m converter.setup_windows remove
    if ($LASTEXITCODE -ne 0) { throw 'The Explorer integration could not be removed.' }
}
finally {
    Pop-Location
}
