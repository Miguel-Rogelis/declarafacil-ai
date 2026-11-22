"""Arma el .zip de la extensión.

    python extension/tienda/empaquetar.py            → extension/dist/declarafacil-extension-<versión>.zip
    python extension/tienda/empaquetar.py --tienda   → el mismo, listo para Chrome Web Store

Deja afuera las pruebas, esta carpeta y el README. Con --tienda además quita de manifest.json las
direcciones de desarrollo (localhost, 127.0.0.1): la revisión de la tienda pide permisos mínimos.
Solo usa la librería estándar de Python.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUERA = {"pruebas", "tienda", "dist", "README.md", ".DS_Store"}
DESARROLLO = ("http://localhost", "http://127.0.0.1")


def manifiesto(tienda: bool) -> dict:
    m = json.loads((RAIZ / "manifest.json").read_text(encoding="utf-8"))
    if tienda:
        for cs in m.get("content_scripts", []):
            cs["matches"] = [u for u in cs["matches"] if not u.startswith(DESARROLLO)]
    return m


def empaquetar(tienda: bool = False, destino: Path | None = None) -> Path:
    m = manifiesto(tienda)
    destino = destino or RAIZ / "dist" / f"declarafacil-extension-{m['version']}{'-tienda' if tienda else ''}.zip"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(RAIZ.rglob("*")):
            rel = f.relative_to(RAIZ)
            if f.is_dir() or rel.parts[0] in FUERA:
                continue
            if rel.as_posix() == "manifest.json":
                z.writestr("manifest.json", json.dumps(m, ensure_ascii=False, indent=2) + "\n")
            else:
                z.write(f, rel.as_posix())
    return destino


if __name__ == "__main__":
    tienda = "--tienda" in sys.argv
    salida = next((Path(a) for a in sys.argv[1:] if not a.startswith("--")), None)
    ruta = empaquetar(tienda, salida)
    with zipfile.ZipFile(ruta) as z:
        print(f"{ruta} ({len(z.namelist())} archivos, {ruta.stat().st_size // 1024} KB)")
