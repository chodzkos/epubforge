; Inno Setup — instalator EpubForge (Windows).
; Pakuje wynik buildu ONEDIR: dist\epubforge\ (zob. epubforge-dir.spec).
; Wersję można nadpisać:  ISCC /DMyAppVersion=1.0.0 installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-dev"
#endif

#define MyAppName "EpubForge"
#define MyAppPublisher "chodzkos"
#define MyAppURL "https://github.com/chodzkos/epubforge"
#define MyAppExeName "epubforge.exe"

; Ikona: prawdziwa z assets, gdy dostarczona; inaczej placeholder z build/.
#define AssetsIcon "..\src\epubforge\gui\assets\icon.ico"
#if FileExists(AssetsIcon)
  #define AppIcon AssetsIcon
#else
  #define AppIcon "icon.ico"
#endif

[Setup]
AppId={{8E7B2C1A-EPUB-FORGE-0001-CHODZKOS0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=dist
OutputBaseFilename=epubforge-setup
SetupIconFile={#AppIcon}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Cała zawartość folderu ONEDIR.
Source: "dist\epubforge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
