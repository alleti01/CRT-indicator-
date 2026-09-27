# Install local Tesseract and the cdx_vision Python packages.
# Idempotent. Does not enable trading. Does not store credentials.
$ErrorActionPreference = "Stop"
if (-not $IsWindows -and -not ($env:OS -eq "Windows_NT")) {
    Write-Output "CDX_OCR_INSTALL_WRONG_OS"
    exit 2
}
$existing = @(
    "$env:ProgramFiles\Tesseract-OCR\tesseract.exe",
    "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe",
    "$env:LOCALAPPDATA\Tesseract-OCR\tesseract.exe"
) | Where-Object { Test-Path $_ }
if (-not $existing) {
    $cmd = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($cmd) { $existing = @($cmd.Source) }
}
if (-not $existing) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Output "CDX_TESSERACT_MANUAL_INSTALL_REQUIRED"
        exit 3
    }
    winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements --disable-interactivity
}
python -m pip install -r "$PSScriptRoot\..\cdx_vision\requirements.txt"
python -m cdx_vision.doctor
python -m unittest cdx_vision.tests.test_vision cdx_vision.tests.test_tesseract_cmd -q
Write-Output "CDX_VISION_ENABLED remains false"
