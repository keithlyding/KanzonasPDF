; KanzonasPDF installer (Inno Setup 6). Built by the GitHub workflow:
;   ISCC.exe /DMyAppVersion=1.0 installer\KanzonasPDF.iss
; Installs for the current user (no administrator rights needed) unless the user picks
; "all users" on the first page.

#ifndef MyAppVersion
  #define MyAppVersion "0.0"
#endif
#define MyAppName "KanzonasPDF"
#define MyAppExe "KanzonasPDF.exe"

[Setup]
AppId={{8F4C2A61-5B7E-4D3A-9C1F-2E6B7A9D4C11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=KanzonasPDF
AppPublisherURL=https://github.com/keithlyding/KanzonasPDF
AppSupportURL=https://github.com/keithlyding/KanzonasPDF
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename={#MyAppName}-v{#MyAppVersion}-setup
SetupIconFile=..\assets\kanzonas.ico
WizardImageFile=..\assets\wizard-large.bmp
WizardSmallImageFile=..\assets\wizard-small.bmp
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "pdfdefault"; Description: "Offer {#MyAppName} as an app for opening PDF files"

[Files]
Source: "..\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; "Open with" entry for PDFs. Windows 10/11 never let an installer silently take over as the
; default app: the first time, Windows asks which app to use (pick KanzonasPDF, "Always").
Root: HKA; Subkey: "Software\Classes\KanzonasPDF.Document"; ValueType: string; ValueData: "PDF document"; Flags: uninsdeletekey; Tasks: pdfdefault
Root: HKA; Subkey: "Software\Classes\KanzonasPDF.Document\DefaultIcon"; ValueType: string; ValueData: "{app}\{#MyAppExe},0"; Tasks: pdfdefault
Root: HKA; Subkey: "Software\Classes\KanzonasPDF.Document\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Tasks: pdfdefault
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "KanzonasPDF.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: pdfdefault
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent
