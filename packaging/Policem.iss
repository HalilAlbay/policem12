#define AppName "Parantez Policem Pilot"
#define AppVersion "0.1.0-pilot"
#define AppPublisher "Parantez"
[Setup]
AppId={{B89A62F1-8B55-4B7D-B2F7-8AC5C88B6E7A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Policem
DefaultGroupName=Policem
OutputDir=..\dist-installer
OutputBaseFilename=Policem_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\PolicemServer.exe
[Files]
Source: "..\dist\PolicemServer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\WinSW\PolicemService.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "PolicemService.xml"; DestDir: "{app}"; Flags: ignoreversion
[Dirs]
Name: "{commonappdata}\Policem\data"; Permissions: admins-full system-full
Name: "{commonappdata}\Policem\data\documents"; Permissions: admins-full system-full
Name: "{commonappdata}\Policem\logs"; Permissions: admins-full system-full
Name: "{commonappdata}\Policem\backups"; Permissions: admins-full system-full
[Run]
Filename: "{app}\PolicemService.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; Check: not ServiceExists
[UninstallRun]
Filename: "{app}\PolicemService.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated
[Code]
function ServiceExists(): Boolean;
var ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{sys}\sc.exe'), 'query PolicemServer', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;
function InitializeSetup(): Boolean;
begin
  Result := True;
  if ServiceExists() then begin
    MsgBox('An existing Poliçem service was found. Stop and back up the service, then uninstall the old application before installing this pilot package. Data under ProgramData will be preserved.', mbError, MB_OK);
    Result := False;
  end;
end;
