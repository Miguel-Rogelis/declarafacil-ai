"""Carga y guarda las reglas tributarias por año gravable.

Cada año vive en un archivo JSON (data/reglas/agAAAA.json). Para soportar un año
nuevo basta con clonar el anterior y ajustar los valores; el motor no cambia.

Lo que se edita desde la pantalla de administración se guarda en el almacén persistente
(clave «reglas:AAAA») con su historial de versiones, y manda sobre el archivo: así un cambio
sobrevive a los reinicios del servidor y se puede revertir.
"""

import json
from pathlib import Path
from typing import Any

from app import almacen
from app.config import settings

CAMPOS_OBLIGATORIOS = [
    "anio_gravable",
    "uvt",
    "topes_obligacion_uvt",
    "tabla_renta_art241",
    "cedula_general",
    "cedula_pensiones",
    "dividendos",
    "ganancias_ocasionales",
    "anticipo",
    "sanciones",
]


class ReglasNoEncontradas(Exception):
    pass


def _ruta(anio: int) -> Path:
    return settings.reglas_dir / f"ag{anio}.json"


def _clave(anio: int) -> str:
    return f"reglas:{anio}"


def anios_disponibles() -> list[dict[str, Any]]:
    anios = {int(a.stem[2:]) for a in settings.reglas_dir.glob("ag*.json")}
    anios |= {int(k.split(":")[1]) for k in almacen.obtener().claves("reglas:") if k.split(":")[1].isdigit()}
    salida = []
    for anio in sorted(anios, reverse=True):
        datos = cargar(anio)
        salida.append(
            {
                "anio_gravable": datos["anio_gravable"],
                "estado": datos.get("estado", "vigente"),
                "uvt": datos["uvt"],
                "descripcion": datos.get("descripcion", ""),
                "editado": almacen.obtener().leer(_clave(anio)) is not None,
            }
        )
    return salida


def uvt_del_anio(anio: int) -> float | None:
    """UVT vigente en un año calendario (sirve para sanciones del año en que se declara)."""
    ruta = settings.data_dir / "uvt.json"
    if not ruta.exists():
        return None
    valor = json.loads(ruta.read_text(encoding="utf-8")).get("valores", {}).get(str(anio))
    return float(valor) if valor else None


def uvt_provisional(anio: int) -> bool:
    """La UVT de ese año todavía es una estimación (la DIAN aún no publica la resolución)."""
    ruta = settings.data_dir / "uvt.json"
    return ruta.exists() and str(anio) in json.loads(ruta.read_text(encoding="utf-8")).get("provisionales", {})


def cargar(anio: int) -> dict[str, Any]:
    editado = almacen.obtener().leer(_clave(anio))
    if editado is not None:
        return editado
    ruta = _ruta(anio)
    if not ruta.exists():
        raise ReglasNoEncontradas(f"No hay reglas para el año gravable {anio}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def del_archivo(anio: int) -> dict[str, Any] | None:
    """Las reglas tal como vienen en el repositorio (sin los cambios hechos en pantalla)."""
    ruta = _ruta(anio)
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def validar(datos: dict[str, Any]) -> list[str]:
    errores = [f"Falta el campo '{c}'" for c in CAMPOS_OBLIGATORIOS if c not in datos]
    if errores:
        return errores
    if not isinstance(datos["uvt"], (int, float)) or datos["uvt"] <= 0:
        errores.append("La UVT debe ser un número positivo")
    tabla = datos["tabla_renta_art241"]
    if not tabla or tabla[0].get("desde_uvt") != 0:
        errores.append("La tabla del art. 241 debe empezar en 0 UVT")
    for i in range(1, len(tabla)):
        if tabla[i]["desde_uvt"] != tabla[i - 1]["hasta_uvt"]:
            errores.append(f"La tabla del art. 241 tiene un hueco en el tramo {i + 1}")
    return errores


def guardar(anio: int, datos: dict[str, Any], autor: str = "sistema") -> int:
    """Valida y guarda en el almacén persistente. Devuelve el número de versión."""
    datos["anio_gravable"] = anio
    errores = validar(datos)
    if errores:
        raise ValueError("; ".join(errores))
    return almacen.obtener().escribir(_clave(anio), datos, autor)


def revertir(anio: int, version: int | None, autor: str = "sistema") -> dict[str, Any]:
    """Vuelve a una versión anterior del historial, o al archivo del repositorio si version es None."""
    if version is None:
        original = del_archivo(anio)
        if original is None:
            raise ReglasNoEncontradas(f"El año {anio} no tiene archivo en el repositorio")
        almacen.obtener().escribir(_clave(anio), original, f"{autor} (restauró el archivo del repositorio)")
        return original
    v = almacen.obtener().version(version)
    if not v or v.get("clave") != _clave(anio):
        raise ReglasNoEncontradas(f"No hay una versión {version} de las reglas de {anio}")
    guardar(anio, v["datos"], f"{autor} (revirtió a la versión {version})")
    return cargar(anio)


def historial(anio: int, limite: int = 30) -> list[dict[str, Any]]:
    return almacen.obtener().historial(_clave(anio), limite)


def clonar(origen: int, destino: int, uvt: float | None = None, autor: str = "sistema") -> dict[str, Any]:
    existe = _ruta(destino).exists() or almacen.obtener().leer(_clave(destino)) is not None
    if existe:
        raise ValueError(f"Ya existen reglas para {destino}")
    datos = cargar(origen)
    datos["anio_gravable"] = destino
    datos["estado"] = "borrador"
    datos["descripcion"] = f"Borrador creado a partir de {origen}. Revisa UVT, topes y calendario."
    datos["vencimientos"] = {}
    if uvt:
        datos["uvt"] = uvt
    guardar(destino, datos, autor)
    return datos
