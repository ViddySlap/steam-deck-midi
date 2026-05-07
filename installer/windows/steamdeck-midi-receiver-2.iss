#define AppName "STEAMDECK MIDI Receiver 2"
#define AppExeName "STEAMDECK-MIDI-RECEIVER-2.exe"
#ifndef AppVersion
#define AppVersion "0.1.0"
#endif
#define AppPublisher "ViddySlap"
#define AppURL "https://github.com/ViddySlap/steam-deck-midi"

[Setup]
AppId={{82164218-F8E4-4DC5-AB5A-711BB4189A4B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductTextVersion={#AppVersion}
DefaultDirName={autopf}\STEAMDECK MIDI Receiver 2
DefaultGroupName={#AppName}
SetupIconFile=..\..\assets\windows\install-wizard.ico
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\..\installer-output
OutputBaseFilename=STEAMDECK-MIDI-RECEIVER-2-Setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=STEAMDECK-MIDI-RECEIVER-2.exe
RestartApplications=no

[Dirs]
Name: "{app}\config"; Permissions: users-modify
Name: "{app}\config\presets"; Permissions: users-modify
Name: "{app}\config\engines"; Permissions: users-modify
Name: "{app}\config\engines.factory"; Permissions: users-modify

[Files]
Source: "..\..\dist\STEAMDECK-MIDI-RECEIVER-2.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\assets\windows\receiver.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\config\windows_midi_map.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\..\config\windows_receiver_settings.example.json"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\..\config\windows_receiver_settings.example.json"; DestDir: "{app}\config"; DestName: "windows_receiver_settings.local.json"; Flags: onlyifdoesntexist
Source: "..\..\scripts\windows\start_installed_receiver_v2.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\config\presets\default.json"; DestDir: "{app}\config\presets"; Flags: onlyifdoesntexist
Source: "..\..\config\macro_library.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist
Source: "..\..\config\engines\README.md"; DestDir: "{app}\config\engines"; Flags: onlyifdoesntexist
Source: "..\..\config\engines.factory\*.json"; DestDir: "{app}\config\engines.factory"; Flags: ignoreversion
Source: "..\..\config\actions.yaml"; DestDir: "{app}\config"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\STEAMDECK MIDI Receiver 2"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoLogo -NoExit -File ""{app}\scripts\start_installed_receiver_v2.ps1"" -InstallRoot ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\receiver.ico"
Name: "{group}\STEAMDECK MIDI Receiver 2"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoLogo -NoExit -File ""{app}\scripts\start_installed_receiver_v2.ps1"" -InstallRoot ""{app}"""; WorkingDir: "{app}"; IconFilename: "{app}\receiver.ico"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoLogo -NoExit -File ""{app}\scripts\start_installed_receiver_v2.ps1"" -InstallRoot ""{app}"""; Description: "Launch STEAMDECK MIDI Receiver 2"; Flags: nowait postinstall skipifsilent
