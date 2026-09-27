# CDX vision install

Windows 11 (10.0.26200). Python 3.12.10 at `C:\Users\allet\AppData\Local\Programs\Python\Python312\python.exe`. No virtualenv. Package manager for Python is pip. System package manager is winget. Chocolatey is not installed.

Tesseract was not on PATH and not in `C:\Program Files\Tesseract-OCR`.

`winget install --id UB-Mannheim.TesseractOCR` downloaded the official 5.4.0.20240606 installer and verified its hash, then the install was canceled (`0x800704c7`). A second winget attempt and a user-folder silent install of the same signed installer were also canceled before the files were written. That dialog needs an approval click. Nothing was taken from an unofficial site.

Python packages installed into that interpreter:

- pytesseract 0.3.13
- mss 10.2.0
- pywin32 311
- opencv-python 4.14.0.94

Pillow 12.3.0 and numpy 2.5.2 were already present.

`python -m cdx_vision.doctor` reports `TESSERACT MISSING` and exits 1. The synthetic image is ready in the doctor command and will run once `tesseract.exe` exists.

`python -m cdx_vision.calibrate` found no TradingView window. It listed Chrome windows and did not pick one. Status: CALIBRATION_PENDING_TRADINGVIEW.

Vision flags were left off. `CDX_VISION_ENABLED` is false. Shadow-only and execution-disabled stay the defaults. `may_route_orders()` is false.

Vision unit tests: 12 passed (`test_vision` and `test_tesseract_cmd`).
