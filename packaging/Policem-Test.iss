#define AppName "Policem - Windows 10 Test"
#define AppVersion "0.1.0-test"
[Setup]
AppId={{A5E6C4A1-49D9-4D8C-BB21-90B54D8C2D38}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\PolicemTest
DefaultGroupName=Policem Test
OutputDir=..\dist-installer
OutputBaseFilename=Policem_Setup_Win10_TEST
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\PolicemServer.exe
[Files]
Source: "..\dist\PolicemServer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "run-win10-test.cmd"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{autodesktop}\Policem TEST"; Filename: "{app}\run-win10-test.cmd"; WorkingDir: "{app}"
Name: "{group}\Policem TEST"; Filename: "{app}\run-win10-test.cmd"; WorkingDir: "{app}"
[Run]
Filename: "{app}\run-win10-test.cmd"; Description: "Policem TEST uygulamasini baslat"; Flags: postinstall nowait skipifsilent shellexec
