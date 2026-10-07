Write-Host "Building Sudarshana Chakra Application..." -ForegroundColor Cyan
.\.venv\Scripts\pyinstaller.exe installer\SudarshanaChakra.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build main application!" -ForegroundColor Red
    exit 1
}

Write-Host "Main Application built successfully. Now building Setup Wizard..." -ForegroundColor Cyan
.\.venv\Scripts\pyinstaller.exe installer\SudarshanaChakra_Setup.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to build setup wizard!" -ForegroundColor Red
    exit 1
}

Write-Host "Build complete! Setup is located in dist\SudarshanaChakra_Setup.exe" -ForegroundColor Green
