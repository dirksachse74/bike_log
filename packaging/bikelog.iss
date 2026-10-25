; Inno Setup script for Bike Log (per-user install, no admin rights).
; Compiled by Dirk on Windows on 2026-10-25; the commit naming below is untested on Windows.
; Build: packaging\build.ps1 does everything, or after PyInstaller produced dist\BikeLog\ run
;   iscc packaging\bikelog.iss
#define AppVersion "0.1.0"
; Every build is named after the git commit it was built from (BikeLog-0.1.0-<commit>-setup.exe), so an
; old installer cannot be mistaken for a new one. build.ps1 passes /DBuildCommit=...; otherwise the
; commit is read from the PyInstaller output.
#ifndef BuildCommit
  #define CommitFile AddBackslash(SourcePath) + "..\dist\BikeLog\_internal\bikelog\build_commit.txt"
  #if FileExists(CommitFile)
    #define CommitHandle FileOpen(CommitFile)
    #define BuildCommit Trim(FileRead(CommitHandle))
    #expr FileClose(CommitHandle)
  #else
    #define BuildCommit "unknown"
  #endif
#endif

[Setup]
; Fixed AppId: installing a newer version over an older one is an upgrade, not a second app.
AppId={{6A3C2E57-4C1B-4E0B-9D8B-2B7F5C1D9E41}
AppName=Bike Log
AppVersion={#AppVersion}
AppVerName=Bike Log {#AppVersion} ({#BuildCommit})
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Bike Log {#AppVersion} commit {#BuildCommit}
AppPublisher=Dirk Sachse
DefaultDirName={localappdata}\Programs\BikeLog
DefaultGroupName=Bike Log
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=BikeLog-{#AppVersion}-{#BuildCommit}-setup
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
