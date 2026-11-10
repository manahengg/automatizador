; Instalador de Windows (Inno Setup 6). Lo compila el flujo .github/workflows/windows.yml:
;   ISCC.exe /DVersion=1.0.0 /DOrigen=<ruta a dist\ComparadorOfertas> windows\instalador.iss
#ifndef Version
  #define Version "1.0.0"
#endif
#ifndef Origen
  #define Origen "..\..\dist\ComparadorOfertas"
#endif

[Setup]
AppId={{6C1C1D5E-2B7A-4C61-9C2E-0A9F3C1E7B21}
AppName=Comparador de ofertas
AppVersion={#Version}
AppPublisher=Comparador de ofertas
DefaultDirName={localappdata}\Programs\ComparadorOfertas
DefaultGroupName=Comparador de ofertas
PrivilegesRequired=lowest
OutputBaseFilename=ComparadorOfertas_Setup_{#Version}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Comparador de ofertas"; Filename: "{app}\ComparadorOfertas.exe"
Name: "{group}\Carpeta de datos (obras y base de precios)"; Filename: "{localappdata}\ComparadorOfertas"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Comparador de ofertas"; Filename: "{app}\ComparadorOfertas.exe"; Tasks: escritorio

[Run]
Filename: "{app}\ComparadorOfertas.exe"; Description: "Abrir ahora el Comparador de ofertas"; Flags: nowait postinstall skipifsilent

; Los datos (%LOCALAPPDATA%\ComparadorOfertas) NO se borran al desinstalar: la base de datos de precios se conserva.
