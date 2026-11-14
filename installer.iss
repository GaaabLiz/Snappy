; Script di esempio Inno Setup per l'installer PySide6

#define MyAppVersion "0.3.0"


[Setup]
AppId={{0f0058d8-3cc1-4707-b86a-ed74d880c26a}}
AppMutex=snappymutex
AppName=Snappy
AppVersion={#MyAppVersion}
DefaultDirName={commonpf}\Snappy
DefaultGroupName=Snappy
OutputDir=Output
OutputBaseFilename=snappy-setup
Compression=lzma
SolidCompression=yes
DisableProgramGroupPage=yes
SetupIconFile=resources\logo2.ico

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Files]
Source: "dist\snappy\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Snappy"; Filename: "{app}\snappy.exe"; IconFilename: "{app}\snappy.exe"

[Run]
Filename: "{app}\snappy.exe"; Description: "Avvia Snappy"; Flags: nowait postinstall skipifsilent
