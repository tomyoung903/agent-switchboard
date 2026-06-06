@echo off
set ELECTRON_RUN_AS_NODE=

set "NTFY_ENV_FILE=C:\noti_app_electron\noti_ntfy.env"
if exist "%NTFY_ENV_FILE%" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%NTFY_ENV_FILE%") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

"C:\noti_app_electron\node_modules\electron\dist\electron.exe" C:\noti_app_electron\main.js >> C:\noti_app_electron\start_out.log 2>&1
