"""Localización de las herramientas externas opcionales (Java, veraPDF, EPUBCheck).

Orden de búsqueda:

1. variables de entorno: `TDMSEAL_JAVA`, `TDMSEAL_VERAPDF`, `TDMSEAL_EPUBCHECK_JAR`;
2. la carpeta de herramientas de TDM Seal: `TDMSEAL_TOOLS` o, por defecto,
   `%LOCALAPPDATA%\\TDMSeal\\tools` (ahí las deja
   `scripts\\instalar_herramientas.ps1`): `jre\\bin\\java.exe`,
   `verapdf\\verapdf.bat`, `epubcheck-*\\epubcheck.jar`;
3. el PATH del sistema.

Si no se encuentran, las validaciones quedan `SKIPPED` y el sellado sigue.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def tools_dir() -> Path:
    env = os.environ.get("TDMSEAL_TOOLS")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "TDMSeal" / "tools"


def find_java() -> str | None:
    env = os.environ.get("TDMSEAL_JAVA")
    if env and Path(env).exists():
        return env
    exe = "java.exe" if sys.platform == "win32" else "java"
    bundled = tools_dir() / "jre" / "bin" / exe
    if bundled.exists():
        return str(bundled)
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / exe).exists():
        return str(Path(java_home) / "bin" / exe)
    return shutil.which("java")


def no_window() -> dict:
    """kwargs de subprocess para no abrir ventanas de consola desde la GUI/.exe."""
    if sys.platform == "win32":
        import subprocess

        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def java_env() -> dict[str, str]:
    """Entorno para lanzar scripts Java (veraPDF lee JAVACMD)."""
    env = dict(os.environ)
    java = find_java()
    if java:
        env["JAVACMD"] = java
    return env


def find_verapdf() -> list[str] | None:
    env = os.environ.get("TDMSEAL_VERAPDF")
    if env and Path(env).exists():
        return [env]
    for candidate in (tools_dir() / "verapdf" / "verapdf.bat", tools_dir() / "verapdf" / "verapdf"):
        if candidate.exists():
            return [str(candidate)]
    for name in ("verapdf", "verapdf.bat", "verapdf.cmd"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def find_epubcheck() -> list[str] | None:
    java = find_java()
    jar = os.environ.get("TDMSEAL_EPUBCHECK_JAR")
    if not (jar and Path(jar).exists()):
        jars = sorted(tools_dir().glob("epubcheck-*/epubcheck.jar"))
        jar = str(jars[-1]) if jars else None
    if jar and java:
        return [java, "-jar", jar]
    for name in ("epubcheck", "epubcheck.bat", "epubcheck.cmd"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


def tools_status() -> dict[str, str | None]:
    """Qué herramientas encontró (para `tdmseal tools` y la GUI)."""
    verapdf = find_verapdf()
    epubcheck = find_epubcheck()
    return {
        "carpeta de herramientas": str(tools_dir()),
        "java": find_java(),
        "verapdf": verapdf[0] if verapdf else None,
        "epubcheck": " ".join(epubcheck) if epubcheck else None,
    }
