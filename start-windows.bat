@echo off
setlocal

cd /d "%~dp0"

py -3 -m pip install -r windows-runtime-requirements.txt
py -3 desktop_app.py
