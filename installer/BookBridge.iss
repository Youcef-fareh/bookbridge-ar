[Setup]
AppName=BookBridge
AppVersion=1.0.0
AppId=BookBridge
AppPublisher=BookBridge
AppPublisherURL=https://github.com/Youcef-fareh/bookbridge-ar
AppSupportURL=https://github.com/Youcef-fareh/bookbridge-ar
AppUpdatesURL=https://github.com/Youcef-fareh/bookbridge-ar
DefaultDirName={autopf}\BookBridge
DefaultGroupName=BookBridge
Compression=lzma
SolidCompression=yes
OutputDir=..\dist\installer
OutputBaseFilename=BookBridge-Setup
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
LicenseFile=..\LICENSE
InfoBeforeFile=..\README.md
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\BookBridge.exe
ShowLanguageDialog=no
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\app\BookBridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\sample_data\*"; DestDir: "{app}\sample_data"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{commonprograms}\BookBridge"; Filename: "{app}\BookBridge.exe"; WorkingDir: "{app}"; IconFilename: "{app}\BookBridge.exe"
Name: "{commondesktop}\BookBridge"; Filename: "{app}\BookBridge.exe"; WorkingDir: "{app}"; IconFilename: "{app}\BookBridge.exe"

[Run]
Filename: "{app}\BookBridge.exe"; Description: "Launch BookBridge"; Flags: nowait postinstall skipifsilent
