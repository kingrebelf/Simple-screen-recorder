# Build on 64-bit Windows in PowerShell. Requires Python 3.11, FFmpeg with libx264,
# and Inno Setup 6. Run from the repository root.
$ErrorActionPreference = 'Stop'
$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction Stop).Source
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Install Inno Setup 6 before building.' }
py -3.11 -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed.' }
$icon = (Resolve-Path 'app.ico').Path
py -3.11 -m PyInstaller --noconfirm --clean --windowed --onedir --name 'Simple Screen Recorder' --icon $icon --add-data "${icon};." --collect-all soundcard --collect-all soundfile --collect-all customtkinter app.py
if ($LASTEXITCODE) { throw 'Application build failed.' }
Copy-Item $ffmpeg 'dist\Simple Screen Recorder\_internal\ffmpeg.exe'
$ffmpegRoot = Split-Path (Split-Path $ffmpeg)
if (-not (Test-Path (Join-Path $ffmpegRoot 'LICENSE'))) { throw 'FFmpeg LICENSE not found alongside the distribution; supply a complete FFmpeg distribution.' }
Copy-Item (Join-Path $ffmpegRoot 'LICENSE') 'dist\Simple Screen Recorder\FFmpeg-LICENSE.txt'
& $iscc installer.iss
if ($LASTEXITCODE) { throw 'Installer build failed.' }

