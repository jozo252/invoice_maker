@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
if not exist ".venv\Scripts\python.exe" (
  echo Chyba lokalne Python prostredie .venv. Postup je v README_CRM.md.
  goto problem
)
if not exist "static\crm\vendor\ocr\tesseract.min.js" (
  ".venv\Scripts\python.exe" scripts\prepare_receipt_ocr.py
  if errorlevel 1 goto problem
)
".venv\Scripts\python.exe" crm_local.py --init --open
if errorlevel 1 goto problem
exit /b
:problem
echo CRM sa nepodarilo spustit. Precitaj chybu nad tymto textom.
pause
