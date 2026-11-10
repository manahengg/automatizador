; Instalador de Windows (Inno Setup 6). Lo compila el flujo .github/workflows/windows.yml:
;   ISCC.exe /DVersion=1.0.0 /DOrigen=<carpeta creada por windows\empaquetar.py> windows\instalador.iss
;
; Se instala el Python embebido OFICIAL (firmado) + el código de la app, y los accesos directos abren
;   python\python.exe app\automatizador\windows\lanzador.py
; en lugar de un .exe propio sin firmar (que Smart App Control / Control de aplicaciones de Windows bloquea).
#ifndef Version
  #define Version "1.0.0"
#endif
#ifndef Origen
  #define Origen "..\..\paquete"
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
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\icono.ico
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; restos de versiones anteriores, que usaban un .exe hecho con PyInstaller
Type: files; Name: "{app}\ComparadorOfertas.exe"
Type: filesandordirs; Name: "{app}\_internal"
; el código de la app se reemplaza entero en cada actualización
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Comparador de ofertas"; Filename: "{app}\python\python.exe"; Parameters: """{app}\app\automatizador\windows\lanzador.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\icono.ico"
Name: "{group}\Carpeta de datos (obras y base de precios)"; Filename: "{localappdata}\ComparadorOfertas"
Name: "{group}\Desinstalar"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Comparador de ofertas"; Filename: "{app}\python\python.exe"; Parameters: """{app}\app\automatizador\windows\lanzador.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\icono.ico"; Tasks: escritorio

[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\app\automatizador\windows\lanzador.py"""; WorkingDir: "{app}\app"; Description: "Abrir ahora el Comparador de ofertas"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; cachés de Python que se crean al usar la app
Type: filesandordirs; Name: "{app}\app"

; Los datos (%LOCALAPPDATA%\ComparadorOfertas) NO se borran al desinstalar: la base de datos de precios se conserva.
