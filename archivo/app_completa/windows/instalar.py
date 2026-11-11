"""Instalación sin ejecutables propios (la llama Instalar.bat con el python.exe oficial que va en el ZIP).

Por qué así: Smart App Control / Control de aplicaciones de Windows bloquea cualquier .exe sin firma digital, también
el instalador de Inno Setup (error 4551 "No se pudo ejecutar archivo en la carpeta temporal"). Aquí no se ejecuta
nada nuestro: solo python.exe (firmado por la Python Software Foundation) leyendo ficheros .py.

1. Copia python\\ y app\\ a %LOCALAPPDATA%\\Programs\\ComparadorOfertas (sustituye la versión anterior).
2. Quita la marca "descargado de Internet" de lo copiado.
3. Crea los accesos directos "Comparador de ofertas" (escritorio y menú Inicio) -> python.exe + lanzador.py.
Los datos (obras, precios.db) están en %LOCALAPPDATA%\\ComparadorOfertas y no se tocan.
Uso:  python\\python.exe app\\automatizador\\windows\\instalar.py [--destino CARPETA] [--sin-accesos] [--no-abrir]
"""
import os
import shutil
import subprocess
import sys

ORIGEN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _arg(nombre, defecto=None):
    if nombre in sys.argv:
        return sys.argv[sys.argv.index(nombre) + 1]
    return defecto


def _ps(orden):
    """Ejecuta una orden de PowerShell (sin fichero .ps1, que Smart App Control podría bloquear)."""
    return subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', orden],
                          capture_output=True, text=True)


def _comillas(s):
    return "'" + s.replace("'", "''") + "'"


def accesos_directos(dest):
    py = os.path.join(dest, 'python', 'python.exe')
    lanzador = os.path.join(dest, 'app', 'automatizador', 'windows', 'lanzador.py')
    orden = ("$w = New-Object -ComObject WScript.Shell; "
             "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { "
             "$s = $w.CreateShortcut((Join-Path $d 'Comparador de ofertas.lnk')); "
             "$s.TargetPath = %s; $s.Arguments = %s; $s.WorkingDirectory = %s; $s.IconLocation = %s; $s.Save() }"
             % (_comillas(py), _comillas('"%s"' % lanzador), _comillas(os.path.join(dest, 'app')),
                _comillas(os.path.join(dest, 'icono.ico'))))
    r = _ps(orden)
    return r.returncode == 0, (r.stderr or '').strip()


def main():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    dest = os.path.abspath(_arg('--destino', os.path.join(base, 'Programs', 'ComparadorOfertas')))
    print('Instalando Comparador de ofertas en:\n  %s\n' % dest)
    if os.path.normcase(dest) == os.path.normcase(ORIGEN):
        raise SystemExit('Ya está instalado aquí; ejecuta Instalar.bat desde la carpeta descomprimida del ZIP.')
    os.makedirs(dest, exist_ok=True)
    # versión anterior (también la del instalador antiguo con PyInstaller); los datos están en otra carpeta
    for viejo in ('python', 'app', '_internal'):
        shutil.rmtree(os.path.join(dest, viejo), ignore_errors=True)
    for viejo in ('ComparadorOfertas.exe', 'unins000.exe', 'unins000.dat'):
        try:
            os.remove(os.path.join(dest, viejo))
        except OSError:
            pass
    print('Copiando ficheros...')
    shutil.copytree(os.path.join(ORIGEN, 'python'), os.path.join(dest, 'python'))
    shutil.copytree(os.path.join(ORIGEN, 'app'), os.path.join(dest, 'app'))
    for f in ('icono.ico', 'Abrir Comparador.bat', 'LEEME.txt'):
        if os.path.exists(os.path.join(ORIGEN, f)):
            shutil.copy2(os.path.join(ORIGEN, f), os.path.join(dest, f))
    if os.name == 'nt':
        _ps('Get-ChildItem -LiteralPath %s -Recurse -File | Unblock-File' % _comillas(dest))
        if '--sin-accesos' not in sys.argv:
            ok, error = accesos_directos(dest)
            if ok:
                print('Acceso directo "Comparador de ofertas" creado en el escritorio y en el menú Inicio.')
            else:
                print('No se pudo crear el acceso directo (%s).\nAbre la app con:  %s'
                      % (error[:200], os.path.join(dest, 'Abrir Comparador.bat')))
    print('\nInstalación terminada.')
    if os.name == 'nt' and '--no-abrir' not in sys.argv:
        print('Abriendo la app...')
        subprocess.Popen(['cmd', '/c', 'start', '', os.path.join(dest, 'Abrir Comparador.bat')])


if __name__ == '__main__':
    main()
