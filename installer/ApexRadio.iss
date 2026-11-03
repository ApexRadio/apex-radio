; Installateur Windows d'Apex Radio (Inno Setup 6)
; Construit automatiquement par GitHub Actions (.github/workflows/installer.yml)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B0E7C4F-4C1D-4B8E-9C55-A9E0A1B2C3D4}
AppName=Apex Radio
AppVersion={#AppVersion}
AppPublisher=Apex Radio
AppPublisherURL=https://github.com/laurent22230/apex-radio
DefaultDirName={localappdata}\Programs\Apex Radio
DefaultGroupName=Apex Radio
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ApexRadio-Setup-{#AppVersion}
SetupIconFile=..\build\app\apex.ico
UninstallDisplayIcon={app}\ApexRadio.exe
CloseApplications=force
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\build\app\LICENSE
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\build\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Apex Radio"; Filename: "{app}\ApexRadio.exe"; WorkingDir: "{app}"
Name: "{group}\Apex Radio (demo)"; Filename: "{app}\ApexRadio.exe"; Parameters: "--demo"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,Apex Radio}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Apex Radio"; Filename: "{app}\ApexRadio.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ApexRadio.exe"; Parameters: "--demo"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Apex Radio}"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\__pycache__"
