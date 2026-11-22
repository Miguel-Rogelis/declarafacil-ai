"""Cupo de uso de la IA, para que un link público no se coma las llamadas gratis del día.

- Por persona: máximo IA_POR_HORA llamadas en la última hora (la persona es su usuario si inició
  sesión o, si no, su dirección IP).
- En total: máximo IA_TOPE_DIARIO llamadas por día (hora de Colombia), un poco por debajo del
  cupo gratis de OpenRouter.
Los valores por defecto dependen del perfil de modelos: con los gratis, 15 por hora y 45 al día; con
los de pago (PERFIL_MODELOS=pago), 40 por hora y 3000 al día, que alcanzan para el pico de temporada
(95 declaraciones al día × ~14 llamadas) con un techo de gasto de unos USD 45 diarios (HU-40).
Cuando se pasa cualquiera de los dos, el agente responde sin IA (con reglas), que también funciona.
Los contadores viven en memoria y se copian al almacén persistente cada pocos segundos (clave
«cupo:estado»), así un reinicio del servidor no regala el cupo del día. Quién llama se guarda
solo como una huella (hash) de su usuario o IP, nunca la IP.
"""

import hashlib
import os
import threading
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from app import almacen
from app.config import settings

_PAGO = settings.perfil_modelos == "pago"
POR_HORA = int(os.getenv("IA_POR_HORA", "40" if _PAGO else "15"))
TOPE_DIARIO = int(os.getenv("IA_TOPE_DIARIO", "3000" if _PAGO else "45"))

_COLOMBIA = timezone(timedelta(hours=-5))

# Quién hace la solicitud y si en esta solicitud ya se negó la IA (los pone el middleware de main.py)
quien: ContextVar[str] = ContextVar("quien", default="anonimo")
sin_ia: ContextVar[bool] = ContextVar("sin_ia", default=False)  # el modo demo pide respuestas sin IA
limitado: ContextVar[bool] = ContextVar("limitado", default=False)

_por_persona: dict[str, deque[float]] = defaultdict(deque)
_dia = {"fecha": "", "usadas": 0}
_estado = {"cargado": False, "guardado": 0.0}
_CADA = 5.0  # segundos entre copias al almacén


def _hoy() -> str:
    return datetime.now(_COLOMBIA).date().isoformat()


def _huella(q: str) -> str:
    sal = os.getenv("ADMIN_TOKEN", "declarafacil")
    return hashlib.sha256((sal + q).encode()).hexdigest()[:16]


def _cargar() -> None:
    _estado["cargado"] = True
    guardado = almacen.obtener().leer("cupo:estado") or {}
    if guardado.get("fecha") == _hoy():
        _dia.update(fecha=guardado["fecha"], usadas=int(guardado.get("usadas", 0)))
    ahora = time.time()
    for h, marcas in (guardado.get("personas") or {}).items():
        _por_persona[h] = deque(t for t in marcas if ahora - t <= 3600)


def _guardar(forzar: bool = False) -> None:
    ahora = time.time()
    if not forzar and ahora - _estado["guardado"] < _CADA:
        return
    _estado["guardado"] = ahora
    personas = {h: list(m) for h, m in _por_persona.items() if m and ahora - m[-1] <= 3600}
    datos = {"fecha": _dia["fecha"], "usadas": _dia["usadas"], "personas": personas}

    def escribir() -> None:
        try:
            almacen.obtener().escribir("cupo:estado", datos, "cupo", historial=False)
        except Exception:  # noqa: BLE001 - si el almacén falla, el cupo sigue en memoria
            pass

    if almacen.obtener().nombre == "supabase":
        threading.Thread(target=escribir, daemon=True).start()  # no frena la respuesta
    else:
        escribir()


def reservar() -> bool:
    """Cuenta una llamada a la IA si hay cupo. Devuelve False si no hay (y marca la solicitud como limitada)."""
    if sin_ia.get():
        return False
    if not _estado["cargado"]:
        _cargar()
    ahora = time.time()
    if _dia["fecha"] != _hoy():
        _dia.update(fecha=_hoy(), usadas=0)
    llamadas = _por_persona[_huella(quien.get())]
    while llamadas and ahora - llamadas[0] > 3600:
        llamadas.popleft()
    if len(llamadas) >= POR_HORA or _dia["usadas"] >= TOPE_DIARIO:
        limitado.set(True)
        return False
    llamadas.append(ahora)
    _dia["usadas"] += 1
    _guardar()
    return True


def restante_hoy() -> int:
    return TOPE_DIARIO if _dia["fecha"] != _hoy() else max(0, TOPE_DIARIO - _dia["usadas"])


def reiniciar() -> None:
    """Para las pruebas."""
    _por_persona.clear()
    _dia.update(fecha="", usadas=0)
    _estado.update(cargado=True, guardado=0.0)
