VERSION = "1.5.0"
USER_MODE_TYPES = {16, 32, 96, 288, 80, 272}
HIVE = "SYSTEM\\CurrentControlSet"

LOAD_HIVE_LINES = f"""@echo off
REM This script was built using service-list-builder v{VERSION}
REM Set drive letter to target
set "DRIVE_LETTER=C"

if not "%DRIVE_LETTER%" == "C" (
    reg load "tempSYSTEM" "%DRIVE_LETTER%:\\Windows\\System32\\config\\SYSTEM"
    if not %errorlevel% == 0 (echo error: failed to load SYSTEM hive && pause && exit /b 1)
    set "HIVE=tempSYSTEM\\ControlSet001"
) else (
    set "HIVE={HIVE}"
)

reg query "HKLM\\%HIVE%" > nul 2>&1 || echo error: hive not exists or is unloaded && pause && exit /b 1
"""
