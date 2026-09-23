; Inno Setup script for "Quantum Trading Setup.exe".
;
;   ISCC /DSourceDir=<built app folder> /DAppVersion=0.2.0 /O<out dir> packaging\windows_installer.iss
;
; SourceDir is the folder packaging/build.py writes (dist\quantum-trading-windows-x64).
; Installs per user, so no administrator prompt, into
; %LOCALAPPDATA%\Programs\Quantum Trading.  That folder is the user's own and
; writable, so the paper book (live_state.json) is saved beside the program and
; survives updates: installing a newer version replaces the program files and
; leaves the book alone.  Uninstalling removes the program and asks nothing;
; the book stays unless the user deletes the folder.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Quantum Trading"
#define AppExe "Quantum Trading.exe"

[Setup]
AppId={{71D9327D-E3E6-4D8E-A295-AD46B1587417}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion} (paper trading)
AppPublisher=Quantum Trading
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=Quantum Trading Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} (paper trading)
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Put a {#AppName} icon on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "Paper-trading dashboard"
Name: "{group}\Read me"; Filename: "{app}\README.txt"
Name: "{group}\Simulator in the browser"; Filename: "{app}\quantum-trading.html"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "Open {#AppName} now"; Flags: nowait postinstall skipifsilent
