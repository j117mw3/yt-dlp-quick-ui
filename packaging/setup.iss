#ifndef StageDir
  #error StageDir must be set to the built application directory.
#endif
#ifndef ReleaseDir
  #error ReleaseDir must be set to the release output directory.
#endif
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{5D2E36A5-4E09-4C51-B9B9-60EF77CB45A6}
AppName=yt-dlp Quick UI
AppVersion={#AppVersion}
AppPublisher=j117mw3
AppPublisherURL=https://github.com/j117mw3/yt-dlp-quick-ui
AppSupportURL=https://github.com/j117mw3/yt-dlp-quick-ui/issues
AppUpdatesURL=https://github.com/j117mw3/yt-dlp-quick-ui/releases
DefaultDirName={localappdata}\Programs\yt-dlp Quick UI
DefaultGroupName=yt-dlp Quick UI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
UninstallDisplayName=yt-dlp Quick UI
UninstallDisplayIcon={app}\yt-dlp Quick UI.exe
OutputDir={#ReleaseDir}
OutputBaseFilename=yt-dlp-quick-ui-setup-v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
RestartApplications=no
SetupLogging=yes
VersionInfoCompany=j117mw3
VersionInfoProductName=yt-dlp Quick UI
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription=yt-dlp Quick UI installer
VersionInfoCopyright=Copyright (c) 2026 j117mw3

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\yt-dlp Quick UI"; Filename: "{app}\yt-dlp Quick UI.exe"
Name: "{autodesktop}\yt-dlp Quick UI"; Filename: "{app}\yt-dlp Quick UI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\yt-dlp Quick UI.exe"; Description: "Launch yt-dlp Quick UI"; Flags: nowait postinstall skipifsilent

