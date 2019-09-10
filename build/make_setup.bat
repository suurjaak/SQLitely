:: Creates NSIS setup file for executable in current directory named 
:: sqlitely_%conf.Version%[_x64].exe, or filename given in argument.
:: Processor architecture is determined from OS environment.
::
:: @author    Erki Suurjaak
:: @created   21.08.2019
:: @modified  21.08.2019
@echo off
setlocal EnableDelayedExpansion
set INITIAL_DIR=%CD%
cd %0\..
set SETUPDIR=%CD%

cd ../sqlitely
if defined PROGRAMW6432 set SUFFIX64=_x64
if [%1] == [] (
    for /f %%I in ('python -c "import conf; print conf.Version"') do set VERSION=%%I
    set EXEFILE=%INITIAL_DIR%\sqlitely_!VERSION!%SUFFIX64%.exe
) else (
    for /f "tokens=2 delims=_ " %%a in ("%~n1") do set VERSION=%%a
    set EXEFILE=%INITIAL_DIR%\%1
)

if not exist "%EXEFILE%" echo %EXEFILE% missing. && goto :END
set NSISDIR=C:\Program Files (x86)\Nullsoft Scriptable Install System
if not exist "%NSISDIR%" set NSISDIR=C:\Program Files\Nullsoft Scriptable Install System
if not exist "%NSISDIR%" set NSISDIR=C:\Program Files (x86)\NSIS
if not exist "%NSISDIR%" set NSISDIR=C:\Program Files\NSIS
if not exist "%NSISDIR%\makensis.exe" echo NSIS not found. && goto :END

echo Creating installer for SQLitely %VERSION%%SUFFIX64%.
cd %SETUPDIR%
set DESTFILE=sqlitely_%VERSION%%SUFFIX64%_setup.exe
if exist "%DESTFILE%" echo Removing previous %DESTFILE%. & del "%DESTFILE%"
if exist sqlitely.exe del sqlitely.exe
copy /V "%EXEFILE%" sqlitely.exe > NUL 2>&1
"%NSISDIR%\makensis.exe" /DPRODUCT_VERSION=%VERSION% /DSUFFIX64=%SUFFIX64% "%SETUPDIR%\exe_setup.nsi"
del sqlitely.exe > NUL 2>&1
if exist "%DESTFILE%" echo. & echo Successfully created SQLitely source distribution %DESTFILE%.
move "%DESTFILE%" "%INITIAL_DIR%" > NUL 2>&1

:END
cd "%INITIAL_DIR%"
