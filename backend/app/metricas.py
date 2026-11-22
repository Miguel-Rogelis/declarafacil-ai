"""Métricas de uso y calidad SIN datos personales (HU-41).

Cada evento es un diccionario pequeño con un tipo y campos de una lista cerrada: números,
verdadero/falso y palabras de un conjunto fijo. Nunca entra texto del usuario, montos, cédulas,
nombres ni nombres de archivo: lo que no está en el esquema se descarta antes de guardar.

La sesión es un identificador aleatorio que genera el navegador (cabecera X-Sesion) y que no se
relaciona con la cuenta de la persona. Los eventos se guardan en el almacén (Supabase en
producción) y de ahí salen los KPI (app/kpis.py).
"""

from __future__ import annotations

import math
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app import almacen

sesion: ContextVar[str] = ContextVar("sesion", default="sin-sesion")
# Marcas de lo que pasó en la solicitud actual (las ponen los agentes; las lee quien registra el evento)
_marcas: ContextVar[dict[str, Any] | None] = ContextVar("marcas", default=None)

_RE_SESION = re.compile(r"^[a-f0-9-]{8,40}$")
_RE_MODELO = re.compile(r"^[a-z0-9][a-z0-9./:_-]{1,79}$")

AGENTES = {"lector", "anonimizador", "clasificador", "interprete", "extractor", "conciliador", "motor", "auditor", "explicador", "asistente"}
TIPOS_DOC = {"exogena", "certificado_220", "certificado_bancario", "certificado_vivienda", "certificado_prepagada", "certificado_voluntarios",
             "certificado_cesantias", "certificado_retencion", "predial", "declaracion_anterior", "desconocido"}

# tipo de evento → campo → tipo permitido («n» número, «b» booleano, o un conjunto de palabras)
ESQUEMA: dict[str, dict[str, Any]] = {
    "documentos": {"n": "n", "n_ok": "n", "n_error": "n", "ocr": "n", "ms": "n", "tipos": TIPOS_DOC,
                   "asalariado": "b", "independiente": "b", "pensionado": "b", "capital": "b", "primerizo": "b", "exterior": "b"},
    "liquidacion": {
        "ms": "n", "anio": "n", "formulario": "b", "alertas_criticas": "n", "alertas_advertencia": "n",
        "explicacion_ia": "b", "explicacion_descartada": "b", "casillas_sin_origen": "n", "resultado": {"pagar", "favor", "cero"},
        "asalariado": "b", "independiente": "b", "pensionado": "b", "capital": "b", "primerizo": "b", "exterior": "b",
    },
    "chat": {"ms": "n", "ia_intento": "b", "con_ia": "b", "descartada": "b", "sin_cupo": "b", "error_ia": "b", "tokens_entrada": "n",
             "calcular": "b", "pregunta": "b"},
    "ia": {"agente": AGENTES, "modelo": "modelo", "resultado": {"ok", "error", "sin_cupo", "cache"}, "tokens_entrada": "n",
           "tokens_salida": "n", "costo_usd": "n", "ms": "n"},
    "http": {"ruta": "ruta", "estado": "n", "ms": "n"},
}


def _valor(regla: Any, v: Any) -> Any:
    """El valor si cumple el esquema; None si no (y entonces se descarta)."""
    if regla == "n":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        return round(float(v), 6)
    if regla == "b":
        return v if isinstance(v, bool) else None
    if regla == "modelo":
        return v if isinstance(v, str) and _RE_MODELO.match(v) else None
    if regla == "ruta":  # plantilla de la ruta de la API, sin valores (/api/reglas/{anio})
        return v if isinstance(v, str) and re.fullmatch(r"/api(/[a-z0-9_{}.-]+){0,4}", v) else None
    if isinstance(regla, set):
        if isinstance(v, str):
            return v if v in regla else None
        if isinstance(v, (list, tuple)):
            return [x for x in v if isinstance(x, str) and x in regla] or None
    return None


def limpiar(tipo: str, campos: dict[str, Any]) -> dict[str, Any] | None:
    esquema = ESQUEMA.get(tipo)
    if esquema is None:
        return None
    limpio = {}
    for k, v in campos.items():
        if k in esquema and (x := _valor(esquema[k], v)) is not None:
            limpio[k] = x
    return limpio


def registrar(tipo: str, **campos: Any) -> dict[str, Any] | None:
    limpio = limpiar(tipo, campos)
    if limpio is None:
        return None
    evento = {"tipo": tipo, "sesion": sesion.get(), "creado": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **limpio}
    almacen.obtener().agregar_eventos([evento])
    return evento


def fijar_sesion(valor: str | None) -> None:
    v = (valor or "").strip().lower()
    sesion.set(v if _RE_SESION.match(v) else "sin-sesion")
    _marcas.set({})


def marcar(**marcas: Any) -> None:
    """Los agentes anotan lo que pasó (p. ej. descartada=True) sin conocer quién registra el evento."""
    actual = _marcas.get()
    if actual is None:
        actual = {}
        _marcas.set(actual)
    for k, v in marcas.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(actual.get(k), (int, float)):
            actual[k] += v  # los contadores se suman (p. ej. tokens de varias llamadas)
        else:
            actual[k] = v


def marcas() -> dict[str, Any]:
    return dict(_marcas.get() or {})
