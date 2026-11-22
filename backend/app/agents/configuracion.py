"""Configuración editable de los agentes (modelos, temperatura, activo).

Vive en data/agentes.json (perfil «gratis») o data/agentes_pago.json (perfil «pago», para el
piloto) para poder cambiar los modelos de OpenRouter —los gratuitos rotan seguido— sin volver
a desplegar. Lo que se cambia desde la pantalla se guarda en el almacén persistente (clave
«agentes:<perfil>») con su historial, así sobrevive a los reinicios y se puede revertir.
"""

import json
from typing import Any

from app import almacen
from app.config import settings

_EDITABLES = {"modelos", "temperatura", "activo", "sin_retencion"}


def perfil() -> str:
    return "pago" if settings.perfil_modelos == "pago" else "gratis"


def _ruta():
    return settings.data_dir / ("agentes_pago.json" if perfil() == "pago" else "agentes.json")


def _clave() -> str:
    return f"agentes:{perfil()}"


def del_archivo() -> dict[str, dict[str, Any]]:
    return json.loads(_ruta().read_text(encoding="utf-8"))


def todos() -> dict[str, dict[str, Any]]:
    editado = almacen.obtener().leer(_clave())
    return editado if editado is not None else del_archivo()


def obtener(agente: str) -> dict[str, Any]:
    return todos().get(agente, {})


def actualizar(agente: str, cambios: dict[str, Any], autor: str = "sistema") -> dict[str, Any]:
    datos = todos()
    if agente not in datos:
        raise KeyError(agente)
    if not datos[agente].get("usa_ia") and ({"modelos", "temperatura"} & cambios.keys()):
        raise ValueError("Este agente no usa IA; no tiene modelos que configurar")
    for k, v in cambios.items():
        if k not in _EDITABLES:
            raise ValueError(f"El campo '{k}' no se puede editar")
        if k == "modelos":
            if not isinstance(v, list) or not v or not all(isinstance(m, str) and m.strip() for m in v):
                raise ValueError("'modelos' debe ser una lista no vacía de identificadores")
            v = [m.strip() for m in v][:6]
        if k == "temperatura" and not (0 <= float(v) <= 1.5):
            raise ValueError("La temperatura debe estar entre 0 y 1.5")
        if k in ("activo", "sin_retencion") and not isinstance(v, bool):
            raise ValueError(f"'{k}' debe ser verdadero o falso")
        datos[agente][k] = v
    almacen.obtener().escribir(_clave(), datos, autor)
    return datos[agente]


def historial(limite: int = 30) -> list[dict[str, Any]]:
    return almacen.obtener().historial(_clave(), limite)


def revertir(version: int | None, autor: str = "sistema") -> dict[str, dict[str, Any]]:
    """Vuelve a una versión del historial, o al archivo del repositorio si version es None."""
    if version is None:
        datos = del_archivo()
        almacen.obtener().escribir(_clave(), datos, f"{autor} (restauró el archivo del repositorio)")
        return datos
    v = almacen.obtener().version(version)
    if not v or v.get("clave") != _clave():
        raise KeyError(version)
    almacen.obtener().escribir(_clave(), v["datos"], f"{autor} (revirtió a la versión {version})")
    return v["datos"]
