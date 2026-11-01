; Inno Setup script for Bike Log (per-user install, no admin rights).
; Compiled by Dirk on Windows on 2026-10-25; the commit naming below is untested on Windows.
; Build: packaging\build.ps1 does everything, or after PyInstaller produced dist\BikeLog\ run
;   iscc packaging\bikelog.iss
; Version: taken from the PyInstaller output (build_version.txt, written from bikelog.__version__), so the
; installer can never disagree with the app. A release build is "0.2.0" (installer BikeLog-0.2.0-setup.exe);
; any other build carries its commit, "0.2.0+abc1234" (BikeLog-0.2.0+abc1234-setup.exe).
#ifndef AppVersion
  #define VersionFile AddBackslash(SourcePath) + "..\dist\BikeLog\_internal\bikelog\build_version.txt"
  #if FileExists(VersionFile)
    #define VersionHandle FileOpen(VersionFile)
    #define AppVersion Trim(FileRead(VersionHandle))
    #expr FileClose(VersionHandle)
  #else
    #error dist\BikeLog is missing or old: build BikeLog.exe with PyInstaller first
  #endif
#endif
; Windows wants a plain number for the file version: the part before "+".
#if Pos("+", AppVersion) > 0
  #define NumericVersion Copy(AppVersion, 1, Pos("+", AppVersion) - 1)
#else
  #define NumericVersion AppVersion
#endif

[Setup]
; Fixed AppId: installing a newer version over an older one is an upgrade, not a second app.
AppId={{6A3C2E57-4C1B-4E0B-9D8B-2B7F5C1D9E41}
AppName=Bike Log
AppVersion={#AppVersion}
AppVerName=Bike Log {#AppVersion}
VersionInfoVersion={#NumericVersion}
VersionInfoProductVersion={#NumericVersion}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoDescription=Bike Log {#AppVersion} setup
AppPublisher=Dirk Sachse
DefaultDirName={localappdata}\Programs\BikeLog
DefaultGroupName=Bike Log
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=BikeLog-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Close a running Bike Log before upgrading (the launcher holds a lock file; see single_instance.py).
CloseApplications=yes
UninstallDisplayName=Bike Log

[Files]
Source: "..\dist\BikeLog\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Bike Log"; Filename: "{app}\BikeLog.exe"
Name: "{userdesktop}\Bike Log"; Filename: "{app}\BikeLog.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\BikeLog.exe"; Description: "Start Bike Log"; Flags: nowait postinstall skipifsilent

; User data lives in %LOCALAPPDATA%\BikeLog (database, backups, logs). It is outside {app} and is
; deliberately NOT removed on uninstall.
