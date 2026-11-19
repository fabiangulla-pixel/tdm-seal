; Instalador de TDM Seal (Inno Setup).
; Genera un Setup.exe que instala TDM-Seal.exe con accesos directos en el
; Menú Inicio y (opcional) el Escritorio, y registra un desinstalador.
;
; Requiere que dist\TDM-Seal.exe ya exista (ver scripts\build_exe.bat).
; Compilar con: ISCC.exe scripts\installer.iss

#define MyAppName "TDM Seal"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TDM Seal"
#define MyAppExeName "TDM-Seal.exe"

[Setup]
AppId={{6C1E1E4E-7B7C-4E9C-9C5A-3E7A5F0A9B10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=TDM-Seal-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos adicionales:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\guia-10-minutos.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\aviso-visible.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\xmp-namespace-iscc.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent
