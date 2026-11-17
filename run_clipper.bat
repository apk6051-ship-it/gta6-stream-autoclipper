@echo off
cd /d "%~dp0"
echo Starting GTA 6 Auto-Clipper Session...
python -m src.main
echo Session finished with exit code %errorlevel%
