@echo off
setlocal
cd /d "%~dp0"

rem Chon Python: uu tien "py -3", neu khong co thi dung "python".
set "PY=py -3"
%PY% --version >nul 2>&1 || set "PY=python"
%PY% --version >nul 2>&1 || (
  echo Khong tim thay Python 3.10+. Cai tu https://www.python.org/downloads/ ^(tick "Add to PATH"^).
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto :fail
)
rem Chi cai lai thu vien khi lan cai truoc chua xong hoac requirements.txt thay doi.
fc /b requirements.txt ".venv\installed.txt" >nul 2>&1 || (
  ".venv\Scripts\python" -m pip install -r requirements.txt || goto :fail
  copy /y requirements.txt ".venv\installed.txt" >nul
)

".venv\Scripts\python" -m video_studio || goto :fail
exit /b 0

:fail
echo.
echo Co loi xay ra. Xem thong bao phia tren.
pause
exit /b 1
