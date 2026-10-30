[Setup]
AppId={{4DE7354F-5513-4A07-B894-1EA16F3F644E}
AppName=Simple Screen Recorder
AppVersion=1.1.0
AppPublisher=Simple Screen Recorder
DefaultDirName={localappdata}\Programs\Simple Screen Recorder
DefaultGroupName=Simple Screen Recorder
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Simple-Screen-Recorder-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Simple Screen Recorder.exe
SetupIconFile=app.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Files]
Source: "dist\Simple Screen Recorder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Simple Screen Recorder"; Filename: "{app}\Simple Screen Recorder.exe"
Name: "{autodesktop}\Simple Screen Recorder"; Filename: "{app}\Simple Screen Recorder.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\Simple Screen Recorder.exe"; Description: "Launch Simple Screen Recorder"; Flags: nowait postinstall skipifsilent
