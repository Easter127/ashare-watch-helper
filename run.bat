@echo off
setlocal
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (set "PYEXE=venv\Scripts\python.exe") else (set "PYEXE=python")
%PYEXE% -m pip install --quiet --disable-pip-version-check -r requirements.txt 2>nul
%PYEXE% src\stock_desktop.py
endlocal
