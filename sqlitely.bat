@echo off
setlocal
set PYTHONPATH=%~dp0src;%PYTHONPATH%
start pythonw -m sqlitely %*
endlocal
