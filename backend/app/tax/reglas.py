"""Carga y guarda las reglas tributarias por año gravable.

Cada año vive en un archivo JSON (data/reglas/agAAAA.json). Para soportar un año
nuevo basta con clonar el anterior y ajustar los valores; el motor no cambia.
"""

import json
from pathlib import Path
from typing import Any

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


def anios_disponibles() -> list[dict[str, Any]]:
    salida = []
    for archivo in sorted(settings.reglas_dir.glob("ag*.json"), reverse=True):
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        salida.append(
            {
                "anio_gravable": datos["anio_gravable"],
                "estado": datos.get("estado", "vigente"),
                "uvt": datos["uvt"],
                "descripcion": datos.get("descripcion", ""),
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


def cargar(anio: int) -> dict[str, Any]:
    ruta = _ruta(anio)
    if not ruta.exists():
        raise ReglasNoEncontradas(f"No hay reglas para el año gravable {anio}")
    return json.loads(ruta.read_text(encoding="utf-8"))


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


def guardar(anio: int, datos: dict[str, Any]) -> None:
    datos["anio_gravable"] = anio
    errores = validar(datos)
    if errores:
        raise ValueError("; ".join(errores))
    _ruta(anio).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def clonar(origen: int, destino: int, uvt: float | None = None) -> dict[str, Any]:
    if _ruta(destino).exists():
        raise ValueError(f"Ya existen reglas para {destino}")
    datos = cargar(origen)
    datos["anio_gravable"] = destino
    datos["estado"] = "borrador"
    datos["descripcion"] = f"Borrador creado a partir de {origen}. Revisa UVT, topes y calendario."
    datos["vencimientos"] = {}
    if uvt:
        datos["uvt"] = uvt
    guardar(destino, datos)
    return datos
