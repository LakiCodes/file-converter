[CmdletBinding()]
param([switch]$SkipWindowsIntegration)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $converterPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $converterPythonCheck = "import struct, sys; sys.exit(sys.version_info[:2] != (3, 13) or struct.calcsize('P') != 8)"
    if (-not (Test-Path -LiteralPath $converterPython)) {
        $converterLauncher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($converterLauncher) {
            & $converterLauncher.Source -3.13 -c $converterPythonCheck
            if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.13 for Windows, then run setup again.' }
            & $converterLauncher.Source -3.13 -m venv .venv
        }
        else {
            $converterSystemPython = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if (-not $converterSystemPython) { throw 'Install 64-bit Python 3.13 for Windows, then run setup again.' }
            & $converterSystemPython.Source -c $converterPythonCheck
            if ($LASTEXITCODE -ne 0) { throw 'Install 64-bit Python 3.13 for Windows, then run setup again.' }
            & $converterSystemPython.Source -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the .venv folder.' }
    }
    & $converterPython -c $converterPythonCheck
    if ($LASTEXITCODE -ne 0) { throw 'The .venv folder needs 64-bit Python 3.13. Remove .venv and run setup again.' }
    Write-Host 'Installing Python packages...'
    & $converterPython -m pip install --disable-pip-version-check --quiet -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'The Python dependencies could not be installed.' }

    $converterTessdata = Join-Path $PSScriptRoot 'tessdata'
    $converterEnglish = Join-Path $converterTessdata 'eng.traineddata'
    $converterEnglishHash = '7D4322BD2A7749724879683FC3912CB542F19906C83BCC1A52132556427170B2'
    New-Item -ItemType Directory -Path $converterTessdata -Force | Out-Null
    $converterDownload = $null
    try {
        if (-not (Test-Path -LiteralPath $converterEnglish) -or
            (Get-FileHash -LiteralPath $converterEnglish).Hash -ne $converterEnglishHash) {
            Write-Host 'Downloading English OCR data...'
            $converterDownload = Join-Path $converterTessdata ('eng.' + [guid]::NewGuid().ToString('N') + '.download')
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 30 -Uri 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata' -OutFile $converterDownload
            if ((Get-FileHash -LiteralPath $converterDownload).Hash -ne $converterEnglishHash) {
                throw 'Downloaded OCR data did not match its expected hash.'
            }
            Move-Item -LiteralPath $converterDownload -Destination $converterEnglish -Force
        }
    }
    catch {
        Write-Warning "English OCR setup is incomplete. Other tools will still work. $($_.Exception.Message)"
    }
    finally {
        if ($converterDownload -and (Test-Path -LiteralPath $converterDownload)) {
            Remove-Item -LiteralPath $converterDownload
        }
    }

    if (-not $SkipWindowsIntegration) {
        & $converterPython -m converter.setup_windows install
        if ($LASTEXITCODE -ne 0) { throw 'The Explorer integration could not be registered.' }
    }
    Write-Host 'File Converter setup complete.'
}
finally {
    Pop-Location
}
