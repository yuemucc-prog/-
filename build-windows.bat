@echo off
setlocal

cd /d "%~dp0"

py -3 -m pip install --upgrade pip
py -3 -m pip install -r pyinstaller-build-requirements.txt
py -3 -m PyInstaller --noconfirm BossLoopTimer.spec

where iscc >nul 2>nul
if %errorlevel%==0 (
  iscc BossLoopTimer.iss
)

echo.
echo Build complete:
echo %cd%\dist\BossLoopTimer.exe
if exist "%cd%\dist-installer\BossLoopTimer-Setup.exe" echo %cd%\dist-installer\BossLoopTimer-Setup.exe
pause
