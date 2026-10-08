@echo off
rem One-time setup: creates .venv. Lithnode needs nothing beyond Python itself.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
echo Setup done.
