"""Configuración editable de los agentes (modelos, temperatura, activo).

Vive en data/agentes.json para poder cambiar los modelos gratuitos de OpenRouter
—que rotan seguido— sin volver a desplegar.
"""

import json
from typing import Any

from app.config import settings

_EDITABLES = {"modelos", "temperatura", "activo"}


def _ruta():
    return settings.data_dir / "agentes.json"


def todos() -> dict[str, dict[str, Any]]:
    return json.loads(_ruta().read_text(encoding="utf-8"))


def obtener(agente: str) -> dict[str, Any]:
    return todos().get(agente, {})


def actualizar(agente: str, cambios: dict[str, Any]) -> dict[str, Any]:
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
        datos[agente][k] = v
    _ruta().write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos[agente]
