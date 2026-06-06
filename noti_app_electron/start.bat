@echo off
wsl.exe bash -c "cd /home/tom/windows/noti_app_electron && export DISPLAY=:0 && npm start"
