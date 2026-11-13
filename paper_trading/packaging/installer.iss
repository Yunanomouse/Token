; Inno Setup script for "Paper Trading Setup.exe".
;
;   ISCC /DSourceDir=<built program folder> /DAppVersion=1.0.0 [/DSetupIcon=<.ico>] /O<out dir> paper_trading\packaging\installer.iss
;
; SourceDir is the folder paper_trading/packaging/build.py writes
; (dist\paper-trading-windows-x64).  Installs for the current user only, so
; there is no administrator prompt, into %LOCALAPPDATA%\Programs\Paper Trading,
; with a Start menu entry, an optional desktop icon and an entry in
; Settings > Apps for uninstalling.
;
; The account is NOT in the program folder: the program keeps it in
; %APPDATA%\Paper Trading (window.py's data_home()).  Installing a newer
; version or uninstalling never touches that folder, so the account carries
; over; delete the folder by hand to start completely fresh.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Paper Trading"
#define AppExe "Paper Trading.exe"

[Setup]
; Not the Quantum Trading AppId: the two programs install and uninstall separately.
AppId={{5C0E7A51-3B8F-4F2D-9C61-7E4A2B9D8F13}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} (pretend money)
AppPublisher=Paper Trading
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=Paper Trading Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} (pretend money)
; Close a running copy (it holds its files open) before replacing or removing them.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
#ifdef SetupIcon
SetupIconFile={#SetupIcon}
#endif

[Messages]
FinishedLabel=Paper Trading is installed. Open it from the Start menu or the desktop icon.%n%nPretend money only: no broker is connected.%n%nYour account is kept in your own AppData\Roaming\Paper Trading folder, not in the program folder, so it stays when you install a newer version or uninstall.
ConfirmUninstall=Remove %1 from this computer?%n%nYour pretend-money account (in AppData\Roaming\Paper Trading) is kept; delete that folder yourself if you want it gone.

[Tasks]
Name: "desktopicon"; Description: "Put a {#AppName} icon on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Program files from an older version that the new one no longer has.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Buy and sell by hand with pretend money"
Name: "{group}\Read me"; Filename: "{win}\notepad.exe"; Parameters: """{app}\README.md"""
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Buy and sell by hand with pretend money"; Tasks: desktopicon

[UninstallRun]
; In case Windows' Restart Manager couldn't close it: a running copy keeps its files locked.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#AppExe}"""; Flags: runhidden; RunOnceId: "StopApp"

[UninstallDelete]
; Only the program folder itself (the account is elsewhere and is kept).
Type: dirifempty; Name: "{app}"

[Run]
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
