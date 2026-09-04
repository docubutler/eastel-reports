@echo off
setlocal

REM Simple Windows drag-and-drop uploader.
REM Drop a file onto this .bat (or its shortcut) and it runs:
REM   aws s3 cp "<dropped file>" s3://anchor-prod-ap-southeast-5/build-images/

set "BUCKET=s3://anchor-prod-ap-southeast-5/build-images"

if "%~1"=="" (
    echo No file detected.
    echo Drag and drop a file onto this script.
    pause
    exit /b 1
)

set "SRC=%~1"

echo Uploading: "%SRC%"
echo Target:    %BUCKET%/
echo.
aws s3 cp "%SRC%" %BUCKET%/
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo Upload FAILED ^(exit code %RC%^). Check AWS CLI / credentials.
) else (
    echo Done. Uploaded to %BUCKET%/%~nx1
)
pause
endlocal
