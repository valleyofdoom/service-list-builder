VERSION = "1.6.4"

# 0x10 and above are user mode services
# https://learn.microsoft.com/en-us/dotnet/api/system.serviceprocess.servicetype?view=net-9.0-pp#fields
USER_MODE_TYPE_THRESHOLD = 0x10

HIVE = "SYSTEM\\CurrentControlSet"

LOAD_HIVE_LINES = f"""@echo off
REM This script was built using service-list-builder v{VERSION}
REM ---> IMPORTANT: Do NOT run this script on any system other than the one it was generated on <---

REM Set drive letter to target
set "DRIVE_LETTER=C"

if not "%DRIVE_LETTER%" == "C" (
    reg load "HKLM\\tempSYSTEM" "%DRIVE_LETTER%:\\Windows\\System32\\config\\SYSTEM"
    if not %errorlevel% == 0 (echo error: failed to load SYSTEM hive && pause && exit /b 1)
    set "HIVE=tempSYSTEM\\ControlSet001"
) else (
    set "HIVE={HIVE}"
)

reg query "HKLM\\%HIVE%" > nul 2>&1 || echo error: hive not exists or is unloaded && pause && exit /b 1
"""

# use lowercase key as the path will be converted to lowercase when comparing
IMAGEPATH_REPLACEMENTS = {
    "\\systemroot\\": "C:\\Windows\\",
    "system32\\": "C:\\Windows\\System32\\",
    "\\??\\": "",
}
